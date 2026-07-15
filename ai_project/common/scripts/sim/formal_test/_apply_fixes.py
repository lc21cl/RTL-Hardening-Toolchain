#!/usr/bin/env python3
"""Apply targeted fixes to auto_repair.py based on test results."""
import re

FILE = r"d:\learning\AI_RESEARCH\ai_project\common\scripts\sim\formal_test\auto_repair.py"

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# ── Fix 1: Move comma-end check before input/output check ──
old1 = """            # input/output/inout declaration (outside port list)
            if re.match(r'(input|output|inout)\\s', stripped, re.IGNORECASE):
                fixed_lines.append(raw_line + ';')
                changes += 1
                continue

            # Submodule instantiation:  module_name #(...) inst_name (...);"""

new1 = """            # Lines ending with commas/parens/operators — no semicolon (port list)
            if stripped.endswith((',', '(', ')', '{', '}', '+', '-', '*', '/', '=', ':', '[')):
                fixed_lines.append(raw_line)
                continue

            # input/output/inout declaration (outside port list)
            if re.match(r'(input|output|inout)\\s', stripped, re.IGNORECASE):
                if not stripped.endswith(','):
                    fixed_lines.append(raw_line + ';')
                    changes += 1
                    continue
                else:
                    fixed_lines.append(raw_line)
                    continue

            # Submodule instantiation:  module_name #(...) inst_name (...);"""

if old1 in content:
    content = content.replace(old1, new1)
    changes += 1
    print("Fix 1 applied: comma check before input/output")
else:
    print("Fix 1 NOT applied: pattern not found")

# ── Fix 2: _safe_sub comment detection ──
old2 = """        def _in_comment(pos: int) -> bool:
            pre = content[:pos]
            # Single-line comment on same line
            line_start = pre.rfind('\\n') + 1
            if '//' in pre[line_start:]:
                return True"""

new2 = """        def _in_comment(pos: int) -> bool:
            pre = content[:pos]
            # Single-line comment on same line
            line_start = pre.rfind('\\n') + 1
            line_text = pre[line_start:]
            if '//' in line_text:
                # Only mark as comment if // is BEFORE the match
                comment_pos = line_text.find('//')
                return comment_pos < (pos - line_start)
            return False"""

if old2 in content:
    content = content.replace(old2, new2)
    changes += 1
    print("Fix 2 applied: _safe_sub comment detection")
else:
    print("Fix 2 NOT applied: _in_comment not found")

# ── Fix 3: missing_endgenerate pattern ──
old3 = """        # Unclosed generate block (missing endgenerate)
        (85, "missing_endgenerate",
         r'(\\bgenerate\\b(?:.*?\\n)*?)(?=\\bendmodule\\b)',
         r'\\1endgenerate\\n'),"""

new3 = """        # Unclosed generate block (missing endgenerate)  
        # Uses negative lookahead to skip generate blocks that already have endgenerate
        (85, "missing_endgenerate",
         r'\\bgenerate\\b(?![\\s\\S]*?\\bendgenerate\\b)[\\s\\S]*?(?=\\bendmodule\\b)',
         r'\\g<0>\\nendgenerate\\n'),"""

if old3 in content:
    content = content.replace(old3, new3)
    changes += 1
    print("Fix 3 applied: missing_endgenerate pattern")
else:
    print("Fix 3 NOT applied: generate pattern not found")

# ── Fix 4: missing_parameter_default — handle trailing comments ──
# The current pattern is fine, but we need to make it handle trailing comments
old4 = """        # Parameter without default value
        (50, "missing_parameter_default",
         r'parameter\\s+(\\w+)\\s*(?=[,);])',
         r'parameter \\1 = 0'),"""

new4 = """        # Parameter without default value
        (50, "missing_parameter_default",
         r'parameter\\s+(\\w+)\\s*(?=[,);])',
         r'\\g<0> = 0'),"""

if old4 in content:
    content = content.replace(old4, new4)
    changes += 1
    print("Fix 4 applied: missing_parameter_default")
else:
    print("Fix 4 NOT applied: param pattern not found")

# ── Fix 5: missing_case_default — better multi-line handling ──
old5 = """        # Case statement missing 'default' inside always block
        (25, "missing_case_default",
         r'case\\s*\\(.*?\\)\\s*\\n(.*?)\\n\\s*endcase',
         r'case \\1\\n        default : ;\\n    endcase'),"""

new5 = """        # Case statement missing 'default' inside always block
        (25, "missing_case_default",
         r'case\\s*\\(.*?\\)\\s*\\n(.*?)\\s*endcase',
         r'case \\1\\n        default : ;\\n    endcase'),"""

if old5 in content:
    content = content.replace(old5, new5)
    changes += 1
    print("Fix 5 applied: missing_case_default")
else:
    print("Fix 5 NOT applied: case pattern not found")

# Write back
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\nTotal fixes applied: {changes}")
