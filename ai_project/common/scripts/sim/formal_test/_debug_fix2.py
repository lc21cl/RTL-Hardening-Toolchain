#!/usr/bin/env python3
"""Test SyntaxFixer with encoding-safe file reading."""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

from auto_repair import SyntaxFixer

fixer = SyntaxFixer()

# Test 1: Simple parameter case
content = """module test #(
    parameter DATA_WIDTH,
    parameter ADDR_WIDTH = 8
);
    wire a;
    assign a = 1;
endmodule
"""

for priority, name, search, replace in fixer._FIX_PATTERNS:
    if name == 'missing_parameter_default':
        print(f"Test 1: {name}")
        # Test _safe_sub
        fixed = fixer._safe_sub(search, replace, content)
        if fixed != content:
            print(f"  PASS: _safe_sub applied change")
            print(f"  DATA_WIDTH = 0" in fixed and "PASS" or "FAIL" )
        else:
            print(f"  FAIL: _safe_sub made no change")
        break

# Test 2: Test with real file (read with utf-8 encoding)
test_file = os.path.join(os.path.dirname(__file__), "test_complex_repair.v")
with open(test_file, 'r', encoding='utf-8') as f:
    complex_content = f.read()

errors = ["syntax error, expecting ';'"]
fixed = fixer.fix(complex_content, errors)

checks = [
    ("inout wire", "inout_without_direction"),
    ("endgenerate\nendmodule", "missing_endgenerate"),
    ("debug_bus;", "missing_semicolon_decl (line)"),
    ("DATA_WIDTH = 0", "missing_parameter_default"),
    ("posedge clk or", "missing_seq_sensitivity_or"),
    ("default :", "missing_case_default"),
]

print(f"\nTest 2: Complex file ({len(complex_content)} → {len(fixed)} chars)")
all_pass = True
for pattern, desc in checks:
    found = pattern in fixed
    if not found:
        all_pass = False
    status = "PASS" if found else "FAIL"
    print(f"  [{status}] {desc}")

# Check for bad artifacts
bad = [",;", ");;"]
for b in bad:
    if b in fixed:
        # Check position
        idx = fixed.index(b)
        ctx = fixed[max(0,idx-30):idx+30]
        print(f"  WARN: artifact '{b}' at pos {idx}: ...{repr(ctx)}...")

print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
