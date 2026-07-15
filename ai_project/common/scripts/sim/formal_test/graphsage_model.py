#!/usr/bin/env python3
"""
graphsage_model.py — GraphSAGE Vulnerability Prediction (FT-Pilot Replication)

GraphSAGE-based node-level vulnerability prediction for circuit/graph data.
Supports single-graph node classification, multi-graph learning, K-fold CV,
early stopping, and comprehensive evaluation metrics.

Usage:
    python graphsage_model.py --train --data data/training_data.pt --epochs 200
    python graphsage_model.py --predict --model models/best_model.pt --data data/test_data.pt
    python graphsage_model.py --cross-validate --data data/training_data.pt --folds 5
    python graphsage_model.py --inspect --data data/training_data.pt
"""

import os
import sys
import json
import math
import argparse
import warnings
import numpy as np
from typing import List, Tuple, Dict, Optional, Union

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import random_split, Subset

from torch_geometric.nn import SAGEConv, global_mean_pool
from torch_geometric.data import Data, DataLoader
from torch_geometric.utils import add_self_loops, degree

warnings.filterwarnings("ignore", category=UserWarning, module="torch_geometric")


# ============================================================================
# Focal Loss
# ============================================================================

class FocalLoss(nn.Module):
    """Focal Loss for handling class imbalance and hard examples.

    FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)
    where p_t = sigmoid(x) if y=1 else 1-sigmoid(x)
    """
    def __init__(self, alpha=0.75, gamma=2.0, reduction='mean'):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.reduction = reduction

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        bce = F.binary_cross_entropy_with_logits(inputs, targets, reduction='none')
        pt = torch.exp(-bce)  # pt = P_t (probability of correct class)
        alpha_t = self.alpha * targets + (1 - self.alpha) * (1 - targets)
        focal = alpha_t * (1 - pt) ** self.gamma * bce
        if self.reduction == 'mean':
            return focal.mean()
        elif self.reduction == 'sum':
            return focal.sum()
        return focal


# ============================================================================
# 1. GraphSAGE Vulnerability Prediction Model
# ============================================================================


class VulnerabilityPredictor(nn.Module):
    """2-layer GraphSAGE with MLP head for vulnerability prediction.

    Architecture:
        SAGEConv(in_channels, hidden_channels) → ReLU → Dropout →
        SAGEConv(hidden_channels, hidden_channels//2) → ReLU →
        Linear(hidden_channels//2, 16) → ReLU → Dropout → Linear(16, 1)

    Forward returns raw logits (suitable for BCEWithLogitsLoss).
    Apply torch.sigmoid() externally for [0,1] vulnerability scores.
    """

    def __init__(
        self,
        in_channels: int = 10,
        hidden_channels: int = 64,
        num_layers: int = 2,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.dropout_layer = nn.Dropout(dropout)

        # GraphSAGE layers
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels // 2)

        # MLP prediction head
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels // 2, 16),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(16, 1),
        )

        self._init_weights()

    def _init_weights(self):
        """Apply Xavier uniform initialization to all linear layers."""
        for module in self.modules():
            if isinstance(module, (nn.Linear, SAGEConv)):
                if hasattr(module, "weight") and module.weight is not None:
                    nn.init.xavier_uniform_(module.weight)
                if hasattr(module, "bias") and module.bias is not None:
                    nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        """Forward pass returning raw logits.

        Args:
            x: Node features [num_nodes, in_channels]
            edge_index: Graph connectivity [2, num_edges]

        Returns:
            Logits of shape [num_nodes] or [batch_size] (for multi-graph).
        """
        # ---- GraphSAGE layers ----
        h1 = self.conv1(x, edge_index).relu()
        h1 = self.dropout_layer(h1)

        h2 = self.conv2(h1, edge_index).relu()

        # ---- MLP head ----
        out = self.mlp(h2)
        return out.squeeze(-1)

    @torch.no_grad()
    def predict(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        """Get vulnerability scores in [0, 1].

        Args:
            x: Node features
            edge_index: Graph connectivity

        Returns:
            Vulnerability scores [num_nodes] in range [0, 1]
        """
        self.eval()
        logits = self.forward(x, edge_index)
        return torch.sigmoid(logits)

    def count_parameters(self) -> int:
        """Return total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def print_architecture(self) -> None:
        """Print detailed model architecture with parameter counts per layer."""
        print("=" * 68)
        print("  VulnerabilityPredictor — Model Architecture")
        print("=" * 68)
        print(f"  {'Layer':<28s} {'Output Shape':<20s} {'Params':>8s}")
        print("  " + "-" * 60)
        grand_total = 0
        for name, param in self.named_parameters():
            if param.requires_grad:
                num = param.numel()
                grand_total += num
                shape_str = str(list(param.shape))
                # Shorten name for display
                display_name = name if len(name) < 28 else "..." + name[-25:]
                print(
                    f"  {display_name:<28s} {shape_str:<20s} {num:>8,d}"
                )
        print("  " + "-" * 60)
        print(f"  {'Total trainable parameters':<28s} {'':20s} {grand_total:>8,d}")
        print("=" * 68)


# ============================================================================
# 2. Evaluation Metrics
# ============================================================================


def compute_metrics(
    preds: torch.Tensor,
    labels: torch.Tensor,
    threshold: float = 0.5,
) -> Dict[str, float]:
    """Compute binary classification metrics.

    Args:
        preds: Predicted probabilities or logits [N]
        labels: Ground truth binary labels [N]
        threshold: Classification threshold (used if preds are not binary)

    Returns:
        dict with keys: f1, precision, recall, accuracy, auc_roc
    """
    # Convert to numpy
    preds_np = preds.detach().cpu().numpy().flatten()
    labels_np = labels.detach().cpu().numpy().flatten().astype(np.int64)

    # Binarize predictions
    binary = (preds_np >= threshold).astype(np.int64)

    # --- Confusion matrix components ---
    tp = np.sum((binary == 1) & (labels_np == 1)).item()
    fp = np.sum((binary == 1) & (labels_np == 0)).item()
    tn = np.sum((binary == 0) & (labels_np == 0)).item()
    fn = np.sum((binary == 0) & (labels_np == 1)).item()

    # --- Accuracy ---
    accuracy = (tp + tn) / max(tp + tn + fp + fn, 1)

    # --- Precision ---
    precision = tp / max(tp + fp, 1)

    # --- Recall ---
    recall = tp / max(tp + fn, 1)

    # --- F1 ---
    f1 = 2 * precision * recall / max(precision + recall, 1e-8)

    # --- AUC-ROC ---
    auc_roc = _compute_auc_roc(preds_np, labels_np)

    return {
        "f1": round(f1, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "accuracy": round(accuracy, 6),
        "auc_roc": round(auc_roc, 6),
    }


def _compute_auc_roc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Compute AUC-ROC manually using the trapezoidal rule.

    Falls back to sklearn.metrics.roc_auc_score if available.
    """
    try:
        from sklearn.metrics import roc_auc_score

        # Handle single-class edge case
        if len(np.unique(labels)) < 2:
            return 0.5
        return float(roc_auc_score(labels, scores))
    except ImportError:
        pass

    # Manual computation using varying thresholds
    n_pos = int(labels.sum())
    n_neg = int((1 - labels).sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5

    thresholds = np.linspace(0.0, 1.0, 1001)
    tpr_list = []
    fpr_list = []

    for thresh in thresholds:
        pred_bin = (scores >= thresh).astype(np.int64)
        tp = int(((pred_bin == 1) & (labels == 1)).sum())
        fp = int(((pred_bin == 1) & (labels == 0)).sum())
        tpr = tp / n_pos
        fpr = fp / n_neg
        tpr_list.append(tpr)
        fpr_list.append(fpr)

    # Trapezoidal integration
    tpr_arr = np.array(tpr_list)
    fpr_arr = np.array(fpr_list)
    idx = np.argsort(fpr_arr)
    sorted_fpr = fpr_arr[idx]
    sorted_tpr = tpr_arr[idx]
    auc = float(np.trapz(sorted_tpr, sorted_fpr))
    return auc


# ============================================================================
# 3. Vulnerability Trainer
# ============================================================================


class VulnerabilityTrainer:
    """Trainer for VulnerabilityPredictor with early stopping and metrics tracking.

    Supports both:
      - Single graph (node-level classification with train/val/test masks)
      - Multiple graphs (dataset split by graphs)
    """

    def __init__(
        self,
        model: VulnerabilityPredictor,
        device: Union[str, torch.device] = "cpu",
        lr: float = 1e-3,
        weight_decay: float = 5e-4,
    ):
        self.model = model.to(device)
        self.device = torch.device(device)
        self.optimizer = torch.optim.Adam(
            model.parameters(), lr=lr, weight_decay=weight_decay
        )
        self.criterion = nn.BCEWithLogitsLoss()

        # Training state
        self.history: Dict[str, List[float]] = {
            "train_loss": [],
            "val_loss": [],
            "val_f1": [],
            "val_precision": [],
            "val_recall": [],
        }
        self.best_val_loss = float("inf")
        self.best_state_dict = None
        self.patience_counter = 0
        self.current_epoch = 0

    def _is_single_graph(self, data) -> bool:
        """Check if data is a single PyG Data object (not a list/dataset)."""
        return isinstance(data, Data)

    def _prepare_batch(self, data) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Move data to device; return (x, edge_index, y)."""
        data = data.to(self.device)
        return data.x, data.edge_index, data.y

    def _train_epoch_single(self, data: Data) -> float:
        """Single training epoch on a single graph with node masks."""
        self.model.train()
        self.optimizer.zero_grad()

        x, edge_index, y = self._prepare_batch(data)
        logits = self.model(x, edge_index)

        # Masked loss for node-level classification
        loss = self.criterion(logits[data.train_mask], y[data.train_mask].float())
        loss.backward()
        self.optimizer.step()

        return float(loss.item())

    def _validate_single(self, data: Data) -> Dict[str, float]:
        """Validation on a single graph using val_mask."""
        self.model.eval()
        with torch.no_grad():
            x, edge_index, y = self._prepare_batch(data)
            logits = self.model(x, edge_index)
            val_logits = logits[data.val_mask]
            val_labels = y[data.val_mask]

            loss = float(self.criterion(val_logits, val_labels.float()).item())
            scores = torch.sigmoid(val_logits)
            metrics = compute_metrics(scores, val_labels)
            metrics["loss"] = loss
        return metrics

    def _train_epoch_multi(self, loader: DataLoader) -> float:
        """Single training epoch on multiple graphs using DataLoader."""
        self.model.train()
        total_loss = 0.0
        count = 0

        for batch in loader:
            batch = batch.to(self.device)
            self.optimizer.zero_grad()

            logits = self.model(batch.x, batch.edge_index)
            loss = self.criterion(logits, batch.y.float())
            loss.backward()
            self.optimizer.step()

            total_loss += float(loss.item()) * batch.num_graphs
            count += batch.num_graphs

        return total_loss / max(count, 1)

    def _validate_multi(self, loader: DataLoader) -> Dict[str, float]:
        """Validation on multiple graphs."""
        self.model.eval()
        total_loss = 0.0
        all_scores = []
        all_labels = []
        count = 0

        with torch.no_grad():
            for batch in loader:
                batch = batch.to(self.device)
                logits = self.model(batch.x, batch.edge_index)
                loss = self.criterion(logits, batch.y.float())
                total_loss += float(loss.item()) * batch.num_graphs
                count += batch.num_graphs

                scores = torch.sigmoid(logits)
                all_scores.append(scores.cpu())
                all_labels.append(batch.y.cpu())

        scores = torch.cat(all_scores)
        labels = torch.cat(all_labels)
        metrics = compute_metrics(scores, labels)
        metrics["loss"] = total_loss / max(count, 1)
        return metrics

    def train(
        self,
        data: Union[Data, List[Data]],
        epochs: int = 200,
        patience: int = 20,
        val_split: float = 0.2,
        batch_size: int = 32,
        verbose: bool = True,
        save_path: Optional[str] = None,
    ) -> Dict[str, List[float]]:
        """Train the model.

        Args:
            data: Single Data object (node-level) or list of Data (graph-level)
            epochs: Maximum number of epochs
            patience: Early stopping patience
            val_split: Validation split ratio (for single graph node masks)
            batch_size: Batch size (for multi-graph datasets)
            verbose: Print progress per epoch
            save_path: Path to save best model checkpoint

        Returns:
            Training history dict
        """
        self.history = {
            "train_loss": [],
            "val_loss": [],
            "val_f1": [],
            "val_precision": [],
            "val_recall": [],
        }
        self.best_val_loss = float("inf")
        self.best_state_dict = None
        self.patience_counter = 0

        is_single = self._is_single_graph(data)

        if is_single:
            # Single graph: ensure masks exist
            data = data.to(self.device)
            if not hasattr(data, "train_mask") or data.train_mask is None:
                data = self._create_masks(data, val_split)
            train_loader = None
            val_loader = None
        else:
            # Multi-graph: split into train/val sets
            dataset = list(data)
            n_val = max(1, int(len(dataset) * val_split))
            n_train = len(dataset) - n_val
            # Shuffle deterministically
            rng = torch.Generator().manual_seed(42)
            train_dataset, val_dataset = random_split(
                dataset, [n_train, n_val], generator=rng
            )
            train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
            val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

        for epoch in range(1, epochs + 1):
            self.current_epoch = epoch

            # --- Training ---
            if is_single:
                train_loss = self._train_epoch_single(data)
            else:
                train_loss = self._train_epoch_multi(train_loader)

            # --- Validation ---
            if is_single:
                val_metrics = self._validate_single(data)
            else:
                val_metrics = self._validate_multi(val_loader)

            val_loss = val_metrics["loss"]
            val_f1 = val_metrics["f1"]
            val_precision = val_metrics["precision"]
            val_recall = val_metrics["recall"]

            # Record history
            self.history["train_loss"].append(train_loss)
            self.history["val_loss"].append(val_loss)
            self.history["val_f1"].append(val_f1)
            self.history["val_precision"].append(val_precision)
            self.history["val_recall"].append(val_recall)

            # --- Early stopping ---
            if val_loss < self.best_val_loss - 1e-6:
                self.best_val_loss = val_loss
                self.best_state_dict = {
                    k: v.clone().cpu() for k, v in self.model.state_dict().items()
                }
                self.patience_counter = 0
            else:
                self.patience_counter += 1

            # --- Verbose output ---
            if verbose and (
                epoch == 1
                or epoch % 10 == 0
                or epoch == epochs
                or self.patience_counter == 0
            ):
                print(
                    f"  Epoch {epoch:>4d}/{epochs}  |  "
                    f"Train Loss: {train_loss:.4f}  |  "
                    f"Val Loss: {val_loss:.4f}  |  "
                    f"Val F1: {val_f1:.4f}  |  "
                    f"Prec: {val_precision:.4f}  |  "
                    f"Rec: {val_recall:.4f}  |  "
                    f"Patience: {self.patience_counter}/{patience}"
                )

            # --- Early stop check ---
            if self.patience_counter >= patience:
                if verbose:
                    print(
                        f"  [Early stopping] No improvement for {patience} epochs. "
                        f"Best val_loss: {self.best_val_loss:.6f}"
                    )
                break

        # Restore best model
        if self.best_state_dict is not None:
            self.model.load_state_dict(
                {k: v.to(self.device) for k, v in self.best_state_dict.items()}
            )

        # Save best model
        if save_path is not None:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            torch.save(self.best_state_dict, save_path)
            if verbose:
                print(f"  [Checkpoint] Best model saved to {save_path}")

        return self.history

    def _create_masks(self, data: Data, val_split: float = 0.2) -> Data:
        """Create random train/val masks for a single-graph dataset."""
        num_nodes = data.num_nodes
        indices = torch.randperm(num_nodes)
        n_val = max(1, int(num_nodes * val_split))
        n_train = num_nodes - n_val

        train_idx = indices[:n_train]
        val_idx = indices[n_train:]

        data.train_mask = torch.zeros(num_nodes, dtype=torch.bool)
        data.val_mask = torch.zeros(num_nodes, dtype=torch.bool)
        data.train_mask[train_idx] = True
        data.val_mask[val_idx] = True
        return data

    def plot_history(self, save_path: Optional[str] = None) -> None:
        """Plot training loss curves and validation metrics."""
        try:
            import matplotlib
            matplotlib.use("Agg")  # Non-interactive backend
            import matplotlib.pyplot as plt
        except ImportError:
            print("[Warning] matplotlib not available. Skipping plots.")
            return

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Loss curves
        ax = axes[0]
        epochs = range(1, len(self.history["train_loss"]) + 1)
        ax.plot(epochs, self.history["train_loss"], label="Train Loss", alpha=0.8)
        ax.plot(epochs, self.history["val_loss"], label="Val Loss", alpha=0.8)
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Loss")
        ax.set_title("Loss Curves")
        ax.legend()
        ax.grid(alpha=0.3)

        # Validation metrics
        ax = axes[1]
        ax.plot(epochs, self.history["val_f1"], label="F1", alpha=0.8)
        ax.plot(epochs, self.history["val_precision"], label="Precision", alpha=0.8)
        ax.plot(epochs, self.history["val_recall"], label="Recall", alpha=0.8)
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Score")
        ax.set_title("Validation Metrics")
        ax.legend()
        ax.grid(alpha=0.3)

        plt.tight_layout()
        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"  [Plot] Saved to {save_path}")
        plt.close(fig)

    def evaluate(self, data: Data) -> Dict[str, float]:
        """Evaluate the model on a given data object (uses test_mask or all nodes)."""
        self.model.eval()
        data = data.to(self.device)
        with torch.no_grad():
            logits = self.model(data.x, data.edge_index)
            scores = torch.sigmoid(logits)

            test_mask = getattr(data, "test_mask", None)
            if test_mask is not None:
                scores = scores[test_mask]
                labels = data.y[test_mask]
            else:
                labels = data.y

            metrics = compute_metrics(scores, labels)
        return metrics


# ============================================================================
# 4. K-fold Cross Validation
# ============================================================================


def cross_validate(
    dataset: List[Data],
    k: int = 5,
    in_channels: int = 8,
    hidden_channels: int = 64,
    epochs: int = 100,
    patience: int = 15,
    batch_size: int = 32,
    device: Union[str, torch.device] = "cpu",
    verbose: bool = True,
) -> Dict[str, List[float]]:
    """Perform K-fold cross-validation on a multi-graph dataset.

    Args:
        dataset: List of PyG Data objects
        k: Number of folds
        in_channels: Input feature dimension
        hidden_channels: Hidden dimension for GraphSAGE
        epochs: Max epochs per fold
        patience: Early stopping patience per fold
        batch_size: Batch size for training
        device: Device to use
        verbose: Print per-fold results

    Returns:
        dict with per-fold metrics and averaged results
    """
    n_graphs = len(dataset)
    if n_graphs < k:
        k = max(2, n_graphs)
        if verbose:
            print(f"  [Warning] Reducing folds to {k} (only {n_graphs} graphs)")

    fold_size = n_graphs // k
    indices = torch.randperm(n_graphs)

    fold_metrics: Dict[str, List[float]] = {
        "f1": [],
        "precision": [],
        "recall": [],
        "accuracy": [],
        "auc_roc": [],
    }

    for fold in range(k):
        if verbose:
            print(f"\n{'='*60}")
            print(f"  Fold {fold + 1}/{k}")
            print(f"{'='*60}")

        # Split indices
        start = fold * fold_size
        end = start + fold_size if fold < k - 1 else n_graphs
        val_idx = indices[start:end]
        train_idx = torch.cat([indices[:start], indices[end:]])

        train_set = [dataset[i] for i in train_idx]
        val_set = [dataset[i] for i in val_idx]

        train_loader = DataLoader(train_set, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_set, batch_size=batch_size, shuffle=False)

        # Initialize model
        model = VulnerabilityPredictor(
            in_channels=in_channels,
            hidden_channels=hidden_channels,
            dropout=0.3,
        ).to(device)

        trainer = VulnerabilityTrainer(model, device=device)
        trainer.train(
            data=[d.to(device) for d in train_set],
            epochs=epochs,
            patience=patience,
            val_split=0.0,  # Already split by cross-val
            verbose=verbose,
        )

        # Evaluate on validation fold
        model.eval()
        all_scores = []
        all_labels = []
        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(device)
                logits = model(batch.x, batch.edge_index)
                scores = torch.sigmoid(logits)
                all_scores.append(scores.cpu())
                all_labels.append(batch.y.cpu())

        scores = torch.cat(all_scores)
        labels = torch.cat(all_labels)
        metrics = compute_metrics(scores, labels)

        for key in fold_metrics:
            fold_metrics[key].append(metrics[key])

        if verbose:
            print(
                f"  Fold {fold + 1} Results: F1={metrics['f1']:.4f}  "
                f"Prec={metrics['precision']:.4f}  Rec={metrics['recall']:.4f}  "
                f"Acc={metrics['accuracy']:.4f}  AUC={metrics['auc_roc']:.4f}"
            )

    # Compute averages
    avg_metrics = {}
    std_metrics = {}
    for key in fold_metrics:
        vals = fold_metrics[key]
        avg_metrics[key] = round(float(np.mean(vals)), 6)
        std_metrics[key] = round(float(np.std(vals)), 6)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Cross-Validation Results ({k}-fold)")
        print(f"{'='*60}")
        for key in avg_metrics:
            print(f"    {key.capitalize():>10s}: {avg_metrics[key]:.4f} ± {std_metrics[key]:.4f}")
        print(f"{'='*60}")

    return {
        "per_fold": fold_metrics,
        "average": avg_metrics,
        "std": std_metrics,
    }


# ============================================================================
# 5. Training Pipeline
# ============================================================================


def train_from_scratch(
    data_dir: str = "data",
    device: Union[str, torch.device] = "cpu",
    epochs: int = 200,
    patience: int = 20,
    lr: float = 1e-3,
    weight_decay: float = 5e-4,
    hidden_channels: int = 64,
    dropout: float = 0.3,
    verbose: bool = True,
) -> Tuple[VulnerabilityPredictor, VulnerabilityTrainer]:
    """End-to-end training pipeline from saved data.

    Loads 'training_data.pt' from data_dir, trains a VulnerabilityPredictor,
    plots loss curves, and saves results to 'training_results.json'.

    Expected file structure:
        {data_dir}/training_data.pt  — single Data or list of Data

    Args:
        data_dir: Directory containing training_data.pt
        device: Device to use
        epochs: Max epochs
        patience: Early stopping patience
        lr: Learning rate
        weight_decay: Weight decay
        hidden_channels: Hidden dimension
        dropout: Dropout rate
        verbose: Print progress

    Returns:
        (trained_model, trainer)
    """
    device = torch.device(device)

    # ---- Load data ----
    data_path = os.path.join(data_dir, "training_data.pt")
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Training data not found: {data_path}")

    if verbose:
        print(f"[Data] Loading {data_path} ...")
    raw_data = torch.load(data_path, map_location="cpu", weights_only=False)

    # Handle dict-based splits {train, val, test}
    if isinstance(raw_data, dict):
        data = raw_data['train'] + raw_data['val']
        test_data = raw_data.get('test', [])
        if verbose:
            print(f"  Dict data: {len(raw_data['train'])} train + "
                  f"{len(raw_data['val'])} val + {len(test_data)} test")
    else:
        data = raw_data
        test_data = []

    # Determine input channels
    if isinstance(data, Data):
        in_channels = data.x.size(-1)
    elif isinstance(data, list) and len(data) > 0:
        in_channels = data[0].x.size(-1)
    else:
        raise ValueError("Empty or invalid dataset")

    if verbose:
        if isinstance(data, Data):
            print(f"  Single graph: {data.num_nodes} nodes, {data.num_edges} edges")
        else:
            print(f"  Multi-graph dataset: {len(data)} graphs")
        print(f"  Input features: {in_channels}")

    # ---- Initialize model ----
    model = VulnerabilityPredictor(
        in_channels=in_channels,
        hidden_channels=hidden_channels,
        dropout=dropout,
    )
    if verbose:
        model.print_architecture()

    # ---- Train ----
    trainer = VulnerabilityTrainer(model, device=device, lr=lr, weight_decay=weight_decay)
    model_dir = os.path.join(data_dir, "models")
    os.makedirs(model_dir, exist_ok=True)
    save_path = os.path.join(model_dir, "best_model.pt")

    history = trainer.train(
        data=data,
        epochs=epochs,
        patience=patience,
        verbose=verbose,
        save_path=save_path,
    )

    # ---- Plot ----
    plot_path = os.path.join(data_dir, "training_curves.png")
    trainer.plot_history(save_path=plot_path)

    # ---- Evaluate ----
    final_metrics = {"train_loss": history["train_loss"][-1], "val_loss": history["val_loss"][-1]}
    eval_data = test_data if test_data else (data if isinstance(data, list) else [])
    if isinstance(data, Data):
        eval_metrics = trainer.evaluate(data)
        final_metrics.update(eval_metrics)
    elif eval_data:
        model.eval()
        model.to(device)
        all_scores = []
        all_labels = []
        loader = DataLoader(eval_data, batch_size=32, shuffle=False)
        with torch.no_grad():
            for batch in loader:
                batch = batch.to(device)
                logits = model(batch.x, batch.edge_index)
                scores = torch.sigmoid(logits)
                all_scores.append(scores.cpu())
                all_labels.append(batch.y.cpu())
        scores = torch.cat(all_scores).float()
        labels = torch.cat(all_labels).float()
        eval_metrics = compute_metrics(scores, labels)
        final_metrics.update(eval_metrics)

    # ---- Save results ----
    results = {
        "best_val_loss": trainer.best_val_loss,
        "final_metrics": final_metrics,
        "total_parameters": model.count_parameters(),
        "epochs_trained": trainer.current_epoch,
        "early_stopped": trainer.patience_counter >= patience,
    }
    results_path = os.path.join(data_dir, "training_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    if verbose:
        print(f"\n[Results] Saved to {results_path}")
        print(json.dumps(results, indent=2))

    return model, trainer


# ============================================================================
# 6. Prediction / Inference Utilities
# ============================================================================


@torch.no_grad()
def predict(
    model: VulnerabilityPredictor,
    data: Data,
    device: Union[str, torch.device] = "cpu",
) -> torch.Tensor:
    """Run inference to get per-node vulnerability scores.

    Args:
        model: Trained VulnerabilityPredictor
        data: Single PyG Data object
        device: Device

    Returns:
        Vulnerability scores [num_nodes] in range [0, 1]
    """
    model.eval()
    data = data.to(device)
    model = model.to(device)
    logits = model(data.x, data.edge_index)
    return torch.sigmoid(logits).cpu()


@torch.no_grad()
def get_vulnerable_nodes(
    model: VulnerabilityPredictor,
    data: Data,
    threshold: float = 0.5,
    device: Union[str, torch.device] = "cpu",
) -> List[Tuple[int, float]]:
    """Get nodes predicted vulnerable above the given threshold.

    Args:
        model: Trained VulnerabilityPredictor
        data: Single PyG Data object
        threshold: Classification threshold
        device: Device

    Returns:
        List of (node_id, vulnerability_score) sorted by score descending
    """
    scores = predict(model, data, device=device)
    node_ids = torch.where(scores >= threshold)[0]
    result = [(int(nid), float(scores[nid])) for nid in node_ids]
    result.sort(key=lambda x: x[1], reverse=True)
    return result


@torch.no_grad()
def rank_by_vulnerability(
    model: VulnerabilityPredictor,
    data: Data,
    device: Union[str, torch.device] = "cpu",
) -> List[Tuple[int, float]]:
    """Rank all nodes by vulnerability score descending.

    Args:
        model: Trained VulnerabilityPredictor
        data: Single PyG Data object
        device: Device

    Returns:
        List of (node_id, vulnerability_score) sorted descending
    """
    scores = predict(model, data, device=device)
    # Sort descending by score
    sorted_indices = torch.argsort(scores, descending=True)
    return [(int(idx), float(scores[idx])) for idx in sorted_indices]


# ============================================================================
# 7. Helper: Data Inspection
# ============================================================================


def inspect_data(data_path: str) -> None:
    """Print detailed information about a saved data file."""
    if not os.path.exists(data_path):
        print(f"[Error] File not found: {data_path}")
        return

    data = torch.load(data_path, map_location="cpu", weights_only=False)

    if isinstance(data, Data):
        print(f"\n{'='*60}")
        print(f"  Data Object Inspection")
        print(f"{'='*60}")
        print(f"  num_nodes: {data.num_nodes}")
        print(f"  num_edges: {data.num_edges}")
        print(f"  num_node_features: {data.num_node_features}")
        print(f"  num_edge_features: {data.num_edge_features}")
        if hasattr(data, "y") and data.y is not None:
            print(f"  y shape: {list(data.y.shape)}")
            if data.y.dtype in (torch.float, torch.long, torch.int):
                pos_ratio = (data.y > 0.5).float().mean().item() * 100
                print(f"  Positive ratio: {pos_ratio:.1f}%")
        if hasattr(data, "train_mask"):
            print(f"  train_mask: {data.train_mask.sum().item()} nodes")
        if hasattr(data, "val_mask"):
            print(f"  val_mask: {data.val_mask.sum().item()} nodes")
        if hasattr(data, "test_mask"):
            print(f"  test_mask: {data.test_mask.sum().item()} nodes")

        # Edge case checks
        print(f"\n  Edge Cases:")
        if data.num_edges == 0:
            print("    ⚠ Graph has NO edges (isolated nodes only)")
        else:
            # Check for isolated nodes
            unique_nodes = torch.unique(data.edge_index)
            n_isolated = data.num_nodes - unique_nodes.size(0)
            if n_isolated > 0:
                print(f"    ⚠ {n_isolated} isolated nodes (no edges)")
            else:
                print(f"    ✓ All nodes have at least one edge")

        # Check for NaN/Inf
        x = data.x
        nan_count = torch.isnan(x).sum().item()
        inf_count = torch.isinf(x).sum().item()
        if nan_count > 0:
            print(f"    ⚠ {nan_count} NaN values in features")
        if inf_count > 0:
            print(f"    ⚠ {inf_count} Inf values in features")
        if nan_count == 0 and inf_count == 0:
            print(f"    ✓ No NaN/Inf in features")

    elif isinstance(data, list):
        print(f"\n{'='*60}")
        print(f"  Dataset Inspection ({len(data)} graphs)")
        print(f"{'='*60}")
        in_chan = data[0].x.size(-1) if len(data) > 0 else "N/A"
        print(f"  Input channels: {in_chan}")
        node_counts = [g.num_nodes for g in data]
        edge_counts = [g.num_edges for g in data]
        print(f"  Nodes: min={min(node_counts)}, max={max(node_counts)}, avg={np.mean(node_counts):.1f}")
        print(f"  Edges: min={min(edge_counts)}, max={max(edge_counts)}, avg={np.mean(edge_counts):.1f}")
        zero_edge = sum(1 for e in edge_counts if e == 0)
        if zero_edge > 0:
            print(f"  ⚠ {zero_edge} graphs with zero edges")
        else:
            print(f"  ✓ All graphs have edges")
    else:
        print(f"[Error] Unknown data type: {type(data)}")


# ============================================================================
# 8. Main CLI
# ============================================================================


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="GraphSAGE Vulnerability Prediction (FT-Pilot)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python graphsage_model.py --train --data data/training_data.pt --epochs 200
  python graphsage_model.py --predict --model models/best_model.pt --data data/test_data.pt
  python graphsage_model.py --cross-validate --data data/training_data.pt --folds 5
  python graphsage_model.py --inspect --data data/training_data.pt
        """,
    )

    # Mode selection
    parser.add_argument("--train", action="store_true", help="Train model from scratch")
    parser.add_argument("--predict", action="store_true", help="Run prediction/inference")
    parser.add_argument("--cross-validate", action="store_true", help="Run K-fold cross-validation")
    parser.add_argument("--inspect", action="store_true", help="Inspect data file contents")

    # Data and model paths
    parser.add_argument("--data", type=str, default="data/training_data.pt",
                        help="Path to training/inference data (.pt)")
    parser.add_argument("--model", type=str, default="models/best_model.pt",
                        help="Path to saved model checkpoint")
    parser.add_argument("--blif", type=str, default=None,
                        help="Path to BLIF file (for --predict)")

    # Training hyperparameters
    parser.add_argument("--epochs", type=int, default=200, help="Max training epochs")
    parser.add_argument("--patience", type=int, default=20, help="Early stopping patience")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    parser.add_argument("--weight-decay", type=float, default=5e-4, help="Weight decay")
    parser.add_argument("--hidden", type=int, default=64, help="Hidden channels")
    parser.add_argument("--dropout", type=float, default=0.3, help="Dropout rate")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Classification threshold")

    # Cross-validation
    parser.add_argument("--folds", type=int, default=5, help="Number of CV folds")

    # Device
    parser.add_argument("--device", type=str, default="auto",
                        help="Device: 'cpu', 'cuda', 'mps', or 'auto'")

    return parser.parse_args()


def _resolve_device(device_str: str) -> str:
    """Resolve device string to actual device name."""
    if device_str != "auto":
        return device_str
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main():
    """Main entry point."""
    args = parse_args()
    device = _resolve_device(args.device)

    print(f"{'='*68}")
    print(f"  GraphSAGE Vulnerability Prediction (FT-Pilot)")
    print(f"  Device: {device}")
    print(f"{'='*68}")

    # ---- Inspect mode ----
    if args.inspect:
        inspect_data(args.data)
        return

    # ---- Train mode ----
    if args.train:
        data_dir = os.path.dirname(args.data) if os.path.dirname(args.data) else "data"
        model, trainer = train_from_scratch(
            data_dir=data_dir,
            device=device,
            epochs=args.epochs,
            patience=args.patience,
            lr=args.lr,
            weight_decay=args.weight_decay,
            hidden_channels=args.hidden,
            dropout=args.dropout,
        )
        return

    # ---- Cross-validation mode ----
    if args.cross_validate:
        print(f"\n[CV] Loading {args.data} ...")
        dataset = torch.load(args.data, map_location="cpu", weights_only=False)
        if isinstance(dataset, Data):
            print("[Warning] Single Data object detected. K-fold CV requires a list of graphs.")
            print("  Converting to list of single-graph Data objects...")
            dataset = [dataset]

        in_channels = dataset[0].x.size(-1) if len(dataset) > 0 else 8
        cross_validate(
            dataset=dataset,
            k=args.folds,
            in_channels=in_channels,
            hidden_channels=args.hidden,
            epochs=args.epochs,
            patience=args.patience,
            batch_size=args.batch_size,
            device=device,
        )
        return

    # ---- Predict mode ----
    if args.predict:
        model_path = args.model
        data_path = args.data

        if not os.path.exists(model_path):
            print(f"[Error] Model not found: {model_path}")
            sys.exit(1)
        if not os.path.exists(data_path):
            print(f"[Error] Data not found: {data_path}")
            sys.exit(1)

        print(f"\n[Predict] Loading model from {model_path}")
        checkpoint = torch.load(model_path, map_location=device, weights_only=True)
        data = torch.load(data_path, map_location="cpu", weights_only=False)

        if not isinstance(data, Data):
            print(f"[Error] Prediction requires a single Data object, got {type(data)}")
            sys.exit(1)

        in_channels = data.x.size(-1)
        model = VulnerabilityPredictor(in_channels=in_channels).to(device)
        model.load_state_dict(checkpoint)
        model.print_architecture()

        print(f"\n[Predict] Running inference on {data.num_nodes} nodes...")
        scores = predict(model, data, device=device)

        vulnerable = get_vulnerable_nodes(
            model, data, threshold=args.threshold, device=device
        )
        ranked = rank_by_vulnerability(model, data, device=device)

        print(f"\n  Prediction Summary:")
        print(f"    Total nodes: {data.num_nodes}")
        print(f"    Above threshold ({args.threshold}): {len(vulnerable)} nodes")
        print(f"    Max score: {ranked[0][1]:.4f} (node {ranked[0][0]})" if ranked else "    No predictions")
        print(f"    Min score: {ranked[-1][1]:.4f} (node {ranked[-1][0]})" if ranked else "")

        print(f"\n  Top-10 Most Vulnerable Nodes:")
        print(f"    {'Rank':>4s}  {'Node ID':>8s}  {'Score':>8s}")
        print(f"    {'-'*24}")
        for i, (nid, score) in enumerate(ranked[:10], 1):
            print(f"    {i:>4d}  {nid:>8d}  {score:.6f}")

        if len(vulnerable) > 10:
            print(f"    ... and {len(vulnerable) - 10} more above threshold")

        # Save predictions
        results_dir = os.path.dirname(data_path) if os.path.dirname(data_path) else "."
        pred_path = os.path.join(results_dir, "prediction_results.json")
        pred_results = {
            "num_nodes": data.num_nodes,
            "threshold": args.threshold,
            "num_vulnerable": len(vulnerable),
            "top_10_vulnerable": [
                {"node_id": nid, "score": round(score, 6)}
                for nid, score in ranked[:10]
            ],
            "all_vulnerable": [
                {"node_id": nid, "score": round(score, 6)}
                for nid, score in vulnerable
            ],
        }
        with open(pred_path, "w") as f:
            json.dump(pred_results, f, indent=2)
        print(f"\n[Predict] Results saved to {pred_path}")
        return

    # ---- No valid mode ----
    print("[Error] No valid mode specified. Use --train, --predict, --cross-validate, or --inspect.")
    print("  Run 'python graphsage_model.py --help' for usage.")


if __name__ == "__main__":
    main()
