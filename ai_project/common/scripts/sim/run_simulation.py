#!/usr/bin/env python3
"""
仿真回归测试运行器
自动查找 iverilog, 编译并运行所有/指定 testbench, 生成覆盖率和报告

用法:
  python run_simulation.py --all              # 运行全部测试
  python run_simulation.py --suite cnt_comp   # 运行指定套件 (模糊匹配)
  python run_simulation.py --json             # 仅输出 JSON 报告
  python run_simulation.py --output ./my_report  # 指定输出目录
  python run_simulation.py --verbose          # 显示详细输出

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
import argparse

# =============================================================
# 路径配置
# =============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # ai_project/common/scripts -> ai_project/common
REPORT_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'reports')
TEST_MOCK_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'test_mock_data')

# 默认 iverilog 路径 (与 run_sva_regression.py 保持一致)
IVERILOG_DEFAULT = r'D:\software\pango\iverilog\bin\iverilog.exe'
VVP_DEFAULT = r'D:\software\pango\iverilog\bin\vvp.exe'

# =============================================================
# 测试套件注册表
# =============================================================

TEST_SUITES = [
    {
        'name': 'cnt_comp 基本功能',
        'file': 'tb_cnt_comp.v',
        'src': 'cnt_comp_template.v',
        'expected_pass': 6,
        'tests': ['Reset', 'Up count', 'Down count', 'Mod wrap', 'SEU detect', 'False-alarm free']
    },
    {
        'name': 'cnt_comp 故障注入',
        'file': 'tb_cnt_comp_fault.v',
        'src': 'cnt_comp_template.v',
        'expected_pass': 9,
        'tests': ['Reset', 'Normal count', 'SEU on counter', 'SEU on shadow',
                   'Error counter', 'Recovery', 'False-alarm free',
                   'Error counter saturation', 'Dual bit-flip']
    },
    {
        'name': '奇偶校验',
        'file': 'tb_parity.v',
        'src': 'parity_template.v',
        'expected_pass': 268,
        'tests': ['Reset', 'Write/Read', 'Single-bit SEU', 'Recovery',
                   'Parity bit flip', 'Multi-bit SEU', '2-bit SEU limitation',
                   'False-alarm free', 'Error counter', 'All 256 patterns']
    },
    {
        'name': 'DICE',
        'file': 'tb_dice.v',
        'src': 'dice_template.v',
        'expected_pass': 6,
        'tests': ['Reset', 'Write/Read', 'Single node SEU', 'Dual node SEU',
                   'Stability', 'Error counter']
    },
    {
        'name': 'ECC (SECDED)',
        'file': 'tb_ecc.v',
        'src': 'ecc_template.v',
        'expected_pass': 265,
        'tests': ['Reset', 'Write/Read', 'Single-bit SEU', 'Recovery',
                   'Double-bit SEU', 'Recovery2', 'False-alarm free',
                   'All 256 patterns', 'Parity-bit SEU']
    },
    {
        'name': 'ECC 加固混合设计 (新)',
        'file': 'tb_mixed_design_ecc.v',
        'src': 'mixed_design_ecc.v',
        'expected_pass': 40,
        'tests': ['Reset', 'Basic R/W', 'Accumulator', 'Single SEU acc',
                   'Single SEU tmp', 'Double SEU', 'Error counter',
                   'Recovery', '50-cycle free']
    }
]

# =============================================================
# 覆盖率类型分类
# =============================================================

COVERAGE_CLASSIFICATION = {
    'cnt_comp 基本功能': {
        'type': 'functional',
        'weight': 'core',
        'signals_tested': ['up_cnt', 'down_cnt', 'mod_cnt', 'up_err', 'down_err', 'mod_err']
    },
    'cnt_comp 故障注入': {
        'type': 'fault-injection',
        'weight': 'hardening',
        'signals_tested': ['counter', 'shadow', 'err_flag', 'err_cnt', 'force_release']
    },
    '奇偶校验': {
        'type': 'mixed',
        'weight': 'core+exhaustive',
        'signals_tested': ['q', 'err', 'ecnt', 'code_word', 'parity_bits']
    },
    'DICE': {
        'type': 'fault-injection',
        'weight': 'hardening',
        'signals_tested': ['dice_out', 'node_a', 'node_b', 'node_c', 'node_d', 'err_flag']
    },
    'ECC (SECDED)': {
        'type': 'mixed',
        'weight': 'core+exhaustive',
        'signals_tested': ['q', 'err_flag', 'corrected', 'code_word', 'syndrome']
    },
    'ECC 加固混合设计 (新)': {
        'type': 'functional',
        'weight': 'core',
        'signals_tested': ['result', 'done', 'acc_reg', 'tmp_reg', 'error_flag', 'err_count']
    }
}

# =============================================================
# 辅助函数
# =============================================================

def find_tool(tool_name, default_path):
    """查找工具路径, 先检查默认路径, 再搜索 PATH"""
    if os.path.exists(default_path):
        return default_path
    for path in os.environ.get('PATH', '').split(os.pathsep):
        exe = os.path.join(path, tool_name)
        if os.path.exists(exe):
            return exe
        exe = os.path.join(path, f'{tool_name}.exe')
        if os.path.exists(exe):
            return exe
    return default_path


def print_header(title):
    print(f'\n{"=" * 72}')
    print(f'  {title}')
    print(f'{"=" * 72}')


def print_pass(msg):
    print(f'  ✅ {msg}')


def print_fail(msg):
    print(f'  ❌ {msg}')


def print_warn(msg):
    print(f'  ⚠️  {msg}')


def print_info(msg):
    print(f'  ℹ️  {msg}')


def parse_pass_fail(output):
    """从仿真输出中解析 PASS/FAIL 计数"""
    pass_count = 0
    fail_count = 0

    # 匹配: PASS: ... 或 FAIL: ... 格式
    pass_lines = re.findall(r'\bPASS:\s*(.*)', output)
    fail_lines = re.findall(r'\bFAIL:\s*(.*)', output)

    pass_count = len(pass_lines)
    fail_count = len(fail_lines)

    # 尝试从汇总行解析 (如 "cnt_comp Tests: 6 PASS, 0 FAIL")
    summary_match = re.search(r'(\d+)\s*PASS\s*,\s*(\d+)\s*FAIL', output, re.IGNORECASE)
    if summary_match:
        sp = int(summary_match.group(1))
        sf = int(summary_match.group(2))
        # 如果直接匹配到的更多, 优先用直接匹配; 否则用汇总行
        if sp > pass_count:
            pass_count = sp
        if sf > fail_count:
            fail_count = sf

    # 另一种格式: "总测试数: 40" / "通过 (PASS): 40" / "失败 (FAIL): 0"
    if pass_count == 0 and fail_count == 0:
        total_m = re.search(r'总测试数:\s*(\d+)', output)
        pass_m = re.search(r'通过\s*\(PASS\).*?(\d+)', output)
        fail_m = re.search(r'失败\s*\(FAIL\).*?(\d+)', output)
        if pass_m and fail_m:
            pass_count = int(pass_m.group(1))
            fail_count = int(fail_m.group(1))

    return pass_count, fail_count


def classify_coverage_type(suite_name):
    """根据套件名分类覆盖率类型"""
    info = COVERAGE_CLASSIFICATION.get(suite_name, {})
    ctype = info.get('type', 'unknown')

    if ctype == 'functional':
        return 'functional'
    elif ctype == 'fault-injection':
        return 'fault-injection'
    elif ctype == 'mixed':
        # mixed 包含 exhaustive (穷举) 和 stress (压力)
        weight = info.get('weight', '')
        if 'exhaustive' in weight:
            return 'exhaustive'
        return 'stress'
    return 'functional'


def get_signals_tested(suite_name):
    """获取套件测试的信号列表"""
    info = COVERAGE_CLASSIFICATION.get(suite_name, {})
    return info.get('signals_tested', [])


# =============================================================
# 仿真运行器
# =============================================================

def run_testbench(test_dir, tb_file, src_files, timeout=120, verbose=False):
    """
    运行单个 testbench

    参数:
        test_dir: 测试文件所在目录
        tb_file:  testbench 文件名
        src_files: 源文件列表 (相对于 test_dir)
        timeout:   超时秒数
        verbose:   是否显示详细输出

    返回:
        (success, output, pass_count, fail_count, error_msg)
    """
    iverilog = find_tool('iverilog.exe', IVERILOG_DEFAULT)
    vvp = find_tool('vvp.exe', VVP_DEFAULT)

    tb_path = os.path.join(test_dir, tb_file)
    if not os.path.exists(tb_path):
        return False, '', 0, 0, f'找不到 testbench: {tb_path}'

    # 构建源文件列表
    src_paths = []
    for src in src_files:
        sp = os.path.join(test_dir, src)
        if os.path.exists(sp):
            src_paths.append(sp)
        else:
            # 也尝试直接用文件名 (可能由 `include 解析)
            src_paths.append(src)

    # 编译
    vvp_output = os.path.join(test_dir, f'_{os.path.splitext(tb_file)[0]}.vvp')
    src_names = ' '.join(
        '"' + (os.path.basename(s) if os.path.exists(s) else s) + '"'
        for s in src_paths
    )
    compile_cmd = (
        'cd /d "' + test_dir + '" && "' + iverilog + '" -g2005-sv -o "' + vvp_output + '" '
        '"' + tb_file + '" ' + src_names
    )

    if verbose:
        print(f'    编译命令: {compile_cmd}')

    try:
        compile_result = subprocess.run(
            compile_cmd, capture_output=True, text=True, shell=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return False, '', 0, 0, '编译超时'

    if compile_result.returncode != 0:
        # 提取关键错误信息
        error_lines = []
        for line in compile_result.stderr.split('\n'):
            if 'error' in line.lower():
                error_lines.append(line.strip())
        error_msg = '\n'.join(error_lines[:10]) if error_lines else compile_result.stderr[:500]
        return False, compile_result.stderr, 0, 0, f'编译失败 (exit={compile_result.returncode}): {error_msg}'

    # 运行仿真
    run_cmd = f'cd /d "{test_dir}" && "{vvp}" "{vvp_output}"'

    if verbose:
        print(f'    运行命令: {run_cmd}')

    try:
        run_result = subprocess.run(
            run_cmd, capture_output=True, text=True, shell=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return False, '', 0, 0, '仿真运行超时'

    output = run_result.stdout + '\n' + run_result.stderr

    # 解析 PASS/FAIL
    pass_count, fail_count = parse_pass_fail(output)

    success = run_result.returncode == 0 or (pass_count + fail_count > 0)

    # 累计 total 测试行
    error_msg = None
    if run_result.returncode != 0 and pass_count == 0 and fail_count == 0:
        error_msg = f'仿真异常退出 (exit={run_result.returncode})'

    # 清理临时文件
    try:
        if os.path.exists(vvp_output):
            os.remove(vvp_output)
    except (OSError, PermissionError):
        pass

    return success, output, pass_count, fail_count, error_msg


# =============================================================
# 覆盖率统计
# =============================================================

def compute_coverage(results):
    """
    根据所有套件结果计算覆盖率统计

    返回:
        {
            'by_component': [...],
            'by_type': {...},
            'matrix': {...},
            'pie_data': {...}
        }
    """
    by_component = []
    by_type = {
        'functional': {'total': 0, 'passed': 0, 'suites': 0},
        'fault-injection': {'total': 0, 'passed': 0, 'suites': 0},
        'stress': {'total': 0, 'passed': 0, 'suites': 0},
        'exhaustive': {'total': 0, 'passed': 0, 'suites': 0},
    }

    matrix_rows = []

    for r in results:
        suite_name = r['name']
        ctype = classify_coverage_type(suite_name)
        signals = get_signals_tested(suite_name)

        total = r['pass'] + r['fail']
        passed = r['pass']

        # 按组件
        by_component.append({
            'name': suite_name,
            'total': total,
            'passed': passed,
            'failed': r['fail'],
            'pass_rate': (passed / total * 100) if total > 0 else 0,
            'expected_pass': r['expected_pass'],
            'status': 'passed' if r['fail'] == 0 else 'failed'
        })

        # 按类型
        if ctype in by_type:
            by_type[ctype]['total'] += total
            by_type[ctype]['passed'] += passed
            by_type[ctype]['suites'] += 1

        # 覆盖率矩阵行
        for sig in signals:
            matrix_rows.append({
                'suite': suite_name,
                'signal': sig,
                'tested': True,
                'passed': r['fail'] == 0
            })

    # 计算类型覆盖率百分比
    for t in by_type:
        total = by_type[t]['total']
        by_type[t]['rate'] = (by_type[t]['passed'] / total * 100) if total > 0 else 0

    # 构建矩阵
    all_signals = sorted(set(row['signal'] for row in matrix_rows))
    all_suites = [r['name'] for r in results]

    matrix = {
        'suites': all_suites,
        'signals': all_signals,
        'cells': {}
    }
    for s in all_suites:
        sigs_for_suite = [row for row in matrix_rows if row['suite'] == s]
        matrix['cells'][s] = {
            row['signal']: {'tested': row['tested'], 'passed': row['passed']}
            for row in sigs_for_suite
        }

    # 饼图数据
    pie_data = {}
    for t, data in by_type.items():
        if data['total'] > 0:
            pie_data[t] = data['total']

    return {
        'by_component': by_component,
        'by_type': by_type,
        'matrix': matrix,
        'pie_data': pie_data
    }


def format_pie_chart(pie_data, width=30):
    """生成 ASCII 饼图"""
    if not pie_data:
        return '  (无数据)'

    total = sum(pie_data.values())
    if total == 0:
        return '  (无数据)'

    # 饼图字符
    chars = ['█', '▓', '▒', '░', '■', '●', '◆', '▲', '▼', '◄']
    colors = {
        'functional': '功能',
        'fault-injection': '故障注入',
        'stress': '压力',
        'exhaustive': '穷举',
    }

    lines = [f'  测试分布 (总计 {total} 项):']
    sorted_items = sorted(pie_data.items(), key=lambda x: -x[1])

    for i, (key, val) in enumerate(sorted_items):
        pct = val / total * 100
        bar_len = max(1, int(pct / 100 * width))
        bar = chars[i % len(chars)] * bar_len
        label = colors.get(key, key)
        lines.append(f'  {bar} {label}: {val} ({pct:.1f}%)')

    return '\n'.join(lines)


def format_coverage_matrix(matrix_data):
    """生成 ASCII 覆盖率矩阵"""
    suites = matrix_data.get('suites', [])
    signals = matrix_data.get('signals', [])
    cells = matrix_data.get('cells', {})

    if not suites or not signals:
        return '  (无覆盖率数据)'

    lines = []
    lines.append(f'  {"测试套件":<30} | ' + ' '.join(f'{s:<12}' for s in signals))
    lines.append('  ' + '-' * (32 + 14 * len(signals)))

    for suite in suites:
        row = f'  {suite:<30} | '
        for sig in signals:
            cell = cells.get(suite, {}).get(sig, {})
            if cell.get('tested'):
                if cell.get('passed'):
                    row += '✅           '
                else:
                    row += '❌           '
            else:
                row += '—            '
        lines.append(row)

    return '\n'.join(lines)


# =============================================================
# 报告生成
# =============================================================

def generate_markdown_report(results, coverage, elapsed, output_dir):
    """生成 Markdown 格式的测试报告"""
    total_pass = sum(r['pass'] for r in results)
    total_fail = sum(r['fail'] for r in results)
    total_tests = total_pass + total_fail
    total_suites = len(results)
    passed_suites = sum(1 for r in results if r['fail'] == 0)
    overall_rate = (total_pass / total_tests * 100) if total_tests > 0 else 0

    lines = []
    lines.append('# 仿真回归测试报告')
    lines.append('')
    lines.append('## 概述')
    lines.append('')
    lines.append(f'- 测试时间: {time.strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append(f'- 运行组件: {passed_suites}/{total_suites}')
    lines.append(f'- 总通过: {total_pass}/{total_tests}')
    lines.append(f'- 通过率: {overall_rate:.2f}%')
    lines.append(f'- 耗时: {elapsed:.1f} 秒')
    lines.append('')

    # 逐组件结果
    lines.append('## 逐组件结果')
    lines.append('')
    lines.append('| 组件 | 测试数 | 通过 | 失败 | 通过率 | 状态 |')
    lines.append('|:-----|:------:|:----:|:----:|:------:|:----:|')

    for r in results:
        total = r['pass'] + r['fail']
        rate = (r['pass'] / total * 100) if total > 0 else 0
        status_icon = '✅' if r['fail'] == 0 else '❌'
        lines.append(f'| {r["name"]} | {total} | {r["pass"]} | {r["fail"]} | {rate:.1f}% | {status_icon} |')

    lines.append('')

    # 覆盖率分析
    lines.append('## 覆盖率分析')
    lines.append('')
    by_type = coverage['by_type']
    for ctype, data in by_type.items():
        if data['total'] > 0:
            type_label = {'functional': '功能测试', 'fault-injection': '故障注入测试',
                          'stress': '压力测试', 'exhaustive': '穷举测试'}.get(ctype, ctype)
            lines.append(f'- **{type_label}覆盖率**: {data["passed"]}/{data["total"]} ({data["rate"]:.1f}%) '
                         f'({data["suites"]} 套件)')
    lines.append('')

    # 逐组件深度分析
    lines.append('## 逐组件深度分析')
    lines.append('')
    for r in results:
        total = r['pass'] + r['fail']
        expected = r['expected_pass']
        rate = (r['pass'] / total * 100) if total > 0 else 0
        status = '通过' if r['fail'] == 0 else f'失败 ({r["fail"]} 项未通过)'
        lines.append(f'### {r["name"]}')
        lines.append(f'- 预期通过: {expected}')
        lines.append(f'- 实际通过: {r["pass"]}')
        lines.append(f'- 失败: {r["fail"]}')
        lines.append(f'- 通过率: {rate:.1f}%')
        lines.append(f'- 状态: {status}')
        lines.append('')

    # 覆盖率矩阵
    lines.append('## 覆盖率矩阵 (ASCII)')
    lines.append('')
    lines.append('```')
    lines.append(format_coverage_matrix(coverage['matrix']))
    lines.append('```')
    lines.append('')

    # 饼图
    lines.append('## 测试分布图 (ASCII)')
    lines.append('')
    lines.append('```')
    lines.append(format_pie_chart(coverage['pie_data']))
    lines.append('```')
    lines.append('')

    # 失败详情
    failed_suites = [r for r in results if r['fail'] > 0]
    if failed_suites:
        lines.append('## 失败详情')
        lines.append('')
        for r in failed_suites:
            lines.append(f'### {r["name"]}')
            lines.append(f'- 通过: {r["pass"]}, 失败: {r["fail"]}')
            if r.get('error_msg'):
                lines.append(f'- 错误信息: {r["error_msg"]}')
            lines.append('')

    # 汇总行
    lines.append('---')
    lines.append('')
    lines.append(f'_报告由 run_simulation.py 自动生成 | {time.strftime("%Y-%m-%d %H:%M:%S")}_')

    return '\n'.join(lines)


def generate_json_report(results, coverage, elapsed):
    """生成 JSON 格式的测试报告"""
    total_pass = sum(r['pass'] for r in results)
    total_fail = sum(r['fail'] for r in results)
    total_tests = total_pass + total_fail

    report = {
        'metadata': {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'elapsed_seconds': elapsed,
            'tool': 'Icarus Verilog',
            'script_version': '1.0.0'
        },
        'summary': {
            'total_suites': len(results),
            'passed_suites': sum(1 for r in results if r['fail'] == 0),
            'total_tests': total_tests,
            'total_pass': total_pass,
            'total_fail': total_fail,
            'pass_rate': round((total_pass / total_tests * 100) if total_tests > 0 else 0, 2)
        },
        'suites': [
            {
                'name': r['name'],
                'file': r['file'],
                'src': r['src'],
                'expected_pass': r['expected_pass'],
                'pass': r['pass'],
                'fail': r['fail'],
                'total': r['pass'] + r['fail'],
                'pass_rate': round((r['pass'] / (r['pass'] + r['fail']) * 100)
                                    if (r['pass'] + r['fail']) > 0 else 0, 2),
                'status': 'passed' if r['fail'] == 0 else 'failed',
                'error': r.get('error_msg')
            }
            for r in results
        ],
        'coverage': {
            'by_type': {
                k: {
                    'total': v['total'],
                    'passed': v['passed'],
                    'suites': v['suites'],
                    'rate': round(v['rate'], 2)
                }
                for k, v in coverage['by_type'].items() if v['total'] > 0
            },
            'by_component': coverage['by_component'],
            'matrix': {
                'suites': coverage['matrix']['suites'],
                'signals': coverage['matrix']['signals']
            }
        }
    }

    return report


def save_reports(results, coverage, elapsed, output_dir):
    """保存 JSON 和 Markdown 报告"""
    os.makedirs(output_dir, exist_ok=True)

    # Markdown
    md_content = generate_markdown_report(results, coverage, elapsed, output_dir)
    md_path = os.path.join(output_dir, 'simulation_report.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print_info(f'Markdown 报告已保存: {md_path}')

    # JSON
    json_report = generate_json_report(results, coverage, elapsed)
    json_path = os.path.join(output_dir, 'simulation_report.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2)
    print_info(f'JSON 报告已保存: {json_path}')

    return md_path, json_path


# =============================================================
# 主流程
# =============================================================

def resolve_src_files(suite, test_dir):
    """解析套件所需的源文件列表"""
    src = suite.get('src', '')
    if not src:
        return []

    srcs = [src]

    # 对于包含 `include 的模块, 可能还需要其他文件
    # mixed_design_ecc.v 本身就是源文件 (tb 通过 `include 引入)
    tb_file = suite['file']
    tb_path = os.path.join(test_dir, tb_file)
    if os.path.exists(tb_path):
        with open(tb_path, 'r') as f:
            content = f.read(4096)
            # 检查是否通过 `include 引入了源文件
            includes = re.findall(r'`include\s+["<]([^">]+)[">]', content)
            for inc in includes:
                inc_path = os.path.join(test_dir, inc)
                if os.path.exists(inc_path) and inc not in srcs:
                    srcs.append(inc)

    return srcs


def run_simulation(args):
    """主仿真运行逻辑"""
    start_time = time.time()

    # 确定要运行的套件
    if args.suite:
        matched = [s for s in TEST_SUITES if args.suite.lower() in s['name'].lower()
                   or args.suite.lower() in s['file'].lower()]
        if not matched:
            print_fail(f'未找到匹配 "{args.suite}" 的套件')
            print_info(f'可用套件: {", ".join(s["name"] for s in TEST_SUITES)}')
            return 1
        suites_to_run = matched
    else:
        suites_to_run = TEST_SUITES

    # 确定 test_mock_data 目录
    test_dir = TEST_MOCK_DIR
    if args.test_dir:
        test_dir = args.test_dir

    if not os.path.isdir(test_dir):
        print_fail(f'测试目录不存在: {test_dir}')
        print_info(f'尝试使用: {TEST_MOCK_DIR}')
        test_dir = TEST_MOCK_DIR
        if not os.path.isdir(test_dir):
            print_fail(f'默认测试目录也不存在: {test_dir}')
            return 1

    # 验证 iverilog
    iverilog = find_tool('iverilog.exe', IVERILOG_DEFAULT)
    vvp = find_tool('vvp.exe', VVP_DEFAULT)

    if not os.path.exists(iverilog):
        print_warn(f'iverilog 未找到, 将尝试从 PATH 搜索: {iverilog}')
    if not os.path.exists(vvp):
        print_warn(f'vvp 未找到, 将尝试从 PATH 搜索: {vvp}')

    print_header(f'仿真回归测试运行器 (找到 {len(suites_to_run)} 个套件)')
    print(f'  测试目录: {test_dir}')
    print(f'  iverilog: {iverilog}')
    print(f'  vvp:      {vvp}')
    print(f'  时间:     {time.strftime("%Y-%m-%d %H:%M:%S")}')
    print()

    # 运行每个套件
    results = []
    for suite in suites_to_run:
        name = suite['name']
        tb_file = suite['file']
        expected = suite['expected_pass']

        print(f'  [{name}]')
        print(f'    文件: {tb_file}')
        print(f'    预期通过: {expected}')

        src_files = resolve_src_files(suite, test_dir)
        if src_files:
            print(f'    源文件: {", ".join(src_files)}')

        success, output, pass_count, fail_count, error_msg = run_testbench(
            test_dir, tb_file, src_files,
            timeout=args.timeout,
            verbose=args.verbose
        )

        result = {
            'name': name,
            'file': tb_file,
            'src': suite['src'],
            'expected_pass': expected,
            'pass': pass_count,
            'fail': fail_count,
            'success': success,
            'error_msg': error_msg,
            'tests': suite['tests']
        }

        # 结果判断
        total = pass_count + fail_count
        if fail_count > 0:
            print_fail(f'通过: {pass_count}, 失败: {fail_count}')
        elif pass_count == 0 and error_msg:
            print_fail(f'运行失败: {error_msg}')
        else:
            print_pass(f'通过: {pass_count}/{total} (预期 {expected})')

        if error_msg and args.verbose:
            print(f'    错误: {error_msg[:200]}')

        results.append(result)

        if args.verbose and output:
            # 显示仿真输出的关键行
            key_lines = [l for l in output.split('\n')
                         if 'PASS' in l or 'FAIL' in l
                         or 'error' in l.lower() or 'warning' in l.lower()]
            for line in key_lines[:15]:
                print(f'      {line.strip()}')

        print()

    # 计算耗时
    elapsed = time.time() - start_time

    # 汇总
    total_pass = sum(r['pass'] for r in results)
    total_fail = sum(r['fail'] for r in results)
    total_tests = total_pass + total_fail
    passed_suites = sum(1 for r in results if r['fail'] == 0)
    overall_rate = (total_pass / total_tests * 100) if total_tests > 0 else 0

    print_header('回归测试汇总')
    print(f'  运行套件: {passed_suites}/{len(results)}')
    print(f'  总通过:   {total_pass}/{total_tests}')
    print(f'  总失败:   {total_fail}')
    print(f'  通过率:   {overall_rate:.2f}%')
    print(f'  耗时:     {elapsed:.1f} 秒')
    print()

    for r in results:
        total = r['pass'] + r['fail']
        icon = '✅' if r['fail'] == 0 else '❌'
        status = '通过' if r['fail'] == 0 else '失败'
        rate = (r['pass'] / total * 100) if total > 0 else 0
        print(f'  {icon} {r["name"]}: {r["pass"]}/{total} ({rate:.1f}%) {status}')

    print()

    # 覆盖率统计
    coverage = compute_coverage(results)

    print_header('覆盖率分析')
    by_type = coverage['by_type']
    for ctype, data in by_type.items():
        if data['total'] > 0:
            type_label = {'functional': '功能测试', 'fault-injection': '故障注入测试',
                          'stress': '压力测试', 'exhaustive': '穷举测试'}.get(ctype, ctype)
            icon = '✅' if data['rate'] >= 90 else ('⚠️' if data['rate'] >= 50 else '❌')
            print(f'  {icon} {type_label}: {data["passed"]}/{data["total"]} ({data["rate"]:.1f}%)')

    print()
    print('  测试分布:')
    print(format_pie_chart(coverage['pie_data']))

    print()
    print('  覆盖率矩阵:')
    print(format_coverage_matrix(coverage['matrix']))

    # 生成报告
    output_dir = args.output_dir or REPORT_DIR
    md_path, json_path = save_reports(results, coverage, elapsed, output_dir)

    # 如果指定了 --json, 打印 JSON 到 stdout
    if args.json:
        json_report = generate_json_report(results, coverage, elapsed)
        print()
        print(json.dumps(json_report, ensure_ascii=False, indent=2))

    # 返回退出码
    has_failures = any(r['fail'] > 0 for r in results)
    return 1 if has_failures else 0


# =============================================================
# CLI 入口
# =============================================================

def main():
    parser = argparse.ArgumentParser(
        description='仿真回归测试运行器 — Icarus Verilog 测试 + 覆盖率报告',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例:\n'
            '  python run_simulation.py --all\n'
            '  python run_simulation.py --suite cnt_comp\n'
            '  python run_simulation.py --suite ecc --verbose\n'
            '  python run_simulation.py --all --output ./my_report\n'
            '  python run_simulation.py --all --json > report.json\n'
        )
    )

    # 运行模式
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--all', action='store_true', default=True,
                            help='运行所有测试套件 (默认)')
    mode_group.add_argument('--suite', type=str, default=None,
                            help='仅运行匹配的套件 (模糊匹配名称或文件名)')

    # 输出选项
    parser.add_argument('--output', '-o', dest='output_dir', type=str, default=None,
                        help='报告输出目录 (默认: ../reports)')
    parser.add_argument('--json', action='store_true', default=False,
                        help='输出 JSON 格式到 stdout')
    parser.add_argument('--verbose', '-v', action='store_true', default=False,
                        help='显示详细输出 (编译/运行命令, 仿真输出)')

    # 高级选项
    parser.add_argument('--test-dir', type=str, default=None,
                        help='测试文件目录 (默认: ../test_mock_data)')
    parser.add_argument('--timeout', type=int, default=120,
                        help='每个套件的超时秒数 (默认: 120)')

    args = parser.parse_args()

    try:
        exit_code = run_simulation(args)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print('\n\n用户中断')
        sys.exit(130)
    except Exception as e:
        print_fail(f'运行时错误: {e}')
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
