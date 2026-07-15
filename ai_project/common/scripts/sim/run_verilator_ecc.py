#!/usr/bin/env python3
"""
run_verilator_ecc.py — Verilator ECC 验证运行器

功能:
  1. 检查 Verilator 是否可用
  2. 若可用: 运行 Verilator 编译 + 仿真
  3. 若不可用: 降级到 iverilog (graceful degradation)
  4. 输出 PASS/FAIL 汇总

用法:
  python run_verilator_ecc.py
  python run_verilator_ecc.py --trace     # 生成 VCD 波形
  python run_verilator_ecc.py --sim iverilog  # 强制使用 iverilog
"""

import subprocess
import os
import sys
import argparse
import re

# ---- 路径配置 ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
TEST_MOCK_DIR = os.path.normpath(os.path.join(PROJECT_ROOT, "test_mock_data"))

ECC_DFT_SRC    = os.path.normpath(os.path.join(TEST_MOCK_DIR, "ecc_register_dft.v"))
SIM_MAIN_CPP   = os.path.normpath(os.path.join(SCRIPT_DIR, "sim_main.cpp"))
IVERILOG_TB    = os.path.normpath(os.path.join(TEST_MOCK_DIR, "tb_ecc_dft.v"))


def check_verilator():
    """检查 Verilator 是否在 PATH 中"""
    try:
        # Windows: where, Linux/Mac: which
        if sys.platform == "win32":
            result = subprocess.run(
                ["where", "verilator"],
                capture_output=True, text=True, timeout=10
            )
        else:
            result = subprocess.run(
                ["which", "verilator"],
                capture_output=True, text=True, timeout=10
            )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_iverilog():
    """检查 iverilog 是否在 PATH 中"""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["where", "iverilog"],
                capture_output=True, text=True, timeout=10
            )
        else:
            result = subprocess.run(
                ["which", "iverilog"],
                capture_output=True, text=True, timeout=10
            )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def run_verilator(trace=False):
    """用 Verilator 编译并仿真

    步骤:
      1. verilator --cc ecc_register_dft.v --exe sim_main.cpp
      2. make -C obj_dir -f Vecc_register_dft.mk
      3. ./obj_dir/Vecc_register_dft
    """
    build_dir = os.path.join(SCRIPT_DIR, "obj_dir")
    sim_exe   = os.path.join(build_dir, "Vecc_register_dft")

    if not os.path.isfile(ECC_DFT_SRC):
        print(f"ERROR: 找不到 ECC DFT 源文件: {ECC_DFT_SRC}")
        return None
    if not os.path.isfile(SIM_MAIN_CPP):
        print(f"ERROR: 找不到 C++ testbench: {SIM_MAIN_CPP}")
        return None

    # ---- Step 1: Verilator 编译 ----
    print("=" * 60)
    print("Verilator 编译阶段")
    print("=" * 60)

    verilator_cmd = [
        "verilator",
        "--cc",
        "--exe",
        "--build",
        "-O3",
        "--top-module", "ecc_register_dft",
        "-Wno-WIDTH",
        "-Wno-CASEINCOMPLETE",
        "-Wno-UNOPTFLAT",
        "-Mdir", build_dir,
        ECC_DFT_SRC,
        SIM_MAIN_CPP,
    ]

    if trace:
        verilator_cmd.insert(3, "--trace")  # 在 --cc 后插入 --trace

    print(f"运行: {' '.join(verilator_cmd)}")
    result = subprocess.run(
        verilator_cmd,
        cwd=SCRIPT_DIR,
        capture_output=True, text=True, timeout=300
    )

    print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)

    if result.returncode != 0:
        print("VERILATOR COMPILATION FAILED")
        print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        return None

    # ---- Step 2: 运行仿真 ----
    print("\n" + "=" * 60)
    print("Verilator 仿真阶段")
    print("=" * 60)

    if not os.path.isfile(sim_exe):
        print(f"ERROR: 仿真可执行文件不存在: {sim_exe}")
        return None

    sim_cmd = [sim_exe]
    if trace:
        sim_cmd.append("--trace")

    print(f"运行: {' '.join(sim_cmd)}")
    result = subprocess.run(
        sim_cmd,
        cwd=SCRIPT_DIR,
        capture_output=True, text=True, timeout=300
    )

    print(result.stdout)

    if trace and os.path.isfile(os.path.join(SCRIPT_DIR, "ecc_dft_trace.vcd")):
        print(f"VCD 波形已生成: {os.path.join(SCRIPT_DIR, 'ecc_dft_trace.vcd')}")

    return result.stdout


def run_iverilog(trace=False):
    """用 iverilog 仿真 (降级方案)"""
    print("=" * 60)
    print("Iverilog 仿真 (降级方案)")
    print("=" * 60)

    if not os.path.isfile(ECC_DFT_SRC):
        print(f"ERROR: 找不到 ECC DFT 源文件: {ECC_DFT_SRC}")
        return None

    # 生成 iverilog testbench (如果不存在)
    if not os.path.isfile(IVERILOG_TB):
        print(f"WARNING: iverilog testbench 不存在: {IVERILOG_TB}")
        print(f"尝试使用现有的 tb_ecc.v (需要修改以适配 DFT 端口)...")
        # 回退到 tb_ecc.v 但可能不支持 DFT 端口
        iv_tb = os.path.normpath(os.path.join(TEST_MOCK_DIR, "tb_ecc.v"))
        if not os.path.isfile(iv_tb):
            print(f"ERROR: 也无 tb_ecc.v 可用")
            return None
    else:
        iv_tb = IVERILOG_TB

    # 编译
    compile_cmd = [
        "iverilog",
        "-o", os.path.join(SCRIPT_DIR, "ecc_dft_sim"),
        "-g2012",
        ECC_DFT_SRC,
        iv_tb,
    ]

    print(f"编译: {' '.join(compile_cmd)}")
    result = subprocess.run(
        compile_cmd,
        cwd=SCRIPT_DIR,
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        print("IVERILOG COMPILATION FAILED")
        print(result.stderr[-2000:])
        return None

    # 运行
    vvp_exe = os.path.join(SCRIPT_DIR, "ecc_dft_sim")
    if trace:
        # iverilog + vvp 默认生成 vcd
        pass

    print(f"运行: {vvp_exe}")
    result = subprocess.run(
        [vvp_exe],
        cwd=SCRIPT_DIR,
        capture_output=True, text=True, timeout=120
    )

    print(result.stdout)
    return result.stdout


def parse_results(output):
    """解析 PASS/FAIL 计数"""
    if output is None:
        return 0, 0

    pass_match = re.search(r'(\d+)\s*PASS', output)
    fail_match = re.search(r'(\d+)\s*FAIL', output)

    pass_cnt = int(pass_match.group(1)) if pass_match else 0
    fail_cnt = int(fail_match.group(1)) if fail_match else 0

    return pass_cnt, fail_cnt


def main():
    parser = argparse.ArgumentParser(
        description="Verilator ECC 验证运行器 (可降级到 iverilog)"
    )
    parser.add_argument(
        "--sim", choices=["verilator", "iverilog", "auto"],
        default="auto",
        help="选择仿真器 (默认: auto 自动检测)"
    )
    parser.add_argument(
        "--trace", action="store_true",
        help="生成 VCD 波形"
    )
    args = parser.parse_args()

    # ---- 选择仿真器 ----
    sim_choice = args.sim

    if sim_choice == "auto":
        if check_verilator():
            sim_choice = "verilator"
            print("[INFO] 检测到 Verilator, 使用 Verilator 仿真")
        elif check_iverilog():
            sim_choice = "iverilog"
            print("[INFO] 未检测到 Verilator, 降级到 iverilog")
        else:
            print("[ERROR] 未检测到任何仿真器 (verilator / iverilog)")
            print("请安装 Verilator 或 iverilog")
            sys.exit(1)
    elif sim_choice == "verilator" and not check_verilator():
        print("[ERROR] 指定使用 Verilator, 但未检测到 verilator 命令")
        if check_iverilog():
            print("提示: 使用 --sim iverilog 以降级到 iverilog")
        sys.exit(1)
    elif sim_choice == "iverilog" and not check_iverilog():
        print("[ERROR] 指定使用 iverilog, 但未检测到 iverilog 命令")
        sys.exit(1)

    # ---- 运行仿真 ----
    if sim_choice == "verilator":
        output = run_verilator(trace=args.trace)
    else:
        output = run_iverilog(trace=args.trace)

    # ---- 解析结果 ----
    pass_cnt, fail_cnt = parse_results(output)

    print("\n" + "=" * 60)
    print(f"ECC DFT Verification Summary")
    print(f"  Simulator:  {sim_choice}")
    print(f"  PASS count: {pass_cnt}")
    print(f"  FAIL count: {fail_cnt}")
    print("=" * 60)

    if fail_cnt == 0 and pass_cnt > 0:
        print("  *** ALL TESTS PASSED ***")
        sys.exit(0)
    elif output is not None:
        print("  *** SOME TESTS FAILED ***")
        sys.exit(1)
    else:
        print("  *** SIMULATION FAILED TO COMPLETE ***")
        sys.exit(1)


if __name__ == "__main__":
    main()
