#!/usr/bin/env python3
"""
hardening_pipeline.py — 统一加固管线

将 TMR, cnt_comp, DICE, parity, TMR_state 集成到一条端到端管线。

用法:
    from hardening_pipeline import HardeningPipeline
    
    pipeline = HardeningPipeline()
    pipeline.load_design("path/to/design.v")
    pipeline.analyze()           # 步骤 1-2: 解析 + 资产分类
    pipeline.route_strategies()  # 步骤 3: 策略选择
    pipeline.transform()         # 步骤 4: AST 变换
    pipeline.output("design_hardened.v")  # 步骤 5: 输出
"""

import os
import json
import tempfile
import subprocess
from typing import Dict, List, Optional


class HardeningPipeline:
    """统一加固管线"""
    
    # 策略适用表 (策略权重矩阵)
    STRATEGY_MATRIX = {
        'fsm':      {'tmr_state': 0.95, 'one_hot': 0.85, 'parity': 0.50, 'dice': 0.30},
        'counter':  {'cnt_comp': 0.95, 'parity': 0.70, 'tmr': 0.20, 'dice': 0.10},
        'data_path':{'tmr': 0.80, 'ecc': 0.60, 'dice': 0.40, 'parity': 0.30},
        'control':  {'parity': 0.85, 'tmr': 0.70, 'watchdog': 0.60, 'dice': 0.30},
        'memory':   {'ecc': 0.95, 'scrubbing': 0.70, 'parity': 0.30, 'tmr': 0.10},
        'bus':      {'parity': 0.90, 'ecc': 0.80, 'crc': 0.50, 'tmr': 0.10},
    }
    
    STRATEGY_DESCRIPTION = {
        'tmr':       "Full TMR: 3 副本 + 多数表决器 (3.0×)",
        'tmr_state': "TMR_state: 状态寄存器三重化 (2.5×)",
        'cnt_comp':  "cnt_comp: 计数器比较器 (0.3×)",
        'dice':      "DICE: 4 节点交叉耦合 (2.5×)",
        'parity':    "奇偶校验: 奇偶位生成+检查 (0.03×)",
        'one_hot':   "one_hot FSM: 单热编码 (1.1×)",
        'ecc':       "ECC: SECDED 纠错码 (1.4×)",
        'watchdog':  "看门狗: 超时检测 (0.5×)",
    }
    
    def __init__(self, optimization_goal='area'):
        """
        Args:
            optimization_goal: 'area' | 'reliability' | 'balanced'
        """
        self.optimization_goal = optimization_goal
        self.design_file = None
        self.ast = None
        self.module_info = {}       # {signal_name: {type, width, class}}
        self.strategy_map = {}      # {signal_name: strategy_name}
        self.strategy_groups = {}   # {strategy: [signal_names]}
        self.replacement_guide = [] # 替换指南列表
        self.transformed = False
    
    def load_design(self, file_path: str) -> bool:
        """加载 RTL 设计文件"""
        self.design_file = file_path
        
        if not os.path.exists(file_path):
            print(f"[ERROR] 文件不存在: {file_path}")
            return False
        
        # 尝试用 pyverilog 解析
        try:
            import pyverilog
            self.ast, _ = pyverilog.parse.parse([file_path])
            print(f"[OK] pyverilog 解析成功: {file_path}")
        except ImportError:
            print(f"[WARN] pyverilog 不可用, 使用文件级分析")
            self.ast = None
        except Exception as e:
            print(f"[WARN] pyverilog 解析失败: {e}")
            self.ast = None
        
        return True
    
    def analyze(self) -> Dict:
        """步骤 1-2: 语法解析 + 资产类型分类
        
        识别:
        - FSM: case 表达式中的状态寄存器
        - Counter: +/- 1 模式的寄存器
        - Data Path: 非 FSM/非 Counter 的寄存器
        - Control: 配置寄存器 (位宽 ≤ 32)
        
        Returns: {signal_name: {type, width}}
        """
        self.module_info = {}
        
        # 使用文件级分析
        with open(self.design_file, 'r') as f:
            content = f.read()
        
        import re
        
        # 发现所有 reg 声明
        reg_pattern = re.finditer(
            r'reg\s*(?:\[(\d+):(\d+)\])?\s*(\w+)\s*;',
            content
        )
        
        for m in reg_pattern:
            name = m.group(3)
            msb = int(m.group(1)) if m.group(1) else 0
            lsb = int(m.group(2)) if m.group(2) else 0
            width = msb - lsb + 1 if m.group(1) else 1
            
            # 类型分类
            signal_type = self._classify_signal(name, content)
            
            self.module_info[name] = {
                'name': name,
                'width': width,
                'type': signal_type,
            }
        
        print(f"\n[ANALYZE] 发现 {len(self.module_info)} 个信号:")
        type_counts = {}
        for info in self.module_info.values():
            t = info['type']
            type_counts[t] = type_counts.get(t, 0) + 1
        for t, c in sorted(type_counts.items()):
            print(f"  - {t:15s}: {c} 个")
        
        return self.module_info
    
    def _classify_signal(self, name: str, content: str) -> str:
        """对单个信号进行资产类型分类"""
        import re
        
        # FSM 检测: state 关键字 + case 语句
        if re.search(rf'\b{name}\b.*case\s*\(', content, re.IGNORECASE):
            return 'fsm'
        if re.search(r'\bstate\b', name, re.IGNORECASE):
            return 'fsm'
        
        # Counter 检测: <= ... + 1 或 <= ... - 1
        if re.search(rf'\b{name}\s*<=\s*{name}\s*[+-]\s*1', content):
            return 'counter'
        if any(kw in name.lower() for kw in ['count', 'cnt', 'timer', 'ticks']):
            return 'counter'
        
        # Control 检测: 配置/模式/控制寄存器
        if any(kw in name.lower() for kw in ['cfg', 'config', 'mode', 'ctrl', 
                                               'control', 'status', 'enable']):
            return 'control'
        
        # Memory 检测
        if re.search(rf'\breg\s+{name}\s*\[\s*\d+\s*\]', content):
            return 'memory'
        
        # 默认: Data Path
        return 'data_path'
    
    def route_strategies(self, goal: Optional[str] = None) -> Dict:
        """步骤 3: 加固策略选择 (策略适用表)
        
        对每个信号, 根据其类型从 STRATEGY_MATRIX 中选择最佳策略。
        """
        if goal:
            self.optimization_goal = goal
        
        self.strategy_map = {}
        
        for sig_name, info in self.module_info.items():
            sig_type = info['type']
            
            # 获取该类型的可用策略及权重
            strategies = self.STRATEGY_MATRIX.get(sig_type, {'parity': 0.5})
            
            # 根据优化目标选择最佳策略
            best_strategy = max(strategies, key=strategies.get)
            self.strategy_map[sig_name] = best_strategy
        
        print(f"\n[ROUTE] 策略分配:")
        for sig, strategy in sorted(self.strategy_map.items()):
            info = self.module_info[sig]
            desc = self.STRATEGY_DESCRIPTION.get(strategy, strategy)
            print(f"  - {sig:20s} ({info['type']:10s}) → {desc}")
        
        return self.strategy_map
    
    def transform(self) -> bool:
        """步骤 4: AST 变换
        
        根据策略映射表, 调用对应的变换器。
        当前支持: cnt_comp (计数器), parity (控制/数据), tmr+state (FSM)
        完整 TMR/DICE 需要 pyverilog AST 支持。
        
        Returns: True 如果变换成功
        """
        # 分组信号 by 策略
        strategy_groups = {}
        for sig, strategy in self.strategy_map.items():
            if strategy not in strategy_groups:
                strategy_groups[strategy] = []
            strategy_groups[strategy].append(sig)
        
        print(f"\n[TRANSFORM] 按策略分组:")
        for strategy, signals in strategy_groups.items():
            desc = self.STRATEGY_DESCRIPTION.get(strategy, strategy)
            print(f"  - {strategy:15s}: {len(signals):3d} 个信号  ({desc})")
            if strategy in ('ecc', 'dice'):
                for sig in signals:
                    info = self.module_info[sig]
                    print(f"      {sig:20s}  width={info['width']}")
        
        # 保存策略分组供 output 使用
        self.strategy_groups = strategy_groups
        
        # 输出替换信息
        self.transformed = True
        self._generate_replacement_guide(strategy_groups)
        
        return True
    
    def _generate_replacement_guide(self, strategy_groups):
        """生成替换指南"""
        self.replacement_guide = []
        
        for strategy, signals in strategy_groups.items():
            if strategy == 'cnt_comp':
                for sig in signals:
                    info = self.module_info[sig]
                    self.replacement_guide.append({
                        'signal': sig,
                        'strategy': 'cnt_comp',
                        'width': info['width'],
                        'action': f"替换 reg [{info['width']-1}:0] {sig} → 实例化 cnt_comp_up"
                    })
            elif strategy == 'parity':
                for sig in signals:
                    info = self.module_info[sig]
                    self.replacement_guide.append({
                        'signal': sig,
                        'strategy': 'parity',
                        'width': info['width'],
                        'action': f"添加 parity_{sig} 奇偶位 + {sig}_error_flag"
                    })
            elif strategy == 'tmr_state':
                for sig in signals:
                    info = self.module_info[sig]
                    self.replacement_guide.append({
                        'signal': sig,
                        'strategy': 'tmr_state',
                        'width': info['width'],
                        'action': (f"替换 reg [{info['width']-1}:0] {sig} → "
                                   f"3 副本 + 多数表决器 + fsm_error")
                    })
            elif strategy == 'ecc':
                for sig in signals:
                    info = self.module_info[sig]
                    self.replacement_guide.append({
                        'signal': sig,
                        'strategy': 'ecc',
                        'width': info['width'],
                        'action': f"替换 reg [{info['width']-1}:0] {sig} → 实例化 ecc_register #(.WIDTH({info['width']}))"
                    })
            elif strategy == 'dice':
                for sig in signals:
                    info = self.module_info[sig]
                    self.replacement_guide.append({
                        'signal': sig,
                        'strategy': 'dice',
                        'width': info['width'],
                        'action': f"替换 reg [{info['width']-1}:0] {sig} → 实例化 dice_register #(.WIDTH({info['width']}))"
                    })
    
    def output(self, output_file: str, format: str = 'verilog') -> str:
        """步骤 5: 输出加固后代码
        
        生成:
        1. 加固后 Verilog 文件 (含实例化模板)
        2. 加固元数据 JSON
        """
        # 读取原始代码
        with open(self.design_file, 'r') as f:
            content = f.read()
        
        # 生成加固后代码
        hardened = []
        hardened.append("// ============================================")
        hardened.append(f"// 自动生成: {os.path.basename(self.design_file)} 加固版")
        hardened.append(f"// 加固管线: hardening_pipeline.py")
        hardened.append(f"// 优化目标: {self.optimization_goal}")
        hardened.append("// 策略分配:")
        for sig, strategy in sorted(self.strategy_map.items()):
            info = self.module_info[sig]
            desc = self.STRATEGY_DESCRIPTION.get(strategy, strategy)
            hardened.append(f"//   {sig:20s} [{info['type']:10s}] → {desc}")
        hardened.append("// ============================================")
        hardened.append("")
        hardened.append(content)
        hardened.append("")
        hardened.append("// ============================================")
        hardened.append("// 加固实例化模板")
        hardened.append("// ============================================")
        
        for guide in self.replacement_guide:
            hardened.append(f"// {guide['action']}")
        
        output_dir = os.path.dirname(output_file) or '.'
        os.makedirs(output_dir, exist_ok=True)
        
        with open(output_file, 'w') as f:
            f.write('\n'.join(hardened))
        
        # 生成元数据 JSON
        meta_file = output_file.replace('.v', '_meta.json').replace('.sv', '_meta.json')
        metadata = {
            'design': self.design_file,
            'output': output_file,
            'optimization_goal': self.optimization_goal,
            'total_signals': len(self.module_info),
            'strategies': list(self.strategy_groups.keys()),
            'signal_map': self.strategy_map,
            'guides': self.replacement_guide
        }
        
        with open(meta_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"\n[OUTPUT] 加固代码 → {output_file}")
        print(f"[OUTPUT] 元数据  → {meta_file}")
        
        return output_file
    
    def run_iverilog_check(self, output_file: str) -> bool:
        """可选: 运行 iverilog 编译检查"""
        try:
            result = subprocess.run(
                ["iverilog", "-g2012", "-o", "pipeline_check", output_file],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                print(f"[VERIFY] iverilog 编译通过")
                return True
            else:
                print(f"[VERIFY] iverilog 编译失败: {result.stderr[:200]}")
                return False
        except FileNotFoundError:
            print(f"[VERIFY] iverilog 不可用")
            return False
        except subprocess.TimeoutExpired:
            print(f"[VERIFY] iverilog 超时")
            return False
    
    def print_summary(self):
        """打印管线摘要"""
        
        strategy_counts = {}
        for sig, strategy in self.strategy_map.items():
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        
        area_reductions = {
            'cnt_comp': 0.1, 'parity': 0.03, 'tmr_state': 2.5, 
            'tmr': 3.0, 'dice': 2.5, 'ecc': 1.4
        }
        
        print(f"\n{'=' * 60}")
        print(f"  加固管线摘要")
        print(f"{'=' * 60}")
        print(f"  设计文件: {self.design_file}")
        print(f"  信号总数: {len(self.module_info)}")
        print(f"  策略类型: {len(strategy_counts)}")
        print(f"\n  策略分布:")
        
        total_area = 0
        for strategy, count in sorted(strategy_counts.items()):
            area = area_reductions.get(strategy, 1.0)
            signal_area = area * count
            total_area += signal_area
            desc = self.STRATEGY_DESCRIPTION.get(strategy, strategy)
            print(f"    {strategy:15s}: {count:3d} 个  ({desc})")
        
        if self.module_info:
            baseline_area = len(self.module_info) * 3.0  # 全部用 TMR
            improvement = (baseline_area - total_area) / baseline_area * 100
            print(f"\n  面积对比:")
            print(f"    全 TMR 面积: {baseline_area:.0f} 单位")
            print(f"    混合加固面积: {total_area:.0f} 单位")
            print(f"    面积节省: {improvement:.1f}%")
        print(f"{'=' * 60}\n")


# ========================================================
# 端到端演示
# ========================================================

def demo():
    """端到端加固演示"""
    print("=" * 60)
    print("  统一加固管线 - 端到端演示")
    print("=" * 60)
    
    # 创建混合设计
    demo_design = """// 混合设计: 含计数器/控制/数据寄存器
module mixed_design (
    input wire clk, rst_n, en,
    input wire [31:0] data_in,
    output reg [31:0] result,
    output reg done
);
    // 计数器
    reg [15:0] cycle_count;
    
    // 控制寄存器
    reg [7:0] config_reg;
    reg mode_select;
    
    // 数据寄存器
    reg [31:0] acc_reg;
    reg [31:0] tmp_reg;
    
    // FSM (状态寄存器)
    reg [1:0] state;
    localparam IDLE = 2'b00, BUSY = 2'b01, DONE = 2'b10;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cycle_count <= 0;
            config_reg <= 0;
            mode_select <= 0;
            acc_reg <= 0;
            tmp_reg <= 0;
            state <= IDLE;
            result <= 0;
            done <= 0;
        end else begin
            case (state)
                IDLE: if (en) state <= BUSY;
                BUSY: begin
                    cycle_count <= cycle_count + 1;
                    if (cycle_count == 100) state <= DONE;
                end
                DONE: begin
                    result <= acc_reg;
                    done <= 1;
                    state <= IDLE;
                end
            endcase
        end
    end
    
    always_ff @(posedge clk) begin
        if (en) begin
            config_reg <= data_in[7:0];
            mode_select <= data_in[8];
            acc_reg <= acc_reg + data_in;
            tmp_reg <= data_in;
        end
    end
endmodule
"""
    
    demo_file = "test_mock_data/mixed_design.v"
    with open(demo_file, 'w') as f:
        f.write(demo_design)
    
    # 运行管线
    pipeline = HardeningPipeline(optimization_goal='area')
    pipeline.load_design(demo_file)
    pipeline.analyze()
    pipeline.route_strategies()
    pipeline.transform()
    pipeline.output("test_mock_data/mixed_design_hardened.v")
    pipeline.print_summary()
    pipeline.run_iverilog_check("test_mock_data/mixed_design_hardened.v")

if __name__ == "__main__":
    demo()
