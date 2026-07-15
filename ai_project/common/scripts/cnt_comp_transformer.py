#!/usr/bin/env python3
"""
cnt_comp_transformer.py — 计数器比较器加固的 AST 变换引擎

功能:
1. 在 AST 中检测计数器模式 (递增/递减/模)
2. 将计数器替换为 cnt_comp 加固版本
3. 注入错误信号和错误计数器

计数器模式检测规则:
- 递增: reg <= reg + 1    (在 always_ff 中)
- 递减: reg <= reg - 1    (在 always_ff 中)
- 模:   if (reg == MAX) reg <= 0 else reg <= reg + 1

依赖: pyverilog
"""

import re
import pyverilog.vparser.ast as vast

# AstModifier 在 pyverilog 1.3.0 中不可用, 仅变换演示需要
try:
    from pyverilog.ast_modifier import AstModifier
    _HAVE_AST_MODIFIER = True
except ImportError:
    _HAVE_AST_MODIFIER = False


class CounterDetector:
    """检测 AST 中的计数器模式"""
    
    # 计数器类型枚举
    UP_COUNTER   = "up_counter"
    DOWN_COUNTER = "down_counter" 
    MOD_COUNTER  = "mod_counter"
    
    @staticmethod
    def detect(sens_list, statement):
        """检测 always_ff 块中是否是计数器模式
        
        Args:
            sens_list: 敏感列表 (always @(posedge clk ...))
            statement: always 块体
            
        Returns:
            {signal_name: counter_type} 或 {}
        """
        results = {}
        
        # 检测是否为时序逻辑 (posedge/negedge)
        if not CounterDetector._is_edge_triggered(sens_list):
            return results
        
        # 解析 always 块体
        if isinstance(statement, vast.Block):
            for stmt in statement.statements:
                if isinstance(stmt, vast.NonblockingSubstitution):
                    # 解析非阻塞赋值 reg <= value
                    lhs = stmt.left
                    rhs = stmt.right
                    
                    if isinstance(lhs, vast.Identifier):
                        signal = lhs.name
                        pattern = CounterDetector._match_counter_pattern(rhs)
                        if pattern:
                            results[signal] = pattern
        
        return results
    
    @staticmethod
    def _is_edge_triggered(sens_list):
        """检查敏感列表是否为 posedge/negedge"""
        if isinstance(sens_list, vast.SensList):
            for sens in sens_list.list:
                if isinstance(sens, vast.Sens) and sens.type in ('posedge', 'negedge'):
                    return True
        return False
    
    @staticmethod
    def _match_counter_pattern(rhs):
        """匹配计数器赋值模式
        
        Returns:
            counter_type or None
        """
        # 模式 1: reg <= reg + 1 (递增)
        if isinstance(rhs, vast.Plus):
            left = rhs.left
            right = rhs.right
            if (isinstance(left, vast.Identifier) and 
                isinstance(right, vast.IntConst) and right.value == '1'):
                return CounterDetector.UP_COUNTER
        
        # 模式 2: reg <= reg - 1 (递减)
        if isinstance(rhs, vast.Minus):
            left = rhs.left
            right = rhs.right
            if (isinstance(left, vast.Identifier) and 
                isinstance(right, vast.IntConst) and right.value == '1'):
                return CounterDetector.DOWN_COUNTER
        
        # 模式 3: 模计数器 (通过 if/else 匹配)
        if isinstance(rhs, vast.Cond):
            # if (reg == MAX) reg <= 0 else reg <= reg + 1
            cond = rhs.cond
            true_val = rhs.true_value
            false_val = rhs.false_value
            
            if (isinstance(true_val, vast.IntConst) and true_val.value == '0' and
                isinstance(cond, vast.Eq)):
                left_cond = cond.left
                if isinstance(left_cond, vast.Identifier):
                    # 进一步检查模式
                    return CounterDetector.MOD_COUNTER
        
        return None


class CounterTransform:
    """计数器 cnt_comp 变换"""
    
    @staticmethod
    def transform(ast, counters):
        """对检测到的计数器应用 cnt_comp 加固
        
        Args:
            ast: pyverilog AST
            counters: {signal_name: counter_type} (来自 CounterDetector)
            
        Returns:
            修改后的 AST
        """
        modifier = AstModifier()
        
        for signal_name, ctype in counters.items():
            # 1. 替换信号声明: reg [W-1:0] signal -> wire [W-1:0] signal;
            # 2. 添加影子寄存器: reg [W-1:0] shadow_signal;
            # 3. 添加错误标志:    wire signal_error_flag;
            # 4. 添加错误计数器: reg [CW-1:0] signal_error_count;
            # 5. 替换 always 块体为 cnt_comp 版本
            
            # 具体实现取决于 pyverilog 版本
            # 这里提供伪代码逻辑:
            modifier.remove_stmt(f"always_ff @(posedge clk) {signal_name} <= ...")
            modifier.insert_after(f"reg [31:0] {signal_name};", 
                                  f"reg [31:0] shadow_{signal_name};")
            modifier.insert_after(f"reg [31:0] {signal_name};",
                                  f"wire {signal_name}_error_flag;")
            
        return modifier


# 使用示例
if __name__ == "__main__":
    import pyverilog
    
    # 解析 Verilog 文件
    ast, _ = pyverilog.parse.parse(
        ["test_mock_data/counter_example.v"],
        preprocess_include=[],
        preprocess_define=[]
    )
    
    # 检测计数器
    counters = {}
    for module in ast.children():
        for item in module.items:
            if isinstance(item, vast.Always):
                detected = CounterDetector.detect(item.sens_list, item.statement)
                counters.update(detected)
    
    print(f"检测到 {len(counters)} 个计数器: {counters}")
    
    # 变换
    new_ast = CounterTransform.transform(ast, counters)
    
    # 输出
    from pyverilog.codegen.codegen import CodeGen
    codegen = CodeGen()
    codegen.visit(new_ast)
    with open("test_mock_data/counter_hardened.v", "w") as f:
        f.write(codegen.text)
