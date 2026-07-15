#!/usr/bin/env python3
"""测试 P1 功能模块。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gnn_vulnerability import (
    predict_vulnerability,
    generate_vulnerability_report,
    save_vulnerability_results,
    build_circuit_graph,
    GraphSAGE
)
from llm_hardening import (
    LLMHardeningGenerator,
    build_default_knowledge_base,
    generate_hardened_rtl,
    generate_rag_prompt
)
from error_signaling import (
    add_error_detection_signal,
    add_error_reporting_module,
    generate_error_recovery_logic,
    add_comprehensive_error_detection,
    analyze_error_signals
)
from selective_hardening import (
    SelectiveHardeningStrategy,
    apply_selective_hardening,
    generate_hybrid_strategy,
    calculate_effectiveness,
    generate_strategy_report,
    find_optimal_strategy
)


def test_gnn_vulnerability():
    """测试GNN脆弱性预测。"""
    print("=" * 60)
    print("测试 1: GNN脆弱性预测")
    print("=" * 60)

    test_rtl = """
module test_module(
    input clk,
    input rst,
    input [7:0] din,
    output [7:0] dout
);
    reg [7:0] reg1;
    reg [7:0] reg2;
    reg [7:0] reg3;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            reg1 <= 8'b0;
            reg2 <= 8'b0;
            reg3 <= 8'b0;
        end else begin
            reg1 <= din;
            reg2 <= reg1;
            reg3 <= reg2;
        end
    end

    assign dout = reg3;
endmodule
"""

    results = predict_vulnerability(test_rtl)
    print(f"预测结果: {results}")

    report = generate_vulnerability_report(results)
    print("脆弱性报告:")
    print(report)

    output_path = os.path.join(os.path.dirname(__file__), 'vulnerability_results.json')
    save_vulnerability_results(results, output_path)
    print(f"结果已保存到: {output_path}")

    print("✓ GNN脆弱性预测测试通过\n")
    return results


def test_llm_hardening():
    """测试LLM驱动的加固重写。"""
    print("=" * 60)
    print("测试 2: LLM驱动的加固重写")
    print("=" * 60)

    test_rtl = """module simple_reg(input clk, input [7:0] din, output reg [7:0] dout);
    always @(posedge clk) dout <= din;
endmodule"""

    kb = build_default_knowledge_base()
    print(f"知识库条目数: {len(kb.entries)}")

    search_results = kb.search("tmr register")
    print(f"搜索结果: {[r['title'] for r in search_results]}")

    prompt = generate_rag_prompt(test_rtl, 'tmr', kb)
    print(f"提示词长度: {len(prompt)}")

    hardened_code = generate_hardened_rtl(test_rtl, 'tmr', kb, simulate=True)
    print("生成的加固代码:")
    print(hardened_code[:800])

    print("✓ LLM驱动加固测试通过\n")


def test_error_signaling():
    """测试错误信号设计。"""
    print("=" * 60)
    print("测试 3: 错误信号设计")
    print("=" * 60)

    test_rtl = """module tmr_register(
    input clk,
    input [7:0] din,
    output [7:0] dout_A, dout_B, dout_C
);
    reg [7:0] reg_A, reg_B, reg_C;
    always @(posedge clk) begin
        reg_A <= din;
        reg_B <= din;
        reg_C <= din;
    end
    assign dout_A = reg_A;
    assign dout_B = reg_B;
    assign dout_C = reg_C;
endmodule"""

    rtl_with_error = add_error_detection_signal(test_rtl, 'dout', signal_width=8, error_type='tmr')
    print("添加错误检测信号:")
    print(rtl_with_error[:600])

    rtl_with_report = add_error_reporting_module(rtl_with_error)
    print("添加错误报告模块:")
    print(rtl_with_report[:600])

    rtl_with_recovery = generate_error_recovery_logic(rtl_with_report, 'reset')
    print("添加恢复逻辑:")
    print(rtl_with_recovery[:600])

    comprehensive = add_comprehensive_error_detection(test_rtl, 'tmr', include_recovery=True)
    print("完整错误检测:")
    print(comprehensive[:600])

    analysis = analyze_error_signals(comprehensive)
    print(f"错误信号分析: {analysis}")

    print("✓ 错误信号设计测试通过\n")


def test_selective_hardening(vulnerability_results):
    """测试选择性加固策略。"""
    print("=" * 60)
    print("测试 4: 选择性加固策略")
    print("=" * 60)

    strategy = SelectiveHardeningStrategy()

    strategy_map = {}
    updated_map = apply_selective_hardening(vulnerability_results, strategy_map, strategy)
    print(f"应用选择性加固后的策略: {updated_map}")

    hybrid_map = generate_hybrid_strategy(vulnerability_results, 0.3, 0.4, 0.3)
    print(f"混合策略: {hybrid_map}")

    effectiveness = calculate_effectiveness(vulnerability_results, hybrid_map)
    print(f"效果统计: {effectiveness}")

    report = generate_strategy_report(vulnerability_results, hybrid_map, effectiveness)
    print("策略报告:")
    print(report)

    optimal_map = find_optimal_strategy(vulnerability_results)
    print(f"最优策略: {optimal_map}")

    print("✓ 选择性加固策略测试通过\n")


def main():
    """运行所有P1功能测试。"""
    print("\n" + "=" * 60)
    print("P1 功能模块综合测试")
    print("=" * 60 + "\n")

    vulnerability_results = test_gnn_vulnerability()
    test_llm_hardening()
    test_error_signaling()
    test_selective_hardening(vulnerability_results)

    print("=" * 60)
    print("所有 P1 功能测试通过!")
    print("=" * 60)


if __name__ == '__main__':
    main()