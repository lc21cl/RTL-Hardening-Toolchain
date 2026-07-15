"""Synthesize multiple Verilog designs to BLIF using OSS CAD Suite Yosys."""
import subprocess, os, sys

# OSS CAD Suite environment
OSS_DIR = r"D:\learning\AI_RESEARCH\oss-cad-suite"
ENV_SCRIPT = os.path.join(OSS_DIR, "environment.ps1")
YOSYS = os.path.join(OSS_DIR, "bin", "yosys.exe")

# Input/output dirs
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MOCK_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', 'test_mock_data'))

DESIGNS = [
    # (verilog_file, top_module)
    ("counter_demo_input.v", "counter_demo_input"),
    ("ecc_register_dft.v", "ecc_register_dft"),
    ("cnt_comp_template.v", "cnt_comp_template"),
    ("parity_template.v", "parity_template"),
    ("mixed_design_ecc.v", "mixed_design_ecc"),
    ("mixed_design_hardened.v", "mixed_design_hardened"),
]

def run_yosys_script(script: str) -> tuple:
    """Run a yosys script via stdin."""
    cmd = f'cd "{MOCK_DIR}"; & "{ENV_SCRIPT}"; echo "{"$"*0}" | & "{YOSYS}" -s - 2>&1'
    full_cmd = f'cd "{MOCK_DIR}"; & "{ENV_SCRIPT}"; {script} | & "{YOSYS}" -s - 2>&1'
    result = subprocess.run(
        ["powershell", "-Command", full_cmd],
        capture_output=True, text=True, cwd=MOCK_DIR
    )
    return result.stdout, result.stderr

for vfile, top in DESIGNS:
    vpath = os.path.join(MOCK_DIR, vfile)
    blif_path = os.path.join(MOCK_DIR, f"output_{top}.blif")
    
    if not os.path.exists(vpath):
        print(f"SKIP: {vfile} not found")
        continue
    
    # Check if BLIF already exists and is newer than V
    if os.path.exists(blif_path):
        vtime = os.path.getmtime(vpath)
        btime = os.path.getmtime(blif_path)
        if btime > vtime:
            print(f"SKIP: {blif_path} already up-to-date")
            continue
    
    print(f"Synth: {vfile} -> output_{top}.blif")
    ps_cmd = (
        f'echo "read_verilog {vfile}; "
        f'synth -top {top}; '
        f'write_blif output_{top}.blif; '
        f'exit" | & "{YOSYS}" -s -'
    )
    full_cmd = f'cd "{MOCK_DIR}"; & "{ENV_SCRIPT}"; {ps_cmd}'
    result = subprocess.run(
        ["powershell", "-Command", full_cmd],
        capture_output=True, text=True, cwd=MOCK_DIR,
        timeout=120
    )
    if os.path.exists(blif_path):
        size = os.path.getsize(blif_path)
        print(f"  OK: {blif_path} ({size} bytes)")
    else:
        print(f"  FAIL: {result.stdout[-500:]}")
        print(f"  STDERR: {result.stderr[-500:]}")
