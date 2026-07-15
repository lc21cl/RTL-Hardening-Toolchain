#!/usr/bin/env python3
"""Debug script to test SyntaxFixer in isolation."""
import sys
sys.path.insert(0, ".")

from auto_repair import SyntaxFixer

with open("test_buggy_design.v", "r") as f:
    content = f.read()

print("=== ORIGINAL ===")
lines = content.split("\n")
for i, line in enumerate(lines):
    print(f"  L{i+1:2d}: {repr(line)}")

fixer = SyntaxFixer()

# Simulate the first error from yosys
errors = [
    r"C:\test_buggy_design.v:21: ERROR: syntax error, unexpected TOK_ASSIGN, expecting ',' or ';' or '=' or '["
]

fixed = fixer.fix(content, errors)
fixed_lines = fixed.split("\n")

print("\n=== CHANGED LINES ===")
for i, (a, b) in enumerate(zip(lines, fixed_lines)):
    if a != b:
        print(f"  L{i+1:2d}: {repr(a)}")
        print(f"       -> {repr(b)}")

print("\n=== FIXED FULL ===")
for i, line in enumerate(fixed_lines):
    print(f"  L{i+1:2d}: {repr(line)}")
