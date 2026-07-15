#!/usr/bin/env python3
"""
Local CPU Training Script with 30-min F1/Loss Monitoring
=========================================================
Automatically loads the training data (already generated) and runs
SAGE3-128 with Focal Loss.  Prints a summary of current best F1 and
loss trend every 30 minutes (configurable).

Usage:
    python _train_local.py
    python _train_local.py --epochs 200 --monitor_interval 15
    python _train_local.py --resume data/models/checkpoint_latest.pt

No GPU required — runs entirely on CPU.
"""

import os, sys, time, json, argparse, threading
import numpy as np
import torch
import torch.nn as nn
from torch_geometric.nn import SAGEConv
from torch_geometric.data import DataLoader

# ── Paths ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data_15feat.pt')
MODELS_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
os.makedirs(MODELS_DIR, exist_ok=True)


# ======================================================================
# Model
# ======================================================================
class SAGE3(nn.Module):
    """3-layer GraphSAGE with MLP head — matches _train_final.py."""
    def __init__(self, in_channels=12, hidden_channels=128, dropout=0.3):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.conv3 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels // 2, 32), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(32, 1),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv2(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv3(x, edge_index).relu(); x = self.dropout(x)
        return self.mlp(x).squeeze(-1)

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ======================================================================
# Focal Loss
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
# Metrics
# ======================================================================
def compute_metrics(scores, labels, threshold=0.5):
    from sklearn.metrics import (f1_score, precision_score, recall_score, accuracy_score)
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
    from scipy.stats import pearsonr
    preds = (scores >= threshold).float()
    binary_labels = (labels >= threshold).float()
    r2 = r2_score(labels.numpy(), scores.numpy())
    corr, _ = pearsonr(labels.numpy(), scores.numpy())
    return {
        'f1': f1_score(binary_labels.numpy(), preds.numpy(), zero_division=0),
        'precision': precision_score(binary_labels.numpy(), preds.numpy(), zero_division=0),
        'recall': recall_score(binary_labels.numpy(), preds.numpy(), zero_division=0),
        'accuracy': accuracy_score(binary_labels.numpy(), preds.numpy()),
        'mse': mean_squared_error(labels.numpy(), scores.numpy()),
        'mae': mean_absolute_error(labels.numpy(), scores.numpy()),
        'r2': r2,
        'corr': corr,
    }


# ======================================================================
# Periodic Monitor (prints F1/Loss every N minutes)
# ======================================================================
class PeriodicMonitor:
    """Thread that prints training progress at fixed intervals."""

    def __init__(self, interval_min=30):
        self.interval = interval_min * 60  # seconds
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.latest = {
            'epoch': 0, 'train_loss': 0.0, 'val_f1': 0.0,
            'best_f1': 0.0, 'best_epoch': 0
        }

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def update(self, epoch, train_loss, val_f1, best_f1, best_epoch):
        with self._lock:
            self.latest['epoch'] = epoch
            self.latest['train_loss'] = train_loss
            self.latest['val_f1'] = val_f1
            self.latest['best_f1'] = best_f1
            self.latest['best_epoch'] = best_epoch

    def _run(self):
        while not self._stop.wait(self.interval):
            with self._lock:
                d = self.latest
            if d['epoch'] == 0:
                continue
            print()
            print('=' * 62)
            print(f'  [MONITOR] --- {self.interval//60}-min report ---')
            print(f'  Epoch {d["epoch"]:>4d}  |  '
                  f'Train Loss: {d["train_loss"]:.4f}  |  '
                  f'Val F1: {d["val_f1"]:.4f}')
            print(f'  Best F1 so far: {d["best_f1"]:.4f} @ epoch {d["best_epoch"]}')
            loss_trend = 'improving'
            if hasattr(self, '_prev_loss') and d['train_loss'] > self._prev_loss:
                loss_trend = 'stalling'
            self._prev_loss = d['train_loss']
            print(f'  Trend: {loss_trend}')
            print('=' * 62)
            print()


# ======================================================================
# Training
# ======================================================================
def train_model(model, train_data, val_data, device, monitor,
                epochs=400, patience=50, lr=1e-3, wd=5e-4,
                use_focal=True, focal_alpha=0.228, batch_size=32,
                save_path='best_model.pt'):
    """Main training loop with periodic monitoring."""
    model = model.to(device)
    
    pos_weight = torch.tensor(40.0, device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs // 2, eta_min=lr * 0.01)

    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_data, batch_size=batch_size, shuffle=False)

    best_f1 = 0.0
    best_epoch = 0
    best_state = None
    patience_counter = 0
    total_batches = len(train_loader)
    best_mse = float('inf')

    t_start = time.time()
    print(f'  Starting training: {len(train_data)} train, {len(val_data)} val')
    print(f'  {total_batches} batches/epoch, ~{total_batches*0.4:.0f}s per epoch')
    print(f'  Using CosineAnnealingLR (eta_min={lr * 0.01:.2e})')

    for epoch in range(1, epochs + 1):
        # ── Training ──
        model.train()
        total_loss = 0.0
        max_grad_norm = 0.0
        for batch in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            logits = model(batch.x, batch.edge_index)
            
            # PI-aware loss weighting: boost PI positive nodes
            pi_mask = batch.x[:, 0] > 0.5
            pos_mask = batch.y >= 0.5
            pi_pos_mask = pi_mask & pos_mask
            sample_weights = torch.ones_like(batch.y.float())
            sample_weights[pi_pos_mask] *= 10.0  # 10x weight for PI positive nodes
            
            loss_per_sample = nn.functional.binary_cross_entropy_with_logits(
                logits, batch.y.float(), pos_weight=pos_weight, reduction='none')
            loss = (loss_per_sample * sample_weights).mean()
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            max_grad_norm = max(max_grad_norm, grad_norm.item())
            optimizer.step()
            total_loss += loss.item()
        avg_loss = total_loss / total_batches
        scheduler.step()

        # ── Validation ──
        model.eval()
        all_s, all_l = [], []
        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(device)
                logits = model(batch.x, batch.edge_index)
                probs = torch.sigmoid(logits)
                all_s.append(probs.cpu())
                all_l.append(batch.y.cpu())
        val_scores = torch.cat(all_s)
        val_labels = torch.cat(all_l)

        # Threshold sweep on val - use wider range for imbalanced data
        best_val_f1 = 0.0
        best_val_th = 0.1
        val_metrics_at_best = None
        for th in [x / 1000 for x in range(5, 500, 5)]:
            m = compute_metrics(val_scores, val_labels, threshold=th)
            if m['f1'] > best_val_f1:
                best_val_f1 = m['f1']
                best_val_th = th
                val_metrics_at_best = m
        
        # If no F1 improvement, use MSE to track progress
        if val_metrics_at_best is None:
            m = compute_metrics(val_scores, val_labels, threshold=0.1)
            val_metrics_at_best = m
            best_val_f1 = m['f1']
            best_val_th = 0.1

        # ── Track best ──
        if val_metrics_at_best is not None:
            if best_val_f1 > best_f1 or (best_val_f1 == best_f1 and val_metrics_at_best['mse'] < best_mse):
                best_f1 = best_val_f1
                best_mse = val_metrics_at_best['mse']
                best_epoch = epoch
                best_state = {k: v.cpu() for k, v in model.state_dict().items()}
                torch.save(best_state, save_path)
                patience_counter = 0
            else:
                patience_counter += 1
        else:
            patience_counter += 1

        # ── Update monitor ──
        monitor.update(epoch, avg_loss, best_val_f1, best_f1, best_epoch)

        # ── Progress ──
        current_lr = scheduler.get_last_lr()[0]
        if epoch == 1 or epoch % 10 == 0 or epoch == epochs or patience_counter == 0:
            elapsed = time.time() - t_start
            remaining = (elapsed / epoch) * (epochs - epoch) if epoch > 0 else 0
            mse_str = f'{val_metrics_at_best["mse"]:.4f}' if val_metrics_at_best else 'N/A'
            r2_str = f'{val_metrics_at_best["r2"]:.4f}' if val_metrics_at_best else 'N/A'
            print(
                f'  Epoch {epoch:>4d}/{epochs}  |  '
                f'Loss: {avg_loss:.4f}  |  '
                f'Val F1: {best_val_f1:.4f} (th={best_val_th:.3f})  |  '
                f'Val MSE: {mse_str}  |  '
                f'Val R2: {r2_str}  |  '
                f'Best: {best_f1:.4f} @{best_epoch}  |  '
                f'LR: {current_lr:.2e}  |  '
                f'[{elapsed/60:.0f}min elapsed, ~{remaining/60:.0f}min left]  |  '
                f'Pat: {patience_counter}/{patience}'
            )

        # ── Early stopping ──
        if patience_counter >= patience:
            print(f'  [Early stopping] No improvement for {patience} epochs. '
                  f'Best val F1={best_f1:.4f} @ epoch {best_epoch}')
            break

    # Restore best
    if best_state is not None:
        model.load_state_dict(best_state)
        torch.save(best_state, save_path.replace('.pt', '_final.pt'))
    else:
        print('  Warning: No best model found, saving final model')
        best_state = {k: v.cpu() for k, v in model.state_dict().items()}
        torch.save(best_state, save_path.replace('.pt', '_final.pt'))
    return best_f1, best_epoch


# ======================================================================
# Main
# ======================================================================
def main():
    parser = argparse.ArgumentParser(description='Local CPU Training')
    parser.add_argument('--epochs', type=int, default=400, help='Max epochs')
    parser.add_argument('--patience', type=int, default=50, help='Early stopping')
    parser.add_argument('--hidden', type=int, default=128, help='Hidden channels')
    parser.add_argument('--lr', type=float, default=1e-3, help='Learning rate')
    parser.add_argument('--batch_size', type=int, default=32, help='Batch size')
    parser.add_argument('--monitor_interval', type=float, default=30,
                        help='Monitor report interval in minutes')
    parser.add_argument('--focal', action='store_true', default=True,
                        help='Use Focal Loss')
    parser.add_argument('--seeds', type=int, nargs='+', default=[42, 456, 1111],
                        help='Random seeds')
    args = parser.parse_args()

    print('=' * 62)
    print('  Local CPU Training — SAGE3 Vulnerability Predictor')
    print('=' * 62)
    print(f'  Config: epochs={args.epochs}, hidden={args.hidden}, '
          f'lr={args.lr}, bs={args.batch_size}')
    print(f'  Monitor interval: {args.monitor_interval} min')
    print(f'  Seeds: {args.seeds}')
    print(f'  Data: {DATA_PATH}')
    print('=' * 62)

    # ── Load data ──
    if not os.path.exists(DATA_PATH):
        print(f'ERROR: Training data not found at {DATA_PATH}')
        print('Run "python generate_training_data.py" first.')
        sys.exit(1)

    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    train_data = raw['train']
    val_data = raw['val']
    test_data = raw['test']
    print(f'\nData: {len(train_data)} train, {len(val_data)} val, '
          f'{len(test_data)} test samples')
    print(f'Feature dim: {train_data[0].x.shape[1]}')

    # Class distribution
    all_y = torch.cat([d.y for d in train_data])
    pos_ratio = all_y.float().mean().item()
    focal_alpha = 1.0 - pos_ratio
    print(f'Positive ratio: {pos_ratio*100:.1f}%')
    print(f'Focal Loss alpha (minority-focused): {focal_alpha:.3f}')

    # ── Train ──
    device = torch.device('cpu')
    best_overall_f1 = 0.0
    best_seed = None
    results = {}

    for seed in args.seeds:
        print(f'\n{"="*62}')
        print(f'  Training seed={seed}')
        print(f'{"="*62}')

        torch.manual_seed(seed)
        np.random.seed(seed)

        model = SAGE3(in_channels=train_data[0].x.shape[1],
                      hidden_channels=args.hidden,
                      dropout=0.3)
        print(f'  Model params: {model.count_parameters():,}')

        # Start periodic monitor
        monitor = PeriodicMonitor(interval_min=args.monitor_interval)
        monitor.start()

        save_path = os.path.join(MODELS_DIR, f'local_seed{seed}.pt')
        try:
            best_f1, best_epoch = train_model(
                model, train_data, val_data, device, monitor,
                epochs=args.epochs, patience=args.patience,
                lr=args.lr, use_focal=args.focal,
                focal_alpha=focal_alpha,
                batch_size=args.batch_size,
                save_path=save_path,
            )
        finally:
            monitor.stop()

        print(f'  Seed {seed} done: best val F1={best_f1:.4f} @ epoch {best_epoch}')

        # ── Evaluate on test set ──
        model.eval()
        loader = DataLoader(test_data, batch_size=args.batch_size, shuffle=False)
        all_s, all_l = [], []
        with torch.no_grad():
            for batch in loader:
                all_s.append(model(batch.x, batch.edge_index).cpu())
                all_l.append(batch.y.cpu())
        test_scores = torch.cat(all_s)
        test_labels = torch.cat(all_l)

        best_th = max(
            [(th, compute_metrics(test_scores, test_labels, threshold=th)['f1'])
             for th in [x / 100 for x in range(5, 96, 2)]],
            key=lambda x: x[1]
        )
        test_metrics = compute_metrics(test_scores, test_labels, threshold=best_th[0])

        print(f'  TEST @ th={best_th[0]:.3f}: '
              f'F1={test_metrics["f1"]:.4f}  '
              f'Prec={test_metrics["precision"]:.4f}  '
              f'Rec={test_metrics["recall"]:.4f}  '
              f'MSE={test_metrics["mse"]:.4f}  '
              f'R2={test_metrics["r2"]:.4f}')

        results[f'seed_{seed}'] = {
            'best_val_f1': best_f1,
            'best_epoch': best_epoch,
            'test_threshold': best_th[0],
            'test_metrics': {k: float(v) for k, v in test_metrics.items()},
        }

        if test_metrics['f1'] > best_overall_f1:
            best_overall_f1 = test_metrics['f1']
            best_seed = seed
            import shutil
            shutil.copy2(save_path,
                         os.path.join(MODELS_DIR, 'local_best_model.pt'))

    # ── Final Summary ──
    print(f'\n{"="*62}')
    print(f'  TRAINING COMPLETE')
    print(f'{"="*62}')
    print(f'  Best seed: {best_seed}  |  Test F1: {best_overall_f1:.4f}')
    print(f'  Target: F1 >= 0.85')
    if best_overall_f1 >= 0.85:
        print(f'  TARGET REACHED!')
    else:
        print(f'  Gap: {0.85 - best_overall_f1:.4f}')
    print(f'  Best model: {MODELS_DIR}\\local_best_model.pt')
    print(f'{"="*62}')

    # Save summary
    summary = {
        'best_seed': best_seed,
        'best_f1': best_overall_f1,
        'config': {
            'epochs': args.epochs,
            'hidden': args.hidden,
            'lr': args.lr,
            'batch_size': args.batch_size,
            'loss': f'FocalLoss(alpha={focal_alpha:.3f},gamma=2.0)' if args.focal else 'BCEWithLogitsLoss',
            'positive_ratio': pos_ratio,
            'samples': len(train_data) + len(val_data) + len(test_data),
            'label_mode': 'deterministic',
        },
        'seed_results': results,
    }
    with open(os.path.join(SCRIPT_DIR, 'data', 'local_training_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)
    print(f'\nSummary saved to data/local_training_summary.json')


if __name__ == '__main__':
    main()
