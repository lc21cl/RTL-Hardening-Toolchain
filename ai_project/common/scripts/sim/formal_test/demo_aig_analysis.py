#!/usr/bin/env python3
"""
demo_aig_analysis.py — AIG 解析分析示例

解析 synth_output.aig 并输出:
  1. AIG 统计信息
  2. Top 10 高扇出节点 (AND 门)
  3. Top 5 逻辑深度
  4. 扇入/扇出分布统计
"""

import sys
import os

# 确保可以导入 aig_parser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aig_parser import AIGParser


def analyze_aig(aig_path: str):
    """解析并分析 AIG 文件"""
    parser = AIGParser()
    if not parser.parse_file(aig_path):
        print(f"[错误] AIG 解析失败: {aig_path}", file=sys.stderr)
        return

    # 打印基本统计
    parser.print_stats()

    # ========== Top 10 高扇出 AND 节点 ==========
    and_nodes = [
        (nid, n) for nid, n in parser.nodes.items()
        if n.type == 'AND'
    ]

    by_fanout = sorted(
        and_nodes, key=lambda x: len(x[1].fanout), reverse=True
    )[:10]

    print()
    print("=" * 64)
    print("  Top 10 高扇出 AND 节点 (高扇入 = 被更多下游引用)")
    print("=" * 64)
    print(f"  {'排名':>4s}  {'变量#':>6s}  {'扇出':>6s}  "
          f"{'扇入0':>6s}  {'扇入1':>6s}  {'反相':>8s}  {'类型':>8s}")
    print("  " + "-" * 52)
    for rank, (nid, node) in enumerate(by_fanout, 1):
        inv_str = ""
        if node.inv0:
            inv_str += "0~"
        if node.inv1:
            inv_str += "1~"
        inv_str = inv_str if inv_str else "-"

        # 判断扇入类型
        fi0_type = parser.nodes[node.fanin0].type if node.fanin0 in parser.nodes else "?"
        fi1_type = parser.nodes[node.fanin1].type if node.fanin1 in parser.nodes else "?"

        print(f"  {rank:>4d}  {nid:>6d}  {len(node.fanout):>6d}  "
              f"{node.fanin0:>6d}  {node.fanin1:>6d}  {inv_str:>8s}  "
              f"{fi0_type}->{fi1_type}")

    # ========== Top 5 逻辑深度 ==========
    node_ids = sorted(parser.nodes.keys())
    depth = parser._compute_depth(node_ids)
    depth_pairs = sorted(
        zip(node_ids, depth), key=lambda x: -x[1]
    )[:5]

    print()
    print("=" * 64)
    print("  Top 5 关键路径 (逻辑深度)")
    print("=" * 64)
    print(f"  {'排名':>4s}  {'节点ID':>6s}  {'深度':>6s}  {'类型':>8s}")
    print("  " + "-" * 30)
    for rank, (nid, d) in enumerate(depth_pairs, 1):
        nt = parser.nodes[nid].type
        print(f"  {rank:>4d}  {nid:>6d}  {d:>6d}  {nt:>8s}")

    # ========== 扇入/扇出分布 ==========
    fanouts = [len(n.fanout) for n in parser.nodes.values()]

    print()
    print("=" * 64)
    print("  扇出分布统计")
    print("=" * 64)
    if fanouts:
        print(f"  节点总数:      {len(parser.nodes)}")
        print(f"  最大扇出:      {max(fanouts)}")
        print(f"  平均扇出:      {sum(fanouts) / len(fanouts):.2f}")
        print(f"  扇出 >= 3:     {sum(1 for f in fanouts if f >= 3)} 个节点")
        print(f"  扇出 >= 5:     {sum(1 for f in fanouts if f >= 5)} 个节点")
        print(f"  扇出 = 0:      {sum(1 for f in fanouts if f == 0)} 个节点 (PI/PO/孤立)")

    # ========== 脆弱性评估 ==========
    print()
    print("=" * 64)
    print("  脆弱性评估 (基于 GraphSAGE 的特征提取)")
    print("=" * 64)
    high_risk = [
        (nid, n, len(n.fanout))
        for nid, n in by_fanout
        if len(n.fanout) >= 3
    ]
    if high_risk:
        print(f"  高风险节点 (扇出 >= 3):")
        for nid, n, fo in high_risk[:10]:
            print(f"    - 变量 #{nid}: 扇出={fo}, "
                  f"扇入=({n.fanin0},{n.fanin1})")

    print()
    print(f"  [提示] 这些高扇出节点是 GraphSAGE 脆弱性预测的")
    print(f"         重点候选对象 — 扇出越大, 单点故障影响越广")


if __name__ == "__main__":
    default_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__),
                     "..", "..", "test_mock_data", "synth_output.aig")
    )
    alt_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__),
                     "..", "..", "test_mock_data", "output.aig")
    )
    aig_path = sys.argv[1] if len(sys.argv) > 1 else default_path
    
    if not os.path.isfile(aig_path) and os.path.isfile(alt_path):
        aig_path = alt_path

    if not os.path.isfile(aig_path):
        print(f"[错误] AIG 文件不存在: {aig_path}")
        print(f"请先运行: python gen_mock_aig.py")
        sys.exit(1)

    analyze_aig(aig_path)
