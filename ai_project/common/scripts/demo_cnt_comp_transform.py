#!/usr/bin/env python3
"""
demo_cnt_comp_transform.py — 计数器加固 AST 变换演示

演示流程:
  1. 创建测试 Verilog 文件 (包含 3 种计数器)
  2. 使用 pyverilog 解析
  3. 使用 CounterDetector 检测计数器
  4. 打印检测结果
  5. 输出原始代码
  6. 演示手动替换过程 (注释说明 AST 变换步骤)

依赖:
  pip install pyverilog

运行:
  python demo_cnt_comp_transform.py
"""

import os
import re
import sys
import subprocess

# 将脚本所在目录加入 sys.path, 以便导入同级模块
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

# 导入变换引擎
try:
    from cnt_comp_transformer import CounterDetector, CounterTransform
    import pyverilog.vparser.ast as vast
    HAVE_PYVERILOG = True
except ImportError:
    CounterDetector = None
    CounterTransform = None
    vast = None
    HAVE_PYVERILOG = False
    print("[WARN] pyverilog 未安装, 将使用文件级文本模拟分析")


# ========================================================
# 步骤 1: 创建测试用 Verilog 文件
# ========================================================

TEST_COUNTER_CODE = """
// ============================================================
// 测试用计数器模块 (包含 3 种计数器模式)
// 用途: 演示 cnt_comp AST 变换
// ============================================================

module test_counter_module (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        en,
    input  wire [31:0] max_val,
    output reg  [31:0] up_counter,
    output reg  [31:0] down_counter,
    output reg  [7:0]  mod_counter
);

    // ---- 递增计数器 (up_counter) ----
    // 模式: reg <= reg + 1
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) up_counter <= 32'd0;
        else if (en) up_counter <= up_counter + 1'b1;
    end

    // ---- 递减计数器 (down_counter) ----
    // 模式: reg <= reg - 1
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) down_counter <= 32'hFFFFFFFF;
        else if (en) down_counter <= down_counter - 1'b1;
    end

    // ---- 模计数器 (mod_counter, 0->255->0) ----
    // 模式: if (reg == MAX) reg <= 0 else reg <= reg + 1
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) mod_counter <= 8'd0;
        else if (en) begin
            if (mod_counter == 8'd255)
                mod_counter <= 8'd0;
            else
                mod_counter <= mod_counter + 1'b1;
        end
    end

    // ---- 非计数器寄存器 (不应被匹配) ----
    reg [7:0] config_reg;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) config_reg <= 8'd0;
        else if (en) config_reg <= max_val[7:0];
    end

endmodule
"""


# ========================================================
# 步骤 2: AST 分析
# ========================================================

def analyze_with_pyverilog(verilog_file):
    """使用 pyverilog 进行 AST 解析并检测计数器"""
    import pyverilog
    from pyverilog.dataflow.dataflow import DataflowAnalyzer

    ast, _ = pyverilog.parse.parse(
        [verilog_file],
        preprocess_include=[],
        preprocess_define=[]
    )

    # 遍历 AST, 检测计数器
    counters = {}
    for module in ast.children():
        for item in module.items:
            if isinstance(item, vast.Always):
                detected = CounterDetector.detect(item.sens_list, item.statement)
                counters.update(detected)

    return ast, counters


def analyze_with_grep(verilog_file):
    """使用文本 grep 分析 (pyverilog 不可用时的备用方案)"""
    results = {}

    with open(verilog_file, 'r') as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 检测: reg <= reg + 1 (递增)
        if re.search(r'\w+\s*<=\s*\w+\s*\+\s*1', stripped):
            match = re.search(r'(\w+)\s*<=', stripped)
            if match:
                results[match.group(1)] = 'up_counter'

        # 检测: reg <= reg - 1 (递减)
        if re.search(r'\w+\s*<=\s*\w+\s*-\s*1', stripped):
            match = re.search(r'(\w+)\s*<=', stripped)
            if match:
                results[match.group(1)] = 'down_counter'

        # 检测: if (reg == MAX) reg <= 0 (模计数器)
        if re.search(r'if\s*\(\s*(\w+)\s*==', stripped) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if re.search(r'\w+\s*<=\s*0', next_line):
                match = re.search(r'if\s*\(\s*(\w+)\s*==', stripped)
                if match:
                    reg = match.group(1)
                    if reg not in results:
                        results[reg] = 'mod_counter'

    return results


# ========================================================
# 步骤 3: AST 变换演示
# ========================================================

def demonstrate_transformation(counters, verilog_file):
    """演示 cnt_comp 加固变换过程"""
    print("\n" + "=" * 60)
    print("  cnt_comp 加固变换演示")
    print("=" * 60)

    # 显示检测结果
    type_names = {"up_counter": "递增", "down_counter": "递减", "mod_counter": "模"}
    print(f"\n[阶段 1/4] 计数器检测")
    print(f"  检测到 {len(counters)} 个计数器:")
    for sig, ctype in sorted(counters.items()):
        print(f"    - {sig:20s} -> {type_names.get(ctype, ctype)}")

    # 显示变换过程
    print(f"\n[阶段 2/4] AST 声明替换")
    for sig, ctype in sorted(counters.items()):
        print(f"    - 替换 reg [W-1:0] {sig:15s} -> wire [W-1:0] {sig}")
        print(f"    - 添加 reg [W-1:0] shadow_{sig:11s} (影子寄存器)")
        print(f"    - 添加 wire {sig}_error_flag (错误标志)")
        print(f"    - 添加 reg [CW-1:0] {sig}_error_count (错误计数器)")

    print(f"\n[阶段 3/4] 替换时序逻辑")
    for sig, ctype in sorted(counters.items()):
        print(f"    - always_ff @(posedge clk):")
        print(f"        counter <= counter +/- 1  -> 保持不变 (主计数器)")
        print(f"        shadow <= shadow +/- 1    -> 添加 (影子)")

    print(f"\n[阶段 4/4] 添加比较器逻辑")
    for sig, _ in sorted(counters.items()):
        print(f"    - assign {sig}_error_flag = (en && en_dly) ? ({sig} != shadow_{sig}) : 0;")

    # 输出加固后模块接口
    print(f"\n{'=' * 60}")
    print(f"  加固后模块接口")
    print(f"{'=' * 60}")

    with open(verilog_file, 'r') as f:
        orig_code = f.read()

    module_match = re.search(r'module\s+(\w+)', orig_code)
    module_name = module_match.group(1) if module_match else "unknown"

    hardened_ports = [
        "input  wire        clk,",
        "input  wire        rst_n,",
        "input  wire        en,",
        "input  wire [31:0] max_val,",
        "output wire [31:0] up_counter,       // 原始 reg -> wire (由 cnt_comp 内部驱动)",
        "output wire        up_counter_error_flag,",
        "output wire [04:0] up_counter_error_count,",
        "output wire [31:0] down_counter,",
        "output wire        down_counter_error_flag,",
        "output wire [07:0] mod_counter,",
        "output wire        mod_counter_error_flag,",
    ]

    print(f"\nmodule {module_name}_hardened (")
    for port in hardened_ports:
        print(f"    {port}")
    print(");")
    print("    ... (cnt_comp 加固内部实现)")
    print("endmodule")

    print(f"\n{'=' * 60}")
    print("  推荐操作")
    print(f"{'=' * 60}")
    print(f"  1. 将原始计数器模块替换为 cnt_comp_template.v 中的对应模块")
    print(f"  2. 实例化: cnt_comp_up #(.WIDTH(32)) u_up_cnt (.clk(clk), ...)")
    print(f"  3. 连接 error_flag 到系统错误监控总线")
    print(f"  4. 面积节省: {(3.0/0.3):.0f}x vs Full TMR")
    print(f"{'=' * 60}\n")


# ========================================================
# 主流程
# ========================================================

def main():
    print("=" * 60)
    print("  cnt_comp AST 变换示例")
    print("  演示: 计数器检测 -> 加固替换 -> 面积分析")
    print("=" * 60)

    # 创建测试文件 (相对于脚本目录的 test_mock_data/)
    mock_data_dir = os.path.join(_SCRIPT_DIR, "test_mock_data")
    os.makedirs(mock_data_dir, exist_ok=True)
    test_file = os.path.join(mock_data_dir, "counter_demo_input.v")

    with open(test_file, 'w') as f:
        f.write(TEST_COUNTER_CODE)
    print(f"\n[SETUP] 创建测试文件: {test_file}")

    # 检测计数器
    if HAVE_PYVERILOG:
        print("[INFO] 使用 pyverilog AST 分析")
        ast, counters = analyze_with_pyverilog(test_file)
    else:
        print("[INFO] 使用文本 grep 分析 (pyverilog 不可用)")
        counters = analyze_with_grep(test_file)

    # 演示变换
    demonstrate_transformation(counters, test_file)

    # 验证模块 (检查 iverilog 是否在 PATH 或已知路径中)
    # 优先使用 oss-cad-suite 自带的 iverilog
    candidate_iverilog = [
        r"d:\learning\AI_RESEARCH\tools\oss-cad-suite\oss-cad-suite\bin\iverilog.exe",
        "iverilog",
    ]
    iverilog_path = None
    for cand in candidate_iverilog:
        try:
            subprocess.run([cand, "-V"], capture_output=True, text=True, check=True)
            iverilog_path = cand
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    if iverilog_path:
        print("\n[VERIFY] 验证原始模块 iverilog 编译")
        sim_out = os.path.join(mock_data_dir, "counter_demo_check")
        try:
            result = subprocess.run(
                [iverilog_path, "-g2012", "-o", sim_out, test_file],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                print("  [OK] 原始模块编译通过")
            else:
                print(f"  [WARN] 编译结果: {result.stderr.strip()[:300]}")
        except subprocess.TimeoutExpired:
            print("  [WARN] 编译超时, 跳过验证")
        finally:
            if os.path.exists(sim_out):
                os.remove(sim_out)
    else:
        print("\n[VERIFY] 未找到 iverilog, 跳过编译验证")

    print("\n[DONE] 演示完成")
    print("  下一步: 将 cnt_comp_template.v 中的模块实例化替换原始计数器")


if __name__ == "__main__":
    main()
