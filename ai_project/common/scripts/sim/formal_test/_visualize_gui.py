#!/usr/bin/env python3
"""
GUI Visualization Dashboard for Vulnerability Prediction
=========================================================
Real-time training monitor with:
  - Loss curve (train)
  - F1 score progression
  - Vulnerability heatmap on a sample circuit graph / BLIF design

Modes:
  analyze   Load model checkpoint + training history → static plots
  live      Background training + real-time Loss/F1 curves
  infer     Single BLIF file → gate-level vulnerability heatmap

Usage:
    # Analyze mode
    python _visualize_gui.py --mode analyze \
        --model data/models/SAGE2-Lite-64.pth \
        --history data/local_training_summary.json

    # Live mode
    python _visualize_gui.py --mode live \
        --checkpoint data/models/local_best_model.pt

    # Infer mode (BLIF file)
    python _visualize_gui.py --mode infer \
        --model data/models/SAGE2-Lite-64.pth \
        --blif blifs/design.blif

    # Override data path / model type
    python _visualize_gui.py --mode analyze \
        --data data/training_data_15feat.pt \
        --model-type auto

Requires: matplotlib, networkx, PyTorch Geometric, tkinter
"""

import os
import sys
import json
import time
import threading
import argparse
from collections import deque

import numpy as np
import torch
import torch.nn as nn
from torch_geometric.data import DataLoader

# ── Import shared model definitions & inference engine ─────────────────────
try:
    from gnn_inference import GNNInference, SAGE3, SAGE2Lite, MODEL_REGISTRY
except ImportError:
    # Fallback: define stubs so the file can at least be parsed for help
    GNNInference = None
    SAGE3 = None
    SAGE2Lite = None
    MODEL_REGISTRY = None

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data_15feat.pt')
MODELS_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
DEFAULT_SUMMARY_PATH = os.path.join(SCRIPT_DIR, 'data', 'local_training_summary.json')


# ======================================================================
# Focal Loss (kept local for training runner)
# ======================================================================
class FocalLoss(nn.Module):
    def __init__(self, alpha=0.75, gamma=2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, inputs, targets):
        bce = nn.functional.binary_cross_entropy_with_logits(
            inputs, targets, reduction='none')
        pt = torch.exp(-bce)
        alpha_t = self.alpha * targets + (1 - self.alpha) * (1 - targets)
        return (alpha_t * (1 - pt) ** self.gamma * bce).mean()


# ======================================================================
# Metrics helper
# ======================================================================
def compute_metrics(scores, labels, threshold=0.5):
    from sklearn.metrics import f1_score, precision_score, recall_score
    preds = (scores >= threshold).float()
    binary_labels = (labels >= threshold).float()
    return {
        'f1': f1_score(binary_labels.numpy(), preds.numpy(), zero_division=0),
        'precision': precision_score(binary_labels.numpy(), preds.numpy(), zero_division=0),
        'recall': recall_score(binary_labels.numpy(), preds.numpy(), zero_division=0),
    }


# ======================================================================
# Heatmap helper — sample graph with node vulnerability scores
# ======================================================================
def get_heatmap_data(model, test_data, device='cpu', num_samples=5):
    """Run inference on sample test graphs and return node scores + layout."""
    model = model.to(device)
    model.eval()
    results = []

    for idx in range(min(num_samples, len(test_data))):
        data = test_data[idx].to(device)
        with torch.no_grad():
            scores = torch.sigmoid(model(data.x, data.edge_index)).cpu().numpy()

        # Build layout using networkx spring layout
        try:
            import networkx as nx
            G = nx.DiGraph()
            src = data.edge_index[0].tolist()
            dst = data.edge_index[1].tolist()
            for s, d in zip(src, dst):
                G.add_edge(s, d)
            pos = nx.spring_layout(G.to_undirected(), k=1.5, iterations=30, seed=42)
        except Exception:
            pos = None

        results.append({
            'idx': idx,
            'num_nodes': data.num_nodes,
            'scores': scores,
            'labels': data.y.cpu().numpy(),
            'pos': pos,
            'edge_index': data.edge_index,
        })

    return results


# ======================================================================
# Training Runner (background thread for live mode)
# ======================================================================
class TrainingRunner(threading.Thread):
    """Runs training in a background thread, pushing metrics to a queue."""

    def __init__(self, train_data, val_data, model, callback, device='cpu',
                 epochs=400, patience=50, lr=1e-3, focal_alpha=0.228,
                 batch_size=32):
        super().__init__(daemon=True)
        self.train_data = train_data
        self.val_data = val_data
        self.model = model
        self.callback = callback
        self.device = device
        self.epochs = epochs
        self.patience = patience
        self.lr = lr
        self.focal_alpha = focal_alpha
        self.batch_size = batch_size
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        device = self.device
        model = self.model.to(device)
        criterion = FocalLoss(alpha=self.focal_alpha, gamma=2.0)
        optimizer = torch.optim.AdamW(model.parameters(), lr=self.lr, weight_decay=5e-4)

        train_loader = DataLoader(self.train_data, batch_size=self.batch_size, shuffle=True)
        val_loader = DataLoader(self.val_data, batch_size=self.batch_size, shuffle=False)

        best_f1 = 0.0
        best_state = None
        patience_counter = 0

        for epoch in range(1, self.epochs + 1):
            if self._stop.is_set():
                break

            # Train
            model.train()
            total_loss = 0.0
            for batch in train_loader:
                batch = batch.to(device)
                optimizer.zero_grad()
                logits = model(batch.x, batch.edge_index)
                loss = criterion(logits, batch.y.float())
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
            avg_loss = total_loss / len(train_loader)

            # Validate
            model.eval()
            all_s, all_l = [], []
            with torch.no_grad():
                for batch in val_loader:
                    batch = batch.to(device)
                    logits = model(batch.x, batch.edge_index)
                    all_s.append(torch.sigmoid(logits).cpu())
                    all_l.append(batch.y.cpu())
            val_scores = torch.cat(all_s)
            val_labels = torch.cat(all_l)

            best_val_f1 = max(
                (compute_metrics(val_scores, val_labels, threshold=th)['f1']
                 for th in [x / 100 for x in range(10, 91, 2)]),
                default=0.0
            )

            if best_val_f1 > best_f1:
                best_f1 = best_val_f1
                best_state = {k: v.cpu() for k, v in model.state_dict().items()}
                patience_counter = 0
            else:
                patience_counter += 1

            # Callback
            self.callback(epoch, {
                'train_loss': avg_loss,
                'val_f1': best_val_f1,
                'best_f1': best_f1,
                'patience': patience_counter,
            })

            if patience_counter >= self.patience:
                print(f'  [Trainer] Early stopping at epoch {epoch}')
                break

        # Save best model
        if best_state:
            os.makedirs(MODELS_DIR, exist_ok=True)
            torch.save(best_state, os.path.join(MODELS_DIR, 'gui_best_model.pt'))
            model.load_state_dict(best_state)


# ======================================================================
# BLIF Heatmap helper — visualise vulnerability on BLIF-derived graphs
# ======================================================================
def get_blif_heatmap(gnn_engine, blif_path):
    """Run inference on a BLIF file and return node positions + scores."""
    data = gnn_engine.converter.convert(blif_path)
    scores = gnn_engine.infer(data)

    # Build layout
    try:
        import networkx as nx
        G = nx.DiGraph()
        src = data.edge_index[0].tolist()
        dst = data.edge_index[1].tolist()
        for s, d in zip(src, dst):
            G.add_edge(s, d)
        pos = nx.spring_layout(G.to_undirected(), k=1.5, iterations=30, seed=42)
    except Exception:
        pos = None

    return {
        'design_name': getattr(data, 'design_name',
                                os.path.splitext(os.path.basename(blif_path))[0]),
        'num_nodes': data.num_nodes,
        'scores': scores.numpy(),
        'pos': pos,
        'edge_index': data.edge_index,
        'source_file': blif_path,
    }


# ======================================================================
# Matplotlib GUI
# ======================================================================
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.colors as mcolors
try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    import tkinter as tk
    from tkinter import ttk


class VulnerabilityDashboard:
    """Tkinter + Matplotlib dashboard for training / inference visualization."""

    def __init__(self, mode='analyze', checkpoint_path=None, history_path=None,
                 model_type='auto', data_path=None, blif_path=None):
        self.mode = mode
        self.checkpoint_path = checkpoint_path
        self.history_path = history_path
        self.model_type = model_type
        self.data_path = data_path or DATA_PATH
        self.blif_path = blif_path

        # Training state (for live mode)
        self.train_runner = None
        self.loss_history = deque(maxlen=500)
        self.f1_history = deque(maxlen=500)
        self.epoch_history = deque(maxlen=500)
        self.best_f1 = 0.0

        # Data
        self.test_data = None
        self.model = None
        self.heatmap_results = None

        # GNNInference engine (used for infer mode and model loading)
        self.gnn_engine = None

        # ── Build UI ──
        self.root = tk.Tk()
        self.root.title('Circuit Vulnerability Prediction Dashboard')
        self.root.geometry('1400x900')
        self.root.configure(bg='#1e1e2e')

        # Style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', background='#1e1e2e', foreground='#cdd6f4',
                        font=('Segoe UI', 10))
        style.configure('TFrame', background='#1e1e2e')
        style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'),
                        foreground='#cba6f7')
        style.configure('Status.TLabel', font=('Segoe UI', 11),
                        foreground='#a6e3a1')

        # ── Top status bar ──
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=(10, 0))

        mode_label = {'analyze': 'Analysis', 'live': 'Live Training',
                       'infer': 'BLIF Inference'}.get(mode, mode.capitalize())
        self.header_label = ttk.Label(
            top_frame, text=f'Circuit Vulnerability Prediction — {mode_label}',
            style='Header.TLabel')
        self.header_label.pack(side=tk.LEFT)

        self.status_label = ttk.Label(top_frame, text='Status: Ready',
                                      style='Status.TLabel')
        self.status_label.pack(side=tk.RIGHT)

        # ── Control buttons ──
        ctrl_frame = ttk.Frame(self.root)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=5)

        if mode == 'live':
            self.start_btn = ttk.Button(
                ctrl_frame, text='Start Training', command=self._start_training)
            self.start_btn.pack(side=tk.LEFT, padx=5)
            self.stop_btn = ttk.Button(
                ctrl_frame, text='Stop', command=self._stop_training, state=tk.DISABLED)
            self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.refresh_btn = ttk.Button(
            ctrl_frame, text='Refresh Heatmap', command=self._refresh_heatmap)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)

        self.export_btn = ttk.Button(
            ctrl_frame, text='Export Plot', command=self._export_plot)
        self.export_btn.pack(side=tk.LEFT, padx=5)

        # Information display
        self.info_var = tk.StringVar(value='No model loaded')
        info_label = ttk.Label(ctrl_frame, textvariable=self.info_var,
                               font=('Segoe UI', 9, 'italic'))
        info_label.pack(side=tk.RIGHT, padx=10)

        # ── Matplotlib figure ──
        fig_frame = ttk.Frame(self.root)
        fig_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.fig = plt.Figure(figsize=(14, 8), dpi=100,
                              facecolor='#1e1e2e')
        self.fig.subplots_adjust(hspace=0.4, wspace=0.3,
                                 left=0.06, right=0.97,
                                 top=0.94, bottom=0.06)

        # Subplot layout: Loss (top-left), F1 (top-right), Heatmap (bottom)
        self.ax_loss = self.fig.add_subplot(2, 2, 1, facecolor='#181825')
        self.ax_f1 = self.fig.add_subplot(2, 2, 2, facecolor='#181825')
        self.ax_heatmap = self.fig.add_subplot(2, 2, (3, 4), facecolor='#181825')

        self._style_axes()

        self.canvas = FigureCanvasTkAgg(self.fig, master=fig_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar = NavigationToolbar2Tk(self.canvas, fig_frame)
        toolbar.config(background='#313244')
        toolbar.update()

        # ── Init plots ──
        self.loss_line = None
        self.f1_line = None
        self.scatter_plot = None
        self._init_plots()

        # ── Load data ──
        if mode == 'analyze':
            self._load_for_analysis()
        elif mode == 'infer':
            self._load_for_infer()

        # ── Periodic update ──
        self._update_timer()

    # ------------------------------------------------------------------
    def _style_axes(self):
        """Apply dark theme to axes."""
        for ax in [self.ax_loss, self.ax_f1, self.ax_heatmap]:
            ax.spines['bottom'].set_color('#45475a')
            ax.spines['top'].set_color('#45475a')
            ax.spines['left'].set_color('#45475a')
            ax.spines['right'].set_color('#45475a')
            ax.tick_params(colors='#cdd6f4', labelsize=9)
            ax.xaxis.label.set_color('#cdd6f4')
            ax.yaxis.label.set_color('#cdd6f4')
            ax.title.set_color('#cba6f7')

    # ------------------------------------------------------------------
    def _init_plots(self):
        """Initialize empty plots."""
        self.ax_loss.set_title('Training Loss', fontsize=13, fontweight='bold')
        self.ax_loss.set_xlabel('Epoch')
        self.ax_loss.set_ylabel('Loss')
        self.ax_loss.set_xlim(0, 10)
        self.ax_loss.set_ylim(0, 1)
        self.ax_loss.grid(True, alpha=0.15, color='#585b70')
        self.loss_line, = self.ax_loss.plot([], [], color='#89b4fa',
                                             linewidth=2, label='Train Loss')

        self.ax_f1.set_title('Validation F1 Score', fontsize=13, fontweight='bold')
        self.ax_f1.set_xlabel('Epoch')
        self.ax_f1.set_ylabel('F1')
        self.ax_f1.set_xlim(0, 10)
        self.ax_f1.set_ylim(0, 1)
        self.ax_f1.grid(True, alpha=0.15, color='#585b70')
        self.f1_line, = self.ax_f1.plot([], [], color='#a6e3a1',
                                         linewidth=2, label='Val F1')
        self.best_f1_line = self.ax_f1.axhline(y=0, color='#f9e2af',
                                                linestyle='--', linewidth=1,
                                                label='Best F1')

        self.ax_heatmap.set_title('Vulnerability Heatmap — Sample Circuit',
                                  fontsize=13, fontweight='bold')
        self.ax_heatmap.set_xlabel('Node Position')
        self.ax_heatmap.set_ylabel('Node Position')

    # ------------------------------------------------------------------
    def _detect_model_arch(self, checkpoint_path):
        """Detect model architecture from checkpoint file."""
        if not os.path.exists(checkpoint_path):
            return None, None
        try:
            ckpt = torch.load(checkpoint_path, map_location='cpu',
                               weights_only=True)
            if GNNInference is not None:
                arch_name, model_cls, h_channels = \
                    GNNInference._detect_model_config(ckpt, self.model_type)
                in_channels = GNNInference._detect_in_channels(ckpt)
                return model_cls, {'arch': arch_name, 'hidden': h_channels,
                                    'in_channels': in_channels}
            else:
                # Fallback: SAGE3
                return SAGE3, {'arch': 'SAGE3', 'hidden': 128, 'in_channels': 12}
        except Exception as e:
            print(f'  [WARN] Could not detect model arch: {e}')
            return None, None

    # ------------------------------------------------------------------
    def _load_model_from_checkpoint(self, checkpoint_path):
        """Load a model from checkpoint with architecture detection."""
        if not os.path.exists(checkpoint_path):
            return None

        try:
            model_cls, info = self._detect_model_arch(checkpoint_path)
            if model_cls is None:
                model_cls = SAGE3
                info = {'arch': 'SAGE3', 'hidden': 128, 'in_channels': 12}

            in_c = info['in_channels']
            h_c = info['hidden']
            model = model_cls(in_channels=in_c, hidden_channels=h_c)

            ckpt = torch.load(checkpoint_path, map_location='cpu',
                               weights_only=False)
            # Handle nested / prefixed state dicts
            if isinstance(ckpt, dict):
                state = ckpt
                # Strip 'model.' prefix if present
                if any(k.startswith('model.') for k in state.keys()):
                    state = {k[6:]: v for k, v in state.items() if k.startswith('model.')}
                try:
                    model.load_state_dict(state)
                except Exception:
                    # Try full checkpoint with 'state_dict' key
                    if 'state_dict' in ckpt:
                        model.load_state_dict(ckpt['state_dict'])
                    else:
                        print('  [WARN] Could not load state dict, using untrained model')
                        return None

            model.eval()
            self.info_var.set(f'Loaded: {os.path.basename(checkpoint_path)} '
                              f'({info["arch"]}, {info["in_channels"]}->{info["hidden"]}d)')
            return model
        except Exception as e:
            print(f'  [WARN] Could not load checkpoint {checkpoint_path}: {e}')
            return None

    # ------------------------------------------------------------------
    def _load_for_analysis(self):
        """Load checkpoint and data for analysis mode."""
        # Load training data
        if os.path.exists(self.data_path):
            try:
                raw = torch.load(self.data_path, map_location='cpu',
                                  weights_only=False)
                self.test_data = raw.get('test', raw.get('val', None))
                if self.test_data is None:
                    # Single dataset — use as is
                    if isinstance(raw, dict):
                        keys = [k for k in raw.keys() if k != 'config']
                        if keys:
                            self.test_data = raw[keys[0]]
                if self.test_data is not None:
                    n = len(self.test_data) if hasattr(self.test_data, '__len__') else 1
                    self.status_label.configure(text=f'Status: Loaded {n} test samples')
                else:
                    self.status_label.configure(text='Status: No test data found in file')
            except Exception as e:
                self.status_label.configure(text=f'Status: Error loading data: {str(e)[:40]}')
                return
        else:
            self.status_label.configure(text='Status: No test data found')
            return

        # Load history if available
        hist_path = self.history_path or DEFAULT_SUMMARY_PATH
        if os.path.exists(hist_path):
            try:
                with open(hist_path) as f:
                    history = json.load(f)
                    self._plot_history_from_json(history)
                    self.status_label.configure(
                        text=f'Status: Loaded history from {os.path.basename(hist_path)}')
            except Exception as e:
                print(f'  [WARN] Could not load history: {e}')

        # Load model
        ckpt = self.checkpoint_path or os.path.join(MODELS_DIR, 'local_best_model.pt')
        self.model = self._load_model_from_checkpoint(ckpt)
        if self.model is not None:
            self.status_label.configure(text='Status: Model loaded, generating heatmap...')
            self._refresh_heatmap()
        else:
            self.info_var.set('No checkpoint found')
            self.status_label.configure(text='Status: No model checkpoint')

    # ------------------------------------------------------------------
    def _load_for_infer(self):
        """Load model and BLIF file for inference mode."""
        # Initialise GNNInference engine
        if GNNInference is not None:
            self.gnn_engine = GNNInference(threshold=0.05)

            model_type = None if self.model_type == 'auto' else self.model_type
            ckpt = self.checkpoint_path or os.path.join(MODELS_DIR, 'local_best_model.pt')

            if self.gnn_engine.load_model(ckpt, model_type=model_type):
                info = self.gnn_engine.model_info
                self.info_var.set(
                    f'{info.get("architecture", "?")} ({info.get("in_channels", "?")}d)')
                self.status_label.configure(
                    text=f'Status: Model loaded — {os.path.basename(ckpt)}')
            else:
                self.status_label.configure(text='Status: Failed to load model')
                return
        else:
            self.status_label.configure(text='Status: GNNInference not available')
            return

        # Run BLIF inference
        if self.blif_path and os.path.exists(self.blif_path):
            self._run_blif_inference(self.blif_path)
        else:
            self.status_label.configure(text='Status: No BLIF file specified')

    # ------------------------------------------------------------------
    def _plot_history_from_json(self, history):
        """Plot metrics from a saved JSON summary."""
        seed_results = history.get('seed_results', {})
        if not seed_results:
            return

        best_f1 = history.get('best_f1', 0)
        self.best_f1_line.set_ydata([best_f1])
        self.ax_f1.set_ylim(0, max(1.0, best_f1 * 1.2))

        # Show config info
        config = history.get('config', {})
        info_parts = []
        if config:
            info_parts.append(f'Samples: {config.get("samples", "?")}')
            if config.get('positive_ratio'):
                info_parts.append(f'Pos ratio: {config["positive_ratio"]:.1%}')
            info_parts.append(f'Best F1: {best_f1:.4f}')
        self.info_var.set(' | '.join(info_parts))
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    def _update_plots(self, epoch=None, metrics=None):
        """Update line plots with new data point."""
        if metrics is not None:
            self.epoch_history.append(epoch)
            self.loss_history.append(metrics['train_loss'])
            self.f1_history.append(metrics['val_f1'])
            if metrics['best_f1'] > self.best_f1:
                self.best_f1 = metrics['best_f1']

        epochs_arr = list(self.epoch_history)
        loss_arr = list(self.loss_history)
        f1_arr = list(self.f1_history)

        if len(epochs_arr) < 2:
            return

        # Loss plot
        self.loss_line.set_data(epochs_arr, loss_arr)
        self.ax_loss.set_xlim(0, max(epochs_arr) + 5)
        self.ax_loss.set_ylim(0, max(loss_arr) * 1.3 + 0.05)

        # F1 plot
        self.f1_line.set_data(epochs_arr, f1_arr)
        self.ax_f1.set_xlim(0, max(epochs_arr) + 5)
        self.ax_f1.set_ylim(0, 1.0)
        self.best_f1_line.set_ydata([self.best_f1])

        # Update status
        if metrics:
            self.status_label.configure(
                text=f'Epoch {epoch} | Loss: {metrics["train_loss"]:.4f} | '
                     f'F1: {metrics["val_f1"]:.4f} | Best: {self.best_f1:.4f}')

        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    def _refresh_heatmap(self):
        """Generate and plot vulnerability heatmap (from training data or BLIF)."""
        if self.mode == 'infer':
            if self.blif_path and os.path.exists(self.blif_path):
                self._run_blif_inference(self.blif_path)
            return

        if self.model is None or self.test_data is None:
            self.status_label.configure(text='Status: Load a model first')
            return

        self.status_label.configure(text='Status: Generating heatmap...')
        self.root.update()

        try:
            results = get_heatmap_data(self.model, self.test_data,
                                       device='cpu', num_samples=5)

            # Pick the most interesting sample
            results.sort(key=lambda r: abs(r['scores'].std() - 0.5) + r['num_nodes'] / 1000,
                         reverse=True)
            r = results[0]

            self.ax_heatmap.cla()
            self._style_axes()
            self.ax_heatmap.set_title(
                f'Vulnerability Heatmap — Sample #{r["idx"]} '
                f'({r["num_nodes"]} nodes)',
                fontsize=13, fontweight='bold', color='#cba6f7')

            if r['pos'] is not None:
                pos = r['pos']
                scores = r['scores']
                labels = r['labels']

                from sklearn.metrics import mean_squared_error, r2_score
                mse = mean_squared_error(labels, scores)
                r2 = r2_score(labels, scores)
                corr = np.corrcoef(labels, scores)[0, 1] if len(labels) > 1 else 0

                # Draw edges
                src = r['edge_index'][0].tolist()
                dst = r['edge_index'][1].tolist()
                for s, d in zip(src, dst):
                    if s in pos and d in pos:
                        xs = [pos[s][0], pos[d][0]]
                        ys = [pos[s][1], pos[d][1]]
                        self.ax_heatmap.plot(xs, ys, color='#45475a',
                                             linewidth=0.3, alpha=0.4, zorder=1)

                # Draw nodes with vulnerability color
                node_pos = np.array([pos[i] for i in range(len(pos))])
                sc = self.ax_heatmap.scatter(
                    node_pos[:, 0], node_pos[:, 1],
                    c=scores, cmap='viridis', vmin=0, vmax=1,
                    s=40, edgecolors='#cdd6f4', linewidth=0.3,
                    alpha=0.85, zorder=2)

                # Colorbar
                cbar = self.fig.colorbar(sc, ax=self.ax_heatmap,
                                          shrink=0.7, pad=0.02)
                cbar.set_label('Predicted Vulnerability', color='#cdd6f4')
                cbar.ax.tick_params(colors='#cdd6f4')

                self.ax_heatmap.set_xlabel('Node Position')
                self.ax_heatmap.set_ylabel('Node Position')
                self.ax_heatmap.set_aspect('equal')

                # Stats
                self.ax_heatmap.text(
                    0.02, 0.98,
                    f'MSE: {mse:.4f}  |  R2: {r2:.4f}  |  Corr: {corr:.4f}',
                    transform=self.ax_heatmap.transAxes,
                    color='#a6e3a1', fontsize=10, va='top',
                    bbox=dict(boxstyle='round', facecolor='#313244',
                              edgecolor='#585b70', alpha=0.8))
            else:
                # Fallback: histogram
                self.ax_heatmap.hist(r['scores'], bins=30, color='#89b4fa',
                                     alpha=0.7, edgecolor='#1e1e2e')
                self.ax_heatmap.set_xlabel('Vulnerability Score')
                self.ax_heatmap.set_ylabel('Node Count')
                self.ax_heatmap.set_title(
                    f'Vulnerability Score Distribution — Sample #{r["idx"]}',
                    fontsize=13, fontweight='bold', color='#cba6f7')

            self.status_label.configure(text='Status: Heatmap ready')
            self.canvas.draw_idle()

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status_label.configure(text=f'Status: Heatmap error: {str(e)[:50]}')

    # ------------------------------------------------------------------
    def _run_blif_inference(self, blif_path):
        """Run BLIF inference and plot vulnerability heatmap."""
        if self.gnn_engine is None or self.gnn_engine.model is None:
            self.status_label.configure(text='Status: No model loaded')
            return

        self.status_label.configure(text=f'Status: Analysing {os.path.basename(blif_path)}...')
        self.root.update()

        try:
            result = get_blif_heatmap(self.gnn_engine, blif_path)
            self.heatmap_results = result

            self.ax_heatmap.cla()
            self._style_axes()

            title = (f'BLIF Vulnerability Heatmap — {result["design_name"]} '
                     f'({result["num_nodes"]} nodes)')
            self.ax_heatmap.set_title(title, fontsize=13, fontweight='bold',
                                      color='#cba6f7')

            scores = result['scores']
            num_vuln = int((scores >= 0.05).sum())
            vuln_ratio = num_vuln / max(result['num_nodes'], 1)

            if result['pos'] is not None:
                pos = result['pos']
                edge_index = result['edge_index']

                # Draw edges
                src = edge_index[0].tolist()
                dst = edge_index[1].tolist()
                for s, d in zip(src, dst):
                    if s in pos and d in pos:
                        xs = [pos[s][0], pos[d][0]]
                        ys = [pos[s][1], pos[d][1]]
                        self.ax_heatmap.plot(xs, ys, color='#45475a',
                                             linewidth=0.3, alpha=0.4, zorder=1)

                # Draw nodes
                node_pos = np.array([pos[i] for i in range(len(pos))])
                sc = self.ax_heatmap.scatter(
                    node_pos[:, 0], node_pos[:, 1],
                    c=scores, cmap='RdYlGn_r', vmin=0, vmax=1,
                    s=50, edgecolors='#cdd6f4', linewidth=0.3,
                    alpha=0.85, zorder=2)

                # Colorbar
                cbar = self.fig.colorbar(sc, ax=self.ax_heatmap,
                                          shrink=0.7, pad=0.02)
                cbar.set_label('Predicted Vulnerability', color='#cdd6f4')
                cbar.ax.tick_params(colors='#cdd6f4')

                self.ax_heatmap.set_xlabel('Gate Position')
                self.ax_heatmap.set_ylabel('Gate Position')
                self.ax_heatmap.set_aspect('equal')

                # Stats overlay
                stats_text = (
                    f'Vulnerable: {num_vuln}/{result["num_nodes"]} '
                    f'({vuln_ratio*100:.1f}%)  |  '
                    f'Max: {float(scores.max()):.4f}  |  '
                    f'Mean: {float(scores.mean()):.4f}'
                )
                self.ax_heatmap.text(
                    0.02, 0.98, stats_text,
                    transform=self.ax_heatmap.transAxes,
                    color='#a6e3a1', fontsize=10, va='top',
                    bbox=dict(boxstyle='round', facecolor='#313244',
                              edgecolor='#585b70', alpha=0.8))
            else:
                # Histogram fallback
                self.ax_heatmap.hist(scores, bins=30, color='#f38ba8',
                                     alpha=0.7, edgecolor='#1e1e2e')
                self.ax_heatmap.set_xlabel('Vulnerability Score')
                self.ax_heatmap.set_ylabel('Gate Count')

            self.status_label.configure(
                text=f'Status: {os.path.basename(blif_path)} — '
                     f'{num_vuln}/{result["num_nodes"]} vulnerable nodes')
            self.info_var.set(
                f'{result["design_name"]} | {result["num_nodes"]} gates | '
                f'{vuln_ratio*100:.1f}% vulnerable')
            self.canvas.draw_idle()

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status_label.configure(text=f'Status: BLIF inference error: {str(e)[:50]}')

    # ------------------------------------------------------------------
    def _start_training(self):
        """Start background training thread."""
        if not os.path.exists(self.data_path):
            self.status_label.configure(text='Status: Error — training data not found')
            return

        raw = torch.load(self.data_path, map_location='cpu', weights_only=False)
        train_data = raw['train']
        val_data = raw['val']
        self.test_data = raw['test']

        all_y = torch.cat([d.y for d in train_data])
        pos_ratio = all_y.float().mean().item()
        focal_alpha = 1.0 - pos_ratio

        in_channels = train_data[0].x.shape[1]
        model = SAGE3(in_channels=in_channels, hidden_channels=128)

        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_label.configure(text='Status: Training in background...')

        def callback(epoch, metrics):
            self.root.after(0, self._update_plots, epoch, metrics)

        self.train_runner = TrainingRunner(
            train_data, val_data, model, callback,
            device='cpu', focal_alpha=focal_alpha,
            batch_size=32, epochs=400, patience=50,
        )
        self.train_runner.start()

        # Poll for completion
        self._poll_training()

    def _poll_training(self):
        """Poll training thread for completion."""
        if self.train_runner and self.train_runner.is_alive():
            self.root.after(1000, self._poll_training)
        elif self.train_runner:
            self.start_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED)
            self.status_label.configure(
                text=f'Status: Training complete! Best F1: {self.best_f1:.4f}')
            self._refresh_heatmap()

    def _stop_training(self):
        """Stop training thread."""
        if self.train_runner:
            self.train_runner.stop()
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text='Status: Training stopped by user')

    # ------------------------------------------------------------------
    def _export_plot(self):
        """Save current figure to file."""
        path = os.path.join(SCRIPT_DIR, 'data', 'dashboard_export.png')
        self.fig.savefig(path, dpi=150, bbox_inches='tight',
                         facecolor='#1e1e2e')
        self.status_label.configure(text=f'Status: Export saved to {os.path.basename(path)}')

    # ------------------------------------------------------------------
    def _update_timer(self):
        """Periodic UI update for live mode."""
        if self.mode == 'live' and self.train_runner is None:
            pass
        self.root.after(2000, self._update_timer)

    # ------------------------------------------------------------------
    def run(self):
        """Start the GUI event loop."""
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self.train_runner:
            self.train_runner.stop()
        self.root.destroy()


# ======================================================================
# Entry Point
# ======================================================================
def main():
    parser = argparse.ArgumentParser(
        description='Circuit Vulnerability Prediction Dashboard',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)

    parser.add_argument('--mode', type=str, default='analyze',
                        choices=['analyze', 'live', 'infer'],
                        help='analyze=load checkpoint+history, '
                             'live=background training+real-time plots, '
                             'infer=single BLIF vulnerability analysis')

    # Model / checkpoint
    parser.add_argument('--model', '--checkpoint', type=str, default=None,
                        dest='checkpoint',
                        help='Path to model checkpoint (.pt / .pth)')
    parser.add_argument('--model-type', type=str, default='auto',
                        choices=['auto', 'SAGE3', 'SAGE2Lite'],
                        help='Model architecture (auto = detect from checkpoint)')

    # Data
    parser.add_argument('--data', type=str, default=None,
                        help='Path to training data .pt file')
    parser.add_argument('--history', type=str, default=None,
                        help='Path to training history JSON')

    # BLIF inference
    parser.add_argument('--blif', type=str, default=None,
                        help='Path to BLIF file for vulnerability analysis')

    args = parser.parse_args()

    # Validate: infer mode requires --blif
    if args.mode == 'infer' and not args.blif:
        print('[ERROR] infer mode requires --blif <path>')
        sys.exit(1)

    # Build dashboard
    dashboard = VulnerabilityDashboard(
        mode=args.mode,
        checkpoint_path=args.checkpoint,
        history_path=args.history,
        model_type=args.model_type,
        data_path=args.data,
        blif_path=args.blif,
    )
    dashboard.run()


if __name__ == '__main__':
    main()
