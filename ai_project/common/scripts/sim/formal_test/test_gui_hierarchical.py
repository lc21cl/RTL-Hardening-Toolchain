#!/usr/bin/env python3
"""
test_gui_hierarchical.py — GUI Hierarchical Hardening Functional Test

验证层次化加固 GUI 功能的核心逻辑，包括：
  1. RTL 设计加载和模块层次提取
  2. 模块树状视图数据结构
  3. 策略配置和映射
  4. 层次化加固执行
  5. 策略配置导出

注意：这是一个功能测试，不启动图形界面，只测试核心业务逻辑。
"""

import os
import sys
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag_integration import (
    analyze_design_for_hardening,
    allocate_strategy_per_module,
    apply_module_strategies,
)


def create_test_design():
    """创建测试用的层次化 RTL 设计"""
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

    fsm_core u_fsm (
        .clk(clk),
        .rst_n(rst_n),
        .start(1'b1),
        .done()
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

    fsm_rtl = """
module fsm_core (
    input wire clk,
    input wire rst_n,
    input wire start,
    output reg done
);
    reg [2:0] fsm_state;
endmodule
"""

    return {
        'top.v': top_rtl,
        'control_unit.v': ctrl_rtl,
        'data_path.v': data_rtl,
        'fsm_core.v': fsm_rtl,
    }


def test_design_load():
    """测试 RTL 设计加载和模块层次提取"""
    print("\n" + "=" * 60)
    print("  Test 1: Design Loading and Module Hierarchy Extraction")
    print("=" * 60)

    design_files = create_test_design()

    with tempfile.TemporaryDirectory() as tmpdir:
        for fname, content in design_files.items():
            with open(os.path.join(tmpdir, fname), 'w') as f:
                f.write(content)

        top_path = os.path.join(tmpdir, 'top.v')

        print(f"\n[GUI_TEST] Loading design: {os.path.basename(top_path)}")
        analysis = analyze_design_for_hardening(
            top_path,
            recursive=True,
            search_paths=[tmpdir],
        )

        print(f"[GUI_TEST] Parse success: {analysis.get('parse_success')}")
        print(f"[GUI_TEST] Top module: {analysis.get('module_name')}")
        print(f"[GUI_TEST] Submodules: {list(analysis.get('submodules', {}).keys())}")
        print(f"[GUI_TEST] Total registers: {len(analysis.get('all_registers', []))}")

        assert analysis.get('parse_success') is True, "设计解析失败"
        assert analysis.get('module_name') == 'top_module', "顶层模块名称不正确"
        assert 'control_unit' in analysis.get('submodules', {}), "缺少 control_unit 子模块"
        assert 'data_path' in analysis.get('submodules', {}), "缺少 data_path 子模块"
        assert 'fsm_core' in analysis.get('submodules', {}), "缺少 fsm_core 子模块"
        assert len(analysis.get('all_registers', [])) == 6, "寄存器数量不正确"

        print("\n[GUI_TEST] ✅ Design loading test PASSED")

        for reg in analysis.get('all_registers', []):
            print(f"[GUI_TEST]   Register: {reg['name']} (width={reg['width']}, module={reg.get('module', 'top')})")

    return analysis


def test_module_strategy_configuration():
    """测试模块策略配置和映射"""
    print("\n" + "=" * 60)
    print("  Test 2: Module Strategy Configuration")
    print("=" * 60)

    design_files = create_test_design()

    with tempfile.TemporaryDirectory() as tmpdir:
        for fname, content in design_files.items():
            with open(os.path.join(tmpdir, fname), 'w') as f:
                f.write(content)

        top_path = os.path.join(tmpdir, 'top.v')
        analysis = analyze_design_for_hardening(top_path, recursive=True, search_paths=[tmpdir])

        module_strategies = {
            'top_module': 'tmr',
            'control_unit': 'parity',
            'data_path': 'ecc',
            'fsm_core': 'onehot_fsm',
        }

        print(f"\n[GUI_TEST] Configuring module strategies:")
        for module, strategy in module_strategies.items():
            print(f"[GUI_TEST]   {module}: {strategy}")

        result = allocate_strategy_per_module(analysis, module_strategies)

        print(f"\n[GUI_TEST] Module strategy map:")
        for module, strategy in sorted(result['module_strategy_map'].items()):
            print(f"[GUI_TEST]   {module}: {strategy}")

        print(f"\n[GUI_TEST] Signal strategy mapping:")
        for signal, strategy in sorted(result['signal_strategy_map'].items()):
            print(f"[GUI_TEST]   {signal}: {strategy}")

        assert result['module_strategy_map']['top_module'] == 'tmr'
        assert result['module_strategy_map']['control_unit'] == 'parity'
        assert result['module_strategy_map']['data_path'] == 'ecc'
        assert result['module_strategy_map']['fsm_core'] == 'onehot_fsm'

        assert result['signal_strategy_map']['top_reg'] == 'tmr'
        assert result['signal_strategy_map']['control_unit.state_reg'] == 'parity'
        assert result['signal_strategy_map']['data_path.buffer_reg'] == 'ecc'
        assert result['signal_strategy_map']['fsm_core.fsm_state'] == 'onehot_fsm'

        print("\n[GUI_TEST] ✅ Module strategy configuration test PASSED")


def test_hierarchical_hardening():
    """测试层次化加固执行"""
    print("\n" + "=" * 60)
    print("  Test 3: Hierarchical Hardening Execution")
    print("=" * 60)

    design_files = create_test_design()

    with tempfile.TemporaryDirectory() as tmpdir:
        for fname, content in design_files.items():
            with open(os.path.join(tmpdir, fname), 'w') as f:
                f.write(content)

        top_path = os.path.join(tmpdir, 'top.v')
        analysis = analyze_design_for_hardening(top_path, recursive=True, search_paths=[tmpdir])

        module_strategies = {
            'top_module': 'tmr',
            'control_unit': 'parity',
            'data_path': 'ecc',
            'fsm_core': 'onehot_fsm',
        }

        result = allocate_strategy_per_module(analysis, module_strategies)

        with open(top_path, 'r', encoding='utf-8') as f:
            rtl_content = f.read()

        print(f"\n[GUI_TEST] Applying hierarchical hardening...")
        hardened_content = apply_module_strategies(rtl_content, result)

        output_path = os.path.join(tmpdir, 'top_hardened.v')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(hardened_content)

        print(f"[GUI_TEST] Hardened output: {os.path.basename(output_path)}")
        print(f"[GUI_TEST] Original lines: {rtl_content.count('\\n')}")
        print(f"[GUI_TEST] Hardened lines: {hardened_content.count('\\n')}")

        assert '// Hardened Design with Module-Level Strategies' in hardened_content
        assert '// Strategy Distribution:' in hardened_content

        print("\n[GUI_TEST] ✅ Hierarchical hardening test PASSED")


def test_strategy_config_export():
    """测试策略配置导出"""
    print("\n" + "=" * 60)
    print("  Test 4: Strategy Configuration Export")
    print("=" * 60)

    module_strategies = {
        'top_module': 'tmr',
        'control_unit': 'parity',
        'data_path': 'ecc',
        'fsm_core': 'onehot_fsm',
    }

    config = {
        'rtl_file': '/path/to/top.v',
        'module_strategies': module_strategies,
        'export_time': '2026-07-15 12:00:00',
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        config_path = f.name

    print(f"\n[GUI_TEST] Exporting config to: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        loaded_config = json.load(f)

    assert loaded_config['rtl_file'] == '/path/to/top.v'
    assert loaded_config['module_strategies'] == module_strategies

    print(f"[GUI_TEST] Config content:")
    print(json.dumps(loaded_config, indent=2, ensure_ascii=False))

    os.unlink(config_path)

    print("\n[GUI_TEST] ✅ Strategy config export test PASSED")


def test_gui_tree_structure():
    """测试模块树状视图数据结构"""
    print("\n" + "=" * 60)
    print("  Test 5: Module Tree Structure")
    print("=" * 60)

    design_files = create_test_design()

    with tempfile.TemporaryDirectory() as tmpdir:
        for fname, content in design_files.items():
            with open(os.path.join(tmpdir, fname), 'w') as f:
                f.write(content)

        top_path = os.path.join(tmpdir, 'top.v')
        analysis = analyze_design_for_hardening(top_path, recursive=True, search_paths=[tmpdir])

        tree_data = []

        top_name = analysis.get('module_name', 'top')
        top_regs = len(analysis.get('registers', []))
        tree_data.append({
            'name': top_name,
            'strategy': 'tmr',
            'registers': top_regs,
            'children': [],
        })

        submodules = analysis.get('submodules', {})
        for sub_name, sub_info in submodules.items():
            sub_regs = len(sub_info.get('registers', []))
            tree_data[0]['children'].append({
                'name': sub_name,
                'strategy': 'tmr',
                'registers': sub_regs,
                'children': [],
            })

        print(f"\n[GUI_TEST] Module tree structure:")

        def print_tree(node, indent=0):
            prefix = "  " * indent
            print(f"{prefix}- {node['name']} (strategy={node['strategy']}, regs={node['registers']})")
            for child in node['children']:
                print_tree(child, indent + 1)

        for root in tree_data:
            print_tree(root)

        assert len(tree_data) == 1
        assert tree_data[0]['name'] == 'top_module'
        assert len(tree_data[0]['children']) == 3

        child_names = [c['name'] for c in tree_data[0]['children']]
        assert 'control_unit' in child_names
        assert 'data_path' in child_names
        assert 'fsm_core' in child_names

        print("\n[GUI_TEST] ✅ Module tree structure test PASSED")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 70)
    print("  GUI Hierarchical Hardening Functional Tests")
    print("=" * 70)

    tests = [
        test_design_load,
        test_module_strategy_configuration,
        test_hierarchical_hardening,
        test_strategy_config_export,
        test_gui_tree_structure,
    ]

    passed = 0
    failed = 0

    for i, test_func in enumerate(tests, 1):
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n[GUI_TEST] ❌ Test {i} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 70)
    print(f"  Test Summary: {passed}/{len(tests)} passed")
    if failed == 0:
        print("  ✅ All tests PASSED!")
    else:
        print(f"  ❌ {failed} test(s) FAILED!")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
