#!/usr/bin/env python3
"""
deploy_ci.py — CI 自动化部署脚本
====================================

合并回归测试脚本和 CI 配置，实现完整的自动化部署流程：
  1. 运行回归测试（包含 ECC+TMR 混合策略）
  2. 收集测试结果和详细日志（RAG缓存命中、AST迭代次数）
  3. 自动提交到 Git 仓库

用法:
    python deploy_ci.py                          # 默认模式
    python deploy_ci.py --quick                  # 快速模式
    python deploy_ci.py --branch feature/my-feature  # 指定分支
    python deploy_ci.py --dry-run                # 模拟运行，不提交

退出码:
    0 — 全部通过并提交成功
    1 — 测试失败
    2 — Git 操作失败
"""

import os
import sys
import json
import time
import datetime
import subprocess
import argparse
from typing import Dict, List, Optional


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', '..', '..', '..', '..'))


def log(msg: str, level: str = "INFO"):
    """带时间戳的日志输出。"""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


def run_cmd(cmd: List[str], timeout: int = 300, cwd: Optional[str] = None,
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


def run_regression_test(quick: bool = False) -> Dict:
    """运行回归测试套件。"""
    log("── Step 1: Running Regression Test Suite ──")

    regression_script = os.path.join(_SCRIPT_DIR, "test_regression_suite.py")
    if not os.path.isfile(regression_script):
        log(f"  ✗ Regression script not found: {regression_script}", "ERROR")
        return {"passed": False, "error": "Regression script not found"}

    cmd = [sys.executable, regression_script]
    if quick:
        cmd.append("--quick")

    log(f"  Running: {' '.join(cmd)}")
    result = run_cmd(cmd, timeout=300)

    passed = result["returncode"] == 0
    status = "PASSED" if passed else "FAILED"
    log(f"  Result: {status} ({result['elapsed']:.2f}s)")

    test_count_match = __import__('re').search(
        r"Total:\s*(\d+)/(\d+)\s+tests passed", result["stdout"]
    )
    if test_count_match:
        passed_count = int(test_count_match.group(1))
        total_count = int(test_count_match.group(2))
    else:
        passed_count = 0
        total_count = 0

    cache_hits = 0
    cache_misses = 0
    for line in result["stdout"].split('\n'):
        if "rag_cache_hits" in line:
            parts = line.split(',')
            for part in parts:
                if "rag_cache_hits" in part:
                    value = part.split('=')[1].strip()
                    cache_hits = int(''.join([c for c in value if c.isdigit()]))
                if "rag_cache_misses" in part:
                    value = part.split('=')[1].strip()
                    cache_misses = int(''.join([c for c in value if c.isdigit()]))

    log(f"  Tests: {passed_count}/{total_count} passed")
    log(f"  RAG Cache: {cache_hits} hits, {cache_misses} misses")

    return {
        "passed": passed,
        "passed_count": passed_count,
        "total_count": total_count,
        "elapsed": result["elapsed"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "rag_cache_hits": cache_hits,
        "rag_cache_misses": cache_misses,
    }


def collect_test_details(stdout: str) -> List[Dict]:
    """从测试输出中提取详细的测试结果。"""
    details = []
    for line in stdout.split('\n'):
        if "Strategy:" in line or "Design Error Analysis" in line or "AST Repair" in line:
            parts = line.split()
            if len(parts) >= 3:
                test_name = parts[0]
                status = parts[1] if len(parts) > 1 else "UNKNOWN"
                elapsed = parts[2] if len(parts) > 2 else ""
                detail_str = " ".join(parts[3:]) if len(parts) > 3 else ""

                iterations = "N/A"
                hardened_lines = "N/A"
                for d in detail_str.split(','):
                    if "iterations" in d:
                        iterations = d.split('=')[1].strip()
                    if "hardened_lines" in d:
                        hardened_lines = d.split('=')[1].strip()

                details.append({
                    "name": test_name,
                    "status": status,
                    "elapsed": elapsed,
                    "iterations": iterations,
                    "hardened_lines": hardened_lines,
                })
    return details


def git_commit_and_push(branch: Optional[str] = None, dry_run: bool = False,
                        test_result: Dict = None) -> bool:
    """提交并推送更改到 Git 仓库。"""
    log("── Step 2: Git Commit & Push ──")
    os.chdir(_PROJECT_ROOT)

    if branch:
        log(f"  Checking out branch: {branch}")
        result = run_cmd(["git", "checkout", branch])
        if result["returncode"] != 0:
            log(f"  ✗ Failed to checkout branch: {result['stderr']}", "ERROR")
            return False

    run_cmd(["git", "reset", "HEAD"])

    source_files = [
        os.path.join(_PROJECT_ROOT, "ai_project", "common", "scripts", "sim", "formal_test", "deploy_ci.py"),
        os.path.join(_PROJECT_ROOT, "ai_project", "common", "scripts", "sim", "formal_test", "deploy_ci.sh"),
        os.path.join(_PROJECT_ROOT, "ai_project", "common", "scripts", "sim", "formal_test", "test_regression_suite.py"),
        os.path.join(_PROJECT_ROOT, "ai_project", "common", "scripts", "sim", "formal_test", "rag_integration.py"),
        os.path.join(_PROJECT_ROOT, "ai_project", "common", "scripts", "sim", "formal_test", "run_ci_verify.py"),
        os.path.join(_PROJECT_ROOT, "ai_project", "common", "scripts", "sim", "formal_test", "DEPLOY_CI_USER_GUIDE.md"),
    ]
    
    for src_file in source_files:
        if os.path.isfile(src_file):
            result = run_cmd(["git", "add", src_file])
            if result["returncode"] != 0:
                log(f"  ⚠️  Failed to stage {os.path.basename(src_file)}: {result['stderr']}", "INFO")
        else:
            log(f"  ⚠️  File not found: {os.path.basename(src_file)}", "INFO")
    
    result = run_cmd(["git", "diff", "--cached", "--quiet"])
    if result["returncode"] == 0:
        log("  No changes to commit — skipping")
        return True

    if dry_run:
        log("  Dry run mode: showing what would be committed")
        result = run_cmd(["git", "diff", "--cached", "--stat"])
        log(f"  Changes:\n{result['stdout']}")
        return True

    test_details = collect_test_details(test_result.get("stdout", "")) if test_result else []
    details_lines = []
    for td in test_details:
        details_lines.append(f"    - {td['name']}: {td['status']} (iter={td['iterations']}, lines={td['hardened_lines']})")

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = f"""CI: Automated deployment - {timestamp}

- Regression tests: {'PASSED' if test_result.get('passed') else 'FAILED'}
- Tests: {test_result.get('passed_count', 0)}/{test_result.get('total_count', 0)}
- RAG Cache: {test_result.get('rag_cache_hits', 0)} hits, {test_result.get('rag_cache_misses', 0)} misses
- Quick mode: {test_result.get('quick', False)}

Test Details:
{chr(10).join(details_lines) if details_lines else '    - None'}

Files updated:
- ai_project/common/scripts/sim/formal_test/test_regression_suite.py
- ai_project/common/scripts/sim/formal_test/rag_integration.py
- ai_project/common/scripts/sim/formal_test/deploy_ci.py
"""

    log("  Committing changes...")
    result = run_cmd(["git", "commit", "-m", commit_msg])
    if result["returncode"] != 0:
        log(f"  ✗ Failed to commit: {result['stderr']}", "ERROR")
        return False

    result = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current_branch = result["stdout"].strip()

    log(f"  Pushing to origin/{current_branch}...")
    result = run_cmd(["git", "push", "origin", current_branch])
    if result["returncode"] != 0:
        log(f"  ✗ Failed to push: {result['stderr']}", "ERROR")
        return False

    result = run_cmd(["git", "rev-parse", "--short", "HEAD"])
    commit_hash = result["stdout"].strip()
    log(f"  ✅ Committed: {commit_hash}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="CI 自动化部署脚本 — 运行回归测试并自动提交到 Git"
    )
    parser.add_argument("--quick", action="store_true",
                        help="快速模式：仅运行基础测试")
    parser.add_argument("--branch", type=str, default=None,
                        help="指定分支（默认当前分支）")
    parser.add_argument("--dry-run", action="store_true",
                        help="模拟运行，不执行实际的 Git 提交")
    parser.add_argument("--report-dir", type=str, default=None,
                        help="保存测试报告到指定目录")
    args = parser.parse_args()

    log("=" * 60)
    log("  CI Automated Deployment Script")
    log("=" * 60)
    log(f"  Script dir:   {_SCRIPT_DIR}")
    log(f"  Project root: {_PROJECT_ROOT}")
    log(f"  Quick mode:   {args.quick}")
    log(f"  Branch:       {args.branch or 'current'}")
    log(f"  Dry run:      {args.dry_run}")
    log("=" * 60)

    start_time = time.time()

    test_result = run_regression_test(quick=args.quick)

    if not test_result["passed"]:
        log("  ✗ Regression tests failed!", "ERROR")
        log(f"  Output:\n{test_result.get('stdout', '')[:1000]}")
        if test_result.get('stderr'):
            log(f"  Error:\n{test_result.get('stderr', '')[:500]}")
        log("=" * 60)
        log("  DEPLOYMENT ABORTED — Tests Failed")
        log("=" * 60)
        sys.exit(1)

    log("  ✅ Regression tests passed!")

    if args.report_dir:
        os.makedirs(args.report_dir, exist_ok=True)
        report_path = os.path.join(
            args.report_dir,
            f"ci_deploy_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        report = {
            "status": "PASSED",
            "timestamp": datetime.datetime.now().isoformat(),
            "quick_mode": args.quick,
            "branch": args.branch,
            "test_result": test_result,
            "test_details": collect_test_details(test_result.get("stdout", "")),
        }
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        log(f"  Report saved: {report_path}")

    success = git_commit_and_push(branch=args.branch, dry_run=args.dry_run,
                                   test_result=test_result)

    total_elapsed = time.time() - start_time
    log("=" * 60)
    if success:
        log(f"  DEPLOYMENT COMPLETED SUCCESSFULLY ({total_elapsed:.2f}s)")
        if not args.dry_run:
            result = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
            branch = result["stdout"].strip()
            result = run_cmd(["git", "rev-parse", "--short", "HEAD"])
            commit = result["stdout"].strip()
            log(f"  Branch:     {branch}")
            log(f"  Commit:     {commit}")
    else:
        log("  DEPLOYMENT FAILED — Git Operation Error", "ERROR")
        sys.exit(2)
    log("=" * 60)

    sys.exit(0)


if __name__ == "__main__":
    main()
