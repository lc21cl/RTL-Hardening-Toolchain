#!/usr/bin/env python3
"""test_performance.py — 端到端性能基准测试

测量关键操作耗时，生成性能报告。
"""

import sys, os, time, json
sys.path.insert(0, '.')

from hardening_pipeline import HardeningPipeline

class PerformanceBenchmark:
    """性能基准测试"""
    
    def __init__(self):
        self.results = {}
    
    def run_all(self):
        self._benchmark('load_design')
        self._benchmark('analyze')
        self._benchmark('route + transform')
        self._benchmark('output')
        self._benchmark('fault_injection')
        
        self._print_report()
        self._save_report()
    
    def _benchmark(self, name):
        pipeline = HardeningPipeline(optimization_goal='balanced')
        times = []
        
        for i in range(5):
            start = time.perf_counter()
            pipeline.design_file = 'test_mock_data/mixed_design.v'
            pipeline.load_design(pipeline.design_file)
            pipeline.analyze()
            pipeline.route_strategies()
            pipeline.transform()
            pipeline.output('output/perf_test.v')
            elapsed = time.perf_counter() - start
            times.append(elapsed)
        
        avg = sum(times) / len(times)
        self.results[name] = {
            'times': times,
            'avg': round(avg, 4),
            'min': round(min(times), 4),
            'max': round(max(times), 4),
        }
    
    def _print_report(self):
        print("\n" + "=" * 60)
        print("性能基准测试报告")
        print("=" * 60)
        print(f"{'操作':25s} {'均值':>8s} {'最小':>8s} {'最大':>8s}")
        print("-" * 60)
        for name, data in self.results.items():
            print(f"{name:25s} {data['avg']:>8.4f}s {data['min']:>8.4f}s {data['max']:>8.4f}s")
    
    def _save_report(self):
        with open('output/perf_report.json', 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"报告已保存: output/perf_report.json")

if __name__ == '__main__':
    os.makedirs('output', exist_ok=True)
    bm = PerformanceBenchmark()
    bm.run_all()
