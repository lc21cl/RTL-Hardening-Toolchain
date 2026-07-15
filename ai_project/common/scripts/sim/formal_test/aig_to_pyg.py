#!/usr/bin/env python3
"""
aig_to_pyg.py — AIG 文件到 PyTorch Geometric Data 对象的独立转换模块

重用 aig_parser.AIGParser 进行 AIGER 二进制格式解析，将其 8 维节点特征
封装为 torch_geometric.data.Data 对象，供 GNN 推理/训练使用。

节点特征 (8 维):
    dim 0: is_PI      — 是否为输入端口 (1/0)
    dim 1: is_PO      — 是否为输出端口 (1/0)
    dim 2: is_AND     — 是否为 AND 门 (1/0)
    dim 3: is_Latch   — 是否为锁存器 (1/0, AIG 中通常为 0)
    dim 4: is_Const   — 是否为常量 (1/0)
    dim 5: fan_in     — 归一化扇入数 [0, 1]
    dim 6: fan_out    — 归一化扇出数 [0, 1]
    dim 7: depth      — 归一化逻辑深度 [0, 1]

边特征 (1 维):
    dim 0: inverted   — 该边是否反相 (1/0)

用法:
    from aig_to_pyg import convert_aig_to_pyg, batch_convert

    data = convert_aig_to_pyg("design.aig")
    dataset = batch_convert("aigs/", pattern="*.aig")
"""

import os
import sys
import glob
from typing import List, Optional

# ── Logger ────────────────────────────────────────────────────────────────────

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# ── 软依赖检查 ───────────────────────────────────────────────────────────────

try:
    import torch
except ImportError:
    raise ImportError(
        "PyTorch is required. Install it via: pip install torch"
    )

try:
    from torch_geometric.data import Data
except ImportError:
    raise ImportError(
        "PyTorch Geometric is required. Install it via: pip install torch_geometric"
    )

# ── AIG Parser 导入 ──────────────────────────────────────────────────────────

try:
    from aig_parser import AIGParser
except ImportError as e:
    raise ImportError(
        f"Cannot import AIGParser from aig_parser.py: {e}"
    )


# ============================================================================
# 核心转换函数
# ============================================================================

def convert_aig_to_pyg(
    aig_path: str,
    feature_dim: int = 8,
    add_design_name: bool = True,
) -> Data:
    """将 AIG 文件转换为 PyTorch Geometric Data 对象。

    Args:
        aig_path: AIGER 二进制 .aig 文件路径。
        feature_dim: 输出特征维度（默认 8）。AIGParser 原生输出 8 维，
                     指定更小的值会截断，更大的值会用零填充。
        add_design_name: 若为 True，将 design_name 属性设为文件名（不含扩展名）。

    Returns:
        torch_geometric.data.Data 对象，包含 x, edge_index, edge_attr, node_type。

    Raises:
        FileNotFoundError: AIG 文件不存在。
        RuntimeError: AIG 解析失败。
        ImportError: PyTorch/PyG 未安装。
    """
    aig_path = os.path.abspath(aig_path)
    if not os.path.isfile(aig_path):
        raise FileNotFoundError(f"AIG file not found: {aig_path}")

    parser = AIGParser()
    if not parser.parse_file(aig_path):
        raise RuntimeError(f"Failed to parse AIG file: {aig_path}")

    if feature_dim == 8:
        data = parser.to_pyg_data()
    else:
        data = parser.to_pyg_data()
        cur_dim = data.x.shape[1]
        if feature_dim < cur_dim:
            data.x = data.x[:, :feature_dim]
        elif feature_dim > cur_dim:
            pad = torch.zeros(data.num_nodes, feature_dim - cur_dim, dtype=torch.float)
            data.x = torch.cat([data.x, pad], dim=1)

    data.original_file = aig_path
    data.graph_type = "aig"

    if add_design_name:
        data.design_name = os.path.splitext(os.path.basename(aig_path))[0]

    logger.info(
        f"[AIG→PyG] {os.path.basename(aig_path)}: "
        f"{data.num_nodes} nodes, {data.edge_index.shape[1]} edges, "
        f"{data.x.shape[1]}-dim features"
    )
    return data


# ============================================================================
# 批量转换
# ============================================================================

def batch_convert(
    aig_dir: str,
    pattern: str = "*.aig",
    feature_dim: int = 8,
) -> List[Data]:
    """批量转换指定目录下的所有 AIG 文件。

    Args:
        aig_dir: 包含 .aig 文件的目录路径。
        pattern: 文件匹配模式（默认 ``*.aig``）。
        feature_dim: 输出特征维度（见 :func:`convert_aig_to_pyg`）。

    Returns:
        转换成功的 PyG Data 对象列表。跳过解析失败的文件并记录警告。
    """
    aig_dir = os.path.abspath(aig_dir)
    if not os.path.isdir(aig_dir):
        raise NotADirectoryError(f"Directory not found: {aig_dir}")

    files = sorted(glob.glob(os.path.join(aig_dir, pattern)))
    if not files:
        logger.warning(f"[Batch] No files matching '{pattern}' in {aig_dir}")
        return []

    results: List[Data] = []
    logger.info(f"[Batch] Converting {len(files)} AIG files from {aig_dir}")

    for i, fpath in enumerate(files):
        try:
            data = convert_aig_to_pyg(fpath, feature_dim=feature_dim)
            results.append(data)
            logger.info(f"  [{i+1}/{len(files)}] {os.path.basename(fpath)} OK")
        except Exception as e:
            logger.warning(f"  [{i+1}/{len(files)}] {os.path.basename(fpath)} FAILED: {e}")

    logger.info(f"[Batch] Done: {len(results)}/{len(files)} converted successfully")
    return results


# ============================================================================
# 带 BLIF 回退的转换
# ============================================================================

def convert_with_blif_fallback(
    aig_path: str,
    blif_path: Optional[str] = None,
) -> Data:
    """优先使用 AIG 转换，失败时回退到 BLIF 转换。

    当 ``blif_path`` 未指定时，自动在 AIG 同目录下查找同名 .blif 文件。
    该函数仅在 ``blif_to_pyg`` 模块可用时启用 BLIF 回退。

    Args:
        aig_path: AIGER 二进制 .aig 文件路径。
        blif_path: 可选的 BLIF 文件路径。若为 None，自动推断。

    Returns:
        PyG Data 对象。成功转换的数据中 ``graph_type`` 标注为 ``'aig'``
        或 ``'blif'``。

    Raises:
        FileNotFoundError: AIG 文件和 BLIF 回退均不可用。
        RuntimeError: 两种格式均转换失败。
    """
    # 尝试 AIG
    try:
        data = convert_aig_to_pyg(aig_path)
        logger.info(f"[Fallback] AIG conversion succeeded: {aig_path}")
        return data
    except Exception as aig_err:
        logger.warning(f"[Fallback] AIG failed: {aig_err}")

    # 自动推断 BLIF 路径
    if blif_path is None:
        base = os.path.splitext(aig_path)[0]
        blif_path = base + ".blif"

    # 尝试 BLIF 回退
    try:
        from blif_to_pyg import BlifToAIG  # type: ignore[import-untyped]
        converter = BlifToAIG(blif_path)
        data = converter.build_pyg_data()
        data.original_file = blif_path
        data.graph_type = "blif"
        data.design_name = os.path.splitext(os.path.basename(blif_path))[0]

        # 若需要 8 维，截取 BLIF 的前 8 维
        if data.x.shape[1] > 8:
            data.x = data.x[:, :8]

        logger.info(f"[Fallback] BLIF fallback succeeded: {blif_path}")
        return data
    except Exception as blif_err:
        raise RuntimeError(
            f"AIG conversion failed ('{aig_err}') "
            f"and BLIF fallback also failed ('{blif_err}')"
        )


# ============================================================================
# CLI
# ============================================================================

def main() -> None:
    """命令行入口。

    支持:
        python aig_to_pyg.py --aig design.aig --output data.pt
        python aig_to_pyg.py --batch aigs/ --output dataset.pt
        python aig_to_pyg.py --aig design.aig --blif design.blif --output data.pt
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert AIG (And-Inverter Graph) files to PyTorch Geometric Data objects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python aig_to_pyg.py --aig design.aig --output data.pt\n"
            "  python aig_to_pyg.py --batch aigs/ --output dataset.pt\n"
            "  python aig_to_pyg.py --aig design.aig --blif design.blif --output data.pt\n"
        ),
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--aig", type=str, help="Path to a single .aig file")
    input_group.add_argument("--batch", type=str, help="Directory containing .aig files for batch conversion")

    parser.add_argument("--blif", type=str, default=None,
                        help="BLIF fallback path (used with --aig)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output .pt file path")
    parser.add_argument("--feature-dim", type=int, default=8,
                        help="Feature dimension (default: 8)")
    parser.add_argument("--summary", action="store_true",
                        help="Print graph summary after conversion")

    args = parser.parse_args()

    try:
        if args.batch:
            dataset = batch_convert(args.batch, feature_dim=args.feature_dim)
            logger.info(f"Converted {len(dataset)} graphs")

            if args.output and dataset:
                os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
                torch.save(dataset, args.output)
                logger.info(f"Saved {len(dataset)} graphs to {args.output}")

            if args.summary:
                for i, d in enumerate(dataset):
                    name = getattr(d, "design_name", f"graph_{i}")
                    logger.print(f"  [{i}] {name}: {d.num_nodes} nodes, "
                                 f"{d.edge_index.shape[1]} edges, {d.x.shape[1]}-dim")
        else:
            data = convert_with_blif_fallback(args.aig, args.blif) if args.blif \
                   else convert_aig_to_pyg(args.aig, feature_dim=args.feature_dim)

            logger.info(
                f"Graph: {data.num_nodes} nodes, "
                f"{data.edge_index.shape[1]} edges, "
                f"{data.x.shape[1]}-dim features"
            )

            if args.output:
                os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
                torch.save(data, args.output)
                logger.info(f"Saved graph to {args.output}")

            if args.summary:
                logger.print(f"\n{'=' * 48}")
                logger.print(f"  Design:   {getattr(data, 'design_name', 'unknown')}")
                logger.print(f"  Type:     {getattr(data, 'graph_type', 'aig')}")
                logger.print(f"  Nodes:    {data.num_nodes}")
                logger.print(f"  Edges:    {data.edge_index.shape[1]}")
                logger.print(f"  Features: {data.x.shape[1]}-dim")
                logger.print(f"{'=' * 48}")

    except Exception as e:
        logger.error(f"Conversion failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
