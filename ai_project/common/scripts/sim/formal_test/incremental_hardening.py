#!/usr/bin/env python3
"""incremental_hardening.py — 增量加固模块

支持对已加固设计进行增量修改和验证，避免全量重新加固。

用法:
    from incremental_hardening import IncrementalHardener

    hardener = IncrementalHardener()
    result = hardener.incremental_update(original_rtl, modified_rtl, previous_hardened)
    report = hardener.get_update_report()
"""

import re
import json
from typing import List, Dict, Any, Optional


class IncrementalHardener:
    """增量加固器。

    支持对已加固设计进行增量修改和验证。
    """

    def __init__(self):
        """初始化增量加固器。"""
        self._update_history: List[Dict[str, Any]] = []

    def _parse_module(self, rtl_content: str) -> Dict[str, Any]:
        """解析 RTL 模块结构。

        Args:
            rtl_content: RTL 代码

        Returns:
            模块结构信息
        """
        module_info = {
            "name": "",
            "ports": [],
            "signals": [],
            "always_blocks": [],
            "assignments": [],
        }

        name_match = re.search(r"\bmodule\s+(\w+)\s*\(", rtl_content)
        if name_match:
            module_info["name"] = name_match.group(1)

        port_pattern = r"\b(input|output|inout)\s+(\[\d+:\d+\])?\s*(\w+)"
        ports = re.findall(port_pattern, rtl_content)
        for direction, width, name in ports:
            module_info["ports"].append({
                "name": name,
                "direction": direction,
                "width": width.strip() if width else "1",
            })

        signal_pattern = r"\b(reg|wire|logic)\s+(\[\d+:\d+\])?\s*(\w+)"
        signals = re.findall(signal_pattern, rtl_content)
        for sig_type, width, name in signals:
            module_info["signals"].append({
                "name": name,
                "type": sig_type,
                "width": width.strip() if width else "1",
            })

        always_blocks = re.findall(r"\balways\s+@\([^)]+\)\s*begin.*?end", rtl_content, re.DOTALL)
        module_info["always_blocks"] = len(always_blocks)

        assignments = re.findall(r"\bassign\s+\w+\s*=\s*[^;]+;", rtl_content)
        module_info["assignments"] = len(assignments)

        return module_info

    def _diff_modules(self, original: Dict, modified: Dict) -> Dict[str, Any]:
        """比较两个模块的差异。

        Args:
            original: 原始模块信息
            modified: 修改后模块信息

        Returns:
            差异信息
        """
        diff = {
            "added_ports": [],
            "removed_ports": [],
            "modified_ports": [],
            "added_signals": [],
            "removed_signals": [],
            "always_block_count_changed": False,
            "assignment_count_changed": False,
            "structure_changed": False,
        }

        original_ports = {p["name"]: p for p in original["ports"]}
        modified_ports = {p["name"]: p for p in modified["ports"]}

        for name, port in modified_ports.items():
            if name not in original_ports:
                diff["added_ports"].append(port)
            else:
                orig = original_ports[name]
                if orig["direction"] != port["direction"] or orig["width"] != port["width"]:
                    diff["modified_ports"].append((orig, port))

        for name, port in original_ports.items():
            if name not in modified_ports:
                diff["removed_ports"].append(port)

        original_signals = {s["name"] for s in original["signals"]}
        modified_signals = {s["name"] for s in modified["signals"]}

        for name in modified_signals:
            if name not in original_signals:
                diff["added_signals"].append(name)

        for name in original_signals:
            if name not in modified_signals:
                diff["removed_signals"].append(name)

        diff["always_block_count_changed"] = original["always_blocks"] != modified["always_blocks"]
        diff["assignment_count_changed"] = original["assignments"] != modified["assignments"]

        diff["structure_changed"] = (
            len(diff["added_ports"]) > 0 or
            len(diff["removed_ports"]) > 0 or
            len(diff["modified_ports"]) > 0 or
            diff["always_block_count_changed"] or
            diff["assignment_count_changed"]
        )

        return diff

    def incremental_update(
        self,
        original_rtl: str,
        modified_rtl: str,
        previous_hardened_rtl: str,
    ) -> Dict[str, Any]:
        """对已加固设计进行增量更新。

        Args:
            original_rtl: 原始 RTL 代码
            modified_rtl: 修改后的 RTL 代码
            previous_hardened_rtl: 之前加固后的 RTL 代码

        Returns:
            更新结果
        """
        original_info = self._parse_module(original_rtl)
        modified_info = self._parse_module(modified_rtl)
        diff = self._diff_modules(original_info, modified_info)

        update_type = "incremental"
        updated_hardened = previous_hardened_rtl

        if diff["structure_changed"]:
            update_type = "full"
            updated_hardened = "REQUIRES_FULL_REHARDENING"
        else:
            for signal in diff["added_signals"]:
                updated_hardened = re.sub(
                    r"(endmodule)",
                    f"    reg [7:0] {signal};\n\\1",
                    updated_hardened,
                )

            for signal in diff["removed_signals"]:
                updated_hardened = re.sub(
                    rf"\b(reg|wire|logic)\s+(\[\d+:\d+\])?\s*{signal};\n?",
                    "",
                    updated_hardened,
                )

        result = {
            "update_type": update_type,
            "diff": diff,
            "original_info": original_info,
            "modified_info": modified_info,
            "updated_hardened": updated_hardened,
            "requires_full_rehardening": update_type == "full",
        }

        self._update_history.append(result)
        return result

    def validate_incremental_change(
        self,
        original_rtl: str,
        modified_rtl: str,
    ) -> Dict[str, Any]:
        """验证增量变更的可行性。

        Args:
            original_rtl: 原始 RTL 代码
            modified_rtl: 修改后的 RTL 代码

        Returns:
            验证结果
        """
        original_info = self._parse_module(original_rtl)
        modified_info = self._parse_module(modified_rtl)
        diff = self._diff_modules(original_info, modified_info)

        validation = {
            "is_valid": True,
            "issues": [],
            "warnings": [],
            "change_summary": {},
        }

        if diff["structure_changed"]:
            validation["is_valid"] = False
            validation["issues"].append("模块结构发生变化，需要全量重新加固")

        if len(diff["added_ports"]) > 0:
            validation["warnings"].append(f"新增 {len(diff['added_ports'])} 个端口")

        if len(diff["removed_ports"]) > 0:
            validation["issues"].append(f"删除 {len(diff['removed_ports'])} 个端口")

        if len(diff["modified_ports"]) > 0:
            validation["issues"].append(f"修改 {len(diff['modified_ports'])} 个端口")

        validation["change_summary"] = {
            "added_ports": [p["name"] for p in diff["added_ports"]],
            "removed_ports": [p["name"] for p in diff["removed_ports"]],
            "modified_ports": [o["name"] for o, m in diff["modified_ports"]],
            "added_signals": diff["added_signals"],
            "removed_signals": diff["removed_signals"],
            "always_blocks_changed": diff["always_block_count_changed"],
            "assignments_changed": diff["assignment_count_changed"],
        }

        return validation

    def get_update_report(self) -> Dict[str, Any]:
        """生成更新报告。

        Returns:
            更新报告
        """
        report = {
            "total_updates": len(self._update_history),
            "incremental_updates": sum(1 for u in self._update_history if u["update_type"] == "incremental"),
            "full_updates": sum(1 for u in self._update_history if u["update_type"] == "full"),
            "history": self._update_history,
        }

        return report

    def clear_history(self):
        """清空更新历史。"""
        self._update_history = []


if __name__ == "__main__":
    original_rtl = """
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

    modified_rtl = """
module test_module(
    input clk,
    input rst,
    input [7:0] din,
    output [7:0] dout,
    output [7:0] status
);
    reg [7:0] buffer;
    reg [7:0] status_reg;
    always @(posedge clk or posedge rst) begin
        if (rst) buffer <= 0;
        else buffer <= din;
    end
    always @(posedge clk) begin
        status_reg <= buffer;
    end
    assign dout = buffer;
    assign status = status_reg;
endmodule
"""

    hardened_rtl = """
module test_module_tmr(
    input clk,
    input rst,
    input [7:0] din,
    output [7:0] dout
);
    reg [7:0] buffer_0, buffer_1, buffer_2;
    always @(posedge clk or posedge rst) begin
        if (rst) begin buffer_0 <= 0; buffer_1 <= 0; buffer_2 <= 0; end
        else begin buffer_0 <= din; buffer_1 <= din; buffer_2 <= din; end
    end
    assign dout = (buffer_0 & buffer_1) | (buffer_0 & buffer_2) | (buffer_1 & buffer_2);
endmodule
"""

    hardener = IncrementalHardener()

    print("=== Validation Test ===")
    validation = hardener.validate_incremental_change(original_rtl, modified_rtl)
    print(f"Is valid: {validation['is_valid']}")
    print(f"Issues: {validation['issues']}")
    print(f"Warnings: {validation['warnings']}")

    print("\n=== Incremental Update Test ===")
    result = hardener.incremental_update(original_rtl, modified_rtl, hardened_rtl)
    print(f"Update type: {result['update_type']}")
    print(f"Requires full rehardening: {result['requires_full_rehardening']}")

    print("\n=== Update Report ===")
    report = hardener.get_update_report()
    print(json.dumps(report, indent=2))
