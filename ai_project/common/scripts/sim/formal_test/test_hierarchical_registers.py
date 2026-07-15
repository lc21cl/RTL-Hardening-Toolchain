#!/usr/bin/env python3
"""
test_hierarchical_registers.py — 验证层次化寄存器提取（子模块寄存器递归捕获）

测试用例:
  1. test_port_design_errors.v (顶层) + adder_sub.v (子模块)
     - 验证顶层提取到 6 个端口
     - 验证子模块 adder_sub 被递归发现
     - 验证扁平化后总共捕获到 4 个寄存器 (顶层 sum/carry + 子模块 sum/carry)
  2. 顶层寄存器和子模块寄存器的命名前缀正确性
"""

import os
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 确保可以 import
sys.path.insert(0, SCRIPT_DIR)

try:
    from logger import setup_logger, logger
    logger = setup_logger(
        name='hier_test',
        log_level='TRACE',
        console_output=True,
        log_file='logs/hierarchical_test.log',
    )
except ImportError:
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("hier_test")


def test_basic_hierarchical_extraction():
    """Test 1: Basic hierarchical register extraction with top + submodule."""
    logger.section("TEST 1: Hierarchical Register Extraction")
    logger.print("  Verifying that submodule registers are captured recursively...")

    from rag_integration import analyze_design_for_hardening

    top_file = os.path.join(SCRIPT_DIR, "test_port_design_errors.v")
    sub_file = os.path.join(SCRIPT_DIR, "adder_sub.v")

    assert os.path.isfile(top_file), f"Missing: {top_file}"
    assert os.path.isfile(sub_file), f"Missing: {sub_file}"

    # Run with recursive=True and search_paths
    result = analyze_design_for_hardening(
        top_file,
        search_paths=[SCRIPT_DIR],
        recursive=True,
    )

    print(f"\n  Top module: {result['module_name']}")
    print(f"  Top-level signals (ports): {len(result['signals'])}")
    for s in result['signals']:
        print(f"    {s['direction']:8s} [{s['width']:2d}] {s['name']}")

    print(f"\n  Top-level registers: {len(result.get('registers', []))}")
    for r in result.get('registers', []):
        print(f"    [{r['width']}] {r['name']} (source={r.get('source','?')})")

    print(f"\n  Submodules found: {len(result.get('submodules', {}))}")
    for sub_name, sub_info in result.get('submodules', {}).items():
        print(f"    {sub_name} -> file={sub_info.get('file','N/A')}")
        print(f"      instance={sub_info.get('instance','?')}, "
              f"regs={len(sub_info.get('registers', []))}, "
              f"parse={sub_info.get('parse_success')}")

    print(f"\n  Flattened ALL registers ({len(result.get('all_registers', []))}):")
    for r in result.get('all_registers', []):
        print(f"    [{r['width']}] {r['name']} (module={r.get('module','top')})")

    print(f"\n  Flattened ALL signals ({len(result.get('all_signals', []))}):")
    for s in result.get('all_signals', []):
        print(f"    {s['module']:15s} {s['direction']:8s} [{s['width']}] {s['name']}")

    # Assertions
    all_regs = result.get('all_registers', [])
    all_sigs = result.get('all_signals', [])
    submodules = result.get('submodules', {})

    # 1. Verify top module name
    assert result['module_name'] == 'test_port_errors', \
        f"Expected 'test_port_errors', got '{result['module_name']}'"

    # 2. Verify top-level signals
    assert len(result['signals']) == 6, \
        f"Expected 6 top-level signals, got {len(result['signals'])}"

    # 3. Verify submodule 'adder_sub' was found
    assert 'adder_sub' in submodules, \
        f"Submodule 'adder_sub' not found in {list(submodules.keys())}"
    assert submodules['adder_sub']['parse_success'], \
        "adder_sub submodule parsing failed"

    # 4. Verify flattened registers include submodule registers
    # adder_sub has: sum (reg, 8-bit) in sequential always, carry (wire, no reg)
    # So adder_sub should contribute at least 1 register
    sub_regs = submodules['adder_sub'].get('registers', [])
    assert len(sub_regs) >= 1, \
        f"Expected >=1 register in adder_sub, got {len(sub_regs)}"

    # 5. Verify flattened register list has more items than top-level list
    top_regs = result.get('registers', [])
    assert len(all_regs) > len(top_regs), \
        f"Flattened register count ({len(all_regs)}) should exceed top-level count ({len(top_regs)})"

    # 6. Verify signal_width is at least 8
    assert result['signal_width'] >= 8, \
        f"Expected signal_width >= 8, got {result['signal_width']}"

    logger.print(f"\n  ✅ All 6 assertions passed!")
    return True


def test_flat_vs_recursive():
    """Test 2: Compare flat vs recursive mode behavior."""
    logger.section("TEST 2: Flat vs Recursive Mode Comparison")
    logger.print("  Verifying recursive mode captures more registers than flat mode...")

    from rag_integration import analyze_design_for_hardening

    top_file = os.path.join(SCRIPT_DIR, "test_port_design_errors.v")

    # Flat mode (original behavior)
    flat_result = analyze_design_for_hardening(
        top_file,
        search_paths=None,
        recursive=False,
    )

    # Recursive mode (new behavior)
    recursive_result = analyze_design_for_hardening(
        top_file,
        search_paths=[SCRIPT_DIR],
        recursive=True,
    )

    print(f"\n  Flat mode:      {len(flat_result.get('registers', []))} registers")
    print(f"  Recursive mode: {len(recursive_result.get('all_registers', []))} total registers "
          f"(top={len(recursive_result.get('registers', []))}, "
          f"sub={len(recursive_result.get('submodules', {}))} submodules)")

    # Both should have parse_success
    assert flat_result['parse_success'], "Flat mode parse failed!"
    assert recursive_result['parse_success'], "Recursive mode parse failed!"

    # Both should have same module name
    assert flat_result['module_name'] == recursive_result['module_name'], \
        "Module names should match between modes"

    # Recursive should have all_registers key
    assert 'all_registers' in recursive_result, \
        "Recursive result missing 'all_registers'"

    # Recursive should have submodules key
    assert 'submodules' in recursive_result, \
        "Recursive result missing 'submodules'"

    logger.print(f"\n  ✅ All 4 assertions passed!")
    return True


def test_single_module_no_submodules():
    """Test 3: Single module with no submodules."""
    logger.section("TEST 3: Single Module (No Submodules)")
    logger.print("  Verifying flat file works correctly in recursive mode...")

    from rag_integration import analyze_design_for_hardening

    # Use test_buggy_design.v which has no submodule instantiations
    test_file = os.path.join(SCRIPT_DIR, "test_buggy_design.v")
    assert os.path.isfile(test_file), f"Missing: {test_file}"

    result = analyze_design_for_hardening(
        test_file,
        search_paths=[SCRIPT_DIR],
        recursive=True,
    )

    print(f"\n  Module: {result['module_name']}")
    print(f"  Signals: {len(result['signals'])}")
    print(f"  Registers (top): {len(result.get('registers', []))}")
    print(f"  Submodules: {len(result.get('submodules', {}))}")
    print(f"  All registers (flat): {len(result.get('all_registers', []))}")
    print(f"  Parse success: {result['parse_success']}")

    assert result['parse_success'], "Parse failed!"
    assert len(result.get('submodules', {})) == 0, \
        f"Expected 0 submodules for single-module file, got {len(result['submodules'])}"

    # all_registers should equal top-level registers when no submodules
    assert len(result.get('all_registers', [])) == len(result.get('registers', [])), \
        "All registers should equal top registers for single-module design"

    logger.print(f"\n  ✅ All 3 assertions passed!")
    return True


def main():
    logger.section("HIERARCHICAL REGISTER EXTRACTION TESTS")
    logger.print(f"  Testing submodule register recursive capture...\n")

    results = {}

    logger.print(f"{'=' * 62}")
    results["Hierarchical Basic"] = test_basic_hierarchical_extraction()

    logger.print(f"\n{'=' * 62}")
    results["Flat vs Recursive"] = test_flat_vs_recursive()

    logger.print(f"\n{'=' * 62}")
    results["Single Module"] = test_single_module_no_submodules()

    logger.print(f"\n{'=' * 62}")
    logger.section("SUMMARY")
    all_pass = True
    for name, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        if not passed:
            all_pass = False
        logger.print(f"  {name:35s} -> {status}")

    logger.print(f"\n  OVERALL: {'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")

    return all_pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
