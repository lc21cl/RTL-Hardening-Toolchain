#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plugin_manager.py — 插件系统框架

支持外部加固策略的动态加载和注册。
每个插件是一个Python模块，包含一个 `register()` 函数。

用法:
    from plugin_manager import PluginManager
    pm = PluginManager()
    pm.load_plugins('./plugins')
    pm.apply_plugins(pipeline, strategy_map)
"""

import os, sys, json, time, importlib.util
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class PluginInfo:
    """插件元数据"""
    name: str
    version: str
    description: str
    author: str = "unknown"
    strategies: List[str] = field(default_factory=list)
    file_path: str = ""
    enabled: bool = True


class PluginManager:
    """插件管理器（v5.1新增）
    
    支持:
    - 从指定目录加载插件模块
    - 插件注册策略
    - 在加固管线中应用插件
    - 启用/禁用插件
    """
    
    def __init__(self, plugin_dir: str = None):
        if plugin_dir is None:
            plugin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins')
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, PluginInfo] = {}
        self._loaded_modules = {}
        os.makedirs(plugin_dir, exist_ok=True)
        print(f"[PLUGIN] 插件目录: {plugin_dir}")
    
    def discover_plugins(self) -> List[PluginInfo]:
        """扫描插件目录，发现所有可用插件"""
        discovered = []
        
        if not os.path.isdir(self.plugin_dir):
            return discovered
        
        for fname in sorted(os.listdir(self.plugin_dir)):
            if fname.endswith('.py') and not fname.startswith('_'):
                fpath = os.path.join(self.plugin_dir, fname)
                mod_name = fname[:-3]
                try:
                    spec = importlib.util.spec_from_file_location(mod_name, fpath)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        
                        # 检查是否包含 register 函数
                        if hasattr(mod, 'register'):
                            info_dict = mod.register() if callable(mod.register) else {}
                            info = PluginInfo(
                                name=info_dict.get('name', mod_name),
                                version=info_dict.get('version', '0.1'),
                                description=info_dict.get('description', ''),
                                author=info_dict.get('author', 'unknown'),
                                strategies=info_dict.get('strategies', []),
                                file_path=fpath,
                            )
                            discovered.append(info)
                            self.plugins[info.name] = info
                            self._loaded_modules[info.name] = mod
                            print(f"[PLUGIN] ✅ 加载: {info.name} v{info.version} ({info.description})")
                except Exception as e:
                    print(f"[PLUGIN] ⚠️ 加载失败 {fname}: {e}")
        
        return discovered
    
    def get_plugin_info(self, name: str) -> Optional[PluginInfo]:
        return self.plugins.get(name)
    
    def enable_plugin(self, name: str):
        if name in self.plugins:
            self.plugins[name].enabled = True
            print(f"[PLUGIN] 启用: {name}")
    
    def disable_plugin(self, name: str):
        if name in self.plugins:
            self.plugins[name].enabled = False
            print(f"[PLUGIN] 禁用: {name}")
    
    def apply_plugins(self, strategy_map: Dict[str, str], pipeline: Any = None) -> Dict[str, str]:
        """应用启用的插件到策略映射
        
        Args:
            strategy_map: {signal: strategy} 映射
            pipeline: 可选的pipeline实例
            
        Returns:
            更新后的策略映射
        """
        result = dict(strategy_map)
        
        for name, info in self.plugins.items():
            if not info.enabled:
                continue
            
            mod = self._loaded_modules.get(name)
            if mod and hasattr(mod, 'apply'):
                try:
                    modified = mod.apply(strategy_map, pipeline)
                    if modified:
                        result.update(modified)
                        print(f"[PLUGIN] 插件 {name} 已应用")
                except Exception as e:
                    print(f"[PLUGIN] ⚠️ 插件 {name} 应用失败: {e}")
        
        return result
    
    def list_plugins(self) -> List[PluginInfo]:
        return list(self.plugins.values())


# ── 示例插件 ──
SAMPLE_PLUGIN_CODE = '''#!/usr/bin/env python3
"""示例插件: 针对特定信号类型添加ABFT(算法级容错)加固策略"""

def register():
    return {
        'name': 'abft_extension',
        'version': '1.0',
        'description': 'ABFT算法级容错加固策略',
        'author': 'RTL Hardening Tool',
        'strategies': ['abft'],
    }

def apply(strategy_map, pipeline):
    """为矩阵运算信号添加ABFT策略"""
    import re
    modified = {}
    for sig, strategy in strategy_map.items():
        if any(kw in sig.lower() for kw in ['matrix', 'dot', 'conv', 'mm_', 'mac_']):
            modified[sig] = 'abft'
    return modified
'''

def install_sample_plugin(plugin_dir: str = None):
    """安装示例插件"""
    if plugin_dir is None:
        plugin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins')
    os.makedirs(plugin_dir, exist_ok=True)
    plugin_path = os.path.join(plugin_dir, 'abft_plugin.py')
    if not os.path.exists(plugin_path):
        with open(plugin_path, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_PLUGIN_CODE)
        print(f"[PLUGIN] 示例插件已安装: {plugin_path}")

# ── 入口 ──
if __name__ == '__main__':
    pm = PluginManager()
    install_sample_plugin()
    discovered = pm.discover_plugins()
    print(f"\n发现 {len(discovered)} 个插件:")
    for info in discovered:
        print(f"  - {info.name} v{info.version}: {info.description} (策略: {info.strategies})")
    
    # 测试应用
    test_map = {'matrix_a': 'parity', 'counter': 'tmr', 'dot_product': 'parity'}
    result = pm.apply_plugins(test_map, None)
    modified = [f"{k}:{v}" for k, v in result.items() if v != test_map.get(k)]
    print(f"\n插件应用后修改: {modified}")
    print(f"PluginManager: OK")
