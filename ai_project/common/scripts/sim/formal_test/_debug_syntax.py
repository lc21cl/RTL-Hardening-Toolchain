#!/usr/bin/env python3
"""Debug syntax_check - what yosys returns"""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verification_engine import VerificationEngine

v = VerificationEngine(verbose=True)
r = v.syntax_check(r'D:\learning\AI_RESEARCH\ai_project\common\scripts\test_mock_data\dice_template.v')
print("pass:", r['passed'])
print("elapsed:", r['elapsed'])
print("errors:", r['errors'][:3] if r['errors'] else "[] (no errors)")
print("warnings:", r['warnings'][:3] if r['warnings'] else "[] (no warnings)")

# Check what yosys actually returns
yosys_path = r'D:\learning\AI_RESEARCH\tools\oss-cad-suite\oss-cad-suite\bin\yosys.exe'
script = "read_verilog -sv " + r'D:\learning\AI_RESEARCH\ai_project\common\scripts\test_mock_data\dice_template.v'
env = os.environ.copy()
yosys_dir = os.path.dirname(os.path.abspath(yosys_path))
lib_dir = os.path.join(os.path.dirname(yosys_dir), 'lib')
if os.path.isdir(lib_dir):
    env['PATH'] = f"{yosys_dir};{lib_dir};{env.get('PATH','')}"
else:
    env['PATH'] = f"{yosys_dir};{env.get('PATH','')}"

proc = subprocess.run([yosys_path, '-p', script], capture_output=True, text=True, timeout=30)
print("\nReturn code:", proc.returncode)
# Check if return code 0 = pass in the engine
from verification_engine import _parse_syntax_errors
errs, warns = _parse_syntax_errors(proc.stdout + proc.stderr)
print("Parsed errors:", errs[:3] if errs else "[]")
print("Parsed warnings:", warns[:3] if warns else "[]")
