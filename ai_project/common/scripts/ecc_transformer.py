#!/usr/bin/env python3
"""
ecc_transformer.py — ECC (SECDED) 加固 AST 变换引擎

功能:
1. 数据总线 / 存储器信号识别 (适合 ECC 保护的信号)
2. ECC 编码器/解码器实例替换代码生成
3. 使用 ecc_template.v 模板作为底层硬件模块

策略适用表:
  宽数据总线 (>=16bit)   -> ecc_bus (推荐)
  存储器阵列             -> ecc_register (推荐)
  高扇出数据路径         -> ecc_bus (推荐)
"""

import pyverilog.vparser.ast as vast

try:
    from pyverilog.ast_modifier import AstModifier
    _HAVE_AST_MODIFIER = True
except ImportError:
    _HAVE_AST_MODIFIER = False


class EccTargetIdentifier:
    """识别适合 ECC (SECDED) 保护的目标信号"""

    # 默认阈值
    DEFAULT_WIDTH_THRESHOLD = 16   # 宽数据总线位宽阈值
    DEFAULT_MEMORY_THRESHOLD = 4   # 存储器阵列深度阈值

    @staticmethod
    def identify(ast, signal_scores=None, exclude_signals=None,
                 width_threshold=None, memory_threshold=None):
        """识别适合 ECC 保护的信号

        规则:
        - 宽数据总线: 位宽 >= width_threshold (默认 16)
        - 存储器阵列: reg [W-1:0] mem [N-1:0], N >= memory_threshold (默认 4)
        - 高扇出数据路径: 根据 signal_scores 判定
        - 或: 用户显式标记 {{ecc}} 的信号

        Args:
            ast:            pyverilog AST
            signal_scores:  {signal_name: score}, 用于扇出分析
            exclude_signals: set, 要排除的信号名
            width_threshold:  int, 宽总线阈值
            memory_threshold: int, 存储器深度阈值

        Returns:
            [{name, width, depth, signal_type, protection_module}]
        """
        targets = []
        exclude = set(exclude_signals or [])
        wt = width_threshold or EccTargetIdentifier.DEFAULT_WIDTH_THRESHOLD
        mt = memory_threshold or EccTargetIdentifier.DEFAULT_MEMORY_THRESHOLD

        for module_def in ast.children():
            if not isinstance(module_def, vast.ModuleDef):
                continue

            for item in module_def.items:
                if isinstance(item, vast.Decl):
                    for decl in item.list:
                        name = str(decl.name) if hasattr(decl, 'name') else ''
                        if not name or name in exclude:
                            continue

                        # 检测存储器阵列: reg [W-1:0] mem [N-1:0]
                        if hasattr(decl, 'array') and decl.array:
                            mem_info = EccTargetIdentifier._analyze_memory(decl)
                            if mem_info and mem_info['depth'] >= mt:
                                targets.append({
                                    'name': name,
                                    'width': mem_info['width'],
                                    'depth': mem_info['depth'],
                                    'signal_type': 'memory_array',
                                    'protection_module': 'ecc_register',
                                })
                            continue

                        # 检测宽数据总线 / 寄存器
                        if isinstance(decl, (vast.Reg, vast.Wire)):
                            width = EccTargetIdentifier._get_width(decl)
                            if width >= wt:
                                targets.append({
                                    'name': name,
                                    'width': width,
                                    'depth': 1,
                                    'signal_type': 'data_bus',
                                    'protection_module': 'ecc_bus',
                                })

        # 高扇出数据路径检测 (基于 signal_scores)
        if signal_scores:
            existing_names = {t['name'] for t in targets}
            for sig_name, score in signal_scores.items():
                if sig_name not in existing_names and sig_name not in exclude:
                    if score > 5:  # 扇出阈值
                        targets.append({
                            'name': sig_name,
                            'width': EccTargetIdentifier._infer_width_by_score(score),
                            'depth': 1,
                            'signal_type': 'high_fanout',
                            'protection_module': 'ecc_bus',
                        })

        return targets

    @staticmethod
    def _analyze_memory(decl):
        """分析存储器阵列声明

        reg [W-1:0] mem [N-1:0] -> {'width': W, 'depth': N}
        """
        if not hasattr(decl, 'array') or not decl.array:
            return None
        width = EccTargetIdentifier._get_width(decl) or 1
        depth = 1
        array = decl.array
        if hasattr(array, 'msb') and hasattr(array, 'lsb'):
            msb = array.msb
            lsb = array.lsb
            if isinstance(msb, vast.IntConst) and isinstance(lsb, vast.IntConst):
                depth = int(msb.value) - int(lsb.value) + 1
        return {'width': width, 'depth': depth}

    @staticmethod
    def _get_width(decl):
        """提取信号位宽"""
        if hasattr(decl, 'width') and decl.width:
            msb = decl.width.msb
            lsb = decl.width.lsb
            if isinstance(msb, vast.IntConst) and isinstance(lsb, vast.IntConst):
                return int(msb.value) - int(lsb.value) + 1
        return 1

    @staticmethod
    def _infer_width_by_score(score):
        """根据扇出分数推断位宽"""
        if score > 20:
            return 64
        elif score > 10:
            return 32
        return 16

    @staticmethod
    def _is_ecc_annotated(decl):
        """检查是否包含 {{ecc}} 注释标记"""
        if hasattr(decl, 'annotations'):
            for ann in decl.annotations:
                if 'ecc' in str(ann).lower():
                    return True
        return False


class EccTransform:
    """ECC 加固 AST 变换

    生成 ECC 编码器/解码器实例替换代码，
    使用 ecc_template.v 中的模块:
      - ecc_encoder:   ECC 编码器
      - ecc_decoder:   ECC 解码器 (SEC + DED)
      - ecc_register:  带 ECC 保护的寄存器
      - ecc_bus:       总线 ECC 保护
    """

    ECC_TEMPLATE_PATH = "test_mock_data/ecc_template.v"

    @staticmethod
    def transform(ast, targets, template_path=None):
        """对目标信号应用 ECC 加固

        为每个目标信号生成 Verilog 替换代码，
        用 ECC 保护版本替换原始寄存器/总线声明。

        Args:
            ast:           pyverilog AST
            targets:       [{name, width, signal_type, protection_module}]
            template_path: ecc_template.v 路径

        Returns:
            修改后的 AST (AstModifier)
        """
        modifier = AstModifier()

        for t in targets:
            name = t['name']
            width = t['width']
            pmod = t['protection_module']

            replacement_code = EccTransform._generate_ecc_replacement(
                name, width, pmod, template_path
            )

            modifier.insert_before("endmodule", replacement_code)

        return modifier

    @staticmethod
    def generate_replacement_guide(targets, template_path=None):
        """生成 ECC 替换指南 (文本描述)

        不依赖 pyverilog AST，直接输出 Verilog 替换代码块。
        适用于手动集成或文档生成。

        Args:
            targets:       [{name, width, signal_type, protection_module}]
            template_path: ecc_template.v 路径

        Returns:
            str: Verilog 替换代码
        """
        tpl_path = template_path or EccTransform.ECC_TEMPLATE_PATH
        lines = []
        lines.append("// ====================================================")
        lines.append("// ECC (SECDED) 加固替换指南")
        lines.append(f"// 模板文件: {tpl_path}")
        lines.append("// ====================================================")
        lines.append("")
        lines.append(f"`include \"{tpl_path}\"")
        lines.append("")

        for t in targets:
            name = t['name']
            width = t['width']
            pmod = t['protection_module']
            sig_type = t.get('signal_type', 'unknown')

            lines.append(f"// ---- {name} ({sig_type}, width={width}) ----")
            code = EccTransform._generate_ecc_replacement(
                name, width, pmod, tpl_path
            )
            lines.append(code)
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _generate_ecc_replacement(name, width, protection_module,
                                  template_path=None):
        """生成单个信号的 ECC 替换代码"""

        if protection_module == 'ecc_register':
            return f"""// 原始: reg [{width-1}:0] {name};
// 替换: 使用带 ECC 保护的寄存器
reg [{width-1}:0] {name};
wire {name}_error_flag;
wire {name}_corrected;
ecc_register #(
    .WIDTH({width})
) u_ecc_{name} (
    .clk         (clk),
    .rst_n       (rst_n),
    .en          (en),
    .d           ({name}_d),
    .q           ({name}),
    .error_flag  ({name}_error_flag),
    .corrected   ({name}_corrected)
);"""

        elif protection_module == 'ecc_bus':
            return f"""// 原始: wire/reg [{width-1}:0] {name};
// 替换: 使用 ECC 保护的总线
wire [{width-1}:0] {name};
wire {name}_error_flag;
wire {name}_corrected;
ecc_bus #(
    .WIDTH({width})
) u_ecc_{name} (
    .clk         (clk),
    .rst_n       (rst_n),
    .data_in     ({name}_in),
    .data_out    ({name}),
    .error_flag  ({name}_error_flag),
    .corrected   ({name}_corrected)
);"""

        else:
            cw = EccTransform._calc_codeword_width(width)
            return f"""// 原始: {name} (ECC 保护, 自动选择模块)
// 使用 ecc_encoder/ecc_decoder 直接保护
wire [{cw}:0] {name}_codeword;
ecc_encoder #(
    .WIDTH({width})
) u_enc_{name} (
    .data     ({name}),
    .codeword ({name}_codeword)
);
ecc_decoder #(
    .WIDTH({width})
) u_dec_{name} (
    .codeword      ({name}_codeword),
    .data_corrected({name}_corrected),
    .single_error  ({name}_corrected_flag),
    .double_error  ({name}_error_flag)
);"""

    @staticmethod
    def _calc_codeword_width(width):
        """计算 ECC 码字总宽度: WIDTH + P + GP - 1 (0-indexed)"""
        p = max(1, (width - 1).bit_length())  # clog2(WIDTH)
        gp = 1
        return width + p + gp - 1


# ====================================================
# 使用示例
# ====================================================
if __name__ == "__main__":
    import pyverilog

    test_code = """
module ecc_targets (
    input wire clk, rst_n, en,
    input wire [15:0] data_in,
    output reg [15:0] data_out
);
    // 宽数据总线 (>=16bit)
    reg [31:0] config_word;
    reg [15:0] status_word;

    // 存储器阵列
    reg [7:0] mem_array [0:15];
    reg [31:0] large_mem [0:63];

    // 窄信号 (不需要ECC)
    reg [3:0] small_reg;
    reg [7:0] ctrl_byte;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            config_word <= 0;
            status_word <= 0;
            small_reg <= 0;
            ctrl_byte <= 0;
            data_out <= 0;
        end else if (en) begin
            config_word <= data_in;
            status_word <= status_word + 1;
            small_reg <= data_in[3:0];
            ctrl_byte <= data_in[7:0];
            data_out <= config_word;
        end
    end
endmodule
"""
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.v', delete=False) as f:
        f.write(test_code)
        tmpfile = f.name

    ast, _ = pyverilog.parse.parse([tmpfile])

    # 识别 ECC 目标
    targets = EccTargetIdentifier.identify(ast)
    print(f"ECC 保护目标 ({len(targets)}):")
    for t in targets:
        print(f"  - {t['name']}: width={t['width']}, "
              f"type={t['signal_type']}, module={t['protection_module']}")

    # 生成替换指南
    if _HAVE_AST_MODIFIER:
        guide = EccTransform.generate_replacement_guide(targets)
        print(f"\nECC 替换指南:\n{guide}")
    else:
        print("\nECC 替换指南生成跳过: pyverilog AstModifier 不可用")

    os.unlink(tmpfile)
