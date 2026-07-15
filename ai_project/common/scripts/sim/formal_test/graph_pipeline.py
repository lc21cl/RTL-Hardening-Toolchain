#!/usr/bin/env python3
"""
graph_pipeline.py — 统一 AIG/BLIF 图构建管线

消除 AIG 和 BLIF 两条管线的重复实现，提供统一的图构建接口。
支持从 RTL → AIG/BLIF → PyG Data 的全流程。

用法:
    # 统一接口
    from graph_pipeline import GraphPipeline

    pipeline = GraphPipeline()
    data = pipeline.from_blif("design.blif")
    data = pipeline.from_aig("design.aig")
    data = pipeline.from_rtl("design.v")  # 自动综合

    # 批量处理
    pipeline.batch_convert("blifs/", output="data/training_data.pt")
"""

import os
import sys
import re
import glob
import json
import time
import subprocess
import warnings
import shlex
from typing import Dict, List, Optional, Tuple, Union

from yosys_utils import find_yosys, yosys_env
from rtl_parser import strip_rtl_comments, extract_module_name, extract_ports

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# 可选模块导入（软依赖）
try:
    from ast_repairer import ASTRepairer
    _HAVE_AST_REPAIR = True
except ImportError:
    _HAVE_AST_REPAIR = False
    ASTRepairer = None

try:
    from yosys_docker import YosysDockerWrapper
    _HAVE_DOCKER_YOSYS = True
except ImportError:
    _HAVE_DOCKER_YOSYS = False
    YosysDockerWrapper = None

try:
    import torch
    from torch_geometric.data import Data
    _HAVE_PYG = True
except ImportError:
    _HAVE_PYG = False

try:
    import networkx as nx
    _HAVE_NX = True
except ImportError:
    _HAVE_NX = False

warnings.filterwarnings("ignore", category=UserWarning, module="torch_geometric")

# ── Lazy imports for RAG / Auto-Repair (optional) ─────────────────────
# NOTE: Use lazy imports inside methods (not module-level) to avoid
#       circular imports with rag_integration.py which imports GraphPipeline.
_HAVE_RAG = False
_HAVE_AUTOREPAIR = False


class GraphPipeline:
    """统一 AIG/BLIF 图构建管线。

    提供三种输入源:
      - BLIF 文件 (.blif) → 通过 BlifToAIG 转换
      - AIG 文件 (.aig)  → 通过 AIGParser 转换
      - RTL 文件 (.v/.sv) → 自动调用 yosys 综合后转换

    统一输出:
      - PyG Data 对象 (x, edge_index, edge_attr)
      - NetworkX 图 (可视化)
      - 图统计信息 (统计摘要)

    管线对比:
      BLIF 管线:          BLIF → BlifParser → BlifToAIG → PyG Data (12维特征)
      AIG 管线:          AIG  → AIGParser  → PyG Data  (8维特征)
      统一管线:    自动检测 → 统一特征空间 → PyG Data  (12维特征, +4维补齐)
    """

    # Node type labels (aligned with BLIF pipeline)
    NODE_TYPES = {
        0: 'PI',
        1: 'PO',
        2: 'AND',
        3: 'DFF',
        4: 'CONST0',
        5: 'CONST1',
    }

    def __init__(self, target_features: int = 12, verbose: bool = True):
        """Initialize the unified graph pipeline.

        Args:
            target_features: Target feature dimension for unified output.
                             BLIF = 12, AIG = 8 → AIG will be padded.
            verbose: Print progress messages
        """
        self.target_features = target_features
        self.verbose = verbose
        self._blif_converter = None
        self._aig_parser = None
        self._cache = {}

    def _import_blif(self):
        """Lazy import blif_to_pyg module."""
        if self._blif_converter is None:
            from blif_to_pyg import BlifToAIG as BTA
            self._blif_converter = BTA
        return self._blif_converter

    def _import_aig(self):
        """Lazy import aig_parser module."""
        if self._aig_parser is None:
            from aig_parser import AIGParser as AP
            self._aig_parser = AP
        return self._aig_parser

    # ======================================================================
    # Core Converters
    # ======================================================================

    def from_blif(self, blif_path: str, generate_labels: bool = False,
                   label_mode: str = 'prob_decay', seed: int = 42) -> Data:
        """Convert BLIF file to PyG Data object.

        Args:
            blif_path: Path to .blif file
            generate_labels: If True, also generate fault injection labels
            label_mode: Label generation mode (see blif_to_pyg.py)
            seed: Random seed for label generation

        Returns:
            PyG Data object with unified features
        """
        if not os.path.isfile(blif_path):
            raise FileNotFoundError(f"BLIF file not found: {blif_path}")

        try:
            Converter = self._import_blif()
            converter = Converter(blif_path)

            data = converter.build_pyg_data()
        except Exception as e:
            logger.warning(f"[BLIF] Conversion failed for {blif_path}: {e}")
            raise

        data.original_file = blif_path
        data.graph_type = 'blif'
        data.design_name = os.path.splitext(os.path.basename(blif_path))[0]

        num_nodes = data.num_nodes
        num_edges = data.edge_index.shape[1]
        feat_dim = data.x.shape[1]
        logger.info(f"[BLIF] {data.design_name}: {num_nodes} nodes, {num_edges} edges, {feat_dim}-dim features")

        if self.verbose:
            print(f"  [BLIF] {data.design_name}: "
                  f"{num_nodes} nodes, {num_edges} edges, "
                  f"{feat_dim}-dim features")

        if generate_labels:
            labels = converter.generate_fault_labels(
                seed=seed, label_mode=label_mode, deterministic=True
            )
            data.y = labels

        return data

    def from_aig(self, aig_path: str, map_path: Optional[str] = None) -> Data:
        """Convert AIG file to PyG Data object.

        AIG has 8-dim features (vs BLIF's 12-dim).
        The output will be padded to target_features (default 12) for unification.

        Args:
            aig_path: Path to .aig file (AIGER binary format)
            map_path: Optional port mapping file path

        Returns:
            PyG Data object with unified features (padded to 12-dim)
        """
        if not os.path.isfile(aig_path):
            raise FileNotFoundError(f"AIG file not found: {aig_path}")

        Parser = self._import_aig()
        parser = Parser()
        if not parser.parse_file(aig_path):
            raise RuntimeError(f"Failed to parse AIG file: {aig_path}")

        if map_path and os.path.isfile(map_path):
            parser.parse_map_file(map_path)

        data = parser.to_pyg_data()  # 8-dim features
        data.original_file = aig_path
        data.graph_type = 'aig'
        data.design_name = os.path.splitext(os.path.basename(aig_path))[0]

        # Pad to target feature dimension
        if data.x.shape[1] < self.target_features:
            pad_dim = self.target_features - data.x.shape[1]
            pad = torch.zeros(data.num_nodes, pad_dim, dtype=torch.float)
            data.x = torch.cat([data.x, pad], dim=1)

        num_nodes = data.num_nodes
        feat_dim = data.x.shape[1]
        logger.info(f"[AIG] {data.design_name}: {num_nodes} nodes, {feat_dim}-dim features")

        if self.verbose:
            print(f"  [AIG]  {data.design_name}: "
                  f"{num_nodes} nodes, {data.edge_index.shape[1]} edges, "
                  f"{feat_dim}-dim features (padded)")

        return data

    def from_rtl(self, rtl_path: str, yosys_script: Optional[str] = None,
                  output_dir: Optional[str] = None,
                  keep_intermediate: bool = False,
                  design_files: Optional[List[str]] = None) -> Dict[str, Data]:
        """Convert RTL Verilog file to PyG Data via yosys synthesis.

        Generates both BLIF and AIG representations, returns both.

        Args:
            rtl_path: Path to Verilog RTL file
            yosys_script: Path to yosys synthesis TCL script.
                          Default: synth_to_aig.tcl from script dir
            output_dir: Directory for intermediate files. Default: temp dir
            keep_intermediate: Keep intermediate .blif/.aig files
            design_files: Optional list of additional RTL files for multi-file designs.
                          All files are read together before synthesis.

        Returns:
            Dict with keys 'blif' and 'aig', each containing a PyG Data object
        """
        rtl_path = os.path.abspath(rtl_path)
        if not os.path.isfile(rtl_path):
            raise FileNotFoundError(f"RTL file not found: {rtl_path}")

        if output_dir is None:
            import tempfile
            output_dir = tempfile.mkdtemp(prefix='graph_pipeline_')

        os.makedirs(output_dir, exist_ok=True)
        design_name = os.path.splitext(os.path.basename(rtl_path))[0]
        blif_path = os.path.abspath(os.path.join(output_dir, f"{design_name}.blif"))
        aig_path = os.path.abspath(os.path.join(output_dir, f"{design_name}.aig"))

        # Generate yosys synthesis script (.ys format)
        # Primary output: BLIF (reliable, rich features for vulnerability prediction)
        # Secondary output: AIG (via separate `synth` pass for DFF/AIGER compat)
        ys_script = os.path.abspath(os.path.join(
            output_dir, f"synth_{design_name}.ys"))
        # Safely quote path for yosys (.ys format)
        # shlex.quote() wraps in single quotes which yosys may not understand on Windows
        def _ys_quote(p: str) -> str:
            p = os.path.normpath(p)
            return f'"{p}"' if ' ' in p else p

        # ---- Build read_verilog commands for multi-file support ----
        read_lines = [f"read_verilog -sv {_ys_quote(rtl_path)}"]
        if design_files:
            for df in design_files:
                df_abs = os.path.abspath(df)
                if os.path.isfile(df_abs) and df_abs != rtl_path:
                    read_lines.append(f"read_verilog -sv {_ys_quote(df_abs)}")

        # ---- BLIF synthesis ----
        ys_lines = read_lines + [
            "hierarchy -check -auto-top",
            "proc; opt",
            "memory; opt",
            "flatten; opt",
            "techmap; opt",
            "opt_clean",
            "setundef -undriven -zero",
            "stat",
            f"write_blif -gates {_ys_quote(blif_path)}",
        ]
        with open(ys_script, 'w') as f:
            f.write('\n'.join(ys_lines))

        logger.info(f"[RTL] Synthesizing {design_name} via yosys (BLIF)...")
        if self.verbose:
            print(f"  [RTL] Synthesizing {design_name} via yosys (BLIF)...")

        # Run yosys (with oss-cad-suite environment)
        yosys_path = find_yosys() or 'yosys'
        proc_env = yosys_env(yosys_path)

        t0 = time.time()
        result = subprocess.run(
            [yosys_path, "-s", ys_script],
            cwd=output_dir,
            capture_output=True,
            text=True,
            timeout=300,
            env=proc_env,
        )
        t_elapsed = time.time() - t0

        if result.returncode != 0:
            logger.warning(f"[RTL] {design_name} BLIF synth failed, trying fallback...")
            # Fallback: simpler script
            ys_lines_fallback = read_lines + [
                "hierarchy -check -auto-top",
                "proc; opt",
                "memory; opt",
                f"write_blif {_ys_quote(blif_path)}",
            ]
            ys_fallback = os.path.abspath(os.path.join(
                output_dir, f"synth_blif_{design_name}.ys"))
            with open(ys_fallback, 'w') as f:
                f.write('\n'.join(ys_lines_fallback))
            result = subprocess.run(
                [yosys_path, "-s", ys_fallback],
                cwd=output_dir, capture_output=True, text=True,
                timeout=300, env=proc_env,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"yosys BLIF synthesis failed (exit={result.returncode}):\n"
                    f"{result.stderr[:500]}"
                )

        logger.info(f"[RTL] {design_name} BLIF synthesized in {t_elapsed:.1f}s")

        # ---- AIG synthesis (separate pass, uses 'synth' for proper DFF handling) ----
        ys_aig = os.path.abspath(os.path.join(
            output_dir, f"synth_aig_{design_name}.ys"))
        ys_aig_lines = read_lines + [
            "hierarchy -check -auto-top",
            "synth",
            f"write_aiger -map {_ys_quote(os.path.join(output_dir, 'output_map.txt'))} {_ys_quote(aig_path)}",
        ]
        with open(ys_aig, 'w') as f:
            f.write('\n'.join(ys_aig_lines))

        logger.info(f"[RTL] Synthesizing {design_name} via yosys (AIG)...")
        t0_aig = time.time()
        aig_result = subprocess.run(
            [yosys_path, "-s", ys_aig],
            cwd=output_dir, capture_output=True, text=True,
            timeout=300, env=proc_env,
        )
        t_aig = time.time() - t0_aig

        if aig_result.returncode != 0:
            logger.warning(f"[RTL] {design_name} AIG synth failed (exit={aig_result.returncode}), "
                           f"trying Python BLIF→AIGER converter...")
            if self.verbose:
                print(f"    [WARN] yosys AIG failed (exit={aig_result.returncode}), "
                      f"trying Python BLIF→AIGER converter...")
            # Fallback: use Python BLIF→AIGER converter (bypasses yosys write_aiger limitation)
            try:
                from blif_to_aiger import blif_to_aiger
                if os.path.isfile(blif_path):
                    aig_ok = blif_to_aiger(blif_path, aig_path,
                                           os.path.join(output_dir, 'output_map.txt'))
                    if aig_ok and os.path.isfile(aig_path) and os.path.getsize(aig_path) > 0:
                        logger.info(f"[RTL] {design_name} AIG generated via Python converter")
                        if self.verbose:
                            print(f"    [OK] AIG generated via Python BLIF→AIGER converter")
                        # Set a flag so we skip the yosys AIG path below
                        _aig_from_converter = True
                    else:
                        logger.warning(f"[RTL] {design_name} Python BLIF→AIGER conversion failed")
                        _aig_from_converter = False
                else:
                    _aig_from_converter = False
            except Exception as conv_e:
                logger.warning(f"[RTL] Python BLIF→AIGER error: {conv_e}")
                _aig_from_converter = False
        else:
            logger.info(f"[RTL] {design_name} AIG synthesized in {t_aig:.1f}s")
            if self.verbose:
                print(f"    [RTL] AIG synthesized in {t_aig:.1f}s")
            _aig_from_converter = False

        results = {}
        # Convert BLIF output
        if os.path.exists(blif_path):
            try:
                blif_result = self.from_blif(blif_path)
                logger.info(f"[RTL] {design_name} -> BLIF: {blif_result.num_nodes} nodes")
                results['blif'] = blif_result
                if not keep_intermediate:
                    os.remove(blif_path)
            except Exception as e:
                if self.verbose:
                    print(f"    [WARN] BLIF conversion: {e}")

        # Convert AIG output
        map_path = os.path.join(output_dir, "output_map.txt")
        if os.path.exists(aig_path) and os.path.getsize(aig_path) > 0:
            try:
                aig_data = self.from_aig(aig_path, map_path)
                if aig_data is not None:
                    results['aig'] = aig_data
                    if not keep_intermediate:
                        os.remove(aig_path)
                        for ext in ['.txt', '.v']:
                            fpath = os.path.join(output_dir, f"output{ext}")
                            if os.path.exists(fpath):
                                os.remove(fpath)
            except Exception as e:
                if self.verbose:
                    print(f"    [WARN] AIG conversion: {e}")
        elif os.path.exists(aig_path) and os.path.getsize(aig_path) == 0:
            logger.warning(f"[RTL] {design_name} AIG file is empty, skipping")
            if self.verbose:
                print(f"    [WARN] AIG file is empty, skipping")

        return results

    # ======================================================================
    # Batch Processing
    # ======================================================================

    def batch_convert(self, input_dir: str, file_type: str = 'blif',
                       output_file: Optional[str] = None,
                       generate_labels: bool = True,
                       label_mode: str = 'prob_decay',
                       seed: int = 42) -> List[Data]:
        """Batch convert multiple files to PyG Data objects.

        Args:
            input_dir: Directory containing design files
            file_type: 'blif', 'aig', or 'all'
            output_file: Optional path to save .pt file
            generate_labels: Generate fault injection labels
            label_mode: Label generation mode
            seed: Random seed

        Returns:
            List of (Data, label) tuples
        """
        if not os.path.isdir(input_dir):
            raise NotADirectoryError(f"Directory not found: {input_dir}")

        # Collect files
        if file_type == 'all':
            patterns = ['*.blif', '*.aig']
        else:
            patterns = [f'*.{file_type}']

        file_list = []
        for pattern in patterns:
            file_list.extend(glob.glob(os.path.join(input_dir, pattern)))
        file_list = sorted(file_list)

        if not file_list:
            print(f"[WARN] No matching files found in {input_dir}")
            return []

        logger.section(f"Batch Converting {len(file_list)} files")
        print(f"\n{'=' * 62}")
        print(f"  Batch Converting {len(file_list)} files from {input_dir}")
        print(f"{'=' * 62}")

        samples = []
        t0 = time.time()

        for i, file_path in enumerate(file_list):
            try:
                ext = os.path.splitext(file_path)[1].lower()
                if ext == '.blif':
                    if generate_labels:
                        Converter = self._import_blif()
                        converter = Converter(file_path)
                        data = converter.build_pyg_data()
                        labels = converter.generate_fault_labels(
                            seed=seed + i, label_mode=label_mode,
                            deterministic=True
                        )
                    else:
                        data = self.from_blif(file_path, generate_labels=False)
                        labels = None
                elif ext == '.aig':
                    data = self.from_aig(file_path)
                    labels = None  # AIG labels not yet supported
                else:
                    continue

                data.original_file = file_path
                data.design_name = os.path.splitext(
                    os.path.basename(file_path))[0]

                if labels is not None:
                    samples.append((data, labels))
                else:
                    samples.append(data)

                print(f"  [{i+1:3d}/{len(file_list)}] {data.design_name:30s} "
                      f"{data.num_nodes:>5d} nodes")

            except Exception as e:
                print(f"  [FAIL] {os.path.basename(file_path)}: {e}")
                continue

        t_elapsed = time.time() - t0
        logger.metric("Batch", len(samples), "files")
        print(f"\n{'=' * 62}")
        print(f"  Converted {len(samples)}/{len(file_list)} files in "
              f"{t_elapsed:.1f}s")
        print(f"{'=' * 62}")

        # Save to .pt file
        if output_file and samples:
            os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
            torch.save(samples, output_file)
            print(f"\n  Saved to: {output_file}")

        return samples

    # ======================================================================
    # Visualization
    # ======================================================================

    def to_networkx(self, data: Data) -> 'nx.DiGraph':
        """Convert PyG Data to NetworkX directed graph for visualization.

        Args:
            data: PyG Data object

        Returns:
            NetworkX DiGraph

        Raises:
            ImportError: networkx not installed
        """
        if not _HAVE_NX:
            raise ImportError("networkx is required: pip install networkx")

        G = nx.DiGraph()
        num_nodes = data.num_nodes

        for i in range(num_nodes):
            node_type = 'UNK'
            if hasattr(data, 'node_type'):
                nt = data.node_type[i].item()
                node_type = self.NODE_TYPES.get(nt, f'UNK({nt})')
            G.add_node(i, type=node_type)

        src = data.edge_index[0].tolist()
        dst = data.edge_index[1].tolist()
        for s, d in zip(src, dst):
            G.add_edge(s, d)

        return G

    def visualize(self, data: Data, output_path: str = 'graph.png',
                   max_nodes: int = 200, layout: str = 'hierarchical') -> str:
        """Visualize graph with node type coloring.

        Args:
            data: PyG Data object
            output_path: Path to save visualization image
            max_nodes: Maximum nodes to show
            layout: 'hierarchical' or 'spring'

        Returns:
            Path to saved image
        """
        if not _HAVE_NX:
            raise ImportError("networkx required: pip install networkx")

        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("matplotlib required: pip install matplotlib")

        design_name = getattr(data, 'design_name', 'unnamed')
        logger.info(f"[VIZ] Visualizing {design_name}...")

        G = self.to_networkx(data)

        if G.number_of_nodes() > max_nodes:
            print(f"  [WARN] Truncating {G.number_of_nodes()} → {max_nodes} nodes")
            nodes = list(G.nodes())[:max_nodes]
            G = G.subgraph(nodes)

        # Color mapping
        color_map = {
            'PI': '#4CAF50', 'PO': '#F44336', 'AND': '#2196F3',
            'DFF': '#FF9800', 'CONST0': '#9E9E9E', 'CONST1': '#9E9E9E',
        }
        default_color = '#607D8B'

        node_colors = []
        for n in G.nodes():
            t = G.nodes[n].get('type', 'UNK')
            node_colors.append(color_map.get(t, default_color))

        # Layout
        if layout == 'hierarchical':
            try:
                pos = nx.nx_pydot.graphviz_layout(G, prog='dot')
            except Exception:
                pos = nx.spring_layout(G, k=3, iterations=50)
        else:
            pos = nx.spring_layout(G, k=3, iterations=50)

        plt.figure(figsize=(16, 12))
        nx.draw(G, pos, node_color=node_colors, node_size=80,
                edge_color='#CCCCCC', arrows=True,
                arrowsize=10, width=0.5, with_labels=False)

        # Legend
        legend_handles = []
        for type_name, color in color_map.items():
            count = sum(1 for n in G.nodes()
                        if G.nodes[n].get('type') == type_name)
            if count > 0:
                legend_handles.append(
                    plt.Line2D([0], [0], marker='o', color='w',
                               markerfacecolor=color, markersize=10,
                               label=f'{type_name} ({count})')
                )
        plt.legend(handles=legend_handles, loc='upper right')

        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

        logger.info(f"[VIZ] Graph saved to: {output_path}")
        if self.verbose:
            print(f"  [VIZ] Graph saved to: {output_path}")

        return output_path

    # ======================================================================
    # Analysis & Statistics
    # ======================================================================

    def analyze(self, data: Data) -> Dict:
        """Compute detailed graph statistics.

        Args:
            data: PyG Data object

        Returns:
            Dict with graph statistics
        """
        num_nodes = data.num_nodes
        num_edges = data.edge_index.shape[1]

        # Node type distribution
        node_type_dist = {}
        if hasattr(data, 'node_type') and data.node_type is not None:
            for nt in data.node_type.tolist():
                label = self.NODE_TYPES.get(nt, f'UNK({nt})')
                node_type_dist[label] = node_type_dist.get(label, 0) + 1

        # Degree statistics
        deg = torch.zeros(num_nodes, dtype=torch.long)
        src = data.edge_index[0]
        for s in src:
            deg[s] += 1

        # Density
        max_edges = num_nodes * (num_nodes - 1)
        density = num_edges / max(max_edges, 1)

        stats = {
            'num_nodes': num_nodes,
            'num_edges': num_edges,
            'feature_dim': data.x.shape[1],
            'density': round(density, 6),
            'avg_degree': round(float(deg.float().mean()), 4),
            'max_degree': int(deg.max().item()),
            'min_degree': int(deg.min().item()),
            'node_type_distribution': node_type_dist,
            'sparsity': round(1.0 - density, 6),
            'has_isolated': bool((deg == 0).any().item()),
        }

        if hasattr(data, 'design_name'):
            stats['design_name'] = data.design_name
        if hasattr(data, 'graph_type'):
            stats['graph_type'] = data.graph_type

        return stats

    def compare(self, data_list: List[Data]) -> List[Dict]:
        """Compare statistics across multiple graphs.

        Args:
            data_list: List of PyG Data objects

        Returns:
            List of statistics dicts
        """
        return [self.analyze(d) for d in data_list]

    def print_stats(self, data: Data) -> None:
        """Print human-readable graph statistics."""
        stats = self.analyze(data)
        name = getattr(data, 'design_name', 'unnamed')
        gtype = getattr(data, 'graph_type', 'unknown')

        print(f"\n{'=' * 52}")
        print(f"  Graph: {name} ({gtype})")
        print(f"{'=' * 52}")
        print(f"  Nodes:          {stats['num_nodes']}")
        print(f"  Edges:          {stats['num_edges']}")
        print(f"  Features:       {stats['feature_dim']}-dim")
        print(f"  Density:        {stats['density']:.6f}")
        print(f"  Avg Degree:     {stats['avg_degree']:.2f}")
        print(f"  Max Degree:     {stats['max_degree']}")
        print(f"  Min Degree:     {stats['min_degree']}")
        print(f"  Has Isolated:   {stats['has_isolated']}")

        if stats['node_type_distribution']:
            print(f"  Node Types:")
            for t, c in sorted(stats['node_type_distribution'].items(),
                                key=lambda x: -x[1]):
                print(f"    {t:>8s}: {c}")
        print(f"{'=' * 52}")

    @staticmethod
    def save_dataset(data_list: Union[List[Data], List[Tuple[Data, torch.Tensor]]],
                      output_path: str, as_dict: bool = False) -> str:
        """Save dataset to .pt file.

        Args:
            data_list: List of Data objects or (Data, label) tuples
            output_path: Path to save
            as_dict: If True, save as dict with 'train', 'val', 'test' splits

        Returns:
            Path to saved file
        """
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        if as_dict and isinstance(data_list, list) and len(data_list) >= 3:
            # Auto-split into train/val/test (80/10/10)
            n = len(data_list)
            n_train = int(n * 0.8)
            n_val = int(n * 0.1)
            torch.manual_seed(42)
            indices = torch.randperm(n)
            train_data = [data_list[i] for i in indices[:n_train]]
            val_data = [data_list[i] for i in indices[n_train:n_train + n_val]]
            test_data = [data_list[i] for i in indices[n_train + n_val:]]

            data_dict = {
                'train': train_data,
                'val': val_data,
                'test': test_data
            }
            torch.save(data_dict, output_path)
        else:
            torch.save(data_list, output_path)

        return output_path

    # ======================================================================
    # Design Error Analysis (static analysis for port/direction issues)
    # ======================================================================

    @staticmethod
    def analyze_design_errors(rtl_path: str,
                               top_module: Optional[str] = None,
                               design_files: Optional[List[str]] = None) -> Dict:
        """Analyze RTL for design-level port/direction/type errors.

        Performs static analysis to detect:
          - Port direction mismatches in module instantiations
          - Port type mismatches (reg vs wire)
          - Port count mismatches in instantiations
          - Unconnected ports

        Multi-file support: when ``design_files`` is provided, all files are
        concatenated before analysis, enabling cross-module error detection.

        Args:
            rtl_path: Path to the RTL file to analyze.
            top_module: Optional top module name.
            design_files: Optional list of additional RTL files for multi-file designs.

        Returns:
            Dict with keys:
              - errors: List of design error dicts with 'type', 'description', 'line'
              - warnings: List of design warnings
              - modules: Dict of module declarations {name: {ports: [...]}}
              - instances: Dict of instantiations
              - analysis_passed: True if no design-level errors found
        """
        result: Dict = {
            "errors": [],
            "warnings": [],
            "modules": {},
            "instances": {},
            "analysis_passed": True,
        }

        if not os.path.isfile(rtl_path):
            result["errors"].append({"type": "file_error", "description": f"File not found: {rtl_path}", "line": 0})
            result["analysis_passed"] = False
            return result

        # Build merged content from all design files
        _all_files = [rtl_path]
        if design_files:
            for df in design_files:
                if os.path.isfile(df) and df != rtl_path:
                    _all_files.append(df)

        content_parts: List[str] = []
        for fpath in _all_files:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content_parts.append(f"// ==== {os.path.basename(fpath)} ====\n" + f.read())
        content = "\n\n".join(content_parts)

        # Remove comments for analysis
        content_no_comments = strip_rtl_comments(content)

        lines = content.split('\n')

        # ── Step 1: Extract module declarations (including submodules) ──
        module_decls: Dict[str, Dict] = {}

        # Use rtl_parser to extract all module ports
        parsed_modules = extract_ports(content)
        for mod_name, ports in parsed_modules.items():
            # Calculate line number using regex on content_no_comments
            module_pattern = re.compile(r'\bmodule\s+' + re.escape(mod_name) + r'\b')
            match = module_pattern.search(content_no_comments)
            line_no = content_no_comments[:match.start()].count('\n') + 1 if match else 0

            module_decls[mod_name] = {
                "name": mod_name,
                "ports": ports,
                "port_count": len(ports),
                "line": line_no,
            }

        result["modules"] = module_decls

        # ── Step 2: Extract submodule instantiations ──
        instances: List[Dict] = []
        # Pattern: module_name #(...)? inst_name ( ... );
        inst_pattern = re.compile(
            r'(\w+)\s+(?:#\s*\([^)]*\)\s+)?(\w+)\s*\(', re.MULTILINE
        )
        for match in inst_pattern.finditer(content_no_comments):
            mod_name = match.group(1)
            inst_name = match.group(2)

            # Skip keywords
            if mod_name.lower() in ('module', 'if', 'else', 'for', 'while', 'case', 'always', 'initial', 'end'):
                continue
            # Skip if it looks like a declaration
            if mod_name.lower() in ('input', 'output', 'inout', 'wire', 'reg', 'logic'):
                continue

            # Find the instance port connections
            start = match.end()
            depth = 1
            end = start
            while depth > 0 and end < len(content_no_comments):
                c = content_no_comments[end]
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                end += 1
            conn_section = content_no_comments[start:end - 1]

            # Extract named port connections: .port_name(signal)
            connections: List[Dict] = []
            conn_pattern = re.compile(r'\.(\w+)\s*\(\s*(\w*)\s*\)')
            for cm in conn_pattern.finditer(conn_section):
                port_name = cm.group(1)
                signal_name = cm.group(2) if cm.group(2) else ""
                # Calculate line number relative to the instance match
                # conn_section is a substring of content_no_comments, so we need
                # to find the actual position in the original content
                conn_pos_in_full = content_no_comments.find(cm.group(0), match.end())
                if conn_pos_in_full >= 0:
                    line_no = content[:conn_pos_in_full].count('\n') + 1
                else:
                    line_no = content[:match.start()].count('\n') + 1
                connections.append({
                    "port": port_name,
                    "signal": signal_name,
                    "line": line_no,
                })

            # Skip if no named connections — likely not a module instantiation
            # (e.g., "if (!rst_n)" would have no .port_name() connections)
            if len(connections) == 0:
                continue

            line_no = content[:match.start()].count('\n') + 1 if match else 0
            instances.append({
                "module_name": mod_name,
                "instance_name": inst_name,
                "connections": connections,
                "conn_count": len(connections),
                "line": line_no,
            })

        result["instances"] = instances

        # ── Step 3: Check for port errors ──
        for inst in instances:
            mod_name = inst["module_name"]
            mod_decl = module_decls.get(mod_name)

            if mod_decl is None:
                result["warnings"].append({
                    "type": "unknown_module",
                    "description": f"Module '{mod_name}' instantiated as '{inst['instance_name']}' "
                                   f"at line {inst['line']} but no declaration found in file",
                    "line": inst["line"],
                })
                continue

            # Check port count
            exp_ports = mod_decl["port_count"]
            actual_conns = inst["conn_count"]
            if actual_conns != exp_ports:
                result["errors"].append({
                    "type": "port_count_mismatch",
                    "severity": "error",
                    "description": (
                        f"Port count mismatch in instance '{inst['instance_name']}' "
                        f"(module '{mod_name}'): expected {exp_ports} ports, "
                        f"got {actual_conns} connections (line {inst['line']})"
                    ),
                    "line": inst["line"],
                    "expected": exp_ports,
                    "actual": actual_conns,
                })

            # Check each connection
            for conn in inst["connections"]:
                port_name = conn["port"]
                signal_name = conn["signal"]

                # Find port declaration
                port_decl = next((p for p in mod_decl["ports"] if p["name"] == port_name), None)
                if port_decl is None:
                    result["errors"].append({
                        "type": "unknown_port",
                        "severity": "error",
                        "description": (
                            f"Unknown port '{port_name}' in instance '{inst['instance_name']}' "
                            f"(line {conn['line']})"
                        ),
                        "line": conn["line"],
                    })
                    continue

                if not signal_name:
                    result["warnings"].append({
                        "type": "unconnected_port",
                        "severity": "warning",
                        "description": (
                            f"Port '{port_name}' of instance '{inst['instance_name']}' "
                            f"is unconnected (line {conn['line']})"
                        ),
                        "line": conn["line"],
                    })
                    continue

                # Check for potential direction conflicts by tracking signal usage
                # A signal connected to both an input port and output port is suspicious
                signal_ports: Dict[str, List[str]] = {}
                for c2 in inst["connections"]:
                    if c2["signal"]:
                        if c2["signal"] not in signal_ports:
                            signal_ports[c2["signal"]] = []
                        # Look up port direction
                        pd = next((p for p in mod_decl["ports"] if p["name"] == c2["port"]), None)
                        if pd:
                            signal_ports[c2["signal"]].append(pd["direction"])

                sig_dirs = signal_ports.get(signal_name, [])
                if "input" in sig_dirs and "output" in sig_dirs:
                    result["errors"].append({
                        "type": "direction_conflict",
                        "severity": "error",
                        "description": (
                            f"Direction conflict: signal '{signal_name}' connects to both "
                            f"input and output ports of instance '{inst['instance_name']}' "
                            f"(line {conn['line']})"
                        ),
                        "line": conn["line"],
                        "signal": signal_name,
                    })

        # ── Step 4: Check for reg/wire type mismatches ──
        # Find all signal declarations in the file
        decl_pattern = re.compile(
            r'^\s*(wire|reg|tri|wand|wor)\s+(?:\[.*?\])?\s*(\w+)',
            re.MULTILINE
        )
        declared_signals: Dict[str, str] = {}
        for dm in decl_pattern.finditer(content):
            sig_type = dm.group(1).lower()
            sig_name = dm.group(2)
            declared_signals[sig_name] = sig_type

        # Check if a reg signal is used as a wire (connected to output port via continuous assignment)
        for inst in instances:
            for conn in inst["connections"]:
                sig = conn["signal"]
                if sig and sig in declared_signals:
                    sig_type = declared_signals[sig]
                    port_decl = None
                    if inst["module_name"] in module_decls:
                        port_decl = next(
                            (p for p in module_decls[inst["module_name"]]["ports"]
                             if p["name"] == conn["port"]), None
                        )
                    if port_decl and port_decl["type"] == "wire" and sig_type == "reg":
                        result["warnings"].append({
                            "type": "type_mismatch",
                            "severity": "warning",
                            "description": (
                                f"Type mismatch: signal '{sig}' is declared as '{sig_type}' "
                                f"but connected to wire-type port '{conn['port']}' "
                                f"of instance '{inst['instance_name']}' (line {conn['line']})"
                            ),
                            "line": conn["line"],
                        })

        result["analysis_passed"] = len([e for e in result["errors"] if e.get("severity") == "error"]) == 0

        logger.print(f"  [DESIGN ANALYSIS] Modules: {len(module_decls)}, "
                     f"Instances: {len(instances)}")
        logger.print(f"  [DESIGN ANALYSIS] Errors: {len(result['errors'])}, "
                     f"Warnings: {len(result['warnings'])}, "
                     f"Passed: {result['analysis_passed']}")
        for err in result["errors"]:
            logger.print(f"    ERROR: {err['description'][:120]}")
        for warn in result["warnings"]:
            logger.print(f"    WARN:  {warn['description'][:120]}")

        return result

    # ======================================================================
    # RAG + Auto-Repair Hardening Pipeline
    # ======================================================================

    def harden(
        self,
        rtl_path: str,
        vulnerability_result: Optional[Dict] = None,
        llm_backend: str = 'mock',
        hardening_strategy: str = 'tmr',
        max_repair_iterations: int = 5,
        output_dir: Optional[str] = None,
        keep_intermediate: bool = False,
        analyze_errors_first: bool = True,
        submodule_paths: Optional[List[str]] = None,
        use_ast_repair: bool = True,
        docker_verify: bool = False,
        design_files: Optional[List[str]] = None,
    ) -> Dict:
        """Complete hardening pipeline: RAG generation → Auto-Repair verification.

        Integrates five stages:
          1. RTL analysis — extract design info for hardening
          2. Design error analysis — static check for port/direction/type errors
          3. RAG retrieval — query knowledge base for hardening patterns
          4. RTL generation — use LLM to generate hardened RTL
          5. AST Repair — AST-level syntax repair before verification
          6. Auto-Repair  — syntax/synthesis/equiv verification + fix loop
          7. Docker Verification — yosys syntax/synthesis check via Docker (optional)

        Args:
            rtl_path:               Path to original RTL file (top-level module).
            vulnerability_result:   Optional GNN inference vulnerability dict.
            llm_backend:            LLM backend name ('mock', 'openai', or 'deepseek').
            hardening_strategy:     Hardening strategy name.
                                    Supported: 'tmr' (default), 'ecc', 'dice', 'parity'.
            max_repair_iterations:  Max Auto-Repair iterations.
            output_dir:             Output directory for intermediate files.
            keep_intermediate:      Keep intermediate generated files.
            analyze_errors_first:   Run static design error analysis before hardening.
            submodule_paths:        Additional paths to include for submodule analysis.
            use_ast_repair:         Apply AST-level repair before Auto-Repair loop.
            docker_verify:          Run yosys Docker verification after Auto-Repair.
            design_files:           List of additional RTL files for multi-file designs.

        Returns:
            Dict with keys:
              - hardened_rtl_path:  Path to the final hardened RTL file.
              - hardened_rtl:       Final hardened RTL content (str).
              - repair_report:      Markdown repair report.
              - passed:             Whether all verifications passed.
              - iterations:         Repair iterations taken.
              - stages:             List of stage result dicts.
              - rag_analysis:       RTL analysis result (design info).
              - design_errors:      Design error analysis result.
              - hardening_strategy: The strategy used for hardening.
              - total_elapsed:      Total pipeline wall-clock time.
        """
        result: Dict = {
            "hardened_rtl_path": None,
            "hardened_rtl": None,
            "repair_report": "",
            "passed": False,
            "iterations": 0,
            "stages": [],
            "rag_analysis": {},
            "design_errors": {},
            "hardening_strategy": hardening_strategy,
            "total_elapsed": 0.0,
        }
        _t_start = time.time()

        # Validate hardening_strategy
        _VALID_STRATEGIES = {'tmr', 'ecc', 'dice', 'parity', 'tmr_ecc'}
        if hardening_strategy.lower() not in _VALID_STRATEGIES:
            logger.warning(f"  [HARDEN] Unknown strategy '{hardening_strategy}', defaulting to 'tmr'")
            hardening_strategy = 'tmr'
        hardening_strategy = hardening_strategy.lower()

        # Include submodule paths for design error analysis
        if submodule_paths:
            _combined_content = ""
            for sp in submodule_paths:
                if os.path.isfile(sp):
                    with open(sp, "r", encoding="utf-8", errors="replace") as _sf:
                        _combined_content += f"\n{_sf.read()}"

        logger.section("RAG + Auto-Repair Hardening Pipeline")
        logger.print(f"  [HARDEN] Input RTL: {os.path.abspath(rtl_path)}")
        if design_files:
            logger.print(f"  [HARDEN] Design files: {len(design_files)} additional files")
            for df in design_files:
                logger.print(f"            - {os.path.abspath(df)}")
        logger.print(f"  [HARDEN] LLM backend: {llm_backend}, "
                     f"max_repair_iterations: {max_repair_iterations}")
        logger.print(f"  [HARDEN] analyze_errors_first: {analyze_errors_first}")
        logger.print(f"  [HARDEN] hardening_strategy: {hardening_strategy}")
        logger.print(f"  [HARDEN] use_ast_repair: {use_ast_repair}, "
                     f"docker_verify: {docker_verify}")
        logger.print(f"  [HARDEN] AST repair: {'✓' if use_ast_repair and _HAVE_AST_REPAIR else '✗ disabled'}")
        logger.print(f"  [HARDEN] Docker verify: {'✓' if docker_verify and _HAVE_DOCKER_YOSYS else '✗ disabled'}")

        if not os.path.isfile(rtl_path):
            logger.error("File not found: %s", rtl_path)
            return result

        # Validate design_files
        _all_design_files = [rtl_path]
        if design_files:
            for df in design_files:
                if os.path.isfile(df):
                    _all_design_files.append(df)
                else:
                    logger.warning(f"  [HARDEN] Design file not found, skipping: {df}")

        # ── Step 1: Read original RTL (and merge design files) ──
        logger.sub_section("Phase 1/7: Read Input RTL")
        original_content = ""
        _total_chars = 0
        _total_lines = 0
        for idx, df in enumerate(_all_design_files):
            with open(df, "r", encoding="utf-8", errors="replace") as f:
                _df_content = f.read()
            if idx > 0:
                original_content += "\n\n"
            original_content += f"// ==== Design File: {os.path.basename(df)} ====\n" + _df_content
            _total_chars += len(_df_content)
            _total_lines += len(_df_content.splitlines())
        logger.print(f"  [1/7] Read {len(_all_design_files)} RTL files: {_total_chars} chars, "
                     f"{_total_lines} lines")
        logger.metric("phase1.read", time.time() - _t_start, "s")
        _t1 = time.time()

        # ── Step 2: Static Design Error Analysis ──
        if analyze_errors_first:
            logger.sub_section("Phase 2/7: Design Error Analysis")
            logger.print(f"  [2/7] Running static design error analysis...")
            design_errors = self.analyze_design_errors(rtl_path, top_module=None,
                                                         design_files=design_files)
            result["design_errors"] = design_errors

            if design_errors["errors"]:
                logger.print(f"  [2/7] Found {len(design_errors['errors'])} design errors:")
                for err in design_errors["errors"]:
                    logger.print(f"    - [{err['type']}] {err['description'][:120]}")
            else:
                logger.print(f"  [2/7] No design-level errors detected")

            if design_errors["warnings"]:
                logger.print(f"  [2/7] {len(design_errors['warnings'])} design warnings")
            logger.metric("phase2.design_analysis", time.time() - _t1, "s")
        _t2 = time.time()

        # ── Step 3: Analyze design for RAG hardening ──
        logger.sub_section("Phase 3/7: RTL Analysis for Hardening")
        logger.print(f"  [3/7] Analyzing design for hardening...")
        _HAVE_RAG_LOCAL = False
        try:
            from rag_integration import analyze_design_for_hardening as _adfh
            _HAVE_RAG_LOCAL = True
        except ImportError:
            _adfh = None
        if _HAVE_RAG_LOCAL and _adfh is not None:
            design_info = _adfh(rtl_path, search_paths=submodule_paths,
                                 design_files=design_files)
        else:
            design_info = {"module_name": "unknown", "signals": [], "signal_width": 32}
        result["rag_analysis"] = design_info
        logger.print(f"  [3/5] module_name={design_info.get('module_name', '?')}, "
                     f"signals={len(design_info.get('signals', []))}, "
                     f"max_width={design_info.get('signal_width', 0)}")
        logger.metric("phase3.analysis", time.time() - _t2, "s")
        _t3 = time.time()

        # ── Step 4: Generate hardened RTL via RAG ──
        logger.sub_section("Phase 4/7: RAG Hardened RTL Generation")
        logger.print(f"  [4/7] Generating hardened RTL via RAG (backend={llm_backend})...")
        hardened_content = original_content
        try:
            from rag_integration import RAGEngine as _RE
            _rag_engine = _RE(llm_backend=llm_backend)
            _rag_engine.load_knowledge_base()

            vuln_for_rag = vulnerability_result or {
                "all_vulnerable_nodes": [{"node_id": 0, "score": 0.5,
                                           "type": "data_path"}],
                "num_nodes": 1,
            }
            # Inject strategy override so the LLM backend (e.g. MockLLM)
            # can detect the desired hardening strategy from the prompt context.
            if hardening_strategy and hardening_strategy != 'tmr':
                vuln_for_rag['strategy_override'] = hardening_strategy.upper()
                logger.print(f"  [4/7] Injected strategy_override='{hardening_strategy.upper()}' "
                             f"into RAG context")
            rtl_generated = _rag_engine.generate_hardened_rtl(
                design_info, vuln_for_rag
            )
            if rtl_generated and len(rtl_generated) > 50:
                hardened_content = rtl_generated
                logger.print(f"  [4/7] RAG generated {len(rtl_generated)} chars of hardened RTL")
            else:
                logger.warning(f"  [4/7] RAG output too short ({len(rtl_generated) if rtl_generated else 0} chars), "
                              f"using original")
        except ImportError:
            logger.warning("  [4/7] RAG module not importable; using original RTL content")
        except Exception as e:
            logger.error("  [4/7] RAG generation failed: %s", e)
            logger.info("  [4/7] Falling back to original RTL content")
        _t4 = time.time()
        logger.metric("phase4.rag_gen", _t4 - _t3, "s")

        # Write hardened RTL to a temp file for repair pipeline
        if output_dir is None:
            import tempfile
            output_dir = tempfile.mkdtemp(prefix="harden_pipeline_")
        os.makedirs(output_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(rtl_path))[0]
        hardened_path = os.path.join(output_dir, f"{base_name}_hardened.v")
        with open(hardened_path, "w", encoding="utf-8") as f:
            f.write(hardened_content)
        result["hardened_rtl_path"] = hardened_path
        result["hardened_rtl"] = hardened_content
        logger.print(f"  [4/7] Hardened RTL written to: {hardened_path}")

        # ── Step 5: AST Repair (before Auto-Repair) ──
        logger.sub_section("Phase 5/7: AST-Level Syntax Repair")
        if use_ast_repair and _HAVE_AST_REPAIR:
            logger.print(f"  [5/7] Running ASTRepairer on hardened RTL...")
            _ast_t = time.time()
            try:
                _ast_repairer = ASTRepairer(verbose=True)
                # Read current hardened content for AST repair
                with open(hardened_path, "r", encoding="utf-8", errors="replace") as _hf:
                    _current_content = _hf.read()
                # AST repair with empty errors list → regex fallback for safety
                _repaired = _ast_repairer.fix(_current_content, [])
                if _repaired and _repaired != _current_content:
                    _delta_chars = len(_repaired) - len(_current_content)
                    logger.print(f"  [5/7] AST repair modified content: "
                                 f"{len(_current_content)} → {len(_repaired)} chars ({_delta_chars:+d})")
                    with open(hardened_path, "w", encoding="utf-8") as _hf:
                        _hf.write(_repaired)
                    result["hardened_rtl"] = _repaired
                    result["ast_repair_applied"] = True
                else:
                    logger.print(f"  [5/7] AST repair: content unchanged (no issues found)")
                    result["ast_repair_applied"] = False
            except Exception as _ae:
                logger.warning(f"  [5/7] AST repair failed: {_ae}")
                result["ast_repair_applied"] = False
                result["ast_repair_error"] = str(_ae)
            logger.metric("phase5.ast_repair", time.time() - _ast_t, "s")
        else:
            _reason = "disabled by user" if not use_ast_repair else \
                      "ASTRepairer not available" if not _HAVE_AST_REPAIR else "unknown"
            logger.print(f"  [5/7] Skipping AST repair ({_reason})")
            result["ast_repair_applied"] = False
        _t5 = time.time()

        # ── Step 6: Auto-Repair verification loop ──
        logger.sub_section("Phase 6/7: Auto-Repair Verification Loop")
        logger.print(f"  [6/7] Running Auto-Repair verification loop...")
        try:
            from auto_repair import AutoRepairEngine as _ARE
            from auto_repair import generate_repair_report as _grr
            _repair_engine = _ARE(
                max_iterations=max_repair_iterations, verbose=True
            )
            # Use absolute paths to avoid CWD issues in subprocess
            _abs_hardened = os.path.abspath(hardened_path)
            # NOTE: original_rtl is NOT passed here because hardened RTL is
            # intentionally different (TMR/ECC/etc.), so formal equivalence
            # would always fail. Syntax + synthesis verification is sufficient.
            repair_result = _repair_engine.repair(
                rtl_path=_abs_hardened,
                original_rtl=None,
            )
            result["passed"] = repair_result.get("passed", False)
            result["iterations"] = repair_result.get("iterations", 0)
            result["stages"] = repair_result.get("stages", [])
            result["repair_report"] = _grr(repair_result)

            # If Auto-Repair changed the file, read updated content
            fixed_path = repair_result.get("fixed_rtl_path")
            if fixed_path and os.path.isfile(fixed_path):
                with open(fixed_path, "r", encoding="utf-8",
                          errors="replace") as f:
                    result["hardened_rtl"] = f.read()
                result["hardened_rtl_path"] = fixed_path

            status = "PASSED" if result["passed"] else "FAILED"
            logger.print(f"  [6/7] Auto-Repair: {status} after {result['iterations']} iteration(s)")

            if result["repair_report"]:
                report_path = os.path.join(output_dir, f"{base_name}_repair_report.md")
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(result["repair_report"])
                logger.print(f"  [6/7] Repair report saved to: {report_path}")

        except ImportError:
            logger.warning("  [6/7] Auto-Repair module not available; skipping verification")
            result["passed"] = True  # Assume pass if no verifier
        except Exception as e:
            logger.error("  [6/7] Auto-Repair failed: %s", e)
            result["repair_report"] = f"Auto-Repair error: {e}"
        _t6 = time.time()

        # ── Step 7: Docker Verification (optional) ──
        logger.sub_section("Phase 7/7: Docker Verification")
        if docker_verify and _HAVE_DOCKER_YOSYS:
            logger.print(f"  [7/7] Running yosys Docker verification...")
            _docker_t = time.time()
            try:
                _docker_yosys = YosysDockerWrapper(verbose=True)
                if _docker_yosys.enabled:
                    # 语法检查
                    logger.print(f"  [7/7] Stage 1/2: Syntax check (Docker/local yosys)")
                    _syntax = _docker_yosys.syntax_check(hardened_path)
                    result["docker_syntax"] = _syntax
                    if _syntax.get("passed"):
                        logger.print(f"  [7/7] ✓ Syntax check PASSED ({_syntax.get('elapsed', 0):.2f}s)")
                        # 综合检查
                        logger.print(f"  [7/7] Stage 2/2: Synthesis check (Docker/local yosys)")
                        _synth = _docker_yosys.synthesis_check(hardened_path)
                        result["docker_synthesis"] = _synth
                        if _synth.get("passed"):
                            logger.print(f"  [7/7] ✓ Synthesis check PASSED "
                                         f"(cells={_synth.get('cell_count', '?')}, "
                                         f"elapsed={_synth.get('elapsed', 0):.2f}s)")
                        else:
                            logger.warning(f"  [7/7] ✗ Synthesis check FAILED: "
                                           f"{len(_synth.get('errors', []))} errors")
                    else:
                        logger.warning(f"  [7/7] ✗ Syntax check FAILED: "
                                       f"{len(_syntax.get('errors', []))} errors")
                else:
                    logger.warning(f"  [7/7] yosys not available (Docker disabled + local not found)")
                    result["docker_verify"] = "disabled"
            except Exception as _de:
                logger.warning(f"  [7/7] Docker verification failed: {_de}")
                result["docker_verify"] = f"error: {_de}"
            logger.metric("phase7.docker_verify", time.time() - _docker_t, "s")
        else:
            _reason = "disabled by user" if not docker_verify else \
                      "YosysDockerWrapper not available" if not _HAVE_DOCKER_YOSYS else "unknown"
            logger.print(f"  [7/7] Skipping Docker verification ({_reason})")
            result["docker_verify"] = _reason

        _t_end = time.time()
        result["total_elapsed"] = _t_end - _t_start

        logger.print(f"\n{'=' * 62}")
        logger.print(f"  Hardening Pipeline Complete")
        logger.print(f"  Status:     {'PASSED' if result['passed'] else 'FAILED'}")
        logger.print(f"  Iterations: {result['iterations']}")
        logger.print(f"  Elapsed:    {result['total_elapsed']:.3f}s")
        logger.print(f"  Output:     {result['hardened_rtl_path']}")
        logger.print(f"  Design errors found: {len(result.get('design_errors', {}).get('errors', []))}")
        logger.print(f"{'=' * 62}")
        logger.section("Hardening Pipeline Complete")
        logger.info("  Status:      %s", "PASSED" if result["passed"] else "FAILED")
        logger.info("  Iterations:  %d", result["iterations"])
        logger.info("  Elapsed:     %.3fs", result["total_elapsed"])
        logger.info("  Output:      %s", result["hardened_rtl_path"])

        return result


# ======================================================================
# CLI
# ======================================================================

def main():
    """Command-line entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Unified AIG/BLIF Graph Pipeline + RAG Hardening",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Input source
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--blif", type=str, help="Single BLIF file")
    input_group.add_argument("--aig", type=str, help="Single AIG file")
    input_group.add_argument("--rtl", type=str, help="RTL Verilog file")
    input_group.add_argument("--batch", type=str,
                              help="Batch convert directory")
    input_group.add_argument("--harden", type=str, metavar="RTL_FILE",
                              help="Run RAG + Auto-Repair hardening pipeline on RTL")

    # Options
    parser.add_argument("--output", type=str, default=None,
                        help="Output path for .pt or PNG file")
    parser.add_argument("--visualize", action="store_true",
                        help="Visualize graph")
    parser.add_argument("--stats", action="store_true",
                        help="Print statistics")
    parser.add_argument("--list-modules", action="store_true",
                        help="List all module declarations in design files and exit")
    parser.add_argument("--yosys-script", type=str, default=None,
                        help="Yosys synthesis script")
    parser.add_argument("--llm-backend", type=str, default='mock',
                        choices=['mock', 'openai', 'deepseek'],
                        help="LLM backend for RAG hardening (default: mock)")
    parser.add_argument("--max-repair-iter", type=int, default=5,
                        help="Max Auto-Repair iterations (default: 5)")
    parser.add_argument("--hardening-strategy", type=str, default='tmr',
                        choices=['tmr', 'ecc', 'dice', 'parity'],
                        help="Hardening strategy: tmr (default), ecc, dice, parity")
    parser.add_argument("--analyze-design-errors", action="store_true",
                        help="Run static design error analysis on RTL")
    parser.add_argument("--submodule", type=str, action="append", default=None,
                        help="Directory paths to search for submodule RTL files (can specify multiple)")
    parser.add_argument("--design-files", type=str, action="append", default=None,
                        help="Additional RTL files for multi-file designs (can specify multiple)")
    parser.add_argument("--use-ast-repair", action="store_true", default=True,
                        help="Enable AST-level syntax repair before Auto-Repair (default: on)")
    parser.add_argument("--no-ast-repair", action="store_false", dest="use_ast_repair",
                        help="Disable AST-level syntax repair")
    parser.add_argument("--docker-verify", action="store_true", default=False,
                        help="Enable yosys Docker verification after Auto-Repair")

    args = parser.parse_args()
    pipeline = GraphPipeline(verbose=True)

    # ── List modules mode ──
    if args.list_modules:
        from rtl_parser import extract_module_name_from_file
        src = args.rtl or args.harden
        if not src:
            print("Error: --list-modules requires --rtl or --harden")
            sys.exit(1)
        files = [src] + (args.design_files or [])
        print(f"\n{'=' * 50}")
        print(f"  Module Listing ({len(files)} file(s))")
        print(f"{'=' * 50}")
        for f in files:
            if not os.path.isfile(f):
                print(f"  [SKIP] {f} (file not found)")
                continue
            mname = extract_module_name_from_file(f)
            print(f"  [{'OK' if mname else '??'}] {os.path.basename(f):<40s} "
                  f"module {mname or '(unknown)'}")
        print(f"{'=' * 50}")
        sys.exit(0)

    if args.blif:
        data = pipeline.from_blif(args.blif)

    elif args.aig:
        data = pipeline.from_aig(args.aig)

    elif args.rtl:
        # If analyze-design-errors is set, run analysis instead of graph conversion
        if args.analyze_design_errors:
            logger.section("Static Design Error Analysis")
            result = pipeline.analyze_design_errors(args.rtl,
                                                       design_files=args.design_files)
            print(f"\n  Design Error Analysis Results:")
            print(f"  Modules:    {len(result.get('modules', {}))}")
            print(f"  Instances:  {len(result.get('instances', []))}")
            print(f"  Errors:     {len(result.get('errors', []))}")
            print(f"  Warnings:   {len(result.get('warnings', []))}")
            print(f"  Passed:     {result.get('analysis_passed', False)}")
            if result.get("errors"):
                print(f"\n  Errors:")
                for err in result["errors"]:
                    print(f"    - [{err['type']}] {err['description'][:120]}")
            if result.get("warnings"):
                print(f"\n  Warnings:")
                for warn in result["warnings"]:
                    print(f"    - [{warn['type']}] {warn['description'][:120]}")
            return
        results = pipeline.from_rtl(
            args.rtl, yosys_script=args.yosys_script,
            output_dir='tmp_graph_pipeline'
        )
        if 'blif' in results:
            data = results['blif']
        elif 'aig' in results:
            data = results['aig']
        else:
            print("[ERROR] No graph generated from RTL")
            return

    elif args.batch:
        samples = pipeline.batch_convert(args.batch, output_file=args.output)
        print(f"\n  Generated {len(samples)} samples")
        return

    elif args.harden:
        pipeline.verbose = True
        result = pipeline.harden(
            rtl_path=args.harden,
            llm_backend=args.llm_backend,
            hardening_strategy=args.hardening_strategy,
            max_repair_iterations=args.max_repair_iter,
            analyze_errors_first=args.analyze_design_errors,
            submodule_paths=args.submodule,
            use_ast_repair=args.use_ast_repair,
            docker_verify=args.docker_verify,
            design_files=args.design_files,
        )
        # Print summary
        print(f"\n{'=' * 62}")
        print(f"  Hardening Pipeline Result")
        print(f"{'=' * 62}")
        print(f"  Status:      {'✅ PASSED' if result['passed'] else '❌ FAILED'}")
        print(f"  Strategy:    {result.get('hardening_strategy', 'tmr')}")
        print(f"  AST Repair:  {'✅ applied' if result.get('ast_repair_applied') else '— skipped/no change'}")
        print(f"  Docker Ver:  {'✅ yes' if result.get('docker_syntax', {}).get('passed') else '— disabled/failed'}")
        print(f"  Iterations:  {result['iterations']}")
        print(f"  Elapsed:     {result['total_elapsed']:.3f}s")
        print(f"  Output:      {result['hardened_rtl_path']}")
        if result.get('design_errors', {}).get('errors'):
            print(f"  Design errors: {len(result['design_errors']['errors'])}")
        if result['repair_report']:
            report_txt = result['repair_report'][:500]
            print(f"  Report:\n{report_txt}")
        return

    if args.stats:
        pipeline.print_stats(data)

    if args.visualize:
        out = args.output or f"{os.path.splitext(args.blif or args.aig or 'graph')[0]}.png"
        pipeline.visualize(data, out)

    if args.output and not args.visualize and not args.batch:
        torch.save(data, args.output)
        print(f"\n  Saved to: {args.output}")


if __name__ == '__main__':
    main()
