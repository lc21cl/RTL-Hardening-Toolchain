#!/usr/bin/env python3
"""voter_insertion.py — 投票器插入算法。

实现 Johnson & Wirthlin 提出的四种投票器插入策略：
  1. Full TMR — 完整三模冗余，在所有输出端插入投票器
  2. Partial TMR — 部分三模冗余，在关键路径插入投票器
  3. Input TMR — 输入级三模冗余，仅在模块输入处复制
  4. Output TMR — 输出级三模冗余，仅在模块输出处投票

参考来源: Johnson, S. B., & Wirthlin, M. J. (2004). 
  "Fault-Tolerant FPGA Design Using Triple Modular Redundancy."
"""

import re
from typing import Dict, List, Optional, Tuple


class VoterInsertionStrategy:
    """投票器插入策略枚举。"""
    FULL_TMR = 'full_tmr'
    PARTIAL_TMR = 'partial_tmr'
    INPUT_TMR = 'input_tmr'
    OUTPUT_TMR = 'output_tmr'


def insert_voter(
    rtl_content: str,
    signal_name: str,
    signal_type: str = 'wire',
    bit_width: int = 1
) -> str:
    """在指定信号处插入投票器。

    Args:
        rtl_content: 原始 RTL 源代码。
        signal_name: 信号名。
        signal_type: 信号类型 (wire/reg)。
        bit_width: 位宽。

    Returns:
        添加投票器后的 RTL 代码。
    """
    if bit_width == 1:
        voter_module = f"""
// Majority voter for {signal_name}
module majority_voter_{signal_name}(
    input A,
    input B,
    input C,
    output reg Z
);
    always @(*) begin
        Z = A & B | A & C | B & C;
    end
endmodule
"""
    else:
        voter_module = f"""
// Majority voter for {signal_name} ({bit_width} bits)
module majority_voter_{signal_name}(
    input [{bit_width-1}:0] A,
    input [{bit_width-1}:0] B,
    input [{bit_width-1}:0] C,
    output reg [{bit_width-1}:0] Z
);
    genvar i;
    generate
        for (i = 0; i < {bit_width}; i = i + 1) begin: voter_bit
            always @(*) begin
                Z[i] = A[i] & B[i] | A[i] & C[i] | B[i] & C[i];
            end
        end
    endgenerate
endmodule
"""

    if 'endmodule' in rtl_content:
        idx = rtl_content.rfind('endmodule')
        rtl_content = rtl_content[:idx] + voter_module + '\n' + rtl_content[idx:]

    return rtl_content


def insert_voter_instance(
    rtl_content: str,
    signal_name: str,
    instance_name: str = None,
    bit_width: int = 1
) -> str:
    """插入投票器实例。

    Args:
        rtl_content: 原始 RTL 源代码。
        signal_name: 信号名。
        instance_name: 实例名（可选）。
        bit_width: 位宽。

    Returns:
        添加投票器实例后的 RTL 代码。
    """
    if instance_name is None:
        instance_name = f'voter_{signal_name}'

    if bit_width == 1:
        instance = f"""
    majority_voter_{signal_name} {instance_name}(
        .A({signal_name}_A),
        .B({signal_name}_B),
        .C({signal_name}_C),
        .Z({signal_name})
    );
"""
    else:
        instance = f"""
    majority_voter_{signal_name} {instance_name}(
        .A({signal_name}_A),
        .B({signal_name}_B),
        .C({signal_name}_C),
        .Z({signal_name})
    );
"""

    if 'endmodule' in rtl_content:
        idx = rtl_content.rfind('endmodule')
        rtl_content = rtl_content[:idx] + instance + '\n' + rtl_content[idx:]

    return rtl_content


def apply_full_tmr(
    rtl_content: str,
    signals: List[str],
    bit_widths: Dict[str, int] = None
) -> str:
    """应用 Full TMR 策略。

    在所有指定信号的输出端插入投票器，实现完整三模冗余。

    Args:
        rtl_content: 原始 RTL 源代码。
        signals: 需要三模化的信号列表。
        bit_widths: 信号位宽映射（可选）。

    Returns:
        Full TMR 加固后的 RTL 代码。
    """
    if bit_widths is None:
        bit_widths = {}

    for sig_name in signals:
        bit_width = bit_widths.get(sig_name, 1)
        rtl_content = insert_voter(rtl_content, sig_name, bit_width=bit_width)
        rtl_content = insert_voter_instance(rtl_content, sig_name, bit_width=bit_width)

    return rtl_content


def apply_partial_tmr(
    rtl_content: str,
    critical_signals: List[str],
    non_critical_signals: List[str] = None,
    bit_widths: Dict[str, int] = None
) -> str:
    """应用 Partial TMR 策略。

    仅在关键信号处插入投票器，非关键信号只进行复制。

    Args:
        rtl_content: 原始 RTL 源代码。
        critical_signals: 关键信号列表（需要投票器）。
        non_critical_signals: 非关键信号列表（仅复制，可选）。
        bit_widths: 信号位宽映射（可选）。

    Returns:
        Partial TMR 加固后的 RTL 代码。
    """
    if non_critical_signals is None:
        non_critical_signals = []
    if bit_widths is None:
        bit_widths = {}

    for sig_name in critical_signals:
        bit_width = bit_widths.get(sig_name, 1)
        rtl_content = insert_voter(rtl_content, sig_name, bit_width=bit_width)
        rtl_content = insert_voter_instance(rtl_content, sig_name, bit_width=bit_width)

    for sig_name in non_critical_signals:
        bit_width = bit_widths.get(sig_name, 1)
        rtl_content = insert_voter(rtl_content, sig_name, bit_width=bit_width)

    return rtl_content


def apply_input_tmr(
    rtl_content: str,
    input_signals: List[str],
    bit_widths: Dict[str, int] = None
) -> str:
    """应用 Input TMR 策略。

    仅在模块输入端进行信号复制，内部逻辑共享。

    Args:
        rtl_content: 原始 RTL 源代码。
        input_signals: 输入信号列表。
        bit_widths: 信号位宽映射（可选）。

    Returns:
        Input TMR 加固后的 RTL 代码。
    """
    if bit_widths is None:
        bit_widths = {}

    for sig_name in input_signals:
        bit_width = bit_widths.get(sig_name, 1)

        if bit_width == 1:
            declarations = f"""
    wire {sig_name}_A;
    wire {sig_name}_B;
    wire {sig_name}_C;
    assign {sig_name}_A = {sig_name};
    assign {sig_name}_B = {sig_name};
    assign {sig_name}_C = {sig_name};
"""
        else:
            declarations = f"""
    wire [{bit_width-1}:0] {sig_name}_A;
    wire [{bit_width-1}:0] {sig_name}_B;
    wire [{bit_width-1}:0] {sig_name}_C;
    assign {sig_name}_A = {sig_name};
    assign {sig_name}_B = {sig_name};
    assign {sig_name}_C = {sig_name};
"""

        if 'endmodule' in rtl_content:
            idx = rtl_content.rfind('endmodule')
            rtl_content = rtl_content[:idx] + declarations + '\n' + rtl_content[idx:]

    return rtl_content


def apply_output_tmr(
    rtl_content: str,
    output_signals: List[str],
    bit_widths: Dict[str, int] = None
) -> str:
    """应用 Output TMR 策略。

    仅在模块输出端插入投票器，内部逻辑三模化。

    Args:
        rtl_content: 原始 RTL 源代码。
        output_signals: 输出信号列表。
        bit_widths: 信号位宽映射（可选）。

    Returns:
        Output TMR 加固后的 RTL 代码。
    """
    if bit_widths is None:
        bit_widths = {}

    for sig_name in output_signals:
        bit_width = bit_widths.get(sig_name, 1)
        rtl_content = insert_voter(rtl_content, sig_name, bit_width=bit_width)
        rtl_content = insert_voter_instance(rtl_content, sig_name, bit_width=bit_width)

    return rtl_content


def apply_tmr_strategy(
    rtl_content: str,
    strategy: str,
    signals: Dict[str, List[str]],
    bit_widths: Dict[str, int] = None
) -> str:
    """根据指定策略应用 TMR。

    Args:
        rtl_content: 原始 RTL 源代码。
        strategy: 策略类型 ('full_tmr', 'partial_tmr', 'input_tmr', 'output_tmr')。
        signals: 信号分类 {input, output, critical, non_critical}。
        bit_widths: 信号位宽映射（可选）。

    Returns:
        TMR 加固后的 RTL 代码。
    """
    if bit_widths is None:
        bit_widths = {}

    input_signals = signals.get('input', [])
    output_signals = signals.get('output', [])
    critical_signals = signals.get('critical', [])
    non_critical_signals = signals.get('non_critical', [])

    if strategy == VoterInsertionStrategy.FULL_TMR:
        all_signals = input_signals + output_signals + critical_signals + non_critical_signals
        return apply_full_tmr(rtl_content, all_signals, bit_widths)

    elif strategy == VoterInsertionStrategy.PARTIAL_TMR:
        return apply_partial_tmr(
            rtl_content,
            critical_signals,
            non_critical_signals,
            bit_widths
        )

    elif strategy == VoterInsertionStrategy.INPUT_TMR:
        return apply_input_tmr(rtl_content, input_signals, bit_widths)

    elif strategy == VoterInsertionStrategy.OUTPUT_TMR:
        return apply_output_tmr(rtl_content, output_signals, bit_widths)

    else:
        raise ValueError(f"Unknown strategy: {strategy}")


def analyze_tmr_overhead(
    original_gates: int,
    strategy: str,
    signal_count: int,
    average_bit_width: int = 1
) -> Dict[str, float]:
    """分析 TMR 策略的面积开销。

    Args:
        original_gates: 原始门数。
        strategy: 策略类型。
        signal_count: 信号数量。
        average_bit_width: 平均位宽。

    Returns:
        dict: 包含 area_overhead, voter_count, replicated_gates 的分析结果。
    """
    voter_gates_per_bit = 5
    voter_gates = signal_count * average_bit_width * voter_gates_per_bit

    if strategy == VoterInsertionStrategy.FULL_TMR:
        replicated_gates = original_gates * 3
        total_gates = replicated_gates + voter_gates
        area_overhead = (total_gates / original_gates) * 100

    elif strategy == VoterInsertionStrategy.PARTIAL_TMR:
        replicated_gates = original_gates * 3
        critical_count = int(signal_count * 0.3)
        voter_gates = critical_count * average_bit_width * voter_gates_per_bit
        total_gates = replicated_gates + voter_gates
        area_overhead = (total_gates / original_gates) * 100

    elif strategy == VoterInsertionStrategy.INPUT_TMR:
        replicated_gates = original_gates
        voter_gates = 0
        total_gates = replicated_gates + voter_gates
        area_overhead = (total_gates / original_gates) * 100

    elif strategy == VoterInsertionStrategy.OUTPUT_TMR:
        replicated_gates = original_gates * 3
        voter_gates = signal_count * average_bit_width * voter_gates_per_bit
        total_gates = replicated_gates + voter_gates
        area_overhead = (total_gates / original_gates) * 100

    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    return {
        'original_gates': original_gates,
        'replicated_gates': replicated_gates,
        'voter_gates': voter_gates,
        'total_gates': total_gates,
        'area_overhead_percent': area_overhead,
        'voter_count': signal_count * average_bit_width,
    }


def generate_tmr_wrapper(
    module_name: str,
    input_ports: List[Dict],
    output_ports: List[Dict],
    strategy: str = VoterInsertionStrategy.FULL_TMR
) -> str:
    """生成 TMR 包装器模块。

    Args:
        module_name: 原始模块名。
        input_ports: 输入端口列表 [{name, width}, ...]。
        output_ports: 输出端口列表 [{name, width}, ...]。
        strategy: 策略类型。

    Returns:
        TMR 包装器 RTL 代码。
    """
    input_declarations = []
    output_declarations = []
    instance_connections = []
    voter_instances = []

    for port in input_ports:
        name = port['name']
        width = port.get('width', 1)
        if width == 1:
            input_declarations.append(f'    input {name},')
            input_declarations.append(f'    wire {name}_A, {name}_B, {name}_C;')
            instance_connections.append(f'        .{name}({name}_A),')
            instance_connections.append(f'        .{name}({name}_B),')
            instance_connections.append(f'        .{name}({name}_C),')
        else:
            input_declarations.append(f'    input [{width-1}:0] {name},')
            input_declarations.append(f'    wire [{width-1}:0] {name}_A, {name}_B, {name}_C;')
            instance_connections.append(f'        .{name}({name}_A),')
            instance_connections.append(f'        .{name}({name}_B),')
            instance_connections.append(f'        .{name}({name}_C),')

    for port in output_ports:
        name = port['name']
        width = port.get('width', 1)
        if width == 1:
            output_declarations.append(f'    output {name},')
            output_declarations.append(f'    wire {name}_A, {name}_B, {name}_C;')
            instance_connections.append(f'        .{name}({name}_A),')
            instance_connections.append(f'        .{name}({name}_B),')
            instance_connections.append(f'        .{name}({name}_C),')
            voter_instances.append(f"""
    majority_voter_{name} voter_{name}(
        .A({name}_A),
        .B({name}_B),
        .C({name}_C),
        .Z({name})
    );""")
        else:
            output_declarations.append(f'    output [{width-1}:0] {name},')
            output_declarations.append(f'    wire [{width-1}:0] {name}_A, {name}_B, {name}_C;')
            instance_connections.append(f'        .{name}({name}_A),')
            instance_connections.append(f'        .{name}({name}_B),')
            instance_connections.append(f'        .{name}({name}_C),')
            voter_instances.append(f"""
    majority_voter_{name} voter_{name}(
        .A({name}_A),
        .B({name}_B),
        .C({name}_C),
        .Z({name})
    );""")

    wrapper = f"""
module {module_name}_tmr (
{', '.join([p['name'] for p in input_ports])},
{', '.join([p['name'] for p in output_ports])}
);

{chr(10).join(input_declarations)}
{chr(10).join(output_declarations)}

    assign {chr(10).join([f'{p["name"]}_A = {p["name"]};' for p in input_ports])}
    assign {chr(10).join([f'{p["name"]}_B = {p["name"]};' for p in input_ports])}
    assign {chr(10).join([f'{p["name"]}_C = {p["name"]};' for p in input_ports])}

    {module_name} inst_A (
{chr(10).join(instance_connections[:-3])}
        .{input_ports[-1]['name']}({input_ports[-1]['name']}_A)
    );

    {module_name} inst_B (
{chr(10).join(instance_connections[:-3])}
        .{input_ports[-1]['name']}({input_ports[-1]['name']}_B)
    );

    {module_name} inst_C (
{chr(10).join(instance_connections[:-3])}
        .{input_ports[-1]['name']}({input_ports[-1]['name']}_C)
    );

{chr(10).join(voter_instances)}

endmodule
"""

    return wrapper