#!/usr/bin/env python3
"""
gen_mock_aig.py — 生成模拟 AIGER 二进制文件

在缺少 yosys 工具链时，生成一个结构上模拟真实设计的
AIG 文件，用于演示 AIGParser 的解析和分析能力。

生成的电路模拟一个 4 级加法器链 + 状态控制逻辑，
具有非均匀的扇入扇出分布。

用法:
    python gen_mock_aig.py [output_path]
"""

import struct
import sys
import os


def encode_varint(n: int) -> bytes:
    """编码 AIGER 变长无符号整数"""
    result = []
    while n > 0x7F:
        result.append((n & 0x7F) | 0x80)
        n >>= 7
    result.append(n & 0x7F)
    return bytes(result)


def generate_mock_aig(output_path: str) -> str:
    """生成模拟 AIG 文件
    
    电路结构 (模拟 4-bit 加法器 + 流水线控制):
      PI:     clk, rst_n, en, A[3:0], B[3:0]  (10 PIs)
              + data_in[7:0]                     (8 PIs)
              总计 18 PIs
      
      内部逻辑 (~50 个 AND 门):
        - 4-bit 加法器的进位链 (逐位进位传播)
        - 累加器逻辑 (acc_reg 相关的多路选择)
        - 状态机转移逻辑 (state_next 的 3 种状态)
        - 错误检测逻辑 (奇偶校验、ECC syndrome)
      
      PO:     sum[3:0], carry_out, state[1:0],
              result[7:0], done, error_flag    (9 POs)
    
    扇入分布特点:
      - 低位加法器: 扇入 2 (简单 AND)
      - 高位加法器 (进位链): 扇入 4-6 (多级 AND)
      - 状态译码: 扇入 4-5
      - 错误检测: 扇入 6-8 (高扇入)
    """

    # ========== 设计参数 ==========
    I = 18        # Primary Inputs (变量 1..18)
    A = 52        # AND gates
    O = 9         # Primary Outputs
    M = I + A     # Max variable (1 CONST0 + I PIs + A ANDs)
    L = 0         # 无锁存器 (组合 AIG)

    # ========== 构建 AND 门输入对 ==========
    # 每个 AND 门 i 的输入 (rhs0_lit, rhs1_lit)
    # 要求: rhs0_lit >= rhs1_lit (delta 编码前提)
    # 字面量 = var * 2 (正相) 或 var * 2 + 1 (反相)
    
    and_inputs = []  # [(rhs0_lit, rhs1_lit), ...]
    
    # --- 第一级: 基础逻辑 (扇入 2) ---
    # AND 门 0:  clk & rst_n
    and_inputs.append((2*1 + 1, 2*1))      # ~var1 & var1 = 0 (占位)
    # 实际上我们要构建有意义的电路
    # 重新来: 使用 var 1..18 作为 PI
    
    pi = lambda v: 2 * v              # 正相 PI 字面量
    npi = lambda v: 2 * v + 1         # 反相 PI 字面量
    and_out = lambda i: 2 * (I + 1 + i)  # AND gate i 输出字面量

    def ordered_pair(a, b):
        """确保 rhs0 >= rhs1 (delta 编码前提)"""
        return (a, b) if a >= b else (b, a)

    # 加法器进位链:
    # 第 0 级: PI 的简单组合 (AND 0-5)
    and_inputs.append(ordered_pair(pi(3),  pi(4)))    # en & A[0]       → var 19
    and_inputs.append(ordered_pair(pi(5),  pi(6)))    # A[1] & A[2]      → var 20
    and_inputs.append(ordered_pair(pi(7),  pi(8)))    # A[3] & B[0]      → var 21
    and_inputs.append(ordered_pair(pi(9),  pi(10)))   # B[1] & B[2]      → var 22
    and_inputs.append(ordered_pair(pi(11), pi(12)))   # B[3] & data_in[0] → var 23
    and_inputs.append(ordered_pair(pi(13), pi(14)))   # data_in[1] & data_in[2] → var 24
    
    # AND gates 6-13: 进位传播 (扇入 2-4)
    # 使用前几级 AND 的输出作为输入
    and_inputs.append(ordered_pair(and_out(0), and_out(1)))     # var 19 & var 20 → var 25
    and_inputs.append(ordered_pair(and_out(2), and_out(3)))     # var 21 & var 22 → var 26
    and_inputs.append(ordered_pair(and_out(4), and_out(5)))     # var 23 & var 24 → var 27
    # 混合 PI + AND 输出
    and_inputs.append(ordered_pair(and_out(6), pi(15)))          # var 25 & data_in[3] → var 28
    and_inputs.append(ordered_pair(and_out(7), pi(16)))          # var 26 & data_in[4] → var 29
    and_inputs.append(ordered_pair(and_out(8), pi(17)))          # var 27 & data_in[5] → var 30
    and_inputs.append(ordered_pair(pi(3), npi(4)))               # en & ~A[0]         → var 31
    and_inputs.append(ordered_pair(npi(5), npi(6)))              # ~A[1] & ~A[2]      → var 32
    
    # AND gates 14-21: 进位链传播 (扇入 3-4)
    and_inputs.append(ordered_pair(and_out(9), and_out(10)))    # var 28 & var 29 → var 33
    and_inputs.append(ordered_pair(and_out(11), and_out(12)))   # var 30 & var 31 → var 34
    and_inputs.append(ordered_pair(and_out(13), and_out(14)))   # var 32 & var 33 → var 35
    # 反相输入 + 层次化
    inv_35 = and_out(15) + 1  # ~var 35 (反相)
    and_inputs.append(ordered_pair(pi(1),  inv_35))              # clk & ~var 35     → var 36
    and_inputs.append(ordered_pair(pi(2),  and_out(14)))         # rst_n & var 33   → var 37
    and_inputs.append(ordered_pair(pi(3),  and_out(9)))          # en & var 28      → var 38
    inv_38 = and_out(20) + 1                                     # ~var 38
    and_inputs.append(ordered_pair(pi(4),  inv_38))              # A[0] & ~var 38   → var 39
    
    # AND gates 22-29: 状态机逻辑 (扇入 3-5)
    # state[0] 的组合逻辑
    and_inputs.append(ordered_pair(and_out(0),  and_out(6)))     # var 19 & var 25 → var 40
    and_inputs.append(ordered_pair(and_out(1),  and_out(7)))     # var 20 & var 26 → var 41
    and_inputs.append(ordered_pair(and_out(22), and_out(23)))    # var 40 & var 41 → var 42
    and_inputs.append(ordered_pair(pi(5), and_out(24)))          # A[1] & var 42   → var 43
    # state[1] 的组合逻辑
    and_inputs.append(ordered_pair(and_out(9),  and_out(25)))    # var 28 & var 43 → var 44
    and_inputs.append(ordered_pair(pi(6),  and_out(26)))         # A[2] & var 44   → var 45
    and_inputs.append(ordered_pair(npi(7), and_out(27)))         # ~A[3] & var 45  → var 46
    inv_46 = and_out(28) + 1                          # ~var 46
    and_inputs.append(ordered_pair(pi(8),  inv_46))               # B[0] & ~var 46  → var 47
    
    # AND gates 30-37: 累加器逻辑 (扇入 3-5)
    and_inputs.append(ordered_pair(and_out(0), and_out(28)))     # var 19 & var 46 → var 48
    and_inputs.append(ordered_pair(pi(9),  and_out(29)))          # B[1] & var 47   → var 49
    and_inputs.append(ordered_pair(and_out(30), and_out(31)))    # var 48 & var 49 → var 50
    and_inputs.append(ordered_pair(pi(10), and_out(32)))          # B[2] & var 50   → var 51
    and_inputs.append(ordered_pair(pi(11), and_out(33)))          # B[3] & var 51   → var 52
    and_inputs.append(ordered_pair(and_out(34), and_out(35)))    # var 51 & var 52 → var 53
    and_inputs.append(ordered_pair(pi(12), and_out(36)))          # data_in[0] & var 53 → var 54
    inv_54 = and_out(36) + 1                          # ~var 54
    and_inputs.append(ordered_pair(pi(13), inv_54))               # data_in[1] & ~var 54 → var 55
    
    # AND gates 38-45: 错误检测逻辑 (ECC 校验, 高扇入 5-6)
    and_inputs.append(ordered_pair(and_out(0),  and_out(30)))    # var 19 & var 48 → var 56
    and_inputs.append(ordered_pair(and_out(1),  and_out(31)))    # var 20 & var 49 → var 57
    and_inputs.append(ordered_pair(and_out(38), and_out(39)))    # var 56 & var 57 → var 58
    and_inputs.append(ordered_pair(and_out(2),  and_out(32)))    # var 21 & var 50 → var 59
    and_inputs.append(ordered_pair(and_out(3),  and_out(33)))    # var 22 & var 51 → var 60
    and_inputs.append(ordered_pair(and_out(41), and_out(42)))    # var 59 & var 60 → var 61
    and_inputs.append(ordered_pair(and_out(40), and_out(43)))    # var 58 & var 61 → var 62 (高扇入:6输入)
    and_inputs.append(ordered_pair(and_out(4),  and_out(34)))    # var 23 & var 52 → var 63
    
    # AND gates 46-51: 输出驱动 (扇入 2-4)
    and_inputs.append(ordered_pair(and_out(44), and_out(45)))    # var 62 & var 63 → var 64
    and_inputs.append(ordered_pair(and_out(37), and_out(46)))    # var 55 & var 64 → var 65
    and_inputs.append(ordered_pair(and_out(38), pi(14)))          # var 56 & data_in[2] → var 66
    and_inputs.append(ordered_pair(and_out(39), pi(15)))          # var 57 & data_in[3] → var 67
    and_inputs.append(ordered_pair(and_out(48), and_out(49)))    # var 66 & var 67 → var 68
    and_inputs.append(ordered_pair(and_out(47), and_out(50)))    # var 65 & var 68 → var 69
    
    # 验证数量
    assert len(and_inputs) == A, f"AND gate count mismatch: {len(and_inputs)} vs {A}"
    
    # ========== PO 字面量 ==========
    # PO 字面量 (需要按降序排列: PO delta 编码要求 lit[i] >= lit[i+1])
    po_lits = sorted([
        and_out(44),    # var 62 — 高扇入节点 (6 inputs)
        and_out(47),    # var 65 — 次高扇入
        and_out(50),    # var 68 — 扇入 2
        and_out(51),    # var 69 — 扇入 2
        and_out(46),    # var 64 — 输出驱动
        and_out(37),    # var 55 — 累加器输出
        and_out(35),    # var 53 — 累加器中间
        and_out(29),    # var 47 — B[0] 状态逻辑
        and_out(0),     # var 19 — 基础逻辑
    ], reverse=True)
    assert len(po_lits) == O, f"PO count mismatch: {len(po_lits)} vs {O}"
    
    # ========== 写入二进制文件 ==========
    header = f"aig {M} {I} {L} {O} {A}\n"
    
    body_parts = []
    
    # --- AND 门 delta 编码 ---
    for i, (rhs0, rhs1) in enumerate(and_inputs):
        S_i = 2 * (I + 1 + i)  # 序列参考点
        delta0 = S_i - rhs0
        delta1 = rhs0 - rhs1
        assert delta0 >= 0, f"AND {i}: delta0={delta0} < 0 (S_i={S_i}, rhs0={rhs0})"
        assert delta1 >= 0, f"AND {i}: delta1={delta1} < 0 (rhs0={rhs0}, rhs1={rhs1})"
        body_parts.append(encode_varint(delta0))
        body_parts.append(encode_varint(delta1))
    
    # --- PO delta 编码 ---
    po_seq = 2 * (M + 1)  # PO 序列起点
    for lit in po_lits:
        delta = po_seq - lit
        assert delta >= 0, f"PO: delta={delta} < 0"
        body_parts.append(encode_varint(delta))
        po_seq = lit  # 更新序列 (标准 AIGER)
    
    # 写出文件
    with open(output_path, 'wb') as f:
        f.write(header.encode('ascii'))
        for part in body_parts:
            f.write(part)
    
    return output_path


def print_circuit_info(output_path: str):
    """打印生成的电路信息"""
    import os
    size = os.path.getsize(output_path)
    print(f"[生成] 模拟 AIG 文件: {output_path}")
    print(f"       文件大小: {size} 字节")
    print(f"       电路: 4-bit 加法器链 + 状态控制 + 错误检测")
    print(f"       PI 数: 18 (clk, rst_n, en, A[3:0], B[3:0], data_in[7:0])")
    print(f"       AND 门数: 52")
    print(f"       PO 数: 9 (sum[3:0], carry_out, state[1:0], result, done, error)")
    print(f"       扇入分布: 低位 2, 中位 3-4, 高位(错误检测) 5-6")
    print()


if __name__ == "__main__":
    # 默认输出到 test_mock_data 目录
    default_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), 
                     "..", "..", "test_mock_data", "synth_output.aig")
    )
    
    output_path = sys.argv[1] if len(sys.argv) > 1 else default_path
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    
    generate_mock_aig(output_path)
    print_circuit_info(output_path)
    
    print("提示: 运行以下命令解析此 AIG 文件:")
    print(f"  python aig_parser.py --aig {output_path}")
