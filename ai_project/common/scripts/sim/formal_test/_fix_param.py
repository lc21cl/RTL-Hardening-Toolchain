#!/usr/bin/env python3
"""Fix the missing_parameter_default replacement pattern."""
FILE = r"d:\learning\AI_RESEARCH\ai_project\common\scripts\sim\formal_test\auto_repair.py"

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# The old pattern incorrectly uses \g<0> which keeps the trailing comma
old = r"r'\g<0> = 0'),\n"
new = r"r'parameter \1 = 0'),\n"

if old in content:
    content = content.replace(old, new)
    with open(FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed: restored correct parameter replacement")
else:
    print("Pattern not found - checking what's there...")
    idx = content.find('missing_parameter_default')
    if idx > 0:
        print(repr(content[idx:idx+150]))
