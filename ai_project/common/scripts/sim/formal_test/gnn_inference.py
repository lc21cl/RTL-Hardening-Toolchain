#!/usr/bin/env python3
"""
gnn_inference.py — GNN 脆弱性预测推理部署管线

将训练好的 GraphSAGE 模型集成到加固工具流程中。
支持 BLIF/AIG 输入 → PyG 转换 → GNN 推理 → 脆弱节点输出。

用法:
    # 命令行
    python gnn_inference.py --blif path/to/design.blif --model data/models/local_best_model.pt
    python gnn_inference.py --aig path/to/design.aig --model data/models/local_best_model.pt
    python gnn_inference.py --batch data/blifs/ --model data/models/local_best_model.pt

    # Python API
    from gnn_inference import GNNInference
    engine = GNNInference(model_path="data/models/local_best_model.pt")
    result = engine.infer_from_blif("path/to/design.blif")
    engine.integrate_to_hardening_pipeline(result, pipeline)
"""

import os
import sys
import json
import time
import argparse
import warnings
from typing import List, Tuple, Dict, Optional, Union

import torch
import torch.nn as nn
from torch_geometric.nn import SAGEConv
from torch_geometric.data import Data

warnings.filterwarnings("ignore", category=UserWarning, module="torch_geometric")

# Logger setup
try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ============================================================================
# 1. Model Architectures
# ============================================================================

# ── Model Registry ──────────────────────────────────────────────────────
# Auto-detection: maps checkpoint key signatures to model classes
MODEL_REGISTRY = {
    # SAGE3-128: keys start with conv1, conv2, conv3 (3 SAGE layers)
    'SAGE3': {
        'keys': lambda k: any(k.startswith('conv3.') for k in k),
        'hidden_channels': 128,
    },
    # SAGE2Lite-64: keys start with conv1, conv2 (2 SAGE layers) + mlp.0/mlp.3
    'SAGE2Lite': {
        'keys': lambda k: any(k.startswith('conv2.') for k in k)
                          and not any(k.startswith('conv3.') for k in k),
        'hidden_channels': 64,
    },
}


class SAGE3(nn.Module):
    """3-layer GraphSAGE with MLP head — matches trained local_best_model.pt.

    Architecture:
        SAGEConv(15→128) → ReLU → Dropout →
        SAGEConv(128→128) → ReLU → Dropout →
        SAGEConv(128→64) → ReLU → Dropout →
        Linear(64→32) → ReLU → Dropout → Linear(32→1)
    """
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
        x = self.conv1(x, edge_index).relu()
        x = self.dropout(x)
        x = self.conv2(x, edge_index).relu()
        x = self.dropout(x)
        x = self.conv3(x, edge_index).relu()
        x = self.dropout(x)
        return self.mlp(x).squeeze(-1)

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class SAGE2Lite(nn.Module):
    """2-layer GraphSAGE with lightweight MLP head — matches SAGE2-Lite-64.

    Architecture:
        SAGEConv(15→64) → ReLU → Dropout →
        SAGEConv(64→32) → ReLU → Dropout →
        Linear(32→8) → ReLU → Dropout → Linear(8→1)

    Total params: ~6,385 (vs SAGE3-128: 55,425)
    """
    def __init__(self, in_channels=15, hidden_channels=64, dropout=0.2):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels // 2, 8), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(8, 1),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        x = self.dropout(x)
        x = self.conv2(x, edge_index).relu()
        x = self.dropout(x)
        return self.mlp(x).squeeze(-1)

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ============================================================================
# 2. Graph Converter — Unified Interface for BLIF / AIG
# ============================================================================

class GraphConverter:
    """Convert BLIF or AIG files to PyG Data objects for GNN inference.

    Auto-detects file type by extension:
      - .blif → uses blif_to_pyg.BlifToAIG
      - .aig  → uses aig_parser.AIGParser
    """

    def __init__(self):
        self._blif_converter = None
        self._aig_converter = None

    def _import_blif_module(self):
        if self._blif_converter is None:
            from blif_to_pyg import BlifToAIG as BTA
            self._blif_converter = BTA
        return self._blif_converter

    def _import_aig_module(self):
        if self._aig_converter is None:
            from aig_parser import AIGParser as AP
            self._aig_converter = AP
        return self._aig_converter

    def convert(self, file_path: str) -> Data:
        """Convert a BLIF or AIG file to PyG Data.

        Args:
            file_path: Path to .blif or .aig file

        Returns:
            PyG Data object with node features and edge connectivity
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.blif':
            return self._convert_blif(file_path)
        elif ext == '.aig':
            return self._convert_aig(file_path)
        else:
            raise ValueError(f"Unsupported file type: {ext} (use .blif or .aig)")

    def _convert_blif(self, blif_path: str) -> Data:
        """Convert BLIF file to PyG Data."""
        converter_cls = self._import_blif_module()
        converter = converter_cls(blif_path)
        data = converter.build_pyg_data()
        data.original_file = blif_path
        data.graph_type = 'blif'
        return data

    def _convert_aig(self, aig_path: str) -> Data:
        """Convert AIG file to PyG Data."""
        parser_cls = self._import_aig_module()
        parser = parser_cls()
        if not parser.parse_file(aig_path):
            raise RuntimeError(f"Failed to parse AIG file: {aig_path}")
        data = parser.to_pyg_data()
        data.original_file = aig_path
        data.graph_type = 'aig'
        return data

    def convert_with_fault_labels(self, file_path: str, seed: int = 42,
                                   fault_prob: float = 0.1) -> Tuple[Data, torch.Tensor]:
        """Convert and generate fault injection labels for evaluation.

        Args:
            file_path: Path to .blif or .aig file
            seed: Random seed for fault injection
            fault_prob: Fault probability per node

        Returns:
            (data, labels) tuple
        """
        data = self.convert(file_path)
        if data.graph_type == 'blif':
            converter_cls = self._import_blif_module()
            converter = converter_cls(file_path)
            labels = converter.generate_fault_labels(
                seed=seed, fault_prob=fault_prob, deterministic=True
            )
        else:
            # AIG: fallback to simulated labels
            labels = torch.zeros(data.num_nodes, dtype=torch.float)
        return data, labels


# ============================================================================
# 3. GNN Inference Engine
# ============================================================================

class GNNInference:
    """GNN vulnerability prediction inference engine.

    Loads a trained GraphSAGE model and provides inference methods
    for BLIF/AIG circuit designs.
    """

    def __init__(self, model_path: str = None, device: str = 'cpu',
                 threshold: float = 0.05):
        """Initialize the inference engine.

        Args:
            model_path: Path to trained model .pt file.
                        If None, uses default local_best_model.pt.
            device: 'cpu' or 'cuda'
            threshold: Classification threshold for vulnerability
        """
        self.device = torch.device(device)
        self.threshold = threshold
        self.model = None
        self.converter = GraphConverter()
        self.model_info = {}
        self.model_path = model_path

    def load_model(self, model_path: str = None,
                    model_type: str = None) -> bool:
        """Load a trained model checkpoint with auto-architecture detection.

        Auto-detects model architecture (SAGE3 / SAGE2Lite) from checkpoint
        keys. Use `model_type` to override detection.

        Args:
            model_path: Path to .pt file. Falls back to default if None.
            model_type: Override architecture ('SAGE3', 'SAGE2Lite', or None).

        Returns:
            True if model loaded successfully
        """
        model_path = model_path or self.model_path
        if model_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            default_path = os.path.join(script_dir, 'data', 'models',
                                         'local_best_model.pt')
            model_path = default_path

        if not os.path.exists(model_path):
            logger.error(f"[Model] Not found: {model_path}")
            print(f"[ERROR] Model not found: {model_path}")
            print(f"  Train a model first: python _train_local.py")
            return False

        checkpoint = torch.load(model_path, map_location=self.device,
                                 weights_only=True)

        # Detect architecture and input channels
        arch_name, model_cls, h_channels = self._detect_model_config(
            checkpoint, model_type)

        in_channels = self._detect_in_channels(checkpoint)
        self.model = model_cls(in_channels=in_channels,
                                hidden_channels=h_channels)
        self.model.load_state_dict(checkpoint)
        self.model.to(self.device)
        self.model.eval()

        self.model_info = {
            'path': model_path,
            'architecture': arch_name,
            'in_channels': in_channels,
            'hidden_channels': h_channels,
            'num_params': self.model.count_parameters(),
            'loaded': True,
        }

        logger.info(f"[Model] Loaded {arch_name}: {in_channels} in, {self.model_info['num_params']:,} params")
        return True

    @staticmethod
    def _detect_in_channels(checkpoint: Dict) -> int:
        """Detect input feature dimension from checkpoint weights."""
        for key in ['conv1.lin_l.weight', 'conv1.lin.weight']:
            if key in checkpoint:
                return checkpoint[key].shape[1]
        return 12  # default for BLIF 12-dim features

    @staticmethod
    def _detect_model_config(checkpoint: Dict,
                              model_type: str = None) -> tuple:
        """Detect model architecture from checkpoint keys.

        Args:
            checkpoint: Model state dict
            model_type: Override ('SAGE3', 'SAGE2Lite', None)

        Returns:
            (arch_name, model_class, hidden_channels) tuple
        """
        if model_type and model_type in MODEL_REGISTRY:
            cfg = MODEL_REGISTRY[model_type]
            cls_map = {'SAGE3': SAGE3, 'SAGE2Lite': SAGE2Lite}
            return (model_type, cls_map[model_type], cfg['hidden_channels'])

        keys = set(checkpoint.keys())
        for name, cfg in MODEL_REGISTRY.items():
            if cfg['keys'](keys):
                cls_map = {'SAGE3': SAGE3, 'SAGE2Lite': SAGE2Lite}
                logger.info(f"[Model] Auto-detected architecture: {name}")
                return (name, cls_map[name], cfg['hidden_channels'])

        # Fallback: SAGE3 default
        logger.warning(f"[Model] Unknown architecture, defaulting to SAGE3")
        print(f"  [WARN] Unknown architecture, defaulting to SAGE3")
        return ('SAGE3', SAGE3, 128)

    def infer(self, data: Data) -> torch.Tensor:
        """Run inference on a PyG Data object.

        Args:
            data: PyG Data object with .x and .edge_index

        Returns:
            Vulnerability scores [num_nodes] in range [0, 1]
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        # Auto-pad features if input dim < model expected dim
        model_in = self.model_info.get('in_channels', data.x.shape[1])
        x = data.x
        if x.shape[1] < model_in:
            pad = torch.zeros(x.shape[0], model_in - x.shape[1],
                               dtype=torch.float)
            x = torch.cat([x, pad], dim=1)
        elif x.shape[1] > model_in:
            x = x[:, :model_in]

        logger.info(f"[Infer] {len(x)} nodes, {data.edge_index.shape[1]} edges")
        logger.debug(f"[Infer] Running model...")

        with torch.no_grad():
            x = x.to(self.device)
            edge_index = data.edge_index.to(self.device)
            logits = self.model(x, edge_index)
            scores = torch.sigmoid(logits).cpu()

        n_vuln = int((scores >= self.threshold).sum().item())
        logger.metric("Inference", n_vuln, "vulnerable nodes")

        return scores

    def infer_from_blif(self, blif_path: str) -> Dict:
        """Run inference on a BLIF design file.

        Args:
            blif_path: Path to .blif file

        Returns:
            Dict with vulnerability results
        """
        logger.info(f"[Infer] BLIF: {blif_path}")
        try:
            data = self.converter.convert(blif_path)
            scores = self.infer(data)
            return self._build_result(data, scores, blif_path)
        except Exception as e:
            logger.warning(f"[Infer] Failed: {e}")
            raise

    def infer_from_aig(self, aig_path: str) -> Dict:
        """Run inference on an AIG design file.

        Args:
            aig_path: Path to .aig file

        Returns:
            Dict with vulnerability results
        """
        logger.info(f"[Infer] AIG: {aig_path}")
        try:
            data = self.converter.convert(aig_path)
            scores = self.infer(data)
            return self._build_result(data, scores, aig_path)
        except Exception as e:
            logger.warning(f"[Infer] Failed: {e}")
            raise

    def infer_from_file(self, file_path: str) -> Dict:
        """Auto-detect file type and run inference.

        Args:
            file_path: Path to .blif or .aig file

        Returns:
            Dict with vulnerability results
        """
        data = self.converter.convert(file_path)
        scores = self.infer(data)
        return self._build_result(data, scores, file_path)

    def _build_result(self, data: Data, scores: torch.Tensor,
                       source_file: str) -> Dict:
        """Build a structured result dict from inference output."""
        vulnerable_mask = scores >= self.threshold
        vulnerable_indices = torch.where(vulnerable_mask)[0].tolist()
        vulnerable_scores = scores[vulnerable_mask].tolist()

        # Sort vulnerable nodes by score descending
        vuln_list = sorted(
            [(int(idx), float(scores[idx])) for idx in vulnerable_indices],
            key=lambda x: x[1], reverse=True
        )

        # Rank all nodes by score descending
        sorted_indices = torch.argsort(scores, descending=True)
        all_ranked = [
            (int(idx), float(scores[idx])) for idx in sorted_indices
        ]

        # Node type distribution if available
        node_type_dist = {}
        if hasattr(data, 'node_type') and data.node_type is not None:
            type_labels = {0: 'PI', 1: 'PO', 2: 'AND', 3: 'DFF',
                           4: 'CONST0', 5: 'CONST1'}
            for nt in data.node_type.tolist():
                label = type_labels.get(nt, f'UNK({nt})')
                node_type_dist[label] = node_type_dist.get(label, 0) + 1

        result = {
            'source_file': source_file,
            'design_name': getattr(data, 'design_name',
                                    os.path.splitext(os.path.basename(source_file))[0]),
            'graph_type': getattr(data, 'graph_type', 'unknown'),
            'num_nodes': data.num_nodes,
            'num_edges': data.edge_index.shape[1],
            'threshold': self.threshold,
            'num_vulnerable': len(vuln_list),
            'vulnerability_ratio': len(vuln_list) / max(data.num_nodes, 1),
            'max_score': float(scores.max().item()),
            'mean_score': float(scores.mean().item()),
            'min_score': float(scores.min().item()),
            'std_score': float(scores.std().item()),
            'top_10_vulnerable': [
                {'node_id': nid, 'score': round(score, 6)}
                for nid, score in vuln_list[:10]
            ],
            'all_vulnerable_nodes': [
                {'node_id': nid, 'score': round(score, 6)}
                for nid, score in vuln_list
            ],
            'node_type_distribution': node_type_dist,
            'feature_dim': data.x.shape[1],
            'model_path': self.model_info.get('path', ''),
        }

        return result

    def batch_infer(self, file_list: List[str]) -> List[Dict]:
        """Run inference on multiple design files.

        Args:
            file_list: List of paths to .blif or .aig files

        Returns:
            List of result dicts
        """
        logger.section(f"Batch Inference: {len(file_list)} files")
        results = []
        for file_path in file_list:
            try:
                result = self.infer_from_file(file_path)
                results.append(result)
                name = os.path.basename(file_path)
                logger.info(f"  {name}: {result['num_vulnerable']}/{result['num_nodes']} vulnerable (max={result['max_score']:.3f})")
                print(f"  [OK] {name}: "
                      f"{result['num_vulnerable']}/{result['num_nodes']} "
                      f"vulnerable (max_score={result['max_score']:.4f})")
            except Exception as e:
                logger.warning(f"  {os.path.basename(file_path)}: FAILED - {e}")
                print(f"  [FAIL] {file_path}: {e}")
                results.append({
                    'source_file': file_path,
                    'error': str(e),
                })
        logger.metric("Batch", len(results), "files")
        return results

    def integrate_to_hardening_pipeline(self, result: Dict,
                                         pipeline) -> Dict:
        """Integrate vulnerability results into HardeningPipeline.

        Maps vulnerable nodes to signals in the hardening pipeline.
        Returns a strategy override dict for route_strategies().

        Args:
            result: Vulnerability result from infer_from_file()
            pipeline: HardeningPipeline instance
                (from d:/learning/../hardening_pipeline.py)

        Returns:
            strategy_overrides: {signal_name: recommended_strategy}
        """
        logger.section("Integrating to Hardening Pipeline")
        strategy_overrides = {}

        # Signal names available in the pipeline
        signal_names = list(pipeline.module_info.keys())
        if not signal_names:
            logger.warning("[Hardening] No signals registered in pipeline")
            print("[WARN] No signals registered in pipeline")
            return strategy_overrides

        # Map vulnerable node IDs to signal names
        # (heuristic: matching by index position in design)
        vuln_node_ids = {n['node_id']
                         for n in result['all_vulnerable_nodes']}

        for i, sig_name in enumerate(signal_names):
            if i < result['num_nodes'] and i in vuln_node_ids:
                info = pipeline.module_info.get(sig_name, {})
                sig_type = info.get('type', 'data_path')

                # Upgrade strategy for vulnerable signals
                if sig_type == 'fsm':
                    strategy_overrides[sig_name] = 'tmr_state'
                elif sig_type == 'counter':
                    strategy_overrides[sig_name] = 'cnt_comp'
                elif sig_type == 'data_path':
                    strategy_overrides[sig_name] = 'tmr'
                elif sig_type == 'control':
                    strategy_overrides[sig_name] = 'parity'
                elif sig_type == 'memory':
                    strategy_overrides[sig_name] = 'ecc'
                elif sig_type == 'bus':
                    strategy_overrides[sig_name] = 'parity'
                else:
                    strategy_overrides[sig_name] = 'dice'

        num_upgrades = len(strategy_overrides)
        n_vuln = len(result.get('all_vulnerable_nodes', []))
        n_total = result.get('num_nodes', 0)
        logger.info(f"Hardened {n_vuln}/{n_total} vulnerable nodes")
        if num_upgrades > 0:
            print(f"\n[GNN INTEGRATION] {num_upgrades} vulnerable signals "
                  f"flagged for strategy upgrade")
            for sig, strat in sorted(strategy_overrides.items())[:10]:
                print(f"  - {sig} → {strat}")
            if num_upgrades > 10:
                print(f"  ... and {num_upgrades - 10} more")
        else:
            print("[GNN INTEGRATION] No vulnerable signals found")

        return strategy_overrides

    def export_results(self, results: Union[Dict, List[Dict]],
                        output_path: str) -> str:
        """Export inference results to JSON file.

        Args:
            results: Single result dict or list of result dicts
            output_path: Path to output JSON file

        Returns:
            Path to saved file
        """
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        export_data = {
            'inference_engine': 'GNNInference',
            'model': self.model_info,
            'threshold': self.threshold,
            'num_designs': 1 if isinstance(results, dict) else len(results),
            'results': results if isinstance(results, list) else [results],
        }

        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)

        return output_path

    def print_result_summary(self, result: Dict) -> None:
        """Print a human-readable summary of inference results."""
        print("=" * 62)
        print(f"  Vulnerability Inference Report")
        print("=" * 62)
        print(f"  File:     {os.path.basename(result['source_file'])}")
        print(f"  Type:     {result['graph_type']}")
        print(f"  Nodes:    {result['num_nodes']}")
        print(f"  Edges:    {result['num_edges']}")
        print(f"  Features: {result['feature_dim']}-dim")
        print("-" * 62)
        print(f"  Score Distribution:")
        print(f"    Max:   {result['max_score']:.4f}")
        print(f"    Mean:  {result['mean_score']:.4f}")
        print(f"    Min:   {result['min_score']:.4f}")
        print(f"    Std:   {result['std_score']:.4f}")
        print("-" * 62)
        print(f"  Threshold:         {result['threshold']}")
        print(f"  Vulnerable nodes:  {result['num_vulnerable']} / "
              f"{result['num_nodes']} ({result['vulnerability_ratio']*100:.1f}%)")
        print(f"  Node Type Dist:    {result.get('node_type_distribution', 'N/A')}")
        print("-" * 62)
        if result['all_vulnerable_nodes']:
            print(f"  Top-5 Most Vulnerable Nodes:")
            for i, n in enumerate(result['all_vulnerable_nodes'][:5]):
                print(f"    {i+1:>3d}. Node {n['node_id']:>6d}  "
                      f"Score: {n['score']:.6f}")
        print("=" * 62)

    def benchmark(self, file_path: str, num_runs: int = 10) -> Dict:
        """Benchmark inference latency.

        Args:
            file_path: Path to .blif file for benchmarking
            num_runs: Number of inference runs

        Returns:
            Dict with latency statistics
        """
        import time

        data = self.converter.convert(file_path)
        x = data.x.to(self.device)
        edge_index = data.edge_index.to(self.device)

        # Warm-up
        with torch.no_grad():
            for _ in range(3):
                _ = self.model(x, edge_index)

        # Benchmark
        latencies = []
        with torch.no_grad():
            for _ in range(num_runs):
                t0 = time.perf_counter()
                logits = self.model(x, edge_index)
                _ = torch.sigmoid(logits)
                t1 = time.perf_counter()
                latencies.append((t1 - t0) * 1000)  # ms

        stats = {
            'file': file_path,
            'num_nodes': data.num_nodes,
            'num_edges': data.edge_index.shape[1],
            'num_runs': num_runs,
            'mean_latency_ms': float(np.mean(latencies)),
            'min_latency_ms': float(np.min(latencies)),
            'max_latency_ms': float(np.max(latencies)),
            'std_latency_ms': float(np.std(latencies)),
        }
        return stats


# ============================================================================
# 4. CLI
# ============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="GNN Vulnerability Prediction Inference Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single file inference
  python gnn_inference.py --blif data/blifs/design.blif
  python gnn_inference.py --aig data/aigs/design.aig

  # Batch inference
  python gnn_inference.py --batch data/blifs/ --model data/models/local_best_model.pt

  # Full pipeline integration demo
  python gnn_inference.py --demo
        """,
    )

    # Input sources
    input_group = parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument("--blif", type=str, default=None,
                              help="Path to single BLIF file")
    input_group.add_argument("--aig", type=str, default=None,
                              help="Path to single AIG file")
    input_group.add_argument("--input", type=str, default=None,
                              help="Path to BLIF or AIG file (auto-detect)")
    input_group.add_argument("--batch", type=str, default=None,
                              help="Directory of BLIF/AIG files for batch inference")
    input_group.add_argument("--demo", action="store_true",
                              help="Run end-to-end demo with hardening_pipeline")

    # Model
    parser.add_argument("--model", type=str, default=None,
                        help="Path to trained model .pt file")
    parser.add_argument("--model-type", type=str, default=None,
                        choices=['SAGE3', 'SAGE2Lite', 'auto'],
                        help="Model architecture (auto = detect from checkpoint)")
    parser.add_argument("--threshold", type=float, default=0.05,
                        help="Vulnerability classification threshold")

    # Output
    parser.add_argument("--output", type=str, default=None,
                        help="Path to save results JSON")
    parser.add_argument("--benchmark", action="store_true",
                        help="Run latency benchmark")

    return parser.parse_args()


def run_demo():
    """End-to-end demo: BLIF → GNN inference → hardening pipeline."""
    print("=" * 62)
    print("  GNN Inference Demo — Hardening Pipeline Integration")
    print("=" * 62)

    # 1. Initialize inference engine
    print("\n[1] Loading GNN inference engine...")
    engine = GNNInference(threshold=0.05)
    if not engine.load_model():
        print("  [FAIL] Model not found. Train first: python _train_local.py")
        return

    print(f"  Model: {os.path.basename(engine.model_info['path'])}")
    print(f"  Parameters: {engine.model_info['num_params']:,}")
    print(f"  Input channels: {engine.model_info['in_channels']}")

    # 2. Find test BLIF file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    blif_dir = os.path.join(script_dir, 'data', 'blifs')

    if not os.path.isdir(blif_dir):
        blif_dir = os.path.join(script_dir, 'blifs')

    blif_files = [f for f in os.listdir(blif_dir)
                   if f.endswith('.blif')] if os.path.isdir(blif_dir) else []

    if not blif_files:
        print("\n  [SKIP] No BLIF files found for demo.")
        print("  Use: python gnn_inference.py --blif <your_design.blif>")
        return

    # 3. Run inference on first BLIF
    test_blif = os.path.join(blif_dir, blif_files[0])
    print(f"\n[2] Running inference on: {os.path.basename(test_blif)}")
    t0 = time.time()
    result = engine.infer_from_blif(test_blif)
    t_elapsed = time.time() - t0

    engine.print_result_summary(result)
    print(f"\n  Inference time: {t_elapsed*1000:.1f} ms")

    # 4. Integrate with HardeningPipeline
    print(f"\n[3] Integrating with HardeningPipeline...")
    try:
        sys.path.insert(0,
            os.path.join(script_dir, '..', '..', '..'))
        from hardening_pipeline import HardeningPipeline

        pipeline = HardeningPipeline(optimization_goal='balanced')
        # Create a mock design for the demo
        demo_design = os.path.join(script_dir, '..', '..',
                                    'test_mock_data', 'target_design.v')
        if os.path.exists(demo_design):
            pipeline.load_design(demo_design)
            pipeline.analyze()
            overrides = engine.integrate_to_hardening_pipeline(result, pipeline)
            if overrides:
                print(f"\n  Strategy Overrides: {len(overrides)} signals")
                pipeline.route_strategies()
        else:
            print(f"  [SKIP] Demo design not found: {demo_design}")
    except ImportError as e:
        print(f"  [SKIP] hardening_pipeline import failed: {e}")

    # 5. Save results
    output_path = os.path.join(script_dir, 'data',
                                'fpga', 'gnn_inference_demo_result.json')
    engine.export_results(result, output_path)
    print(f"\n[4] Results saved to: {output_path}")
    print("\n  Demo complete!")


def main():
    """Main entry point."""
    args = parse_args()

    if args.demo:
        run_demo()
        return

    # Initialize inference engine
    engine = GNNInference(threshold=args.threshold)
    model_type = args.model_type if args.model_type != 'auto' else None
    if not engine.load_model(args.model, model_type=model_type):
        sys.exit(1)

    # Single file inference
    if args.input or args.blif or args.aig:
        file_path = args.input or args.blif or args.aig
        if not os.path.exists(file_path):
            print(f"[ERROR] File not found: {file_path}")
            sys.exit(1)

        print(f"\n[Inference] {file_path}")
        t0 = time.time()
        result = engine.infer_from_file(file_path)
        t_elapsed = time.time() - t0

        engine.print_result_summary(result)
        print(f"\n  Inference time: {t_elapsed*1000:.1f} ms")

        if args.benchmark:
            print(f"\n[Benchmark] Running {10} inference runs...")
            bench = engine.benchmark(file_path)
            print(f"  Mean latency: {bench['mean_latency_ms']:.3f} ms")
            print(f"  Min latency:  {bench['min_latency_ms']:.3f} ms")
            print(f"  Max latency:  {bench['max_latency_ms']:.3f} ms")

        if args.output:
            engine.export_results(result, args.output)
            print(f"\n[Save] Results → {args.output}")
        else:
            default_out = os.path.splitext(file_path)[0] + '_vulnerability.json'
            engine.export_results(result, default_out)
            print(f"\n[Save] Results → {default_out}")

    # Batch inference
    elif args.batch:
        if not os.path.isdir(args.batch):
            print(f"[ERROR] Directory not found: {args.batch}")
            sys.exit(1)

        supported = ['.blif', '.aig']
        file_list = sorted([
            os.path.join(args.batch, f) for f in os.listdir(args.batch)
            if os.path.splitext(f)[1].lower() in supported
        ])

        if not file_list:
            print(f"[ERROR] No .blif/.aig files found in {args.batch}")
            sys.exit(1)

        print(f"\n[Batch] Running inference on {len(file_list)} files...")
        t0 = time.time()
        results = engine.batch_infer(file_list)
        t_elapsed = time.time() - t0

        # Summary
        successful = [r for r in results if 'error' not in r]
        total_vuln = sum(r['num_vulnerable'] for r in successful)
        total_nodes = sum(r['num_nodes'] for r in successful)

        print(f"\n  Batch Summary:")
        print(f"    Total files:      {len(file_list)}")
        print(f"    Successful:       {len(successful)}")
        print(f"    Failed:           {len(file_list) - len(successful)}")
        print(f"    Total nodes:      {total_nodes}")
        print(f"    Total vulnerable: {total_vuln}")
        print(f"    Time:             {t_elapsed:.2f}s")

        output_path = args.output or os.path.join(args.batch,
                                                    'batch_results.json')
        engine.export_results(results, output_path)
        print(f"\n  Results → {output_path}")


if __name__ == "__main__":
    # Try to import numpy for benchmark; optional
    try:
        import numpy as np
    except ImportError:
        np = type('', (), {'mean': lambda x: sum(x)/len(x),
                           'min': min, 'max': max, 'std': lambda x: 0})()

    main()
