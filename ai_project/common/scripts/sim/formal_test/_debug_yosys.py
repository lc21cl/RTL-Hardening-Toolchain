#!/usr/bin/env python3
"""Debug yosys subprocess env issue"""
import os, subprocess, sys

yosys_path = r'D:\learning\AI_RESEARCH\tools\oss-cad-suite\oss-cad-suite\bin\yosys.exe'
yosys_bin = os.path.dirname(os.path.abspath(yosys_path))
lib_dir = os.path.join(os.path.dirname(yosys_bin), 'lib')

print(f"yosys_bin: {yosys_bin} exists={os.path.isdir(yosys_bin)}")
print(f"lib_dir: {lib_dir} exists={os.path.isdir(lib_dir)}")

# Build env exactly like _yosys_env
env = os.environ.copy()
paths_to_add = []
if yosys_bin not in env.get('PATH', ''):
    paths_to_add.append(yosys_bin)
if os.path.isdir(lib_dir) and lib_dir not in env.get('PATH', ''):
    paths_to_add.append(lib_dir)
if paths_to_add:
    env['PATH'] = ';'.join(paths_to_add) + ';' + env.get('PATH', '')

# Check env PATH entries
for p in env['PATH'].split(';'):
    if 'oss-cad' in p.lower():
        print(f"  PATH: {p}")

# Test 1: Direct path
proc = subprocess.run([yosys_path, '--version'], capture_output=True, text=True, timeout=30, env=env)
print(f"\nDirect: rc={hex(proc.returncode)} out='{proc.stdout.strip()[:60]}'")

# Test 2: Just 'yosys' from PATH
proc2 = subprocess.run(['yosys', '--version'], capture_output=True, text=True, timeout=30, env=env)
print(f"PATH:   rc={hex(proc2.returncode)} out='{proc2.stdout.strip()[:60]}'")

# Test 3: With shell=True
import subprocess
cmd = f'"{yosys_path}" --version'
proc3 = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env, shell=True)
print(f"Shell:  rc={hex(proc3.returncode)} out='{proc3.stdout.strip()[:60]}'")
