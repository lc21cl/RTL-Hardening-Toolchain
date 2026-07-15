#!/usr/bin/env python3
"""
aig_visualizer.py — AIG (And-Inverter Graph) 可视化模块

提供 AIG 图结构、特征分布、度分布、深度分布等可视化功能。

依赖:
  - matplotlib, networkx (必需)
  - PyTorch Geometric (可选, 用于特征分布图)

用法:
  python aig_visualizer.py --aig input.aig
  python aig_visualizer.py --aig input.aig --mode graph --max-nodes 50
  python aig_visualizer.py --aig input.aig --mode report -o ./my_report
"""

import os
import sys
import argparse
from typing import Optional, Union, Tuple
from collections import Counter

# ── 尝试导入绘图库 ──────────────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    _HAVE_MPL = True
except ImportError:
    _HAVE_MPL = False

try:
    import networkx as nx
    _HAVE_NX = True
except ImportError:
    _HAVE_NX = False

# ── 本地导入 ────────────────────────────────────────────────────────
try:
    from aig_parser import AIGParser, _HAVE_PYG as _AIG_HAVE_PYG
except ImportError:
    AIGParser = None
    _AIG_HAVE_PYG = False

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger('aig_visualizer')

# ── 常量 ────────────────────────────────────────────────────────────
NODE_COLORS = {
    'PI': '#2ecc71', 'PO': '#e74c3c', 'AND': '#3498db',
    'CONST0': '#95a5a6', 'LATCH': '#f39c12',
}
FEATURE_NAMES = [
    'Is PI', 'Is PO', 'Is AND', 'Is Latch',
    'Is Const0', 'Fan-in (norm)', 'Fan-out (norm)', 'Depth (norm)',
]


def _check_deps(need_pyg: bool = False) -> None:
    """检查所需依赖是否可用, 不可用时抛出 ImportError"""
    if not _HAVE_MPL:
        raise ImportError("需要安装 matplotlib: pip install matplotlib")
    if not _HAVE_NX:
        raise ImportError("需要安装 networkx: pip install networkx")
    if AIGParser is None:
        raise ImportError("需要 aig_parser.py (位于同目录)")
    if need_pyg and not _AIG_HAVE_PYG:
        raise ImportError("需要 PyTorch Geometric: pip install torch_geometric")


def _parse_aig(aig_path: str) -> AIGParser:
    """解析 .aig 文件, 返回 AIGParser 实例"""
    parser = AIGParser()
    if not parser.parse_file(aig_path):
        raise ValueError(f"AIG 文件解析失败: {aig_path}")
    return parser


def _resolve_output(output_path: Optional[str], default_name: str) -> str:
    """确定输出路径, 默认为 data/figures/<default_name>"""
    if output_path:
        return output_path
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'data', 'figures')
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, default_name)


# ── 绘图函数 ────────────────────────────────────────────────────────

def plot_aig_graph(aig_path: str,
                   output_path: Optional[str] = None,
                   max_nodes: int = 100,
                   figsize: Tuple[int, int] = (16, 12)) -> Optional[str]:
    """可视化 AIG 图结构.

    PI 节点绿色, PO 红色, AND 蓝色. 反相边带橙色小圆圈气泡.
    标题显示节点/边数统计.

    Args:
        aig_path: .aig 文件路径
        output_path: 输出图像路径, 默认 data/figures/aig_graph.png
        max_nodes: 最大显示节点数
        figsize: 图像尺寸 (宽, 高)

    Returns:
        输出路径; 失败返回 None
    """
    _check_deps()
    logger.info(f"可视化 AIG 图: {aig_path}")

    try:
        parser = _parse_aig(aig_path)
    except Exception as e:
        logger.error(f"解析 AIG 失败: {e}")
        return None

    G = parser.to_networkx()
    total_nodes = G.number_of_nodes()
    total_edges = G.number_of_edges()
    logger.info(f"图统计: {total_nodes} 节点, {total_edges} 边")

    if total_nodes > max_nodes:
        logger.warning(f"节点数 ({total_nodes}) 超过限制 ({max_nodes}), 截取中")
        nodes = sorted(G.nodes())[:max_nodes]
        G = G.subgraph(nodes).copy()

    pos = nx.spring_layout(G, k=3.0, iterations=50, seed=42)
    node_groups: dict = {}
    for nid in G.nodes():
        t = G.nodes[nid].get('type', 'AND')
        node_groups.setdefault(t, []).append(nid)

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor('white')

    # 区分反相 / 非反相边
    inv_edges, normal_edges = [], []
    for u, v, d in G.edges(data=True):
        (inv_edges if d.get('inverted', False) else normal_edges).append((u, v))

    if normal_edges:
        nx.draw_networkx_edges(G, pos, edgelist=normal_edges,
                               arrows=True, arrowsize=12,
                               edge_color='gray', alpha=0.5,
                               connectionstyle='arc3,rad=0.05', ax=ax)
    if inv_edges:
        nx.draw_networkx_edges(G, pos, edgelist=inv_edges,
                               arrows=True, arrowsize=12,
                               edge_color='#e67e22', alpha=0.7,
                               connectionstyle='arc3,rad=0.05', ax=ax)
        for u, v in inv_edges:
            bx = pos[u][0] * 0.2 + pos[v][0] * 0.8
            by = pos[u][1] * 0.2 + pos[v][1] * 0.8
            ax.add_patch(plt.Circle((bx, by), 0.035,
                                    facecolor='white', edgecolor='#e67e22',
                                    linewidth=1.5, zorder=5))

    for ntype, nlist in node_groups.items():
        color = NODE_COLORS.get(ntype, '#95a5a6')
        nx.draw_networkx_nodes(G, pos, nodelist=nlist,
                               node_color=color, node_size=80,
                               edgecolors='white', linewidths=0.5, ax=ax)

    patches = [mpatches.Patch(color=NODE_COLORS.get(t, '#95a5a6'), label=t)
               for t in ['PI', 'PO', 'AND', 'CONST0'] if t in node_groups]
    patches.append(mpatches.Patch(color='#e67e22', label='Inverted edge'))
    ax.legend(handles=patches, loc='upper right', fontsize=10, framealpha=0.9)
    ax.set_title(f'AIG Graph — {total_nodes} nodes, {total_edges} edges\n'
                 f'(showing {G.number_of_nodes()} nodes)',
                 fontsize=14, fontweight='bold')
    ax.axis('off')

    out = _resolve_output(output_path, 'aig_graph.png')
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info(f"图保存至: {out}")
    return out


def plot_feature_distribution(aig_data: Union[str, 'Data'],
                              output_path: Optional[str] = None
                              ) -> Optional[str]:
    """绘制 8 维节点特征分布直方图 (2×4 子图).

    Args:
        aig_data: .aig 文件路径 或 PyG Data 对象
        output_path: 输出路径, 默认 data/figures/feature_distribution.png

    Returns:
        输出路径; 失败返回 None
    """
    _check_deps(need_pyg=True)
    logger.info("绘制特征分布图")

    # 获取 PyG Data
    if isinstance(aig_data, str):
        try:
            data = _parse_aig(aig_data).to_pyg_data()
        except Exception as e:
            logger.error(f"生成 PyG Data 失败: {e}")
            return None
    else:
        data = aig_data

    if not hasattr(data, 'x') or data.x is None:
        logger.error("Data 对象无 x 属性")
        return None

    x = data.x.numpy() if hasattr(data.x, 'numpy') else data.x
    nf = min(x.shape[1], 8)

    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    axes = axes.flatten()

    for i in range(nf):
        ax = axes[i]
        ax.hist(x[:, i], bins=50, color='#3498db', edgecolor='white', alpha=0.8)
        ax.set_title(FEATURE_NAMES[i], fontsize=11, fontweight='bold')
        ax.set_xlabel('Value')
        ax.set_ylabel('Count')
        ax.grid(True, alpha=0.3)

    for i in range(nf, 8):
        axes[i].set_visible(False)

    fig.suptitle('Node Feature Distribution (8-dim)',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()

    out = _resolve_output(output_path, 'feature_distribution.png')
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info(f"特征分布图保存至: {out}")
    return out


def plot_degree_distribution(aig_path: str,
                              output_path: Optional[str] = None
                              ) -> Optional[str]:
    """绘制入度/出度分布的 log-log 散点图.

    Args:
        aig_path: .aig 文件路径
        output_path: 输出路径, 默认 data/figures/degree_distribution.png

    Returns:
        输出路径; 失败返回 None
    """
    _check_deps()
    logger.info(f"绘制度分布: {aig_path}")

    try:
        parser = _parse_aig(aig_path)
    except Exception as e:
        logger.error(f"解析 AIG 失败: {e}")
        return None

    in_deg, out_deg = [], []
    for nid, node in parser.nodes.items():
        in_deg.append(2 if node.type == 'AND' else (1 if node.type == 'PO' else 0))
        out_deg.append(len(node.fanout))

    in_cnt = Counter(in_deg)
    out_cnt = Counter(out_deg)
    total_n = len(in_deg)

    fig, ax = plt.subplots(figsize=(10, 7))

    for vals, cnt, color, label in [
        (in_deg, in_cnt, '#3498db', 'In-degree'),
        (out_deg, out_cnt, '#e74c3c', 'Out-degree'),
    ]:
        xs = [k for k in sorted(cnt.keys()) if k > 0]
        ys = [cnt[k] for k in xs]
        if xs:
            ax.scatter(xs, ys, c=color, s=40, alpha=0.8,
                       edgecolors='white', linewidth=0.5, zorder=3,
                       label=f'{label} (avg={sum(vals)/total_n:.2f})')

    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel('Degree (log)', fontsize=12)
    ax.set_ylabel('Count (log)', fontsize=12)
    ax.set_title('AIG Degree Distribution (log-log)', fontsize=14,
                 fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3, which='both')

    out = _resolve_output(output_path, 'degree_distribution.png')
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info(f"度分布图保存至: {out}")
    return out


def plot_depth_histogram(aig_path: str,
                          output_path: Optional[str] = None
                          ) -> Optional[str]:
    """绘制逻辑深度分布直方图, 标注最大/平均深度.

    Args:
        aig_path: .aig 文件路径
        output_path: 输出路径, 默认 data/figures/depth_histogram.png

    Returns:
        输出路径; 失败返回 None
    """
    _check_deps()
    logger.info(f"绘制深度分布: {aig_path}")

    try:
        parser = _parse_aig(aig_path)
    except Exception as e:
        logger.error(f"解析 AIG 失败: {e}")
        return None

    node_ids = sorted(parser.nodes.keys())
    depths = parser._compute_depth(node_ids)

    if not depths:
        logger.warning("深度列表为空")
        return None

    max_d, avg_d = max(depths), sum(depths) / len(depths)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(depths, bins=min(50, max_d + 1), color='#2ecc71',
            edgecolor='white', alpha=0.8)
    ax.axvline(max_d, color='#e74c3c', linestyle='--', linewidth=2,
               label=f'Max depth = {max_d}')
    ax.axvline(avg_d, color='#f39c12', linestyle='--', linewidth=2,
               label=f'Avg depth = {avg_d:.2f}')
    ax.set_xlabel('Logic Depth', fontsize=12)
    ax.set_ylabel('Node Count', fontsize=12)
    ax.set_title('AIG Logic Depth Distribution', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)

    out = _resolve_output(output_path, 'depth_histogram.png')
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info(f"深度分布图保存至: {out}")
    return out


# ── 报告生成 ────────────────────────────────────────────────────────

def generate_report(aig_path: str,
                     output_dir: str = 'aig_report') -> Optional[str]:
    """生成完整 AIG 分析报告 (文本统计 + 四张图表).

    报告包含:
      - 图统计 (节点/边/PI/PO/AND 计数)
      - 度统计 (平均入度/出度)
      - 深度统计 (最大/平均/中位数深度)
      - 全部四张可视化图表

    Args:
        aig_path: .aig 文件路径
        output_dir: 报告输出目录

    Returns:
        输出目录绝对路径; 失败返回 None
    """
    _check_deps()
    logger.info(f"生成 AIG 报告: {aig_path} → {output_dir}")
    os.makedirs(output_dir, exist_ok=True)

    try:
        parser = _parse_aig(aig_path)
    except Exception as e:
        logger.error(f"解析 AIG 失败: {e}")
        return None

    # ── 统计量 ──
    node_ids = sorted(parser.nodes.keys())
    depths = parser._compute_depth(node_ids)
    total = len(parser.nodes)
    pi_n = sum(1 for n in parser.nodes.values() if n.type == 'PI')
    po_n = sum(1 for n in parser.nodes.values() if n.type == 'PO')
    and_n = sum(1 for n in parser.nodes.values() if n.type == 'AND')
    const_n = sum(1 for n in parser.nodes.values() if n.type == 'CONST0')

    in_deg = []
    out_deg = []
    for nid, node in parser.nodes.items():
        in_deg.append(2 if node.type == 'AND' else (1 if node.type == 'PO' else 0))
        out_deg.append(len(node.fanout))

    avg_in = sum(in_deg) / total if total else 0
    avg_out = sum(out_deg) / total if total else 0
    max_d = max(depths) if depths else 0
    avg_d = sum(depths) / len(depths) if depths else 0
    med_d = sorted(depths)[len(depths) // 2] if depths else 0

    # ── 文本报告 ──
    lines = [
        "=" * 56,
        "  AIG Analysis Report",
        "=" * 56,
        f"  Source:    {os.path.abspath(aig_path)}",
        "",
        "  -- Graph Statistics --",
        f"  Total nodes:   {total}",
        f"  Total edges:   {sum(in_deg)}",
        f"  PI count:      {pi_n}",
        f"  PO count:      {po_n}",
        f"  AND gates:     {and_n}",
        f"  Constants:     {const_n}",
        "",
        "  -- Degree Statistics --",
        f"  Avg in-degree:   {avg_in:.3f}",
        f"  Avg out-degree:  {avg_out:.3f}",
        "",
        "  -- Depth Statistics --",
        f"  Max depth:       {max_d}",
        f"  Avg depth:       {avg_d:.3f}",
        f"  Median depth:    {med_d}",
        "",
        "  -- Generated Plots --",
    ]
    report = "\n".join(lines)

    # ── 生成图表 ──
    plots = {
        'aig_graph': (plot_aig_graph, [aig_path]),
        'feature_distribution': (plot_feature_distribution, [aig_path]),
        'degree_distribution': (plot_degree_distribution, [aig_path]),
        'depth_histogram': (plot_depth_histogram, [aig_path]),
    }

    plot_paths = {}
    for name, (func, args) in plots.items():
        try:
            out = os.path.join(output_dir, f'{name}.png')
            result = func(*args, output_path=out)
            plot_paths[name] = result
            lines.append(f"  {'✓' if result else '✗'}  {name}.png")
        except Exception as e:
            logger.warning(f"生成 {name} 失败: {e}")
            plot_paths[name] = None
            lines.append(f"  ✗  {name}.png  ({e})")

    lines.extend(["", "=" * 56])
    report = "\n".join(lines)

    rpt_path = os.path.join(output_dir, 'report.txt')
    with open(rpt_path, 'w') as f:
        f.write(report + "\n")
    logger.info(f"报告文本保存至: {rpt_path}")

    logger.print('\n' + report)
    abs_dir = os.path.abspath(output_dir)
    logger.section(f'报告生成完成: {abs_dir}')
    return abs_dir


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="AIG (And-Inverter Graph) 可视化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python aig_visualizer.py --aig input.aig
  python aig_visualizer.py --aig input.aig --mode graph --max-nodes 50
  python aig_visualizer.py --aig input.aig --mode degree -o degree.png
  python aig_visualizer.py --aig input.aig --mode report -o ./my_report
""")
    ap.add_argument('--aig', required=True, help='输入 .aig 文件路径')
    ap.add_argument('--output', '-o', default=None,
                    help='输出路径 (文件或目录, 取决于模式)')
    ap.add_argument('--mode', '-m', default='all',
                    choices=['graph', 'features', 'degree', 'depth',
                             'report', 'all'],
                    help='绘图模式 (默认: all)')
    ap.add_argument('--max-nodes', type=int, default=100,
                    help='图结构最大节点数 (默认: 100)')
    ap.add_argument('--figsize', type=int, nargs=2, default=[16, 12],
                    metavar=('W', 'H'), help='图像尺寸 (默认: 16 12)')
    args = ap.parse_args()

    if not os.path.isfile(args.aig):
        logger.error(f"文件不存在: {args.aig}")
        sys.exit(1)

    fs = tuple(args.figsize)

    try:
        if args.mode == 'graph':
            plot_aig_graph(args.aig, args.output, args.max_nodes, fs)
        elif args.mode == 'features':
            plot_feature_distribution(args.aig, args.output)
        elif args.mode == 'degree':
            plot_degree_distribution(args.aig, args.output)
        elif args.mode == 'depth':
            plot_depth_histogram(args.aig, args.output)
        elif args.mode == 'report':
            generate_report(args.aig, args.output or 'aig_report')
        elif args.mode == 'all':
            base = args.output or os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'data', 'figures')
            os.makedirs(base, exist_ok=True)
            plot_aig_graph(args.aig, os.path.join(base, 'aig_graph.png'),
                           args.max_nodes, fs)
            plot_feature_distribution(
                args.aig, os.path.join(base, 'feature_distribution.png'))
            plot_degree_distribution(
                args.aig, os.path.join(base, 'degree_distribution.png'))
            plot_depth_histogram(args.aig,
                                 os.path.join(base, 'depth_histogram.png'))
            logger.section('全部图表生成完成')
            logger.print(f"  输出目录: {os.path.abspath(base)}")
    except ImportError as e:
        logger.error(f"依赖缺失: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
