#!/usr/bin/env python3
"""rtl_parser.py — 统一的 RTL 解析工具。

消除 graph_pipeline.py、verification_engine.py、ast_repairer.py 中
重复的端口解析、注释清理、模块名提取等逻辑。

提供:
  - strip_rtl_comments()  — 移除 Verilog 注释
  - extract_module_name() — 提取模块名
  - extract_ports()       — 解析端口列表
  - extract_signals()     — 提取所有声明信号
"""

import re
from typing import Dict, List, Optional, Tuple


def strip_rtl_comments(content: str) -> str:
    """移除 Verilog RTL 中的注释。

    处理:
      - 行注释 `// ...`
      - 块注释 `/* ... */`
      - 避免误处理字符串中的 `//` 字面量（如 $display("//")）

    Args:
        content: 原始 RTL 源代码。

    Returns:
        移除注释后的代码。
    """
    # 先保护字符串字面量
    strings: List[str] = []
    def _protect_strings(m):
        strings.append(m.group(0))
        return f'__STR_{len(strings)-1}__'

    # 保护双引号字符串
    content_protected = re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', _protect_strings, content)

    # 移除行注释（非字符串内）
    content_protected = re.sub(r'//.*?$', '', content_protected, flags=re.MULTILINE)
    # 移除块注释
    content_protected = re.sub(r'/\*.*?\*/', '', content_protected, flags=re.DOTALL)

    # 恢复字符串字面量
    for i, s in enumerate(strings):
        content_protected = content_protected.replace(f'__STR_{i}__', s)

    return content_protected


def extract_module_name(content: str) -> Optional[str]:
    """从 RTL 内容中提取第一个模块名。

    Args:
        content: 原始 RTL 源代码。

    Returns:
        模块名，未找到时返回 None。
    """
    content_clean = strip_rtl_comments(content)
    match = re.search(r'\bmodule\s+(\w+)', content_clean)
    return match.group(1) if match else None


def extract_module_name_from_file(rtl_path: str) -> Optional[str]:
    """从 RTL 文件中提取第一个模块名。

    Args:
        rtl_path: RTL 文件路径。

    Returns:
        模块名，未找到或文件读取失败时返回 None。
    """
    try:
        with open(rtl_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return extract_module_name(content)
    except OSError:
        return None


def extract_ports(content: str) -> Dict[str, List[Dict]]:
    """从 RTL 内容中提取所有模块的端口声明。

    支持:
      - input/output/inout 方向
      - wire/reg 类型
      - [MSB:LSB] 位宽（含小端序和参数化位宽）
      - 多模块设计

    Args:
        content: 原始 RTL 源代码。

    Returns:
        dict: {module_name: [{name, direction, type, width}, ...]}
    """
    content_clean = strip_rtl_comments(content)

    def _parse_width(msb_str: Optional[str], lsb_str: Optional[str]) -> int:
        """解析位宽，支持小端序 [0:7] 和参数化 [WIDTH-1:0]。"""
        if not msb_str or not lsb_str:
            return 1
        try:
            msb = int(msb_str)
            lsb = int(lsb_str)
            return abs(msb - lsb) + 1
        except ValueError:
            pass
        # 参数化位宽
        for pat in [r'(\w+)-1:\s*0', r'(\w+)-1\s*:\s*0']:
            m = re.match(pat, f"{msb_str}:{lsb_str}")
            if m:
                return 1
        return 1

    result: Dict[str, List[Dict]] = {}
    module_pattern = re.compile(r'module\s+(\w+)\s*(?:#\s*\(.*?\))?\s*\(', re.DOTALL)

    for match in module_pattern.finditer(content_clean):
        mod_name = match.group(1)
        start = match.end()
        depth = 1
        end = start
        while depth > 0 and end < len(content_clean):
            c = content_clean[end]
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            end += 1
        port_section = content_clean[start:end - 1]

        ports: List[Dict] = []
        port_pattern = re.compile(
            r'(input|output|inout)\s+'
            r'(?:wire|reg|logic|signed|unsigned)?\s*'
            r'(?:\[(\d+):(\d+)\])?\s*'
            r'(\w+)(?:\s*,\s*|\s*;|$)',
            re.IGNORECASE
        )

        for pm in port_pattern.finditer(port_section):
            direction = pm.group(1).lower()
            ptype = "reg" if "reg" in port_section[max(0, pm.start()-20):pm.start()].lower() else "wire"
            msb, lsb = pm.group(2), pm.group(3)
            width = _parse_width(msb, lsb)
            ports.append({
                "name": pm.group(4),
                "direction": direction,
                "type": ptype,
                "width": width,
            })

        result[mod_name] = ports

    return result


def extract_signals(content: str) -> Dict[str, int]:
    """从 RTL 内容中提取所有声明信号（wire/reg/input/output/inout）。

    Args:
        content: 原始 RTL 源代码。

    Returns:
        dict: {signal_name: line_number}
    """
    from collections import defaultdict
    signals: Dict[str, int] = {}
    content_clean = strip_rtl_comments(content)
    lines = content.split('\n')

    # 信号声明模式
    decl_patterns = [
        (r'(wire|reg)\s+(?:\[.*?\])?\s*(\w+)\s*[;,]', None),
        (r'(input|output|inout)\s+(?:wire|reg)?\s*(?:\[.*?\])?\s*(\w+)\s*[;,]', None),
        (r'(input|output|inout)\s+(\w+)\s*[;,]', None),
    ]

    for i, line in enumerate(lines):
        line_stripped = line.split('//')[0]
        for pattern, _ in decl_patterns:
            for m in re.finditer(pattern, line_stripped):
                sig_name = m.group(2)
                if sig_name and sig_name not in ('wire', 'reg', 'input', 'output', 'inout'):
                    signals[sig_name] = i + 1

    return signals
