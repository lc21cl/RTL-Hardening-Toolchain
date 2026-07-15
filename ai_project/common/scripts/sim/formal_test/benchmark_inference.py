import os
import sys
import time
import json
import torch
import torch.nn as nn
import numpy as np
from torch_geometric.nn import SAGEConv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data_15feat.pt')
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'data')


class SAGE3(nn.Module):
    def __init__(self, in_channels=15, hidden_channels=32, dropout=0.3):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.conv3 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels // 2, 8), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(8, 1),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv2(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv3(x, edge_index).relu(); x = self.dropout(x)
        return self.mlp(x).squeeze(-1)


class SAGE2Lite(nn.Module):
    def __init__(self, in_channels=15, hidden_channels=64, dropout=0.2):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels // 2, 8), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(8, 1),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv2(x, edge_index).relu(); x = self.dropout(x)
        return self.mlp(x).squeeze(-1)


def benchmark_model(model, data, device, num_runs=10):
    model = model.to(device)
    model.eval()

    total_time = 0.0
    total_nodes = 0
    inference_times = []

    with torch.no_grad():
        for run in range(num_runs):
            for graph in data:
                graph = graph.to(device)
                start_time = time.perf_counter()
                logits = model(graph.x, graph.edge_index)
                _ = torch.sigmoid(logits)
                end_time = time.perf_counter()
                
                elapsed = (end_time - start_time) * 1000
                total_time += elapsed
                total_nodes += graph.x.shape[0]
                inference_times.append(elapsed)

    avg_time = total_time / len(data) / num_runs
    avg_per_node = total_time / total_nodes * 1000
    min_time = min(inference_times)
    max_time = max(inference_times)
    std_time = np.std(inference_times)

    return {
        'avg_time_ms': round(avg_time, 3),
        'avg_per_node_ms': round(avg_per_node, 4),
        'min_time_ms': round(min_time, 3),
        'max_time_ms': round(max_time, 3),
        'std_time_ms': round(std_time, 3),
        'total_nodes': total_nodes,
        'num_graphs': len(data) * num_runs,
    }


def main():
    print('=' * 68)
    print('  Inference Latency Benchmark')
    print('=' * 68)

    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    test_data = raw['test']
    print(f'  Test data: {len(test_data)} graphs')

    device = torch.device('cpu')
    print(f'  Device: {device}')

    models_to_test = [
        {
            'name': 'SAGE2-Lite-64 (Optimized)',
            'class': SAGE2Lite,
            'hidden': 64,
            'model_path': os.path.join(MODEL_DIR, 'SAGE2-Lite-64.pth'),
            'description': 'Optimized 2-layer model with 64 hidden channels',
        },
        {
            'name': 'SAGE2-Lite-32 (Lightweight)',
            'class': SAGE2Lite,
            'hidden': 32,
            'model_path': os.path.join(MODEL_DIR, 'SAGE2-Lite-32.pth'),
            'description': 'Lightweight 2-layer model with 32 hidden channels',
        },
        {
            'name': 'SAGE3-Lite-32 (3-layer)',
            'class': SAGE3,
            'hidden': 32,
            'model_path': os.path.join(MODEL_DIR, 'SAGE3-Lite-32.pth'),
            'description': '3-layer model with 32 hidden channels',
        },
    ]

    results = []

    for mcfg in models_to_test:
        print(f'\n{"-" * 68}')
        print(f'  {mcfg["name"]}')
        print(f'  {mcfg["description"]}')
        print(f'{"-" * 68}')

        if not os.path.exists(mcfg['model_path']):
            print(f'  ⚠️ Model file not found: {mcfg["model_path"]}')
            print(f'  Skipping...')
            continue

        model = mcfg['class'](in_channels=15, hidden_channels=mcfg['hidden'])
        model.load_state_dict(torch.load(mcfg['model_path'], map_location='cpu', weights_only=True))
        
        num_params = sum(p.numel() for p in model.parameters())
        print(f'  Parameters: {num_params:,}')

        bench_result = benchmark_model(model, test_data, device, num_runs=3)
        
        results.append({
            'name': mcfg['name'],
            'parameters': num_params,
            'hidden_channels': mcfg['hidden'],
            **bench_result,
        })

        print(f'  Average time per graph: {bench_result["avg_time_ms"]:.3f} ms')
        print(f'  Time per node: {bench_result["avg_per_node_ms"]:.4f} ms')
        print(f'  Min/Max: {bench_result["min_time_ms"]:.3f} / {bench_result["max_time_ms"]:.3f} ms')
        print(f'  Std: {bench_result["std_time_ms"]:.3f} ms')

    print(f'\n{"=" * 68}')
    print('  Benchmark Results Summary')
    print(f'{"=" * 68}')

    print('\n  Model                          Params    Avg(ms)  PerNode(ms)  Min(ms)  Max(ms)  Std(ms)')
    print('  ' + '-' * 95)
    for r in results:
        print(f'  {r["name"]:40} {r["parameters"]:9,} {r["avg_time_ms"]:9.3f} {r["avg_per_node_ms"]:12.4f} '
              f'{r["min_time_ms"]:8.3f} {r["max_time_ms"]:8.3f} {r["std_time_ms"]:8.3f}')

    print('\n  Real-time Requirement Check:')
    print('  ' + '-' * 68)
    for r in results:
        meets_rt = r['avg_time_ms'] < 100
        status = '✅' if meets_rt else '❌'
        print(f'  {status} {r["name"]:40} - Avg: {r["avg_time_ms"]:.3f} ms {"(Meets <100ms)" if meets_rt else "(Exceeds 100ms)"}')

    result_path = os.path.join(OUTPUT_DIR, 'inference_benchmark.json')
    with open(result_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  Results saved to: {result_path}')

    return results


if __name__ == '__main__':
    main()
