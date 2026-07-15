import os
import sys
import json
import torch
import torch.nn as nn
import numpy as np
from torch_geometric.nn import SAGEConv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data_15feat.pt')
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


class INT16Quantizer:
    def __init__(self, symmetric=True):
        self.scale_factor = {}
        self.zero_point = {}
        self.symmetric = symmetric

    def quantize_weight(self, weight):
        min_val = weight.min().item()
        max_val = weight.max().item()
        
        if self.symmetric:
            abs_max = max(abs(min_val), abs(max_val))
            if abs_max == 0:
                scale = 1.0
            else:
                scale = abs_max / 32767.0
            zero_point = 0
            quantized = torch.clamp((weight / scale).round(), -32768, 32767).short()
        else:
            if max_val == min_val:
                scale = 1.0
                zero_point = 0
            else:
                scale = (max_val - min_val) / 65535.0
                zero_point = int(-min_val / scale)
                zero_point = max(-32768, min(32767, zero_point))
            quantized = torch.clamp((weight / scale + zero_point).round(), -32768, 32767).short()
        
        return quantized, scale, zero_point

    def quantize_model(self, model):
        quantized_params = {}
        for name, param in model.state_dict().items():
            if 'weight' in name:
                quantized, scale, zero_point = self.quantize_weight(param)
                quantized_params[name] = {
                    'data': quantized.numpy().tolist(),
                    'scale': float(scale),
                    'zero_point': int(zero_point),
                    'shape': list(param.shape),
                    'type': 'weight',
                    'symmetric': self.symmetric,
                }
            else:
                quantized, scale, zero_point = self.quantize_weight(param)
                quantized_params[name] = {
                    'data': quantized.numpy().tolist(),
                    'scale': float(scale),
                    'zero_point': int(zero_point),
                    'shape': list(param.shape),
                    'type': 'bias',
                    'symmetric': self.symmetric,
                }
            self.scale_factor[name] = quantized_params[name]['scale']
            self.zero_point[name] = quantized_params[name]['zero_point']
        return quantized_params


class INT16Inference:
    def __init__(self, model, quantized_params):
        self.model = model
        self.quantized_params = quantized_params
        self.device = torch.device('cpu')
        self.dequantized_weights = {}
        for name, param in quantized_params.items():
            q_data = torch.tensor(param['data'], dtype=torch.float32)
            self.dequantized_weights[name] = (q_data - param['zero_point']) * param['scale']

    def forward_int16(self, x, edge_index):
        x = x.to(self.device)
        edge_index = edge_index.to(self.device)

        conv1_l_weight = self.dequantized_weights['conv1.lin_l.weight'].to(self.device)
        conv1_r_weight = self.dequantized_weights['conv1.lin_r.weight'].to(self.device)
        conv1_bias = self.dequantized_weights['conv1.lin_l.bias'].to(self.device)
        
        conv2_l_weight = self.dequantized_weights['conv2.lin_l.weight'].to(self.device)
        conv2_r_weight = self.dequantized_weights['conv2.lin_r.weight'].to(self.device)
        conv2_bias = self.dequantized_weights['conv2.lin_l.bias'].to(self.device)
        
        mlp0_weight = self.dequantized_weights['mlp.0.weight'].to(self.device)
        mlp0_bias = self.dequantized_weights['mlp.0.bias'].to(self.device)
        mlp3_weight = self.dequantized_weights['mlp.3.weight'].to(self.device)
        mlp3_bias = self.dequantized_weights['mlp.3.bias'].to(self.device)

        h0 = x

        conv1_l_out = h0 @ conv1_l_weight.t()
        conv1_r_out = h0 @ conv1_r_weight.t()
        
        num_nodes = h0.size(0)
        src, dst = edge_index
        conv1_r_agg = torch.zeros(num_nodes, conv1_r_out.size(1), device=self.device)
        conv1_r_agg.index_add_(0, dst, conv1_r_out[src])
        deg = torch.bincount(dst, minlength=num_nodes).float().clamp(min=1).view(-1, 1)
        conv1_r_agg = conv1_r_agg / deg
        
        h1 = torch.relu(conv1_l_out + conv1_r_agg + conv1_bias)

        conv2_l_out = h1 @ conv2_l_weight.t()
        conv2_r_out = h1 @ conv2_r_weight.t()
        
        conv2_r_agg = torch.zeros(num_nodes, conv2_r_out.size(1), device=self.device)
        conv2_r_agg.index_add_(0, dst, conv2_r_out[src])
        conv2_r_agg = conv2_r_agg / deg
        
        h2 = torch.relu(conv2_l_out + conv2_r_agg + conv2_bias)

        h3 = torch.relu(h2 @ mlp0_weight.t() + mlp0_bias)

        out = h3 @ mlp3_weight.t() + mlp3_bias

        return out


def compute_metrics(logits, labels, threshold=0.5):
    preds = (torch.sigmoid(logits) >= threshold).float()
    tp = (preds * labels).sum().item()
    fp = (preds * (1 - labels)).sum().item()
    fn = ((1 - preds) * labels).sum().item()
    tn = ((1 - preds) * (1 - labels)).sum().item()

    precision = tp / (tp + fp + 1e-8)
    recall = tp / (tp + fn + 1e-8)
    f1 = 2 * precision * recall / (precision + recall + 1e-8)
    acc = (tp + tn) / (tp + fp + fn + tn + 1e-8)

    return {
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1': round(f1, 4),
        'accuracy': round(acc, 4),
        'tp': int(tp), 'fp': int(fp), 'fn': int(fn), 'tn': int(tn),
    }


def find_best_threshold(val_scores, val_labels):
    best_th = 0.5
    best_f1 = 0.0
    for th in [x / 100 for x in range(5, 96, 1)]:
        m = compute_metrics(val_scores, val_labels, threshold=th)
        if m['f1'] > best_f1:
            best_f1 = m['f1']
            best_th = th
    return best_th, best_f1


def test_quantization():
    print('=' * 70)
    print('  INT16 Quantization Accuracy Test - SAGE2-Lite-64')
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

    if not os.path.exists(DATA_PATH):
        print(f'  ⚠️ Data file not found: {DATA_PATH}')
        return

    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    val_data = raw['val']
    test_data = raw['test']
    print(f'  Val data: {len(val_data)} graphs')
    print(f'  Test data: {len(test_data)} graphs')

    results = {}
    
    for symmetric in [True, False]:
        print(f'\n  --- {"Symmetric" if symmetric else "Asymmetric"} INT16 Quantization ---')
        quantizer = INT16Quantizer(symmetric=symmetric)
        quantized_params = quantizer.quantize_model(model)

        quant_path = os.path.join(OUTPUT_DIR, f'quantized_weights_sage2_lite_64_int16_{"sym" if symmetric else "asym"}.json')
        with open(quant_path, 'w') as f:
            json.dump(quantized_params, f, indent=2)
        print(f'  Quantized weights saved to: {quant_path}')

        int16_infer = INT16Inference(model, quantized_params)

        print('\n  --- Running Validation for Threshold Tuning ---')
        val_fp32 = []
        val_int16 = []
        val_labels = []
        with torch.no_grad():
            for graph in val_data:
                graph = graph.to('cpu')
                val_fp32.append(model(graph.x, graph.edge_index))
                val_int16.append(int16_infer.forward_int16(graph.x, graph.edge_index).squeeze())
                val_labels.append(graph.y)
        val_fp32 = torch.cat(val_fp32)
        val_int16 = torch.cat(val_int16)
        val_labels = torch.cat(val_labels)

        fp32_th, fp32_val_f1 = find_best_threshold(val_fp32, val_labels)
        int16_th, int16_val_f1 = find_best_threshold(val_int16, val_labels)
        print(f'  FP32 Best Threshold: {fp32_th:.2f} (Val F1={fp32_val_f1:.4f})')
        print(f'  INT16 Best Threshold: {int16_th:.2f} (Val F1={int16_val_f1:.4f})')

        print('\n  --- Running Test Inference ---')
        test_fp32 = []
        test_int16 = []
        test_labels = []
        with torch.no_grad():
            for i, graph in enumerate(test_data):
                if i % 50 == 0:
                    print(f'    Processing graph {i}/{len(test_data)}...')
                
                graph = graph.to('cpu')
                test_fp32.append(model(graph.x, graph.edge_index))
                test_int16.append(int16_infer.forward_int16(graph.x, graph.edge_index).squeeze())
                test_labels.append(graph.y)

        test_fp32 = torch.cat(test_fp32)
        test_int16 = torch.cat(test_int16)
        test_labels = torch.cat(test_labels)

        print('\n  --- Computing Metrics ---')
        fp32_metrics = compute_metrics(test_fp32, test_labels, threshold=fp32_th)
        int16_metrics_same_th = compute_metrics(test_int16, test_labels, threshold=fp32_th)
        int16_metrics_own_th = compute_metrics(test_int16, test_labels, threshold=int16_th)

        print('\n  FP32 Metrics (th=%s):' % fp32_th)
        print(f'    Precision: {fp32_metrics["precision"]:.4f}')
        print(f'    Recall:    {fp32_metrics["recall"]:.4f}')
        print(f'    F1:        {fp32_metrics["f1"]:.4f}')
        print(f'    Accuracy:  {fp32_metrics["accuracy"]:.4f}')

        print('\n  INT16 Metrics (same th=%s):' % fp32_th)
        print(f'    Precision: {int16_metrics_same_th["precision"]:.4f}')
        print(f'    Recall:    {int16_metrics_same_th["recall"]:.4f}')
        print(f'    F1:        {int16_metrics_same_th["f1"]:.4f}')
        print(f'    Accuracy:  {int16_metrics_same_th["accuracy"]:.4f}')

        print('\n  INT16 Metrics (own th=%s):' % int16_th)
        print(f'    Precision: {int16_metrics_own_th["precision"]:.4f}')
        print(f'    Recall:    {int16_metrics_own_th["recall"]:.4f}')
        print(f'    F1:        {int16_metrics_own_th["f1"]:.4f}')
        print(f'    Accuracy:  {int16_metrics_own_th["accuracy"]:.4f}')

        print('\n  --- Accuracy Loss Analysis (Same Threshold) ---')
        f1_loss = fp32_metrics['f1'] - int16_metrics_same_th['f1']
        acc_loss = fp32_metrics['accuracy'] - int16_metrics_same_th['accuracy']
        
        print(f'    F1 Loss:   {f1_loss*100:.4f}%')
        print(f'    Acc Loss:  {acc_loss*100:.4f}%')

        max_abs_diff = torch.max(torch.abs(test_fp32 - test_int16)).item()
        avg_abs_diff = torch.mean(torch.abs(test_fp32 - test_int16)).item()
        std_abs_diff = torch.std(torch.abs(test_fp32 - test_int16)).item()
        
        print(f'\n  --- Output Difference Analysis ---')
        print(f'    Max Absolute Difference: {max_abs_diff:.6f}')
        print(f'    Avg Absolute Difference: {avg_abs_diff:.6f}')
        print(f'    Std Absolute Difference: {std_abs_diff:.6f}')

        print('\n  --- Quantization Acceptance Check ---')
        f1_acceptable = f1_loss < 0.01
        acc_acceptable = acc_loss < 0.01
        diff_acceptable = max_abs_diff < 0.1

        print(f'    F1 Loss < 1%:       {"✅ PASS" if f1_acceptable else "❌ FAIL"}')
        print(f'    Accuracy Loss < 1%: {"✅ PASS" if acc_acceptable else "❌ FAIL"}')
        print(f'    Max Diff < 0.1:     {"✅ PASS" if diff_acceptable else "❌ FAIL"}')

        all_pass = f1_acceptable and acc_acceptable and diff_acceptable
        print(f'\n    Overall:            {"✅ ALL CHECKS PASSED" if all_pass else "❌ SOME CHECKS FAILED"}')

        fp32_bytes = sum(p.numel() * 4 for p in model.parameters())
        int16_bytes = sum(p.numel() * 2 for p in model.parameters())
        memory_saving = (1 - int16_bytes / fp32_bytes) * 100
        
        print(f'\n  --- Memory Analysis ---')
        print(f'    FP32 Memory: {fp32_bytes:,} bytes')
        print(f'    INT16 Memory: {int16_bytes:,} bytes')
        print(f'    Memory Saving: {memory_saving:.1f}%')

        key = 'symmetric' if symmetric else 'asymmetric'
        results[key] = {
            'fp32_metrics': fp32_metrics,
            'int16_metrics_same_th': int16_metrics_same_th,
            'int16_metrics_own_th': int16_metrics_own_th,
            'accuracy_loss': {
                'f1_loss': f1_loss,
                'acc_loss': acc_loss,
            },
            'output_difference': {
                'max_abs_diff': max_abs_diff,
                'avg_abs_diff': avg_abs_diff,
                'std_abs_diff': std_abs_diff,
            },
            'acceptance': {
                'f1_acceptable': f1_acceptable,
                'acc_acceptable': acc_acceptable,
                'diff_acceptable': diff_acceptable,
                'all_pass': all_pass,
            },
            'memory_analysis': {
                'fp32_bytes': fp32_bytes,
                'int16_bytes': int16_bytes,
                'memory_saving': memory_saving,
            },
        }

    results['model'] = 'SAGE2-Lite-64'
    results['num_params'] = num_params
    results['num_graphs'] = len(test_data)

    result_path = os.path.join(OUTPUT_DIR, 'int16_quantization_test_results.json')
    with open(result_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  Results saved to: {result_path}')

    return results


if __name__ == '__main__':
    test_quantization()
