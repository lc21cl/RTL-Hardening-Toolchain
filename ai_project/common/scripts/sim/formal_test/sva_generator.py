#!/usr/bin/env python3
"""sva_generator.py — SVA断言生成模块。

自动为加固代码生成SystemVerilog断言。

功能:
  - TMR一致性断言
  - 错误检测断言
  - 时序断言
  - 覆盖率断言
"""

from typing import Dict, List, Optional


def generate_tmr_consistency_assertions(
    signals: List[str],
    module_name: str = 'top'
) -> str:
    """生成TMR一致性断言。

    Args:
        signals: 需要检查的信号列表。
        module_name: 模块名称。

    Returns:
        SVA断言代码。
    """
    assertions = []

    for sig in signals:
        assertions.append(f"""
    // TMR一致性断言: {sig}
    assert property (@(posedge clk)
        {sig}_A === {sig}_B && {sig}_B === {sig}_C
    ) else begin
        $error("TMR inconsistency detected for {sig}: A=%b, B=%b, C=%b",
            {sig}_A, {sig}_B, {sig}_C);
    end
    """)

    return '\n'.join(assertions)


def generate_error_detection_assertions(
    error_signals: List[str],
    module_name: str = 'top'
) -> str:
    """生成错误检测断言。

    Args:
        error_signals: 错误信号列表。
        module_name: 模块名称。

    Returns:
        SVA断言代码。
    """
    assertions = []

    for sig in error_signals:
        assertions.append(f"""
    // 错误检测断言: {sig}
    assert property (@(posedge clk)
        !{sig}
    ) else begin
        $error("Error detected on {sig}");
    end

    cover property (@(posedge clk)
        {sig}
    );
    """)

    return '\n'.join(assertions)


def generate_timing_assertions(
    signals: List[str],
    max_delay: int = 10,
    module_name: str = 'top'
) -> str:
    """生成时序断言。

    Args:
        signals: 需要检查的信号列表。
        max_delay: 最大延迟（时钟周期）。
        module_name: 模块名称。

    Returns:
        SVA断言代码。
    """
    assertions = []

    for sig in signals:
        assertions.append(f"""
    // 时序断言: {sig} 变化后 {max_delay} 周期内稳定
    assert property (@(posedge clk)
        $changed({sig}) |=> $stable({sig})[*{max_delay}]
    ) else begin
        $warning("{sig} not stable within {max_delay} cycles");
    end
    """)

    return '\n'.join(assertions)


def generate_reset_assertions(
    reset_signal: str = 'rst',
    signals: List[str] = None,
    module_name: str = 'top'
) -> str:
    """生成复位断言。

    Args:
        reset_signal: 复位信号名。
        signals: 需要检查的信号列表。
        module_name: 模块名称。

    Returns:
        SVA断言代码。
    """
    if signals is None:
        signals = []

    assertions = []

    assertions.append(f"""
    // 复位信号有效性断言
    assert property (@(posedge clk)
        $rose({reset_signal}) |=> {reset_signal}
    ) else begin
        $error("Reset signal de-asserted too quickly");
    end
    """)

    for sig in signals:
        zero_val = "'b0"
        assertions.append(f"""
    // 复位期间 {sig} 应为0
    assert property (@(posedge clk)
        {reset_signal} |-> {sig} === {zero_val}
    ) else begin
        $error("{sig} not zero during reset");
    end
    """)

    return '\n'.join(assertions)


def generate_interface_assertions(
    input_signals: List[str],
    output_signals: List[str],
    clock_signal: str = 'clk',
    reset_signal: str = 'rst'
) -> str:
    """生成接口断言。

    Args:
        input_signals: 输入信号列表。
        output_signals: 输出信号列表。
        clock_signal: 时钟信号名。
        reset_signal: 复位信号名。

    Returns:
        SVA断言代码。
    """
    assertions = []

    assertions.append(f"""
    // 接口断言: 时钟稳定性
    assert property (@(posedge {clock_signal})
        $stable({clock_signal})
    ) else begin
        $error("Clock signal instability detected");
    end
    """)

    for sig in input_signals:
        assertions.append(f"""
    // 输入 {sig} 在时钟沿稳定
    assert property (@(posedge {clock_signal})
        $stable({sig})
    ) else begin
        $warning("Input {sig} changed during clock edge");
    end
    """)

    for sig in output_signals:
        assertions.append(f"""
    // 输出 {sig} 在复位后有效
    assert property (@(posedge {clock_signal})
        !{reset_signal} |-> !$isunknown({sig})
    ) else begin
        $error("Output {sig} has unknown value after reset");
    end
    """)

    return '\n'.join(assertions)


def generate_comprehensive_sva(
    module_name: str,
    tmr_signals: List[str] = None,
    error_signals: List[str] = None,
    input_signals: List[str] = None,
    output_signals: List[str] = None,
    clock_signal: str = 'clk',
    reset_signal: str = 'rst'
) -> str:
    """生成完整的SVA断言模块。

    Args:
        module_name: 模块名称。
        tmr_signals: TMR信号列表。
        error_signals: 错误信号列表。
        input_signals: 输入信号列表。
        output_signals: 输出信号列表。
        clock_signal: 时钟信号名。
        reset_signal: 复位信号名。

    Returns:
        SVA断言模块代码。
    """
    if tmr_signals is None:
        tmr_signals = []
    if error_signals is None:
        error_signals = []
    if input_signals is None:
        input_signals = []
    if output_signals is None:
        output_signals = []

    sva_code = f"""
module {module_name}_sva(
    input {clock_signal},
    input {reset_signal}
);

{chr(10).join([f'    input {sig};' for sig in input_signals])}
{chr(10).join([f'    input {sig};' for sig in output_signals])}
{chr(10).join([f'    input {sig}_A, {sig}_B, {sig}_C;' for sig in tmr_signals])}
{chr(10).join([f'    input {sig};' for sig in error_signals])}

    default clocking @(posedge {clock_signal});
    endclocking

    default disable iff ({reset_signal});

"""

    sva_code += "    // =======================================================\n"
    sva_code += "    // TMR一致性断言\n"
    sva_code += "    // =======================================================\n"
    sva_code += generate_tmr_consistency_assertions(tmr_signals)

    sva_code += "\n    // =======================================================\n"
    sva_code += "    // 错误检测断言\n"
    sva_code += "    // =======================================================\n"
    sva_code += generate_error_detection_assertions(error_signals)

    sva_code += "\n    // =======================================================\n"
    sva_code += "    // 接口断言\n"
    sva_code += "    // =======================================================\n"
    sva_code += generate_interface_assertions(input_signals, output_signals, clock_signal, reset_signal)

    sva_code += "\n    // =======================================================\n"
    sva_code += "    // 复位断言\n"
    sva_code += "    // =======================================================\n"
    sva_code += generate_reset_assertions(reset_signal, tmr_signals)

    sva_code += "\nendmodule\n"

    return sva_code


def add_sva_to_rtl(rtl_content: str, sva_code: str) -> str:
    """将SVA断言添加到RTL代码中。

    Args:
        rtl_content: RTL源代码。
        sva_code: SVA断言代码。

    Returns:
        添加SVA后的代码。
    """
    if 'endmodule' in rtl_content:
        idx = rtl_content.rfind('endmodule')
        rtl_content = rtl_content[:idx] + sva_code + '\n' + rtl_content[idx:]
    else:
        rtl_content += '\n' + sva_code

    return rtl_content


def generate_sva_report(
    module_name: str,
    tmr_signals: List[str],
    error_signals: List[str],
    input_signals: List[str],
    output_signals: List[str]
) -> str:
    """生成SVA断言报告。

    Args:
        module_name: 模块名称。
        tmr_signals: TMR信号列表。
        error_signals: 错误信号列表。
        input_signals: 输入信号列表。
        output_signals: 输出信号列表。

    Returns:
        报告文本。
    """
    report_lines = [
        "=" * 70,
        "SVA断言生成报告",
        "=" * 70,
        ""
    ]

    report_lines.append(f"模块名称: {module_name}")
    report_lines.append(f"TMR一致性断言数量: {len(tmr_signals)}")
    report_lines.append(f"错误检测断言数量: {len(error_signals)}")
    report_lines.append(f"接口断言数量: {len(input_signals) + len(output_signals)}")
    report_lines.append(f"复位断言数量: {1 + len(tmr_signals)}")

    report_lines.append("")
    report_lines.append("TMR信号:")
    for sig in tmr_signals:
        report_lines.append(f"  - {sig}")

    report_lines.append("")
    report_lines.append("错误信号:")
    for sig in error_signals:
        report_lines.append(f"  - {sig}")

    report_lines.append("")
    report_lines.append("=" * 70)

    return '\n'.join(report_lines)