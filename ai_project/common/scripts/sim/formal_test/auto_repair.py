#!/usr/bin/env python3
"""auto_repair.py — AST-level自动修复模块。

实现基于AST的代码自动修复功能。

功能:
  - Verilog AST解析
  - 缺陷检测与定位
  - AST-level修复
  - 修复验证
"""

import re
from typing import Dict, List, Optional, Tuple


class RepairAction:
    """修复动作类。"""

    def __init__(
        self,
        action_type: str,
        location: Tuple[int, int],
        target: str,
        replacement: str,
        description: str = ""
    ):
        """初始化修复动作。

        Args:
            action_type: 修复类型。
            location: 位置(行, 列)。
            target: 目标代码。
            replacement: 替换代码。
            description: 描述。
        """
        self.action_type = action_type
        self.location = location
        self.target = target
        self.replacement = replacement
        self.description = description

    def apply(self, code: str) -> str:
        """应用修复。

        Args:
            code: 源代码。

        Returns:
            修复后的代码。
        """
        return code.replace(self.target, self.replacement)

    def to_dict(self) -> Dict:
        """转换为字典。"""
        return {
            'action_type': self.action_type,
            'location': self.location,
            'target': self.target,
            'replacement': self.replacement,
            'description': self.description
        }


class ASTNode:
    """AST节点类。"""

    def __init__(self, node_type: str, value: str = ""):
        """初始化节点。

        Args:
            node_type: 节点类型。
            value: 节点值。
        """
        self.node_type = node_type
        self.value = value
        self.children = []
        self.location = None

    def add_child(self, child: 'ASTNode'):
        """添加子节点。"""
        self.children.append(child)

    def to_dict(self) -> Dict:
        """转换为字典。"""
        return {
            'node_type': self.node_type,
            'value': self.value,
            'children': [child.to_dict() for child in self.children],
            'location': self.location
        }


class VerilogParser:
    """Verilog简单解析器。"""

    def __init__(self):
        self.tokens = []
        self.pos = 0

    def tokenize(self, code: str) -> List[Tuple[str, str, Tuple[int, int]]]:
        """分词。

        Args:
            code: Verilog代码。

        Returns:
            令牌列表。
        """
        tokens = []
        lines = code.split('\n')

        for line_num, line in enumerate(lines, 1):
            pos = 0
            while pos < len(line):
                if line[pos].isspace():
                    pos += 1
                    continue

                if line[pos] == '/':
                    if pos + 1 < len(line) and line[pos + 1] == '/':
                        break
                    elif pos + 1 < len(line) and line[pos + 1] == '*':
                        end_pos = line.find('*/', pos)
                        if end_pos == -1:
                            break
                        pos = end_pos + 2
                        continue

                if line[pos].isalpha() or line[pos] == '_':
                    end = pos
                    while end < len(line) and (line[end].isalnum() or line[end] == '_'):
                        end += 1
                    tokens.append(('IDENTIFIER', line[pos:end], (line_num, pos + 1)))
                    pos = end
                    continue

                if line[pos].isdigit():
                    end = pos
                    while end < len(line) and line[end].isdigit():
                        end += 1
                    tokens.append(('NUMBER', line[pos:end], (line_num, pos + 1)))
                    pos = end
                    continue

                if line[pos] in '{}();,:=<>+-*/&|~^':
                    tokens.append((line[pos], line[pos], (line_num, pos + 1)))
                    pos += 1
                    continue

                pos += 1

        return tokens

    def parse(self, code: str) -> ASTNode:
        """解析Verilog代码。

        Args:
            code: Verilog代码。

        Returns:
            AST根节点。
        """
        self.tokens = self.tokenize(code)
        self.pos = 0

        root = ASTNode('MODULE')

        while self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            if token[0] == 'IDENTIFIER' and token[1] == 'module':
                module_node = self.parse_module()
                root.add_child(module_node)
            elif token[0] == 'IDENTIFIER' and token[1] in ('always', 'assign', 'reg', 'wire', 'input', 'output'):
                stmt_node = self.parse_statement()
                root.add_child(stmt_node)
            else:
                self.pos += 1

        return root

    def parse_module(self) -> ASTNode:
        """解析模块声明。"""
        self.pos += 1
        module_name = self.tokens[self.pos][1]
        self.pos += 1

        module_node = ASTNode('MODULE_DECL', module_name)
        module_node.location = self.tokens[self.pos - 2][2]

        if self.tokens[self.pos][0] == '(':
            self.pos += 1
            while self.pos < len(self.tokens) and self.tokens[self.pos][0] != ')':
                if self.tokens[self.pos][0] == 'IDENTIFIER':
                    port_node = ASTNode('PORT', self.tokens[self.pos][1])
                    port_node.location = self.tokens[self.pos][2]
                    module_node.add_child(port_node)
                self.pos += 1
            self.pos += 1

        if self.tokens[self.pos][0] == ';':
            self.pos += 1

        while self.pos < len(self.tokens) and not (
            self.tokens[self.pos][0] == 'IDENTIFIER' and self.tokens[self.pos][1] == 'endmodule'
        ):
            if self.tokens[self.pos][0] == 'IDENTIFIER':
                if self.tokens[self.pos][1] == 'always':
                    always_node = self.parse_always()
                    module_node.add_child(always_node)
                elif self.tokens[self.pos][1] in ('reg', 'wire', 'input', 'output', 'inout'):
                    decl_node = self.parse_declaration()
                    module_node.add_child(decl_node)
                elif self.tokens[self.pos][1] == 'assign':
                    assign_node = self.parse_assign()
                    module_node.add_child(assign_node)
                else:
                    self.pos += 1
            else:
                self.pos += 1

        if self.tokens[self.pos][0] == 'IDENTIFIER' and self.tokens[self.pos][1] == 'endmodule':
            self.pos += 1

        return module_node

    def parse_always(self) -> ASTNode:
        """解析always块。"""
        self.pos += 1

        always_node = ASTNode('ALWAYS', '')
        always_node.location = self.tokens[self.pos - 1][2]

        if self.tokens[self.pos][0] == '@':
            self.pos += 1
            if self.tokens[self.pos][0] == '(':
                self.pos += 1
                sensitivity = ""
                while self.pos < len(self.tokens) and self.tokens[self.pos][0] != ')':
                    sensitivity += self.tokens[self.pos][1] + ' '
                    self.pos += 1
                self.pos += 1
                always_node.value = sensitivity.strip()

        if self.tokens[self.pos][0] == 'begin':
            self.pos += 1
            while self.pos < len(self.tokens) and not (
                self.tokens[self.pos][0] == 'IDENTIFIER' and self.tokens[self.pos][1] == 'end'
            ):
                stmt_node = self.parse_statement()
                if stmt_node:
                    always_node.add_child(stmt_node)
                else:
                    self.pos += 1
            self.pos += 1

        return always_node

    def parse_declaration(self) -> ASTNode:
        """解析声明。"""
        dtype = self.tokens[self.pos][1]
        self.pos += 1

        decl_node = ASTNode('DECLARATION', dtype)
        decl_node.location = self.tokens[self.pos - 1][2]

        while self.pos < len(self.tokens) and self.tokens[self.pos][0] != ';':
            if self.tokens[self.pos][0] == 'IDENTIFIER':
                var_node = ASTNode('VAR', self.tokens[self.pos][1])
                var_node.location = self.tokens[self.pos][2]
                decl_node.add_child(var_node)
            self.pos += 1

        if self.tokens[self.pos][0] == ';':
            self.pos += 1

        return decl_node

    def parse_assign(self) -> ASTNode:
        """解析assign语句。"""
        self.pos += 1

        assign_node = ASTNode('ASSIGN', '')
        assign_node.location = self.tokens[self.pos - 1][2]

        if self.pos < len(self.tokens) and self.tokens[self.pos][0] == 'IDENTIFIER':
            target = self.tokens[self.pos][1]
            self.pos += 1

            if self.pos < len(self.tokens) and self.tokens[self.pos][0] == '=':
                self.pos += 1

                expr = ""
                while self.pos < len(self.tokens) and self.tokens[self.pos][0] != ';':
                    expr += self.tokens[self.pos][1] + ' '
                    self.pos += 1

                assign_node.value = f"{target} = {expr.strip()}"

                if self.tokens[self.pos][0] == ';':
                    self.pos += 1

        return assign_node

    def parse_statement(self) -> Optional[ASTNode]:
        """解析语句。"""
        if self.pos >= len(self.tokens):
            return None

        token = self.tokens[self.pos]

        if token[0] == 'IDENTIFIER':
            if token[1] == 'always':
                return self.parse_always()
            elif token[1] == 'assign':
                return self.parse_assign()
            elif token[1] in ('if', 'else', 'case', 'for', 'while'):
                return self.parse_control_flow()
            else:
                return self.parse_assignment()

        return None

    def parse_control_flow(self) -> ASTNode:
        """解析控制流语句。"""
        stmt_type = self.tokens[self.pos][1]
        self.pos += 1

        stmt_node = ASTNode(stmt_type.upper(), '')
        stmt_node.location = self.tokens[self.pos - 1][2]

        if stmt_type == 'if':
            if self.tokens[self.pos][0] == '(':
                self.pos += 1
                cond = ""
                while self.pos < len(self.tokens) and self.tokens[self.pos][0] != ')':
                    cond += self.tokens[self.pos][1] + ' '
                    self.pos += 1
                self.pos += 1
                stmt_node.value = cond.strip()

                body_node = self.parse_statement()
                if body_node:
                    stmt_node.add_child(body_node)

        elif stmt_type == 'case':
            if self.tokens[self.pos][0] == '(':
                self.pos += 1
                expr = ""
                while self.pos < len(self.tokens) and self.tokens[self.pos][0] != ')':
                    expr += self.tokens[self.pos][1] + ' '
                    self.pos += 1
                self.pos += 1
                stmt_node.value = expr.strip()

                if self.tokens[self.pos][0] == 'begin':
                    self.pos += 1

        return stmt_node

    def parse_assignment(self) -> ASTNode:
        """解析赋值语句。"""
        target = self.tokens[self.pos][1]
        self.pos += 1

        assign_node = ASTNode('ASSIGNMENT', target)
        assign_node.location = self.tokens[self.pos - 1][2]

        if self.pos < len(self.tokens) and self.tokens[self.pos][0] == '<':
            self.pos += 1
            if self.pos < len(self.tokens) and self.tokens[self.pos][0] == '=':
                self.pos += 1

                expr = ""
                while self.pos < len(self.tokens) and self.tokens[self.pos][0] != ';':
                    expr += self.tokens[self.pos][1] + ' '
                    self.pos += 1

                assign_node.value = f"{target} <= {expr.strip()}"

                if self.tokens[self.pos][0] == ';':
                    self.pos += 1

        elif self.pos < len(self.tokens) and self.tokens[self.pos][0] == '=':
            self.pos += 1

            expr = ""
            while self.pos < len(self.tokens) and self.tokens[self.pos][0] != ';':
                expr += self.tokens[self.pos][1] + ' '
                self.pos += 1

            assign_node.value = f"{target} = {expr.strip()}"

            if self.tokens[self.pos][0] == ';':
                self.pos += 1

        return assign_node


class DefectDetector:
    """缺陷检测器。"""

    def __init__(self):
        self.defects = []

    def detect_single_flop_registers(self, ast: ASTNode) -> List[Dict]:
        """检测单触发器寄存器。

        Args:
            ast: AST节点。

        Returns:
            缺陷列表。
        """
        defects = []

        def traverse(node):
            if node.node_type == 'ASSIGNMENT':
                if 'posedge clk' in ast.value or any(
                    child.node_type == 'ALWAYS' for child in ast.children
                ):
                    defects.append({
                        'type': 'SINGLE_FLOP',
                        'location': node.location,
                        'target': node.value,
                        'description': f"单触发器寄存器: {node.value}"
                    })

            for child in node.children:
                traverse(child)

        traverse(ast)

        return defects

    def detect_missing_reset(self, ast: ASTNode) -> List[Dict]:
        """检测缺失复位的寄存器。

        Args:
            ast: AST节点。

        Returns:
            缺陷列表。
        """
        defects = []

        def traverse(node):
            if node.node_type == 'ALWAYS':
                has_reset = 'rst' in node.value.lower() or 'reset' in node.value.lower()
                if not has_reset:
                    defects.append({
                        'type': 'MISSING_RESET',
                        'location': node.location,
                        'target': node.value,
                        'description': f"缺失复位的always块: {node.value}"
                    })

            for child in node.children:
                traverse(child)

        traverse(ast)

        return defects

    def detect_all(self, ast: ASTNode) -> List[Dict]:
        """检测所有缺陷。

        Args:
            ast: AST节点。

        Returns:
            缺陷列表。
        """
        defects = []
        defects.extend(self.detect_single_flop_registers(ast))
        defects.extend(self.detect_missing_reset(ast))
        return defects


class RepairEngine:
    """修复引擎。"""

    def __init__(self):
        self.actions = []

    def generate_tmr_repair(self, defect: Dict) -> RepairAction:
        """生成TMR修复动作。

        Args:
            defect: 缺陷信息。

        Returns:
            修复动作。
        """
        target = defect['target']

        parts = target.split('<=')
        if len(parts) == 2:
            var_name = parts[0].strip()
            expr = parts[1].strip()

            replacement = f"""
    // TMR加固: {var_name}
    reg {var_name}_A, {var_name}_B, {var_name}_C;
    wire {var_name}_vote;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            {var_name}_A <= 1'b0;
            {var_name}_B <= 1'b0;
            {var_name}_C <= 1'b0;
        end else begin
            {var_name}_A <= {expr};
            {var_name}_B <= {expr};
            {var_name}_C <= {expr};
        end
    end

    assign {var_name}_vote = {var_name}_A & {var_name}_B | {var_name}_A & {var_name}_C | {var_name}_B & {var_name}_C;
    assign {var_name} = {var_name}_vote;
"""
            return RepairAction(
                action_type='TMR_REPAIR',
                location=defect['location'],
                target=target + ';',
                replacement=replacement,
                description=f"TMR加固: {var_name}"
            )

        return None

    def generate_reset_repair(self, defect: Dict) -> RepairAction:
        """生成复位修复动作。

        Args:
            defect: 缺陷信息。

        Returns:
            修复动作。
        """
        target = defect['target']

        if '@(posedge clk)' in target:
            replacement = target.replace(
                '@(posedge clk)',
                '@(posedge clk or posedge rst)'
            )
            return RepairAction(
                action_type='ADD_RESET',
                location=defect['location'],
                target=target,
                replacement=replacement,
                description="添加复位敏感性"
            )

        return None

    def generate_repair_actions(self, defects: List[Dict]) -> List[RepairAction]:
        """生成修复动作列表。

        Args:
            defects: 缺陷列表。

        Returns:
            修复动作列表。
        """
        actions = []

        for defect in defects:
            if defect['type'] == 'SINGLE_FLOP':
                action = self.generate_tmr_repair(defect)
                if action:
                    actions.append(action)
            elif defect['type'] == 'MISSING_RESET':
                action = self.generate_reset_repair(defect)
                if action:
                    actions.append(action)

        return actions

    def apply_repairs(self, code: str, actions: List[RepairAction]) -> str:
        """应用修复动作。

        Args:
            code: 源代码。
            actions: 修复动作列表。

        Returns:
            修复后的代码。
        """
        repaired_code = code

        for action in actions:
            repaired_code = action.apply(repaired_code)

        return repaired_code


def auto_repair(code: str) -> Tuple[str, List[RepairAction]]:
    """自动修复代码。

    Args:
        code: Verilog源代码。

    Returns:
        修复后的代码和修复动作列表。
    """
    parser = VerilogParser()
    detector = DefectDetector()
    engine = RepairEngine()

    ast = parser.parse(code)
    defects = detector.detect_all(ast)
    actions = engine.generate_repair_actions(defects)
    repaired_code = engine.apply_repairs(code, actions)

    return repaired_code, actions


def generate_repair_report(actions: List[RepairAction]) -> str:
    """生成修复报告。

    Args:
        actions: 修复动作列表。

    Returns:
        报告文本。
    """
    report_lines = [
        "=" * 70,
        "Auto-Repair修复报告",
        "=" * 70,
        ""
    ]

    report_lines.append(f"修复动作数量: {len(actions)}")

    for i, action in enumerate(actions, 1):
        report_lines.append("")
        report_lines.append(f"修复 #{i}:")
        report_lines.append(f"  类型: {action.action_type}")
        report_lines.append(f"  位置: 行{action.location[0]}, 列{action.location[1]}")
        report_lines.append(f"  描述: {action.description}")
        report_lines.append(f"  目标: {action.target[:50]}..." if len(action.target) > 50 else f"  目标: {action.target}")
        report_lines.append(f"  替换: {action.replacement[:50]}..." if len(action.replacement) > 50 else f"  替换: {action.replacement}")

    report_lines.append("")
    report_lines.append("=" * 70)

    return '\n'.join(report_lines)


class SyntaxFixer:
    """基于正则的语法修复器。

    使用预定义的修复模式（FIX_PATTERNS）来修复常见的 Verilog 语法错误。
    每个模式包含优先级、名称、搜索模式和替换模式。
    """

    def __init__(self):
        self._FIX_PATTERNS = [
            (100, 'missing_end',
             r'(\balways\s*@\([^)]+\)\s*\begin[^;]*?)(?=\b(?:always|module|endmodule|interface|endinterface|package|endpackage))',
             r'\1\n    end'),

            (95, 'missing_endgenerate',
             r'(generate\s*begin[^;]*?)(?=\b(?:module|endmodule))',
             r'\1\nendgenerate'),

            (90, 'missing_case_default',
             r'(case\s*\([^)]+\)\s*[^;]*?)(?=\bendcase)',
             r'\1    default: ;\n'),

            (85, 'empty_sensitivity',
             r'always\s*@\(\)',
             r'always @(*)'),

            (80, 'missing_or',
             r'always\s*@\(\s*(posedge|negedge)\s+\w+\s+(posedge|negedge)\s+\w+',
             lambda m: f'always @({m.group(1)} {m.group(2).split()[1]} or {m.group(2)} {m.group(2).split()[1]}' if len(m.group(2).split()) > 1 else f'always @({m.group(1)} {m.group(2).split()[0]} or {m.group(2)}'),

            (75, 'missing_semicolon_assign',
             r'(\bassign\s+\w+\s*=\s*[^;]+?)(?=\s*\n\s*\w)',
             r'\1;'),

            (75, 'missing_semicolon_decl',
             r'(\b(?:wire|reg|input|output|inout|parameter)\s+[^;]+?)(?=\s*\n\s*\w)',
             r'\1;'),

            (70, 'old_style_port',
             r'(\bmodule\s+\w+\s*\()([^)]+)(\))',
             r'\1\n    \2\n\3'),

            (70, 'missing_wire_type',
             r'(\b(input|output)\s+(?:\[[^\]]+\]\s+)?)(\w+)',
             r'\1wire \3'),

            (65, 'inout_without_direction',
             r'\binout\s+(?:\[[^\]]+\]\s+)?(\w+)',
             r'inout wire \1'),

            (60, 'missing_parameter_default',
             r'parameter\s+(\w+)\s*(?=[,);])',
             r'parameter \1 = 0'),

            (55, 'missing_assign_continuation_eol',
             r'(\bassign\s+\w+\s*=\s*)([^;]+?)\s*\\\s*$',
             r'\1\2'),

            (55, 'missing_assign_continuation_nl',
             r'(\bassign\s+\w+\s*=\s*)([^;]+?)\s*\n\s*\\',
             r'\1\2'),

            (50, 'stray_backslash',
             r'\\\s*$',
             r''),

            (45, 'missing_semicolon_before_end',
             r'(\b(?:always|if|case|fork|begin)\s*[^{]*?)\s*\n\s*end',
             r'\1;\nend'),

            (40, 'output_reg_type_simple',
             r'(\boutput\s+)(\w+)',
             r'\1reg \2'),

            (35, 'missing_wire_type_multiple',
             r'(\bwire\s+\[[^\]]+\]\s*)(\w+)(,\s*\w+)+',
             r'\1\2'),
        ]

    def _safe_sub(self, pattern, replacement, content):
        """安全替换，保护注释中的内容。"""
        lines = content.split('\n')
        result = []
        for line in lines:
            if '//' in line:
                code_part, comment_part = line.split('//', 1)
                if callable(replacement):
                    code_part = re.sub(pattern, replacement, code_part)
                else:
                    code_part = re.sub(pattern, replacement, code_part)
                result.append(code_part + '//' + comment_part)
            else:
                if callable(replacement):
                    line = re.sub(pattern, replacement, line)
                else:
                    line = re.sub(pattern, replacement, line)
                result.append(line)
        return '\n'.join(result)

    def fix(self, content: str, errors: List[str] = None) -> str:
        """应用所有修复模式。

        Args:
            content: Verilog 源代码。
            errors: 错误消息列表（用于过滤修复模式）。

        Returns:
            修复后的代码。
        """
        if errors is None:
            errors = []

        fixed = content

        for priority, name, search, replace in sorted(self._FIX_PATTERNS, key=lambda x: -x[0]):
            try:
                if callable(replace):
                    fixed = re.sub(search, replace, fixed, flags=re.MULTILINE | re.DOTALL)
                else:
                    fixed = self._safe_sub(search, replace, fixed)
            except re.error:
                pass

        return fixed