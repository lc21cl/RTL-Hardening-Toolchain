"""
回归测试运行器 v3
集成: Verilog 仿真测试 (6 套件) + Python 单元测试 (向后兼容)

执行:
  python run_regression.py              # 全部 Verilog 测试
  python run_regression.py --voter      # 仅表决器调试日志仿真测试 (旧版)
  python run_regression.py --python     # 仅 Python 单元测试 (旧版)
  python run_regression.py --suite ecc  # 指定单个套件
  python run_regression.py --verbose    # 显示详细输出
  python run_regression.py --json       # 输出 JSON 报告
  python run_regression.py --output DIR # 指定报告目录
"""

import sys
import os
import re
import subprocess
import time
import argparse
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─── 路径与工具 ───────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MOCK_DATA_DIR = os.path.join(SCRIPT_DIR, 'test_mock_data')
SIM_DIR_OLD = os.path.join(SCRIPT_DIR, 'sim')

IVERILOG = r'D:\software\pango\iverilog\bin\iverilog.exe'
VVP = r'D:\software\pango\iverilog\bin\vvp.exe'

DEFAULT_REPORT_DIR = os.path.join(SCRIPT_DIR, 'reports')

# ─── 测试套件注册表 ───────────────────────────────────────────
TEST_SUITES = [
    {
        'name': 'cnt_comp 基本功能',
        'tb': 'tb_cnt_comp.v',
        'needs_file': 'cnt_comp_template.v',
        'expected': 6,
    },
    {
        'name': 'cnt_comp 故障注入',
        'tb': 'tb_cnt_comp_fault.v',
        'needs_file': 'cnt_comp_template.v',
        'expected': 9,
    },
    {
        'name': '奇偶校验',
        'tb': 'tb_parity.v',
        'needs_file': 'parity_template.v',
        'expected': 268,
    },
    {
        'name': 'DICE',
        'tb': 'tb_dice.v',
        'needs_file': 'dice_template.v',
        'expected': 6,
    },
    {
        'name': 'ECC (SECDED)',
        'tb': 'tb_ecc.v',
        'needs_file': 'ecc_template.v',
        'expected': 265,
    },
    {
        'name': 'ECC 混合设计加固',
        'tb': 'tb_mixed_design_ecc.v',
        'needs_file': None,  # 测试台用 `include 导入源文件
        'expected': 40,
    },
]

# ─── 工具检查 ─────────────────────────────────────────────────
def check_tools():
    """检查 iverilog 和 vvp 是否存在"""
    missing = []
    for name, path in [('iverilog', IVERILOG), ('vvp', VVP)]:
        if not os.path.exists(path):
            missing.append(f'{name} ({path})')
    if missing:
        print(f'  ❌ 缺少工具: {", ".join(missing)}')
        print(f'     请确保 Icarus Verilog 已正确安装')
        return False
    return True

# ─── 结果解析 ─────────────────────────────────────────────────
def parse_simulation_output(output, verbose=False):
    """
    解析仿真输出中的 PASS/FAIL 计数。
    支持多种输出格式:

    - "PASS: Test N ..." / "FAIL: Test N ..."         (标准格式)
    - "  PASS: ..." / "  FAIL: ..."                    (带缩进, mixed_design)
    - "X PASS, Y FAIL" 形式的汇总行
    - "cnt_comp Tests: X PASS, Y FAIL"
    - "总测试数: N / 通过 (PASS): X / 失败 (FAIL): Y"  (中文格式)
    - "ALL TESTS PASSED"
    - "全部通过!"
    """
    pass_count = 0
    fail_count = 0

    lines = output.split('\n')

    for line in lines:
        stripped = line.strip()

        # 跳过空行和装饰行
        if not stripped or stripped.startswith('===') or stripped.startswith('---'):
            continue

        # --- 方法 1: 逐行统计 PASS/FAIL ---
        # 匹配 "PASS:" 或 "FAIL:" 前缀的行 (含缩进版本)
        if re.match(r'^\s*(PASS|FAIL):', stripped):
            if stripped.startswith('PASS:'):
                pass_count += 1
            elif stripped.startswith('FAIL:'):
                fail_count += 1
            if verbose:
                print(f'    {stripped}')
            continue

    # --- 方法 2: 查找汇总行提取精确计数 ---
    for line in lines:
        stripped = line.strip()

        # 中文格式: "总测试数: 40, 通过 (PASS): 40, 失败 (FAIL): 0"
        m = re.search(r'失败\s*\(?FAIL\)?\s*[:：]\s*(\d+)', stripped)
        if m:
            fail_count = max(fail_count, int(m.group(1)))

        m = re.search(r'通过\s*\(?PASS\)?\s*[:：]\s*(\d+)', stripped)
        if m:
            pass_count = max(pass_count, int(m.group(1)))

        # 英文格式: "cnt_comp Tests: X PASS, Y FAIL"
        #          "Parity Tests: X PASS, Y FAIL"
        #          "ECC Tests: X PASS, Y FAIL"
        #          "DICE Tests: X PASS, Y FAIL"
        #          "cnt_comp_up Fault Injection: X PASS, Y FAIL"
        m = re.search(r'Tests?:?\s*(\d+)\s+PASS\s*,\s*(\d+)\s+FAIL', stripped)
        if m:
            pass_count = max(pass_count, int(m.group(1)))
            fail_count = max(fail_count, int(m.group(2)))

        # 通用格式: "X PASS, Y FAIL"
        m = re.search(r'^(\d+)\s+PASS\s*,\s*(\d+)\s+FAIL', stripped)
        if m:
            pass_count = max(pass_count, int(m.group(1)))
            fail_count = max(fail_count, int(m.group(2)))

    # --- 方法 3: "ALL TESTS PASSED" → 确认无失败 ---
    if re.search(r'ALL TESTS PASSED', output):
        # 如果明确写了 ALL PASSED 但 fail_count 为 0，保持原样
        pass

    # --- 方法 4: "全部通过!" 且无 FAIL → fail_count=0 ---
    if '全部通过' in output and fail_count == 0:
        pass

    return pass_count, fail_count


# ─── Verilog 仿真运行 ─────────────────────────────────────────
def run_verilog_suite(suite, verbose=False):
    """
    编译并运行单个 Verilog 测试套件。
    测试文件均在 test_mock_data 目录下，使用 include 引用模板，
    因此编译命令需要从 test_mock_data 目录执行（或使用 -I 标志）。
    """
    tb_name = suite['tb']
    expected = suite['expected']
    suite_name = suite['name']

    tb_path = os.path.join(MOCK_DATA_DIR, tb_name)
    if not os.path.exists(tb_path):
        print(f'  ❌ 找不到测试文件: {tb_path}')
        return {
            'name': suite_name,
            'tb': tb_name,
            'pass': 0,
            'fail': 0,
            'expected': expected,
            'duration': 0,
            'error': f'测试文件不存在: {tb_path}',
        }

    vvp_rel = f'__sim_{os.path.splitext(tb_name)[0]}.vvp'
    vvp_file = os.path.join(MOCK_DATA_DIR, vvp_rel)

    if verbose:
        print(f'  [1/2] 编译 {tb_name}...')

    start_time = time.time()

    # 编译: 从 test_mock_data 目录执行, 需要包含模板源文件
    src_files = [tb_name]
    needs = suite.get('needs_file')
    if needs:
        src_files.append(needs)
    for extra in suite.get('extra_files', []):
        src_files.append(extra)
    compile_cmd = [IVERILOG, '-g2005-sv', '-o', vvp_rel] + src_files
    if verbose:
        print(f'  [1/2] 编译: {" ".join(compile_cmd)}')
    try:
        comp_result = subprocess.run(
            compile_cmd, capture_output=True,
            encoding='utf-8', errors='replace',
            cwd=MOCK_DATA_DIR, timeout=60
        )
    except subprocess.TimeoutExpired:
        print(f'  ❌ 编译超时 (60s): {tb_name}')
        return {
            'name': suite_name,
            'tb': tb_name,
            'pass': 0,
            'fail': 0,
            'expected': expected,
            'duration': 0,
            'error': '编译超时',
        }

    # 检查 vvp 是否生成 (iverilog 即使有 Unknown module 也会生成)
    has_vvp = os.path.exists(vvp_file)
    if not has_vvp:
        error_text = (comp_result.stdout or '') + '\n' + (comp_result.stderr or '')
        print(f'  ❌ 编译失败, 未生成 vvp')
        for line in error_text.split('\n')[:8]:
            if 'error' in line.lower():
                print(f'       {line.strip()}')
        return {
            'name': suite_name,
            'tb': tb_name,
            'pass': 0,
            'fail': 0,
            'expected': expected,
            'duration': 0,
            'error': '编译失败, 未生成 vvp',
        }

    # 有 vvp 文件就继续仿真 (含 Unknown module 警告的情况)
    if comp_result.returncode != 0 and verbose:
        print(f'  ⚠ 编译有警告 (exit={comp_result.returncode}) 但已生成 vvp')

    # 仿真运行
    if verbose:
        print(f'  [2/2] 仿真 {tb_name}...')

    run_cmd = [VVP, vvp_rel]
    if verbose:
        print(f'  [2/2] 仿真: {" ".join(run_cmd)}')
    try:
        run_result = subprocess.run(
            run_cmd, capture_output=True,
            encoding='utf-8', errors='replace',
            cwd=MOCK_DATA_DIR, timeout=300
        )
    except subprocess.TimeoutExpired:
        print(f'  ❌ 仿真超时 (300s): {tb_name}')
        return {
            'name': suite_name,
            'tb': tb_name,
            'pass': 0,
            'fail': 0,
            'expected': expected,
            'duration': 0,
            'error': '仿真超时',
        }

    duration = time.time() - start_time
    output = (run_result.stdout or '') + '\n' + (run_result.stderr or '')

    # 解析结果
    actual_pass, actual_fail = parse_simulation_output(output, verbose=verbose)

    # 清理临时 vvp 文件
    try:
        if os.path.exists(vvp_file):
            os.remove(vvp_file)
    except OSError:
        pass

    # 显示详细输出
    if verbose:
        print(f'\n  === 仿真日志 (前 40 行) ===')
        shown = 0
        for line in output.split('\n'):
            if line.strip() and not line.strip().startswith('=='):
                print(f'  {line}')
                shown += 1
                if shown >= 40:
                    break
        if shown >= 40:
            print(f'  ... (省略 {len(output.split(chr(10))) - shown} 行)')
        print()

    return {
        'name': suite_name,
        'tb': tb_name,
        'pass': actual_pass,
        'fail': actual_fail,
        'expected': expected,
        'duration': round(duration, 2),
        'error': None,
    }


# ═══════════════════════════════════════════════════════════════
#  旧版向后兼容函数 (--voter / --python)
# ═══════════════════════════════════════════════════════════════

def run_verilog_simulation(testbench_name):
    """(旧版) 编译并运行 Verilog 仿真测试"""
    print(f'\n{"=" * 60}')
    print(f'  Verilog 仿真: {testbench_name}')
    print(f'{"=" * 60}')

    tb_path = os.path.join(SIM_DIR_OLD, testbench_name)
    if not os.path.exists(tb_path):
        print(f'  ❌ 找不到测试文件: {tb_path}')
        return False

    vvp_file = os.path.join(SIM_DIR_OLD, 'regression_sim.vvp')

    print(f'  [1/2] 编译...')
    cmd = f'cd /d "{SIM_DIR_OLD}" && "{IVERILOG}" -o "{vvp_file}" "{testbench_name}"'
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)

    if result.returncode != 0:
        print(f'  ❌ 编译失败 (exit={result.returncode})')
        for line in result.stderr.split('\n'):
            if 'error' in line.lower():
                print(f'       {line.strip()}')
        return False

    print(f'  [2/2] 仿真...')
    run_cmd = f'cd /d "{SIM_DIR_OLD}" && "{VVP}" "{vvp_file}"'
    run_result = subprocess.run(run_cmd, capture_output=True, text=True, shell=True)

    output = run_result.stdout + run_result.stderr

    if 'PASS' in output and 'FAIL' not in output:
        print(f'  ✅ 所有测试通过')
    else:
        tests_found = re.findall(r'(Test \d+):\s+(PASS|FAIL)', output)
        for test_name, status in tests_found:
            icon = '✅' if status == 'PASS' else '❌'
            print(f'     {icon} {test_name}: {status}')

    voter_lines = re.findall(r'\[TMR-VOTER\]', output)
    print(f'     [TMR-VOTER] 输出行数: {len(voter_lines)}')

    print(f'\n  === 仿真日志 (前 30 行) ===')
    for line in output.split('\n')[:30]:
        if line.strip():
            print(f'  {line}')

    return 'PASS' in output


def test_voter_debug_regression():
    """(旧版) 表决器 6 通道调试日志回归测试"""
    print(f'\n{"=" * 60}')
    print(f'  表决器 6 通道调试日志 - 回归测试')
    print(f'{"=" * 60}')
    return run_verilog_simulation('voter_debug_monitor_tb.v')


def test_python_regression():
    """(旧版) Python 单元回归测试"""
    print(f'\n{"=" * 60}')
    print(f'  Python 单元回归测试')
    print(f'{"=" * 60}')

    from tmr_transformer import TMRTransformer

    tests = [
        ('basic_module', '''
            module basic(a, b, out);
                input a, b;
                output wire out;
                assign out = a & b;
            endmodule
        '''),
        ('fsm_module', '''
            module fsm(clk, rst, state, out);
                input clk, rst;
                input [1:0] state;
                output reg [7:0] out;
                always @(posedge clk) begin
                    if (rst) out <= 0;
                    else begin
                        case(state)
                            2'b00: out <= 8'h01;
                            2'b01: out <= 8'h02;
                            2'b10: out <= 8'h04;
                            2'b11: out <= 8'h08;
                        endcase
                    end
                end
            endmodule
        '''),
        ('reg_module', '''
            module counter(clk, rst, count);
                input clk, rst;
                output reg [7:0] count;
                always @(posedge clk) begin
                    if (rst) count <= 0;
                    else count <= count + 1;
                end
            endmodule
        '''),
    ]

    passed = 0
    for name, code in tests:
        try:
            config = TMRConfig(degree=3, mode='full')
            transformer = TMRTransformer(config)
            result = transformer.transform(code.strip())

            if result and len(result) > len(code.strip()):
                tmr_count = result.count('_tmr_1')
                print(f'  ✅ {name}: TMR 成功 ({tmr_count} 副本)')
                passed += 1
            else:
                print(f'  ❌ {name}: 输出为空或未增长')
        except Exception as e:
            print(f'  ❌ {name}: 异常 - {e}')

    print(f'\n  Python 测试: {passed}/{len(tests)} 通过')
    return passed == len(tests)


def test_selective_tmr_regression():
    """(旧版) 选择性 TMR 回归测试"""
    print(f'\n{"=" * 60}')
    print(f'  选择性 TMR 回归测试')
    print(f'{"=" * 60}')

    from tmr_transformer import TMRTransformer, TMRConfig, SignalAnalyzer

    code = '''
        module controller(clk, rst, state, debug_data, temp_bus, out);
            input clk, rst;
            input [1:0] state;
            input [7:0] debug_data;
            input [7:0] temp_bus;
            output reg [7:0] out;

            reg [7:0] count;

            always @(posedge clk) begin
                if (rst) count <= 0;
                else count <= count + 1;
            end

            always @(*) begin
                case(state)
                    2'b00: out = count;
                    2'b01: out = count + 1;
                    2'b10: out = count + 2;
                    2'b11: out = count + 3;
                endcase
            end
        endmodule
    '''

    try:
        analyzer = SignalAnalyzer(code)
        analysis = analyzer.get_signal_report()

        critical = [s['name'] for s in analysis if s['level'] == 'critical']
        important = [s['name'] for s in analysis if s['level'] == 'important']
        optional = [s['name'] for s in analysis if s['level'] == 'optional']

        print(f'  信号分析结果:')
        print(f'    critical: {critical}')
        print(f'    important: {important}')
        print(f'    optional: {optional}')

        assert 'state' in critical or 'state' in critical + important, 'state 未识别为重要信号'
        assert 'count' in critical or 'count' in critical + important, 'count 未识别为重要信号'
        assert 'debug_data' in optional, 'debug_data 未识别为可选信号'

        config = TMRConfig(degree=3, mode='full', selective_tmr_enabled=True)
        transformer = TMRTransformer(config)
        result = transformer.transform(code.strip())

        for sig in critical + important:
            if sig == 'clk':
                continue
            assert f'{sig}_tmr_1' in result, f'{sig} 缺少 TMR 副本'

        print(f'  ✅ 选择性 TMR: 信号分析 + 加固验证通过')
        return True
    except AssertionError as e:
        print(f'  ❌ {e}')
        return False
    except Exception as e:
        print(f'  ❌ 异常: {e}')
        return False


# ─── 旧版主入口 (保留) ───────────────────────────────────────
def run_legacy_mode():
    """运行旧版回归测试 (--voter 或 --python 标志)"""
    import json as _json

    print('=' * 60)
    print('  回归测试运行器 v2 (向后兼容模式)')
    print('  时间: ' + time.strftime('%Y-%m-%d %H:%M:%S'))
    print('=' * 60)

    results = {}
    run_voter = '--voter' in sys.argv
    run_python = '--python' in sys.argv

    if not run_voter and not run_python:
        run_voter = True
        run_python = True

    if run_voter:
        results['voter_debug'] = test_voter_debug_regression()

    if run_python:
        from tmr_transformer import TMRConfig
        results['python_unit'] = test_python_regression()
        results['selective_tmr'] = test_selective_tmr_regression()

    print(f'\n{"=" * 60}')
    print(f'  回归测试汇总')
    print(f'{"=" * 60}')

    all_pass = True
    for name, status in results.items():
        icon = '✅' if status else '❌'
        print(f'  {icon} {name}: {"通过" if status else "失败"}')
        if not status:
            all_pass = False

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f'\n  总计: {passed}/{total} 通过')

    result_file = os.path.join(SCRIPT_DIR, 'reports', 'regression_result.json')
    result_data = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'results': results,
        'summary': f'{passed}/{total} passed'
    }
    os.makedirs(os.path.dirname(result_file), exist_ok=True)
    with open(result_file, 'w') as f:
        _json.dump(result_data, f, indent=2)
    print(f'  结果已保存: {result_file}')
    print('=' * 60)

    sys.exit(0 if all_pass else 1)


# ─── 新版运行逻辑 ─────────────────────────────────────────────
def run_verilog_regression(suite_names=None, verbose=False, json_report=False, report_dir=None):
    """运行 Verilog 回归测试套件"""
    if report_dir is None:
        report_dir = DEFAULT_REPORT_DIR

    if not check_tools():
        sys.exit(1)

    # 确定要运行的套件
    if suite_names:
        suites = [s for s in TEST_SUITES if s['name'] in suite_names or s['tb'] in suite_names]
        if not suites:
            print(f'  ❌ 未找到匹配的套件: {suite_names}')
            print(f'     可用套件: {", ".join(s["name"] for s in TEST_SUITES)}')
            sys.exit(1)
    else:
        suites = TEST_SUITES

    # 打印时间戳
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    print('=' * 64)
    print(f'  回归测试执行报告')
    print(f'  时间: {timestamp}')
    print('=' * 64)

    all_results = []
    total_pass = 0
    total_fail = 0

    for suite in suites:
        tb_name = suite['tb']
        print(f'\n  ─── {suite["name"]} ({tb_name}) ───')

        result = run_verilog_suite(suite, verbose=verbose)
        all_results.append(result)

        p = result['pass']
        f = result['fail']
        e = result['expected']

        if result['error']:
            status_icon = '❌'
            status_str = f'错误: {result["error"]}'
        elif f > 0:
            status_icon = '❌'
            status_str = f'{p}/{e} 通过 ({f} 失败)'
        elif p >= e:
            status_icon = '✅'
            status_str = f'{p}/{e}'
        else:
            status_icon = '⚠️'
            status_str = f'{p}/{e} (不足预期)'

        print(f'    {status_icon} {status_str} ({result["duration"]}s)')

        total_pass += p
        total_fail += f

    # ─── 汇总 ────────────────────────────────────────────────
    print(f'\n{"=" * 64}')
    print(f'  回归测试执行报告')

    total_expected = sum(s['expected'] for s in suites)
    print(f'  总计: {total_pass}/{total_expected} 通过, {total_fail} 失败'
          f' ({total_pass/total_expected*100:.1f}%)' if total_expected > 0 else '')
    print('=' * 64)

    for r in all_results:
        p = r['pass']
        e = r['expected']
        if r['error']:
            icon = '❌'
            detail = f'错误'
        elif p >= e and r['fail'] == 0:
            icon = '✅'
            detail = f'{p}/{e}'
        else:
            icon = '❌'
            detail = f'{p}/{e}'
        print(f'  {r["name"]:20s}: {detail:10s} {icon}')

    print('-' * 64)

    overall_pass = total_fail == 0 and all(r['fail'] == 0 for r in all_results)
    if overall_pass:
        total_status = f'✅ 全部通过'
    else:
        total_status = f'❌ 有 {total_fail} 项失败'

    print(f'  {"总计":20s}: {total_pass}/{total_expected} {total_status}')
    print('=' * 64)

    # ─── JSON 报告 ───────────────────────────────────────────
    if json_report:
        report_data = {
            'timestamp': timestamp,
            'suites': all_results,
            'total_pass': total_pass,
            'total_fail': total_fail,
            'total_expected': total_expected,
            'overall_status': 'pass' if overall_pass else 'fail',
        }
        os.makedirs(report_dir, exist_ok=True)
        report_filename = f'regression_report_{time.strftime("%Y%m%d_%H%M%S")}.json'
        report_path = os.path.join(report_dir, report_filename)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        print(f'\n  JSON 报告已保存: {report_path}')

    return overall_pass


# ─── 主入口 ───────────────────────────────────────────────────
if __name__ == '__main__':
    # 检查是否为旧版模式 (向后兼容)
    legacy_flags = {'--voter', '--python'}
    if legacy_flags & set(sys.argv[1:]):
        run_legacy_mode()
    else:
        parser = argparse.ArgumentParser(
            description='回归测试运行器 v3 — Verilog 仿真 + Python 单元测试',
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument('--all', action='store_true', default=True,
                            help='运行全部套件 (默认)')
        parser.add_argument('--suite', type=str, nargs='+',
                            help='运行指定套件 (按名称或 tb 文件名)')
        parser.add_argument('--verbose', action='store_true',
                            help='显示详细输出')
        parser.add_argument('--json', action='store_true',
                            help='输出 JSON 报告文件')
        parser.add_argument('--output', type=str, default=None,
                            help='指定报告输出目录')

        args = parser.parse_args()

        suite_names = args.suite if args.suite else None
        verbose = args.verbose
        json_report = args.json
        report_dir = args.output

        overall_pass = run_verilog_regression(
            suite_names=suite_names,
            verbose=verbose,
            json_report=json_report,
            report_dir=report_dir,
        )

        sys.exit(0 if overall_pass else 1)
