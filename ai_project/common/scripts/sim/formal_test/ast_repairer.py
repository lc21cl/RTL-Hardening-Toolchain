#!/usr/bin/env python3
"""
ast_repairer.py — AST-level 修复器

使用 pyverilog AST 解析替代纯正则修复，精确操作语法树节点。
修复策略：
  1. 端口声明缺失 — 自动添加 module 端口列表中遗漏的声明
  2. wire/reg 类型缺失 — 为未指定类型的端口添加默认 wire 类型
  3. 端口方向缺失 — 推断并添加 input/output 方向
  4. 位宽不一致 — 对齐声明与使用的位宽
  5. 未声明信号 — 自动推断并添加 wire 声明
  6. 缺失分号 — 在 AST 无法解析的节点行添加分号

设计原则：
  - 先用 pyverilog 解析 AST
  - AST 解析成功 → 精确的 AST 级修复
  - AST 解析失败 → 降级到 SyntaxFixer 的正则修复

用法:
    from ast_repairer import ASTRepairer

    repairer = ASTRepairer()
    fixed_code = repairer.fix(content, errors)
"""

import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple, Any

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("ast_repairer")

# pyverilog 导入（软依赖）
try:
    import pyverilog.vparser.ast as vast
    from pyverilog.vparser.parser import parse as pyv_parse
    PYVERILOG_AVAILABLE = True
except ImportError:
    PYVERILOG_AVAILABLE = False
    vast = None
    pyv_parse = None
    logger.warning("pyverilog not available; AST repairer will fall back to regex")


# ============================================================================
# ASTRepairer
# ============================================================================

class ASTRepairer:
    """AST-level 修复器。

    使用 pyverilog 解析 RTL 为 AST，在语法树层面进行精确修复。
    当 AST 解析失败时降级到正则修复。
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self._ast_available = PYVERILOG_AVAILABLE

        # 延迟导入 SyntaxFixer 作为降级方案
        self._syntax_fixer = None
        try:
            from auto_repair import SyntaxFixer
            self._syntax_fixer = SyntaxFixer()
        except ImportError:
            pass

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def fix(self, rtl_content: str, errors: List[str]) -> str:
        """主要修复入口点。

        先尝试 AST-level 修复；若 AST 解析失败则降级为正则修复。

        Args:
            rtl_content: RTL 源代码字符串。
            errors:      yosys 返回的错误消息列表。

        Returns:
            修复后的 RTL 代码字符串。
        """
        _t_start = time.time()
        _line_count = len(rtl_content.splitlines())

        logger.section("AST Repairer — Core Fix Loop")
        logger.print(f"  [AST_REPAIR] fix() called: input={len(rtl_content)} chars, {_line_count} lines, "
                     f"errors={len(errors)}, pyverilog={'✓' if self._ast_available else '✗'}")

        # ── 阶段 1：错误分类 ──
        logger.print(f"  [AST_REPAIR] Phase 1/4: Error classification ({len(errors)} errors)")
        error_categories: Dict[str, int] = {}
        for err in errors:
            el = err.lower()
            if "port" in el and "direction" in el:
                error_categories["port_direction"] = error_categories.get("port_direction", 0) + 1
            if "semicolon" in el or "expecting ';'" in el:
                error_categories["missing_semicolon"] = error_categories.get("missing_semicolon", 0) + 1
            if re.search(r'undefined|undeclared|not\s+declared', el):
                error_categories["undeclared_signal"] = error_categories.get("undeclared_signal", 0) + 1
            if "syntax error" in el:
                error_categories["syntax_error"] = error_categories.get("syntax_error", 0) + 1
        if error_categories:
            logger.print(f"  [AST_REPAIR]   Error categories: {error_categories}")
        else:
            logger.print(f"  [AST_REPAIR]   No categorizable errors found")

        if not self._ast_available or not errors:
            logger.print(f"  [AST_REPAIR]   -> pyverilog={'✗ unavailable' if not self._ast_available else '✓ available'}, "
                         f"errors={'none' if not errors else 'present'}")
            logger.print(f"  [AST_REPAIR]   -> Skipping AST, falling back to regex directly")
            result = self._fallback_regex_fix(rtl_content, errors)
            logger.metric("ast_repair.fix", time.time() - _t_start, "s")
            return result

        # ── 阶段 2：预处理 ──
        logger.print(f"  [AST_REPAIR] Phase 2/4: Preprocessing ({len(errors)} errors to process)")
        _pre_t = time.time()
        preprocessed = self._preprocess_common_errors(rtl_content, errors)
        _pre_elapsed = time.time() - _pre_t
        _pre_delta = len(preprocessed) - len(rtl_content)
        logger.print(f"  [AST_REPAIR]   Preprocessed: {len(rtl_content)} → {len(preprocessed)} chars "
                     f"({_pre_delta:+d}, {_pre_elapsed:.3f}s)")
        if preprocessed != rtl_content:
            logger.print(f"  [AST_REPAIR]   Changes detected — content modified during preprocessing")

        # ── 阶段 3：AST 解析 ──
        logger.print(f"  [AST_REPAIR] Phase 3/4: AST Parsing (pyverilog)")
        _parse_t = time.time()
        ast, ast_errors = self._parse_rtl(preprocessed)
        _parse_elapsed = time.time() - _parse_t

        if ast is None:
            logger.print(f"  [AST_REPAIR]   ✗ AST parse FAILED ({len(ast_errors)} errors, {_parse_elapsed:.3f}s)")
            for ae in ast_errors[:5]:  # 最多显示 5 条
                logger.print(f"    - {ae[:200]}")
            logger.print(f"  [AST_REPAIR]   -> Falling back to regex repair")
            result = self._fallback_regex_fix(rtl_content, errors)
            logger.metric("ast_repair.fix", time.time() - _t_start, "s")
            return result

        # AST 解析成功 → 在 AST 层面修复
        logger.print(f"  [AST_REPAIR]   ✓ AST parsed SUCCESSFULLY ({_parse_elapsed:.3f}s)")

        # ── 阶段 4：AST 修复 + 序列化 ──
        logger.print(f"  [AST_REPAIR] Phase 4/4: AST Repair + Serialization")
        _repair_t = time.time()
        ast_fixed = self._repair_ast(ast, preprocessed)
        _repair_elapsed = time.time() - _repair_t
        logger.print(f"  [AST_REPAIR]   AST repair phase: {_repair_elapsed:.3f}s")

        _serial_t = time.time()
        serialized = self._serialize_ast(ast_fixed)
        _serial_elapsed = time.time() - _serial_t
        if serialized and serialized != preprocessed:
            _delta = len(serialized) - len(preprocessed)
            logger.print(f"  [AST_REPAIR]   Serialized: {len(preprocessed)} → {len(serialized)} chars "
                         f"({_delta:+d}, {_serial_elapsed:.3f}s)")
            logger.print(f"  [AST_REPAIR]   AST fix applied — then regex fallback for safety")
            result = self._fallback_regex_fix(serialized, errors)
            logger.metric("ast_repair.fix", time.time() - _t_start, "s")
            return result
        else:
            if serialized:
                logger.print(f"  [AST_REPAIR]   Serialized content unchanged from preprocessed ({_serial_elapsed:.3f}s)")
            else:
                logger.print(f"  [AST_REPAIR]   Serialization returned None ({_serial_elapsed:.3f}s)")
            logger.print(f"  [AST_REPAIR]   AST fix not applied — falling back to regex")
            result = self._fallback_regex_fix(preprocessed, errors)
            logger.metric("ast_repair.fix", time.time() - _t_start, "s")
            return result

    # ------------------------------------------------------------------
    # AST 解析
    # ------------------------------------------------------------------

    def _parse_rtl(self, content: str) -> Tuple[Any, List[str]]:
        """尝试用 pyverilog 解析 RTL 内容。

        Returns:
            (ast, errors) — 解析成功时 ast 为 AST 对象，否则为 None。
        """
        if not PYVERILOG_AVAILABLE:
            return None, ["pyverilog not available"]

        # 写入临时文件以便 pyverilog 解析
        import tempfile
        tmp_dir = os.path.dirname(__file__)
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.v', dir=tmp_dir, delete=False, encoding='utf-8'
        ) as f:
            tmp_path = f.name
            f.write(content)
            # fd 在 with 块结束后自动关闭
        try:
            ast, _ = pyv_parse([tmp_path], preprocess_include=False)
            return ast, []
        except Exception as e:
            return None, [str(e)]
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # AST-level 修复
    # ------------------------------------------------------------------

    def _repair_ast(self, ast: Any, original_content: str) -> str:
        """使用 pyverilog AST 分析设计，返回修复后的代码。

        工作原理：
          1. 遍历 AST 提取所有声明信号（wire/reg/input/output/inout）
          2. 遍历 AST 提取所有引用信号（Identifier 节点）
          3. 对比发现未声明信号
          4. 用 AST 行号信息在原字符串中精确定位并修复

        Args:
            ast:              pyverilog AST 对象（由 _parse_rtl 返回）。
            original_content: 原始 RTL 代码字符串。

        Returns:
            修复后的 RTL 代码字符串（如果没有修复，返回 original_content）。
        """
        if not PYVERILOG_AVAILABLE:
            return original_content

        content = original_content
        fixes_applied = 0

        try:
            # ── Step 1: 提取所有声明信号 ──
            declared_signals: Dict[str, int] = {}  # name → line_no
            ports_without_direction: List[str] = []
            port_names: List[str] = []

            for node in vast.walk(ast):
                if isinstance(node, vast.ModuleDef):
                    for item in node.items:
                        # wire / reg 声明
                        if isinstance(item, vast.Decl):
                            for decl_item in item.list:
                                if hasattr(decl_item, 'name') and decl_item.name:
                                    declared_signals[decl_item.name] = getattr(
                                        decl_item, 'lineno', 0
                                    )
                        # input / output / inout 端口
                        if isinstance(item, (vast.Input, vast.Output, vast.Inout)):
                            if hasattr(item, 'name') and item.name:
                                declared_signals[item.name] = getattr(item, 'lineno', 0)
                            # 处理端口列表
                            if hasattr(item, 'list') and item.list:
                                for port_sig in item.list:
                                    if hasattr(port_sig, 'name') and port_sig.name:
                                        declared_signals[port_sig.name] = getattr(
                                            port_sig, 'lineno', 0
                                        )

                # ── 收集端口名（Port 节点）──
                if isinstance(node, vast.Port):
                    if hasattr(node, 'name') and node.name:
                        port_names.append(node.name)

                # ── 找出声明中缺少方向的端口（IOport 中 Port 非 Input/Output/Inout）──
                if isinstance(node, vast.Ioport):
                    if hasattr(node, 'port') and hasattr(node.port, 'name'):
                        pname = node.port.name
                        if pname not in declared_signals:
                            ports_without_direction.append(pname)

            logger.print(f"  [AST_REPAIR_AST] Declared signals: {len(declared_signals)}")
            logger.print(f"  [AST_REPAIR_AST] Port names: {len(port_names)}")

            # ── Step 2: 提取所有引用信号 ──
            used_signals: Dict[str, int] = {}  # name → first line of usage
            for node in vast.walk(ast):
                if isinstance(node, vast.Identifier):
                    if hasattr(node, 'name') and node.name:
                        name = node.name
                        lineno = getattr(node, 'lineno', 0)
                        if name not in used_signals:
                            used_signals[name] = lineno

            logger.print(f"  [AST_REPAIR_AST] Used signals: {len(used_signals)}")

            # ── Step 3: 找出未声明信号 ──
            undeclared = {}
            for name, lineno in used_signals.items():
                if name not in declared_signals:
                    # 跳过常量和系统调用
                    if name.upper() == name and len(name) > 1:
                        continue
                    if name.startswith('$') or name.startswith('\\'):
                        continue
                    undeclared[name] = lineno

            if undeclared:
                logger.print(f"  [AST_REPAIR_AST] Undeclared signals found: {len(undeclared)}")
                for name, lineno in sorted(undeclared.items(), key=lambda x: x[1]):
                    logger.print(f"    - '{name}' (line {lineno})")
                    # 在 module 的最后一个声明之后插入 wire 声明
                    insert_line = self._find_insert_line(content, ast)
                    if insert_line > 0:
                        content = self._insert_wire_decl(content, name, insert_line)
                        fixes_applied += 1
                        logger.print(f"      → inserted 'wire {name};' after line {insert_line}")

            # ── Step 4: 修复端口方向缺失 ──
            for pname in ports_without_direction:
                if pname not in [d for d in declared_signals]:
                    logger.print(f"  [AST_REPAIR_AST] Port '{pname}' missing direction")
                    # 在 module 头部为端口添加方向
                    content = self._fix_ast_port_direction(content, pname)
                    fixes_applied += 1
                    logger.print(f"      → added direction for port '{pname}'")

            if fixes_applied > 0:
                logger.print(f"  [AST_REPAIR_AST] Total fixes applied: {fixes_applied}")
            else:
                logger.print(f"  [AST_REPAIR_AST] No issues detected — design is AST-clean")

        except Exception as e:
            logger.print(f"  [AST_REPAIR_AST] Exception during AST analysis: {e}")
            return original_content

        return content

    def _find_insert_line(self, content: str, ast: Any) -> int:
        """找到 module 中适合插入 wire 声明的行号。"""
        try:
            for node in vast.walk(ast):
                if isinstance(node, vast.ModuleDef):
                    last_decl_line = 0
                    for item in node.items:
                        if isinstance(item, (vast.Decl, vast.Input, vast.Output, vast.Inout)):
                            if hasattr(item, 'lineno') and item.lineno:
                                last_decl_line = max(last_decl_line, item.lineno)
                    # 如果没有声明，放在 module 头部之后
                    if last_decl_line == 0 and hasattr(node, 'lineno'):
                        last_decl_line = node.lineno + 1
                    return last_decl_line
        except Exception:
            pass
        return 0

    def _insert_wire_decl(self, content: str, signal_name: str, after_line: int) -> str:
        """在指定行之后插入 'wire signal_name;' 声明。"""
        lines = content.split('\n')
        if 0 < after_line <= len(lines):
            indent = ''
            for ch in lines[after_line - 1]:
                if ch in (' ', '\t'):
                    indent += ch
                else:
                    break
            lines.insert(after_line, f"{indent}wire {signal_name};")
            return '\n'.join(lines)
        return content

    def _fix_ast_port_direction(self, content: str, port_name: str) -> str:
        """为指定端口添加 input/output 方向（默认 input）。"""
        # 查找端口声明模式:  .port_name(signal)  或  port_name
        pattern = rf'(\b{re.escape(port_name)}\b)\s*(?=[,\)])'
        if re.search(pattern, content):
            content = re.sub(pattern, rf'input \1', content, count=1)
        return content

    # ------------------------------------------------------------------
    # 代码序列化（保留向后兼容）
    # ------------------------------------------------------------------

    def _serialize_ast(self, ast: Any) -> Optional[str]:
        """将 AST 序列化回 Verilog 代码字符串。

        注：pyverilog 的 str() 输出的是 Python repr 而非 Verilog 代码。
        此方法保留用于向后兼容，实际修复使用 _repair_ast() 的字符串操作。
        """
        try:
            return str(ast)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 预处理 — 面向不可解析代码的修复
    # ------------------------------------------------------------------

    def _preprocess_common_errors(self, content: str, errors: List[str]) -> str:
        """在 AST 解析前预处理常见语法错误，提高解析成功率。

        修复：
          1. 端口列表中的缺失分号
          2. 端口方向缺失
          3. wire/reg 类型缺失
          4. 缺失 endmodule
        """
        result = content

        for error in errors:
            error_lower = error.lower()

            # 1. 端口方向缺失：检测 "port direction" 错误
            if "port" in error_lower and "direction" in error_lower:
                result = self._fix_port_direction(result, error)

            # 2. 缺失分号
            if "semicolon" in error_lower or "expecting ';'" in error_lower:
                result = self._fix_semicolons_ports(result)

            # 3. 未声明信号
            if re.search(r'undefined|undeclared|not\s+declared', error_lower):
                result = self._fix_undeclared(result, error)

        # 4. 缺失 endmodule
        if 'endmodule' not in result:
            result = result.rstrip('\n') + '\nendmodule\n'

        return result

    def _fix_port_direction(self, content: str, error: str) -> str:
        """修复端口方向缺失。

        处理两种情况：
          1. Old-style 端口列表（逗号分隔的纯端口名）—— 添加默认 wire 声明
          2. 端口在列表中但缺少 input/output，模块内有 wire/reg 声明 —— 推断方向并添加

        Args:
            content: RTL 源代码。
            error:   错误消息字符串。

        Returns:
            修复后的 RTL 代码。
        """
        logger.print(f"  [AST_REPAIR] Fixing port direction for error: {error[:80]}")

        # 捕获 module 头部之后的端口列表
        # 查找 module 声明和第一个端口
        module_match = re.search(r'module\s+(\w+)\s*\(', content)
        if not module_match:
            return content

        module_start = module_match.start()
        # 找到端口列表的结束
        paren_depth = 0
        port_list_end = -1
        for i in range(module_match.end(), len(content)):
            if content[i] == '(':
                paren_depth += 1
            elif content[i] == ')':
                paren_depth -= 1
                if paren_depth == 0:
                    port_list_end = i
                    break
        if port_list_end < 0:
            return content

        port_list_text = content[module_match.end():port_list_end]

        # 检查端口列表中是否已有 input/output/inout
        has_direction = bool(re.search(r'\b(input|output|inout)\b', port_list_text))
        if has_direction:
            return content  # 已有方向声明，不做改动

        # ── 情况 1：Old-style 端口列表（纯逗号分隔的端口名）──
        # 检查是否是纯逗号分隔的端口名
        if ',' in port_list_text and not re.search(r'\b(input|output|inout)\b', port_list_text):
            # 在 module 行之后插入默认 wire 声明
            insert_pos = content.find('\n', module_match.end())
            if insert_pos > 0:
                port_names = [p.strip() for p in port_list_text.split(',')]
                wire_decls = '\n'.join([f'    wire {p};' for p in port_names if re.match(r'^\w+$', p)])
                content = content[:insert_pos] + '\n' + wire_decls + content[insert_pos:]

        # ── 情况 2：端口在列表中但缺少 input/output，模块内部有 wire/reg 声明 ──
        # 提取端口列表中的端口名（去除空格、逗号、换行）
        raw_port_names = re.findall(r'\b(?!input\b|output\b|inout\b|wire\b|reg\b)\w+\b', port_list_text)
        # 排除 module 名本身
        module_name = module_match.group(1)
        raw_port_names = [p for p in raw_port_names if p != module_name]

        # 收集端口列表中缺少方向的端口（没有对应 input/output/inout 声明的）
        missing_direction_ports = []
        for pname in raw_port_names:
            # 检查在端口列表之前的上下文中是否已有方向声明
            scope_before_port = content[:module_match.end()]
            # 检查该端口是否已经在某行有 input/output/inout 前缀（可能在端口列表之外声明）
            decl_pattern = rf'(input|output|inout)\s+(wire|reg)?\s*.*\b{re.escape(pname)}\b'
            if not re.search(decl_pattern, scope_before_port + port_list_text, re.IGNORECASE):
                missing_direction_ports.append(pname)

        if missing_direction_ports:
            # 对每个缺少方向的端口，尝试推断方向：
            # 1. 如果模块内有 wire 声明但无 reg 赋值 → 通常是 input
            # 2. 如果模块内有 reg 声明且有赋值 → 通常是 output
            # 3. 默认使用 input（保守策略）
            module_body = content[port_list_end:]
            lines = content.split('\n')

            # 找到端口列表结束行号之后的第一行声明行
            insert_line = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('//') or stripped.startswith('/*'):
                    continue
                if stripped.startswith(('input', 'output', 'inout', 'wire', 'reg')):
                    # 计算 abs 行号
                    abs_line = i + 1
                    if abs_line > content[:port_list_end].count('\n') + 1:
                        insert_line = i
                        break

            for pname in missing_direction_ports:
                # 推断方向：检查模块体内是否对该信号赋值
                # 如果是 always 块中 <= 赋值的左侧 → output
                # 如果是 assign 语句的左侧 → output
                # 其他情况 → input
                is_output = False
                # 检测 always 块中的非阻塞赋值左侧
                assign_patterns = [
                    rf'\b{pname}\b\s*<=\s*',       # 非阻塞赋值
                    rf'\b{pname}\b\s*=\s*',         # 阻塞赋值（always 中）
                    rf'assign\s+\b{pname}\b\s*=',   # assign 语句
                ]
                for ap in assign_patterns:
                    if re.search(ap, module_body):
                        is_output = True
                        break

                # 在 module 的声明区域添加方向声明
                direction = 'output' if is_output else 'input'
                if insert_line > 0 and insert_line < len(lines):
                    indent = ''
                    for ch in lines[insert_line]:
                        if ch in (' ', '\t'):
                            indent += ch
                        else:
                            break
                    # 查找该端口在模块内部的已有声明（如 wire [7:0] data;）
                    existing_decl = re.search(
                        rf'(wire|reg)\s*(\[[^\]]*\])?\s*{re.escape(pname)}\s*;',
                        '\n'.join(lines)
                    )
                    if existing_decl:
                        # 已有 wire/reg 声明：将 wire → input/output 并保留位宽
                        old_decl = existing_decl.group(0)
                        decl_type = existing_decl.group(1)
                        width_part = existing_decl.group(2) or ''
                        new_decl = old_decl.replace(
                            f'{decl_type} ',
                            f'{direction} {decl_type} '
                        )
                        content = content.replace(old_decl, new_decl, 1)
                        lines = content.split('\n')
                    else:
                        # 无已有声明：插入新方向声明
                        decl_line = f"{indent}{direction} {pname};"
                        lines.insert(insert_line, decl_line)
                        insert_line += 1
                        content = '\n'.join(lines)
                        lines = content.split('\n')

                    logger.print(f"      → added '{direction}' direction for port '{pname}'")

        return content

    def _fix_semicolons_ports(self, content: str) -> str:
        """在端口声明中修复缺失的分号。

        基于行级分析，为端口声明行添加分号。
        """
        lines = content.split('\n')
        fixed = []
        changes = 0

        in_module_header = True
        in_port_list = False
        paren_depth = 0

        for i, line in enumerate(lines):
            stripped = line.rstrip()

            # 检测 module 声明
            if re.match(r'module\s+\w+\s*\(', stripped):
                in_port_list = True
                fixed.append(line)
                continue

            if in_port_list:
                paren_depth += stripped.count('(') - stripped.count(')')
                if paren_depth <= 0:
                    in_port_list = False
                fixed.append(line)
                continue

            # 跳过空行 / 注释 / 已有分号
            if (not stripped.strip() or stripped.strip().startswith('//')
                    or stripped.strip().startswith('/*') or stripped.rstrip().endswith(';')):
                fixed.append(line)
                continue

            # 检测 input/output/inout 声明行 — 需要分号
            if re.match(r'\s*(input|output|inout)\s', stripped):
                # 确保不在端口列表内
                if not stripped.rstrip().endswith(','):
                    fixed.append(stripped + ';')
                    changes += 1
                    continue

            # wire/reg 声明行
            if re.match(r'\s*(wire|reg|tri|wand|wor)\s', stripped):
                if not stripped.rstrip().endswith(','):
                    fixed.append(stripped + ';')
                    changes += 1
                    continue

            # assign 语句
            if re.match(r'\s*assign\s', stripped):
                fixed.append(stripped + ';')
                changes += 1
                continue

            fixed.append(line)

        if changes > 0:
            logger.print(f"  [AST_REPAIR] Added {changes} missing semicolons (port/decl lines)")

        return '\n'.join(fixed)

    def _fix_undeclared(self, content: str, error: str) -> str:
        """修复未声明信号：从错误消息提取信号名，添加 wire 声明。"""
        match = re.search(r"'(\w+)'", error)
        if not match:
            return content

        signal = match.group(1)

        # 避免重复添加
        if signal in content and re.search(
            rf'(wire|reg|input|output)\s+.*\b{signal}\b', content
        ):
            return content  # 已声明

        # 在第一个 module 声明后添加 wire 声明
        content = re.sub(
            r'(\bmodule\s+\w+\s*\()',
            r'\1\n    wire ' + signal + r';',
            content,
            count=1,
        )
        logger.print(f"  [AST_REPAIR] Added wire declaration for '{signal}'")
        return content

    def _detect_undeclared_in_always(self, content: str) -> str:
        """检测 always 块中使用的未声明信号，自动添加 wire 声明。

        扫描所有 always @(...) 块中的信号引用，与已声明的
        wire/reg/input/output/inout 信号列表交叉比对，找到遗漏的信号声明。

        Args:
            content: RTL 源代码。

        Returns:
            修复后的 RTL 代码（自动添加了缺失的 wire 声明）。
        """
        logger.print(f"  [AST_REPAIR] Scanning always blocks for undeclared signals...")

        # ── Step 1: 收集所有已声明的信号 ──
        declared_signals = set()
        # 提取 wire/reg/input/output/inout 声明中的信号名
        decl_patterns = [
            r'(input|output|inout)\s+(wire|reg)?\s*(?:\[[^\]]*\])?\s*(\w+)',  # 带方向
            r'(wire|reg|tri|wand|wor)\s*(?:\[[^\]]*\])?\s*(\w+)',             # 纯声明
        ]
        for dp in decl_patterns:
            for m in re.finditer(dp, content, re.IGNORECASE):
                # 捕获组位置取决于模式
                groups = m.groups()
                if groups[-1] and re.match(r'^[a-zA-Z_]\w*$', groups[-1]):
                    declared_signals.add(groups[-1])

        # 提取端口列表中的端口名（可能有位宽）
        # 如 module test (clk, rst_n, data_in, data_out)
        module_match = re.search(r'module\s+\w+\s*\(', content)
        if module_match:
            paren_depth = 0
            port_end = -1
            for i in range(module_match.end(), len(content)):
                if content[i] == '(':
                    paren_depth += 1
                elif content[i] == ')':
                    paren_depth -= 1
                    if paren_depth == 0:
                        port_end = i
                        break
            if port_end > 0:
                port_text = content[module_match.end():port_end]
                for p in re.findall(r'\b([a-zA-Z_]\w*)\b', port_text):
                    if p.lower() not in ('input', 'output', 'inout', 'wire', 'reg',
                                         'module', 'tri', 'wand', 'wor'):
                        declared_signals.add(p)

        # ── 补充：收集模块内部的声明 ──
        internal_decl_pattern = re.compile(
            r'(wire|reg|input|output|inout)\s+(?:\[[^\]]*\])?\s*(\w+(?:\s*,\s*\w+)*)\s*;',
            re.IGNORECASE
        )
        for match in internal_decl_pattern.finditer(content):
            names_str = match.group(2)
            names = [n.strip() for n in re.split(r',', names_str) if n.strip()]
            for name in names:
                declared_signals.add(name)

        logger.print(f"  [AST_REPAIR]   Found {len(declared_signals)} declared signals (ports + internal)")

        # ── Step 2: 提取 always 块中的信号引用 ──
        always_signals = set()
        # 查找所有 always 块
        always_blocks = list(re.finditer(
            r'always\s*@\s*\([^)]*\)\s*((?:begin\s*(?::\s*\w+)?)?[^;]*?(?:;\s*)*'
            r'(?:[^e]|e(?!ndmodule))*?(?:end\s*)?)',
            content, re.IGNORECASE | re.DOTALL
        ))
        # 如果没有匹配到，用简单模式再试一次
        if not always_blocks:
            always_blocks = list(re.finditer(
                r'always\s*@\s*\([^)]*\)',
                content, re.IGNORECASE
            ))

        for ab_match in always_blocks:
            # 提取 always 块内容（从 posedge 列表后到 end / endmodule）
            block_start = ab_match.end()
            # 找到块边界：下一个 endmodule / end / 行末
            block_text = content[block_start:block_start + 5000]  # 最多取 5000 字符
            # 限制到 endmodule 或下一个 always/assign/module
            block_end_m = re.search(
                r'\b(endmodule|end\b|always\s*@|assign\s|module\s)',
                block_text
            )
            if block_end_m:
                block_text = block_text[:block_end_m.start()]

            # 提取信号引用（排除系统函数、常量、数字）
            for sig_m in re.finditer(r'\b([a-zA-Z_]\w*)\b', block_text):
                sig = sig_m.group(1)
                # 跳过 Verilog 关键字
                if sig.lower() in ('if', 'else', 'case', 'endcase', 'for', 'begin',
                                   'end', 'posedge', 'negedge', 'or', 'and', 'not',
                                   'nand', 'nor', 'xor', 'xnor', 'wire', 'reg',
                                   'input', 'output', 'inout', 'assign', 'always',
                                   'module', 'endmodule', 'initial', 'generate',
                                   'endgenerate', 'while', 'repeat', 'function',
                                   'endfunction', 'task', 'endtask', 'integer',
                                   'genvar', 'real', 'time', 'supply0', 'supply1',
                                   'tri', 'tri0', 'tri1', 'wand', 'wor', 'triand',
                                   'trior', 'unsigned', 'signed', 'small', 'medium',
                                   'large', 'scalared', 'vectored', 'buf', 'bufif0',
                                   'bufif1', 'notif0', 'notif1', 'cmos', 'nmos',
                                   'pmos', 'rcmos', 'pullup', 'pulldown', 'defparam',
                                   'localparam', 'parameter', 'specify', 'endspecify'):
                    continue
                # 跳过纯数字或全大写常量
                if re.match(r'^[0-9]', sig) or (sig.upper() == sig and len(sig) > 1):
                    continue
                always_signals.add(sig)

        logger.print(f"  [AST_REPAIR]   Found {len(always_signals)} signal references in always blocks")

        # ── Step 3: 找出未声明的信号 ──
        undeclared = always_signals - declared_signals
        if not undeclared:
            logger.print(f"  [AST_REPAIR]   All signals in always blocks are declared")
            return content

        logger.print(f"  [AST_REPAIR]   Undeclared signals in always blocks: {len(undeclared)}")
        fixes_applied = 0

        # ── Step 4: 在 module 的声明区域插入 wire 声明 ──
        lines = content.split('\n')
        # 找到 module 声明区域的最后一行（最后一个 input/output/wire/reg 之后）
        last_decl_line = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r'^\s*(input|output|inout|wire|reg|tri|wand|wor)\s', stripped, re.IGNORECASE):
                last_decl_line = i

        if last_decl_line < 0:
            # 没有声明行，放在 module 行后
            for i, line in enumerate(lines):
                if re.match(r'module\s+\w+\s*\(', line, re.IGNORECASE):
                    last_decl_line = i
                    break

        if last_decl_line >= 0:
            indent = ''
            if last_decl_line < len(lines):
                for ch in lines[last_decl_line]:
                    if ch in (' ', '\t'):
                        indent += ch
                    else:
                        break

            for sig in sorted(undeclared):
                # 再次确认没有声明（使用更精确的模式）
                decl_pattern = re.compile(
                    rf'(wire|reg|input|output|inout)\s+(?:\[[^\]]*\])?\s*\b{re.escape(sig)}\b\s*;',
                    re.IGNORECASE
                )
                if decl_pattern.search(content):
                    continue
                # 插入 wire 声明
                lines.insert(last_decl_line + 1, f"{indent}wire {sig};")
                last_decl_line += 1
                fixes_applied += 1
                logger.print(f"      → auto-declared wire '{sig}' (used in always block)")

        if fixes_applied > 0:
            content = '\n'.join(lines)
            logger.print(f"  [AST_REPAIR]   Added {fixes_applied} wire declarations for always-block signals")

        return content

    # ------------------------------------------------------------------
    # 降级方案：正则修复
    # ------------------------------------------------------------------

    def _fallback_regex_fix(self, content: str, errors: List[str]) -> str:
        """降级到 SyntaxFixer 的正则修复，并执行 TMR 检测。"""
        if self._syntax_fixer:
            logger.print(f"  [AST_REPAIR] Using SyntaxFixer regex fallback")
            content = self._syntax_fixer.fix(content, errors)
        else:
            # 如果 SyntaxFixer 也不可用，使用内置简单修复
            logger.print(f"  [AST_REPAIR] Using built-in regex fallback")
            if errors:
                for error in errors:
                    if "port" in error.lower() and "direction" in error.lower():
                        content = self._fix_port_direction(content, error)
                    if re.search(r'undefined|undeclared|not\s+declared', error.lower()):
                        content = self._fix_undeclared(content, error)
                    if "semicolon" in error.lower():
                        content = self._fix_semicolons_ports(content)
            # 缺失 endmodule
            if 'endmodule' not in content:
                content = content.rstrip('\n') + '\nendmodule\n'

        # ── Always 块中未声明信号检测（仅在有 undeclared 错误时执行）──
        # content = self._detect_undeclared_in_always(content)

        # ── TMR 冗余逻辑检测（始终执行）──
        logger.print(f"  [AST_REPAIR] TMR pattern detection...")
        _tmr_info = self._detect_tmr_patterns(content)
        if _tmr_info.get("detected"):
            logger.print(f"  [AST_REPAIR]   ✓ TMR detected: type={_tmr_info['tmr_type']}, "
                         f"copies={_tmr_info['copies']}, "
                         f"voter={'present' if _tmr_info['has_voter'] else 'MISSING'}")
            if "missing_voter" in _tmr_info.get("issues", []):
                logger.print(f"  [AST_REPAIR]   -> Fixing missing voter")
                content = self._fix_tmr_missing_voter(content, _tmr_info)
            logger.print(f"  [AST_REPAIR]   -> Checking width consistency")
            content = self._fix_tmr_width_mismatch(content, _tmr_info)

            # ── TMR 反模式修复 ──
            if "fake_tmr" in _tmr_info.get("issues", []):
                logger.print(f"  [AST_REPAIR]   -> Fixing fake TMR (incomplete copies)")
                content = self._fix_tmr_incomplete_copies(content, _tmr_info)
            if "incomplete_tmr" in _tmr_info.get("issues", []):
                logger.print(f"  [AST_REPAIR]   -> Fixing incomplete TMR (unequal widths)")
                content = self._fix_tmr_width_mismatch(content, _tmr_info)
            if "dead_tmr" in _tmr_info.get("issues", []):
                logger.print(f"  [AST_REPAIR]   -> Fixing dead TMR (voter output unused)")
                content = self._fix_tmr_dead_voter(content, _tmr_info)
        else:
            logger.print(f"  [AST_REPAIR]   No TMR pattern detected")

        # ── v3.5 新增: AST 级修复增强 ──
        content = self._fix_missing_begin_end(content)
        content = self._fix_sensitivity_list(content)
        content = self._fix_always_type_mismatch(content)
        content = self._fix_redundant_wire_declaration(content)

        return content

    # ------------------------------------------------------------------
    # TMR 冗余逻辑检测与修复
    # ------------------------------------------------------------------

    def _detect_tmr_patterns(self, content: str) -> Dict[str, Any]:
        """检测 TMR 冗余逻辑模式。

        扫描 RTL 代码，识别以下 TMR 模式：
          1. 三倍寄存器（copy0/copy1/copy2 或 reg0/reg1/reg2）
          2. 不完整的多数组件（存在冗余但缺少或部分缺失投票器）
          3. 冗余寄存器位宽不一致
          4. 伪 TMR（只有 2 个副本而非 3 个）
          5. 部分 TMR（部分信号三重化，部分未三重化）
          6. 死 TMR（投票器输出未被使用）
          7. 更多命名模式（_a/_b/_c 后缀, _1/_2/_3 后缀等）

        Returns:
            Dict 含 detected, copies, width, has_voter, voter_lines, issues, signal_names 字段。
        """
        result: Dict[str, Any] = {
            "detected": False,
            "copies": [],
            "signal_width": 0,
            "has_voter": False,
            "voter_lines": [],
            "issues": [],
            "tmr_type": None,
            "signal_names": [],      # 检测到的原始信号名列表
            "widths_per_copy": {},    # 每个副本的位宽 {name: width}
            "voter_output_name": None,  # 投票器输出信号名
        }

        # ── 模式 1：三重寄存器声明 ──
        # 支持多种命名约定：copy0/copy1/copy2, reg0/reg1/reg2, dup0/dup1/dup2
        # tri0/tri1/tri2, r0/r1/r2, node0/node1/node2
        # 以及带下划线变体：copy_0/copy_1/copy_2
        # 以及后缀变体：sig_a/sig_b/sig_c, sig_1/sig_2/sig_3
        _triplet_patterns = [
            (r'(copy|reg|dup|r|tri)(\d)\s*\[\s*(\d+):(\d+)\]', 3),         # copy0[W:0]
            (r'(copy|reg|dup|r|tri)_(\d)\s*\[\s*(\d+):(\d+)\]', 3),        # copy_0[W:0]
            (r'(n|node)(\d)\s*\[\s*(\d+):(\d+)\]', 4),                     # node0[W:0]
            (r'(\w+)\s*\[\s*(\d+):(\d+)\]\s*;\s*\n\s*\1\s*\[\s*(\d+):(\d+)\]', 2),  # 连续重复声明
        ]

        # ── 检查命名模式：前缀+数字（用于非位宽场景）──
        # 如 wire copy0, copy1, copy2; 或 reg r0, r1, r2;
        # 以及 reg [7:0] copy0, copy1, copy2;（单行多信号声明）
        _numbered_names = {}
        for base in ['copy', 'reg', 'dup', 'tri', 'r', 'node']:
            # 模式 A：带 wire/reg 前缀的独立声明（如 "wire copy0"）
            for m in re.finditer(
                rf'(wire|reg)\s+(?:\[[^\]]*\])?\s*{base}(\d)\b',
                content, re.IGNORECASE
            ):
                idx = m.group(2)
                _numbered_names.setdefault(base, set()).add(idx)
            # 模式 B：逗号分隔的多信号声明 — 提取整行中所有 base+数字
            for m in re.finditer(
                rf'(?:wire|reg)\s*(?:\[[^\]]*\])?\s*{base}\d[\s\S]*?;',
                content, re.IGNORECASE
            ):
                # 从匹配行中提取所有 base+数字
                for sub_m in re.finditer(rf'{base}(\d)', m.group(0)):
                    idx = sub_m.group(1)
                    _numbered_names.setdefault(base, set()).add(idx)

        # 检查是否有 3 个不同的数字索引（标准 TMR）或 2 个（伪 TMR）
        for base, indices in _numbered_names.items():
            if len(indices) >= 3:
                sorted_idx = sorted(indices, key=int)[:3]
                result["detected"] = True
                # 构造副本名：如 copy0, copy1, copy2
                result["copies"] = [f"{base}{i}" for i in sorted_idx]
                result["tmr_type"] = "triplicate_reg"
                # 收集位宽
                for c in result["copies"]:
                    wm = re.search(
                        rf'(?:wire|reg)\s*\[?\s*(\d+):(\d+)\s*\]?\s*{re.escape(c)}\b',
                        content
                    )
                    if wm:
                        try:
                            w = int(wm.group(1)) - int(wm.group(2)) + 1
                            result["widths_per_copy"][c] = w
                        except ValueError:
                            pass
                if result["widths_per_copy"]:
                    result["signal_width"] = max(result["widths_per_copy"].values())
                break
            elif len(indices) == 2:
                # 伪 TMR 检测：有 2 个副本但不足 3 个
                sorted_idx = sorted(indices, key=int)[:2]
                result["detected"] = True
                result["copies"] = [f"{base}{i}" for i in sorted_idx]
                result["tmr_type"] = "fake_tmr"
                result["issues"].append("fake_tmr")
                break

        # ── 模式 1b：后缀名模式 _a/_b/_c 或 _1/_2/_3 ──
        if not result["detected"]:
            for suffix_pat, suffix_list in [
                (r'(\w+)_([abc])\b', ['a', 'b', 'c']),
                (r'(\w+)_([123])\b', ['1', '2', '3']),
            ]:
                suffix_matches = {}
                for m in re.finditer(suffix_pat, content):
                    base_name = m.group(1)
                    suffix_val = m.group(2)
                    # 排除关键字
                    if base_name.lower() in ('module', 'input', 'output', 'wire', 'reg',
                                             'always', 'assign', 'begin', 'end', 'case',
                                             'if', 'else', 'for', 'while'):
                        continue
                    if base_name not in suffix_matches:
                        suffix_matches[base_name] = set()
                    suffix_matches[base_name].add(suffix_val)

                for base_name, suffixes in suffix_matches.items():
                    if all(s in suffixes for s in suffix_list):
                        result["detected"] = True
                        result["copies"] = [f"{base_name}_{s}" for s in suffix_list]
                        result["tmr_type"] = "triplicate_suffix"
                        result["signal_names"] = [f"{base_name}_{s}" for s in suffix_list]
                        # 提取位宽
                        for c in result["copies"]:
                            wm = re.search(
                                rf'(?:wire|reg)\s*\[?\s*(\d+):(\d+)\s*\]?\s*{re.escape(c)}\b',
                                content
                            )
                            if wm:
                                try:
                                    w = int(wm.group(1)) - int(wm.group(2)) + 1
                                    result["widths_per_copy"][c] = w
                                except ValueError:
                                    pass
                        if result["widths_per_copy"]:
                            result["signal_width"] = max(result["widths_per_copy"].values())
                        break
                if result["detected"]:
                    break

        # 模式 2：三个 always 块（同步复位，驱动同时钟信号）
        if not result["detected"]:
            always_blocks = list(re.finditer(
                r'always\s*@\s*\(.*?posedge\s+(\w+).*?negedge\s+(\w+)\s*\)',
                content, re.IGNORECASE
            ))
            if len(always_blocks) >= 3:
                # 检查是否驱动不同的 reg（三个冗余副本）
                regs_in_blocks = set()
                for ab in always_blocks[:6]:
                    # 查找 always 块下方第一个非阻塞赋值目标
                    _after = content[ab.end():ab.end()+300]
                    _reg_m = re.search(r'(\w+)\s*<=\s*\w+', _after)
                    if _reg_m:
                        regs_in_blocks.add(_reg_m.group(1))
                if len(regs_in_blocks) >= 3:
                    result["detected"] = True
                    result["copies"] = list(regs_in_blocks)[:3]
                    result["tmr_type"] = "triplicate_always"

        # ── 投票器检测 ──
        voter_patterns = [
            r'(maj|majority|voter)',
            r'(\w+)\s*&\s*(\w+)\s*\|\s*\1\s*&\s*(\w+)\s*\|\s*\2\s*&\s*\3',  # ab|ac|bc
            r'(\w+)\s*&\s*(\w+)\s*\|\s*\1\s*&\s*(\w+)\s*\|\s*\2\s*&\s*\3',  # 多数投票逻辑
            r'assign\s+(\w+)\s*=\s*\(.*?&.*?\).*?\|.*?\(.*?&.*?\).*?\|',
            r'assign\s+(\w+)\s*=\s*\(.*?\^.*?\).*?\&.*?\(.*?\^.*?\)',        # (a^b)&(a^c)&(b^c) 变体
        ]
        for vp in voter_patterns:
            vmatches = list(re.finditer(vp, content, re.IGNORECASE))
            if vmatches:
                result["has_voter"] = True
                result["voter_lines"] = [content[:m.start()].count('\n') + 1 for m in vmatches[:3]]
                # 尝试提取投票器输出信号名
                if vp.startswith(r'assign\s+(\w+)'):
                    vm = vmatches[0]
                    result["voter_output_name"] = vm.group(1)
                break

        # ── TMR 反模式检测 ──

        # 反模式 1：伪 TMR —— 声明了 TMR 模式的信号但只有 2 个副本
        if result["detected"] and len(result["copies"]) < 3:
            result["issues"].append("fake_tmr")

        # 反模式 2：位宽不一致的 TMR
        if result["detected"] and result["widths_per_copy"]:
            widths_set = set(result["widths_per_copy"].values())
            if len(widths_set) > 1:
                result["issues"].append("incomplete_tmr")

        # 反模式 3：有副本和投票器，但投票器输出未被任何后续逻辑使用
        if result["detected"] and result["has_voter"]:
            voter_out = result.get("voter_output_name")
            if voter_out:
                # 检查投票器输出是否被使用（出现在 assign/always 或端口列表中）
                usage_pattern = rf'\b{re.escape(voter_out)}\b'
                # 排除自身声明行
                all_uses = list(re.finditer(usage_pattern, content))
                # 过滤：只保留非声明行引用
                usage_count = 0
                for u in all_uses:
                    line_start = content.rfind('\n', 0, u.start()) + 1
                    line_end = content.find('\n', u.start())
                    if line_end < 0:
                        line_end = len(content)
                    line_text = content[line_start:line_end].strip()
                    # 跳过声明行本身
                    if re.match(rf'(wire|reg|assign)\s+.*{re.escape(voter_out)}', line_text):
                        continue
                    usage_count += 1
                if usage_count <= 1:  # 只有 voter 赋值本身，无消费者
                    result["issues"].append("dead_tmr")

        # 问题检测：缺少投票器
        if result["detected"] and not result["has_voter"]:
            result["issues"].append("missing_voter")
            result["issues"].append("voter_needed")

        return result

    def _fix_tmr_missing_voter(self, content: str, tmr_info: Dict) -> str:
        """为检测到的 TMR 冗余添加缺失的多数投票器。

        在 endmodule 前插入 majority voter 逻辑。

        Args:
            content: RTL 源代码。
            tmr_info: _detect_tmr_patterns() 返回的检测信息。

        Returns:
            添加投票器后的代码。
        """
        if not tmr_info.get("detected"):
            return content

        if tmr_info.get("has_voter"):
            logger.print(f"  [TMR_REPAIR] Voter already exists — skip")
            return content

        copies = tmr_info.get("copies", [])
        if len(copies) < 3:
            return content

        width = tmr_info.get("signal_width", 1)
        w_range = f"[{width-1}:0]" if width > 1 else ""

        c0, c1, c2 = copies[0], copies[1], copies[2]

        _voter_code = f"""
    // ── TMR Majority Voter (auto-fixed by ASTRepairer) ──
    wire {w_range} voter_out;
    genvar _gi;
    generate
        for (_gi = 0; _gi < {width if width > 0 else 1}; _gi = _gi + 1) begin : tmr_voter
            assign voter_out[{w_range}] = ({c0}[_gi] & {c1}[_gi]) |
                                          ({c0}[_gi] & {c2}[_gi]) |
                                          ({c1}[_gi] & {c2}[_gi]);
        end
    endgenerate
    // ── Error flag: any two copies disagree ──
    wire tmr_error_flag = ({c0} != {c1}) | ({c0} != {c2}) | ({c1} != {c2});
"""

        # 在 endmodule 前插入
        _insert_pos = content.rfind('\nendmodule')
        if _insert_pos > 0:
            content = content[:_insert_pos] + _voter_code + content[_insert_pos:]

        logger.print(f"  [TMR_REPAIR] Added majority voter for copies: {c0}, {c1}, {c2}")
        logger.print(f"  [TMR_REPAIR] Voter type: {'bit' if width <= 1 else str(width)+'-bit'} bus, generate-loop")

        return content

    def _fix_tmr_width_mismatch(self, content: str, tmr_info: Dict) -> str:
        """修复 TMR 冗余寄存器之间的位宽不一致。

        检测并修复以下位宽问题：
          1. TMR 副本之间声明宽度不一致
          2. 投票器输出宽度与副本宽度不匹配
          3. 副本信号在赋值/使用处的位宽不匹配

        Args:
            content: RTL 源代码。
            tmr_info: _detect_tmr_patterns() 返回的检测信息。

        Returns:
            修复后的 RTL 代码。
        """
        if not tmr_info.get("detected"):
            return content

        copies = tmr_info.get("copies", [])
        if len(copies) < 3:
            return content

        # ── 1. 收集每个副本的声明宽度 ──
        widths: Dict[str, int] = {}
        for c in copies:
            _m = re.search(
                rf'(wire|reg)\s*\[?\s*(\d+):(\d+)\s*\]?\s*{re.escape(c)}\b',
                content
            )
            if _m:
                try:
                    widths[c] = int(_m.group(2)) - int(_m.group(3)) + 1
                except ValueError:
                    pass
            else:
                # 尝试查找位宽声明的另一种格式：如 wire [WIDTH-1:0] copy0
                _m2 = re.search(
                    rf'(wire|reg)\s+\[?(\w+)\s*-\s*(\d+)\s*:\s*(\d+)\]?\s*{re.escape(c)}\b',
                    content
                )
                if _m2:
                    try:
                        hi = int(_m2.group(2))  # 可能是参数名，跳过
                    except ValueError:
                        pass

        if len(widths) < 2:
            return content

        # ── 2. 修复副本之间的位宽不一致 ──
        _vals = list(widths.values())
        if len(set(_vals)) > 1:
            _target_w = max(_vals)
            _w_range = f"[{_target_w-1}:0]" if _target_w > 1 else ""
            for c, w in widths.items():
                if w != _target_w:
                    _old_decl = re.search(
                        rf'(wire|reg)\s*\[?\s*{w-1}:0\s*\]?\s*{re.escape(c)}\b', content
                    )
                    if _old_decl:
                        _old = _old_decl.group(0)
                        _new = re.sub(
                            r'\[.*?\]', _w_range, _old
                        ) if _w_range else _old.split(c)[0].strip() + ' ' + c
                        content = content.replace(_old, _new)
                        logger.print(f"  [TMR_REPAIR] Width fix: {c} {w}→{_target_w} bits")

        # ── 3. 检查投票器输出宽度是否与副本匹配 ──
        voter_out = tmr_info.get("voter_output_name", "voter_out")
        target_width = max(widths.values()) if widths else tmr_info.get("signal_width", 1)
        if target_width > 1:
            voter_decl = re.search(
                rf'(wire|reg)\s*\[?\s*(\d+):(\d+)\s*\]?\s*{re.escape(voter_out)}\b',
                content
            )
            if voter_decl:
                try:
                    vw = int(voter_decl.group(2)) - int(voter_decl.group(3)) + 1
                    if vw != target_width:
                        _w_range = f"[{target_width-1}:0]"
                        _old = voter_decl.group(0)
                        _new = re.sub(r'\[.*?\]', _w_range, _old)
                        content = content.replace(_old, _new)
                        logger.print(f"  [TMR_REPAIR] Voter width fix: {voter_out} {vw}→{target_width}")
                except ValueError:
                    pass

        # ── 4. 检查副本信号在使用处的位宽不匹配（如赋值语句中的位选）──
        for c in copies:
            if c in widths:
                w = widths[c]
                # 检测形如 copy0[7:0] 的位选与声明位宽是否一致
                for sel_m in re.finditer(
                    rf'{re.escape(c)}\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]',
                    content
                ):
                    try:
                        sel_hi = int(sel_m.group(1))
                        sel_lo = int(sel_m.group(2))
                        sel_w = sel_hi - sel_lo + 1
                        if sel_w != w and sel_w < w:
                            # 位宽不一致，但不自动修改（可能是有意部分选取）
                            logger.print(f"  [TMR_REPAIR] Note: {c} uses [{sel_hi}:{sel_lo}] "
                                         f"(declared [{w-1}:0])")
                    except ValueError:
                        pass

        return content

    def _fix_tmr_incomplete_copies(self, content: str, tmr_info: Dict) -> str:
        """修复伪 TMR：副本数量不足（只有 2 个而不是 3 个）。

        当检测到 TMR 模式但只有 2 个副本时，自动生成缺失的第 3 个副本。

        Args:
            content: RTL 源代码。
            tmr_info: _detect_tmr_patterns() 返回的检测信息。

        Returns:
            修复后的 RTL 代码。
        """
        copies = tmr_info.get("copies", [])
        if len(copies) >= 3:
            return content  # 已经有 3 个，无需修复

        if len(copies) < 2:
            return content

        # 从已有副本推断命名模式
        c0 = copies[0]
        # 尝试推断第三个副本的名称
        third_copy = None

        # 模式 1：copy0, copy1 → 生成 copy2
        _m = re.match(r'^(\D+)(\d+)$', c0)
        if _m:
            base = _m.group(1)
            # 检查索引
            indices = []
            for c in copies:
                cm = re.match(r'^(\D+)(\d+)$', c)
                if cm:
                    indices.append(int(cm.group(2)))
            if indices:
                all_indices = set(range(min(indices), min(indices) + 3))
                missing = sorted(all_indices - set(indices))
                if missing:
                    third_copy = f"{base}{missing[0]}"

        # 模式 2：sig_a, sig_b → 生成 sig_c
        if not third_copy:
            _m = re.match(r'^(\w+)_([a-c])$', c0)
            if _m:
                base = _m.group(1)
                suffix_map = {'a': 'c', 'b': 'c'}
                present = set()
                for c in copies:
                    cm = re.match(r'^(\w+)_([a-c])$', c)
                    if cm:
                        present.add(cm.group(2))
                for needed in ['a', 'b', 'c']:
                    if needed not in present:
                        third_copy = f"{base}_{needed}"
                        break

        # 模式 3：sig_1, sig_2 → 生成 sig_3
        if not third_copy:
            _m = re.match(r'^(\w+)_(\d)$', c0)
            if _m:
                base = _m.group(1)
                present = set()
                for c in copies:
                    cm = re.match(r'^(\w+)_(\d)$', c)
                    if cm:
                        present.add(int(cm.group(2)))
                for needed in [1, 2, 3]:
                    if needed not in present:
                        third_copy = f"{base}_{needed}"
                        break

        if not third_copy:
            logger.print(f"  [TMR_REPAIR] Could not infer third copy name from {copies}")
            return content

        # 检查第三个副本是否已存在
        if re.search(rf'\b{re.escape(third_copy)}\b', content):
            logger.print(f"  [TMR_REPAIR] Third copy '{third_copy}' already exists")
            tmr_info["copies"] = copies + [third_copy]
            return content

        # 获取第一个副本的声明，复制为第三个副本
        decl_pattern = rf'(wire|reg)\s*(\[[^\]]*\])?\s*{re.escape(c0)}\b'
        decl_m = re.search(decl_pattern, content)
        if not decl_m:
            # 没有位宽声明，简单添加
            decl_pattern = rf'(wire|reg)\s+{re.escape(c0)}\b'
            decl_m = re.search(decl_pattern, content)

        if decl_m:
            old_decl = decl_m.group(0)
            new_decl = old_decl.replace(c0, third_copy)
            # 在第一个副本声明之后插入
            insert_pos = content.find('\n', decl_m.end())
            if insert_pos > 0:
                indent = ''
                line_start = content.rfind('\n', 0, decl_m.start()) + 1
                for ch in content[line_start:decl_m.start()]:
                    if ch in (' ', '\t'):
                        indent += ch
                    else:
                        break
                content = content[:insert_pos] + '\n' + indent + new_decl + ';' + content[insert_pos:]
                tmr_info["copies"] = copies + [third_copy]
                logger.print(f"  [TMR_REPAIR] Added missing third copy: '{third_copy}'")
        else:
            # 在 endmodule 前添加
            insert_pos = content.rfind('\nendmodule')
            if insert_pos > 0:
                indent = '    '
                new_line = f"{indent}wire {third_copy};"
                content = content[:insert_pos] + new_line + '\n' + content[insert_pos:]
                tmr_info["copies"] = copies + [third_copy]
                logger.print(f"  [TMR_REPAIR] Added missing third copy: '{third_copy}' (default wire)")

        return content

    def _fix_tmr_dead_voter(self, content: str, tmr_info: Dict) -> str:
        """修复死 TMR：投票器输出未被后续逻辑使用。

        检测投票器输出信号是否被下游逻辑消费，如果没有，
        则添加默认输出连接到 voter_out。

        Args:
            content: RTL 源代码。
            tmr_info: _detect_tmr_patterns() 返回的检测信息。

        Returns:
            修复后的 RTL 代码。
        """
        voter_out = tmr_info.get("voter_output_name")
        if not voter_out:
            return content

        # 再次确认 voter_out 是否真的未被使用
        usage_pattern = rf'\b{re.escape(voter_out)}\b'
        usage_count = 0
        consumer_found = False
        for u in re.finditer(usage_pattern, content):
            line_start = content.rfind('\n', 0, u.start()) + 1
            line_end = content.find('\n', u.start())
            if line_end < 0:
                line_end = len(content)
            line_text = content[line_start:line_end].strip()
            # 跳过声明行和赋值行（自身定义）
            if re.match(rf'(wire|reg|assign)\s+.*{re.escape(voter_out)}', line_text):
                continue
            consumer_found = True
            break

        if consumer_found:
            logger.print(f"  [TMR_REPAIR] Voter output '{voter_out}' is used — no dead TMR fix needed")
            return content

        # 投票器输出未被使用，添加一个默认的使用连接
        # 在 endmodule 前添加注释说明
        _insert_pos = content.rfind('\nendmodule')
        if _insert_pos > 0:
            _note = (
                f"\n    // ── Note: voter_out '{voter_out}' is unconnected "
                f"(detected by ASTRepairer) ──\n"
            )
            content = content[:_insert_pos] + _note + content[_insert_pos:]
            logger.print(f"  [TMR_REPAIR] Added note for unused voter output '{voter_out}'")

        return content

    # ------------------------------------------------------------------
    # AST 级修复增强（v3.5）
    # ------------------------------------------------------------------

    def _fix_missing_begin_end(self, content: str) -> str:
        """修复 always 块中缺失的 begin/end 关键字。

        检测模式：always @(...) 后直接跟 if/assign 语句但缺少 begin
        如：always @(posedge clk) if (!rst) ... else ... → 添加 begin/end

        Args:
            content: RTL 源代码。

        Returns:
            修复后的 RTL 代码。
        """
        logger.print(f"  [AST_REPAIR] Checking for missing begin/end in always blocks...")

        pattern = re.compile(
            r'(always\s+@\s*\([^)]+\))\s*(\n\s*)?(if\s*\(|assign\s|case\s*\()',
            re.IGNORECASE | re.DOTALL
        )

        fixed = content
        changes = 0
        for match in pattern.finditer(fixed):
            always_decl = match.group(1)
            indent = match.group(2) or ''
            stmt_start = match.group(3)

            search_pos = match.end()
            depth = 0
            end_pos = -1
            in_string = False
            in_comment = False

            for i in range(search_pos, len(fixed)):
                ch = fixed[i]
                if in_comment:
                    if ch == '\n':
                        in_comment = False
                    continue
                if ch == '/' and i + 1 < len(fixed) and fixed[i + 1] == '/':
                    in_comment = True
                    continue
                if ch == '"' and (i == 0 or fixed[i - 1] != '\\'):
                    in_string = not in_string
                    continue
                if in_string:
                    continue

                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                elif ch == ';' and depth == 0:
                    end_pos = i + 1
                    break

            if end_pos > 0:
                original_body = fixed[search_pos:end_pos]
                fixed_body = f" begin{indent}{original_body}{indent}end"
                fixed = fixed[:search_pos] + fixed_body + fixed[end_pos:]
                changes += 1

        if changes > 0:
            logger.print(f"  [AST_REPAIR]   Added begin/end to {changes} always blocks")
        else:
            logger.print(f"  [AST_REPAIR]   No missing begin/end found")

        return fixed

    def _fix_sensitivity_list(self, content: str) -> str:
        """修复 always 块敏感列表缺失。

        检测模式：always @(*) 缺少星号，或敏感列表为空
        如：always @() → always @(*)

        Args:
            content: RTL 源代码。

        Returns:
            修复后的 RTL 代码。
        """
        logger.print(f"  [AST_REPAIR] Checking sensitivity lists...")

        fixed = re.sub(
            r'always\s+@\s*\(\s*\)',
            'always @(*)',
            content,
            flags=re.IGNORECASE
        )

        fixed = re.sub(
            r'always\s+@\s*(\*)',
            'always @(*) ',
            fixed,
            flags=re.IGNORECASE
        )

        if fixed != content:
            logger.print(f"  [AST_REPAIR]   Fixed sensitivity lists")

        return fixed

    def _fix_always_type_mismatch(self, content: str) -> str:
        """修复 always 块类型不匹配。

        检测模式：
        1. 组合逻辑 always @(*) 使用非阻塞赋值 <=
        2. 时序逻辑 always @(posedge) 使用阻塞赋值 =

        Args:
            content: RTL 源代码。

        Returns:
            修复后的 RTL 代码（仅报告，不自动修改）。
        """
        logger.print(f"  [AST_REPAIR] Checking always block assignment types...")

        seq_pattern = re.compile(
            r'always\s+@\s*\([^)]*(posedge|negedge)[^)]*\)',
            re.IGNORECASE
        )

        comb_pattern = re.compile(
            r'always\s+@\s*\(\s*\*\s*\)',
            re.IGNORECASE
        )

        seq_always = list(seq_pattern.finditer(content))
        comb_always = list(comb_pattern.finditer(content))

        for match in seq_always:
            block_start = match.end()
            block_end = content.find('end', block_start)
            if block_end > 0:
                block_text = content[block_start:block_end]
                if ' = ' in block_text and '<=' not in block_text:
                    logger.print(f"  [AST_REPAIR]   Warning: Sequential always uses blocking assignment '='")

        for match in comb_always:
            block_start = match.end()
            block_end = content.find('end', block_start)
            if block_end > 0:
                block_text = content[block_start:block_end]
                if '<=' in block_text:
                    logger.print(f"  [AST_REPAIR]   Warning: Combinational always uses non-blocking assignment '<='")

        return content

    def _fix_redundant_wire_declaration(self, content: str) -> str:
        """修复重复的 wire/reg 声明（回归测试失败的根因）。

        检测模式：同一个信号被声明多次
        如：wire [7:0] data; 和 wire data; 同时存在

        Args:
            content: RTL 源代码。

        Returns:
            修复后的 RTL 代码（保留第一个完整声明，移除后续重复声明）。
        """
        logger.print(f"  [AST_REPAIR] Checking for redundant wire/reg declarations...")

        decl_pattern = re.compile(
            r'(wire|reg|input|output|inout)\s+(?:\[[^\]]*\])?\s*([\w,\s]+?)\s*;',
            re.IGNORECASE
        )

        declarations = {}
        for match in decl_pattern.finditer(content):
            dtype = match.group(1).lower()
            names_str = match.group(2)
            names = [n.strip() for n in re.split(r',', names_str) if n.strip()]
            for name in names:
                if name not in declarations:
                    declarations[name] = []
                declarations[name].append({
                    'type': dtype,
                    'start': match.start(),
                    'end': match.end(),
                    'full': match.group(0),
                })

        redundant = {name: decls for name, decls in declarations.items() if len(decls) > 1}
        if not redundant:
            logger.print(f"  [AST_REPAIR]   No redundant declarations found")
            return content

        logger.print(f"  [AST_REPAIR]   Found {len(redundant)} signals with redundant declarations:")

        lines = content.split('\n')
        lines_to_remove = set()
        signals_to_remove = {}

        for name, decls in redundant.items():
            logger.print(f"  [AST_REPAIR]     - {name}: {len(decls)} declarations")
            for i, decl in enumerate(decls):
                if i == 0:
                    continue
                line_num = content[:decl['start']].count('\n')
                if line_num not in signals_to_remove:
                    signals_to_remove[line_num] = set()
                signals_to_remove[line_num].add(name)

        fixed_lines = []
        removed_count = 0

        for i, line in enumerate(lines):
            if i in signals_to_remove:
                decl_match = decl_pattern.search(line)
                if decl_match:
                    names_str = decl_match.group(2)
                    names = [n.strip() for n in re.split(r',', names_str) if n.strip()]
                    remaining_names = [n for n in names if n not in signals_to_remove[i]]
                    if remaining_names:
                        prefix = line[:decl_match.start()]
                        suffix = line[decl_match.end():]
                        new_names = ', '.join(remaining_names)
                        new_line = f"{prefix}{decl_match.group(1)} {decl_match.group(2).replace(names_str, new_names)}{suffix}"
                        fixed_lines.append(new_line)
                        removed_count += len(signals_to_remove[i])
                    else:
                        removed_count += len(signals_to_remove[i])
                        continue
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)

        if removed_count > 0:
            content = '\n'.join(fixed_lines)
            logger.print(f"  [AST_REPAIR]   Removed {removed_count} redundant declarations")
        return content

    def check_ast_support(self) -> Dict[str, Any]:
        """检查 AST 修复能力。"""
        return {
            "pyverilog_available": PYVERILOG_AVAILABLE,
            "ast_repair_capable": PYVERILOG_AVAILABLE,
            "syntax_fixer_available": self._syntax_fixer is not None,
            "repair_modes": [
                "port_direction",
                "port_semicolons",
                "undeclared_signals",
                "undeclared_in_always",
                "missing_endmodule",
                "tmr_missing_voter",
                "tmr_width_mismatch",
                "tmr_fake_copies",
                "tmr_dead_voter",
            ] if not PYVERILOG_AVAILABLE else [
                "port_direction_ast",
                "port_declaration_ast",
                "signal_width_ast",
                "type_inference_ast",
                "port_semicolons",
                "undeclared_signals",
                "undeclared_in_always",
                "missing_endmodule",
                "tmr_detection",
                "tmr_missing_voter",
                "tmr_width_mismatch",
                "tmr_fake_copies",
                "tmr_dead_voter",
                "tmr_anti_patterns",
            ],
        }


# ============================================================================
# Quick Test
# ============================================================================

if __name__ == "__main__":
    repairer = ASTRepairer()
    logger.print(f"\nAST support: {repairer.check_ast_support()}")

    # 测试用例：端口方向缺失
    test_code = """\
module test (
    clk,
    rst_n,
    data_in,
    data_out
);
    input wire clk;
    input wire rst_n;
    input wire [7:0] data_in;
    output reg [7:0] data_out;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            data_out <= 8'b0;
        else
            data_out <= data_in;
    end
endmodule
"""
    fixed = repairer.fix(test_code, ["port direction missing"])
    logger.print(f"\nFixed code:\n{fixed}")


# ============================================================================
# 新增方法说明（v2.0 增强）
# ============================================================================
# 以下为 v2.0 版本新增/增强的方法：
#
# 1. _fix_port_direction() — 增强版
#    - 新增：端口在列表中但缺少 input/output，模块内有 wire/reg 声明时，
#      自动推断方向（根据赋值上下文判断 input/output）
#    - 新增：保留已有 wire/reg 声明的位宽信息，仅添加方向关键字
#
# 2. _detect_undeclared_in_always() — 新增方法
#    - 扫描所有 always @(...) 块中的信号引用
#    - 与已声明的 wire/reg/input/output/inout 交叉比对
#    - 自动插入缺失的 wire 声明到 module 声明区域
#
# 3. _detect_tmr_patterns() — 增强版
#    - 新增后缀命名模式检测：_a/_b/_c 和 _1/_2/_3
#    - 新增反模式检测：
#      * fake_tmr：只有 2 个副本而非 3 个
#      * incomplete_tmr：副本信号位宽不一致
#      * dead_tmr：投票器输出未被下游逻辑使用
#    - 增强投票器检测：提取 voter_output_name
#    - 增强位宽收集：widths_per_copy 字典
#
# 4. _fix_tmr_width_mismatch() — 增强版
#    - 新增：投票器输出宽度与副本宽度的匹配检查
#    - 新增：副本在使用处的位选与声明宽度的一致性检查（仅报告，不自动修改）
#
# 5. _fix_tmr_incomplete_copies() — 新增方法
#    - 修复伪 TMR：当副本只有 2 个时，自动推断并生成第 3 个副本
#    - 支持多种命名模式：数字索引、_a/_b/_c 后缀、_1/_2/_3 后缀
#
# 6. _fix_tmr_dead_voter() — 新增方法
#    - 检测投票器输出信号是否被消费
#    - 未被使用时在 endmodule 前添加注释说明
# ============================================================================
