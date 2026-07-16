#!/usr/bin/env python3
"""aig_builder.py — AIG图构建模块。

实现从RTL到AIG图的构建流程，包括yosys集成和PyG转换。

功能:
  - yosys综合调用
  - AIGER格式解析
  - AIG→PyG Data转换
  - 图可视化
"""

import subprocess
import os
import struct
from typing import Dict, List, Optional, Tuple


class AIGNode:
    """AIG节点类。"""

    def __init__(self, node_id: int, node_type: str = 'AND'):
        """初始化节点。

        Args:
            node_id: 节点ID。
            node_type: 节点类型 ('AND', 'INPUT', 'OUTPUT', 'CONST')。
        """
        self.node_id = node_id
        self.node_type = node_type
        self.fanin0 = None
        self.fanin1 = None
        self.fanin0_inv = False
        self.fanin1_inv = False
        self.features = []

    def to_dict(self) -> Dict:
        """转换为字典。"""
        return {
            'node_id': self.node_id,
            'node_type': self.node_type,
            'fanin0': self.fanin0,
            'fanin1': self.fanin1,
            'fanin0_inv': self.fanin0_inv,
            'fanin1_inv': self.fanin1_inv,
            'features': self.features
        }


class AIGGraph:
    """AIG图类。"""

    def __init__(self):
        self.nodes = {}
        self.inputs = []
        self.outputs = []
        self.const0 = None
        self.edges = []

    def add_node(self, node_id: int, node: AIGNode):
        """添加节点。"""
        self.nodes[node_id] = node
        if node.node_type == 'INPUT':
            self.inputs.append(node_id)
        elif node.node_type == 'OUTPUT':
            self.outputs.append(node_id)
        elif node.node_type == 'CONST':
            self.const0 = node_id

    def add_edge(self, source: int, target: int, inv: bool = False):
        """添加边。"""
        self.edges.append({
            'source': source,
            'target': target,
            'inverted': inv
        })

    def get_node(self, node_id: int) -> AIGNode:
        """获取节点。"""
        return self.nodes.get(node_id)

    def to_pyg_data(self) -> Dict:
        """转换为PyG Data格式。"""
        import torch
        from torch_geometric.data import Data

        num_nodes = len(self.nodes)
        node_features = []
        edge_index = []

        node_id_map = {node_id: idx for idx, node_id in enumerate(self.nodes.keys())}

        for node_id in sorted(self.nodes.keys()):
            node = self.nodes[node_id]
            type_encoding = {
                'CONST': [1, 0, 0, 0],
                'INPUT': [0, 1, 0, 0],
                'AND': [0, 0, 1, 0],
                'OUTPUT': [0, 0, 0, 1]
            }.get(node.node_type, [0, 0, 1, 0])
            node_features.append(type_encoding + node.features)

        for edge in self.edges:
            source_idx = node_id_map.get(edge['source'])
            target_idx = node_id_map.get(edge['target'])
            if source_idx is not None and target_idx is not None:
                edge_index.append([source_idx, target_idx])

        x = torch.tensor(node_features, dtype=torch.float)
        edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()

        return Data(x=x, edge_index=edge_index)

    def to_networkx(self) -> object:
        """转换为NetworkX图。"""
        import networkx as nx

        G = nx.DiGraph()

        for node_id, node in self.nodes.items():
            G.add_node(node_id, **node.to_dict())

        for edge in self.edges:
            G.add_edge(
                edge['source'],
                edge['target'],
                inverted=edge['inverted']
            )

        return G

    def visualize(self, output_path: Optional[str] = None):
        """可视化AIG图。"""
        try:
            import networkx as nx
            import matplotlib.pyplot as plt

            G = self.to_networkx()

            pos = nx.spring_layout(G, seed=42)

            node_colors = []
            for node_id in G.nodes():
                node_type = G.nodes[node_id].get('node_type', 'AND')
                colors = {
                    'CONST': '#FF0000',
                    'INPUT': '#00FF00',
                    'AND': '#0000FF',
                    'OUTPUT': '#FFFF00'
                }
                node_colors.append(colors.get(node_type, '#0000FF'))

            plt.figure(figsize=(12, 8))
            nx.draw(
                G, pos, node_color=node_colors,
                with_labels=True, font_weight='bold',
                node_size=500, font_size=8
            )

            edge_labels = {(u, v): 'INV' if d.get('inverted') else '' for u, v, d in G.edges(data=True)}
            nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=6)

            legend_elements = [
                plt.Line2D([0], [0], marker='o', color='w', label='CONST',
                           markerfacecolor='#FF0000', markersize=10),
                plt.Line2D([0], [0], marker='o', color='w', label='INPUT',
                           markerfacecolor='#00FF00', markersize=10),
                plt.Line2D([0], [0], marker='o', color='w', label='AND',
                           markerfacecolor='#0000FF', markersize=10),
                plt.Line2D([0], [0], marker='o', color='w', label='OUTPUT',
                           markerfacecolor='#FFFF00', markersize=10),
            ]
            plt.legend(handles=legend_elements, loc='best')

            plt.title('AIG Graph Visualization')

            if output_path:
                plt.savefig(output_path, dpi=300, bbox_inches='tight')
            else:
                plt.show()

            plt.close()

        except ImportError:
            print("警告: 需要安装 networkx 和 matplotlib 进行可视化")


def parse_aiger(file_path: str) -> AIGGraph:
    """解析AIGER二进制文件。

    Args:
        file_path: AIGER文件路径。

    Returns:
        AIGGraph对象。
    """
    graph = AIGGraph()

    with open(file_path, 'rb') as f:
        header = f.readline().decode('ascii').strip()

        if not header.startswith('aag'):
            raise ValueError("不是有效的AIGER文件")

        parts = header.split()
        max_node_id = int(parts[1])
        num_inputs = int(parts[2])
        num_latches = int(parts[3])
        num_outputs = int(parts[4])
        num_ands = int(parts[5])

        const_node = AIGNode(0, 'CONST')
        graph.add_node(0, const_node)

        for i in range(1, num_inputs + 1):
            node = AIGNode(i, 'INPUT')
            graph.add_node(i, node)

        for i in range(num_inputs + 1, num_inputs + num_latches + 1):
            node = AIGNode(i, 'INPUT')
            graph.add_node(i, node)

        for i in range(num_inputs + num_latches + 1, max_node_id + 1):
            raw = f.read(4)
            if len(raw) < 4:
                break

            value = struct.unpack('<I', raw)[0]

            fanin1_raw = value & 0x3FFFFFFF
            fanin0_raw = (value >> 2) & 0x3FFFFFFF

            fanin1_id = fanin1_raw // 2
            fanin0_id = fanin0_raw // 2
            fanin1_inv = (fanin1_raw % 2) == 1
            fanin0_inv = (fanin0_raw % 2) == 1

            node = AIGNode(i, 'AND')
            node.fanin0 = fanin0_id
            node.fanin1 = fanin1_id
            node.fanin0_inv = fanin0_inv
            node.fanin1_inv = fanin1_inv
            graph.add_node(i, node)

            graph.add_edge(fanin0_id, i, fanin0_inv)
            graph.add_edge(fanin1_id, i, fanin1_inv)

        for _ in range(num_outputs):
            raw = f.read(4)
            if len(raw) < 4:
                break

            value = struct.unpack('<I', raw)[0]
            output_id = value // 2
            output_inv = (value % 2) == 1

            node = AIGNode(max_node_id + 1 + _, 'OUTPUT')
            node.fanin0 = output_id
            node.fanin0_inv = output_inv
            graph.add_node(node.node_id, node)
            graph.add_edge(output_id, node.node_id, output_inv)

    return graph


def run_yosys_synthesis(
    rtl_file: str,
    output_file: Optional[str] = None,
    yosys_path: str = 'yosys'
) -> str:
    """运行yosys综合生成AIG。

    Args:
        rtl_file: RTL文件路径。
        output_file: AIG输出文件路径（可选）。
        yosys_path: yosys可执行文件路径。

    Returns:
        AIG文件路径。
    """
    if output_file is None:
        output_file = os.path.splitext(rtl_file)[0] + '.aig'

    tcl_script = f"""
read_verilog {rtl_file}
hierarchy -check
proc; opt; fsm; opt; memory; opt;
techmap; opt;
write_aiger -ascii {output_file}
"""

    tcl_file = os.path.splitext(rtl_file)[0] + '_synth.tcl'
    with open(tcl_file, 'w') as f:
        f.write(tcl_script)

    try:
        result = subprocess.run(
            [yosys_path, '-c', tcl_file],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            print(f"yosys综合警告: {result.stderr}")

        os.remove(tcl_file)

        if os.path.exists(output_file):
            return output_file
        else:
            raise RuntimeError(f"yosys未生成AIG文件: {output_file}")

    except FileNotFoundError:
        print("警告: yosys未找到，请安装yosys或设置yosys_path")
        return ''
    except subprocess.TimeoutExpired:
        print("警告: yosys综合超时")
        return ''


def rtl_to_aig(
    rtl_file: str,
    output_file: Optional[str] = None,
    yosys_path: str = 'yosys'
) -> AIGGraph:
    """从RTL文件构建AIG图。

    Args:
        rtl_file: RTL文件路径。
        output_file: AIG输出文件路径（可选）。
        yosys_path: yosys可执行文件路径。

    Returns:
        AIGGraph对象。
    """
    aig_file = run_yosys_synthesis(rtl_file, output_file, yosys_path)

    if not aig_file or not os.path.exists(aig_file):
        print("警告: 使用模拟AIG图")
        return create_mock_aig()

    return parse_aiger(aig_file)


def create_mock_aig() -> AIGGraph:
    """创建模拟AIG图。

    Returns:
        模拟的AIGGraph对象。
    """
    graph = AIGGraph()

    const0 = AIGNode(0, 'CONST')
    const0.features = [0.0, 0.0, 0.0, 0.0]
    graph.add_node(0, const0)

    input1 = AIGNode(1, 'INPUT')
    input1.features = [1.0, 0.0, 0.0, 0.5]
    graph.add_node(1, input1)

    input2 = AIGNode(2, 'INPUT')
    input2.features = [0.0, 1.0, 0.0, 0.6]
    graph.add_node(2, input2)

    and1 = AIGNode(3, 'AND')
    and1.fanin0 = 1
    and1.fanin1 = 2
    and1.fanin0_inv = False
    and1.fanin1_inv = False
    and1.features = [0.7, 0.3, 0.5, 0.8]
    graph.add_node(3, and1)
    graph.add_edge(1, 3, False)
    graph.add_edge(2, 3, False)

    and2 = AIGNode(5, 'AND')
    and2.fanin0 = 0
    and2.fanin1 = 3
    and2.fanin0_inv = True
    and2.fanin1_inv = False
    and2.features = [0.5, 0.5, 0.5, 0.5]
    graph.add_node(5, and2)
    graph.add_edge(0, 5, True)
    graph.add_edge(3, 5, False)

    output1 = AIGNode(4, 'OUTPUT')
    output1.fanin0 = 5
    output1.fanin0_inv = False
    output1.features = [0.9, 0.1, 0.4, 0.7]
    graph.add_node(4, output1)
    graph.add_edge(5, 4, False)

    return graph


def aig_to_pyg(
    aig_graph: AIGGraph,
    feature_dim: int = 12
) -> Dict:
    """将AIG图转换为PyG Data。

    Args:
        aig_graph: AIG图。
        feature_dim: 特征维度。

    Returns:
        PyG Data字典。
    """
    data = aig_graph.to_pyg_data()

    if data.x.shape[1] < feature_dim:
        padding = torch.zeros(data.x.shape[0], feature_dim - data.x.shape[1])
        data.x = torch.cat([data.x, padding], dim=1)

    return data


def generate_aig_report(aig_graph: AIGGraph) -> str:
    """生成AIG图报告。

    Args:
        aig_graph: AIG图。

    Returns:
        报告文本。
    """
    report_lines = [
        "=" * 70,
        "AIG图分析报告",
        "=" * 70,
        ""
    ]

    report_lines.append(f"总节点数: {len(aig_graph.nodes)}")
    report_lines.append(f"输入节点数: {len(aig_graph.inputs)}")
    report_lines.append(f"输出节点数: {len(aig_graph.outputs)}")
    report_lines.append(f"边数: {len(aig_graph.edges)}")

    node_types = {}
    for node in aig_graph.nodes.values():
        node_types[node.node_type] = node_types.get(node.node_type, 0) + 1

    report_lines.append("")
    report_lines.append("节点类型分布:")
    for node_type, count in node_types.items():
        percentage = count / len(aig_graph.nodes) * 100
        report_lines.append(f"  {node_type}: {count} ({percentage:.1f}%)")

    report_lines.append("")
    report_lines.append("=" * 70)

    return '\n'.join(report_lines)