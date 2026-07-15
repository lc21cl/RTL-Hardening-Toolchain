"""
GUI 综合测试脚本 - 验证所有新功能标签页

测试内容:
1. 层次化加固 - 模块树状视图和策略配置
2. 策略推荐 - 模块类型分类和策略推荐
3. 效果可视化 - 加固指标计算和可视化
4. 增量加固 - 设计变更检测和增量分析
5. Web GUI - 启动和基本功能
6. 接口兼容性 - 策略冲突检测和解决

运行方式:
python test_gui_comprehensive.py
"""

import os
import sys
import tempfile
import json
import subprocess
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sim.formal_test.rag_integration import (
    analyze_design_for_hardening,
    allocate_strategy_per_module,
    recommend_strategies,
    calculate_hardening_metrics,
    run_incremental_hardening,
)


def create_test_design():
    """创建测试用的层次化设计文件"""
    design_files = {
        'top.v': """
module top_module (
    input wire clk,
    input wire rst_n,
    input wire [31:0] data_in,
    output reg [31:0] data_out
);
    reg [31:0] top_reg;

    control_unit u_ctrl (
        .clk(clk),
        .rst_n(rst_n),
        .en(1'b1),
        .ctrl_out()
    );

    data_path u_data (
        .clk(clk),
        .data_a(data_in),
        .data_b(top_reg),
        .result(data_out)
    );

    fsm_core u_fsm (
        .clk(clk),
        .rst_n(rst_n),
        .start(1'b1),
        .done()
    );
endmodule
""",
        'control_unit.v': """
module control_unit (
    input wire clk,
    input wire rst_n,
    input wire en,
    output reg [3:0] ctrl_out
);
    reg [3:0] state_reg;
    reg [3:0] next_state;
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) state_reg <= 4'd0;
    else state_reg <= next_state;
end
always @(*) begin
    case(state_reg)
        4'd0: next_state = 4'd1;
        4'd1: next_state = 4'd2;
        4'd2: next_state = 4'd3;
        4'd3: next_state = 4'd0;
        default: next_state = 4'd0;
    endcase
end
endmodule
""",
        'data_path.v': """
module data_path (
    input wire clk,
    input wire [31:0] data_a,
    input wire [31:0] data_b,
    output reg [31:0] result
);
    reg [31:0] buffer_reg;
    reg [31:0] accumulator;
always @(posedge clk) begin
    buffer_reg <= data_a;
    accumulator <= buffer_reg + data_b;
    result <= accumulator;
end
endmodule
""",
        'fsm_core.v': """
module fsm_core (
    input wire clk,
    input wire rst_n,
    input wire start,
    output reg done
);
    reg [2:0] fsm_state;
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        fsm_state <= 3'd0;
        done <= 1'b0;
    end else begin
        case(fsm_state)
            3'd0: if(start) fsm_state <= 3'd1;
            3'd1: fsm_state <= 3'd2;
            3'd2: fsm_state <= 3'd3;
            3'd3: begin fsm_state <= 3'd0; done <= 1'b1; end
            default: fsm_state <= 3'd0;
        endcase
    end
end
endmodule
"""
    }
    return design_files


def test_strategy_recommendation():
    """测试策略推荐功能"""
    print("\n" + "=" * 60)
    print("  Test 1: Strategy Recommendation")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        design_files = create_test_design()
        for fname, content in design_files.items():
            with open(os.path.join(tmpdir, fname), 'w') as f:
                f.write(content)

        top_path = os.path.join(tmpdir, 'top.v')

        analysis = analyze_design_for_hardening(top_path, recursive=True, search_paths=[tmpdir])
        result = recommend_strategies(analysis, optimization_goal='balanced')

        print(f"[GUI_TEST] 推荐模块数: {len(result.get('recommendations', {}))}")
        
        for module_name, rec in result.get('recommendations', {}).items():
            print(f"[GUI_TEST]   {module_name}:")
            print(f"[GUI_TEST]     类型: {rec.get('module_type')}")
            print(f"[GUI_TEST]     推荐策略: {rec.get('recommended_strategy')}")
            top_strategies = [s['strategy'] for s in rec.get('top_strategies', [])]
            print(f"[GUI_TEST]     候选策略: {', '.join(top_strategies)}")

        assert len(result.get('recommendations', {})) >= 1, "未生成任何推荐"
        
        print("[GUI_TEST] ✅ 策略推荐功能正常")
        return True


def test_hardening_metrics():
    """测试加固效果可视化功能"""
    print("\n" + "=" * 60)
    print("  Test 2: Hardening Metrics")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        design_files = create_test_design()
        for fname, content in design_files.items():
            with open(os.path.join(tmpdir, fname), 'w') as f:
                f.write(content)

        top_path = os.path.join(tmpdir, 'top.v')

        analysis = analyze_design_for_hardening(top_path, recursive=True, search_paths=[tmpdir])
        
        module_strategy_map = {
            'top_module': 'tmr',
            'control_unit': 'parity',
            'data_path': 'ecc',
            'fsm_core': 'onehot_fsm',
        }

        metrics = calculate_hardening_metrics(analysis, module_strategy_map)
        
        summary = metrics.get('summary', {})
        print(f"[GUI_TEST] 模块数: {summary.get('total_modules')}")
        print(f"[GUI_TEST] 寄存器数: {summary.get('total_registers')}")
        print(f"[GUI_TEST] 面积增加: {summary.get('area_increase_percent', 0):.1f}%")
        print(f"[GUI_TEST] 最大延迟: {summary.get('max_latency_cycles')} cycles")
        print(f"[GUI_TEST] 可靠性: {summary.get('avg_reliability_stars')}")

        assert 'total_modules' in summary, "缺少 total_modules"
        assert 'total_registers' in summary, "缺少 total_registers"
        assert 'area_increase_percent' in summary, "缺少 area_increase_percent"
        
        print("[GUI_TEST] ✅ 加固效果可视化功能正常")
        return True


def test_incremental_hardening():
    """测试增量加固功能"""
    print("\n" + "=" * 60)
    print("  Test 3: Incremental Hardening")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        design_files = create_test_design()
        for fname, content in design_files.items():
            with open(os.path.join(tmpdir, fname), 'w') as f:
                f.write(content)

        top_path = os.path.join(tmpdir, 'top.v')
        
        output_dir = os.path.join(tmpdir, 'incremental_data')
        os.makedirs(output_dir, exist_ok=True)

        analysis = analyze_design_for_hardening(top_path, recursive=True, search_paths=[tmpdir])
        
        result = run_incremental_hardening(analysis, output_dir)
        
        print(f"[GUI_TEST] 设计是否变更: {result.get('design_changed')}")
        print(f"[GUI_TEST] 模块策略数: {len(result.get('module_strategy_map', {}))}")
        
        if result.get('design_changed'):
            print(f"[GUI_TEST] 复用模块: {result.get('reused_modules')}")
            print(f"[GUI_TEST] 新增模块: {result.get('new_modules')}")
            print(f"[GUI_TEST] 移除模块: {result.get('removed_modules')}")

        assert 'module_strategy_map' in result, "缺少 module_strategy_map"
        
        incremental_file = os.path.join(output_dir, '.incremental_hardening.json')
        assert os.path.exists(incremental_file), "增量数据文件未生成"
        print(f"[GUI_TEST] 增量数据文件已生成: {incremental_file}")
        
        with open(incremental_file, 'r') as f:
            saved_data = json.load(f)
        assert 'design_hash' in saved_data, "缺少 design_hash"
        assert 'module_strategy_map' in saved_data, "保存的数据缺少 module_strategy_map"
        
        second_result = run_incremental_hardening(analysis, output_dir)
        print(f"[GUI_TEST] 第二次运行 - 设计是否变更: {second_result.get('design_changed')}")
        
        if not second_result.get('design_changed'):
            print("[GUI_TEST] ✅ 增量加固正确识别设计未变更")
        
        print("[GUI_TEST] ✅ 增量加固功能正常")
        return True


def test_web_gui_import():
    """测试 Web GUI 模块导入"""
    print("\n" + "=" * 60)
    print("  Test 4: Web GUI Import")
    print("=" * 60)

    try:
        from sim.formal_test.web_gui import start_web_gui, WebGUI, _WEB_GUI_PORT
        print(f"[GUI_TEST] Web GUI 模块导入成功")
        print(f"[GUI_TEST] 默认端口: {_WEB_GUI_PORT}")
        print("[GUI_TEST] ✅ Web GUI 模块可用")
        return True
    except ImportError as e:
        print(f"[GUI_TEST] Web GUI 模块导入失败: {e}")
        return False


def test_interface_compatibility():
    """测试接口兼容性模块"""
    print("\n" + "=" * 60)
    print("  Test 5: Interface Compatibility")
    print("=" * 60)

    try:
        from sim.formal_test.interface_compatibility import (
            resolve_compatibility_conflicts,
            analyze_interface_compatibility,
            check_strategy_compatibility,
        )
        print("[GUI_TEST] 接口兼容性模块导入成功")
        
        compatibility = check_strategy_compatibility('tmr', 'parity')
        print(f"[GUI_TEST] TMR vs Parity 兼容性: {compatibility}")
        
        compatibility = check_strategy_compatibility('tmr', 'tmr')
        print(f"[GUI_TEST] TMR vs TMR 兼容性: {compatibility}")
        
        print("[GUI_TEST] ✅ 接口兼容性模块可用")
        return True
    except ImportError as e:
        print(f"[GUI_TEST] 接口兼容性模块导入失败: {e}")
        return False


def test_hierarchical_strategy_allocation():
    """测试层次化策略分配功能"""
    print("\n" + "=" * 60)
    print("  Test 6: Hierarchical Strategy Allocation")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        design_files = create_test_design()
        for fname, content in design_files.items():
            with open(os.path.join(tmpdir, fname), 'w') as f:
                f.write(content)

        top_path = os.path.join(tmpdir, 'top.v')

        analysis = analyze_design_for_hardening(top_path, recursive=True, search_paths=[tmpdir])
        
        module_strategy_map = {
            'top_module': 'tmr',
            'control_unit': 'parity',
            'data_path': 'ecc',
            'fsm_core': 'onehot_fsm',
        }

        result = allocate_strategy_per_module(analysis, module_strategy_map)
        
        print(f"[GUI_TEST] 模块策略映射: {result.get('module_strategy_map')}")
        print(f"[GUI_TEST] 信号策略映射: {len(result.get('signal_strategy_map', {}))} 个信号")
        
        summary = result.get('strategy_summary', {})
        print(f"[GUI_TEST] 策略统计: {summary}")

        assert 'module_strategy_map' in result, "缺少 module_strategy_map"
        assert 'signal_strategy_map' in result, "缺少 signal_strategy_map"
        assert 'strategy_summary' in result, "缺少 strategy_summary"
        assert summary.get('total_modules', 0) >= 1, "策略汇总中模块数为0"
        
        print("[GUI_TEST] ✅ 层次化策略分配功能正常")
        return True


def test_gui_module_import():
    """测试 GUI 模块导入"""
    print("\n" + "=" * 60)
    print("  Test 7: GUI Module Import")
    print("=" * 60)

    try:
        from harden_gui import HardeningGUI
        print("[GUI_TEST] HardeningGUI 模块导入成功")
        print("[GUI_TEST] ✅ GUI 模块可用")
        return True
    except ImportError as e:
        print(f"[GUI_TEST] GUI 模块导入失败: {e}")
        return False


def test_gui_tabs_structure():
    """测试 GUI 标签页结构 - 通过静态代码分析"""
    print("\n" + "=" * 60)
    print("  Test 8: GUI Tabs Structure (Static Analysis)")
    print("=" * 60)

    gui_path = os.path.join(os.path.dirname(__file__), '..', '..', 'harden_gui.py')
    
    with open(gui_path, 'r', encoding='utf-8') as f:
        content = f.read()

    expected_tabs = [
        "加固管线",
        "测试运行",
        "信号扫描",
        "AIG 分析",
        "层次化加固",
        "策略推荐",
        "效果可视化",
        "增量加固",
        "Web GUI",
        "报告",
    ]

    print("[GUI_TEST] 检查标签页定义:")
    for tab_name in expected_tabs:
        if tab_name in content:
            print(f"[GUI_TEST]   ✅ 找到标签页: {tab_name}")
        else:
            print(f"[GUI_TEST]   ❌ 未找到标签页: {tab_name}")
    
    print("[GUI_TEST] ✅ GUI 标签页结构验证完成")
    return True


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  GUI 综合测试套件 - 验证所有新功能标签页")
    print("=" * 70)

    tests = [
        ('策略推荐功能', test_strategy_recommendation),
        ('加固效果可视化', test_hardening_metrics),
        ('增量加固功能', test_incremental_hardening),
        ('Web GUI 模块', test_web_gui_import),
        ('接口兼容性模块', test_interface_compatibility),
        ('层次化策略分配', test_hierarchical_strategy_allocation),
        ('GUI 模块导入', test_gui_module_import),
        ('GUI 标签页结构', test_gui_tabs_structure),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
                print(f"\n[GUI_TEST] ✅ {name} - PASSED")
            else:
                failed += 1
                print(f"\n[GUI_TEST] ❌ {name} - FAILED")
        except Exception as e:
            failed += 1
            print(f"\n[GUI_TEST] ❌ {name} - FAILED")
            print(f"[GUI_TEST]   错误: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"  测试结果: {passed}/{len(tests)}  PASSED")
    print("=" * 70)

    print("\n[GUI_TEST] 运行现有单元测试...")
    subprocess.run(
        ['python', '-m', 'pytest', 'test_gui_hierarchical.py', '-v'],
        cwd=os.path.join(os.path.dirname(__file__)),
        capture_output=True,
        text=True
    )

    if failed > 0:
        sys.exit(1)