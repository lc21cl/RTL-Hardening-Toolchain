#!/usr/bin/env python3
"""Verify all core imports work correctly."""
import sys, os
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
os.chdir(_SCRIPT_DIR)

print("=== Core Import Verification ===")

# 1. yosys_utils
from yosys_utils import find_yosys, yosys_env, check_yosys_availability, clear_yosys_cache
print(f"  [OK] yosys_utils")
print(f"  find_yosys() = {find_yosys()}")
avail = check_yosys_availability()
print(f"  yosys available = {avail['available']}, path = {avail['path']}")

# 2. rtl_parser
from rtl_parser import strip_rtl_comments, extract_module_name, extract_module_name_from_file, extract_ports, extract_signals
print(f"  [OK] rtl_parser")
mod_name = extract_module_name_from_file("test_complex_repair.v")
print(f"  module name = {mod_name}")

# 3. auto_repair
from auto_repair import AutoRepairEngine, SyntaxFixer, SynthesisFixer, EquivFixer
from auto_repair import generate_repair_report, RepairStrategy, hardening_with_repair
print(f"  [OK] auto_repair")
print(f"  ALL IMPORTS VERIFIED SUCCESSFULLY")
