"""
aig_parser.py — AIGER 二进制格式解析器

AIGER 二进制格式规范:
  Header:  'aig' M I L O A
    M = 最大变量索引
    I = 输入数量 (PI)
    L = 锁存器数量 (通常为 0)
    O = 输出数量 (PO)
    A = AND 门数量

  变量编码:
    - 变量 v (v >= 2) 由 AND 门 v 定义
    - 字面量 lit = (v << 1) | inv_flag
    - 输入 (PI): 变量 1..I

  字面量 Delta 编码 (AND 门):
    - lhs = 2 * (i + 1)  (i = AND 门序号, 从 0 开始)
    - rhs0, rhs1 使用 Delta 编码
"""

import struct
import sys
import os
import subprocess
from typing import List, Tuple, Dict, Optional, Sequence

# 尝试导入 PyTorch Geometric (可选)
try:
    import torch
    from torch_geometric.data import Data
    _HAVE_PYG = True
except ImportError:
    _HAVE_PYG = False

try:
    import networkx as nx
    _HAVE_NETWORKX = True
except ImportError:
    _HAVE_NETWORKX = False


class AIGNode:
    """AIG 节点"""

    def __init__(self, node_id: int, node_type: str,
                 fanin0: int = 0, fanin1: int = 0):
        self.id = node_id
        self.type = node_type  # 'PI', 'PO', 'AND', 'LIT', 'CONST0'
        self.fanin0 = fanin0    # 扇入 0 (字面量)
        self.fanin1 = fanin1    # 扇入 1 (字面量)
        self.inv0 = False       # fanin0 是否反相
        self.inv1 = False       # fanin1 是否反相
        self.fanout: List[int] = []  # 扇出列表 (node_id 列表)
        self.name = ""          # 信号名 (PI/PO 适用)

    def __repr__(self) -> str:
        inv0_str = "~" if self.inv0 else ""
        inv1_str = "~" if self.inv1 else ""
        return (f"AIGNode(id={self.id}, type={self.type}, "
                f"fanin=({inv0_str}{self.fanin0},{inv1_str}{self.fanin1}))")


class AIGParser:
    """AIGER 二进制格式解析器"""

    # ------------------------------------------------------------------
    # 字面量工具函数
    # ------------------------------------------------------------------
    @staticmethod
    def lit_to_var(lit: int) -> int:
        """字面量 → 变量编号"""
        return lit >> 1

    @staticmethod
    def lit_is_inverted(lit: int) -> bool:
        """检查字面量是否反相"""
        return bool(lit & 1)

    @staticmethod
    def var_to_lit(var: int, inverted: bool = False) -> int:
        """变量编号 → 字面量"""
        return (var << 1) | (1 if inverted else 0)

    @staticmethod
    def _decode_varint(data: bytes, offset: int) -> Tuple[int, int]:
        """解码 AIGER 变长无符号整数 (小端序, 每字节低 7 位为数据, MSB 为延续标志)

        Args:
            data: 二进制数据
            offset: 当前读取偏移

        Returns:
            (解码后的值, 新的偏移)
        """
        value = 0
        shift = 0
        pos = offset
        while pos < len(data):
            byte = data[pos]
            pos += 1
            value |= (byte & 0x7f) << shift
            shift += 7
            if (byte & 0x80) == 0:
                break
        return value, pos

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def __init__(self):
        self.nodes: Dict[int, AIGNode] = {}
        self.max_var: int = 0
        self.num_inputs: int = 0
        self.num_latches: int = 0
        self.num_outputs: int = 0
        self.num_ands: int = 0
        self.pi_names: List[str] = []
        self.po_names: List[str] = []
        self.po_lits: List[int] = []   # PO 字面量
        self.name_map: Dict[str, int] = {}  # 信号名 → 字面量

        self.parse_success = False
        self._debug = False  # 调试标志, 外部可开启

    # ------------------------------------------------------------------
    # 文件解析入口
    # ------------------------------------------------------------------
    def parse_file(self, aig_path: str) -> bool:
        """解析 .aig 文件

        Args:
            aig_path: AIGER 二进制文件路径

        Returns:
            解析是否成功
        """
        if not os.path.isfile(aig_path):
            print(f"错误: 文件不存在 — {aig_path}", file=sys.stderr)
            return False

        with open(aig_path, 'rb') as f:
            raw = f.read()

        # --- 解析 header ---
        # header 格式: "aig M I L O A\n" (ASCII, 空格分隔, 换行结束)
        header_end = raw.find(b'\n')
        if header_end == -1:
            print("错误: 无法找到 header 终止符", file=sys.stderr)
            return False

        header_line = raw[:header_end].decode('ascii').strip()
        if not self.parse_header(header_line):
            return False

        # --- 解析 body ---
        body_start = header_end + 1
        return self.parse_body(raw, body_start)

    def parse_header(self, header: str) -> bool:
        """解析 AIGER header: 'aig M I L O A'

        Args:
            header: header 字符串

        Returns:
            解析是否成功
        """
        parts = header.split()
        if len(parts) != 6 or parts[0] != 'aig':
            print(f"错误: header 格式无效 — '{header}'", file=sys.stderr)
            return False

        try:
            self.max_var = int(parts[1])
            self.num_inputs = int(parts[2])
            self.num_latches = int(parts[3])
            self.num_outputs = int(parts[4])
            self.num_ands = int(parts[5])
        except ValueError as e:
            print(f"错误: header 数字解析失败 — {e}", file=sys.stderr)
            return False

        if self._debug:
            print(f"[解析] M={self.max_var}, I={self.num_inputs}, "
                  f"L={self.num_latches}, O={self.num_outputs}, A={self.num_ands}")

        return True

    def parse_body(self, data: bytes, offset: int) -> bool:
        """解析 AIGER body (AND gates + outputs)

        Args:
            data: 完整二进制数据
            offset: body 起始偏移

        Returns:
            解析是否成功
        """
        pos = offset

        # --- 创建常量 0 (Const0) 节点 ---
        # AIGER 中常量 0 用字面量 0 表示 (var=0, inv=0), 特殊处理
        const0 = AIGNode(node_id=0, node_type='CONST0')
        self.nodes[0] = const0

        # --- 创建 PI 节点 (变量 1 ~ I) ---
        for pi_idx in range(1, self.num_inputs + 1):
            pi_node = AIGNode(node_id=pi_idx, node_type='PI')
            pi_node.name = f"pi_{pi_idx}"
            self.nodes[pi_idx] = pi_node
            self.pi_names.append(pi_node.name)

        # --- 解析 AND 门 ---
        # 第 i 个 AND 门 (i 从 0 开始):
        #   - 实际变量编号: var = I + 1 + i  (I = num_inputs)
        #   - 输出字面量:   lit = 2 * (I + 1 + i)
        #   - Delta 编码参考: S_i = 2 * (I + 1 + i)
        #   - rhs0_lit = S_i - delta0,  rhs1_lit = rhs0_lit - delta1
        for i in range(self.num_ands):
            and_var = self.num_inputs + 1 + i          # AND 门输出变量编号
            S_i     = 2 * (self.num_inputs + 1 + i)    # Delta 编码参考点

            # 解码 rhs0: rhs0_lit = S_i - delta0
            delta0, pos = self._decode_varint(data, pos)
            rhs0_lit = S_i - delta0

            # 解码 rhs1: rhs1_lit = rhs0_lit - delta1
            delta1, pos = self._decode_varint(data, pos)
            rhs1_lit = rhs0_lit - delta1

            # 创建 AND 节点
            inv0 = self.lit_is_inverted(rhs0_lit)
            inv1 = self.lit_is_inverted(rhs1_lit)
            fanin0 = self.lit_to_var(rhs0_lit)
            fanin1 = self.lit_to_var(rhs1_lit)

            and_node = AIGNode(
                node_id=and_var,
                node_type='AND',
                fanin0=fanin0,
                fanin1=fanin1,
            )
            and_node.inv0 = inv0
            and_node.inv1 = inv1

            self.nodes[and_var] = and_node

        # --- 解析 PO 字面量 ---
        # PO 使用 Delta 编码, 相对于 M (max_var)
        for _ in range(self.num_outputs):
            delta, pos = self._decode_varint(data, pos)
            lit = self.max_var - delta
            self.po_lits.append(lit)

            # 创建 PO 节点 (用 unique id: max_var + output_idx + 1)
            po_id = self.max_var + len(self.po_lits)
            po_var = self.lit_to_var(lit)
            po_node = AIGNode(
                node_id=po_id,
                node_type='PO',
                fanin0=po_var,
                fanin1=0,
            )
            po_node.inv0 = self.lit_is_inverted(lit)
            po_node.name = f"po_{len(self.po_lits)}"
            self.nodes[po_id] = po_node
            self.po_names.append(po_node.name)

        # --- 构建扇出关系 ---
        self._build_fanouts()

        self.parse_success = True
        return True

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _build_fanouts(self) -> None:
        """遍历所有节点, 构建扇出列表"""
        for node_id, node in self.nodes.items():
            if node.type == 'AND' or node.type == 'PO':
                # 将当前节点加入扇入节点的扇出列表
                for fanin in [node.fanin0, node.fanin1]:
                    if fanin in self.nodes and node.id not in self.nodes[fanin].fanout:
                        self.nodes[fanin].fanout.append(node.id)

    def parse_map_file(self, map_path: str) -> None:
        """解析 output_map.txt (端口名映射)

        映射文件由 yosys write_aiger -map 生成, 格式:
          <字面量> <信号名>

        Args:
            map_path: 映射文件路径
        """
        if not os.path.isfile(map_path):
            print(f"警告: 映射文件不存在 — {map_path}", file=sys.stderr)
            return

        with open(map_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                try:
                    lit = int(parts[0])
                    name = parts[1]
                except ValueError:
                    continue

                self.name_map[name] = lit
                var = self.lit_to_var(lit)

                # 将信号名赋给对应的节点
                if var in self.nodes:
                    self.nodes[var].name = name

                # 如果是 PO 输出, 尝试匹配
                for i, po_lit in enumerate(self.po_lits):
                    if po_lit == lit and i < len(self.po_names):
                        self.po_names[i] = name
                        po_id = self.max_var + i + 1
                        if po_id in self.nodes:
                            self.nodes[po_id].name = name

                # 如果是 PI 输入
                if 1 <= var <= self.num_inputs:
                    idx = var - 1
                    if idx < len(self.pi_names):
                        self.pi_names[idx] = name

    # ------------------------------------------------------------------
    # NetworkX 转换
    # ------------------------------------------------------------------
    def to_networkx(self) -> 'nx.MultiDiGraph':
        """转换为 NetworkX 有向图

        Returns:
            networkx.MultiDiGraph 对象

        Raises:
            ImportError: 未安装 networkx
        """
        if not _HAVE_NETWORKX:
            raise ImportError("需要安装 networkx: pip install networkx")

        G = nx.MultiDiGraph()

        for node_id, node in self.nodes.items():
            G.add_node(node_id,
                       type=node.type,
                       name=node.name,
                       inv0=node.inv0,
                       inv1=node.inv1)

        for node_id, node in self.nodes.items():
            if node.type == 'AND' or node.type == 'PO':
                # fanin0 边
                G.add_edge(node.fanin0, node_id,
                           inverted=node.inv0,
                           fanin_idx=0)
                # AND 门有两条输入
                if node.type == 'AND':
                    G.add_edge(node.fanin1, node_id,
                               inverted=node.inv1,
                               fanin_idx=1)

        return G

    # ------------------------------------------------------------------
    # PyTorch Geometric 转换
    # ------------------------------------------------------------------
    def to_pyg_data(self) -> 'Data':
        """转换为 PyTorch Geometric Data 对象

        节点特征 (8 维):
          - dim 0: 是否为 PI (1/0)
          - dim 1: 是否为 PO (1/0)
          - dim 2: 是否为 AND (1/0)
          - dim 3: 是否为 Latch (1/0)
          - dim 4: 是否为 Constant (1/0)
          - dim 5: 扇入数 (归一化至 [0, 1])
          - dim 6: 扇出数 (归一化至 [0, 1])
          - dim 7: 逻辑深度 (归一化至 [0, 1])

        边特征 (1 维):
          - dim 0: 是否反相 (1/0)

        Returns:
            torch_geometric.data.Data 对象

        Raises:
            ImportError: 未安装 PyTorch Geometric
        """
        if not _HAVE_PYG:
            raise ImportError("需要安装 PyTorch Geometric: "
                              "pip install torch_geometric")

        node_ids = sorted(self.nodes.keys())
        n = len(node_ids)
        id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

        # --- 节点特征 ---
        x = torch.zeros(n, 8, dtype=torch.float)

        # 计算逻辑深度 (拓扑排序)
        depth = self._compute_depth(node_ids)

        # 统计扇入/扇出用于归一化
        all_fanins = []
        all_fanouts = []
        for nid in node_ids:
            node = self.nodes[nid]
            fi = 0
            if node.type == 'AND':
                fi = 2
            elif node.type in ('PO', 'LIT'):
                fi = 1
            all_fanins.append(fi)
            all_fanouts.append(len(node.fanout))

        max_fi = max(all_fanins) if all_fanins else 1
        max_fo = max(all_fanouts) if all_fanouts else 1
        max_depth = max(depth) if depth else 1

        for i, nid in enumerate(node_ids):
            node = self.nodes[nid]
            x[i, 0] = 1.0 if node.type == 'PI' else 0.0
            x[i, 1] = 1.0 if node.type == 'PO' else 0.0
            x[i, 2] = 1.0 if node.type == 'AND' else 0.0
            x[i, 3] = 1.0 if node.type == 'LATCH' else 0.0
            x[i, 4] = 1.0 if node.type == 'CONST0' else 0.0
            x[i, 5] = all_fanins[i] / max_fi
            x[i, 6] = all_fanouts[i] / max_fo
            x[i, 7] = depth[i] / max_depth

        # --- 边 ---
        edge_list: List[Tuple[int, int]] = []
        edge_attr_list: List[float] = []

        for nid in node_ids:
            node = self.nodes[nid]
            if node.type == 'AND' or node.type == 'PO':
                # fanin0 → nid
                if node.fanin0 in id_to_idx:
                    edge_list.append((id_to_idx[node.fanin0], id_to_idx[nid]))
                    edge_attr_list.append(1.0 if node.inv0 else 0.0)
                # AND 门还有 fanin1
                if node.type == 'AND' and node.fanin1 in id_to_idx:
                    edge_list.append((id_to_idx[node.fanin1], id_to_idx[nid]))
                    edge_attr_list.append(1.0 if node.inv1 else 0.0)

        edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
        edge_attr = torch.tensor(edge_attr_list, dtype=torch.float).view(-1, 1)

        # ── 节点类型 (与 BLIF 管线对齐, 方便统一处理) ──
        #  PI=0, PO=1, AND=2, DFF=3, CONST0=4, CONST1=5
        _NODE_TYPE_MAP = {
            'PI': 0, 'PO': 1, 'AND': 2, 'LATCH': 3, 'CONST0': 4, 'CONST1': 5,
        }
        node_type_list = []
        for nid in node_ids:
            node = self.nodes[nid]
            nt = _NODE_TYPE_MAP.get(node.type, 2)  # default to AND (2)
            node_type_list.append(nt)
        node_type = torch.tensor(node_type_list, dtype=torch.long)

        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr,
                    node_type=node_type)

    def _compute_depth(self, node_ids: List[int]) -> List[int]:
        """计算每个节点的逻辑深度 (拓扑排序)

        Args:
            node_ids: 节点 ID 列表

        Returns:
            每个节点对应的深度列表
        """
        id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
        depth = [0] * len(node_ids)

        # 按变量编号升序遍历 (拓扑序保证: 因为 lhs > fanin)
        for nid in sorted(node_ids):
            node = self.nodes[nid]
            if nid in id_to_idx:
                idx = id_to_idx[nid]
                if node.type == 'CONST0':
                    depth[idx] = 0
                elif node.type == 'PI':
                    depth[idx] = 0
                elif node.type == 'AND':
                    d0 = 0
                    d1 = 0
                    if node.fanin0 in id_to_idx:
                        d0 = depth[id_to_idx[node.fanin0]]
                    if node.fanin1 in id_to_idx:
                        d1 = depth[id_to_idx[node.fanin1]]
                    depth[idx] = max(d0, d1) + 1
                elif node.type == 'PO':
                    if node.fanin0 in id_to_idx:
                        depth[idx] = depth[id_to_idx[node.fanin0]] + 1
        return depth

    # ------------------------------------------------------------------
    # 统计信息
    # ------------------------------------------------------------------
    def print_stats(self) -> None:
        """打印 AIG 统计信息"""
        if not self.parse_success:
            print("AIG 尚未解析成功, 无法输出统计信息", file=sys.stderr)
            return

        pi_count = sum(1 for n in self.nodes.values() if n.type == 'PI')
        po_count = sum(1 for n in self.nodes.values() if n.type == 'PO')
        and_count = sum(1 for n in self.nodes.values() if n.type == 'AND')
        const_count = sum(1 for n in self.nodes.values() if n.type == 'CONST0')

        # 计算逻辑深度
        node_ids = sorted(self.nodes.keys())
        depth = self._compute_depth(node_ids)
        max_depth = max(depth) if depth else 0

        # 计算总反相器数量 (边上的反相标记)
        inv_count = 0
        for n in self.nodes.values():
            if n.type in ('AND', 'PO'):
                if n.inv0:
                    inv_count += 1
                if n.type == 'AND' and n.inv1:
                    inv_count += 1

        print("=" * 48)
        print("  AIG 统计信息")
        print("=" * 48)
        print(f"  输入 (PI):         {pi_count:>8d}")
        print(f"  输出 (PO):         {po_count:>8d}")
        print(f"  AND 门:            {and_count:>8d}")
        print(f"  常量 0:            {const_count:>8d}")
        print(f"  反相器:            {inv_count:>8d}")
        print(f"  节点总数:          {len(self.nodes):>8d}")
        print(f"  逻辑深度:          {max_depth:>8d}")
        print(f"  AIG 节点数 (变量): {self.max_var:>8d}")
        print("-" * 48)

        if self.pi_names:
            print(f"  PI 列表: {', '.join(self.pi_names[:10])}"
                  f"{'...' if len(self.pi_names) > 10 else ''}")
        if self.po_names:
            print(f"  PO 列表: {', '.join(self.po_names[:10])}"
                  f"{'...' if len(self.po_names) > 10 else ''}")
        print("=" * 48)


# ======================================================================
# 使用示例
# ======================================================================
def demo_synth_and_parse(verilog_file: str, yosys_script: str = None) -> Optional[AIGParser]:
    """综合 Verilog 文件为 AIG 并解析

    流程:
      1. 调用 yosys 执行综合脚本, 生成 output.aig
      2. 使用 AIGParser 解析 AIG 文件
      3. 尝试转换为 PyG Data 并输出统计信息

    Args:
        verilog_file: Verilog RTL 文件路径
        yosys_script: yosys TCL 脚本路径 (默认使用同目录下的 synth_to_aig.tcl)

    Returns:
        解析成功返回 AIGParser 实例, 否则返回 None
    """
    # 确定脚本路径
    if yosys_script is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        yosys_script = os.path.join(script_dir, "synth_to_aig.tcl")

    work_dir = os.path.dirname(os.path.abspath(verilog_file))

    # 生成 verilog_files.txt
    files_txt = os.path.join(work_dir, "verilog_files.txt")
    with open(files_txt, 'w') as f:
        f.write(verilog_file + "\n")
    print(f"[示例] 已创建 {files_txt}")

    # 调用 yosys
    print(f"[示例] 调用 yosys 综合 '{verilog_file}' → AIG ...")
    cmd = ["yosys", "-s", yosys_script]
    result = subprocess.run(cmd,
                            cwd=work_dir,
                            capture_output=True,
                            text=True)

    # 打印 yosys 输出
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print(f"[示例] yosys 执行失败 (返回码 {result.returncode})",
              file=sys.stderr)
        return None

    # 解析 AIG
    aig_path = os.path.join(work_dir, "output.aig")
    map_path = os.path.join(work_dir, "output_map.txt")

    parser = AIGParser()
    parser._debug = True  # 开启调试输出
    if not parser.parse_file(aig_path):
        print("[示例] AIG 解析失败", file=sys.stderr)
        return None

    # 加载端口映射
    parser.parse_map_file(map_path)

    # 打印统计信息
    parser.print_stats()

    # 转换为 PyG Data
    if _HAVE_PYG:
        try:
            data = parser.to_pyg_data()
            print(f"[示例] PyG Data 对象:")
            print(f"       x:         {data.x.shape}")
            print(f"       edge_index: {data.edge_index.shape}")
            print(f"       edge_attr:  {data.edge_attr.shape}")
        except Exception as e:
            print(f"[示例] PyG 转换失败: {e}", file=sys.stderr)
    else:
        print("[示例] PyTorch Geometric 未安装, 跳过 PyG 转换")

    # 转换为 NetworkX
    if _HAVE_NETWORKX:
        try:
            G = parser.to_networkx()
            print(f"[示例] NetworkX 图: {G.number_of_nodes()} 个节点, "
                  f"{G.number_of_edges()} 条边")
        except Exception as e:
            print(f"[示例] NetworkX 转换失败: {e}", file=sys.stderr)
    else:
        print("[示例] NetworkX 未安装, 跳过图转换")

    # 清理中间文件
    for fname in ["verilog_files.txt", "output.aig", "output_map.txt",
                   "output_netlist.v"]:
        fpath = os.path.join(work_dir, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)
            print(f"[示例] 清理中间文件: {fname}")

    print("[示例] 完成!")
    return parser


def demo_parse_existing(aig_path: str, map_path: str = None) -> Optional[AIGParser]:
    """解析已有的 AIG 文件 (不调用 yosys)

    Args:
        aig_path: AIG 文件路径
        map_path: 可选的端口映射文件路径

    Returns:
        解析成功返回 AIGParser 实例, 否则返回 None
    """
    parser = AIGParser()
    if not parser.parse_file(aig_path):
        print(f"[示例] AIG 解析失败: {aig_path}", file=sys.stderr)
        return None

    if map_path and os.path.isfile(map_path):
        parser.parse_map_file(map_path)

    parser.print_stats()

    if _HAVE_PYG:
        try:
            data = parser.to_pyg_data()
            print(f"[示例] PyG Data: x={data.x.shape}, "
                  f"edge_index={data.edge_index.shape}")
        except Exception as e:
            print(f"[示例] PyG 转换失败: {e}", file=sys.stderr)

    return parser


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="AIGER 二进制格式解析器 — 解析并转换 AIG 为图结构数据")

    parser.add_argument("--aig", type=str, default=None,
                        help="已存在的 .aig 文件路径 (跳过 yosys 综合)")
    parser.add_argument("--map", type=str, default=None,
                        help="端口映射文件路径 (与 --aig 配合使用)")
    parser.add_argument("--verilog", type=str, default=None,
                        help="Verilog RTL 文件路径 (自动调用 yosys 综合)")
    parser.add_argument("--yosys-script", type=str, default=None,
                        help="yosys TCL 综合脚本路径")

    args = parser.parse_args()

    if args.aig:
        # 解析已有 AIG 文件
        demo_parse_existing(args.aig, args.map)
    elif args.verilog:
        # 综合并解析
        demo_synth_and_parse(args.verilog, args.yosys_script)
    else:
        # 无参数: 打印帮助
        parser.print_help()
        print("\n" + "=" * 60)
        print("使用方式:")
        print("  1) python aig_parser.py --verilog <rtl.v>")
        print("     (自动调用 yosys 综合并解析)")
        print()
        print("  2) python aig_parser.py --aig <output.aig> --map <output_map.txt>")
        print("     (解析已有的 AIG 文件)")
        print("=" * 60)
