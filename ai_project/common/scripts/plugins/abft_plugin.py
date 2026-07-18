#!/usr/bin/env python3
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
