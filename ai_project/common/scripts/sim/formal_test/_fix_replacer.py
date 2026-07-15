#!/usr/bin/env python3
"""Fix the _safe_sub._replacer to use m.expand() instead of re.sub()."""
FILE = r"d:\learning\AI_RESEARCH\ai_project\common\scripts\sim\formal_test\auto_repair.py"

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix _replacer: use m.expand(replacement) instead of re.sub(pattern, replacement, m.group(0))
old = """        def _replacer(m: re.Match) -> str:
            if _in_comment(m.start(), len(m.group(0))):
                return m.group(0)
            return re.sub(pattern, replacement, m.group(0), count=1, flags=flags)"""

new = """        def _replacer(m: re.Match) -> str:
            if _in_comment(m.start()):
                return m.group(0)
            return m.expand(replacement)"""

# Also try without the len parameter
old2 = """        def _replacer(m: re.Match) -> str:
            if _in_comment(m.start()):
                return m.group(0)
            return re.sub(pattern, replacement, m.group(0), count=1, flags=flags)"""

if old in content:
    content = content.replace(old, new)
    print("Fix applied: _replacer now uses m.expand() (match_len version)")
elif old2 in content:
    content = content.replace(old2, new)
    print("Fix applied: _replacer now uses m.expand() (simple version)")
else:
    print("Neither pattern found!")
    idx = content.find('def _replacer')
    if idx >= 0:
        print("Found at", idx)
        print(repr(content[idx:idx+300]))

# Also fix the _in_comment to include block comment check (currently dead code after return)
old_bc = """            return False
            # Block comment (unclosed)
            last_open = pre.rfind('/*')
            if last_open > pre.rfind('*/'):
                return True
            return"""

new_bc = """            # Block comment (unclosed)
            last_open = pre.rfind('/*')
            if last_open > pre.rfind('*/'):
                return True
            return False"""

if old_bc in content:
    content = content.replace(old_bc, new_bc)
    print("Fix applied: block comment detection restored")
else:
    print("Block comment pattern not found")

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
