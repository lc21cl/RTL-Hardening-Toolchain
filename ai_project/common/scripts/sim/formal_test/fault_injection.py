#!/usr/bin/env python3
"""fault_injection.py — 故障注入测试框架

实现 SEU、SET、Stuck-at、Bridge 等故障类型的注入测试。

用法:
    from fault_injection import FaultInjector

    injector = FaultInjector()
    result = injector.inject_seu(rtl_content, "register_name", 3)
    report = injector.get_fault_report()
"""

import re
import random
import json
from typing import List, Dict, Any, Optional


class FaultInjector:
    """故障注入器。

    支持 SEU、SET、Stuck-at、Bridge 等多种故障类型的注入。
    """

    def __init__(self):
        """初始化故障注入器。"""
        self._fault_history: List[Dict[str, Any]] = []
        self._fault_types = ["seu", "set", "stuck_at", "bridge"]

    def _extract_registers(self, rtl_content: str) -> List[str]:
        """从 RTL 代码中提取寄存器名称。

        Args:
            rtl_content: RTL 代码

        Returns:
            寄存器名称列表
        """
        registers = []

        reg_patterns = [
            r"\breg\s+(\[\d+:\d+\])?\s*(\w+)",
            r"\bwire\s+(\[\d+:\d+\])?\s*(\w+)",
            r"\binput\s+(\[\d+:\d+\])?\s*(\w+)",
            r"\boutput\s+(\[\d+:\d+\])?\s*(\w+)",
        ]

        for pattern in reg_patterns:
            matches = re.findall(pattern, rtl_content)
            for match in matches:
                reg_name = match[1] if len(match) > 1 else match[0]
                if reg_name and reg_name not in registers:
                    registers.append(reg_name)

        return registers

    def inject_seu(
        self,
        rtl_content: str,
        node_name: str,
        bit_position: int,
    ) -> Dict[str, Any]:
        """注入单粒子翻转故障 (SEU)。

        Args:
            rtl_content: RTL 代码
            node_name: 节点名称（寄存器）
            bit_position: 翻转的位位置

        Returns:
            故障注入结果
        """
        fault_id = f"SEU_{node_name}_{bit_position}"

        injected_content = rtl_content
        effect = "applied"

        if node_name in rtl_content:
            injected_content = re.sub(
                rf"(\b{re.escape(node_name)}\b)",
                lambda m: f"(({m.group(1)} >> {bit_position}) ^ 1) << {bit_position} | ({m.group(1)} & ~(1 << {bit_position}))",
                rtl_content,
                count=1,
            )
        else:
            effect = "skipped (node not found)"

        result = {
            "fault_id": fault_id,
            "fault_type": "seu",
            "node_name": node_name,
            "bit_position": bit_position,
            "effect": effect,
            "injected_content": injected_content,
            "original_length": len(rtl_content),
            "injected_length": len(injected_content),
        }

        self._fault_history.append(result)
        return result

    def inject_set(
        self,
        rtl_content: str,
        signal_name: str,
        pulse_width: int = 1,
    ) -> Dict[str, Any]:
        """注入单粒子瞬态故障 (SET)。

        Args:
            rtl_content: RTL 代码
            signal_name: 信号名称
            pulse_width: 脉冲宽度（周期数）

        Returns:
            故障注入结果
        """
        fault_id = f"SET_{signal_name}_{pulse_width}"

        injected_content = rtl_content
        effect = "applied"

        if signal_name in rtl_content:
            injected_content = re.sub(
                rf"(\b{re.escape(signal_name)}\b)",
                lambda m: f"(({m.group(1)} | (pulse_signal_{signal_name})) & ~(pulse_signal_{signal_name} >> {pulse_width}))",
                rtl_content,
                count=1,
            )
        else:
            effect = "skipped (signal not found)"

        result = {
            "fault_id": fault_id,
            "fault_type": "set",
            "signal_name": signal_name,
            "pulse_width": pulse_width,
            "effect": effect,
            "injected_content": injected_content,
            "original_length": len(rtl_content),
            "injected_length": len(injected_content),
        }

        self._fault_history.append(result)
        return result

    def inject_stuck_at(
        self,
        rtl_content: str,
        signal_name: str,
        value: int = 0,
    ) -> Dict[str, Any]:
        """注入固定故障 (Stuck-at)。

        Args:
            rtl_content: RTL 代码
            signal_name: 信号名称
            value: 固定值（0 或 1）

        Returns:
            故障注入结果
        """
        fault_id = f"SA_{signal_name}_{value}"

        injected_content = rtl_content
        effect = "applied"

        if signal_name in rtl_content:
            injected_content = re.sub(
                rf"(\b{re.escape(signal_name)}\b)",
                str(value),
                rtl_content,
                count=1,
            )
        else:
            effect = "skipped (signal not found)"

        result = {
            "fault_id": fault_id,
            "fault_type": "stuck_at",
            "signal_name": signal_name,
            "stuck_value": value,
            "effect": effect,
            "injected_content": injected_content,
            "original_length": len(rtl_content),
            "injected_length": len(injected_content),
        }

        self._fault_history.append(result)
        return result

    def inject_bridge(
        self,
        rtl_content: str,
        signal1: str,
        signal2: str,
    ) -> Dict[str, Any]:
        """注入桥接故障 (Bridge)。

        Args:
            rtl_content: RTL 代码
            signal1: 第一个信号名称
            signal2: 第二个信号名称

        Returns:
            故障注入结果
        """
        fault_id = f"BRIDGE_{signal1}_{signal2}"

        injected_content = rtl_content
        effect = "applied"

        if signal1 in rtl_content and signal2 in rtl_content:
            injected_content = re.sub(
                rf"(\b{re.escape(signal1)}\b)",
                f"({signal1} | {signal2})",
                rtl_content,
                count=1,
            )
        else:
            effect = "skipped (signals not found)"

        result = {
            "fault_id": fault_id,
            "fault_type": "bridge",
            "signal1": signal1,
            "signal2": signal2,
            "effect": effect,
            "injected_content": injected_content,
            "original_length": len(rtl_content),
            "injected_length": len(injected_content),
        }

        self._fault_history.append(result)
        return result

    def random_inject(
        self,
        rtl_content: str,
        num_faults: int = 1,
        fault_type: str = "seu",
    ) -> List[Dict[str, Any]]:
        """随机注入多个故障。

        Args:
            rtl_content: RTL 代码
            num_faults: 故障数量
            fault_type: 故障类型

        Returns:
            故障注入结果列表
        """
        registers = self._extract_registers(rtl_content)
        if not registers:
            return []

        results = []
        for _ in range(num_faults):
            node_name = random.choice(registers)
            bit_position = random.randint(0, 31)

            if fault_type == "seu":
                result = self.inject_seu(rtl_content, node_name, bit_position)
            elif fault_type == "set":
                result = self.inject_set(rtl_content, node_name, pulse_width=1)
            elif fault_type == "stuck_at":
                result = self.inject_stuck_at(rtl_content, node_name, value=random.randint(0, 1))
            elif fault_type == "bridge":
                signal2 = random.choice([r for r in registers if r != node_name])
                result = self.inject_bridge(rtl_content, node_name, signal2)
            else:
                result = self.inject_seu(rtl_content, node_name, bit_position)

            results.append(result)

        return results

    def generate_test_case(
        self,
        rtl_content: str,
        fault_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """根据配置生成故障注入测试用例。

        Args:
            rtl_content: RTL 代码
            fault_config: 故障配置

        Returns:
            测试用例
        """
        test_case = {
            "test_id": fault_config.get("test_id", "TC_001"),
            "description": fault_config.get("description", ""),
            "faults": [],
        }

        for fault in fault_config.get("faults", []):
            fault_type = fault.get("type", "seu")
            if fault_type == "seu":
                result = self.inject_seu(
                    rtl_content,
                    fault["node_name"],
                    fault.get("bit_position", 0),
                )
            elif fault_type == "set":
                result = self.inject_set(
                    rtl_content,
                    fault["signal_name"],
                    fault.get("pulse_width", 1),
                )
            elif fault_type == "stuck_at":
                result = self.inject_stuck_at(
                    rtl_content,
                    fault["signal_name"],
                    fault.get("value", 0),
                )
            elif fault_type == "bridge":
                result = self.inject_bridge(
                    rtl_content,
                    fault["signal1"],
                    fault["signal2"],
                )
            else:
                continue

            test_case["faults"].append(result)

        return test_case

    def analyze_fault_effects(self, fault_results: List[Dict]) -> Dict[str, Any]:
        """分析故障注入效果。

        Args:
            fault_results: 故障注入结果列表

        Returns:
            分析结果
        """
        analysis = {
            "total_faults": len(fault_results),
            "applied_faults": sum(1 for r in fault_results if r["effect"] == "applied"),
            "skipped_faults": sum(1 for r in fault_results if r["effect"] == "skipped (node not found)" or r["effect"] == "skipped (signal not found)" or r["effect"] == "skipped (signals not found)"),
            "fault_by_type": {},
            "affected_nodes": set(),
        }

        for result in fault_results:
            fault_type = result["fault_type"]
            analysis["fault_by_type"][fault_type] = analysis["fault_by_type"].get(fault_type, 0) + 1

            if "node_name" in result:
                analysis["affected_nodes"].add(result["node_name"])
            if "signal_name" in result:
                analysis["affected_nodes"].add(result["signal_name"])
            if "signal1" in result:
                analysis["affected_nodes"].add(result["signal1"])
                analysis["affected_nodes"].add(result["signal2"])

        analysis["affected_nodes"] = list(analysis["affected_nodes"])
        return analysis

    def get_fault_report(self) -> Dict[str, Any]:
        """生成故障注入报告。

        Returns:
            故障报告
        """
        analysis = self.analyze_fault_effects(self._fault_history)

        return {
            "report_generated_at": "2026-07-16",
            "total_injections": len(self._fault_history),
            "analysis": analysis,
            "fault_history": self._fault_history,
        }

    def clear_history(self):
        """清空故障历史。"""
        self._fault_history = []


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

    injector = FaultInjector()

    print("=== SEU Injection Test ===")
    result = injector.inject_seu(test_rtl, "buffer", 3)
    print(f"Fault ID: {result['fault_id']}")
    print(f"Effect: {result['effect']}")

    print("\n=== SET Injection Test ===")
    result = injector.inject_set(test_rtl, "din", pulse_width=2)
    print(f"Fault ID: {result['fault_id']}")
    print(f"Effect: {result['effect']}")

    print("\n=== Stuck-at Injection Test ===")
    result = injector.inject_stuck_at(test_rtl, "rst", value=1)
    print(f"Fault ID: {result['fault_id']}")
    print(f"Effect: {result['effect']}")

    print("\n=== Bridge Injection Test ===")
    result = injector.inject_bridge(test_rtl, "din", "dout")
    print(f"Fault ID: {result['fault_id']}")
    print(f"Effect: {result['effect']}")

    print("\n=== Random Injection Test ===")
    results = injector.random_inject(test_rtl, num_faults=3, fault_type="seu")
    print(f"Random faults injected: {len(results)}")

    print("\n=== Fault Report ===")
    report = injector.get_fault_report()
    print(json.dumps(report, indent=2))
