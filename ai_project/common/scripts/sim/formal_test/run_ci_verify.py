#!/usr/bin/env python3
"""
run_ci_verify.py — CI 自动化验证脚本

定期在 CI 流水线中运行 graph_pipeline.py 的本地验证模式，
确保 oss-cad 依赖不会再次失效。

用法:
    # 完整验证（语法+综合）
    python run_ci_verify.py

    # 快速验证（仅语法）
    python run_ci_verify.py --quick

    # 同步报告到指定目录
    python run_ci_verify.py --report-dir ./ci_reports

    # 作为 GitHub Actions / Jenkins 步骤
    python run_ci_verify.py --ci-mode

退出码:
    0 — 全部通过
    1 — 语法检查失败
    2 — 综合检查失败
    3 — 管线硬化验证失败
    4 — yosys 不可用
"""

import os
import re
import sys
import json
import time
import datetime
import subprocess
from typing import Dict, List, Optional, Tuple

# 触发 yosys_docker 模块级 oss-cad PATH 初始化（确保子进程能找到 DLL）
try:
    from yosys_docker import _OSS_BIN, _OSS_LIB
except ImportError:
    _OSS_BIN = ""
    _OSS_LIB = ""

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', '..', '..', '..', '..'))

# ── 测试用例 ──
_TEST_RTL = os.path.join(_SCRIPT_DIR, "test_multi_strategy_harden.v")
_TEST_BUGGY_RTL = os.path.join(_SCRIPT_DIR, "test_buggy_design.v")

_EXIT_CODES = {
    "pass": 0,
    "syntax_fail": 1,
    "synthesis_fail": 2,
    "pipeline_fail": 3,
    "yosys_unavailable": 4,
}


def _log(msg: str):
    """带时间戳的日志输出。"""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def _run_cmd(cmd: List[str], timeout: int = 120, cwd: Optional[str] = None,
             env: Optional[Dict[str, str]] = None) -> Dict:
    """运行命令并返回结果。"""
    start = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=cwd or _SCRIPT_DIR, env=env,
        )
        elapsed = time.time() - start
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "elapsed": elapsed,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Timed out",
                "elapsed": time.time() - start}
    except FileNotFoundError as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e),
                "elapsed": time.time() - start}


def _check_yosys() -> Tuple[bool, str]:
    """检查 yosys 是否可用。"""
    _oss_yosys = os.path.join(_PROJECT_ROOT, "tools", "oss-cad-suite",
                              "oss-cad-suite", "bin", "yosys.exe")
    if os.path.isfile(_oss_yosys):
        return True, _oss_yosys

    # Fall back to PATH search
    result = _run_cmd(["where", "yosys"] if sys.platform == "win32" else ["which", "yosys"])
    if result["returncode"] == 0 and result["stdout"].strip():
        return True, result["stdout"].strip().splitlines()[0]
    return False, "not found"


def _verify_syntax(rtl_path: str) -> Dict:
    """使用 yosys 语法验证。"""
    _log(f"  Syntax check: {os.path.basename(rtl_path)}")

    import tempfile
    fd, ys_path = tempfile.mkstemp(suffix=".ys", dir=_SCRIPT_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            ext = os.path.splitext(rtl_path)[1].lower()
            read_cmd = "read_verilog -sv" if ext in (".v", ".sv") else "read_verilog"
            f.write(f"{read_cmd} {os.path.abspath(rtl_path)}\n")

        ok, yosys_path = _check_yosys()
        if not ok:
            return {"passed": False, "errors": ["yosys unavailable"],
                    "exit_code": _EXIT_CODES["yosys_unavailable"]}

        # 使用 oss-cad 的 PATH 环境
        env = os.environ.copy()
        _oss_lib = os.path.join(_PROJECT_ROOT, "tools", "oss-cad-suite",
                                "oss-cad-suite", "lib")
        _oss_bin = os.path.dirname(yosys_path)
        if os.path.isdir(_oss_bin):
            _prepend_paths = []
            for _d in (_oss_bin, _oss_lib if os.path.isdir(_oss_lib) else ''):
                if _d:
                    _prepend_paths.append(_d)
            if _prepend_paths:
                env['PATH'] = os.pathsep.join(_prepend_paths) + os.pathsep + env.get('PATH', '')

        result = _run_cmd(
            [yosys_path, "-s", ys_path],
            timeout=60,
            cwd=os.path.dirname(os.path.abspath(rtl_path)),
            env=env,
        )
        errors = [l for l in (result["stdout"] + result["stderr"]).split('\n')
                  if 'ERROR' in l.upper() or 'syntax error' in l.lower()]
        passed = result["returncode"] == 0 and not errors

        return {
            "passed": passed,
            "errors": errors,
            "returncode": result["returncode"],
            "elapsed": result["elapsed"],
            "exit_code": _EXIT_CODES["pass"] if passed else _EXIT_CODES["syntax_fail"],
        }
    finally:
        try:
            os.unlink(ys_path)
        except OSError:
            pass


def _verify_synthesis(rtl_path: str) -> Dict:
    """使用 yosys 综合验证。"""
    _log(f"  Synthesis check: {os.path.basename(rtl_path)}")

    ok, yosys_path = _check_yosys()
    if not ok:
        return {"passed": False, "errors": ["yosys unavailable"],
                "exit_code": _EXIT_CODES["yosys_unavailable"]}

    # 提取顶层模块
    top = None
    try:
        with open(rtl_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        m = re.search(r'\bmodule\s+(\w+)', content)
        if m:
            top = m.group(1)
    except OSError:
        pass

    top_flag = f" -top {top}" if top else ""

    import tempfile
    fd, ys_path = tempfile.mkstemp(suffix=".ys", dir=_SCRIPT_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"read_verilog {os.path.abspath(rtl_path)}\n")
            f.write(f"synth{top_flag}\n")
            f.write(f"stat\n")

        env = os.environ.copy()
        _oss_lib = os.path.join(_PROJECT_ROOT, "tools", "oss-cad-suite",
                                "oss-cad-suite", "lib")
        _oss_bin = os.path.dirname(yosys_path)
        if os.path.isdir(_oss_bin):
            _prepend_paths = []
            for _d in (_oss_bin, _oss_lib if os.path.isdir(_oss_lib) else ''):
                if _d:
                    _prepend_paths.append(_d)
            if _prepend_paths:
                env['PATH'] = os.pathsep.join(_prepend_paths) + os.pathsep + env.get('PATH', '')

        result = _run_cmd(
            [yosys_path, "-s", ys_path],
            timeout=120,
            cwd=os.path.dirname(os.path.abspath(rtl_path)),
            env=env,
        )
        combined = result["stdout"] + result["stderr"]
        errors = [l for l in combined.split('\n') if 'ERROR' in l.upper()]
        cell_m = re.search(r'Number\s+of\s+cells[:\s]*(\d+)', combined)
        cell_count = int(cell_m.group(1)) if cell_m else 0
        passed = result["returncode"] == 0 and not errors

        return {
            "passed": passed,
            "errors": errors,
            "cell_count": cell_count,
            "returncode": result["returncode"],
            "elapsed": result["elapsed"],
            "exit_code": _EXIT_CODES["pass"] if passed else _EXIT_CODES["synthesis_fail"],
        }
    finally:
        try:
            os.unlink(ys_path)
        except OSError:
            pass


def _verify_pipeline(rtl_path: str, strategy: str = "tmr", quick: bool = False) -> Dict:
    """运行完整加固管线。"""
    _log(f"  Pipeline: {os.path.basename(rtl_path)} (strategy={strategy})")

    cmd = [
        sys.executable, os.path.join(_SCRIPT_DIR, "graph_pipeline.py"),
        "--harden", rtl_path,
        "--hardening-strategy", strategy,
        "--use-ast-repair",
        "--docker-verify",
        "--max-repair-iter", "1" if quick else "3",
    ]
    result = _run_cmd(cmd, timeout=120)

    passed = "PASSED" in result["stdout"] and "FAILED" not in result["stdout"]
    return {
        "passed": passed,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "elapsed": result["elapsed"],
        "exit_code": _EXIT_CODES["pass"] if passed else _EXIT_CODES["pipeline_fail"],
    }


def _run_regression_test(quick: bool = False) -> Dict:
    """运行回归测试套件。"""
    _log("  Regression Test Suite")

    regression_script = os.path.join(_SCRIPT_DIR, "test_regression_suite.py")
    if not os.path.isfile(regression_script):
        _log(f"    ✗ Regression script not found: {regression_script}")
        return {
            "passed": False,
            "elapsed": 0,
            "exit_code": _EXIT_CODES["pipeline_fail"],
            "error": "Regression script not found",
        }

    cmd = [sys.executable, regression_script]
    if quick:
        cmd.append("--quick")

    _log(f"    Running: {' '.join(cmd)}")
    result = _run_cmd(cmd, timeout=300)

    passed = result["returncode"] == 0
    _log(f"    Result: {'PASSED' if passed else 'FAILED'} ({result['elapsed']:.2f}s)")

    # Parse test count from output
    test_count_match = re.search(r"Total:\s*(\d+)/(\d+)\s+tests passed", result["stdout"])
    if test_count_match:
        passed_count = int(test_count_match.group(1))
        total_count = int(test_count_match.group(2))
    else:
        passed_count = 0
        total_count = 0

    return {
        "passed": passed,
        "passed_count": passed_count,
        "total_count": total_count,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "elapsed": result["elapsed"],
        "exit_code": _EXIT_CODES["pass"] if passed else _EXIT_CODES["pipeline_fail"],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="CI 自动化验证 — 确保 oss-cad yosys 依赖正常工作"
    )
    parser.add_argument("--quick", action="store_true",
                        help="快速模式：仅语法检查，跳过综合和全管线")
    parser.add_argument("--ci-mode", action="store_true",
                        help="CI 模式：标准输出格式化 + 退出码")
    parser.add_argument("--report-dir", type=str, default=None,
                        help="保存 JSON 报告到指定目录")
    parser.add_argument("--rtl", type=str, default=None,
                        help="指定 RTL 文件（默认用 test_multi_strategy_harden.v）")
    parser.add_argument("--regression", action="store_true",
                        help="运行回归测试套件")
    parser.add_argument("--regression-only", action="store_true",
                        help="仅运行回归测试套件，跳过其他阶段")
    args = parser.parse_args()

    rtl_path = args.rtl or _TEST_RTL
    if not os.path.isfile(rtl_path) and not args.regression_only:
        _log(f"✗ RTL file not found: {rtl_path}")
        sys.exit(_EXIT_CODES["syntax_fail"])

    # ── 仅回归测试模式 ──
    if args.regression_only:
        _log("── Regression-Only Mode ──")
        r = _run_regression_test(quick=args.quick)
        _log(f"  Result: {'PASSED' if r['passed'] else 'FAILED'} "
             f"({r.get('passed_count', 0)}/{r.get('total_count', 0)} tests, "
             f"{r.get('elapsed', 0):.2f}s)")
        if args.report_dir:
            os.makedirs(args.report_dir, exist_ok=True)
            report_path = os.path.join(
                args.report_dir,
                f"ci_regression_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump({
                    "status": "PASSED" if r["passed"] else "FAILED",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "regression": {
                        "passed": r["passed"],
                        "passed_count": r["passed_count"],
                        "total_count": r["total_count"],
                        "elapsed": r["elapsed"],
                    },
                    "total_elapsed": r["elapsed"],
                    "exit_code": r["exit_code"],
                }, f, indent=2)
            _log(f"Report saved: {report_path}")
        sys.exit(r["exit_code"])

    # ── 检查 yosys ──
    ok, yosys_path = _check_yosys()
    if not ok:
        _log("✗ yosys not found (check PATH or oss-cad-suite installation)")
        sys.exit(_EXIT_CODES["yosys_unavailable"])
    _log(f"✓ yosys: {yosys_path}")

    # ── 阶段 1：语法检查 ──
    _log("── Phase 1: Syntax Check ──")
    r1 = _verify_syntax(rtl_path)
    _log(f"  Syntax: {'PASSED' if r1['passed'] else 'FAILED'} "
         f"(rc={r1.get('returncode', '?')}, {r1.get('elapsed', 0):.3f}s)")
    if not r1["passed"]:
        for e in r1["errors"][:5]:
            _log(f"    Error: {e[:120]}")
        sys.exit(r1["exit_code"])

    if args.quick:
        _log("\n✓ Quick verify: PASSED")
        sys.exit(_EXIT_CODES["pass"])

    # ── 阶段 2：综合检查 ──
    _log("── Phase 2: Synthesis Check ──")
    r2 = _verify_synthesis(rtl_path)
    _log(f"  Synthesis: {'PASSED' if r2['passed'] else 'FAILED'} "
         f"(cells={r2.get('cell_count', '?')}, {r2.get('elapsed', 0):.3f}s)")
    if not r2["passed"]:
        for e in r2["errors"][:5]:
            _log(f"    Error: {e[:120]}")
        sys.exit(r2["exit_code"])

    # ── 阶段 3：管线验证（仅选择 TMR 策略做集成测试）──
    _log("── Phase 3: Pipeline Verify (tmr) ──")
    r3 = _verify_pipeline(rtl_path, strategy="tmr", quick=True)
    _log(f"  Pipeline: {'PASSED' if r3['passed'] else 'FAILED'} "
         f"({r3.get('elapsed', 0):.3f}s)")
    if not r3["passed"]:
        _log(f"  stderr: {r3.get('stderr', '')[:300]}")
        sys.exit(r3["exit_code"])

    # ── 阶段 4：多策略验证 ──
    _log("── Phase 4: Multi-strategy Verify ──")
    strategies = ["dice", "ecc"]
    for s in strategies:
        r = _verify_pipeline(rtl_path, strategy=s, quick=True)
        _log(f"  {s.upper()}: {'PASSED' if r['passed'] else 'FAILED'} "
             f"({r.get('elapsed', 0):.3f}s)")
        if not r["passed"]:
            sys.exit(r["exit_code"])

    # ── 阶段 5：回归测试（可选）──
    r5 = None
    if args.regression or args.regression_only:
        _log("── Phase 5: Regression Test Suite ──")
        r5 = _run_regression_test(quick=args.quick)
        _log(f"  Regression: {'PASSED' if r5['passed'] else 'FAILED'} "
             f"({r5.get('passed_count', 0)}/{r5.get('total_count', 0)} tests, "
             f"{r5.get('elapsed', 0):.2f}s)")
        if not r5["passed"]:
            sys.exit(r5["exit_code"])

    # ── 报告 ──
    total_elapsed = r1["elapsed"] + r2["elapsed"] + r3["elapsed"]
    report = {
        "status": "PASSED",
        "timestamp": datetime.datetime.now().isoformat(),
        "yosys": yosys_path,
        "rtl": os.path.abspath(rtl_path),
        "phases": {
            "syntax": {"passed": r1["passed"], "elapsed": r1["elapsed"]},
            "synthesis": {"passed": r2["passed"], "elapsed": r2["elapsed"],
                          "cells": r2.get("cell_count", 0)},
            "pipeline_tmr": {"passed": r3["passed"], "elapsed": r3["elapsed"]},
            "pipeline_dice": {"passed": True, "elapsed": 0},
            "pipeline_ecc": {"passed": True, "elapsed": 0},
        },
        "total_elapsed": total_elapsed,
        "exit_code": _EXIT_CODES["pass"],
    }

    if args.report_dir:
        os.makedirs(args.report_dir, exist_ok=True)
        report_path = os.path.join(
            args.report_dir,
            f"ci_verify_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        _log(f"Report saved: {report_path}")

    _log(f"\n{'=' * 50}")
    _log(f"  ALL PASSED  ({total_elapsed:.2f}s total)")
    _log(f"{'=' * 50}")
    sys.exit(_EXIT_CODES["pass"])


if __name__ == "__main__":
    main()
