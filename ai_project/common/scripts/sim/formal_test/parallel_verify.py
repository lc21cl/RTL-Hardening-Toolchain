#!/usr/bin/env python3
"""
parallel_verify.py — 并行验证模块

同时运行多种验证检查（语法检查、综合检查、等价性验证），
利用多进程加速验证流程。

核心功能：
  1. 并行执行多种验证检查
  2. 统一的验证结果收集和报告
  3. 支持不同验证引擎（yosys_docker, local yosys）
  4. 可配置的并发度控制
  5. 超时机制防止长时间运行

设计原则：
  - 非阻塞式验证 — 验证过程不阻塞主流程
  - 可扩展 — 易于添加新的验证类型
  - 可靠 — 每个验证任务独立运行，单个失败不影响其他
  - 可观察 — 详细的进度和结果报告

用法:
    from parallel_verify import ParallelVerifier

    verifier = ParallelVerifier(max_workers=4)

    # 提交多个验证任务
    verifier.submit_syntax_check("design.v")
    verifier.submit_synthesis_check("design.v")
    verifier.submit_equiv_check("original.v", "hardened.v")

    # 等待所有任务完成
    results = verifier.wait_all()
"""

import os
import re
import sys
import time
import queue
import threading
import multiprocessing
from typing import Dict, List, Optional, Tuple, Any, Callable

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("parallel_verify")


# ============================================================================
# Verification Task Types
# ============================================================================

class VerifyTask:
    """验证任务基类。"""

    def __init__(self, task_id: str, task_type: str):
        self.task_id = task_id
        self.task_type = task_type
        self.start_time = None
        self.end_time = None
        self._result = None
        self._error = None

    def run(self) -> Dict[str, Any]:
        """执行验证任务，返回结果。"""
        raise NotImplementedError

    def get_result(self) -> Dict[str, Any]:
        """获取任务结果。"""
        if self._result is None and self._error is None:
            try:
                self.start_time = time.time()
                self._result = self.run()
                self.end_time = time.time()
            except Exception as e:
                self._error = str(e)
                self.end_time = time.time()

        if self._error:
            return {
                "task_id": self.task_id,
                "task_type": self.task_type,
                "status": "error",
                "error": self._error,
                "duration": (self.end_time - self.start_time) if self.start_time else 0,
            }

        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self._result.get("status", "unknown"),
            **self._result,
            "duration": (self.end_time - self.start_time) if self.start_time else 0,
        }


class SyntaxCheckTask(VerifyTask):
    """语法检查任务。"""

    def __init__(self, task_id: str, rtl_path: str, yosys_path: Optional[str] = None):
        super().__init__(task_id, "syntax_check")
        self.rtl_path = rtl_path
        self.yosys_path = yosys_path

    def run(self) -> Dict[str, Any]:
        from yosys_utils import find_yosys, yosys_env
        import subprocess

        yosys = self.yosys_path or find_yosys()
        if not yosys:
            return {"status": "skipped", "reason": "yosys not found"}

        proc_env = yosys_env(yosys)
        result = subprocess.run(
            [yosys, "-p", f"read_verilog -sv {self.rtl_path}; check"],
            capture_output=True, text=True, timeout=120, env=proc_env,
        )

        errors = []
        warnings = []
        for line in result.stderr.splitlines():
            if re.search(r'\bERROR\b', line, re.IGNORECASE):
                errors.append(line.strip())
            elif re.search(r'\bWarning\b', line):
                warnings.append(line.strip())

        return {
            "status": "pass" if result.returncode == 0 and not errors else "fail",
            "errors": errors,
            "warnings": warnings,
            "returncode": result.returncode,
        }


class SynthesisCheckTask(VerifyTask):
    """综合检查任务。"""

    def __init__(self, task_id: str, rtl_path: str, yosys_path: Optional[str] = None):
        super().__init__(task_id, "synthesis_check")
        self.rtl_path = rtl_path
        self.yosys_path = yosys_path

    def run(self) -> Dict[str, Any]:
        from yosys_utils import find_yosys, yosys_env
        import subprocess

        yosys = self.yosys_path or find_yosys()
        if not yosys:
            return {"status": "skipped", "reason": "yosys not found"}

        proc_env = yosys_env(yosys)
        ys_script = f"""
read_verilog -sv {self.rtl_path}
hierarchy -check -auto-top
proc; opt
memory; opt
flatten; opt
techmap; opt
opt_clean
setundef -undriven -zero
stat
"""
        result = subprocess.run(
            [yosys, "-p", ys_script],
            capture_output=True, text=True, timeout=120, env=proc_env,
        )

        cell_count = 0
        area_estimate = 0.0
        for line in result.stdout.splitlines():
            cell_match = re.search(r'Number\s+of\s+cells[:\s]*(\d+)', line, re.IGNORECASE)
            if cell_match:
                cell_count = int(cell_match.group(1))
            area_match = re.search(r'Chip\s+area\s+[:\s]*([\d.]+)', line, re.IGNORECASE)
            if area_match:
                area_estimate = float(area_match.group(1))

        errors = []
        for line in result.stderr.splitlines():
            if re.search(r'\bERROR\b', line, re.IGNORECASE):
                errors.append(line.strip())

        return {
            "status": "pass" if result.returncode == 0 and not errors else "fail",
            "errors": errors,
            "cell_count": cell_count,
            "area_estimate": area_estimate,
            "returncode": result.returncode,
        }


class EquivCheckTask(VerifyTask):
    """等价性检查任务。"""

    def __init__(
        self,
        task_id: str,
        original_path: str,
        hardened_path: str,
        yosys_path: Optional[str] = None,
    ):
        super().__init__(task_id, "equiv_check")
        self.original_path = original_path
        self.hardened_path = hardened_path
        self.yosys_path = yosys_path

    def run(self) -> Dict[str, Any]:
        from yosys_utils import find_yosys, yosys_env
        import subprocess

        yosys = self.yosys_path or find_yosys()
        if not yosys:
            return {"status": "skipped", "reason": "yosys not found"}

        proc_env = yosys_env(yosys)

        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ys', delete=False) as f:
            ys_script = f"""
read_verilog -sv {self.original_path}
hierarchy -check -auto-top
proc; opt
memory; opt
write_verilog /tmp/original_opt.v

read_verilog -sv {self.hardened_path}
hierarchy -check -auto-top
proc; opt
memory; opt
write_verilog /tmp/hardened_opt.v

read_verilog /tmp/original_opt.v
rename -top original
read_verilog /tmp/hardened_opt.v
rename -top hardened

equiv_make original hardened
equiv_status
"""
            f.write(ys_script)
            script_path = f.name

        try:
            result = subprocess.run(
                [yosys, "-s", script_path],
                capture_output=True, text=True, timeout=300, env=proc_env,
            )
        finally:
            os.unlink(script_path)

        equivalent = False
        for line in result.stdout.splitlines():
            if re.search(r'Equivalence\s+checked\s+successfully', line):
                equivalent = True
                break

        errors = []
        for line in result.stderr.splitlines():
            if re.search(r'\bERROR\b', line, re.IGNORECASE):
                errors.append(line.strip())

        return {
            "status": "pass" if equivalent else "fail",
            "equivalent": equivalent,
            "errors": errors,
            "returncode": result.returncode,
        }


# ============================================================================
# ParallelVerifier
# ============================================================================

class ParallelVerifier:
    """并行验证器。

    同时运行多种验证检查，利用多进程加速验证流程。
    """

    def __init__(
        self,
        max_workers: int = None,
        timeout: float = 300.0,
        yosys_path: Optional[str] = None,
    ):
        """初始化并行验证器。

        Args:
            max_workers: 最大并发工作进程数。None 使用 CPU 核心数。
            timeout: 单个任务超时时间（秒）。
            yosys_path: yosys 可执行文件路径。
        """
        self.max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        self.timeout = timeout
        self.yosys_path = yosys_path
        self._tasks: List[VerifyTask] = []
        self._results: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._task_counter = 0

    def submit_syntax_check(self, rtl_path: str, task_id: Optional[str] = None) -> str:
        """提交语法检查任务。

        Args:
            rtl_path: RTL 文件路径。
            task_id: 任务 ID（可选，自动生成）。

        Returns:
            任务 ID。
        """
        tid = task_id or f"syntax_{self._task_counter}"
        self._task_counter += 1
        task = SyntaxCheckTask(tid, rtl_path, self.yosys_path)
        self._tasks.append(task)
        return tid

    def submit_synthesis_check(self, rtl_path: str, task_id: Optional[str] = None) -> str:
        """提交综合检查任务。

        Args:
            rtl_path: RTL 文件路径。
            task_id: 任务 ID（可选，自动生成）。

        Returns:
            任务 ID。
        """
        tid = task_id or f"synth_{self._task_counter}"
        self._task_counter += 1
        task = SynthesisCheckTask(tid, rtl_path, self.yosys_path)
        self._tasks.append(task)
        return tid

    def submit_equiv_check(
        self,
        original_path: str,
        hardened_path: str,
        task_id: Optional[str] = None,
    ) -> str:
        """提交等价性检查任务。

        Args:
            original_path: 原始 RTL 文件路径。
            hardened_path: 加固后 RTL 文件路径。
            task_id: 任务 ID（可选，自动生成）。

        Returns:
            任务 ID。
        """
        tid = task_id or f"equiv_{self._task_counter}"
        self._task_counter += 1
        task = EquivCheckTask(tid, original_path, hardened_path, self.yosys_path)
        self._tasks.append(task)
        return tid

    def submit_custom_task(self, task: VerifyTask) -> str:
        """提交自定义验证任务。

        Args:
            task: 验证任务实例。

        Returns:
            任务 ID。
        """
        self._tasks.append(task)
        return task.task_id

    def _worker(self, task_queue: queue.Queue, result_queue: queue.Queue):
        """工作进程函数。"""
        while True:
            try:
                task = task_queue.get(timeout=1)
                if task is None:
                    break
                result = task.get_result()
                result_queue.put(result)
            except queue.Empty:
                continue

    def run_all(self, callback: Optional[Callable] = None) -> Dict[str, Any]:
        """运行所有已提交的任务（阻塞模式）。

        Args:
            callback: 每个任务完成后的回调函数。

        Returns:
            所有任务的结果汇总。
        """
        if not self._tasks:
            logger.print(f"  [PARALLEL_VERIFY] No tasks to run")
            return {"results": [], "summary": {"total": 0, "pass": 0, "fail": 0, "error": 0}}

        logger.print(f"  [PARALLEL_VERIFY] Running {len(self._tasks)} tasks with {self.max_workers} workers")

        task_queue = queue.Queue()
        result_queue = queue.Queue()

        for task in self._tasks:
            task_queue.put(task)

        for _ in range(self.max_workers):
            task_queue.put(None)

        workers = []
        for _ in range(self.max_workers):
            t = threading.Thread(target=self._worker, args=(task_queue, result_queue))
            t.daemon = True
            t.start()
            workers.append(t)

        results = []
        completed = 0
        total = len(self._tasks)

        while completed < total:
            try:
                result = result_queue.get(timeout=self.timeout + 10)
                results.append(result)
                completed += 1
                logger.print(f"  [PARALLEL_VERIFY] Task {completed}/{total} done: {result['task_id']} -> {result['status']}")
                if callback:
                    callback(result)
            except queue.Empty:
                logger.warning(f"  [PARALLEL_VERIFY] Timeout waiting for remaining tasks")
                break

        for t in workers:
            t.join(timeout=5)

        summary = self._summarize_results(results)
        return {"results": results, "summary": summary}

    def _summarize_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """汇总验证结果。"""
        summary = {
            "total": len(results),
            "pass": 0,
            "fail": 0,
            "error": 0,
            "skipped": 0,
            "total_duration": 0.0,
            "details": {},
        }

        for result in results:
            status = result.get("status", "unknown")
            summary["details"][result["task_id"]] = status
            summary["total_duration"] += result.get("duration", 0)

            if status == "pass":
                summary["pass"] += 1
            elif status == "fail":
                summary["fail"] += 1
            elif status == "error":
                summary["error"] += 1
            elif status == "skipped":
                summary["skipped"] += 1

        return summary

    def run_single(self, rtl_path: str, check_types: List[str] = None) -> Dict[str, Any]:
        """对单个 RTL 文件运行多种检查。

        Args:
            rtl_path: RTL 文件路径。
            check_types: 检查类型列表 ('syntax', 'synthesis')。

        Returns:
            检查结果汇总。
        """
        checks = check_types or ['syntax', 'synthesis']

        if 'syntax' in checks:
            self.submit_syntax_check(rtl_path)
        if 'synthesis' in checks:
            self.submit_synthesis_check(rtl_path)

        return self.run_all()

    def run_comparison(self, original_path: str, hardened_path: str) -> Dict[str, Any]:
        """对原始和加固后的 RTL 进行全面比较验证。

        Args:
            original_path: 原始 RTL 文件路径。
            hardened_path: 加固后 RTL 文件路径。

        Returns:
            验证结果汇总。
        """
        self.submit_syntax_check(original_path, "original_syntax")
        self.submit_syntax_check(hardened_path, "hardened_syntax")
        self.submit_synthesis_check(hardened_path, "hardened_synthesis")
        self.submit_equiv_check(original_path, hardened_path, "equiv_check")

        return self.run_all()


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parallel Verification")
    parser.add_argument("--rtl", type=str, help="RTL file path")
    parser.add_argument("--original", type=str, help="Original RTL for comparison")
    parser.add_argument("--hardened", type=str, help="Hardened RTL for comparison")
    parser.add_argument("--checks", type=str, default="all",
                        help="Check types (syntax,synthesis,equiv or all)")
    parser.add_argument("--workers", type=int, default=None, help="Max workers")
    parser.add_argument("--output", type=str, help="Output JSON path")
    args = parser.parse_args()

    verifier = ParallelVerifier(max_workers=args.workers)

    if args.original and args.hardened:
        result = verifier.run_comparison(args.original, args.hardened)
    elif args.rtl:
        checks = args.checks.split(',') if args.checks != 'all' else ['syntax', 'synthesis']
        result = verifier.run_single(args.rtl, checks)
    else:
        parser.error("Please provide --rtl or both --original and --hardened")
        return

    import json
    print(json.dumps(result, indent=2))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"\nResults written to: {args.output}")


if __name__ == "__main__":
    main()
