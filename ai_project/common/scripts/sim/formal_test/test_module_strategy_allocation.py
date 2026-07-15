#!/usr/bin/env python3
"""
test_module_strategy_allocation.py — Unit tests for module-level strategy allocation

验证子模块级策略分配功能的正确性，包括：
  1. 模块级策略映射的准确性
  2. 信号级策略映射的准确性
  3. 默认策略的应用
  4. 层次化寄存器的策略分配
  5. 策略汇总统计的正确性
"""

import os
import sys
import unittest
from typing import Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag_integration import allocate_strategy_per_module, analyze_design_for_hardening


class TestModuleStrategyAllocation(unittest.TestCase):
    """单元测试：模块级策略分配功能"""

    def setUp(self):
        """测试前准备"""
        self.mock_design_analysis = {
            "module_name": "top_module",
            "signals": [
                {"name": "clk", "direction": "input", "width": 1, "module": "top_module"},
                {"name": "rst_n", "direction": "input", "width": 1, "module": "top_module"},
                {"name": "data_in", "direction": "input", "width": 32, "module": "top_module"},
                {"name": "data_out", "direction": "output", "width": 32, "module": "top_module"},
            ],
            "registers": [
                {"name": "top_reg", "width": 32, "source": "declaration"},
            ],
            "submodules": {
                "control_unit": {
                    "module_name": "control_unit",
                    "signals": [
                        {"name": "ctrl_en", "direction": "input", "width": 1},
                        {"name": "ctrl_out", "direction": "output", "width": 8},
                    ],
                    "registers": [
                        {"name": "state_reg", "width": 4},
                        {"name": "count_reg", "width": 8},
                    ],
                    "all_registers": [
                        {"name": "control_unit.state_reg", "width": 4, "module": "control_unit"},
                        {"name": "control_unit.count_reg", "width": 8, "module": "control_unit"},
                    ],
                },
                "data_path": {
                    "module_name": "data_path",
                    "signals": [
                        {"name": "data_a", "direction": "input", "width": 32},
                        {"name": "data_b", "direction": "input", "width": 32},
                        {"name": "result", "direction": "output", "width": 32},
                    ],
                    "registers": [
                        {"name": "buffer_reg", "width": 32},
                        {"name": "accum_reg", "width": 64},
                    ],
                    "all_registers": [
                        {"name": "data_path.buffer_reg", "width": 32, "module": "data_path"},
                        {"name": "data_path.accum_reg", "width": 64, "module": "data_path"},
                    ],
                },
                "fsm_core": {
                    "module_name": "fsm_core",
                    "signals": [
                        {"name": "start", "direction": "input", "width": 1},
                        {"name": "done", "direction": "output", "width": 1},
                    ],
                    "registers": [
                        {"name": "fsm_state", "width": 3},
                    ],
                    "all_registers": [
                        {"name": "fsm_core.fsm_state", "width": 3, "module": "fsm_core"},
                    ],
                },
            },
            "all_registers": [
                {"name": "top_reg", "width": 32, "module": "top_module"},
                {"name": "control_unit.state_reg", "width": 4, "module": "control_unit"},
                {"name": "control_unit.count_reg", "width": 8, "module": "control_unit"},
                {"name": "data_path.buffer_reg", "width": 32, "module": "data_path"},
                {"name": "data_path.accum_reg", "width": 64, "module": "data_path"},
                {"name": "fsm_core.fsm_state", "width": 3, "module": "fsm_core"},
            ],
            "all_signals": [
                {"name": "clk", "direction": "input", "width": 1, "module": "top_module"},
                {"name": "rst_n", "direction": "input", "width": 1, "module": "top_module"},
                {"name": "data_in", "direction": "input", "width": 32, "module": "top_module"},
                {"name": "data_out", "direction": "output", "width": 32, "module": "top_module"},
            ],
            "signal_width": 64,
            "parse_success": True,
        }

    def test_basic_module_strategy_allocation(self):
        """测试基本的模块级策略分配"""
        module_strategies = {
            'top_module': 'tmr',
            'control_unit': 'parity',
            'data_path': 'ecc',
            'fsm_core': 'onehot_fsm',
        }

        result = allocate_strategy_per_module(
            self.mock_design_analysis,
            module_strategies=module_strategies,
            default_strategy='tmr',
        )

        self.assertIn('module_strategy_map', result)
        self.assertIn('signal_strategy_map', result)
        self.assertIn('strategy_summary', result)

        module_map = result['module_strategy_map']
        self.assertEqual(module_map['top_module'], 'tmr')
        self.assertEqual(module_map['control_unit'], 'parity')
        self.assertEqual(module_map['data_path'], 'ecc')
        self.assertEqual(module_map['fsm_core'], 'onehot_fsm')

    def test_signal_strategy_mapping(self):
        """测试信号级策略映射的准确性"""
        module_strategies = {
            'top_module': 'tmr',
            'control_unit': 'parity',
            'data_path': 'ecc',
            'fsm_core': 'onehot_fsm',
        }

        result = allocate_strategy_per_module(
            self.mock_design_analysis,
            module_strategies=module_strategies,
        )

        signal_map = result['signal_strategy_map']

        self.assertEqual(signal_map['top_reg'], 'tmr')
        self.assertEqual(signal_map['control_unit.state_reg'], 'parity')
        self.assertEqual(signal_map['control_unit.count_reg'], 'parity')
        self.assertEqual(signal_map['data_path.buffer_reg'], 'ecc')
        self.assertEqual(signal_map['data_path.accum_reg'], 'ecc')
        self.assertEqual(signal_map['fsm_core.fsm_state'], 'onehot_fsm')

        self.assertEqual(signal_map['clk'], 'tmr')
        self.assertEqual(signal_map['rst_n'], 'tmr')

    def test_default_strategy(self):
        """测试默认策略的应用"""
        module_strategies = {
            'control_unit': 'parity',
        }

        result = allocate_strategy_per_module(
            self.mock_design_analysis,
            module_strategies=module_strategies,
            default_strategy='dice',
        )

        module_map = result['module_strategy_map']
        self.assertEqual(module_map['top_module'], 'dice')
        self.assertEqual(module_map['control_unit'], 'parity')
        self.assertEqual(module_map['data_path'], 'dice')
        self.assertEqual(module_map['fsm_core'], 'dice')

    def test_strategy_summary(self):
        """测试策略汇总统计的正确性"""
        module_strategies = {
            'top_module': 'tmr',
            'control_unit': 'parity',
            'data_path': 'ecc',
            'fsm_core': 'onehot_fsm',
        }

        result = allocate_strategy_per_module(
            self.mock_design_analysis,
            module_strategies=module_strategies,
        )

        summary = result['strategy_summary']
        self.assertEqual(summary['total_modules'], 4)
        self.assertEqual(summary['modules_with_custom_strategy'], 4)
        self.assertEqual(summary['modules_with_default_strategy'], 0)

        dist = summary['strategy_distribution']
        self.assertEqual(dist.get('tmr'), 1)
        self.assertEqual(dist.get('parity'), 1)
        self.assertEqual(dist.get('ecc'), 1)
        self.assertEqual(dist.get('onehot_fsm'), 1)

    def test_partial_module_strategies(self):
        """测试部分模块指定策略的情况"""
        module_strategies = {
            'control_unit': 'parity',
            'fsm_core': 'onehot_fsm',
        }

        result = allocate_strategy_per_module(
            self.mock_design_analysis,
            module_strategies=module_strategies,
            default_strategy='tmr',
        )

        summary = result['strategy_summary']
        self.assertEqual(summary['total_modules'], 4)
        self.assertEqual(summary['modules_with_custom_strategy'], 2)
        self.assertEqual(summary['modules_with_default_strategy'], 2)

    def test_empty_module_strategies(self):
        """测试空模块策略（全部使用默认策略）"""
        result = allocate_strategy_per_module(
            self.mock_design_analysis,
            module_strategies=None,
            default_strategy='tmr',
        )

        module_map = result['module_strategy_map']
        for module in ['top_module', 'control_unit', 'data_path', 'fsm_core']:
            self.assertEqual(module_map[module], 'tmr')

        summary = result['strategy_summary']
        self.assertEqual(summary['total_modules'], 4)
        self.assertEqual(summary['modules_with_custom_strategy'], 0)
        self.assertEqual(summary['modules_with_default_strategy'], 4)

    def test_top_key_alias(self):
        """测试 'top' 作为顶层模块的别名"""
        module_strategies = {
            'top': 'parity',
            'control_unit': 'tmr',
        }

        result = allocate_strategy_per_module(
            self.mock_design_analysis,
            module_strategies=module_strategies,
            default_strategy='dice',
        )

        module_map = result['module_strategy_map']
        self.assertEqual(module_map['top_module'], 'parity')
        self.assertEqual(module_map['control_unit'], 'tmr')
        self.assertEqual(module_map['data_path'], 'dice')
        self.assertEqual(module_map['fsm_core'], 'dice')

    def test_signals_by_strategy(self):
        """测试按策略分组的信号列表"""
        module_strategies = {
            'top_module': 'tmr',
            'control_unit': 'parity',
            'data_path': 'ecc',
            'fsm_core': 'onehot_fsm',
        }

        result = allocate_strategy_per_module(
            self.mock_design_analysis,
            module_strategies=module_strategies,
        )

        signals_by_strategy = result['strategy_summary']['signals_by_strategy']

        self.assertIn('top_reg', signals_by_strategy.get('tmr', []))
        self.assertIn('clk', signals_by_strategy.get('tmr', []))
        self.assertIn('rst_n', signals_by_strategy.get('tmr', []))

        self.assertIn('control_unit.state_reg', signals_by_strategy.get('parity', []))
        self.assertIn('control_unit.count_reg', signals_by_strategy.get('parity', []))

        self.assertIn('data_path.buffer_reg', signals_by_strategy.get('ecc', []))
        self.assertIn('data_path.accum_reg', signals_by_strategy.get('ecc', []))

        self.assertIn('fsm_core.fsm_state', signals_by_strategy.get('onehot_fsm', []))

    def test_with_real_design_analysis(self):
        """测试使用真实设计分析结果的策略分配"""
        import tempfile

        top_rtl = """
module top_module (
    input wire clk,
    input wire rst_n,
    input wire [31:0] data_in,
    output reg [31:0] data_out
);
    reg [31:0] top_reg;

    control_unit u_ctrl (
        .clk(clk),
        .rst_n(rst_n),
        .en(1'b1),
        .ctrl_out()
    );

    data_path u_data (
        .clk(clk),
        .data_a(data_in),
        .data_b(top_reg),
        .result(data_out)
    );
endmodule
"""

        ctrl_rtl = """
module control_unit (
    input wire clk,
    input wire rst_n,
    input wire en,
    output reg [7:0] ctrl_out
);
    reg [3:0] state_reg;
    reg [7:0] count_reg;
endmodule
"""

        data_rtl = """
module data_path (
    input wire clk,
    input wire [31:0] data_a,
    input wire [31:0] data_b,
    output reg [31:0] result
);
    reg [31:0] buffer_reg;
    reg [63:0] accum_reg;
endmodule
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            top_path = os.path.join(tmpdir, 'top.v')
            ctrl_path = os.path.join(tmpdir, 'control_unit.v')
            data_path = os.path.join(tmpdir, 'data_path.v')

            with open(top_path, 'w') as f:
                f.write(top_rtl)
            with open(ctrl_path, 'w') as f:
                f.write(ctrl_rtl)
            with open(data_path, 'w') as f:
                f.write(data_rtl)

            analysis = analyze_design_for_hardening(
                top_path,
                recursive=True,
                search_paths=[tmpdir],
            )

            self.assertTrue(analysis.get('parse_success', False))
            self.assertIn('submodules', analysis)
            self.assertIn('control_unit', analysis['submodules'])
            self.assertIn('data_path', analysis['submodules'])

            module_strategies = {
                'top_module': 'tmr',
                'control_unit': 'parity',
                'data_path': 'ecc',
            }

            result = allocate_strategy_per_module(analysis, module_strategies)

            self.assertIn('module_strategy_map', result)
            self.assertIn('signal_strategy_map', result)

            module_map = result['module_strategy_map']
            self.assertEqual(module_map['top_module'], 'tmr')
            self.assertEqual(module_map['control_unit'], 'parity')
            self.assertEqual(module_map['data_path'], 'ecc')

            signal_map = result['signal_strategy_map']
            self.assertIn('top_reg', signal_map)
            self.assertEqual(signal_map['top_reg'], 'tmr')

            ctrl_regs = [k for k in signal_map.keys() if 'control_unit' in k]
            for reg in ctrl_regs:
                self.assertEqual(signal_map[reg], 'parity')

            data_regs = [k for k in signal_map.keys() if 'data_path' in k]
            for reg in data_regs:
                self.assertEqual(signal_map[reg], 'ecc')


def run_tests():
    """运行所有测试"""
    print("=" * 60)
    print("  Module-Level Strategy Allocation Unit Tests")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestModuleStrategyAllocation)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 60)
    print(f"  Summary: {result.testsRun} tests")
    if result.failures:
        print(f"  Failures: {len(result.failures)}")
    if result.errors:
        print(f"  Errors: {len(result.errors)}")
    if result.wasSuccessful():
        print("  ✅ All tests passed!")
    else:
        print("  ❌ Some tests failed!")
    print("=" * 60)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
