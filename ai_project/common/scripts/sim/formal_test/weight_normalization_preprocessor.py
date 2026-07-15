import os
import sys
import json
import torch
import torch.nn as nn
from torch_geometric.nn import SAGEConv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'data', 'fpga')
os.makedirs(OUTPUT_DIR, exist_ok=True)


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


class WeightNormalizationPreprocessor:
    def __init__(self, method='layer_norm', target_range=1.0):
        self.method = method
        self.target_range = target_range
        self.norm_factors = {}

    def analyze_weights(self, model):
        print('\n  --- Weight Analysis Before Normalization ---')
        weight_stats = {}
        for name, param in model.state_dict().items():
            if 'weight' in name:
                min_val = param.min().item()
                max_val = param.max().item()
                mean_val = param.mean().item()
                std_val = param.std().item()
                abs_max = max(abs(min_val), abs(max_val))
                
                weight_stats[name] = {
                    'min': round(min_val, 4),
                    'max': round(max_val, 4),
                    'mean': round(mean_val, 4),
                    'std': round(std_val, 4),
                    'abs_max': round(abs_max, 4),
                    'range': round(max_val - min_val, 4),
                }
                
                print(f'    {name}:')
                print(f'      Min: {min_val:.4f}, Max: {max_val:.4f}, Range: {max_val - min_val:.4f}')
                print(f'      Mean: {mean_val:.4f}, Std: {std_val:.4f}, AbsMax: {abs_max:.4f}')
        
        return weight_stats

    def normalize_layer(self, weight, method=None):
        if method is None:
            method = self.method
        
        if method == 'layer_norm':
            scale = weight.std()
            if scale > 0:
                normalized = weight / scale
                self.norm_factors['scale'] = float(scale)
            else:
                normalized = weight
                self.norm_factors['scale'] = 1.0
        
        elif method == 'range_norm':
            abs_max = torch.max(torch.abs(weight))
            if abs_max > 0:
                normalized = weight / abs_max * self.target_range
                self.norm_factors['scale'] = float(abs_max / self.target_range)
            else:
                normalized = weight
                self.norm_factors['scale'] = 1.0
        
        elif method == 'max_norm':
            max_val = weight.max()
            min_val = weight.min()
            range_val = max_val - min_val
            if range_val > 0:
                normalized = (weight - min_val) / range_val * 2 - 1
                normalized = normalized * self.target_range
                self.norm_factors['scale'] = float(range_val / 2)
                self.norm_factors['shift'] = float(min_val)
            else:
                normalized = weight
                self.norm_factors['scale'] = 1.0
                self.norm_factors['shift'] = 0.0
        
        elif method == 'quantization_aware':
            abs_max = torch.max(torch.abs(weight))
            num_bits = 8
            max_int = 2 ** (num_bits - 1) - 1
            if abs_max > 0:
                scale = abs_max / max_int
                normalized = weight / scale
                normalized = torch.clamp(normalized, -max_int, max_int)
                normalized = normalized * scale
                self.norm_factors['scale'] = float(scale)
                self.norm_factors['max_int'] = max_int
            else:
                normalized = weight
                self.norm_factors['scale'] = 1.0
        
        return normalized

    def normalize_model(self, model):
        print(f'\n  --- Applying {self.method.upper()} Weight Normalization ---')
        normalized_state = {}
        self.norm_factors = {}
        
        for name, param in model.state_dict().items():
            if 'weight' in name:
                print(f'    Normalizing: {name}')
                normalized = self.normalize_layer(param)
                normalized_state[name] = normalized
                min_val = normalized.min().item()
                max_val = normalized.max().item()
                print(f'      After: Min={min_val:.4f}, Max={max_val:.4f}, Range={max_val-min_val:.4f}')
            else:
                normalized_state[name] = param
        
        model.load_state_dict(normalized_state)
        return model

    def save_norm_factors(self, filepath):
        with open(filepath, 'w') as f:
            json.dump(self.norm_factors, f, indent=2)
        print(f'  Normalization factors saved to: {filepath}')


def apply_weight_normalization():
    print('=' * 70)
    print('  Weight Normalization Preprocessor - SAGE2-Lite-64')
    print('=' * 70)

    model = SAGE2Lite(in_channels=15, hidden_channels=64)
    model_path = os.path.join(MODEL_DIR, 'SAGE2-Lite-64.pth')
    
    if not os.path.exists(model_path):
        print(f'  ⚠️ Model file not found: {model_path}')
        return

    model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
    model = model.to('cpu')
    model.eval()

    num_params = sum(p.numel() for p in model.parameters())
    print(f'\n  Model: SAGE2-Lite-64')
    print(f'  Parameters: {num_params:,}')

    preprocessor = WeightNormalizationPreprocessor()
    original_stats = preprocessor.analyze_weights(model)

    methods = ['layer_norm', 'range_norm', 'max_norm', 'quantization_aware']
    results = {'original': original_stats}

    for method in methods:
        model_copy = SAGE2Lite(in_channels=15, hidden_channels=64)
        model_copy.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
        model_copy = model_copy.to('cpu')
        
        preprocessor = WeightNormalizationPreprocessor(method=method)
        normalized_model = preprocessor.normalize_model(model_copy)
        
        norm_path = os.path.join(OUTPUT_DIR, f'sage2_lite_64_normalized_{method}.pth')
        torch.save(normalized_model.state_dict(), norm_path)
        print(f'  Normalized model saved to: {norm_path}')
        
        factors_path = os.path.join(OUTPUT_DIR, f'norm_factors_{method}.json')
        preprocessor.save_norm_factors(factors_path)
        
        after_stats = preprocessor.analyze_weights(normalized_model)
        results[method] = after_stats

    results_path = os.path.join(OUTPUT_DIR, 'weight_normalization_results.json')
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  All results saved to: {results_path}')

    print('\n  --- Summary of Normalization Effects ---')
    print(f'  {"Method":<20} {"Max Weight Range":<20} {"Max AbsMax":<20}')
    print(f'  {"-"*60}')
    print(f'  {"Original":<20} {max(s["range"] for s in original_stats.values()):<20.4f} {max(s["abs_max"] for s in original_stats.values()):<20.4f}')
    
    for method in methods:
        stats = results[method]
        print(f'  {method:<20} {max(s["range"] for s in stats.values()):<20.4f} {max(s["abs_max"] for s in stats.values()):<20.4f}')

    return results


if __name__ == '__main__':
    apply_weight_normalization()
