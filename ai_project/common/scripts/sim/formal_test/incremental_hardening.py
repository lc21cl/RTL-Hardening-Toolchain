#!/usr/bin/env python3
"""incremental_hardening.py — 增量加固模块

支持对已加固设计进行增量修改和验证，避免全量重新加固。
支持信号级别的细粒度增量更新，包括信号宽度、类型、赋值语句变更。

用法:
    from incremental_hardening import IncrementalHardener

    hardener = IncrementalHardener()
    result = hardener.incremental_update(original_rtl, modified_rtl, previous_hardened)
    report = hardener.get_update_report()
    signal_diff = hardener.get_signal_level_diff()
    patch = hardener.generate_incremental_patch()
"""

import re
import json
from typing import List, Dict, Any, Optional, Set, Tuple


class IncrementalHardener:
    """增量加固器。

    支持对已加固设计进行增量修改和验证。
    """

    def __init__(self):
        """初始化增量加固器。"""
        self._update_history: List[Dict[str, Any]] = []
        self._last_diff: Optional[Dict[str, Any]] = None
        self._last_original_info: Optional[Dict[str, Any]] = None
        self._last_modified_info: Optional[Dict[str, Any]] = None
        self._last_signal_level_diff: Optional[List[Dict[str, Any]]] = None

    def _parse_width(self, width_str: str) -> Dict[str, Any]:
        """解析信号宽度字符串，支持 [7:0]、[0:7]、[WIDTH-1:0] 等格式。

        Args:
            width_str: 宽度字符串，如 "[7:0]", "1" 或空

        Returns:
            详细的宽度信息字典
        """
        result: Dict[str, Any] = {
            "msb": 0,
            "lsb": 0,
            "size": 1,
            "is_packed": False,
            "raw": width_str,
            "msb_str": "",
            "lsb_str": "",
        }
        if not width_str or width_str == "1":
            return result

        m = re.match(r'\[\s*(\S+)\s*:\s*(\S+)\s*\]', width_str)
        if m:
            msb_str, lsb_str = m.group(1), m.group(2)
            result["is_packed"] = True
            result["msb_str"] = msb_str
            result["lsb_str"] = lsb_str
            # 尝试数值解析
            try:
                msb = int(msb_str)
                lsb = int(lsb_str)
                result["msb"] = msb
                result["lsb"] = lsb
                result["size"] = abs(msb - lsb) + 1
            except ValueError:
                pass
        return result

    def _extract_always_block_body(self, text: str, start_pos: int) -> Tuple[str, int]:
        """从文本中提取 always 块的主体内容。

        Args:
            text: 完整文本
            start_pos: always 块开始的起始位置

        Returns:
            (主体内容字符串, 结束位置)
        """
        remaining = text[start_pos:]
        # 跳过空白和注释
        body_start = re.search(r'\S', remaining)
        if not body_start:
            return "", start_pos
        remaining = remaining[body_start.start():]

        # 检查是否以 begin 开头
        has_begin = bool(re.match(r'begin\b', remaining))

        if has_begin:
            # 需要匹配 begin...end，处理嵌套
            depth = 0
            i = 0
            in_block_comment = False
            while i < len(remaining):
                if remaining[i:i+2] == "/*":
                    in_block_comment = True
                    i += 2
                    continue
                if remaining[i:i+2] == "*/":
                    in_block_comment = False
                    i += 2
                    continue
                if not in_block_comment:
                    # 行注释，跳过到行尾
                    if remaining[i:i+2] == "//":
                        nl = remaining.find('\n', i)
                        i = nl + 1 if nl >= 0 else len(remaining)
                        continue
                    # 检查 begin（不是 begin 的一部分的更长的标识符）
                    if remaining[i:i+5] == "begin" and (i+5 >= len(remaining) or not remaining[i+5].isalnum() and remaining[i+5] != '_'):
                        depth += 1
                        i += 5
                        continue
                    if remaining[i:i+3] == "end" and (i+3 >= len(remaining) or not remaining[i+3].isalnum() and remaining[i+3] != '_'):
                        depth -= 1
                        i += 3
                        if depth == 0:
                            body_end = start_pos + body_start.start() + i
                            body_text = text[start_pos + body_start.start():body_end]
                            return body_text, body_end
                        continue
                i += 1
            # 没有匹配到 end，返回整个剩余文本
            return text[start_pos + body_start.start():], len(text)
        else:
            # 没有 begin/end，查找单个语句
            stmt = re.match(r'\s*([^;]+;)', remaining)
            if stmt:
                stmt_end = start_pos + body_start.start() + stmt.end()
                return text[start_pos + body_start.start():stmt_end], stmt_end
            return remaining[:200], start_pos + body_start.start() + 200

    def _parse_module(self, rtl_content: str) -> Dict[str, Any]:
        """解析 RTL 模块结构，支持信号级别的细粒度解析。

        Args:
            rtl_content: RTL 代码

        Returns:
            模块结构信息
        """
        module_info: Dict[str, Any] = {
            "name": "",
            "ports": [],
            "signals": [],      # 信号声明列表，每个元素包含 name, type, width, width_msb, width_lsb 等
            "always_blocks": [],  # always 块列表，每个元素为 dict
            "assignments": [],    # assign 语句列表，每个元素为 dict
            "fanout_map": {},     # signal_name -> 被引用次数（扇出）
            "all_assignments": [],  # 所有赋值语句（包括 always 块内的），用于扇出分析
        }

        # ── 模块名 ──
        name_match = re.search(r"\bmodule\s+(\w+)\s*\(", rtl_content)
        if name_match:
            module_info["name"] = name_match.group(1)

        # ── 端口解析 ──
        port_pattern = r"\b(input|output|inout)\s+(\[\s*\S+\s*:\s*\S+\s*\])?\s*(\w+)"
        ports = re.findall(port_pattern, rtl_content)
        for direction, width, name in ports:
            pw = self._parse_width(width.strip() if width else "1")
            module_info["ports"].append({
                "name": name,
                "direction": direction,
                "width": width.strip() if width else "1",
                "width_msb": pw["msb"],
                "width_lsb": pw["lsb"],
                "width_size": pw["size"],
                "width_expr": width.strip() if width else "",
                "width_raw": pw["raw"],
            })

        # ── 信号声明解析 ──
        signal_pattern = r"\b(reg|wire|logic)\s+(\[\s*\S+\s*:\s*\S+\s*\])?\s*(\w+)"
        signals = re.findall(signal_pattern, rtl_content)
        for sig_type, width, name in signals:
            pw = self._parse_width(width.strip() if width else "1")
            module_info["signals"].append({
                "name": name,
                "type": sig_type,
                "width": width.strip() if width else "1",
                "width_msb": pw["msb"],
                "width_lsb": pw["lsb"],
                "width_size": pw["size"],
                "width_expr": width.strip() if width else "",
                "width_raw": pw["raw"],
                "is_packed": pw["is_packed"],
            })

        # ── always 块解析 ──
        always_pattern = re.compile(r'always\s+@\s*\(([^)]*)\)')
        for m in always_pattern.finditer(rtl_content):
            sensitivity = m.group(1).strip()
            body_text, _ = self._extract_always_block_body(rtl_content, m.end())

            # 判断逻辑类型
            has_edge = bool(re.search(r'\b(posedge|negedge)\b', sensitivity))
            block_type = "sequential" if has_edge else "combinational"

            # 提取块内赋值语句
            assignments = []
            # 匹配 <signal> <= <expr>; 和 <signal> = <expr>;（排除条件判断中的 ==）
            assign_pattern = re.compile(r'(\w+)\s*(<=|=)\s*([^;]+);')
            for am in assign_pattern.finditer(body_text):
                target = am.group(1)
                op = am.group(2)
                expr = am.group(3).strip()
                # 排除用作条件判断的 ==，但保留 <= 和 =
                if op != '==':
                    assignments.append({
                        "target": target,
                        "operator": op,
                        "expression": expr,
                    })
                    # 记录到 all_assignments 用于扇出分析
                    module_info["all_assignments"].append({
                        "target": target,
                        "source": expr,
                    })

            block_info = {
                "type": block_type,
                "sensitivity": sensitivity,
                "assignments": assignments,
                "raw": body_text,
            }
            module_info["always_blocks"].append(block_info)

        # ── assign 语句解析 ──
        assign_pattern = re.compile(r'\bassign\s+(\w+)\s*=\s*([^;]+);')
        for am in assign_pattern.finditer(rtl_content):
            target = am.group(1)
            expr = am.group(2).strip()
            assign_info = {
                "target": target,
                "expression": expr,
            }
            module_info["assignments"].append(assign_info)
            module_info["all_assignments"].append({
                "target": target,
                "source": expr,
            })

        # ── 扇出分析 ──
        fanout_map: Dict[str, int] = {}
        for sig in module_info["signals"]:
            sig_name = sig["name"]
            count = 0
            for assign in module_info["all_assignments"]:
                # 检查信号名是否出现在赋值表达式右侧（作为源被引用）
                if re.search(r'\b' + re.escape(sig_name) + r'\b', assign["source"]):
                    count += 1
            fanout_map[sig_name] = count
        module_info["fanout_map"] = fanout_map

        return module_info

    def _diff_modules(self, original: Dict, modified: Dict) -> Dict[str, Any]:
        """比较两个模块的差异，支持信号级别的细粒度检测。

        Args:
            original: 原始模块信息
            modified: 修改后模块信息

        Returns:
            差异信息
        """
        diff: Dict[str, Any] = {
            "added_ports": [],
            "removed_ports": [],
            "modified_ports": [],
            "added_signals": [],
            "removed_signals": [],
            "modified_signals": [],       # 信号级别变更（宽度、类型修改）
            "changed_always_blocks": [],   # 变化的 always 块索引
            "changed_assignments": [],     # 变化的 assign 语句
            "fanout_changed_signals": [],  # 扇出变化的信号
            "always_block_count_changed": False,
            "assignment_count_changed": False,
            "structure_changed": False,
        }

        # ── 端口差异 ──
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

        # ── 信号差异 ──
        original_signals = {s["name"]: s for s in original["signals"]}
        modified_signals = {s["name"]: s for s in modified["signals"]}

        for name, sig in modified_signals.items():
            if name not in original_signals:
                diff["added_signals"].append(name)
            else:
                orig = original_signals[name]
                # 检测宽度变更
                width_changed = orig["width"] != sig["width"]
                # 检测类型变更（reg <-> wire）
                type_changed = orig["type"] != sig["type"]
                if width_changed or type_changed:
                    diff["modified_signals"].append({
                        "name": name,
                        "width_changed": width_changed,
                        "type_changed": type_changed,
                        "original": orig,
                        "modified": sig,
                    })

        for name, sig in original_signals.items():
            if name not in modified_signals:
                diff["removed_signals"].append(name)

        # ── always 块差异 ──
        orig_always = original["always_blocks"]
        mod_always = modified["always_blocks"]
        diff["always_block_count_changed"] = len(orig_always) != len(mod_always)

        min_always_len = min(len(orig_always), len(mod_always))
        for i in range(min_always_len):
            oa = orig_always[i]
            ma = mod_always[i]
            if oa["type"] != ma["type"] or oa["sensitivity"] != ma["sensitivity"]:
                diff["changed_always_blocks"].append({
                    "index": i,
                    "type": "structure_changed",
                    "original": oa,
                    "modified": ma,
                })
            else:
                # 比较具体的赋值语句
                orig_assigns = {(a["target"], a["operator"]): a["expression"] for a in oa["assignments"]}
                mod_assigns = {(a["target"], a["operator"]): a["expression"] for a in ma["assignments"]}
                changed = False
                assign_diffs = []
                for key, expr in mod_assigns.items():
                    if key not in orig_assigns:
                        assign_diffs.append({
                            "change": "added",
                            "target": key[0],
                            "operator": key[1],
                            "expression": expr,
                        })
                        changed = True
                    elif orig_assigns[key] != expr:
                        assign_diffs.append({
                            "change": "modified",
                            "target": key[0],
                            "operator": key[1],
                            "old_expression": orig_assigns[key],
                            "new_expression": expr,
                        })
                        changed = True
                for key, expr in orig_assigns.items():
                    if key not in mod_assigns:
                        assign_diffs.append({
                            "change": "removed",
                            "target": key[0],
                            "operator": key[1],
                            "expression": expr,
                        })
                        changed = True
                if changed:
                    diff["changed_always_blocks"].append({
                        "index": i,
                        "type": "assignments_changed",
                        "assign_diffs": assign_diffs,
                        "original": oa,
                        "modified": ma,
                    })

        # ── assign 语句差异 ──
        orig_assign_map = {a["target"]: a["expression"] for a in original["assignments"]}
        mod_assign_map = {a["target"]: a["expression"] for a in modified["assignments"]}
        assign_changed = False
        for target, expr in mod_assign_map.items():
            if target not in orig_assign_map:
                diff["changed_assignments"].append({
                    "change": "added",
                    "target": target,
                    "expression": expr,
                })
                assign_changed = True
            elif orig_assign_map[target] != expr:
                diff["changed_assignments"].append({
                    "change": "modified",
                    "target": target,
                    "old_expression": orig_assign_map[target],
                    "new_expression": expr,
                })
                assign_changed = True
        for target, expr in orig_assign_map.items():
            if target not in mod_assign_map:
                diff["changed_assignments"].append({
                    "change": "removed",
                    "target": target,
                    "expression": expr,
                })
                assign_changed = True

        diff["assignment_count_changed"] = (
            len(original["assignments"]) != len(modified["assignments"]) or assign_changed
        )

        # ── 扇出变化检测 ──
        orig_fanout = original.get("fanout_map", {})
        mod_fanout = modified.get("fanout_map", {})
        all_sigs = set(orig_fanout.keys()) | set(mod_fanout.keys())
        for sig in all_sigs:
            orig_count = orig_fanout.get(sig, 0)
            mod_count = mod_fanout.get(sig, 0)
            if orig_count != mod_count:
                diff["fanout_changed_signals"].append({
                    "name": sig,
                    "original_fanout": orig_count,
                    "modified_fanout": mod_count,
                })

        # ── 结构变更判定 ──
        # 端口变化和 always 块数量变化仍视为结构变更
        diff["structure_changed"] = (
            len(diff["added_ports"]) > 0 or
            len(diff["removed_ports"]) > 0 or
            len(diff["modified_ports"]) > 0 or
            diff["always_block_count_changed"] or
            any(b.get("type") == "structure_changed" for b in diff["changed_always_blocks"])
        )

        return diff

    def incremental_update(
        self,
        original_rtl: str,
        modified_rtl: str,
        previous_hardened_rtl: str,
    ) -> Dict[str, Any]:
        """对已加固设计进行增量更新。

        支持信号级别的细粒度增量更新：
        - 新增/删除信号
        - 信号宽度变更
        - 信号类型变更（reg/wire/logic 切换）
        - 赋值语句变更（always 块内赋值、assign 语句）
        - 结构变更则要求全量重新加固

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

        # 保存中间结果供其他方法使用
        self._last_diff = diff
        self._last_original_info = original_info
        self._last_modified_info = modified_info

        update_type = "incremental"
        updated_hardened = previous_hardened_rtl

        if diff["structure_changed"]:
            update_type = "full"
            updated_hardened = "REQUIRES_FULL_REHARDENING"
        else:
            # ── 删除信号 ──
            for signal in diff["removed_signals"]:
                updated_hardened = re.sub(
                    rf"\b(reg|wire|logic)\s+(\[\s*\S+\s*:\s*\S+\s*\])?\s*{signal}\s*;?\n?",
                    "",
                    updated_hardened,
                )

            # ── 修改信号（宽度或类型变更） ──
            for mod_sig in diff["modified_signals"]:
                sig_name = mod_sig["name"]
                orig_sig = mod_sig["original"]
                new_sig = mod_sig["modified"]

                # 在 hardened 代码中查找原始信号声明并更新
                old_decl_pattern = (
                    rf"\b({orig_sig['type']})\s+"
                    rf"({re.escape(orig_sig['width'])}\s+)?"
                    rf"{re.escape(sig_name)}\s*;"
                )

                new_width = new_sig["width"]
                new_type = new_sig["type"]

                # 构建新的声明
                if new_width and new_width != "1":
                    new_decl = f"{new_type} {new_width} {sig_name};"
                else:
                    new_decl = f"{new_type} {sig_name};"

                updated_hardened = re.sub(
                    old_decl_pattern,
                    new_decl,
                    updated_hardened,
                )

            # ── 新增信号 ──
            for signal in diff["added_signals"]:
                # 查找新增信号在 modified 中的声明
                new_sig_info = None
                for s in modified_info["signals"]:
                    if s["name"] == signal:
                        new_sig_info = s
                        break
                if new_sig_info:
                    new_type = new_sig_info["type"]
                    new_width = new_sig_info["width"]
                    if new_width and new_width != "1":
                        decl = f"    {new_type} {new_width} {signal};\n"
                    else:
                        decl = f"    {new_type} {signal};\n"
                    updated_hardened = re.sub(
                        r"(endmodule)",
                        decl + "\\1",
                        updated_hardened,
                    )
                else:
                    # 回退：默认使用 reg [7:0]
                    updated_hardened = re.sub(
                        r"(endmodule)",
                        f"    reg [7:0] {signal};\n\\1",
                        updated_hardened,
                    )

            # ── 赋值语句变更（assign 语句） ──
            for chg in diff["changed_assignments"]:
                if chg["change"] == "modified":
                    # 替换已变更的 assign 语句
                    old_assign = rf"assign\s+{re.escape(chg['target'])}\s*=\s*{re.escape(chg['old_expression'])};"
                    new_assign = f"assign {chg['target']} = {chg['new_expression']};"
                    updated_hardened = re.sub(old_assign, new_assign, updated_hardened)

        # ── 构建顶级快捷字段（兼容 hardening_pipeline.py 的访问方式） ──
        result: Dict[str, Any] = {
            "update_type": update_type,
            "diff": diff,
            "original_info": original_info,
            "modified_info": modified_info,
            "updated_hardened": updated_hardened,
            "requires_full_rehardening": update_type == "full",
            # 顶层快捷字段，兼容调用方代码
            "added_signals": diff["added_signals"],
            "removed_signals": diff["removed_signals"],
            "modified_signals": [s["name"] for s in diff.get("modified_signals", [])],
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

        validation: Dict[str, Any] = {
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

        if len(diff["modified_signals"]) > 0:
            validation["warnings"].append(
                f"信号变更 {len(diff['modified_signals'])} 个: "
                + ", ".join(s["name"] for s in diff["modified_signals"])
            )

        validation["change_summary"] = {
            "added_ports": [p["name"] for p in diff["added_ports"]],
            "removed_ports": [p["name"] for p in diff["removed_ports"]],
            "modified_ports": [o["name"] for o, m in diff["modified_ports"]],
            "added_signals": diff["added_signals"],
            "removed_signals": diff["removed_signals"],
            "modified_signals": [s["name"] for s in diff["modified_signals"]],
            "changed_always_blocks": [b["index"] for b in diff["changed_always_blocks"]],
            "fanout_changed_signals": [s["name"] for s in diff["fanout_changed_signals"]],
            "always_blocks_changed": diff["always_block_count_changed"] or len(diff["changed_always_blocks"]) > 0,
            "assignments_changed": diff["assignment_count_changed"],
        }

        return validation

    def get_signal_level_diff(self, original_rtl: str = None, modified_rtl: str = None) -> List[Dict[str, Any]]:
        """获取每个信号的详细差异信息。

        两种调用方式:
        1. get_signal_level_diff() — 在 incremental_update() 之后调用，使用内部缓存
        2. get_signal_level_diff(original_rtl, modified_rtl) — 直接解析两段RTL代码进行对比

        Args:
            original_rtl: 原始RTL代码（可选）
            modified_rtl: 修改后RTL代码（可选）

        Returns:
            信号级别差异列表，每个元素包含：
            - name: 信号名
            - original: 原始信号信息（或 None）
            - modified: 修改后信号信息（或 None）
            - change_type: 变更类型
            - affects_hardening: 是否影响加固逻辑
            - details: 详细描述
        """
        # 如果提供了两个RTL字符串，直接解析并对比
        if original_rtl is not None and modified_rtl is not None:
            orig_info = self._parse_module(original_rtl)
            mod_info = self._parse_module(modified_rtl)
            return self._compute_signal_diffs(orig_info, mod_info)
        
        # 否则使用内部缓存（需先调用 incremental_update）
        if self._last_diff is None or self._last_original_info is None or self._last_modified_info is None:
            return []
        
        return self._compute_signal_diffs(self._last_original_info, self._last_modified_info)
    
    def _compute_signal_diffs(self, orig_info: Dict, mod_info: Dict) -> List[Dict[str, Any]]:
        """计算两个模块信息之间的信号级别差异"""
        signal_diffs: List[Dict[str, Any]] = []
        
        orig_sigs = {s["name"]: s for s in orig_info["signals"]}
        mod_sigs = {s["name"]: s for s in mod_info["signals"]}
        orig_fanout = orig_info.get("fanout_map", {})
        mod_fanout = mod_info.get("fanout_map", {})
        
        all_names: Set[str] = set(orig_sigs.keys()) | set(mod_sigs.keys())

        for name in sorted(all_names):
            orig = orig_sigs.get(name)
            mod = mod_sigs.get(name)
            change_type = "unchanged"
            details = []
            affects_hardening = False

            if orig is None and mod is not None:
                change_type = "added"
                details.append(f"新增信号 {name}")
                affects_hardening = True
            elif orig is not None and mod is None:
                change_type = "removed"
                details.append(f"删除信号 {name}")
                affects_hardening = True
            elif orig is not None and mod is not None:
                width_changed = orig["width"] != mod["width"]
                type_changed = orig["type"] != mod["type"]
                fanout_orig = orig_fanout.get(name, 0)
                fanout_mod = mod_fanout.get(name, 0)
                fanout_changed = fanout_orig != fanout_mod

                if width_changed and type_changed:
                    change_type = "width_and_type_changed"
                    details.append(
                        f"宽度: {orig['width']} -> {mod['width']}, "
                        f"类型: {orig['type']} -> {mod['type']}"
                    )
                    affects_hardening = True
                elif width_changed:
                    change_type = "width_changed"
                    details.append(f"宽度: {orig['width']} -> {mod['width']}")
                    affects_hardening = True
                elif type_changed:
                    change_type = "type_changed"
                    details.append(f"类型: {orig['type']} -> {mod['type']}")
                    affects_hardening = True

                if fanout_changed:
                    if change_type == "unchanged":
                        change_type = "fanout_changed"
                    details.append(f"扇出: {fanout_orig} -> {fanout_mod}")
                    # 扇出变化不一定影响加固逻辑，记录但标记

            signal_diffs.append({
                "name": name,
                "original": orig,
                "modified": mod,
                "change_type": change_type,
                "affects_hardening": affects_hardening,
                "details": "; ".join(details),
            })

        # 缓存以供 generate_incremental_patch 使用
        self._last_signal_level_diff = signal_diffs
        return signal_diffs

    def generate_incremental_patch(self, original_rtl: str = None, modified_rtl: str = None) -> Dict[str, Any]:
        """生成可应用的增量补丁（patch）文本。

        两种调用方式:
        1. generate_incremental_patch() — 在 incremental_update() 之后调用
        2. generate_incremental_patch(original_rtl, modified_rtl) — 直接解析两段RTL

        Returns:
            增量补丁信息，包含：
            - patch_lines: 补丁文本行列表
            - patch_text: 完整的补丁文本
            - changes: 变更摘要
        """
        # 如果提供了两个RTL字符串，先解析对比
        if original_rtl is not None and modified_rtl is not None:
            orig_info = self._parse_module(original_rtl)
            mod_info = self._parse_module(modified_rtl)
            diff = self._diff_modules(orig_info, mod_info)
        elif self._last_diff is None or self._last_original_info is None or self._last_modified_info is None:
            return {
                "patch_lines": [],
                "patch_text": "",
                "changes": [],
                "error": "请先调用 incremental_update()",
            }
        else:
            diff = self._last_diff
            orig_info = self._last_original_info
            mod_info = self._last_modified_info

        changes: List[Dict[str, Any]] = []
        patch_lines: List[str] = []
        
        orig_sigs = {s["name"]: s for s in orig_info.get("signals", [])}
        mod_sigs = {s["name"]: s for s in mod_info.get("signals", [])}

        patch_lines.append("--- 增量加固补丁 ---")
        patch_lines.append(f"模块结构变更: {'是' if diff['structure_changed'] else '否'}")
        patch_lines.append("")

        # ── 删除的信号 ──
        for sig_name in diff["removed_signals"]:
            orig = orig_sigs[sig_name]
            old_decl = f"{orig['type']} {orig['width']} {sig_name}".strip()
            changes.append({
                "type": "remove_signal",
                "target": sig_name,
                "old": old_decl,
                "patch": f"删除声明: {old_decl}",
            })
            patch_lines.append(f"删除信号: {sig_name}")
            patch_lines.append(f"  - 原声明: {old_decl}")

        # ── 修改的信号 ──
        for mod_sig in diff["modified_signals"]:
            sig_name = mod_sig["name"]
            orig = mod_sig["original"]
            new = mod_sig["modified"]
            old_decl = f"{orig['type']} {orig['width']} {sig_name}".strip()
            new_decl = f"{new['type']} {new['width']} {sig_name}".strip()
            changes.append({
                "type": "modify_signal",
                "target": sig_name,
                "old": old_decl,
                "new": new_decl,
                "patch": f"{old_decl} -> {new_decl}",
            })
            patch_lines.append(f"修改信号: {sig_name}")
            patch_lines.append(f"  - 原声明: {old_decl}")
            patch_lines.append(f"  - 新声明: {new_decl}")

        # ── 新增的信号 ──
        for sig_name in diff["added_signals"]:
            mod = mod_sigs.get(sig_name)
            if mod:
                new_decl = f"{mod['type']} {mod['width']} {sig_name}".strip()
            else:
                new_decl = f"reg [7:0] {sig_name}"
            changes.append({
                "type": "add_signal",
                "target": sig_name,
                "new": new_decl,
                "patch": f"添加声明: {new_decl}",
            })
            patch_lines.append(f"新增信号: {sig_name}")
            patch_lines.append(f"  - 新声明: {new_decl}")

        # ── 变化的 assign 语句 ──
        for chg in diff["changed_assignments"]:
            if chg["change"] == "modified":
                entry = {
                    "type": "modify_assign",
                    "target": chg["target"],
                    "old": f"assign {chg['target']} = {chg['old_expression']};",
                    "new": f"assign {chg['target']} = {chg['new_expression']};",
                    "patch": f"assign {chg['target']} = {chg['old_expression']}; -> assign {chg['target']} = {chg['new_expression']};",
                }
                changes.append(entry)
                patch_lines.append(f"修改 assign 语句: {chg['target']}")
                patch_lines.append(f"  - 原语句: assign {chg['target']} = {chg['old_expression']};")
                patch_lines.append(f"  - 新语句: assign {chg['target']} = {chg['new_expression']};")
            elif chg["change"] == "added":
                entry = {
                    "type": "add_assign",
                    "target": chg["target"],
                    "new": f"assign {chg['target']} = {chg['expression']};",
                    "patch": f"assign {chg['target']} = {chg['expression']};",
                }
                changes.append(entry)
                patch_lines.append(f"新增 assign 语句: {chg['target']}")
                patch_lines.append(f"  - assign {chg['target']} = {chg['expression']};")

        # ── 变化的 always 块 ──
        for blk in diff["changed_always_blocks"]:
            if blk["type"] == "assignments_changed":
                for ad in blk.get("assign_diffs", []):
                    if ad["change"] == "modified":
                        entry = {
                            "type": "modify_always_assign",
                            "target": ad["target"],
                            "old": f"{ad['target']} {ad['operator']} {ad['old_expression']};",
                            "new": f"{ad['target']} {ad['operator']} {ad['new_expression']};",
                            "block_index": blk["index"],
                            "patch": f"always@{blk['index']}: {ad['target']} {ad['operator']} {ad['old_expression']} -> {ad['new_expression']}",
                        }
                        changes.append(entry)
                        patch_lines.append(
                            f"修改 always@{blk['index']} 赋值: {ad['target']}"
                        )
                        patch_lines.append(
                            f"  - {ad['target']} {ad['operator']} {ad['old_expression']};"
                        )
                        patch_lines.append(
                            f"  - {ad['target']} {ad['operator']} {ad['new_expression']};"
                        )

        # ── 扇出变化 ──
        for fs in diff["fanout_changed_signals"]:
            patch_lines.append(
                f"扇出变化: {fs['name']} ({fs['original_fanout']} -> {fs['modified_fanout']})"
            )

        patch_text = "\n".join(patch_lines)

        return {
            "patch_lines": patch_lines,
            "patch_text": patch_text,
            "changes": changes,
            "error": None,
        }

    def get_update_report(self) -> Dict[str, Any]:
        """生成更新报告。

        Returns:
            更新报告
        """
        report: Dict[str, Any] = {
            "total_updates": len(self._update_history),
            "incremental_updates": sum(1 for u in self._update_history if u["update_type"] == "incremental"),
            "full_updates": sum(1 for u in self._update_history if u["update_type"] == "full"),
            "history": self._update_history,
        }

        return report

    def clear_history(self):
        """清空更新历史。"""
        self._update_history = []
        self._last_diff = None
        self._last_original_info = None
        self._last_modified_info = None
        self._last_signal_level_diff = None


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
    output [7:0] dout
);
    reg [15:0] buffer;
    wire [7:0] status;
    always @(posedge clk or posedge rst) begin
        if (rst) buffer <= 0;
        else buffer <= din;
    end
    assign dout = buffer;
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
    print(f"Change summary: {json.dumps(validation['change_summary'], indent=2, ensure_ascii=False)}")

    print("\n=== Incremental Update Test ===")
    result = hardener.incremental_update(original_rtl, modified_rtl, hardened_rtl)
    print(f"Update type: {result['update_type']}")
    print(f"Requires full rehardening: {result['requires_full_rehardening']}")
    print(f"Modified signals: {result.get('modified_signals', [])}")
    if result['update_type'] == 'incremental':
        print("\n=== Updated Hardened RTL ===")
        print(result['updated_hardened'])

    print("\n=== Signal-Level Diff ===")
    signal_diff = hardener.get_signal_level_diff()
    for sd in signal_diff:
        print(f"  {sd['name']}: {sd['change_type']} | affects_hardening={sd['affects_hardening']} | {sd['details']}")

    print("\n=== Incremental Patch ===")
    patch = hardener.generate_incremental_patch()
    print(patch['patch_text'])
    print(f"\nTotal changes: {len(patch['changes'])}")

    print("\n=== Update Report ===")
    report = hardener.get_update_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
