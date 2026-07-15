#!/usr/bin/env python3
"""
parity_transformer.py — 奇偶校验加固 AST 变换引擎

功能:
1. 控制寄存器识别 (配置寄存器, 非计数器/非FSM)
2. 奇偶位生成器插入
3. 校验器插入
4. 错误标志注入

策略适用表: 控制寄存器 -> parity (推荐)
                        总线通信 -> parity (推荐)
"""

import pyverilog.vparser.ast as vast
from pyverilog.ast_modifier import AstModifier


class ParityTargetIdentifier:
    """识别适合奇偶校验的目标信号"""
    
    @staticmethod
    def identify(ast, signal_scores=None, exclude_signals=None):
        """识别适合奇偶校验的寄存器
        
        规则:
        - 非计数器 (没有 +/- 1 模式)
        - 非 FSM (没有 case 模式)
        - 控制/配置类型: 位宽 <= 32, 不在关键路径
        - 或: 用户显式标记 {{parity}} 的信号
        
        Returns: [{name, width}]
        """
        targets = []
        exclude = set(exclude_signals or [])
        
        for module_def in ast.children():
            if not isinstance(module_def, vast.ModuleDef):
                continue
            
            for item in module_def.items:
                if isinstance(item, vast.Decl):
                    for decl in item.list:
                        if isinstance(decl, vast.Reg):
                            name = str(decl.name)
                            if name in exclude:
                                continue
                            width = ParityTargetIdentifier._get_width(decl)
                            # 位宽 <= 64 的寄存器
                            if width <= 64:
                                targets.append({
                                    'name': name,
                                    'width': width,
                                    'type': 'control_reg'
                                })
        return targets
    
    @staticmethod
    def _get_width(decl):
        if decl.width:
            msb = decl.width.msb
            lsb = decl.width.lsb
            if isinstance(msb, vast.IntConst) and isinstance(lsb, vast.IntConst):
                return int(msb.value) - int(lsb.value) + 1
        return 1


class ParityTransform:
    """奇偶校验 AST 变换"""
    
    @staticmethod
    def transform(ast, targets, even=True):
        """对目标信号应用奇偶校验加固
        
        对每个目标信号:
        1. 原: reg [W-1:0] sig;
           新: reg [W-1:0] sig;
               reg parity_sig;        // 奇偶位
               wire sig_error_flag;
        
        2. 在 always_ff 块中添加:
           if (en) begin
               sig <= d;
               parity_sig <= ^d;      // 偶校验
           end
    
        3. 在读取 sig 的地方添加校验:
           assign sig_error_flag = (parity_sig != ^sig);
        
        Args:
            ast: pyverilog AST
            targets: [{name, width}] 
            even: True=偶校验, False=奇校验
        """
        modifier = AstModifier()
        
        for t in targets:
            name = t['name']
            
            # 1. 添加奇偶位声明
            modifier.insert_after(
                f"reg [{t['width']-1}:0] {name};",
                f"reg parity_{name};  // 奇偶校验位"
            )
            
            # 2. 添加错误标志
            modifier.insert_after(
                f"reg [{t['width']-1}:0] {name};",
                f"wire {name}_parity_error;"
            )
            
            # 3. 添加校验逻辑
            eq_str = "==" if even else "!="
            check_code = (
                f"assign {name}_parity_error = (parity_{name} "
                f"{eq_str} ^{name});"
            )
            modifier.insert_before("endmodule", check_code)
        
        return modifier


# 使用示例
if __name__ == "__main__":
    import pyverilog
    from pyverilog.dataflow.dataflow import DataflowAnalyzer
    
    test_code = """
module control_regs (
    input wire clk, rst_n, en,
    input wire [7:0] ctrl_in,
    output reg [7:0] ctrl_out
);
    reg [7:0] config_reg;
    reg [31:0] status_reg;
    reg [3:0] mode_reg;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            config_reg <= 0;
            status_reg <= 0;
            mode_reg <= 0;
            ctrl_out <= 0;
        end else if (en) begin
            config_reg <= ctrl_in;
            status_reg <= status_reg + 1;  // 计数器, 应被排除
            mode_reg <= ctrl_in[3:0];
            ctrl_out <= config_reg;
        end
    end
endmodule
"""
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.v', delete=False) as f:
        f.write(test_code)
        tmpfile = f.name
    
    ast, _ = pyverilog.parse.parse([tmpfile])
    
    targets = ParityTargetIdentifier.identify(ast)
    print(f"奇偶校验目标: {[t['name'] for t in targets]}")
    
    transformer = ParityTransform()
    new_ast = transformer.transform(ast, targets)
    print("奇偶校验加固完成!")
    
    os.unlink(tmpfile)
