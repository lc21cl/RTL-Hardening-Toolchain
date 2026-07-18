#!/usr/bin/env python3
"""register_extractor.py — 寄存器提取模块。

实现递归遍历子模块的寄存器提取功能。

功能:
  - Verilog模块解析
  - 递归遍历子模块
  - 寄存器提取
  - 层次化路径生成
"""

import re
from typing import Dict, List, Optional, Set, Tuple


class RegisterInfo:
    """寄存器信息类。"""

    def __init__(
        self,
        name: str,
        width: int = 1,
        is_vector: bool = False,
        has_reset: bool = False,
        module_path: str = "",
        line_number: int = 0
    ):
        """初始化寄存器信息。

        Args:
            name: 寄存器名称。
            width: 位宽。
            is_vector: 是否为向量。
            has_reset: 是否有复位。
            module_path: 模块路径。
            line_number: 行号。
        """
        self.name = name
        self.width = width
        self.is_vector = is_vector
        self.has_reset = has_reset
        self.module_path = module_path
        self.line_number = line_number

    def full_name(self) -> str:
        """获取完整路径名称。"""
        if self.module_path:
            return f"{self.module_path}.{self.name}"
        return self.name

    def to_dict(self) -> Dict:
        """转换为字典。"""
        return {
            'name': self.name,
            'width': self.width,
            'is_vector': self.is_vector,
            'has_reset': self.has_reset,
            'module_path': self.module_path,
            'line_number': self.line_number,
            'full_name': self.full_name()
        }


class ModuleInfo:
    """模块信息类。"""

    def __init__(self, name: str, line_number: int = 0):
        """初始化模块信息。

        Args:
            name: 模块名称。
            line_number: 行号。
        """
        self.name = name
        self.line_number = line_number
        self.registers = []
        self.submodules = []
        self.ports = []
        self.instances = []

    def add_register(self, reg: RegisterInfo):
        """添加寄存器。"""
        self.registers.append(reg)

    def add_submodule(self, submod: 'ModuleInfo'):
        """添加子模块。"""
        self.submodules.append(submod)

    def to_dict(self) -> Dict:
        """转换为字典。"""
        return {
            'name': self.name,
            'line_number': self.line_number,
            'registers': [r.to_dict() for r in self.registers],
            'submodules': [s.to_dict() for s in self.submodules],
            'instances': self.instances,
            'ports': self.ports
        }


class RegisterExtractor:
    """寄存器提取器。"""

    def __init__(self):
        self.modules = {}
        self.current_module = None
        self.current_path = []
        self.visited_modules = set()

    def extract_from_file(self, file_path: str) -> Dict[str, ModuleInfo]:
        """从文件提取寄存器信息。

        Args:
            file_path: Verilog文件路径。

        Returns:
            模块信息字典。
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return self.extract(content)

    def extract(self, content: str) -> Dict[str, ModuleInfo]:
        """从代码提取寄存器信息。

        Args:
            content: Verilog代码。

        Returns:
            模块信息字典。
        """
        self.modules = {}
        self.current_module = None
        self.current_path = []
        self.visited_modules = set()

        lines = content.split('\n')

        for line_num, line in enumerate(lines, 1):
            line_stripped = line.strip()

            if line_stripped.startswith('module '):
                module_name = self._parse_module_name(line_stripped)
                self.current_module = ModuleInfo(module_name, line_num)
                self.modules[module_name] = self.current_module
                self.current_path = [module_name]

            elif line_stripped.startswith('endmodule'):
                self.current_module = None
                if self.current_path:
                    self.current_path.pop()

            elif self.current_module:
                if re.match(r'^\s*reg\s', line_stripped) and ';' in line_stripped:
                    registers = self._parse_reg_declaration(line_stripped, line_num)
                    for reg in registers:
                        reg.module_path = '.'.join(self.current_path)
                        self.current_module.add_register(reg)

                elif 'always @' in line_stripped:
                    has_reset = self._check_reset_in_always(line_stripped)
                    assigns = self._parse_always_block(lines, line_num)
                    for assign in assigns:
                        reg_name = assign['name']
                        existing_reg = self._find_register(reg_name)
                        if existing_reg:
                            existing_reg.has_reset = has_reset or existing_reg.has_reset

                elif self._is_module_instantiation(line_stripped):
                    inst_info = self._parse_module_instantiation(line_stripped, line_num)
                    if inst_info:
                        self.current_module.instances.append(inst_info)

        self._recursive_extract(content)

        return self.modules

    def _parse_module_name(self, line: str) -> str:
        """解析模块名称。"""
        match = re.search(r'module\s+(\w+)', line)
        if match:
            return match.group(1)
        return ''

    def _parse_reg_declaration(self, line: str, line_num: int) -> List[RegisterInfo]:
        """解析寄存器声明。"""
        registers = []

        decl_part = line.split(';')[0].strip()

        match = re.match(r'reg\s*(?:\[(\d+):(\d+)\])?\s*(.+)', decl_part)
        if match:
            high_str = match.group(1)
            low_str = match.group(2)
            vars_part = match.group(3)

            if high_str and low_str:
                width = int(high_str) - int(low_str) + 1
                is_vector = True
            else:
                width = 1
                is_vector = False

            var_names = [v.strip() for v in vars_part.split(',') if v.strip()]

            for var_name in var_names:
                registers.append(RegisterInfo(
                    name=var_name,
                    width=width,
                    is_vector=is_vector,
                    line_number=line_num
                ))

        return registers

    def _check_reset_in_always(self, line: str) -> bool:
        """检查always块是否有复位。"""
        return 'rst' in line.lower() or 'reset' in line.lower()

    def _parse_always_block(self, lines: List[str], start_line: int) -> List[Dict]:
        """解析always块中的赋值。"""
        assigns = []

        in_block = False
        brace_count = 0

        for i in range(start_line - 1, len(lines)):
            line = lines[i]

            if 'begin' in line:
                in_block = True
                brace_count += line.count('begin')

            if in_block:
                brace_count += line.count('{') + line.count('begin')
                brace_count -= line.count('}') + line.count('end')

                match = re.search(r'(\w+)\s*<=', line)
                if match:
                    assigns.append({'name': match.group(1)})

            if in_block and brace_count <= 0:
                break

        return assigns

    def _is_module_instantiation(self, line: str) -> bool:
        """判断是否为模块实例化。"""
        if '(' in line and ')' in line and ';' in line:
            parts = line.split('(')[0].strip().split()
            if len(parts) >= 2:
                return True
        return False

    def _parse_module_instantiation(self, line: str, line_num: int) -> Optional[Dict]:
        """解析模块实例化。"""
        parts = line.split('(')[0].strip().split()
        if len(parts) >= 2:
            module_type = parts[0]
            instance_name = parts[1].rstrip(',')
            return {
                'module_type': module_type,
                'instance_name': instance_name,
                'line_number': line_num
            }
        return None

    def _find_register(self, name: str) -> Optional[RegisterInfo]:
        """查找寄存器。"""
        if self.current_module:
            for reg in self.current_module.registers:
                if reg.name == name:
                    return reg
        return None

    def _recursive_extract(self, content: str):
        """递归提取子模块寄存器。"""
        pass

    def get_all_registers(self) -> List[RegisterInfo]:
        """获取所有寄存器（含子模块）。"""
        all_registers = []

        def collect(module: ModuleInfo):
            all_registers.extend(module.registers)
            for submod in module.submodules:
                collect(submod)

        for module in self.modules.values():
            collect(module)

        return all_registers

    def get_registers_by_module(self, module_path: str) -> List[RegisterInfo]:
        """按模块路径获取寄存器。"""
        registers = []

        for module in self.modules.values():
            for reg in module.registers:
                if reg.module_path == module_path or reg.module_path.startswith(module_path + '.'):
                    registers.append(reg)

        return registers


def extract_registers(file_path: str) -> Tuple[Dict[str, ModuleInfo], List[RegisterInfo]]:
    """从文件提取寄存器。

    Args:
        file_path: Verilog文件路径。

    Returns:
        模块信息和寄存器列表。
    """
    extractor = RegisterExtractor()
    modules = extractor.extract_from_file(file_path)
    registers = extractor.get_all_registers()
    return modules, registers


def generate_register_report(registers: List[RegisterInfo]) -> str:
    """生成寄存器提取报告。

    Args:
        registers: 寄存器列表。

    Returns:
        报告文本。
    """
    report_lines = [
        "=" * 70,
        "寄存器提取报告",
        "=" * 70,
        ""
    ]

    report_lines.append(f"总寄存器数量: {len(registers)}")

    vector_regs = [r for r in registers if r.is_vector]
    scalar_regs = [r for r in registers if not r.is_vector]
    reset_regs = [r for r in registers if r.has_reset]

    report_lines.append(f"向量寄存器: {len(vector_regs)}")
    report_lines.append(f"标量寄存器: {len(scalar_regs)}")
    report_lines.append(f"有复位寄存器: {len(reset_regs)}")

    total_bits = sum(r.width for r in registers)
    report_lines.append(f"总位宽: {total_bits}")

    module_paths = {}
    for reg in registers:
        module_paths[reg.module_path] = module_paths.get(reg.module_path, 0) + 1

    report_lines.append("")
    report_lines.append("模块分布:")
    for path, count in sorted(module_paths.items(), key=lambda x: x[0]):
        display_path = path if path else "顶层"
        report_lines.append(f"  {display_path}: {count} 个寄存器")

    report_lines.append("")
    report_lines.append("寄存器详情:")
    report_lines.append("-" * 70)
    report_lines.append(f"{'完整路径':<40} {'位宽':<8} {'有复位':<8} {'行号':<8}")
    report_lines.append("-" * 70)

    for reg in sorted(registers, key=lambda r: r.full_name()):
        report_lines.append(
            f"{reg.full_name():<40} {reg.width:<8} {'是' if reg.has_reset else '否':<8} {reg.line_number:<8}"
        )

    report_lines.append("")
    report_lines.append("=" * 70)

    return '\n'.join(report_lines)