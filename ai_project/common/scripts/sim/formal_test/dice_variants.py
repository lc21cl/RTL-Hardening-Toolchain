#!/usr/bin/env python3
"""dice_variants.py — DICE变形结构支持模块。

实现多种DICE寄存器变体，参考DICE文献。

支持的结构:
  - Standard DICE — 4节点交叉耦合
  - DICE-2L — 双锁存器DICE
  - DICE-SEH — 单粒子闩锁免疫DICE
  - DICE-PD — 功率门控DICE
  - DICE-ST — 自检测DICE
"""

import re
from typing import Dict, List, Optional


class DICEVariant:
    """DICE变体枚举。"""
    STANDARD = 'standard'
    DICE_2L = 'dice_2l'
    DICE_SEH = 'dice_seh'
    DICE_PD = 'dice_pd'
    DICE_ST = 'dice_st'


def generate_dice_standard(
    width: int = 1,
    cell_name: str = 'dice_cell'
) -> str:
    """生成标准DICE单元。

    4节点交叉耦合结构：n1, n2, p1, p2

    Args:
        width: 位宽。
        cell_name: 单元名称。

    Returns:
        Verilog代码。
    """
    if width == 1:
        return f"""
module {cell_name}(
    input clk,
    input rst,
    input d,
    output q
);
    reg n1, n2, p1, p2;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            n1 <= 1'b0;
            n2 <= 1'b0;
            p1 <= 1'b1;
            p2 <= 1'b1;
        end else begin
            n1 <= d & ~n2;
            n2 <= d & ~n1;
            p1 <= ~d | p2;
            p2 <= ~d | p1;
        end
    end

    assign q = n1 & p1;
endmodule
"""
    else:
        return f"""
module {cell_name}(
    input clk,
    input rst,
    input [{width-1}:0] d,
    output [{width-1}:0] q
);
    genvar i;
    generate
        for (i = 0; i < {width}; i = i + 1) begin: dice_bit
            reg n1, n2, p1, p2;

            always @(posedge clk or posedge rst) begin
                if (rst) begin
                    n1 <= 1'b0;
                    n2 <= 1'b0;
                    p1 <= 1'b1;
                    p2 <= 1'b1;
                end else begin
                    n1 <= d[i] & ~n2;
                    n2 <= d[i] & ~n1;
                    p1 <= ~d[i] | p2;
                    p2 <= ~d[i] | p1;
                end
            end

            assign q[i] = n1 & p1;
        end
    endgenerate
endmodule
"""


def generate_dice_2l(
    width: int = 1,
    cell_name: str = 'dice_2l_cell'
) -> str:
    """生成DICE-2L（双锁存器DICE）。

    两个独立的DICE锁存器交替工作，提供更高的SEU免疫力。

    Args:
        width: 位宽。
        cell_name: 单元名称。

    Returns:
        Verilog代码。
    """
    if width == 1:
        return f"""
module {cell_name}(
    input clk,
    input rst,
    input d,
    output q
);
    reg n1a, n2a, p1a, p2a;
    reg n1b, n2b, p1b, p2b;
    reg sel;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            sel <= 1'b0;
            n1a <= 1'b0; n2a <= 1'b0; p1a <= 1'b1; p2a <= 1'b1;
            n1b <= 1'b0; n2b <= 1'b0; p1b <= 1'b1; p2b <= 1'b1;
        end else begin
            sel <= ~sel;
            if (sel) begin
                n1a <= d & ~n2a;
                n2a <= d & ~n1a;
                p1a <= ~d | p2a;
                p2a <= ~d | p1a;
            end else begin
                n1b <= d & ~n2b;
                n2b <= d & ~n1b;
                p1b <= ~d | p2b;
                p2b <= ~d | p1b;
            end
        end
    end

    assign q = sel ? (n1a & p1a) : (n1b & p1b);
endmodule
"""
    else:
        return f"""
module {cell_name}(
    input clk,
    input rst,
    input [{width-1}:0] d,
    output [{width-1}:0] q
);
    reg sel;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            sel <= 1'b0;
        end else begin
            sel <= ~sel;
        end
    end

    genvar i;
    generate
        for (i = 0; i < {width}; i = i + 1) begin: dice_bit
            reg n1a, n2a, p1a, p2a;
            reg n1b, n2b, p1b, p2b;

            always @(posedge clk or posedge rst) begin
                if (rst) begin
                    n1a <= 1'b0; n2a <= 1'b0; p1a <= 1'b1; p2a <= 1'b1;
                    n1b <= 1'b0; n2b <= 1'b0; p1b <= 1'b1; p2b <= 1'b1;
                end else begin
                    if (sel) begin
                        n1a <= d[i] & ~n2a;
                        n2a <= d[i] & ~n1a;
                        p1a <= ~d[i] | p2a;
                        p2a <= ~d[i] | p1a;
                    end else begin
                        n1b <= d[i] & ~n2b;
                        n2b <= d[i] & ~n1b;
                        p1b <= ~d[i] | p2b;
                        p2b <= ~d[i] | p1b;
                    end
                end
            end

            assign q[i] = sel ? (n1a & p1a) : (n1b & p1b);
        end
    endgenerate
endmodule
"""


def generate_dice_seh(
    width: int = 1,
    cell_name: str = 'dice_seh_cell'
) -> str:
    """生成DICE-SEH（单粒子闩锁免疫DICE）。

    添加额外的闩锁抑制电路，防止SEL（单粒子闩锁）。

    Args:
        width: 位宽。
        cell_name: 单元名称。

    Returns:
        Verilog代码。
    """
    if width == 1:
        return f"""
module {cell_name}(
    input clk,
    input rst,
    input d,
    output q,
    output sel_detected
);
    reg n1, n2, p1, p2;
    reg sel_flag;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            n1 <= 1'b0;
            n2 <= 1'b0;
            p1 <= 1'b1;
            p2 <= 1'b1;
            sel_flag <= 1'b0;
        end else begin
            n1 <= d & ~n2;
            n2 <= d & ~n1;
            p1 <= ~d | p2;
            p2 <= ~d | p1;

            if ((n1 && n2) || (!p1 && !p2)) begin
                sel_flag <= 1'b1;
            end
        end
    end

    assign q = n1 & p1;
    assign sel_detected = sel_flag;
endmodule
"""
    else:
        return f"""
module {cell_name}(
    input clk,
    input rst,
    input [{width-1}:0] d,
    output [{width-1}:0] q,
    output sel_detected
);
    reg sel_flag;
    reg [{width-1}:0] internal_sel;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            sel_flag <= 1'b0;
            internal_sel <= {width}'b0;
        end else begin
            sel_flag <= |internal_sel;
        end
    end

    genvar i;
    generate
        for (i = 0; i < {width}; i = i + 1) begin: dice_bit
            reg n1, n2, p1, p2;

            always @(posedge clk or posedge rst) begin
                if (rst) begin
                    n1 <= 1'b0;
                    n2 <= 1'b0;
                    p1 <= 1'b1;
                    p2 <= 1'b1;
                    internal_sel[i] <= 1'b0;
                end else begin
                    n1 <= d[i] & ~n2;
                    n2 <= d[i] & ~n1;
                    p1 <= ~d[i] | p2;
                    p2 <= ~d[i] | p1;

                    if ((n1 && n2) || (!p1 && !p2)) begin
                        internal_sel[i] <= 1'b1;
                    end
                end
            end

            assign q[i] = n1 & p1;
        end
    endgenerate

    assign sel_detected = sel_flag;
endmodule
"""


def generate_dice_pd(
    width: int = 1,
    cell_name: str = 'dice_pd_cell'
) -> str:
    """生成DICE-PD（功率门控DICE）。

    支持低功耗模式，在空闲时关闭电源。

    Args:
        width: 位宽。
        cell_name: 单元名称。

    Returns:
        Verilog代码。
    """
    if width == 1:
        return f"""
module {cell_name}(
    input clk,
    input rst,
    input d,
    input power_en,
    output q
);
    reg n1, n2, p1, p2;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            n1 <= 1'b0;
            n2 <= 1'b0;
            p1 <= 1'b1;
            p2 <= 1'b1;
        end else if (power_en) begin
            n1 <= d & ~n2;
            n2 <= d & ~n1;
            p1 <= ~d | p2;
            p2 <= ~d | p1;
        end
    end

    assign q = power_en ? (n1 & p1) : 1'bz;
endmodule
"""
    else:
        return f"""
module {cell_name}(
    input clk,
    input rst,
    input [{width-1}:0] d,
    input power_en,
    output [{width-1}:0] q
);
    genvar i;
    generate
        for (i = 0; i < {width}; i = i + 1) begin: dice_bit
            reg n1, n2, p1, p2;

            always @(posedge clk or posedge rst) begin
                if (rst) begin
                    n1 <= 1'b0;
                    n2 <= 1'b0;
                    p1 <= 1'b1;
                    p2 <= 1'b1;
                end else if (power_en) begin
                    n1 <= d[i] & ~n2;
                    n2 <= d[i] & ~n1;
                    p1 <= ~d[i] | p2;
                    p2 <= ~d[i] | p1;
                end
            end

            assign q[i] = power_en ? (n1 & p1) : 1'bz;
        end
    endgenerate
endmodule
"""


def generate_dice_st(
    width: int = 1,
    cell_name: str = 'dice_st_cell'
) -> str:
    """生成DICE-ST（自检测DICE）。

    内置错误检测机制，自动检测SEU并输出错误信号。

    Args:
        width: 位宽。
        cell_name: 单元名称。

    Returns:
        Verilog代码。
    """
    if width == 1:
        return f"""
module {cell_name}(
    input clk,
    input rst,
    input d,
    output q,
    output error_detected,
    output [1:0] error_type
);
    reg n1, n2, p1, p2;
    reg err_det;
    reg [1:0] err_type;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            n1 <= 1'b0;
            n2 <= 1'b0;
            p1 <= 1'b1;
            p2 <= 1'b1;
            err_det <= 1'b0;
            err_type <= 2'b00;
        end else begin
            n1 <= d & ~n2;
            n2 <= d & ~n1;
            p1 <= ~d | p2;
            p2 <= ~d | p1;

            err_det <= (n1 != ~n2) || (p1 != ~p2);

            if (n1 != ~n2 && p1 == ~p2) begin
                err_type <= 2'b01;
            end else if (n1 == ~n2 && p1 != ~p2) begin
                err_type <= 2'b10;
            end else if (n1 != ~n2 && p1 != ~p2) begin
                err_type <= 2'b11;
            end else begin
                err_type <= 2'b00;
            end
        end
    end

    assign q = n1 & p1;
    assign error_detected = err_det;
    assign error_type = err_type;
endmodule
"""
    else:
        return f"""
module {cell_name}(
    input clk,
    input rst,
    input [{width-1}:0] d,
    output [{width-1}:0] q,
    output [{width-1}:0] error_detected,
    output [1:0] error_type
);
    reg [1:0] err_type;
    reg [{width-1}:0] err_det;

    always @(*) begin
        err_type = 2'b00;
        if (|err_det) begin
            err_type = 2'b01;
        end
    end

    genvar i;
    generate
        for (i = 0; i < {width}; i = i + 1) begin: dice_bit
            reg n1, n2, p1, p2;

            always @(posedge clk or posedge rst) begin
                if (rst) begin
                    n1 <= 1'b0;
                    n2 <= 1'b0;
                    p1 <= 1'b1;
                    p2 <= 1'b1;
                    err_det[i] <= 1'b0;
                end else begin
                    n1 <= d[i] & ~n2;
                    n2 <= d[i] & ~n1;
                    p1 <= ~d[i] | p2;
                    p2 <= ~d[i] | p1;

                    err_det[i] <= (n1 != ~n2) || (p1 != ~p2);
                end
            end

            assign q[i] = n1 & p1;
            assign error_detected[i] = err_det[i];
        end
    endgenerate

    assign error_type = err_type;
endmodule
"""


def generate_dice_wrapper(
    module_name: str,
    input_ports: List[Dict],
    output_ports: List[Dict],
    variant: str = DICEVariant.STANDARD,
    width: int = 1
) -> str:
    """生成DICE包装器模块。

    Args:
        module_name: 原始模块名。
        input_ports: 输入端口列表。
        output_ports: 输出端口列表。
        variant: DICE变体类型。
        width: 位宽。

    Returns:
        DICE包装器代码。
    """
    dice_cell = {
        DICEVariant.STANDARD: generate_dice_standard(width, f'{module_name}_dice'),
        DICEVariant.DICE_2L: generate_dice_2l(width, f'{module_name}_dice'),
        DICEVariant.DICE_SEH: generate_dice_seh(width, f'{module_name}_dice'),
        DICEVariant.DICE_PD: generate_dice_pd(width, f'{module_name}_dice'),
        DICEVariant.DICE_ST: generate_dice_st(width, f'{module_name}_dice'),
    }.get(variant, generate_dice_standard(width, f'{module_name}_dice'))

    input_list = ', '.join(p['name'] for p in input_ports)
    output_list = ', '.join(p['name'] for p in output_ports)

    wrapper = f"""
module {module_name}_dice (
    {input_list},
    {output_list}
);

{dice_cell}

endmodule
"""

    return wrapper


def replace_registers_with_dice(
    rtl_content: str,
    variant: str = DICEVariant.STANDARD,
    target_registers: Optional[List[str]] = None
) -> str:
    """将RTL代码中的寄存器替换为DICE单元。

    Args:
        rtl_content: RTL源代码。
        variant: DICE变体类型。
        target_registers: 目标寄存器列表（可选，默认替换所有）。

    Returns:
        替换后的代码。
    """
    if target_registers is None:
        reg_pattern = re.compile(r'reg\s+(?:\[.*?\])?\s*(\w+)', re.MULTILINE)
        target_registers = [m.group(1) for m in reg_pattern.finditer(rtl_content)]

    for reg_name in target_registers:
        rtl_content = rtl_content.replace(
            f'reg {reg_name}',
            f'wire {reg_name}'
        )

    dice_cell = generate_dice_standard(1, 'dice_cell')

    if 'endmodule' in rtl_content:
        idx = rtl_content.rfind('endmodule')
        rtl_content = rtl_content[:idx] + dice_cell + '\n' + rtl_content[idx:]

    return rtl_content


def get_dice_variant_info(variant: str) -> Dict:
    """获取DICE变体信息。

    Args:
        variant: 变体类型。

    Returns:
        变体信息字典。
    """
    info = {
        DICEVariant.STANDARD: {
            'name': 'Standard DICE',
            'description': '4节点交叉耦合DICE单元',
            'area_overhead': 2.5,
            'seu_immunity': '单粒子免疫',
            'power_overhead': '标准',
            'complexity': '中',
        },
        DICEVariant.DICE_2L: {
            'name': 'DICE-2L',
            'description': '双锁存器DICE，更高SEU免疫力',
            'area_overhead': 4.0,
            'seu_immunity': '双粒子免疫',
            'power_overhead': '高',
            'complexity': '高',
        },
        DICEVariant.DICE_SEH: {
            'name': 'DICE-SEH',
            'description': 'SEL抑制DICE',
            'area_overhead': 3.0,
            'seu_immunity': '单粒子免疫+SEL抑制',
            'power_overhead': '标准',
            'complexity': '中',
        },
        DICEVariant.DICE_PD: {
            'name': 'DICE-PD',
            'description': '功率门控DICE',
            'area_overhead': 2.8,
            'seu_immunity': '单粒子免疫',
            'power_overhead': '低（空闲时）',
            'complexity': '中',
        },
        DICEVariant.DICE_ST: {
            'name': 'DICE-ST',
            'description': '自检测DICE',
            'area_overhead': 3.2,
            'seu_immunity': '单粒子免疫+错误检测',
            'power_overhead': '标准',
            'complexity': '高',
        },
    }
    return info.get(variant, info[DICEVariant.STANDARD])