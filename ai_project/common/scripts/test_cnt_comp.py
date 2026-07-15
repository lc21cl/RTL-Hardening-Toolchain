#!/usr/bin/env python3
"""
test_cnt_comp.py — cnt_comp 加固单元测试
"""
import unittest
import os
import subprocess
import sys

# 确保可以从项目根目录导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    import pyverilog.vparser.ast as vast
    HAVE_PYVERILOG = True
except ImportError:
    vast = None
    HAVE_PYVERILOG = False


class TestCntCompTemplate(unittest.TestCase):
    """测试 cnt_comp Verilog 模板语法和功能"""
    
    def setUp(self):
        self.mock_data_dir = os.path.join(
            os.path.dirname(__file__), 'test_mock_data'
        )
        self.template_file = os.path.join(self.mock_data_dir, 'cnt_comp_template.v')
        self.tb_file = os.path.join(self.mock_data_dir, 'tb_cnt_comp.v')
    
    def test_template_files_exist(self):
        """测试模板文件存在"""
        self.assertTrue(os.path.exists(self.template_file), 
                        f"Template file not found: {self.template_file}")
        self.assertTrue(os.path.exists(self.tb_file),
                        f"Testbench file not found: {self.tb_file}")
    
    def test_iverilog_compile(self):
        """测试 iverilog 编译通过"""
        sim_out = os.path.join(self.mock_data_dir, 'cnt_comp_sim')
        result = subprocess.run(
            ["iverilog", "-g2012", "-o", sim_out,
             self.template_file, self.tb_file],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, 
                         f"Compile failed:\n{result.stderr}")
        # 清理编译产物
        if os.path.exists(sim_out):
            os.remove(sim_out)
    
    def test_vvp_simulation(self):
        """测试仿真通过"""
        sim_out = os.path.join(self.mock_data_dir, 'cnt_comp_sim')
        
        # 先编译
        compile_result = subprocess.run(
            ["iverilog", "-g2012", "-o", sim_out,
             self.template_file, self.tb_file],
            capture_output=True, text=True
        )
        if compile_result.returncode != 0:
            self.skipTest(f"Compile failed, cannot run simulation:\n{compile_result.stderr}")
        
        # 运行仿真
        result = subprocess.run(
            ["vvp", sim_out],
            capture_output=True, text=True
        )
        
        # 清理
        if os.path.exists(sim_out):
            os.remove(sim_out)
        
        self.assertIn("PASS", result.stdout,
                      f"Simulation output missing PASS:\n{result.stdout}")
        # 检查是否有测试失败 (排除汇总行中的 "0 FAIL" 字样)
        fail_lines = [l for l in result.stdout.split('\n') if l.startswith('FAIL:') or l.startswith('FAIL ')]
        self.assertEqual(0, len(fail_lines),
                         f"Simulation reported FAIL:\n" + '\n'.join(fail_lines))


class TestCounterDetector(unittest.TestCase):
    """测试计数器模式检测"""
    
    def setUp(self):
        if not HAVE_PYVERILOG:
            self.skipTest("pyverilog not installed")
    
    def test_up_counter_detection(self):
        """测试递增计数器检测"""
        from cnt_comp_transformer import CounterDetector
        
        # Mock AST for reg <= reg + 1
        result = CounterDetector._match_counter_pattern(
            vast.Plus(vast.Identifier("cnt"), vast.IntConst("1"))
        )
        self.assertIsNotNone(result)
        self.assertEqual(result, CounterDetector.UP_COUNTER)
    
    def test_down_counter_detection(self):
        """测试递减计数器检测"""
        from cnt_comp_transformer import CounterDetector
        
        result = CounterDetector._match_counter_pattern(
            vast.Minus(vast.Identifier("cnt"), vast.IntConst("1"))
        )
        self.assertIsNotNone(result)
        self.assertEqual(result, CounterDetector.DOWN_COUNTER)
    
    def test_mod_counter_detection(self):
        """测试模计数器检测"""
        from cnt_comp_transformer import CounterDetector
        
        # 构造 reg <= (cnt == MAX) ? 0 : cnt + 1 的 AST
        cond = vast.Cond(
            vast.Eq(vast.Identifier("cnt"), vast.Identifier("MAX")),
            vast.IntConst("0"),
            vast.Plus(vast.Identifier("cnt"), vast.IntConst("1"))
        )
        result = CounterDetector._match_counter_pattern(cond)
        self.assertIsNotNone(result)
        self.assertEqual(result, CounterDetector.MOD_COUNTER)
    
    def test_non_counter_not_detected(self):
        """测试非计数器模式不被误检"""
        from cnt_comp_transformer import CounterDetector
        
        # reg <= a + b (不是自加1)
        result = CounterDetector._match_counter_pattern(
            vast.Plus(vast.Identifier("a"), vast.Identifier("b"))
        )
        self.assertIsNone(result)
        
        # reg <= reg + 2 (不是加1)
        result = CounterDetector._match_counter_pattern(
            vast.Plus(vast.Identifier("reg"), vast.IntConst("2"))
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
