#!/usr/bin/env python3
"""placement_constraints.py — 布局约束生成模块。

生成布局约束文件，防止TMR复制模块在物理上靠近导致同时失效。

功能:
  - 生成TCL布局约束
  - 生成Floorplan约束
  - 生成Placement约束
"""

from typing import Dict, List, Optional


def generate_placement_constraints(
    module_name: str,
    replicated_modules: List[str],
    constraint_type: str = 'distance',
    distance: int = 100,
    output_path: Optional[str] = None
) -> str:
    """生成布局约束。

    Args:
        module_name: 顶层模块名。
        replicated_modules: 复制模块列表。
        constraint_type: 约束类型 ('distance', 'region', 'group')。
        distance: 最小距离（微米）。
        output_path: 输出文件路径（可选）。

    Returns:
        约束文件内容。
    """
    constraints = []

    if constraint_type == 'distance':
        constraints = _generate_distance_constraints(module_name, replicated_modules, distance)
    elif constraint_type == 'region':
        constraints = _generate_region_constraints(module_name, replicated_modules)
    elif constraint_type == 'group':
        constraints = _generate_group_constraints(module_name, replicated_modules)

    content = '\n'.join(constraints)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

    return content


def _generate_distance_constraints(
    module_name: str,
    replicated_modules: List[str],
    distance: int
) -> List[str]:
    """生成距离约束。

    Args:
        module_name: 顶层模块名。
        replicated_modules: 复制模块列表。
        distance: 最小距离。

    Returns:
        约束列表。
    """
    constraints = [
        f'# Placement constraints for {module_name}',
        f'# Minimum distance between TMR replicas: {distance} um',
        '',
        '# =======================================================',
        '# TMR replica distance constraints',
        '# =======================================================',
        '',
    ]

    for i, mod in enumerate(replicated_modules):
        for j in range(i + 1, len(replicated_modules)):
            mod2 = replicated_modules[j]
            constraints.append(
                f'set_min_distance -from [get_cells *{mod}*] -to [get_cells *{mod2}*] {distance}'
            )

    constraints.append('')
    return constraints


def _generate_region_constraints(
    module_name: str,
    replicated_modules: List[str]
) -> List[str]:
    """生成区域约束。

    Args:
        module_name: 顶层模块名。
        replicated_modules: 复制模块列表。

    Returns:
        约束列表。
    """
    regions = ['TOP_LEFT', 'TOP_RIGHT', 'BOTTOM_LEFT']

    constraints = [
        f'# Placement constraints for {module_name}',
        '# Assign TMR replicas to different regions',
        '',
        '# =======================================================',
        '# TMR region constraints',
        '# =======================================================',
        '',
    ]

    for i, mod in enumerate(replicated_modules):
        if i < len(regions):
            region = regions[i]
            constraints.append(
                f'place_cell [get_cells *{mod}*] {region}'
            )

    constraints.append('')
    return constraints


def _generate_group_constraints(
    module_name: str,
    replicated_modules: List[str]
) -> List[str]:
    """生成分组约束。

    Args:
        module_name: 顶层模块名。
        replicated_modules: 复制模块列表。

    Returns:
        约束列表。
    """
    constraints = [
        f'# Placement constraints for {module_name}',
        '# TMR grouping constraints',
        '',
        '# =======================================================',
        '# TMR group constraints',
        '# =======================================================',
        '',
    ]

    constraints.append(
        f'create_group tmr_group_{module_name} [get_cells {{"{' '.join([f'*{m}*' for m in replicated_modules])}"}}]'
    )
    constraints.append(
        f'set_group_constraint -group tmr_group_{module_name} -distance 100'
    )

    constraints.append('')
    return constraints


def generate_floorplan_constraints(
    module_name: str,
    width: int = 1000,
    height: int = 1000,
    core_offset_x: int = 100,
    core_offset_y: int = 100,
    output_path: Optional[str] = None
) -> str:
    """生成Floorplan约束。

    Args:
        module_name: 顶层模块名。
        width: 芯片宽度。
        height: 芯片高度。
        core_offset_x: 核心区域X偏移。
        core_offset_y: 核心区域Y偏移。
        output_path: 输出文件路径（可选）。

    Returns:
        约束文件内容。
    """
    constraints = [
        f'# Floorplan constraints for {module_name}',
        '',
        '# =======================================================',
        '# Chip dimensions',
        '# =======================================================',
        f'set_die_area 0 0 {width} {height}',
        f'set_core_area {core_offset_x} {core_offset_y} {width - core_offset_x} {height - core_offset_y}',
        '',
        '# =======================================================',
        '# TMR region definitions',
        '# =======================================================',
        f'create_floorplan_region tmr_region_A {core_offset_x} {height//2} {width//3 - core_offset_x} {height//2 - core_offset_y}',
        f'create_floorplan_region tmr_region_B {width//3} {height//2} {width//3} {height//2 - core_offset_y}',
        f'create_floorplan_region tmr_region_C {2*width//3} {height//2} {width//3 - core_offset_x} {height//2 - core_offset_y}',
        '',
    ]

    content = '\n'.join(constraints)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

    return content


def generate_tmr_placement_script(
    module_name: str,
    replicated_modules: List[str],
    output_path: Optional[str] = None
) -> str:
    """生成完整的TMR布局脚本。

    Args:
        module_name: 顶层模块名。
        replicated_modules: 复制模块列表。
        output_path: 输出文件路径（可选）。

    Returns:
        脚本内容。
    """
    script = [
        f'# TMR Placement Script for {module_name}',
        '# Generated by placement_constraints.py',
        '',
        '# =======================================================',
        '# Step 1: Floorplan',
        '# =======================================================',
        'create_floorplan',
        '',
        '# =======================================================',
        '# Step 2: TMR Region Assignment',
        '# =======================================================',
        '',
    ]

    regions = ['tmr_region_A', 'tmr_region_B', 'tmr_region_C']

    for i, mod in enumerate(replicated_modules):
        if i < len(regions):
            region = regions[i]
            script.append(
                f'assign_cells_to_region [get_cells *{mod}*] {region}'
            )

    script.extend([
        '',
        '# =======================================================',
        '# Step 3: Distance Constraints',
        '# =======================================================',
        '',
    ])

    for i, mod in enumerate(replicated_modules):
        for j in range(i + 1, len(replicated_modules)):
            mod2 = replicated_modules[j]
            script.append(
                f'set_min_distance -from [get_cells *{mod}*] -to [get_cells *{mod2}*] 100'
            )

    script.extend([
        '',
        '# =======================================================',
        '# Step 4: Placement',
        '# =======================================================',
        'place_design',
        '',
        '# =======================================================',
        '# Step 5: Verify Constraints',
        '# =======================================================',
        'check_placement',
        'report_placement_constraints',
    ])

    content = '\n'.join(script)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

    return content


def generate_placement_report(
    module_name: str,
    replicated_modules: List[str],
    constraint_type: str = 'distance'
) -> str:
    """生成布局约束报告。

    Args:
        module_name: 顶层模块名。
        replicated_modules: 复制模块列表。
        constraint_type: 约束类型。

    Returns:
        报告文本。
    """
    report_lines = [
        "=" * 70,
        "布局约束报告",
        "=" * 70,
        ""
    ]

    report_lines.append(f"模块名称: {module_name}")
    report_lines.append(f"复制模块数量: {len(replicated_modules)}")
    report_lines.append(f"约束类型: {constraint_type}")
    report_lines.append("")

    report_lines.append("复制模块列表:")
    for mod in replicated_modules:
        report_lines.append(f"  - {mod}")

    report_lines.append("")

    if constraint_type == 'distance':
        report_lines.append("距离约束:")
        for i, mod in enumerate(replicated_modules):
            for j in range(i + 1, len(replicated_modules)):
                mod2 = replicated_modules[j]
                report_lines.append(f"  {mod} <-> {mod2}: 最小100um")
    elif constraint_type == 'region':
        regions = ['TOP_LEFT', 'TOP_RIGHT', 'BOTTOM_LEFT']
        report_lines.append("区域约束:")
        for i, mod in enumerate(replicated_modules):
            if i < len(regions):
                report_lines.append(f"  {mod} -> {regions[i]}")
    elif constraint_type == 'group':
        report_lines.append("分组约束:")
        report_lines.append(f"  所有模块归入 tmr_group_{module_name}")

    report_lines.append("")
    report_lines.append("=" * 70)

    return '\n'.join(report_lines)