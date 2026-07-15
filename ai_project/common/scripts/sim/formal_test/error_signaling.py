#!/usr/bin/env python3
"""error_signaling.py — 错误信号设计完善模块。

实现错误检测和信号报告机制，参考TaMaRa方法。

功能:
  - 添加错误检测信号
  - 实现错误报告机制
  - 生成错误恢复逻辑
"""

import re
from typing import Dict, List, Optional


def add_error_detection_signal(
    rtl_content: str,
    signal_name: str,
    signal_width: int = 1,
    error_type: str = 'tmr'
) -> str:
    """添加错误检测信号。

    Args:
        rtl_content: RTL源代码。
        signal_name: 信号名。
        signal_width: 位宽。
        error_type: 错误类型 ('tmr', 'dice', 'ecc')。

    Returns:
        添加错误检测信号后的代码。
    """
    if error_type == 'tmr':
        return _add_tmr_error_signal(rtl_content, signal_name, signal_width)
    elif error_type == 'dice':
        return _add_dice_error_signal(rtl_content, signal_name)
    elif error_type == 'ecc':
        return _add_ecc_error_signal(rtl_content, signal_name)
    else:
        return rtl_content


def _add_tmr_error_signal(rtl_content: str, signal_name: str, width: int) -> str:
    """添加TMR错误检测信号。"""
    if width == 1:
        error_signal = f"""
    wire {signal_name};
    assign {signal_name} = ({signal_name}_A != {signal_name}_B) | 
                          ({signal_name}_A != {signal_name}_C) | 
                          ({signal_name}_B != {signal_name}_C);
"""
    else:
        error_signal = f"""
    reg [{width-1}:0] {signal_name};
    always @(*) begin
        for (int i = 0; i < {width}; i = i + 1) begin
            {signal_name}[i] = ({signal_name}_A[i] != {signal_name}_B[i]) | 
                              ({signal_name}_A[i] != {signal_name}_C[i]) | 
                              ({signal_name}_B[i] != {signal_name}_C[i]);
        end
    end
"""

    if 'endmodule' in rtl_content:
        idx = rtl_content.rfind('endmodule')
        rtl_content = rtl_content[:idx] + error_signal + '\n' + rtl_content[idx:]

    return rtl_content


def _add_dice_error_signal(rtl_content: str, signal_name: str) -> str:
    """添加DICE错误检测信号。"""
    error_signal = f"""
    wire {signal_name};
    assign {signal_name} = (n1 != ~n2) | (p1 != ~p2);
"""

    if 'endmodule' in rtl_content:
        idx = rtl_content.rfind('endmodule')
        rtl_content = rtl_content[:idx] + error_signal + '\n' + rtl_content[idx:]

    return rtl_content


def _add_ecc_error_signal(rtl_content: str, signal_name: str) -> str:
    """添加ECC错误检测信号。"""
    error_signal = f"""
    wire {signal_name};
    assign {signal_name} = ^syndrome;
"""

    if 'endmodule' in rtl_content:
        idx = rtl_content.rfind('endmodule')
        rtl_content = rtl_content[:idx] + error_signal + '\n' + rtl_content[idx:]

    return rtl_content


def add_error_reporting_module(rtl_content: str) -> str:
    """添加错误报告模块。

    Args:
        rtl_content: RTL源代码。

    Returns:
        添加错误报告模块后的代码。
    """
    error_report = """
module error_report(
    input clk,
    input rst,
    input [31:0] error_vector,
    output reg error_detected,
    output reg [4:0] error_count
);
    reg [31:0] error_history;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            error_detected <= 1'b0;
            error_count <= 5'b0;
            error_history <= 32'b0;
        end else begin
            error_history <= {error_history[30:0], |error_vector};
            error_detected <= |error_vector;
            if (|error_vector && !error_detected) begin
                error_count <= error_count + 1'b1;
            end
        end
    end
endmodule
"""

    if 'endmodule' in rtl_content:
        idx = rtl_content.rfind('endmodule')
        rtl_content = rtl_content[:idx] + error_report + '\n' + rtl_content[idx:]

    return rtl_content


def generate_error_recovery_logic(
    rtl_content: str,
    recovery_type: str = 'reset'
) -> str:
    """生成错误恢复逻辑。

    Args:
        rtl_content: RTL源代码。
        recovery_type: 恢复类型 ('reset', 'scrub', 'reconfiguration')。

    Returns:
        添加恢复逻辑后的代码。
    """
    if recovery_type == 'reset':
        return _generate_reset_recovery(rtl_content)
    elif recovery_type == 'scrub':
        return _generate_scrub_recovery(rtl_content)
    elif recovery_type == 'reconfiguration':
        return _generate_reconfig_recovery(rtl_content)
    else:
        return rtl_content


def _generate_reset_recovery(rtl_content: str) -> str:
    """生成复位恢复逻辑。"""
    recovery_logic = """
    reg error_reset;
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            error_reset <= 1'b0;
        end else if (error_detected) begin
            error_reset <= 1'b1;
        end else begin
            error_reset <= 1'b0;
        end
    end
"""

    if 'endmodule' in rtl_content:
        idx = rtl_content.rfind('endmodule')
        rtl_content = rtl_content[:idx] + recovery_logic + '\n' + rtl_content[idx:]

    return rtl_content


def _generate_scrub_recovery(rtl_content: str) -> str:
    """生成擦洗恢复逻辑。"""
    recovery_logic = """
    reg [7:0] scrub_counter;
    reg scrub_en;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            scrub_counter <= 8'b0;
            scrub_en <= 1'b0;
        end else begin
            if (error_detected) begin
                scrub_en <= 1'b1;
            end
            if (scrub_en) begin
                scrub_counter <= scrub_counter + 1'b1;
                if (scrub_counter == 8'hFF) begin
                    scrub_en <= 1'b0;
                end
            end
        end
    end
"""

    if 'endmodule' in rtl_content:
        idx = rtl_content.rfind('endmodule')
        rtl_content = rtl_content[:idx] + recovery_logic + '\n' + rtl_content[idx:]

    return rtl_content


def _generate_reconfig_recovery(rtl_content: str) -> str:
    """生成重配置恢复逻辑。"""
    recovery_logic = """
    reg reconfig_trigger;
    reg [2:0] reconfig_state;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            reconfig_trigger <= 1'b0;
            reconfig_state <= 3'b0;
        end else begin
            case (reconfig_state)
                3'b000: begin
                    if (error_detected) begin
                        reconfig_trigger <= 1'b1;
                        reconfig_state <= 3'b001;
                    end
                end
                3'b001: begin
                    reconfig_trigger <= 1'b0;
                    reconfig_state <= 3'b010;
                end
                3'b010: begin
                    reconfig_state <= 3'b011;
                end
                3'b011: begin
                    reconfig_state <= 3'b100;
                end
                3'b100: begin
                    reconfig_state <= 3'b000;
                end
            endcase
        end
    end
"""

    if 'endmodule' in rtl_content:
        idx = rtl_content.rfind('endmodule')
        rtl_content = rtl_content[:idx] + recovery_logic + '\n' + rtl_content[idx:]

    return rtl_content


def add_comprehensive_error_detection(
    rtl_content: str,
    strategy: str = 'tmr',
    include_recovery: bool = True,
    recovery_type: str = 'reset'
) -> str:
    """添加完整的错误检测和恢复机制。

    Args:
        rtl_content: RTL源代码。
        strategy: 加固策略。
        include_recovery: 是否包含恢复逻辑。
        recovery_type: 恢复类型。

    Returns:
        添加错误检测和恢复后的代码。
    """
    signals = _extract_signals(rtl_content)

    for sig_name in signals:
        if '_A' in sig_name:
            base_name = sig_name.replace('_A', '')
            rtl_content = add_error_detection_signal(
                rtl_content, f'{base_name}_error',
                signal_width=1,
                error_type=strategy
            )

    rtl_content = add_error_reporting_module(rtl_content)

    if include_recovery:
        rtl_content = generate_error_recovery_logic(rtl_content, recovery_type)

    return rtl_content


def _extract_signals(rtl_content: str) -> List[str]:
    """提取信号列表。"""
    signals = []
    patterns = [
        r'reg\s+(?:\[.*?\])?\s*(\w+)',
        r'wire\s+(?:\[.*?\])?\s*(\w+)',
        r'input\s+(?:wire|reg)?\s*(?:\[.*?\])?\s*(\w+)',
        r'output\s+(?:wire|reg)?\s*(?:\[.*?\])?\s*(\w+)',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, rtl_content):
            sig_name = match.group(1)
            if sig_name not in ('wire', 'reg', 'input', 'output', 'inout', 'logic'):
                signals.append(sig_name)

    return list(set(signals))


def generate_error_signal_interface(
    module_name: str,
    error_signals: List[str],
    include_reporting: bool = True
) -> str:
    """生成错误信号接口。

    Args:
        module_name: 模块名。
        error_signals: 错误信号列表。
        include_reporting: 是否包含报告模块。

    Returns:
        错误信号接口代码。
    """
    error_ports = []
    for sig in error_signals:
        error_ports.append(f'    output {sig},')

    error_interface = f"""
module {module_name}_error_interface (
    input clk,
    input rst,
{chr(10).join(error_ports)}
    output error_detected,
    output [7:0] error_count
);

    assign error_detected = { ' | '.join(error_signals) };

"""

    if include_reporting:
        error_interface += """
    reg [7:0] count;
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            count <= 8'b0;
        end else if (error_detected) begin
            count <= count + 1'b1;
        end
    end
    assign error_count = count;

"""

    error_interface += "endmodule"
    return error_interface


def analyze_error_signals(rtl_content: str) -> Dict[str, int]:
    """分析RTL代码中的错误信号。

    Args:
        rtl_content: RTL源代码。

    Returns:
        错误信号统计。
    """
    error_count = len(re.findall(r'error', rtl_content, re.IGNORECASE))
    tmr_error_count = len(re.findall(r'_A\s*!=\s*_B', rtl_content))
    ecc_error_count = len(re.findall(r'syndrome', rtl_content, re.IGNORECASE))
    recovery_count = len(re.findall(r'(reset|scrub|reconfig)', rtl_content, re.IGNORECASE))

    return {
        'total_error_signals': error_count,
        'tmr_error_checks': tmr_error_count,
        'ecc_error_checks': ecc_error_count,
        'recovery_mechanisms': recovery_count
    }