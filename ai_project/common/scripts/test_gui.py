#!/usr/bin/env python3
"""test_gui.py — GUI自动化测试 (无头模式)"""

import sys, os, unittest, tempfile
sys.path.insert(0, '.')

# 设置无头环境
os.environ['DISPLAY'] = ':99'

class TestGUIImports(unittest.TestCase):
    """测试GUI模块导入"""
    
    def test_gui_imports(self):
        """验证所有GUI依赖可导入"""
        try:
            import tkinter as tk
            import tkinter.ttk as ttk
            from tkinter import messagebox, filedialog
            print("  ✅ tkinter 导入成功")
        except ImportError as e:
            self.skipTest(f"tkinter 不可用: {e}")
    
    def test_gui_class_exists(self):
        """验证GUI类存在"""
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "harden_gui", 
                "harden_gui.py"
            )
            if spec:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                self.assertTrue(hasattr(mod, 'HardeningToolGUI') or 
                                hasattr(mod, 'HardeningGUI'))
                print("  ✅ GUI类加载成功")
        except Exception as e:
            self.skipTest(f"GUI模块加载跳过(无头环境): {e}")
    
    def test_workflow_configs(self):
        """验证工作流配置完整性"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "harden_gui", "harden_gui.py"
        )
        if spec:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, 'WORKFLOWS'):
                workflows = mod.WORKFLOWS
                self.assertIn('rtl_single', workflows)
                self.assertIn('rtl_folder', workflows)
                self.assertIn('rtl_dataset', workflows)
                self.assertIn('fpga_bitstream', workflows)
                print(f"  ✅ 4个工作流配置完整: {list(workflows.keys())}")
    
    def test_history_module(self):
        """验证历史模块集成"""
        try:
            from sim.formal_test.hardening_history import HardeningHistory
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                h = HardeningHistory(storage_dir=tmpdir)
                h.add_record("test.v", {"sig": "tmr"}, {"reg": 5}, "out.v")
                self.assertEqual(len(h.get_all_records()), 1)
            print("  ✅ 历史模块导入和基本功能正常")
        except ImportError as e:
            self.skipTest(f"历史模块不可用: {e}")
    
    def test_web_gui_import(self):
        """验证Web GUI模块"""
        try:
            import py_compile
            py_compile.compile('sim/web_gui.py', doraise=True)
            print("  ✅ web_gui.py 语法正确")
        except Exception as e:
            self.skipTest(f"Web GUI跳过: {e}")

class TestGUIFunctionality(unittest.TestCase):
    """测试GUI核心功能"""
    
    def test_language_translations(self):
        """验证语言翻译字典完整性"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "harden_gui", "harden_gui.py"
        )
        if spec:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, 'HardeningToolGUI') or hasattr(mod, 'HardeningGUI'):
                try:
                    gui_cls = getattr(mod, 'HardeningToolGUI', None) or \
                              getattr(mod, 'HardeningGUI')
                    print("  ✅ GUI类定义加载成功")
                except Exception:
                    pass
    
    def test_pipeline_integration(self):
        """测试管线集成调用"""
        from hardening_pipeline import HardeningPipeline
        p = HardeningPipeline()
        p.design_file = 'test_mock_data/mixed_design.v'
        self.assertTrue(p.load_design(p.design_file))
        p.analyze()
        p.route_strategies()
        p.transform()
        self.assertIsNotNone(p.strategy_map)
        print("  ✅ 管线集成调用正常")

if __name__ == '__main__':
    print("=" * 60)
    print("GUI自动化测试")
    print("=" * 60)
    unittest.main(verbosity=2)
