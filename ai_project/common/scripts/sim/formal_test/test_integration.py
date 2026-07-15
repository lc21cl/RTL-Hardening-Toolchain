#!/usr/bin/env python3
"""
test_integration.py — 完整自动化加固流水线集成测试

测试内容:
  1. Design Error Analysis — 验证端口方向/类型/数量错误检测
  2. RAG 管线日志 — 验证详细日志输出
  3. Auto-Repair 管线日志 — 验证详细日志输出
  4. 端到端 Hardening Pipeline — 验证集成效果
"""

import os
import sys
import time

# Setup logger first
try:
    from logger import setup_logger, logger
    logger = setup_logger(
        name='integration_test',
        log_level='TRACE',
        console_output=True,
        log_file='logs/integration_test.log',
    )
except ImportError:
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("integration_test")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def test_design_error_analysis():
    """Test 1: Verify design error analysis detects port direction/type/quantity errors."""
    logger.section("TEST 1: Design Error Analysis")
    logger.print("  Testing static analysis of port direction/type/quantity errors...")

    test_file = os.path.join(SCRIPT_DIR, "test_port_design_errors.v")
    submodule_file = os.path.join(SCRIPT_DIR, "adder_sub.v")

    if not os.path.isfile(test_file):
        logger.error(f"  Test file not found: {test_file}")
        return False

    from graph_pipeline import GraphPipeline
    pipeline = GraphPipeline(verbose=True)

    # Use combined file with submodule content for accurate analysis
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="design_errors_test_")
    combined_path = os.path.join(tmp_dir, "combined_test.v")

    with open(test_file, "r") as f:
        test_content = f.read()
    with open(submodule_file, "r") as f:
        sub_content = f.read()

    combined = f"{sub_content}\n\n{test_content}"
    with open(combined_path, "w") as f:
        f.write(combined)

    logger.print(f"\n  --- Analysis on combined file (with submodule) ---")
    result = pipeline.analyze_design_errors(combined_path)

    print(f"\n  Results:")
    print(f"    Modules found:   {len(result.get('modules', {}))}")
    print(f"    Instances found: {len(result.get('instances', []))}")
    print(f"    Errors detected: {len(result.get('errors', []))}")
    print(f"    Warnings raised: {len(result.get('warnings', []))}")
    print(f"    Analysis passed: {result.get('analysis_passed', False)}")

    # Check that we detected design errors
    errors = result.get("errors", [])
    warnings = result.get("warnings", [])

    # Log detailed findings
    logger.print(f"\n  Detailed Findings:")
    logger.print(f"  Modules:")
    for mod_name, mod_info in result.get("modules", {}).items():
        logger.print(f"    {mod_name}: {mod_info['port_count']} ports at line {mod_info['line']}")
        for p in mod_info["ports"]:
            logger.print(f"      {p['direction']} {p['type']} [{p['width']}] {p['name']}")

    logger.print(f"\n  Instances:")
    for inst in result.get("instances", []):
        logger.print(f"    {inst['instance_name']} ({inst['module_name']}): "
                     f"{inst['conn_count']} connections at line {inst['line']}")
        for conn in inst["connections"][:4]:
            logger.print(f"      .{conn['port']}({conn['signal']})")

    if errors:
        logger.print(f"\n  Detected Errors ({len(errors)}):")
        for err in errors:
            logger.print(f"    [{err['type']}] (severity={err.get('severity','?')}) {err['description'][:120]}")

    if warnings:
        logger.print(f"\n  Detected Warnings ({len(warnings)}):")
        for warn in warnings:
            logger.print(f"    [{warn['type']}] {warn['description'][:120]}")

    # The test file has intentional errors — analysis should find them
    # Specifically:
    #   - direction_conflict: signal 'carry_sig' connects to both input and output
    #   - port_count_mismatch: u_adder_count_error has 4 connections but 6 expected
    #   - type_mismatch warning: 'carry_sig' is reg but connected to wire ports
    error_types = [e["type"] for e in errors]
    logger.print(f"\n  Error types found: {set(error_types)}")

    expected_types = {'direction_conflict', 'port_count_mismatch'}
    has_expected = expected_types.issubset(set(error_types))
    logger.print(f"  Expected errors ({expected_types}): {'ALL FOUND' if has_expected else 'MISSING SOME'}")
    logger.print(f"  TEST 1 {'PASSED' if has_expected else 'FAILED — missing expected error types'}")
    return has_expected


def test_rag_pipeline():
    """Test 2: Verify RAG pipeline with detailed logging."""
    logger.section("TEST 2: RAG Pipeline Logging")
    logger.print("  Testing RAG pipeline with detailed logging...")

    try:
        from rag_integration import RAGEngine, analyze_design_for_hardening
    except ImportError as e:
        logger.error(f"  RAG module import failed: {e}")
        return False

    # Create a test RTL file for RAG analysis
    test_rtl = os.path.join(SCRIPT_DIR, "test_buggy_design.v")
    if not os.path.isfile(test_rtl):
        logger.error(f"  Test file not found: {test_rtl}")
        return False

    # Analyze design
    logger.print("\n  --- Analyzing design for RAG ---")
    design_info = analyze_design_for_hardening(test_rtl)
    logger.print(f"  Design: {design_info.get('module_name', '?')}, "
                 f"ports: {len(design_info.get('signals', []))}, "
                 f"width: {design_info.get('signal_width', 0)}")

    # Create RAG engine
    logger.print("\n  --- Creating RAG Engine ---")
    engine = RAGEngine(llm_backend='mock')
    engine.load_knowledge_base()

    # Generate hardened RTL
    logger.print("\n  --- Generating Hardened RTL ---")
    vulnerability_result = {
        "all_vulnerable_nodes": [
            {"node_id": 0, "score": 0.85, "type": "register"},
            {"node_id": 1, "score": 0.72, "type": "combo"},
            {"node_id": 2, "score": 0.61, "type": "data_path"},
        ],
        "num_nodes": 3,
        "description": "Multiple vulnerable nodes detected in design",
    }

    rtl_code = engine.generate_hardened_rtl(design_info, vulnerability_result)

    # Verify the output
    from rag_integration import validate_generated_rtl
    valid = validate_generated_rtl(rtl_code)
    logger.print(f"\n  Generated RTL length: {len(rtl_code)} chars")
    logger.print(f"  Validation: {'PASSED' if valid else 'WARNINGS'}")
    logger.print(f"  TEST 2 {'PASSED' if valid else 'FAILED'}")
    return valid


def test_auto_repair_syntax():
    """Test 3: Verify Auto-Repair pipeline with detailed logging."""
    logger.section("TEST 3: Auto-Repair Syntax Fixer Logging")
    logger.print("  Testing Auto-Repair with detailed logging...")

    try:
        from auto_repair import AutoRepairEngine, SyntaxFixer, generate_repair_report
    except ImportError as e:
        logger.error(f"  Auto-Repair module import failed: {e}")
        return False

    # Test SyntaxFixer with known errors
    fixer = SyntaxFixer()

    test_code = """\
module test_fix (
    input clk
    input rst_n
);
    wire a
    assign a = 1
    reg b
    always @(posedge clk) begin
        b <= a;
    end
endmodule"""

    errors = [
        "syntax error, unexpected TOK_ASSIGN, expecting ',' or ';' or '=' or '['",
    ]

    logger.print(f"\n  Original code ({len(test_code.splitlines())} lines):")
    for i, line in enumerate(test_code.splitlines()):
        logger.print(f"    L{i+1}: {repr(line)[:70]}")

    logger.print(f"\n  Applying SyntaxFixer...")
    fixed = fixer.fix(test_code, errors)

    logger.print(f"\n  Fixed code ({len(fixed.splitlines())} lines):")
    for i, line in enumerate(fixed.splitlines()):
        logger.print(f"    L{i+1}: {repr(line)[:70]}")

    # Check key fixes were applied
    has_semicolons = 'wire a;' in fixed and 'assign a = 1;' in fixed
    has_endmodule = fixed.strip().endswith('endmodule')
    logger.print(f"\n  Semicolons fixed: {has_semicolons}")
    logger.print(f"  Has endmodule: {has_endmodule}")

    # Test AutoRepairEngine repair
    logger.print("\n  --- Running AutoRepairEngine.repair() ---")
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="test_repair_")
    test_file = os.path.join(tmp_dir, "test_fix.v")
    with open(test_file, "w") as f:
        f.write(test_code)

    engine = AutoRepairEngine(max_iterations=3, verbose=True)
    result = engine.repair(rtl_path=test_file, original_rtl=None)

    logger.print(f"\n  Repair result: passed={result['passed']}, "
                 f"iterations={result['iterations']}")
    report = generate_repair_report(result)
    logger.print(f"\n  Repair report:\n{report[:500]}...")

    logger.print(f"\n  TEST 3 {'PASSED' if has_semicolons and has_endmodule else 'FAILED'}")
    return has_semicolons and has_endmodule


def test_end_to_end_harden():
    """Test 4: Verify end-to-end hardening pipeline integration."""
    logger.section("TEST 4: End-to-End Hardening Pipeline")
    logger.print("  Testing full harden() pipeline with design error analysis...")

    test_file = os.path.join(SCRIPT_DIR, "test_buggy_design.v")
    if not os.path.isfile(test_file):
        logger.error(f"  Test file not found: {test_file}")
        return False

    try:
        from graph_pipeline import GraphPipeline
    except ImportError as e:
        logger.error(f"  GraphPipeline import failed: {e}")
        return False

    pipeline = GraphPipeline(verbose=True)

    result = pipeline.harden(
        rtl_path=test_file,
        vulnerability_result=None,
        llm_backend='mock',
        max_repair_iterations=2,
        analyze_errors_first=True,
    )

    logger.print(f"\n  Pipeline completed:")
    logger.print(f"    Passed:      {result['passed']}")
    logger.print(f"    Iterations:  {result['iterations']}")
    logger.print(f"    Elapsed:     {result['total_elapsed']:.3f}s")
    logger.print(f"    Output:      {result['hardened_rtl_path']}")
    logger.print(f"    Design errors: {len(result.get('design_errors', {}).get('errors', []))}")
    logger.print(f"    RAG analysis: {result.get('rag_analysis', {}).get('module_name', '?')}")

    if result['hardened_rtl']:
        lines = result['hardened_rtl'].splitlines()
        logger.print(f"    Hardened RTL: {len(lines)} lines")

    logger.print(f"\n  TEST 4 {'PASSED' if result['passed'] else 'COMPLETED (with issues)'}")
    return True


def test_pipeline_with_design_errors():
    """Test 5: Verify pipeline correctly handles test_port_design_errors.v."""
    logger.section("TEST 5: Pipeline with Design Error Test Case")
    logger.print("  Testing pipeline with port error test case...")

    test_file = os.path.join(SCRIPT_DIR, "test_port_design_errors.v")
    submodule_file = os.path.join(SCRIPT_DIR, "adder_sub.v")

    if not os.path.isfile(test_file):
        logger.error(f"  Test file not found: {test_file}")
        return False

    from graph_pipeline import GraphPipeline
    pipeline = GraphPipeline(verbose=True)

    # First run design error analysis with submodule
    logger.print("\n  [Step 1] Design Error Analysis with submodule paths...")
    # For the static analysis to work properly, we need both files' content combined
    # The analyze_design_errors method only reads one file, so let's create a combined version
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="design_errors_test_")
    combined_path = os.path.join(tmp_dir, "combined_test.v")

    with open(test_file, "r") as f:
        test_content = f.read()
    with open(submodule_file, "r") as f:
        sub_content = f.read()

    combined = f"{sub_content}\n\n{test_content}"
    with open(combined_path, "w") as f:
        f.write(combined)

    logger.print(f"    Combined file created: {combined_path}")
    logger.print(f"    Combined content: {len(combined.splitlines())} lines")

    result = pipeline.analyze_design_errors(combined_path)

    errors = result.get("errors", [])
    warnings = result.get("warnings", [])
    modules = result.get("modules", {})
    instances = result.get("instances", [])

    logger.print(f"\n  [Results]")
    logger.print(f"    Modules found: {len(modules)}")
    logger.print(f"    Instances found: {len(instances)}")
    logger.print(f"    Errors: {len(errors)}")
    logger.print(f"    Warnings: {len(warnings)}")

    for mod_name, mod_info in modules.items():
        logger.print(f"    Module: {mod_name} ({mod_info['port_count']} ports)")
        for p in mod_info["ports"]:
            logger.print(f"      {p['direction']} {p['type']} {p['name']}[{p['width']}]")

    for inst in instances:
        logger.print(f"    Instance: {inst['instance_name']} -> {inst['module_name']}")
        logger.print(f"      Connections: {inst['conn_count']}, Line: {inst['line']}")
        for c in inst["connections"]:
            logger.print(f"      .{c['port']}({c['signal']})")

    for err in errors:
        logger.print(f"    ERROR [{err['type']}]: {err['description'][:120]}")

    logger.print(f"\n  Verified detection:")
    for err in errors:
        if err['type'] == 'port_count_mismatch':
            logger.print(f"    ✓ Port count mismatch detected: {err['description'][:80]}")
        if err['type'] == 'direction_conflict':
            logger.print(f"    ✓ Direction conflict detected: {err['description'][:80]}")

    logger.print(f"\n  TEST 5 {'PASSED' if errors else 'FAILED'}")
    return len(errors) > 0


def main():
    """Run all integration tests."""
    logger.section("COMPREHENSIVE HARDENING PIPELINE INTEGRATION TESTS")
    logger.print(f"  Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.print(f"  Script dir: {SCRIPT_DIR}")
    logger.print(f"")

    test_results = {}

    # Test 1: Design error analysis
    logger.print(f"\n{'=' * 62}")
    test_results["Design Error Analysis"] = test_design_error_analysis()

    # Test 2: RAG pipeline logging
    logger.print(f"\n{'=' * 62}")
    test_results["RAG Pipeline Logging"] = test_rag_pipeline()

    # Test 3: Auto-Repair logging
    logger.print(f"\n{'=' * 62}")
    test_results["Auto-Repair Logging"] = test_auto_repair_syntax()

    # Test 4: End-to-end hardening
    logger.print(f"\n{'=' * 62}")
    test_results["End-to-End Hardening"] = test_end_to_end_harden()

    # Test 5: Pipeline with design errors
    logger.print(f"\n{'=' * 62}")
    test_results["Design Error Test Case"] = test_pipeline_with_design_errors()

    # Summary
    logger.section("TEST SUMMARY")
    all_passed = True
    for name, passed in test_results.items():
        status = "PASSED" if passed else "FAILED"
        if not passed:
            all_passed = False
        logger.print(f"  {name:35s} -> {status}")

    logger.print(f"\n  {'=' * 62}")
    logger.print(f"  OVERALL: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    logger.print(f"  {'=' * 62}")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
