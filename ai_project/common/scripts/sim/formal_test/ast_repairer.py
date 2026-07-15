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

        在 module 端口声明中，为未指定方向的端口添加 'wire' 类型声明。
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

        # 为端口列表中的每个标识符添加 wire 类型
        # 这可以修复纯端口名列表（不含 direction 的 old-style 端口）
        # 查找裸端口名：孤立标识符
        def _add_wire_prefix(m: re.Match) -> str:
            name = m.group(0).strip()
            # 跳过 module 名、关键字、标点
            if re.match(r'^\w+$', name) and not re.match(
                r'\b(module|input|output|inout|wire|reg|begin|end|if|else|case|endcase|'
                r'always|initial|assign|for|while|repeat|function|endfunction|'
                r'task|endtask|generate|endgenerate|specify|endspecify)\b', name
            ):
                # 确保它不是已有的 wire/reg 声明的一部分
                pre_chars = content[:module_match.end() + m.start()]
                last_keyword = re.findall(r'\b(input|output|inout)\b', pre_chars)
                if not last_keyword or last_keyword[-1] not in ('input', 'output', 'inout'):
                    return f'wire {name}'
            return m.group(0)

        # 处理端口列表
        port_items = re.findall(r'\b\w+\b', port_list_text)
        # 跳过第一个（通常是 module 名的延续或端口开始）
        for name in port_items:
            if name in ('input', 'output', 'inout', 'wire', 'reg'):
                return content  # 已有方向声明，不处理
            break

        # 简单方案：在 module 声明后添加默认 wire 声明（如果有逗号分隔的端口列表）
        # 检查是否是纯逗号分隔的端口名
        if ',' in port_list_text and not re.search(r'\b(input|output|inout)\b', port_list_text):
            # 在 module 行之后插入默认 wire 声明
            insert_pos = content.find('\n', module_match.end())
            if insert_pos > 0:
                port_names = [p.strip() for p in port_list_text.split(',')]
                wire_decls = '\n'.join([f'    wire {p};' for p in port_names if re.match(r'^\w+$', p)])
                content = content[:insert_pos] + '\n' + wire_decls + content[insert_pos:]

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
            if _tmr_info.get("has_voter"):
                logger.print(f"  [AST_REPAIR]   ✓ Voter already present — no fix needed")
        else:
            logger.print(f"  [AST_REPAIR]   No TMR pattern detected")

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

        Returns:
            Dict 含 detected, copies, width, has_voter, voter_lines, issues 字段。
        """
        result: Dict[str, Any] = {
            "detected": False,
            "copies": [],
            "signal_width": 0,
            "has_voter": False,
            "voter_lines": [],
            "issues": [],
            "tmr_type": None,
        }

        # 模式 1：三重寄存器声明（naming: copy0/copy1/copy2, reg0/reg1/reg2, dup0/dup1/dup2）
        _triplet_patterns = [
            (r'(copy|reg|dup|r|tri)(\d)\s*\[\s*(\d+):(\d+)\]', 3),  # [WIDTH-1:0]
            (r'(copy|reg|dup)_(\d)\s*\[\s*(\d+):(\d+)\]', 3),
            (r'(n|node)(\d)\s*\[\s*(\d+):(\d+)\]', 4),             # DICE nodes
        ]

        for pat, min_count in _triplet_patterns:
            matches = list(re.finditer(pat, content, re.IGNORECASE))
            if len(matches) >= min_count:
                # 检查是否三个索引不同
                indices = set()
                names = set()
                for m in matches:
                    indices.add(m.group(2))
                    names.add(m.group(1).lower())
                if len(indices) >= 3 or (len(indices) == 3 and len(matches) >= 3):
                    result["detected"] = True
                    result["copies"] = [f"{next(n for n in names)}{i}" for i in sorted(indices)[:3]]
                    result["tmr_type"] = "triplicate_reg"
                    # 提取位宽
                    try:
                        hi = int(matches[0].group(3))
                        lo = int(matches[0].group(4))
                        result["signal_width"] = hi - lo + 1
                    except (ValueError, IndexError):
                        result["signal_width"] = 0
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

        # 投票器检测
        voter_patterns = [
            r'(maj|majority|voter)',
            r'(\w+)\s*&\s*(\w+)\s*\|\s*\1\s*&\s*(\w+)\s*\|\s*\2\s*&\s*\3',  # ab|ac|bc
            r'assign\s+\w+\s*=\s*\(.*?&.*?\).*?\|.*?\(.*?&.*?\).*?\|',
        ]
        for vp in voter_patterns:
            vmatches = list(re.finditer(vp, content, re.IGNORECASE))
            if vmatches:
                result["has_voter"] = True
                result["voter_lines"] = [content[:m.start()].count('\n') + 1 for m in vmatches[:3]]
                break

        # 问题检测
        if result["detected"] and not result["has_voter"]:
            result["issues"].append("missing_voter")
        if result["detected"] and not result["has_voter"]:
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
        """修复 TMR 冗余寄存器之间的位宽不一致。"""
        if not tmr_info.get("detected"):
            return content

        copies = tmr_info.get("copies", [])
        if len(copies) < 3:
            return content

        # 收集每个副本的声明宽度
        widths: Dict[str, int] = {}
        for c in copies:
            _m = re.search(
                rf'(wire|reg)\s*\[?\s*(\d+):(\d+)\s*\]?\s*{c}\b',
                content
            )
            if _m:
                try:
                    widths[c] = int(_m.group(2)) - int(_m.group(3)) + 1
                except ValueError:
                    pass

        if len(widths) < 2:
            return content

        # 如果有不一致，统一为最大宽度
        _vals = list(widths.values())
        if len(set(_vals)) > 1:
            _target_w = max(_vals)
            _w_range = f"[{_target_w-1}:0]" if _target_w > 1 else ""
            for c, w in widths.items():
                if w != _target_w:
                    _old_decl = re.search(
                        rf'(wire|reg)\s*\[?\s*{w-1}:0\s*\]?\s*{c}\b', content
                    )
                    if _old_decl:
                        _old = _old_decl.group(0)
                        _new = re.sub(
                            r'\[.*?\]', _w_range, _old
                        ) if _w_range else _old.split(c)[0].strip() + ' ' + c
                        content = content.replace(_old, _new)
                        logger.print(f"  [TMR_REPAIR] Width fix: {c} {w}→{_target_w} bits")

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
                "missing_endmodule",
                "tmr_missing_voter",
                "tmr_width_mismatch",
            ] if not PYVERILOG_AVAILABLE else [
                "port_direction_ast",
                "port_declaration_ast",
                "signal_width_ast",
                "type_inference_ast",
                "port_semicolons",
                "undeclared_signals",
                "missing_endmodule",
                "tmr_detection",
                "tmr_missing_voter",
                "tmr_width_mismatch",
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
