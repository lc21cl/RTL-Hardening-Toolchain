#!/usr/bin/env python3
"""test_p3_features.py — P3功能测试。

测试AIG图构建、SVA断言、Auto-Repair和寄存器提取功能。
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aig_builder import AIGGraph, create_mock_aig, generate_aig_report
from sva_generator import (
    generate_tmr_consistency_assertions,
    generate_comprehensive_sva,
    generate_sva_report
)
from auto_repair import auto_repair, generate_repair_report
from register_extractor import RegisterExtractor, generate_register_report


class TestAIGBuilder(unittest.TestCase):
    """AIG图构建测试。"""

    def test_create_mock_aig(self):
        """测试创建模拟AIG图。"""
        graph = create_mock_aig()

        self.assertIsInstance(graph, AIGGraph)
        self.assertGreaterEqual(len(graph.nodes), 5)
        self.assertEqual(len(graph.inputs), 2)
        self.assertEqual(len(graph.outputs), 1)
        self.assertGreaterEqual(len(graph.edges), 3)

        const0 = graph.get_node(0)
        self.assertIsNotNone(const0)
        self.assertEqual(const0.node_type, 'CONST')

        input1 = graph.get_node(1)
        self.assertIsNotNone(input1)
        self.assertEqual(input1.node_type, 'INPUT')

        output1 = graph.get_node(4)
        self.assertIsNotNone(output1)
        self.assertEqual(output1.node_type, 'OUTPUT')

        print(f"  ✓ 模拟AIG图创建成功 (节点:{len(graph.nodes)}, 边:{len(graph.edges)})")

    def test_aig_report(self):
        """测试生成AIG报告。"""
        graph = create_mock_aig()
        report = generate_aig_report(graph)

        self.assertIn("AIG图分析报告", report)
        self.assertIn("总节点数", report)
        self.assertIn("输入节点数", report)
        self.assertIn("输出节点数", report)
        self.assertIn("边数", report)

        print("  ✓ AIG报告生成成功")

    def test_aig_to_networkx(self):
        """测试转换为NetworkX图。"""
        graph = create_mock_aig()

        try:
            nx_graph = graph.to_networkx()
            self.assertIsNotNone(nx_graph)
            self.assertEqual(len(nx_graph.nodes), len(graph.nodes))
            self.assertEqual(len(nx_graph.edges), len(graph.edges))
            print(f"  ✓ NetworkX转换成功 (节点:{len(nx_graph.nodes)}, 边:{len(nx_graph.edges)})")
        except ImportError:
            print("  - NetworkX未安装，跳过测试")

    def test_aig_to_pyg(self):
        """测试转换为PyG Data。"""
        graph = create_mock_aig()

        try:
            data = graph.to_pyg_data()
            self.assertIsNotNone(data)
            self.assertEqual(data.x.shape[0], len(graph.nodes))
            self.assertEqual(data.edge_index.shape[1], len(graph.edges))
            print(f"  ✓ PyG转换成功 (节点:{data.x.shape[0]}, 边:{data.edge_index.shape[1]})")
        except ImportError:
            print("  - PyTorch Geometric未安装，跳过测试")


class TestSVAGenerator(unittest.TestCase):
    """SVA断言生成测试。"""

    def test_tmr_consistency_assertions(self):
        """测试TMR一致性断言生成。"""
        signals = ['data', 'addr', 'ctrl']
        assertions = generate_tmr_consistency_assertions(signals)

        for sig in signals:
            self.assertIn(f"{sig}_A === {sig}_B", assertions)
            self.assertIn(f"{sig}_B === {sig}_C", assertions)

        print("  ✓ TMR一致性断言生成成功")

    def test_comprehensive_sva(self):
        """测试完整SVA断言模块生成。"""
        sva_code = generate_comprehensive_sva(
            module_name='test_module',
            tmr_signals=['data'],
            error_signals=['error'],
            input_signals=['clk', 'rst'],
            output_signals=['out']
        )

        self.assertIn('module test_module_sva', sva_code)
        self.assertIn('input clk', sva_code)
        self.assertIn('input rst', sva_code)
        self.assertIn('data_A', sva_code)
        self.assertIn('error', sva_code)
        self.assertIn('default clocking', sva_code)

        print("  ✓ 完整SVA断言模块生成成功")

    def test_sva_report(self):
        """测试SVA报告生成。"""
        report = generate_sva_report(
            module_name='test',
            tmr_signals=['data'],
            error_signals=['err'],
            input_signals=['clk'],
            output_signals=['out']
        )

        self.assertIn("SVA断言生成报告", report)
        self.assertIn("TMR一致性断言数量", report)
        self.assertIn("错误检测断言数量", report)

        print("  ✓ SVA报告生成成功")


class TestAutoRepair(unittest.TestCase):
    """Auto-Repair测试。"""

    def test_auto_repair_simple(self):
        """测试简单代码修复。"""
        verilog_code = """
module test_module(clk, rst, data_in, data_out);
    input clk, rst;
    input [7:0] data_in;
    output [7:0] data_out;

    reg [7:0] data_reg;

    always @(posedge clk) begin
        data_reg <= data_in;
    end

    assign data_out = data_reg;
endmodule
"""

        repaired_code, actions = auto_repair(verilog_code)

        self.assertIsInstance(repaired_code, str)
        self.assertIsInstance(actions, list)

        print(f"  ✓ 修复完成，动作数: {len(actions)}")

    def test_repair_report(self):
        """测试修复报告生成。"""
        verilog_code = """
module test_module(clk, data_in, data_out);
    input clk;
    input [7:0] data_in;
    output [7:0] data_out;

    reg [7:0] data_reg;

    always @(posedge clk) begin
        data_reg <= data_in;
    end

    assign data_out = data_reg;
endmodule
"""

        repaired_code, actions = auto_repair(verilog_code)
        report = generate_repair_report(actions)

        self.assertIn("Auto-Repair修复报告", report)
        self.assertIn("修复动作数量", report)

        print("  ✓ 修复报告生成成功")


class TestRegisterExtractor(unittest.TestCase):
    """寄存器提取测试。"""

    def test_extract_registers_simple(self):
        """测试简单模块寄存器提取。"""
        verilog_code = """
module simple_module(clk, rst, data_in, data_out);
    input clk, rst;
    input [7:0] data_in;
    output [7:0] data_out;

    reg [7:0] data_reg;
    reg flag;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            data_reg <= 8'h00;
            flag <= 1'b0;
        end else begin
            data_reg <= data_in;
            flag <= 1'b1;
        end
    end

    assign data_out = data_reg;
endmodule
"""

        extractor = RegisterExtractor()
        modules = extractor.extract(verilog_code)

        self.assertIn('simple_module', modules)

        simple_mod = modules['simple_module']
        self.assertGreaterEqual(len(simple_mod.registers), 2)

        reg_names = [r.name for r in simple_mod.registers]
        self.assertIn('data_reg', reg_names)
        self.assertIn('flag', reg_names)

        data_reg = next(r for r in simple_mod.registers if r.name == 'data_reg')
        self.assertEqual(data_reg.width, 8)
        self.assertTrue(data_reg.is_vector)
        self.assertTrue(data_reg.has_reset)

        flag = next(r for r in simple_mod.registers if r.name == 'flag')
        self.assertEqual(flag.width, 1)
        self.assertFalse(flag.is_vector)
        self.assertTrue(flag.has_reset)

        print(f"  ✓ 提取到 {len(simple_mod.registers)} 个寄存器")

    def test_extract_with_submodules(self):
        """测试含子模块的寄存器提取。"""
        verilog_code = """
module sub_module(clk, rst, in, out);
    input clk, rst;
    input [7:0] in;
    output [7:0] out;

    reg [7:0] sub_reg;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            sub_reg <= 8'h00;
        end else begin
            sub_reg <= in;
        end
    end

    assign out = sub_reg;
endmodule

module top_module(clk, rst, data_in, data_out);
    input clk, rst;
    input [7:0] data_in;
    output [7:0] data_out;

    reg [7:0] top_reg;

    sub_module sub_inst(.clk(clk), .rst(rst), .in(top_reg), .out(data_out));

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            top_reg <= 8'h00;
        end else begin
            top_reg <= data_in;
        end
    end
endmodule
"""

        extractor = RegisterExtractor()
        modules = extractor.extract(verilog_code)

        self.assertIn('sub_module', modules)
        self.assertIn('top_module', modules)

        top_module = modules['top_module']

        self.assertEqual(len(top_module.instances), 1)
        self.assertEqual(top_module.instances[0]['module_type'], 'sub_module')
        self.assertEqual(top_module.instances[0]['instance_name'], 'sub_inst')

        print("  ✓ 子模块实例化解析成功")

    def test_register_report(self):
        """测试寄存器报告生成。"""
        verilog_code = """
module test_module(clk, rst, data_in, data_out);
    input clk, rst;
    input [7:0] data_in;
    output [7:0] data_out;

    reg [7:0] data_reg;
    reg flag;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            data_reg <= 8'h00;
            flag <= 1'b0;
        end else begin
            data_reg <= data_in;
            flag <= 1'b1;
        end
    end

    assign data_out = data_reg;
endmodule
"""

        extractor = RegisterExtractor()
        modules = extractor.extract(verilog_code)
        registers = extractor.get_all_registers()
        report = generate_register_report(registers)

        self.assertIn("寄存器提取报告", report)
        self.assertIn("总寄存器数量", report)
        self.assertIn("向量寄存器", report)
        self.assertIn("标量寄存器", report)
        self.assertIn("有复位寄存器", report)

        print("  ✓ 寄存器报告生成成功")


if __name__ == '__main__':
    print("=" * 70)
    print("P3功能测试")
    print("=" * 70)
    print()

    print("1. AIG图构建测试")
    print("-" * 40)
    suite1 = unittest.TestLoader().loadTestsFromTestCase(TestAIGBuilder)
    runner1 = unittest.TextTestRunner(verbosity=0)
    result1 = runner1.run(suite1)
    if result1.wasSuccessful():
        print("  全部通过!")
    print()

    print("2. SVA断言生成测试")
    print("-" * 40)
    suite2 = unittest.TestLoader().loadTestsFromTestCase(TestSVAGenerator)
    runner2 = unittest.TextTestRunner(verbosity=0)
    result2 = runner2.run(suite2)
    if result2.wasSuccessful():
        print("  全部通过!")
    print()

    print("3. Auto-Repair测试")
    print("-" * 40)
    suite3 = unittest.TestLoader().loadTestsFromTestCase(TestAutoRepair)
    runner3 = unittest.TextTestRunner(verbosity=0)
    result3 = runner3.run(suite3)
    if result3.wasSuccessful():
        print("  全部通过!")
    print()

    print("4. 寄存器提取测试")
    print("-" * 40)
    suite4 = unittest.TestLoader().loadTestsFromTestCase(TestRegisterExtractor)
    runner4 = unittest.TextTestRunner(verbosity=0)
    result4 = runner4.run(suite4)
    if result4.wasSuccessful():
        print("  全部通过!")
    print()

    print("=" * 70)
    all_passed = result1.wasSuccessful() and result2.wasSuccessful() and \
                 result3.wasSuccessful() and result4.wasSuccessful()
    print(f"P3测试结果: {'全部通过!' if all_passed else '部分失败'}")
    print("=" * 70)