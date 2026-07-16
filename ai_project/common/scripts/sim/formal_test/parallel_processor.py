#!/usr/bin/env python3
"""parallel_processor.py — 并行处理模块

实现多模块并行分析和加固，提高处理速度。

用法:
    from parallel_processor import ParallelProcessor

    processor = ParallelProcessor(max_workers=4)
    results = processor.parallel_harden(rtl_files, strategy="tmr")
    stats = processor.get_stats()
"""

import os
import sys
import time
from typing import List, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

try:
    from rag_integration import MockLLM
    from gnn_vulnerability import predict_vulnerability
    from auto_repair import AutoRepair
    from logger import logger
except ImportError as e:
    print(f"Failed to import core modules: {e}")
    raise


class ParallelProcessor:
    """并行处理器。

    使用线程池实现多模块并行分析和加固。
    """

    def __init__(self, max_workers: int = 4):
        """初始化并行处理器。

        Args:
            max_workers: 最大工作线程数
        """
        self.max_workers = max_workers
        self._stats: Dict[str, Any] = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "total_time": 0.0,
            "task_results": [],
        }
        self._mock_llm = MockLLM()

    def _reset_stats(self):
        """重置统计信息。"""
        self._stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "total_time": 0.0,
            "task_results": [],
        }

    def thread_pool_process(
        self,
        func: Callable,
        items: List[Any],
        max_workers: int = None,
    ) -> List[Dict]:
        """通用线程池处理。

        Args:
            func: 处理函数
            items: 待处理项列表
            max_workers: 最大工作线程数（默认使用实例值）

        Returns:
            处理结果列表
        """
        self._reset_stats()
        workers = max_workers or self.max_workers
        start_time = time.time()

        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_item = {executor.submit(func, item): item for item in items}

            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    result = future.result()
                    results.append(result)
                    self._stats["completed_tasks"] += 1
                except Exception as e:
                    results.append({"item": str(item), "error": str(e), "success": False})
                    self._stats["failed_tasks"] += 1

        self._stats["total_tasks"] = len(items)
        self._stats["total_time"] = time.time() - start_time
        self._stats["task_results"] = results

        return results

    def process_with_progress(
        self,
        items: List[Any],
        process_func: Callable,
        description: str = "Processing",
    ) -> List[Dict]:
        """带进度条的处理。

        Args:
            items: 待处理项列表
            process_func: 处理函数
            description: 进度条描述

        Returns:
            处理结果列表
        """
        self._reset_stats()
        start_time = time.time()
        results = []

        if TQDM_AVAILABLE:
            iterator = tqdm(items, desc=description, unit="item")
        else:
            iterator = items

        for item in iterator:
            try:
                result = process_func(item)
                results.append(result)
                self._stats["completed_tasks"] += 1
            except Exception as e:
                results.append({"item": str(item), "error": str(e), "success": False})
                self._stats["failed_tasks"] += 1

        self._stats["total_tasks"] = len(items)
        self._stats["total_time"] = time.time() - start_time
        self._stats["task_results"] = results

        return results

    def _harden_single(self, item: Dict) -> Dict:
        """处理单个 RTL 文件的加固。"""
        rtl_code = item.get("rtl_code", "")
        strategy = item.get("strategy", "tmr")
        filename = item.get("filename", "unknown")

        try:
            prompt = f"Apply {strategy} hardening to the following RTL module:\n\n{rtl_code}"
            hardened_rtl = self._mock_llm.generate(prompt)

            return {
                "filename": filename,
                "strategy": strategy,
                "success": True,
                "hardened_rtl": hardened_rtl,
                "errors": [],
            }
        except Exception as e:
            return {
                "filename": filename,
                "strategy": strategy,
                "success": False,
                "hardened_rtl": "",
                "errors": [str(e)],
            }

    def parallel_harden(
        self,
        rtl_files: List[str],
        strategy: str = "tmr",
    ) -> List[Dict]:
        """并行处理多个 RTL 文件进行加固。

        Args:
            rtl_files: RTL 文件路径列表或包含 rtl_code 的字典列表
            strategy: 加固策略

        Returns:
            处理结果列表
        """
        items = []
        for rtl in rtl_files:
            if isinstance(rtl, str):
                if os.path.isfile(rtl):
                    with open(rtl, "r", encoding="utf-8") as f:
                        rtl_code = f.read()
                    items.append({
                        "rtl_code": rtl_code,
                        "strategy": strategy,
                        "filename": os.path.basename(rtl),
                    })
                else:
                    items.append({
                        "rtl_code": rtl,
                        "strategy": strategy,
                        "filename": "inline",
                    })
            elif isinstance(rtl, dict):
                items.append({**rtl, "strategy": strategy})

        return self.thread_pool_process(self._harden_single, items)

    def _vulnerability_single(self, item: Dict) -> Dict:
        """处理单个 RTL 文件的脆弱性分析。"""
        rtl_code = item.get("rtl_code", "")
        filename = item.get("filename", "unknown")

        try:
            results = predict_vulnerability(rtl_code)
            return {
                "filename": filename,
                "success": True,
                "results": results,
                "errors": [],
            }
        except Exception as e:
            return {
                "filename": filename,
                "success": False,
                "results": {},
                "errors": [str(e)],
            }

    def parallel_vulnerability(self, rtl_files: List[str]) -> List[Dict]:
        """并行分析多个 RTL 文件的脆弱性。

        Args:
            rtl_files: RTL 文件路径列表或包含 rtl_code 的字典列表

        Returns:
            处理结果列表
        """
        items = []
        for rtl in rtl_files:
            if isinstance(rtl, str):
                if os.path.isfile(rtl):
                    with open(rtl, "r", encoding="utf-8") as f:
                        rtl_code = f.read()
                    items.append({
                        "rtl_code": rtl_code,
                        "filename": os.path.basename(rtl),
                    })
                else:
                    items.append({
                        "rtl_code": rtl,
                        "filename": "inline",
                    })
            elif isinstance(rtl, dict):
                items.append(rtl)

        return self.thread_pool_process(self._vulnerability_single, items)

    def _repair_single(self, item: Dict) -> Dict:
        """处理单个 RTL 文件的语法修复。"""
        rtl_code = item.get("rtl_code", "")
        filename = item.get("filename", "unknown")

        try:
            repairer = AutoRepair()
            result = repairer.run(rtl_code)
            return {
                "filename": filename,
                "success": result.get("success", False),
                "repaired_rtl": result.get("final_rtl", rtl_code),
                "errors_found": result.get("errors_found", []),
                "fixes_applied": result.get("fixes_applied", []),
            }
        except Exception as e:
            return {
                "filename": filename,
                "success": False,
                "repaired_rtl": rtl_code,
                "errors_found": [],
                "fixes_applied": [],
                "errors": [str(e)],
            }

    def parallel_repair(self, rtl_files: List[str]) -> List[Dict]:
        """并行修复多个 RTL 文件的语法错误。

        Args:
            rtl_files: RTL 文件路径列表或包含 rtl_code 的字典列表

        Returns:
            处理结果列表
        """
        items = []
        for rtl in rtl_files:
            if isinstance(rtl, str):
                if os.path.isfile(rtl):
                    with open(rtl, "r", encoding="utf-8") as f:
                        rtl_code = f.read()
                    items.append({
                        "rtl_code": rtl_code,
                        "filename": os.path.basename(rtl),
                    })
                else:
                    items.append({
                        "rtl_code": rtl,
                        "filename": "inline",
                    })
            elif isinstance(rtl, dict):
                items.append(rtl)

        return self.thread_pool_process(self._repair_single, items)

    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计信息。

        Returns:
            统计信息字典
        """
        return {
            "total_tasks": self._stats["total_tasks"],
            "completed_tasks": self._stats["completed_tasks"],
            "failed_tasks": self._stats["failed_tasks"],
            "success_rate": self._stats["completed_tasks"] / max(self._stats["total_tasks"], 1) * 100,
            "total_time": round(self._stats["total_time"], 2),
            "avg_time_per_task": round(self._stats["total_time"] / max(self._stats["total_tasks"], 1), 2),
        }


if __name__ == "__main__":
    test_rtl = """
module test_module(
    input clk,
    input rst,
    input [7:0] din,
    output [7:0] dout
);
    reg [7:0] buffer;
    always @(posedge clk or posedge rst) begin
        if (rst) buffer <= 0;
        else buffer <= din;
    end
    assign dout = buffer;
endmodule
"""

    processor = ParallelProcessor(max_workers=2)

    print("=== Parallel Harden Test ===")
    results = processor.parallel_harden([test_rtl, test_rtl], strategy="tmr")
    stats = processor.get_stats()
    print(f"Results: {len(results)} completed")
    print(f"Stats: {stats}")

    print("\n=== Parallel Vulnerability Test ===")
    results = processor.parallel_vulnerability([test_rtl])
    stats = processor.get_stats()
    print(f"Results: {len(results)} completed")
    print(f"Stats: {stats}")
