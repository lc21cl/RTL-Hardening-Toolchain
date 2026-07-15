#!/usr/bin/env python3
"""
_test_complex_repair.py — 验证 SyntaxFixer 新规则

测试 test_complex_repair.v 中的所有新增修复规则:
  [1] inout_without_direction    — inout 端口声明
  [2] missing_endgenerate        — generate 块缺失 endgenerate
  [3] missing_semicolon          — 缺失分号
  [4] missing_parameter_default  — 参数无默认值
  [5] missing_seq_sensitivity_or — 敏感列表缺少 or
  [6] missing_case_default       — case 语句缺 default
  [7] missing_end_before_endmodule — 通过 _fix_unmatched_begin 处理
"""

import sys
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

from auto_repair import SyntaxFixer
from logger import logger

def main():
    logger.section("Complex Verilog Repair Test")
    
    # 读取测试文件
    test_file = os.path.join(_SCRIPT_DIR, "test_complex_repair.v")
    with open(test_file, "r", encoding="utf-8") as f:
        original = f.read()
    
    logger.print(f"  Original file: {test_file}")
    logger.print(f"  Original size: {len(original)} chars, {len(original.splitlines())} lines")
    
    # 初始化 SyntaxFixer
    fixer = SyntaxFixer()
    
    # 查看注册的所有 FIX_PATTERNS
    logger.sub_section("Registered FIX_PATTERNS")
    for priority, name, search, replace in sorted(fixer._FIX_PATTERNS, key=lambda x: -x[0]):
        logger.print(f"  P={priority:3d}  {name}")
        if search != '__reserved_never_match__':
            logger.print(f"          search={search[:70]}")
    
    # 执行修复
    logger.sub_section("Applying Fixes")
    errors = [
        "syntax error, unexpected TOK_ASSIGN, expecting ';'",
        "port direction missing",
    ]
    fixed = fixer.fix(original, errors)
    
    # 保存修复结果
    output_file = os.path.join(_SCRIPT_DIR, "test_complex_repair_fixed.v")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(fixed)
    
    fixed_lines = fixed.splitlines()
    orig_lines = original.splitlines()
    
    logger.sub_section("Fix Results")
    logger.print(f"  Output file: {output_file}")
    logger.print(f"  Lines: {len(orig_lines)} → {len(fixed_lines)}")
    
    # 检查各规则是否生效
    checks = [
        ("inout_without_direction",    "inout wire" in fixed,                  "inout 端口声明"),
        ("missing_endgenerate",        fixed.count("endgenerate") >= 1,         "endgenerate 关键字"),
        ("missing_semicolon_decl",     "debug_bus;" in fixed,                   "wire 声明分号"),
        ("missing_semicolon_assign",   "assign debug_bus" in fixed,             "assign 语句"),
        ("missing_parameter_default",  "DATA_WIDTH = 0" in fixed,               "参数默认值"),
        ("missing_seq_sensitivity_or", "posedge clk or negedge rst_n" in fixed, "敏感列表 or"),
        ("missing_case_default",       "default : ;" in fixed.lower(),          "case default"),
    ]
    
    logger.sub_section("Rule Verification")
    all_passed = True
    for rule_name, condition, description in checks:
        status = "✅" if condition else "❌"
        if not condition:
            all_passed = False
        logger.print(f"  [{status}] {rule_name:40s} ({description})")
    
    # 显示差异
    logger.sub_section("Line Differences (changed lines)")
    changes = 0
    for i, (a, b) in enumerate(zip(orig_lines, fixed_lines)):
        if a != b:
            logger.print(f"  L{i+1:3d}: {repr(a)[:60]}")
            logger.print(f"         → {repr(b)[:60]}")
            changes += 1
    if len(orig_lines) != len(fixed_lines):
        logger.print(f"  (Line count differs: {len(orig_lines)} → {len(fixed_lines)})")
    if changes == 0:
        logger.print("  (No line-level changes detected)")
    
    logger.print(f"\n  Total changes: {changes}")
    logger.print(f"  Overall: {'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'}")

if __name__ == "__main__":
    main()
