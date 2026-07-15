#!/usr/bin/env python3
"""
SVA 断言回归测试运行器
集成到 CI/CD 流水线的 SVA 断言自动测试 + 覆盖率报告生成

用法:
  python run_sva_regression.py              # 运行全部 SVA 测试
  python run_sva_regression.py --compat      # 仅运行 iverilog 兼容版
  python run_sva_regression.py --report      # 仅生成覆盖率报告

依赖:
  Icarus Verilog 12.0+ (iverilog/vvp)
  Python 3.8+
"""

import sys
import os
import re
import subprocess
import json
import time

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(os.path.dirname(SIM_DIR), 'reports')
IVERILOG = r'D:\software\pango\iverilog\bin\iverilog.exe'
VVP = r'D:\software\pango\iverilog\bin\vvp.exe'

# =============================================================
# 辅助函数
# =============================================================

def find_tool(tool_name, default_path):
    """查找工具路径"""
    if os.path.exists(default_path):
        return default_path
    # 尝试从 PATH 查找
    for path in os.environ.get('PATH', '').split(os.pathsep):
        exe = os.path.join(path, tool_name)
        if os.path.exists(exe):
            return exe
        exe = os.path.join(path, f'{tool_name}.exe')
        if os.path.exists(exe):
            return exe
    return default_path

def print_header(title):
    """打印格式化标题"""
    print(f'\n{"=" * 72}')
    print(f'  {title}')
    print(f'{"=" * 72}')

def print_pass(msg):
    print(f'  ✅ {msg}')

def print_fail(msg):
    print(f'  ❌ {msg}')

def print_info(msg):
    print(f'  ℹ️  {msg}')

# =============================================================
# 测试运行器
# =============================================================

def compile_and_run(compile_cmd, run_cmd, test_name, expected_sva_errors=0):
    """编译并运行仿真，返回 (成功, 输出文本, SVA错误计数)"""
    print(f'\n  [{test_name}] 编译...')
    compile_result = subprocess.run(compile_cmd, capture_output=True, text=True, shell=True)
    
    if compile_result.returncode != 0:
        print_fail(f'编译失败 (exit={compile_result.returncode})')
        for line in compile_result.stderr.split('\n'):
            if 'error' in line.lower():
                print(f'       {line.strip()}')
        return False, '', 0
    
    print(f'  [{test_name}] 运行仿真...')
    run_result = subprocess.run(run_cmd, capture_output=True, text=True, shell=True)
    output = run_result.stdout + run_result.stderr
    
    # 统计 SVA 错误行数
    sva_errors = len(re.findall(r'\[SVA-ERROR\]', output))
    
    # 检查测试结果
    tests_passed = len(re.findall(r'PASS:', output))
    tests_failed = len(re.findall(r'FAIL:', output))
    
    print(f'     [SVA-ERROR] 触发数: {sva_errors}')
    print(f'     测试通过: {tests_passed} | 失败: {tests_failed}')
    
    return True, output, sva_errors


def test_sva_compat():
    """Test 1: iverilog 兼容版 SVA 断言测试"""
    print_header('SVA 断言兼容版测试 (sva_voter_monitor_compat.v)')
    
    vvp_file = os.path.join(SIM_DIR, '_sva_compat_sim.vvp')
    tb_file = 'tb_sva_voter_compat.v'
    src_file = 'sva_voter_monitor_compat.v'
    
    compile_cmd = f'cd /d "{SIM_DIR}" && "{find_tool("iverilog", IVERILOG)}" -o "{vvp_file}" "{src_file}" "{tb_file}"'
    run_cmd = f'cd /d "{SIM_DIR}" && "{find_tool("vvp", VVP)}" "{vvp_file}"'
    
    success, output, sva_errors = compile_and_run(compile_cmd, run_cmd, 'compat')
    
    if success and 'PASS' in output:
        print_pass(f'兼容版 SVA 测试通过 ({sva_errors} 条断言触发)')
        return True, output
    else:
        print_fail('兼容版 SVA 测试失败')
        return False, output


def test_sva_coverage():
    """Test 2: SVA 覆盖率分析 — 统计所有通道触发情况"""
    print_header('SVA 覆盖率分析')
    
    # 收集 coverage 数据
    results = {
        'ch-0': 0, 'ch-1': 0, 'ch-2': 0,
        'ch-3': 0, 'ch-4': 0, 'ch-5': 0,
        'summary': 0
    }
    
    # 运行兼容版测试收集覆盖率
    vvp_file = os.path.join(SIM_DIR, '_sva_coverage_sim.vvp')
    compile_cmd = f'cd /d "{SIM_DIR}" && "{find_tool("iverilog", IVERILOG)}" -o "{vvp_file}" sva_voter_monitor_compat.v tb_sva_voter_compat.v'
    run_cmd = f'cd /d "{SIM_DIR}" && "{find_tool("vvp", VVP)}" "{vvp_file}"'
    
    _, output, _ = compile_and_run(compile_cmd, run_cmd, 'coverage')
    
    for ch in results:
        pattern = rf'\[SVA-ERROR\]\[{re.escape(ch)}\]'
        results[ch] = len(re.findall(pattern, output))
    
    results['summary'] = len(re.findall(r'\[SVA-ERROR\]', output))
    
    print(f'\n  通道触发统计:')
    for ch, count in results.items():
        if ch == 'summary':
            print(f'    [TOTAL] [SVA-ERROR]: {count} 次')
        else:
            status = '✅' if count > 0 else '⚠️'
            print(f'    {status} {ch}: {count} 次触发')
    
    # 生成覆盖率 JSON
    os.makedirs(REPORT_DIR, exist_ok=True)
    coverage_report = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'tool': 'Icarus Verilog + sva_voter_monitor_compat',
        'coverage': results,
        'channels_covered': sum(1 for k, v in results.items() if k != 'summary' and v > 0),
        'total_channels': 6,
        'coverage_rate': f'{sum(1 for k, v in results.items() if k != "summary" and v > 0) / 6 * 100:.1f}%'
    }
    
    report_file = os.path.join(REPORT_DIR, 'sva_coverage_report.json')
    with open(report_file, 'w') as f:
        json.dump(coverage_report, f, indent=2)
    print(f'\n  覆盖率报告已保存: {report_file}')
    
    all_covered = all(results[ch] > 0 for ch in ['ch-0', 'ch-1', 'ch-2', 'ch-3', 'ch-4', 'ch-5'])
    return all_covered, coverage_report


def test_sva_integration():
    """Test 3: 验证 cpu_core_tmr.sv 中的 SVA 断言完整性"""
    print_header('SVA 集成完整性检查')
    
    tmr_file = os.path.join(os.path.dirname(SIM_DIR), 'test_mock_data', 'cpu_core_tmr.sv')
    
    if not os.path.exists(tmr_file):
        print_fail(f'找不到 cpu_core_tmr.sv: {tmr_file}')
        return False
    
    with open(tmr_file, 'r') as f:
        content = f.read()
    
    # 检查 6 个通道是否都包含
    channels = {
        'ch-0': r'mmio_in_1\.ready\s*!==\s*mmio_in_2\.ready',
        'ch-1': r'mmio_out_1\.boot_valid\s*!==\s*mmio_out_2\.boot_valid',
        'ch-2': r'mmio_out_1\.exit_valid\s*!==\s*mmio_out_2\.exit_valid',
        'ch-3': r'mmio_out_1\.exit_code\s*!==\s*mmio_out_2\.exit_code',
        'ch-4': r'mmio_out_1\.print_valid\s*!==\s*mmio_out_2\.print_valid',
        'ch-5': r'mmio_out_1\.print_data\s*!==\s*mmio_out_2\.print_data',
    }
    
    all_ok = True
    for ch, pattern in channels.items():
        if re.search(pattern, content):
            print_pass(f'{ch}: SVA 断言已集成')
        else:
            print_fail(f'{ch}: SVA 断言缺失!')
            all_ok = False
    
    # 检查差异位掩码 (cpu_core_tmr.sv 使用 mmio_out_1.exit_code 格式)
    if re.search(r'mmio_out_1\.exit_code\s*\^\s*mmio_out_2\.exit_code', content):
        print_pass('ch-3: 差异位掩码 (XOR) 已集成')
    else:
        print_fail('ch-3: 差异位掩码缺失!')
        all_ok = False
    
    if re.search(r'mmio_out_1\.print_data\s*\^\s*mmio_out_2\.print_data', content):
        print_pass('ch-5: 差异位掩码 (XOR) 已集成')
    else:
        print_fail('ch-5: 差异位掩码缺失!')
        all_ok = False
    
    # 检查多比特翻转防御
    if re.search(r'hamming_distance|error_count_ch|HAMMING|multi_bit', content):
        print_pass('多比特翻转防御机制已启用')
    else:
        print_info('多比特翻转防御机制待添加')
    
    return all_ok


# =============================================================
# 主入口
# =============================================================

def main():
    print(f'SVA 断言回归测试运行器')
    print(f'  时间: {time.strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'  Sim 目录: {SIM_DIR}')
    
    run_compat = '--compat' in sys.argv or len(sys.argv) == 1
    run_report = '--report' in sys.argv or len(sys.argv) == 1
    
    results = {}
    
    # Test 1: 兼容版 SVA 测试
    if run_compat:
        compat_ok, output = test_sva_compat()
        results['sva_compat_test'] = compat_ok
        
        # 打印前 20 行仿真摘要
        if output:
            summary_lines = [l for l in output.split('\n') if 'PASS' in l or 'SVA-ERROR' in l or 'Test' in l or '验证完成' in l]
            print(f'\n  仿真输出摘要:')
            for line in summary_lines[:20]:
                print(f'    {line}')
    
    # Test 2: 覆盖率分析
    if run_report:
        cov_ok, coverage = test_sva_coverage()
        results['sva_coverage'] = cov_ok
    
    # Test 3: 集成完整性检查
    integ_ok = test_sva_integration()
    results['sva_integration'] = integ_ok
    
    # 保存结果
    os.makedirs(REPORT_DIR, exist_ok=True)
    result_data = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'results': results,
        'summary': f'{sum(1 for v in results.values() if v)}/{len(results)} passed'
    }
    
    result_file = os.path.join(REPORT_DIR, 'sva_regression_result.json')
    with open(result_file, 'w') as f:
        json.dump(result_data, f, indent=2)
    print(f'\n  结果已保存: {result_file}')
    
    # 汇总
    print_header('SVA 回归测试汇总')
    all_pass = True
    for name, status in results.items():
        icon = '✅' if status else '❌'
        print(f'  {icon} {name}: {"通过" if status else "失败"}')
        if not status:
            all_pass = False
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f'\n  总计: {passed}/{total} 通过')
    sys.exit(0 if all_pass else 1)


if __name__ == '__main__':
    main()
