#!/usr/bin/env python3
"""Verify all imports work correctly after refactoring."""
import sys
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
os.chdir(_SCRIPT_DIR)

# Verify yosys_utils imports
print("=== Testing yosys_utils imports ===")
from yosys_utils import find_yosys, yosys_env, check_yosys_availability, clear_yosys_cache
print("  yosys_utils: OK")
print(f"  find_yosys() = {find_yosys()}")
avail = check_yosys_availability()
print(f"  check_yosys_availability() = {avail['available']}, path={avail['path']}")

# Verify rtl_parser imports
print("\n=== Testing rtl_parser imports ===")
from rtl_parser import strip_rtl_comments, extract_module_name, extract_module_name_from_file, extract_ports, extract_signals
print("  rtl_parser: OK")
mod_name = extract_module_name_from_file("test_complex_repair.v")
print(f"  extract_module_name('test_complex_repair.v') = {mod_name}")

# Verify auto_repair imports
print("\n=== Testing auto_repair imports ===")
from auto_repair import AutoRepairEngine, SyntaxFixer, SynthesisFixer, EquivFixer
from auto_repair import generate_repair_report, RepairStrategy, hardening_with_repair
print("  auto_repair: OK")

# Test SyntaxFixer on complex verilog
fixer = SyntaxFixer()
with open("test_complex_repair.v", "r", encoding="utf-8") as f:
    original = f.read()
fixed = fixer.fix(original, ["missing semicolon"])

checks = [
    ('debug_bus;' in fixed, 'semicolon before comment (debug_bus;)'),
    ('endgenerate' in fixed, 'endgenerate keyword added'),
    ('default : ;' in fixed, 'case default added'),
    ('posedge clk or negedge rst_n' in fixed, 'sensitivity list or added'),
    ('DATA_WIDTH = 0' in fixed, 'parameter default added'),
    ('; // [3]' in fixed or '; //' in fixed, 'semicolon before comment pattern'),
]
all_ok = True
for ok, desc in checks:
    print(f"  {'OK' if ok else 'FAIL'} {desc}")
    if not ok:
        all_ok = False

# Test AutoRepairEngine full pipeline
print("\n=== Testing AutoRepairEngine full pipeline ===")
engine = AutoRepairEngine(max_iterations=3, verbose=False)
result = engine.repair(rtl_path="test_complex_repair.v")
print(f"  AutoRepair pipeline: passed={result['passed']}, iterations={result['iterations']}")

print(f"\n=== OVERALL: {'ALL PASSED' if all_ok else 'SOME FAILED'} ===")
