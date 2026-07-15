#!/usr/bin/env python3
"""测试 P0 功能模块。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rtl_parser import (
    extract_tmrg_directives,
    parse_tmrg_constraints,
    apply_tmrg_constraints_to_strategy_map,
    strip_rtl_comments_preserve_tmrg
)
from sdc_generator import (
    add_keep_attributes,
    generate_sdc_constraints,
    protect_tmr_logic,
    generate_protected_rtl
)
from voter_insertion import (
    apply_full_tmr,
    apply_partial_tmr,
    apply_input_tmr,
    apply_output_tmr,
    analyze_tmr_overhead,
    VoterInsertionStrategy
)
from train_data_generator import (
    generate_sft_sample,
    generate_dpo_sample,
    generate_dataset,
    save_dataset,
    split_dataset,
    generate_example_samples
)


def test_tmrg_parser():
    """测试 TMRG 注释约束解析。"""
    print("=" * 60)
    print("测试 1: TMRG 注释约束解析")
    print("=" * 60)

    test_rtl = """
// tmrg default triplicate
module test_module(
    input clk,
    input rst,
    input [7:0] din,
    output [7:0] dout
);
    reg [7:0] internal_reg;
    // tmrg do_not_triplicate internal_reg
    // tmrg triplicate dout
    always @(posedge clk) begin
        internal_reg <= din;
    end
    assign dout = internal_reg;
endmodule
"""

    directives = extract_tmrg_directives(test_rtl)
    print(f"解析到的指令: {directives}")

    constraints = parse_tmrg_constraints(test_rtl)
    print(f"约束配置: {constraints}")

    strategy_map = {}
    updated_map = apply_tmrg_constraints_to_strategy_map(test_rtl, strategy_map)
    print(f"应用约束后的策略映射: {updated_map}")

    preserved = strip_rtl_comments_preserve_tmrg(test_rtl)
    print("保留TMRG注释后的代码:")
    print(preserved)

    print("✓ TMRG解析器测试通过\n")


def test_sdc_generator():
    """测试综合保护机制。"""
    print("=" * 60)
    print("测试 2: 综合保护机制")
    print("=" * 60)

    test_rtl = """
module test_reg(
    input clk,
    input [7:0] din,
    output reg [7:0] dout
);
    reg [7:0] temp;
    always @(posedge clk) begin
        temp <= din;
        dout <= temp;
    end
endmodule
"""

    protected_signals = ['temp', 'dout']
    protected = add_keep_attributes(test_rtl, protected_signals)
    print("添加keep属性后的代码:")
    print(protected)

    sdc_content = generate_sdc_constraints('test_reg', protected_signals)
    print("生成的SDC约束:")
    print(sdc_content[:500])

    tmr_protected = protect_tmr_logic(test_rtl)
    print("自动保护TMR逻辑:")
    print(tmr_protected)

    print("✓ SDC生成器测试通过\n")


def test_voter_insertion():
    """测试投票器插入算法。"""
    print("=" * 60)
    print("测试 3: 投票器插入算法")
    print("=" * 60)

    test_rtl = """
module simple_reg(
    input clk,
    input rst,
    input [7:0] din,
    output reg [7:0] dout
);
    always @(posedge clk or posedge rst) begin
        if (rst)
            dout <= 8'b0;
        else
            dout <= din;
    end
endmodule
"""

    signals = ['dout']
    bit_widths = {'dout': 8}

    full_tmr = apply_full_tmr(test_rtl, signals, bit_widths)
    print("Full TMR 结果:")
    print(full_tmr[:800])

    partial_tmr = apply_partial_tmr(test_rtl, ['dout'], ['din'], bit_widths)
    print("Partial TMR 结果:")
    print(partial_tmr[:800])

    input_tmr = apply_input_tmr(test_rtl, ['din'], {'din': 8})
    print("Input TMR 结果:")
    print(input_tmr[:800])

    output_tmr = apply_output_tmr(test_rtl, ['dout'], {'dout': 8})
    print("Output TMR 结果:")
    print(output_tmr[:800])

    overhead = analyze_tmr_overhead(100, VoterInsertionStrategy.FULL_TMR, 10, 8)
    print(f"面积开销分析: {overhead}")

    print("✓ 投票器插入测试通过\n")


def test_train_data_generator():
    """测试训练数据生成器。"""
    print("=" * 60)
    print("测试 4: SFT/DPO训练数据生成")
    print("=" * 60)

    original_rtl = """module simple_reg(input clk, input [7:0] din, output reg [7:0] dout);
    always @(posedge clk) dout <= din;
endmodule"""

    hardened_rtl = """module simple_reg_tmr(input clk, input [7:0] din, output reg [7:0] dout);
    wire [7:0] dout_A, dout_B, dout_C;
    simple_reg inst_A(.clk(clk), .din(din), .dout(dout_A));
    simple_reg inst_B(.clk(clk), .din(din), .dout(dout_B));
    simple_reg inst_C(.clk(clk), .din(din), .dout(dout_C));
    majority_voter voter(.A(dout_A), .B(dout_B), .C(dout_C), .Z(dout));
endmodule"""

    sft_sample = generate_sft_sample(original_rtl, hardened_rtl, 'tmr')
    print(f"SFT样本ID: {sft_sample['id']}")
    print(f"SFT指令: {sft_sample['instruction'][:50]}...")

    dpo_sample = generate_dpo_sample(original_rtl, hardened_rtl, original_rtl, 'tmr')
    print(f"DPO样本ID: {dpo_sample['id']}")
    print(f"DPO提示: {dpo_sample['prompt']}")

    samples = generate_example_samples(3)
    dataset = generate_dataset(samples, format='sft')
    print(f"数据集样本数: {dataset['num_samples']}")

    train, val, test = split_dataset(dataset)
    print(f"训练集: {train['num_samples']} 验证集: {val['num_samples']} 测试集: {test['num_samples']}")

    output_path = os.path.join(os.path.dirname(__file__), 'test_dataset.json')
    save_dataset(dataset, output_path)
    print(f"数据集已保存到: {output_path}")

    jsonl_path = os.path.join(os.path.dirname(__file__), 'test_dataset.jsonl')
    save_dataset(dataset, jsonl_path, format='jsonl')
    print(f"JSONL格式已保存到: {jsonl_path}")

    print("✓ 训练数据生成测试通过\n")


def main():
    """运行所有P0功能测试。"""
    print("\n" + "=" * 60)
    print("P0 功能模块综合测试")
    print("=" * 60 + "\n")

    test_tmrg_parser()
    test_sdc_generator()
    test_voter_insertion()
    test_train_data_generator()

    print("=" * 60)
    print("所有 P0 功能测试通过!")
    print("=" * 60)


if __name__ == '__main__':
    main()