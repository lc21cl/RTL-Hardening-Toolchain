#!/usr/bin/env python3
"""test_incremental_hardening.py — 增量加固模块单元测试

测试覆盖:
- 模块解析 (_parse_module)
- 差异分析 (_diff_modules)
- 信号级别差异 (get_signal_level_diff)
- 增量更新 (incremental_update)
- 全量更新 (结构变更)
- 增量补丁生成 (generate_incremental_patch)
- 变更验证 (validate_incremental_change)
- 边界条件 (空模块、无变更、多层嵌套等)
"""

import sys, os, json, unittest, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from sim.formal_test.incremental_hardening import IncrementalHardener


class TestParseModule(unittest.TestCase):
    """测试模块解析功能"""
    
    def setUp(self):
        self.hardener = IncrementalHardener()
    
    def test_parse_simple_module(self):
        """解析简单模块: 端口+信号+always"""
        rtl = """
module test(input clk, input rst, output [7:0] out);
    reg [7:0] counter;
    reg flag;
    always @(posedge clk) begin
        if (rst) counter <= 0;
        else counter <= counter + 1;
    end
    assign out = counter;
endmodule
"""
        info = self.hardener._parse_module(rtl)
        self.assertEqual(info['name'], 'test')
        self.assertEqual(len(info['ports']), 3)
        self.assertEqual(len(info['signals']), 2)
        self.assertEqual(len(info['always_blocks']), 1)
        self.assertEqual(len(info['assignments']), 1)
    
    def test_parse_width_variants(self):
        """测试各种宽度格式解析"""
        rtl = """
module test(
    input [15:0] data, input [31:0] addr,
    output [7:0] result
);
    reg [63:0] wide_sig;
    wire [0:7] reverse_sig;
    endmodule
"""
        info = self.hardener._parse_module(rtl)
        sigs = {s['name']: s for s in info['signals']}
        ports_by_name = {p['name']: p for p in info['ports']}
        
        # 检查端口
        self.assertEqual(ports_by_name['data']['width_size'], 16)
        self.assertEqual(ports_by_name['addr']['width_size'], 32)
        self.assertEqual(ports_by_name['result']['width_size'], 8)
        
        # 检查信号
        self.assertEqual(sigs['wide_sig']['width_size'], 64)
        self.assertEqual(sigs['reverse_sig']['width_size'], 8)
    
    def test_parse_array_signals(self):
        """测试数组类型信号解析"""
        rtl = """
module test(input clk);
    reg [7:0] mem [0:255];
    reg [31:0] ram [0:1023];
    endmodule
"""
        info = self.hardener._parse_module(rtl)
        self.assertEqual(len(info['signals']), 2)
    
    def test_parse_always_blocks(self):
        """测试always块解析: 顺序逻辑与组合逻辑"""
        rtl = """
module test(input clk, input rst, input [7:0] d);
    reg [7:0] q, next_q;
    always @(posedge clk or posedge rst) begin
        if (rst) q <= 0;
        else q <= d;
    end
    always @(*) begin
        next_q = q + 1;
    end
endmodule
"""
        info = self.hardener._parse_module(rtl)
        self.assertEqual(len(info['always_blocks']), 2)
        self.assertEqual(info['always_blocks'][0]['type'], 'sequential')
        self.assertEqual(info['always_blocks'][1]['type'], 'combinational')
    
    def test_parse_nested_always_blocks(self):
        """测试嵌套begin/end的always块"""
        rtl = """
module test(input clk, input rst, input [7:0] d);
    reg [7:0] q, t;
    always @(posedge clk) begin
        if (rst) begin
            q <= 0;
            t <= 0;
        end else begin
            q <= d;
            t <= q;
        end
    end
endmodule
"""
        info = self.hardener._parse_module(rtl)
        self.assertEqual(len(info['always_blocks']), 1)
        self.assertEqual(len(info['always_blocks'][0]['assignments']), 4)
    
    def test_parse_empty_module(self):
        """空模块解析"""
        rtl = "module empty(); endmodule"
        info = self.hardener._parse_module(rtl)
        self.assertEqual(info['name'], 'empty')
        self.assertEqual(len(info['signals']), 0)
        self.assertEqual(len(info['always_blocks']), 0)


class TestDiffModules(unittest.TestCase):
    """测试模块差异分析"""
    
    def setUp(self):
        self.hardener = IncrementalHardener()
    
    def _parse(self, rtl):
        return self.hardener._parse_module(rtl)
    
    def test_add_signal(self):
        """新增信号检测"""
        orig = self._parse("""
module test(input clk);
    reg [7:0] a;
    endmodule
""")
        mod = self._parse("""
module test(input clk);
    reg [7:0] a;
    reg [15:0] b;
    endmodule
""")
        diff = self.hardener._diff_modules(orig, mod)
        self.assertIn('b', diff['added_signals'])
        self.assertFalse(diff['structure_changed'])
    
    def test_remove_signal(self):
        """删除信号检测"""
        orig = self._parse("""
module test(input clk);
    reg [7:0] a;
    reg [7:0] b;
    endmodule
""")
        mod = self._parse("""
module test(input clk);
    reg [7:0] a;
    endmodule
""")
        diff = self.hardener._diff_modules(orig, mod)
        self.assertIn('b', diff['removed_signals'])
    
    def test_width_changed(self):
        """宽度变更检测"""
        orig = self._parse("""
module test(input clk);
    reg [7:0] a;
    endmodule
""")
        mod = self._parse("""
module test(input clk);
    reg [15:0] a;
    endmodule
""")
        diff = self.hardener._diff_modules(orig, mod)
        modified_names = [s['name'] for s in diff['modified_signals']]
        self.assertIn('a', modified_names)
    
    def test_type_changed(self):
        """类型变更检测 (reg → wire)"""
        orig = self._parse("""
module test(input clk);
    reg [7:0] a;
    endmodule
""")
        mod = self._parse("""
module test(input clk);
    wire [7:0] a;
    endmodule
""")
        diff = self.hardener._diff_modules(orig, mod)
        modified_names = [s['name'] for s in diff['modified_signals']]
        self.assertIn('a', modified_names)
    
    def test_structure_changed_port_added(self):
        """新增端口视为结构变更"""
        orig = self._parse("""
module test(input clk);
    reg [7:0] a;
    endmodule
""")
        mod = self._parse("""
module test(input clk, input rst);
    reg [7:0] a;
    endmodule
""")
        diff = self.hardener._diff_modules(orig, mod)
        self.assertTrue(diff['structure_changed'])
    
    def test_always_assign_changed(self):
        """always块内赋值语句变更"""
        orig = self._parse("""
module test(input clk, input rst);
    reg [7:0] q;
    always @(posedge clk) begin
        if (rst) q <= 0;
        else q <= q + 1;
    end
endmodule
""")
        mod = self._parse("""
module test(input clk, input rst);
    reg [7:0] q;
    always @(posedge clk) begin
        if (rst) q <= 0;
        else q <= q + 2;
    end
endmodule
""")
        diff = self.hardener._diff_modules(orig, mod)
        self.assertEqual(len(diff['changed_always_blocks']), 1)
    
    def test_assign_statement_changed(self):
        """assign语句变更"""
        orig = self._parse("""
module test(input [7:0] a, input [7:0] b);
    wire [7:0] sum;
    assign sum = a + b;
endmodule
""")
        mod = self._parse("""
module test(input [7:0] a, input [7:0] b);
    wire [7:0] sum;
    assign sum = a - b;
endmodule
""")
        diff = self.hardener._diff_modules(orig, mod)
        self.assertEqual(len(diff['changed_assignments']), 1)
    
    def test_fanout_changed(self):
        """扇出变化检测"""
        orig = self._parse("""
module test(input clk, input [7:0] d);
    reg [7:0] a;
    always @(posedge clk) a <= d;
    endmodule
""")
        mod = self._parse("""
module test(input clk, input [7:0] d);
    reg [7:0] a;
    reg [7:0] b;
    always @(posedge clk) begin a <= d; b <= a; end
    endmodule
""")
        diff = self.hardener._diff_modules(orig, mod)
        fanout_names = [s['name'] for s in diff['fanout_changed_signals']]
        self.assertIn('a', fanout_names)


class TestSignalLevelDiff(unittest.TestCase):
    """测试信号级别差异"""
    
    def setUp(self):
        self.hardener = IncrementalHardener()
    
    def test_signal_diff_by_cache(self):
        """通过内部缓存获取差异"""
        orig = """
module test(input clk);
    reg [7:0] a;
    reg [7:0] b;
    endmodule
"""
        mod = """
module test(input clk);
    reg [15:0] a;
    reg [7:0] c;
    endmodule
"""
        self.hardener.incremental_update(orig, mod, "")
        diffs = self.hardener.get_signal_level_diff()
        diff_map = {d['name']: d for d in diffs}
        
        self.assertEqual(diff_map['a']['change_type'], 'width_changed')
        self.assertEqual(diff_map['b']['change_type'], 'removed')
        self.assertEqual(diff_map['c']['change_type'], 'added')
    
    def test_signal_diff_direct(self):
        """直接通过参数获取差异"""
        orig = """
module test(input clk);
    reg [7:0] a;
    endmodule
"""
        mod = """
module test(input clk);
    reg [15:0] a;
    reg [7:0] b;
    endmodule
"""
        diffs = self.hardener.get_signal_level_diff(orig, mod)
        diff_map = {d['name']: d for d in diffs}
        
        self.assertEqual(diff_map['a']['change_type'], 'width_changed')
        self.assertEqual(diff_map['b']['change_type'], 'added')
        self.assertTrue(diff_map['a']['affects_hardening'])
        self.assertTrue(diff_map['b']['affects_hardening'])
    
    def test_diff_no_cache(self):
        """无缓存时返回空列表"""
        self.hardener._last_diff = None
        diffs = self.hardener.get_signal_level_diff()
        self.assertEqual(diffs, [])


class TestIncrementalUpdate(unittest.TestCase):
    """测试增量更新功能"""
    
    def setUp(self):
        self.hardener = IncrementalHardener()
    
    def test_incremental_add_signal(self):
        """新增信号的增量更新"""
        orig = """
module test(input clk, input rst);
    reg [7:0] counter;
    always @(posedge clk) begin
        if (rst) counter <= 0;
        else counter <= counter + 1;
    end
endmodule
"""
        mod = """
module test(input clk, input rst);
    reg [7:0] counter;
    reg en;
    always @(posedge clk) begin
        if (rst) counter <= 0;
        else counter <= counter + 1;
    end
endmodule
"""
        hardened = """
module test(input clk, input rst);
    reg [7:0] counter;
    wire [7:0] counter_cnt_d;
    wire [7:0] counter_cnt_q;
    wire counter_cnt_error;
    cnt_comp_counter u_counter(.clk(clk), .rst(rst), .d(counter_cnt_d), .q(counter_cnt_q), .error_flag(counter_cnt_error));
    always @(posedge clk) begin
        if (rst) counter <= 0;
        else counter <= counter + 1;
    end
endmodule
"""
        result = self.hardener.incremental_update(orig, mod, hardened)
        self.assertEqual(result['update_type'], 'incremental')
        self.assertIn('en', result['added_signals'])
        self.assertIn('reg en;', result['updated_hardened'])
    
    def test_incremental_width_change(self):
        """信号宽度变更的增量更新"""
        orig = """
module test(input clk);
    reg [7:0] data;
    always @(posedge clk) data <= data + 1;
endmodule
"""
        mod = """
module test(input clk);
    reg [15:0] data;
    always @(posedge clk) data <= data + 1;
endmodule
"""
        hardened = """
module test(input clk);
    reg [7:0] data;
    always @(posedge clk) data <= data + 1;
endmodule
"""
        result = self.hardener.incremental_update(orig, mod, hardened)
        self.assertEqual(result['update_type'], 'incremental')
        self.assertIn('data', result['modified_signals'])
    
    def test_full_rehardening_on_structure_change(self):
        """结构变更触发全量更新"""
        orig = """
module test(input clk);
    reg [7:0] q;
    always @(posedge clk) q <= q + 1;
endmodule
"""
        mod = """
module test(input clk, input rst);
    reg [7:0] q;
    always @(posedge clk) begin
        if (rst) q <= 0;
        else q <= q + 1;
    end
endmodule
"""
        hardened = """
module test(input clk);
    reg [7:0] q_tmr;
    always @(posedge clk) q_tmr <= q_tmr + 1;
endmodule
"""
        result = self.hardener.incremental_update(orig, mod, hardened)
        self.assertEqual(result['update_type'], 'full')
        self.assertTrue(result['requires_full_rehardening'])
    
    def test_no_changes(self):
        """无变更时保持原样"""
        rtl = """
module test(input clk);
    reg [7:0] q;
always @(posedge clk) q <= q + 1;
endmodule
"""
        result = self.hardener.incremental_update(rtl, rtl, rtl)
        # 没有结构变更也没有信号变更，应为增量更新
        self.assertEqual(result['update_type'], 'incremental')
    
    def test_remove_signal_from_hardened(self):
        """删除信号从加固代码中移除"""
        orig = """
module test(input clk);
    reg [7:0] a;
    reg [7:0] b;
    always @(posedge clk) begin a <= a + 1; b <= b + 1; end
endmodule
"""
        mod = """
module test(input clk);
    reg [7:0] a;
    always @(posedge clk) a <= a + 1;
endmodule
"""
        hardened = """
module test(input clk);
    reg [7:0] a;
    reg [7:0] b;
    wire [7:0] b_tmr;
    always @(posedge clk) begin a <= a + 1; b <= b + 1; end
endmodule
"""
        result = self.hardener.incremental_update(orig, mod, hardened)
        self.assertEqual(result['update_type'], 'incremental')
        self.assertIn('b', result['removed_signals'])


class TestValidation(unittest.TestCase):
    """测试变更验证功能"""
    
    def setUp(self):
        self.hardener = IncrementalHardener()
    
    def test_validate_valid_change(self):
        """验证合法变更"""
        orig = """
module test(input clk);
    reg [7:0] q;
    always @(posedge clk) q <= q + 1;
endmodule
"""
        mod = """
module test(input clk);
    reg [15:0] q;
    always @(posedge clk) q <= q + 1;
endmodule
"""
        validation = self.hardener.validate_incremental_change(orig, mod)
        self.assertTrue(validation['is_valid'])
        self.assertEqual(len(validation['issues']), 0)
    
    def test_validate_invalid_change(self):
        """验证结构变更"""
        orig = """
module test(input clk);
    reg [7:0] q;
    always @(posedge clk) q <= q + 1;
endmodule
"""
        mod = """
module test(input clk, input rst);
    reg [7:0] q;
    always @(posedge clk) begin if (rst) q <= 0; else q <= q + 1; end
endmodule
"""
        validation = self.hardener.validate_incremental_change(orig, mod)
        self.assertFalse(validation['is_valid'])
        self.assertGreater(len(validation['issues']), 0)
    
    def test_validate_with_warnings(self):
        """验证带警告的变更"""
        orig = """
module test(input clk, input rst);
    reg [7:0] q;
    always @(posedge clk) begin if (rst) q <= 0; else q <= q + 1; end
endmodule
"""
        # 新增端口触发警告
        mod = """
module test(input clk, input rst, input [7:0] d);
    reg [7:0] q;
    always @(posedge clk) begin if (rst) q <= d; else q <= q + 1; end
endmodule
"""
        validation = self.hardener.validate_incremental_change(orig, mod)
        # 新增端口视为结构变更
        self.assertFalse(validation['is_valid'])


class TestPatchGeneration(unittest.TestCase):
    """测试增量补丁生成"""
    
    def setUp(self):
        self.hardener = IncrementalHardener()
    
    def test_patch_add_signal(self):
        """新增信号的补丁"""
        orig = """
module test(input clk);
    reg [7:0] a;
    endmodule
"""
        mod = """
module test(input clk);
    reg [7:0] a;
    reg [15:0] b;
    endmodule
"""
        patch = self.hardener.generate_incremental_patch(orig, mod)
        self.assertGreater(len(patch['changes']), 0)
        patch_types = [c['type'] for c in patch['changes']]
        self.assertIn('add_signal', patch_types)
    
    def test_patch_modify_signal(self):
        """修改信号的补丁"""
        orig = """
module test(input clk);
    reg [7:0] a;
    endmodule
"""
        mod = """
module test(input clk);
    reg [31:0] a;
    endmodule
"""
        patch = self.hardener.generate_incremental_patch(orig, mod)
        self.assertGreater(len(patch['changes']), 0)
        patch_types = [c['type'] for c in patch['changes']]
        self.assertIn('modify_signal', patch_types)
    
    def test_patch_no_cache(self):
        """无缓存时返回错误"""
        self.hardener._last_diff = None
        patch = self.hardener.generate_incremental_patch()
        self.assertIsNotNone(patch.get('error'))


class TestGetUpdateReport(unittest.TestCase):
    """测试更新报告"""
    
    def setUp(self):
        self.hardener = IncrementalHardener()
    
    def test_empty_report(self):
        """空报告"""
        report = self.hardener.get_update_report()
        self.assertEqual(report['total_updates'], 0)
    
    def test_report_with_updates(self):
        """有更新记录的报告"""
        rtl = """
module test(input clk);
    reg [7:0] q;
    always @(posedge clk) q <= q + 1;
endmodule
"""
        self.hardener.incremental_update(rtl, rtl, rtl)
        report = self.hardener.get_update_report()
        self.assertEqual(report['total_updates'], 1)
    
    def test_clear_history(self):
        """清空历史"""
        rtl = """
module test(input clk);
    reg [7:0] q;
    always @(posedge clk) q <= q + 1;
endmodule
"""
        self.hardener.incremental_update(rtl, rtl, rtl)
        self.assertEqual(self.hardener.get_update_report()['total_updates'], 1)
        self.hardener.clear_history()
        self.assertEqual(self.hardener.get_update_report()['total_updates'], 0)
        self.assertIsNone(self.hardener._last_diff)


class TestEdgeCases(unittest.TestCase):
    """测试边界情况"""
    
    def setUp(self):
        self.hardener = IncrementalHardener()
    
    def test_parse_width(self):
        """宽度解析函数"""
        cases = [
            ("[7:0]", 8), ("[0:7]", 8), ("[31:0]", 32),
            ("[1:0]", 2), (None, 1), ("1", 1),
        ]
        for width_str, expected_size in cases:
            with self.subTest(width_str=width_str):
                result = self.hardener._parse_width(width_str if width_str else "1")
                self.assertEqual(result['size'], expected_size)
    
    def test_generate_incremental_patch_integration(self):
        """incremental_update 后调用 patch"""
        orig = """
module test(input clk);
    reg [7:0] a;
    endmodule
"""
        mod = """
module test(input clk);
    reg [15:0] a;
    reg [7:0] b;
    endmodule
"""
        hardened = """
module test(input clk);
    reg [7:0] a;
    endmodule
"""
        result = self.hardener.incremental_update(orig, mod, hardened)
        patch = self.hardener.generate_incremental_patch()
        self.assertIsNotNone(patch)
        self.assertGreaterEqual(len(patch['changes']), 1)
        # modified_signals 应该包含 a
        self.assertIn('a', result.get('modified_signals', []))


if __name__ == '__main__':
    print("=" * 65)
    print("增量加固模块 单元测试")
    print("=" * 65)
    
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    
    test_classes = [
        TestParseModule,
        TestDiffModules,
        TestSignalLevelDiff,
        TestIncrementalUpdate,
        TestValidation,
        TestPatchGeneration,
        TestGetUpdateReport,
        TestEdgeCases,
    ]
    
    for tc in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(tc))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 65)
    print(f"测试结果: {result.testsRun} 测试用例, "
          f"{len(result.failures)} 失败, "
          f"{len(result.errors)} 错误")
    print("=" * 65)
    
    sys.exit(0 if result.wasSuccessful() else 1)
