#!/usr/bin/env python3
"""
故障注入自动化框架 — Fault Injection Automation Framework

支持随机 SEU 注入、AVF 统计和加固评分校准。

架构:
    FaultInjector   — 故障注入器 (生成 Testbench, 运行仿真, 收集结果)
    AVFAnalyzer     — AVF 分析与寄存器排序
    Calibrator      — 用 AVF 标签校准 SignalAnalyzer 评分权重
    demo()          — 端到端演示

依赖:
    - Python 3.6+
    - numpy (仅 Calibrator.fit_weights)
    - iverilog + vvp (实际仿真用, demo 模式可跳过)
"""

import re
import os
import math
import random
import subprocess
import tempfile
from collections import defaultdict


class FaultInjector:
    """故障注入器 - 对 DUT 的指定寄存器进行随机 SEU 注入"""

    def __init__(self, rtl_files, top_module, clk_period=10):
        """
        Args:
            rtl_files: RTL 文件路径列表
            top_module: 顶层模块名
            clk_period: 时钟周期 (ns), 默认 10
        """
        self.rtl_files = rtl_files
        self.top_module = top_module
        self.clk_period = clk_period
        self.injection_results = []

    def discover_registers(self):
        """读取 RTL 并发现所有寄存器 (使用正则表达式搜索 reg 声明)

        Returns:
            list[dict]: [{name: str, width: int, file: str}]
        """
        registers = []
        for rtl_file in self.rtl_files:
            with open(rtl_file, 'r') as f:
                content = f.read()

            # 匹配 reg 声明: reg [msb:lsb] name; 或 reg name;
            reg_pattern = re.finditer(
                r'reg\s*(?:\[(\d+):(\d+)\])?\s*(\w+)\s*;',
                content
            )
            for m in reg_pattern:
                msb = int(m.group(1)) if m.group(1) else 0
                lsb = int(m.group(2)) if m.group(2) else 0
                width = msb - lsb + 1 if m.group(1) else 1
                registers.append({
                    'name': m.group(3),
                    'width': width,
                    'file': rtl_file
                })
        return registers

    def generate_injection_tb(self, target_reg, bit_pos, inject_time=100):
        """为指定寄存器生成带故障注入的 Verilog 测试台

        Args:
            target_reg: 目标寄存器层次路径 (如 'u_dut.counter')
            bit_pos: 注入位位置 (-1=所有位翻转, 0~W-1=特定位)
            inject_time: 注入时间 (ns)

        Returns:
            str: Verilog 测试台代码
        """
        if bit_pos == -1:
            force_stmt = (
                f"force {target_reg} = ~{target_reg};\n"
            )
        else:
            force_stmt = (
                f"force {target_reg}[{bit_pos}] = ~{target_reg}[{bit_pos}];\n"
            )

        tb_code = f"""`timescale 1ns/1ps
module tb_fault_injection;

    reg clk, rst_n;

    // ===== DUT 实例化 (用户需根据实际模块修改) =====
    // {self.top_module} u_dut (
    //     .clk  (clk),
    //     .rst_n(rst_n)
    // );

    // 时钟生成
    initial begin
        clk = 0;
        forever #({self.clk_period / 2}) clk = ~clk;
    end

    // 复位与测试序列
    initial begin
        $dumpfile("fault_injection.vcd");
        $dumpvars(0, tb_fault_injection);

        rst_n = 0;
        #20 rst_n = 1;

        // 等待系统稳定
        #80;

        // ===== 故障注入点 =====
        #({inject_time});
{force_stmt}        #20;
        release {target_reg};

        // 观察故障传播
        #200;

        $display("==========================================");
        $display("FAULT_INJECTION_RESULT: {target_reg}[{bit_pos}]");
        $display("FAULT_INJECTION_TIME:   {inject_time}");
        $display("==========================================");

        $finish;
    end

    // 监控输出
    initial begin
        $monitor("t=%0t clk=%b rst_n=%b", $time, clk, rst_n);
    end

endmodule
"""
        return tb_code

    def run_single_injection(self, reg_name, bit_pos, num_cycles=50):
        """运行单次故障注入

        使用 iverilog + vvp 运行并解析结果。

        Args:
            reg_name: 寄存器名
            bit_pos: 位位置
            num_cycles: 仿真周期数

        Returns:
            dict: {reg, bit, passed, log/error}
        """
        tb_code = self.generate_injection_tb(
            f"u_dut.{reg_name}", bit_pos, inject_time=50
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tb_file = os.path.join(tmpdir, "tb_fi.v")
            sim_out = os.path.join(tmpdir, "sim")

            with open(tb_file, 'w') as f:
                f.write(tb_code)

            # 编译
            compile_result = subprocess.run(
                ["iverilog", "-g2012", "-o", sim_out,
                 *self.rtl_files, tb_file],
                capture_output=True, text=True
            )

            if compile_result.returncode != 0:
                return {
                    'reg': reg_name,
                    'bit': bit_pos,
                    'passed': False,
                    'error': compile_result.stderr
                }

            # 运行仿真
            run_result = subprocess.run(
                [sim_out],
                capture_output=True, text=True
            )

            return {
                'reg': reg_name,
                'bit': bit_pos,
                'passed': 'ERROR' not in run_result.stdout.upper(),
                'log': run_result.stdout
            }

    def run_monte_carlo(self, num_injections=1000):
        """运行蒙特卡洛故障注入

        随机选择 {reg, bit, time} 组合，对每个组合执行单次注入。

        Args:
            num_injections: 注入次数, 默认 1000

        Returns:
            list[dict]: [{reg, bit, time, passed, avf_contribution}]
        """
        registers = self.discover_registers()
        if not registers:
            print("[警告] 未发现任何寄存器，请检查 RTL 文件路径")
            return []

        results = []
        for i in range(num_injections):
            reg = random.choice(registers)
            bit_pos = random.randint(0, max(0, reg['width'] - 1))

            result = self.run_single_injection(reg['name'], bit_pos)
            results.append(result)

            if (i + 1) % 100 == 0:
                print(f"  进度: {i + 1}/{num_injections} 次注入完成")

        self.injection_results = results
        return results


class AVFAnalyzer:
    """AVF 分析和寄存器排序"""

    @staticmethod
    def compute_avf(injection_results):
        """从故障注入结果计算每个寄存器的 AVF

        AVF = (导致输出错误的注入次数) / (总注入次数)

        Args:
            injection_results: FaultInjector.run_monte_carlo 的输出

        Returns:
            dict: {reg_name: avf}
        """
        reg_stats = defaultdict(lambda: {'total': 0, 'errors': 0})

        for r in injection_results:
            reg = r['reg']
            reg_stats[reg]['total'] += 1
            if not r.get('passed', True):
                reg_stats[reg]['errors'] += 1

        avf = {}
        for reg, stats in reg_stats.items():
            if stats['total'] > 0:
                avf[reg] = stats['errors'] / stats['total']
            else:
                avf[reg] = 0.0

        return avf

    @staticmethod
    def rank_registers(avf, top_k=10):
        """按 AVF 从高到低排序

        Args:
            avf: compute_avf 返回的字典
            top_k: 返回前 k 个, 默认 10

        Returns:
            list[tuple]: [(reg_name, avf), ...]
        """
        sorted_regs = sorted(avf.items(), key=lambda x: -x[1])
        return sorted_regs[:top_k]

    @staticmethod
    def compare_hardening(before_avf, after_avf):
        """比较加固前后的 AVF 变化

        Args:
            before_avf: 加固前 AVF 字典
            after_avf:  加固后 AVF 字典

        Returns:
            dict: {
                'before_mean': float,
                'after_mean': float,
                'improvement': float,       # 改善倍数
                'register_details': [{reg, before, after, reduction}]
            }
        """
        all_regs = set(list(before_avf.keys()) + list(after_avf.keys()))
        details = []

        for reg in sorted(all_regs):
            b = before_avf.get(reg, 0.0)
            a = after_avf.get(reg, 0.0)
            reduction = (b - a) / b if b > 0 else float('inf')
            details.append({
                'reg': reg,
                'before': b,
                'after': a,
                'reduction': reduction
            })

        b_mean = sum(before_avf.values()) / len(before_avf) if before_avf else 0.0
        a_mean = sum(after_avf.values()) / len(after_avf) if after_avf else 0.0

        improvement = b_mean / a_mean if a_mean > 0 else float('inf')

        return {
            'before_mean': b_mean,
            'after_mean': a_mean,
            'improvement': improvement,
            'register_details': details
        }


class Calibrator:
    """用 AVF 标签校准 SignalAnalyzer 评分系统

    将基于静态关键词的评分与 AVF 实测值进行对齐,
    通过线性回归拟合各维度的最优权重。
    """

    # SignalAnalyzer 的 8 个评分维度
    DIMENSIONS = [
        'keyword', 'type', 'fanout', 'depth',
        'width', 'feedback', 'fsm', 'protocol'
    ]

    @staticmethod
    def fit_weights(training_data):
        """用线性回归拟合最佳权重

        Args:
            training_data: list[dict], 每个元素格式:
                {signal: str, features: {dim: score}, avf: float}

        Returns:
            dict: {dim: best_weight}
        """
        import numpy as np

        X = []
        y = []
        for item in training_data:
            features = item['features']
            X.append([features.get(d, 0) for d in Calibrator.DIMENSIONS])
            y.append(item['avf'])

        X = np.array(X)
        y = np.array(y)

        # 最小二乘拟合
        weights, residuals, rank, s = np.linalg.lstsq(X, y, rcond=None)

        return dict(zip(Calibrator.DIMENSIONS, weights))

    @staticmethod
    def compare_keyword(signal_scores, avf):
        """关键词评分 vs AVF 对比分析

        计算皮尔逊相关系数、Top-K 重合率，并列出差异项。

        Args:
            signal_scores: {signal_name: keyword_score}
            avf:           {signal_name: avf_value}

        Returns:
            dict: {
                'correlation': float,       # 皮尔逊相关系数
                'top_k_agreement': float,   # top-10 重合率
                'mismatches': [{signal, keyword_score, avf}]
            }
        """
        common = set(signal_scores.keys()) & set(avf.keys())
        if not common:
            return {'correlation': 0.0, 'top_k_agreement': 0.0, 'mismatches': []}

        ks_vals = [signal_scores[s] for s in common]
        avf_vals = [avf[s] for s in common]

        # 皮尔逊相关系数
        n = len(common)
        k_mean = sum(ks_vals) / n
        a_mean = sum(avf_vals) / n
        num = sum((k - k_mean) * (a - a_mean) for k, a in zip(ks_vals, avf_vals))
        dk = math.sqrt(sum((k - k_mean) ** 2 for k in ks_vals))
        da = math.sqrt(sum((a - a_mean) ** 2 for a in avf_vals))
        correlation = num / (dk * da) if dk * da > 0 else 0.0

        # Top-K 重合率
        top_k = 10
        ks_top = set(sorted(common, key=lambda s: -signal_scores[s])[:top_k])
        avf_top = set(sorted(common, key=lambda s: -avf[s])[:top_k])
        overlap = len(ks_top & avf_top)
        agreement = overlap / top_k

        # 差异项 (关键词评分与 AVF 归一化后差异超过 30 分的信号)
        mismatches = []
        for s in common:
            k = signal_scores[s]
            a = avf[s]
            if abs(k - a * 100) > 30:
                mismatches.append({'signal': s, 'keyword_score': k, 'avf': a})

        return {
            'correlation': correlation,
            'top_k_agreement': agreement,
            'mismatches': sorted(
                mismatches, key=lambda x: -abs(x['keyword_score'] - x['avf'] * 100)
            )
        }


def demo():
    """端到端演示 (使用模拟数据, 无需 iverilog)"""
    print("=" * 60)
    print("     故障注入自动化框架 - 端到端演示")
    print("=" * 60)

    # 1. 尝试从现有 RTL 发现寄存器
    print("\n[1/4] 发现寄存器")
    mock_rtl = os.path.normpath(os.path.join(
        os.path.dirname(__file__),
        "..", "..", "test_mock_data", "cnt_comp_template.v"
    ))

    if os.path.exists(mock_rtl):
        injector = FaultInjector([mock_rtl], "cnt_comp_up")
        registers = injector.discover_registers()
        print(f"  从 {mock_rtl} 发现 {len(registers)} 个寄存器:")
    else:
        print(f"  [提示] 未找到 mock RTL 文件: {mock_rtl}")
        print(f"  使用模拟寄存器列表进行演示")
        registers = [
            {'name': 'counter', 'width': 8},
            {'name': 'state', 'width': 3},
            {'name': 'data_reg', 'width': 16},
            {'name': 'addr_reg', 'width': 8},
            {'name': 'flag_reg', 'width': 1},
        ]
        print(f"  使用 {len(registers)} 个模拟寄存器:")

    for r in registers[:5]:
        print(f"    - {r['name']} (width={r['width']})")

    # 2. 模拟故障注入
    print(f"\n[2/4] 模拟故障注入 (100 次)")
    mock_results = []
    random.seed(42)
    for _ in range(100):
        reg = random.choice(registers)
        bit = random.randint(0, max(0, reg['width'] - 1))
        mock_results.append({
            'reg': reg['name'],
            'bit': bit,
            'passed': random.random() > 0.3,  # 70% 通过, 30% 出错
        })
    passed_count = sum(1 for r in mock_results if r['passed'])
    failed_count = sum(1 for r in mock_results if not r['passed'])
    print(f"  注入完成: {len(mock_results)} 次 (通过={passed_count}, 出错={failed_count})")

    # 3. AVF 分析
    print(f"\n[3/4] AVF 分析")
    analyzer = AVFAnalyzer()
    avf = analyzer.compute_avf(mock_results)

    print(f"\n  AVF 排名 (Top 5):")
    ranked = analyzer.rank_registers(avf, top_k=5)
    for reg, a in ranked:
        print(f"    {reg:20s}: AVF = {a:.2%}")

    # 加固前后对比
    print(f"\n  加固效果对比 (模拟):")
    before_avf = avf
    after_avf = {reg: max(0.0, v * random.uniform(0.1, 0.5))
                 for reg, v in before_avf.items()}
    comparison = analyzer.compare_hardening(before_avf, after_avf)
    print(f"    加固前平均 AVF: {comparison['before_mean']:.4%}")
    print(f"    加固后平均 AVF: {comparison['after_mean']:.4%}")
    print(f"    改善倍数:       {comparison['improvement']:.2f}x")

    # 4. 评分校准对比
    print(f"\n[4/4] 校准对比 (关键词评分 vs AVF)")
    # 模拟 SignalAnalyzer 评分
    mock_scores = {}
    for reg in registers:
        # 模拟评分: 分数与 AVF 大致正相关但带噪声
        base = avf.get(reg['name'], 0.1) * 100
        mock_scores[reg['name']] = min(100, max(0, base + random.uniform(-15, 15)))

    cal = Calibrator()
    comparison_result = cal.compare_keyword(mock_scores, avf)
    print(f"    皮尔逊相关系数: {comparison_result['correlation']:.3f}")
    print(f"    Top-10 重合率:  {comparison_result['top_k_agreement']:.0%}")
    if comparison_result['mismatches']:
        print(f"    差异项 ({len(comparison_result['mismatches'])} 个):")
        for m in comparison_result['mismatches'][:3]:
            print(f"      - {m['signal']}: 评分={m['keyword_score']:.1f}, AVF={m['avf']:.2%}")

    print(f"\n{'=' * 60}")
    print("  说明: 当前为演示模式 (使用模拟数据)")
    print("  实际工作流:")
    print("    1. FaultInjector(rtl_files, top_module)")
    print("    2. injector.run_monte_carlo(10000)")
    print("    3. AVFAnalyzer.compute_avf(results)")
    print("    4. Calibrator.fit_weights(training_data)")
    print("  要求: 安装 iverilog 并提供目标 DUT RTL 文件")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
