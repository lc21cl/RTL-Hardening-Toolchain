#!/usr/bin/env python3
"""Debug the SyntaxFixer to understand the parameter issue."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from auto_repair import SyntaxFixer

fixer = SyntaxFixer()

# Test: does the parameter pattern match?
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
        print(f"Pattern: {name}")
        print(f"  search:   {search}")
        print(f"  replace:  {replace}")
        import re
        m = re.search(search, content, re.DOTALL)
        if m:
            print(f"  MATCH: {repr(m.group(0))}")
            print(f"  Replace result: {re.sub(search, replace, m.group(0), count=1, flags=re.DOTALL)}")
        else:
            print("  NO MATCH")
        
        # Test with raw regex
        m2 = re.search(r'parameter\s+(\w+)\s*(?=[,);])', content)
        if m2:
            print(f"  Raw regex MATCH: {repr(m2.group(0))}")
        
        # Test _safe_sub
        fixed = fixer._safe_sub(search, replace, content)
        if fixed != content:
            print(f"  _safe_sub WORKED!")
        else:
            print(f"  _safe_sub FAILED - no change")
        break

# Now test with the actual complex file
complex_file = os.path.join(os.path.dirname(__file__), "test_complex_repair.v")
with open(complex_file, 'r', encoding='utf-8') as f:
    complex_content = f.read()

print(f"\n--- Testing with complex file ({len(complex_content)} chars) ---")

errors = ["syntax error"]
fixed = fixer.fix(complex_content, errors)

# Check specific fixes
checks = [
    ("DATA_WIDTH = 0", "parameter_default"),
    ("endgenerate", "endgenerate present (should be >=1)"),
    ("default :", "case default"),
    ("posedge clk or", "sensitivity or"),
]
for pattern, desc in checks:
    found = pattern in fixed
    print(f"  {'PASS' if found else 'FAIL'}: {desc} ('{pattern}' {'found' if found else 'NOT found'})")

# Check no bad artifacts
bad_artifacts = [",;", ");;"]
for ba in bad_artifacts:
    if ba in fixed and ba not in complex_content:
        print(f"  WARN: artifact '{ba}' found in fixed output")
