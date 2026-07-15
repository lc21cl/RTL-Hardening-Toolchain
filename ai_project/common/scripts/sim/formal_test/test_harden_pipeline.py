#!/usr/bin/env python3
"""
test_harden_pipeline.py — 完整加固流水线闭环测试

测试三个层面:
  1. Auto-Repair 修复语法错误的测试用例
  2. RAG 知识库检索 + 生成的端到端流程
  3. GraphPipeline.harden() 全自动加固流水线
"""

import os
import sys
import time

sys.path.insert(0, ".")

# ============================================================================
# Test 1: Auto-Repair 修复含有语法错误和端口不匹配的设计
# ============================================================================

print("\n" + "=" * 62)
print("  Test 1: Auto-Repair — Buggy Design with Syntax Errors")
print("=" * 62)

BUGGY_RTL = "test_buggy_design.v"
assert os.path.isfile(BUGGY_RTL), f"Test file not found: {BUGGY_RTL}"

# Read original for equivalence check
with open(BUGGY_RTL, "r") as f:
    original_content = f.read()
print(f"  Original RTL: {len(original_content)} chars")
print(f"  Intended errors: missing semicolons (L20, L21), old-style ports, port mismatch")

from auto_repair import AutoRepairEngine, generate_repair_report

engine = AutoRepairEngine(max_iterations=5, verbose=True)

# NOTE: original_rtl=None because the buggy design has syntax errors itself,
# so equivalence checking against it is not meaningful. We focus on verifying
# that syntax + synthesis checks pass after repair.
_t0 = time.time()
result = engine.repair(rtl_path=BUGGY_RTL, original_rtl=None)
_t1 = time.time()

print(f"\n  Repair {'PASSED' if result['passed'] else 'FAILED'} "
      f"after {result['iterations']} iteration(s) ({_t1 - _t0:.3f}s)")

# Show stage history
print(f"\n  Stage History:")
for i, stage in enumerate(result.get("stages", []), 1):
    stage_name = stage.get("stage", "?")
    stage_passed = stage.get("passed", False)
    errors = stage.get("errors", [])
    detail = "OK" if stage_passed else (errors[0][:60] if errors else "Failed")
    print(f"    [{i}] {stage_name:<12} {'✅' if stage_passed else '❌'}  {detail}")

# Show final report
print(f"\n  Final Report:")
print(f"    {result['final_report']}")

report_md = generate_repair_report(result)

# ============================================================================
# Test 2: RAG Engine 端到端测试
# ============================================================================

print("\n" + "=" * 62)
print("  Test 2: RAG Engine — Knowledge Base + Hardened RTL Generation")
print("=" * 62)

from rag_integration import RAGEngine, analyze_design_for_hardening, validate_generated_rtl

rag = RAGEngine(llm_backend="mock")
rag.load_knowledge_base()

# Analyze the buggy design
design_info = analyze_design_for_hardening(BUGGY_RTL)
print(f"  Design Analysis:")
print(f"    Module:  {design_info['module_name']}")
print(f"    Ports:   {len(design_info['signals'])}")
print(f"    MaxWidth: {design_info['signal_width']}")

# Create a vulnerability result (simulating GNN output)
vuln_result = {
    "all_vulnerable_nodes": [
        {"node_id": 0, "score": 0.92, "type": "register", "signal_type": "data_out"},
        {"node_id": 1, "score": 0.78, "type": "register", "signal_type": "valid"},
        {"node_id": 2, "score": 0.65, "type": "combo", "signal_type": "internal_bus"},
    ],
    "num_nodes": 3,
    "description": "Register vulnerability detected in output data path",
}

_t2 = time.time()
rtl_generated = rag.generate_hardened_rtl(design_info, vuln_result)
_t3 = time.time()

print(f"\n  RAG Generation: {len(rtl_generated)} chars ({_t3 - _t2:.3f}s)")
print(f"  Validation: {'✅ PASSED' if validate_generated_rtl(rtl_generated) else '❌ FAILED'}")
print(f"  RTL Preview:")
for line in rtl_generated.split("\n")[:12]:
    print(f"    {line}")
if rtl_generated.count("\n") > 12:
    print(f"    ... ({rtl_generated.count('\n') - 12} more lines)")

# ============================================================================
# Test 3: GraphPipeline.harden() 完整流水线
# ============================================================================

print("\n" + "=" * 62)
print("  Test 3: GraphPipeline.harden() — Full Automated Pipeline")
print("=" * 62)

from graph_pipeline import GraphPipeline

pipeline = GraphPipeline(verbose=True)

# Create a simple clean design for hardening test
CLEAN_RTL = "test_clean_design.v"
clean_content = """\
module test_clean_design (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] data_in,
    output reg  [7:0] data_out
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            data_out <= 8'b0;
        else
            data_out <= data_in;
    end
endmodule
"""
with open(CLEAN_RTL, "w") as f:
    f.write(clean_content)

_t4 = time.time()
harden_result = pipeline.harden(
    rtl_path=CLEAN_RTL,
    llm_backend="mock",
    max_repair_iterations=3,
    output_dir="tmp_harden_test",
    keep_intermediate=True,
)
_t5 = time.time()

print(f"\n  Pipeline Result:")
print(f"    Status:     {'✅ PASSED' if harden_result['passed'] else '❌ FAILED'}")
print(f"    Iterations: {harden_result['iterations']}")
print(f"    Elapsed:    {harden_result['total_elapsed']:.3f}s")
print(f"    Output:     {harden_result['hardened_rtl_path']}")

if harden_result["hardened_rtl"]:
    final_lines = harden_result["hardened_rtl"].split("\n")
    print(f"    Final RTL:  {len(final_lines)} lines")
    for line in final_lines[:10]:
        print(f"      {line}")

# ============================================================================
# Summary
# ============================================================================

print("\n" + "=" * 62)
print("  Test Summary")
print("=" * 62)
print(f"  Test 1 (Auto-Repair):       {'✅ PASSED' if result['passed'] else '❌ FAILED'}")
print(f"  Test 2 (RAG Engine):        {'✅ PASSED' if validate_generated_rtl(rtl_generated) else '❌ FAILED'}")
print(f"  Test 3 (Pipeline.harden()): {'✅ PASSED' if harden_result['passed'] else '❌ FAILED'}")
print(f"{'=' * 62}")

# Cleanup temp files
for f in [CLEAN_RTL]:
    if os.path.isfile(f):
        os.remove(f)

print("\nAll tests completed.")
