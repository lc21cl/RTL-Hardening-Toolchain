#!/usr/bin/env python3
"""
examples.py — 加固工具使用示例

提供详细的使用示例代码，帮助用户快速上手RTL加固工具链。

示例覆盖：
1. 基础加固流程
2. RTL文件/文件夹/数据集加固
3. 增量加固
4. 可靠性分析报告
5. 形式化验证
6. 策略自动选择
7. FPGA比特流加固
8. 故障注入测试
"""

import os
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

try:
    from hardening_pipeline import HardeningPipeline
except ImportError:
    sys.path.insert(0, os.path.dirname(PARENT_DIR))
    from hardening_pipeline import HardeningPipeline


def example_basic_hardening(input_file, output_file):
    """示例1: 基础加固流程"""
    print("\n" + "="*70)
    print("示例1: 基础加固流程")
    print("="*70)

    pipeline = HardeningPipeline(optimization_goal='balanced')
    
    pipeline.load_design(input_file)
    pipeline.analyze()
    pipeline.route_strategies()
    pipeline.transform()
    pipeline.output(output_file)

    print(f"\n✅ 基础加固完成")
    print(f"   输入: {input_file}")
    print(f"   输出: {output_file}")
    print(f"   加固信号数: {len(pipeline.strategy_map)}")


def example_single_file_hardening(input_file):
    """示例2: 单个RTL文件加固"""
    print("\n" + "="*70)
    print("示例2: 单个RTL文件加固")
    print("="*70)

    base, ext = os.path.splitext(input_file)
    output_file = f"{base}_hardened{ext}"

    pipeline = HardeningPipeline(optimization_goal='reliability')
    pipeline.load_design(input_file)
    pipeline.analyze()
    
    print(f"\n📊 设计分析结果:")
    print(f"   寄存器数: {pipeline.reg_count}")
    print(f"   信号数: {len(pipeline.module_info)}")
    print(f"   关键信号数: {pipeline.critical_count}")

    pipeline.route_strategies()
    pipeline.transform()
    pipeline.output(output_file)

    print(f"\n✅ 单个文件加固完成: {output_file}")


def example_folder_hardening(input_folder, output_folder):
    """示例3: RTL文件夹批量加固"""
    print("\n" + "="*70)
    print("示例3: RTL文件夹批量加固")
    print("="*70)

    os.makedirs(output_folder, exist_ok=True)

    rtl_files = []
    for root, dirs, files in os.walk(input_folder):
        for file in files:
            if file.endswith(('.v', '.sv')):
                rtl_files.append(os.path.join(root, file))

    print(f"📁 发现 {len(rtl_files)} 个RTL文件")

    hardened_count = 0
    for rtl_file in rtl_files:
        try:
            rel_path = os.path.relpath(rtl_file, input_folder)
            output_file = os.path.join(output_folder, rel_path)
            os.makedirs(os.path.dirname(output_file), exist_ok=True)

            pipeline = HardeningPipeline()
            pipeline.load_design(rtl_file)
            pipeline.analyze()
            pipeline.route_strategies()
            pipeline.transform()
            pipeline.output(output_file)

            print(f"   ✅ {rel_path}")
            hardened_count += 1
        except Exception as e:
            print(f"   ❌ {rtl_file}: {e}")

    print(f"\n✅ 文件夹加固完成: {hardened_count}/{len(rtl_files)}")


def example_dataset_hardening(dataset_folder, output_folder):
    """示例4: RTL数据集加固"""
    print("\n" + "="*70)
    print("示例4: RTL数据集加固")
    print("="*70)

    os.makedirs(output_folder, exist_ok=True)

    designs = []
    for item in os.listdir(dataset_folder):
        item_path = os.path.join(dataset_folder, item)
        if os.path.isdir(item_path):
            designs.append(item)

    print(f"📂 发现 {len(designs)} 个设计")

    results = []
    for design in designs:
        design_folder = os.path.join(dataset_folder, design)
        design_output = os.path.join(output_folder, design)
        os.makedirs(design_output, exist_ok=True)

        rtl_files = []
        for f in os.listdir(design_folder):
            if f.endswith(('.v', '.sv')):
                rtl_files.append(os.path.join(design_folder, f))

        if not rtl_files:
            continue

        main_file = rtl_files[0]
        base = os.path.splitext(os.path.basename(main_file))[0]
        output_file = os.path.join(design_output, f"{base}_hardened.v")

        try:
            pipeline = HardeningPipeline()
            pipeline.load_design(main_file)
            pipeline.analyze()
            pipeline.route_strategies()
            pipeline.transform()
            pipeline.output(output_file)

            result = {
                'design': design,
                'status': 'success',
                'registers': pipeline.reg_count,
                'signals': len(pipeline.strategy_map),
                'output': output_file,
            }
            results.append(result)
            print(f"   ✅ {design}: {pipeline.reg_count} 寄存器, {len(pipeline.strategy_map)} 信号")
        except Exception as e:
            results.append({'design': design, 'status': 'failed', 'error': str(e)})
            print(f"   ❌ {design}: {e}")

    summary_file = os.path.join(output_folder, 'hardening_summary.json')
    with open(summary_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ 数据集加固完成，汇总报告: {summary_file}")


def example_incremental_hardening(original_file, modified_file, previous_hardened):
    """示例5: 增量加固"""
    print("\n" + "="*70)
    print("示例5: 增量加固")
    print("="*70)

    pipeline = HardeningPipeline()
    pipeline.load_design(original_file)

    with open(modified_file, 'r') as f:
        modified_rtl = f.read()

    result = pipeline.incremental_update(modified_rtl, previous_hardened)

    print(f"\n📊 增量更新结果:")
    print(f"   更新类型: {result['update_type']}")
    print(f"   添加信号: {len(result.get('added_signals', []))}")
    print(f"   删除信号: {len(result.get('removed_signals', []))}")
    print(f"   修改信号: {len(result.get('modified_signals', []))}")

    if result['update_type'] == 'incremental':
        print(f"\n✅ 增量加固完成，无需全量重新加固")
    else:
        print(f"\n⚠️ 需要全量重新加固")


def example_reliability_report(input_file):
    """示例6: 可靠性分析报告"""
    print("\n" + "="*70)
    print("示例6: 可靠性分析报告")
    print("="*70)

    pipeline = HardeningPipeline()
    pipeline.load_design(input_file)
    pipeline.analyze()
    pipeline.route_strategies()

    report = pipeline.generate_reliability_report()

    print(f"\n📊 可靠性指标:")
    analysis = report.get('analysis', {})
    if 'overall_avf' in analysis:
        print(f"   AVF (架构脆弱性因子): {analysis['overall_avf']:.4f}")
    if 'failure_rate' in analysis:
        print(f"   故障率: {analysis['failure_rate']:.2e} failures/hour")
    if 'mtbf' in analysis:
        print(f"   MTBF (平均故障间隔): {analysis['mtbf']:.2f} 小时")
    if 'reliability_improvement' in analysis:
        print(f"   可靠性提升: {analysis['reliability_improvement'] * 100:.1f}%")

    print(f"\n💡 改进建议:")
    for i, rec in enumerate(report.get('recommendations', []), 1):
        print(f"   {i}. {rec}")

    print(f"\n✅ 可靠性报告生成完成")


def example_strategy_recommendation(input_file):
    """示例7: 策略自动选择"""
    print("\n" + "="*70)
    print("示例7: 策略自动选择")
    print("="*70)

    pipeline = HardeningPipeline()
    pipeline.load_design(input_file)

    constraints = {
        'max_area_overhead': 50,
        'max_power_overhead': 30,
        'target_reliability': 0.99,
    }

    recommendations = pipeline.recommend_strategy(constraints)

    print(f"\n🎯 推荐策略 (基于约束: {constraints}):")
    for i, rec in enumerate(recommendations, 1):
        print(f"\n   {i}. {rec['strategy']}")
        print(f"      得分: {rec['score']:.2f}")
        print(f"      面积开销: {rec['metrics']['area_overhead']}")
        print(f"      功耗开销: {rec['metrics']['power_overhead']}")
        print(f"      可靠性: {rec['metrics']['reliability']}")
        print(f"      延迟: {rec['metrics']['latency']}")

    print(f"\n✅ 策略推荐完成")


def example_formal_verification(rtl_file):
    """示例8: 形式化验证"""
    print("\n" + "="*70)
    print("示例8: 形式化验证")
    print("="*70)

    pipeline = HardeningPipeline()
    pipeline.load_design(rtl_file)

    result = pipeline.formal_verify([rtl_file])

    if result.get('success'):
        print(f"\n✅ 形式化验证通过")
        print(f"   状态: {result.get('status')}")
    else:
        print(f"\n⚠️ 形式化验证: {result.get('error', '未执行')}")
        print("   (需要安装 SymbiYosys)")


def example_fpga_bitstream_hardening(bitstream_file):
    """示例9: FPGA比特流加固"""
    print("\n" + "="*70)
    print("示例9: FPGA比特流加固")
    print("="*70)

    base, ext = os.path.splitext(bitstream_file)
    output_file = f"{base}_hardened{ext}"

    try:
        from fpga_bitstream_hardening import FPGABitstreamHardener

        hardener = FPGABitstreamHardener()

        if not hardener.load_bitstream(bitstream_file):
            print(f"❌ 无法加载比特流文件: {bitstream_file}")
            return

        hardener.configure_tmr(['TOP_MODULE'])
        hardener.configure_ecc_region('CONFIG_REGION', 0x0, 0xFFFF)
        hardener.enable_scrubbing(True, 1000)
        hardener.enable_partial_reconfig(True)

        result = hardener.generate_hardened_bitstream(output_file)

        if result['success']:
            print(f"\n✅ FPGA比特流加固完成")
            print(f"   输出: {output_file}")
            print(f"   应用策略: {', '.join(result['applied_strategies'])}")
            print(f"   可靠性提升: {result['reliability_improvement'] * 100:.1f}%")
            print(f"   面积开销: {result['overhead_percent']:.1f}%")
        else:
            print(f"\n❌ 加固失败: {result.get('error')}")
    except ImportError:
        print("❌ FPGA比特流加固模块不可用")


def example_fault_injection(rtl_file):
    """示例10: 故障注入测试"""
    print("\n" + "="*70)
    print("示例10: 故障注入测试")
    print("="*70)

    try:
        from fault_injection import FaultInjector

        injector = FaultInjector()
        result = injector.inject(rtl_file, fault_type='SEU', count=10)

        print(f"\n📊 故障注入结果:")
        print(f"   注入故障数: {result.get('injected', 0)}")
        print(f"   检测到故障: {result.get('detected', 0)}")
        print(f"   未检测到故障: {result.get('undetected', 0)}")
        print(f"   覆盖率: {result.get('coverage', 0) * 100:.1f}%")

        print(f"\n✅ 故障注入测试完成")
    except ImportError:
        print("❌ 故障注入模块不可用")


def run_all_examples():
    """运行所有示例"""
    test_dir = os.path.join(SCRIPT_DIR, 'test_data')
    os.makedirs(test_dir, exist_ok=True)

    test_rtl = os.path.join(test_dir, 'test_design.v')
    if not os.path.exists(test_rtl):
        with open(test_rtl, 'w') as f:
            f.write("""
module test_design(
    input clk,
    input rst_n,
    input [7:0] data_in,
    output [7:0] data_out,
    output reg [3:0] count
);

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        count <= 4'b0;
    end else begin
        count <= count + 1'b1;
    end
end

assign data_out = data_in;

endmodule
""")

    test_modified = os.path.join(test_dir, 'test_design_modified.v')
    if not os.path.exists(test_modified):
        with open(test_modified, 'w') as f:
            f.write("""
module test_design(
    input clk,
    input rst_n,
    input [7:0] data_in,
    input [7:0] extra_data,
    output [7:0] data_out,
    output [7:0] extra_out,
    output reg [3:0] count
);

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        count <= 4'b0;
    end else begin
        count <= count + 1'b1;
    end
end

assign data_out = data_in;
assign extra_out = extra_data;

endmodule
""")

    output_dir = os.path.join(test_dir, 'output')
    os.makedirs(output_dir, exist_ok=True)

    example_basic_hardening(test_rtl, os.path.join(output_dir, 'basic_hardened.v'))
    example_single_file_hardening(test_rtl)
    example_folder_hardening(test_dir, os.path.join(output_dir, 'folder_output'))
    example_dataset_hardening(test_dir, os.path.join(output_dir, 'dataset_output'))
    example_incremental_hardening(test_rtl, test_modified, None)
    example_reliability_report(test_rtl)
    example_strategy_recommendation(test_rtl)
    example_formal_verification(test_rtl)
    example_fault_injection(test_rtl)

    print("\n" + "="*70)
    print("🎉 所有示例运行完成！")
    print("="*70)


if __name__ == '__main__':
    run_all_examples()