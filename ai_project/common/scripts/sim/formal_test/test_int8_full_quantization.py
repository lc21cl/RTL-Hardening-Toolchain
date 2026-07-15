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


class FullINT8Quantizer:
    def __init__(self, symmetric=True):
        self.symmetric = symmetric
        self.weight_params = {}
        self.activation_params = {}

    def quantize_tensor(self, tensor):
        min_val = tensor.min().item()
        max_val = tensor.max().item()
        
        if self.symmetric:
            abs_max = max(abs(min_val), abs(max_val))
            if abs_max == 0:
                scale = 1.0
            else:
                scale = abs_max / 127.0
            zero_point = 0
            quantized = torch.clamp((tensor / scale).round(), -127, 127).char()
        else:
            if max_val == min_val:
                scale = 1.0
                zero_point = 128
            else:
                scale = (max_val - min_val) / 255.0
                zero_point = int(-min_val / scale)
                zero_point = max(0, min(255, zero_point))
            quantized = torch.clamp((tensor / scale + zero_point).round(), 0, 255).byte()
        
        return quantized, scale, zero_point

    def dequantize_tensor(self, quantized, scale, zero_point):
        return (quantized.float() - zero_point) * scale

    def quantize_model(self, model):
        self.weight_params = {}
        for name, param in model.state_dict().items():
            if 'weight' in name:
                quantized, scale, zero_point = self.quantize_tensor(param)
                self.weight_params[name] = {
                    'data': quantized.numpy().tolist(),
                    'scale': float(scale),
                    'zero_point': int(zero_point),
                    'shape': list(param.shape),
                }
            else:
                quantized, scale, zero_point = self.quantize_tensor(param)
                self.weight_params[name] = {
                    'data': quantized.numpy().tolist(),
                    'scale': float(scale),
                    'zero_point': int(zero_point),
                    'shape': list(param.shape),
                }
        return self.weight_params

    def calibrate_activations(self, model, data_loader):
        model.eval()
        activation_stats = {
            'h0': [], 'h1': [], 'h2': [], 'h3': [], 'out': []
        }
        
        with torch.no_grad():
            for graph in data_loader:
                x = graph.x
                edge_index = graph.edge_index
                
                h0 = x
                activation_stats['h0'].append(h0)
                
                conv1_l_out = x @ model.conv1.lin_l.weight.t()
                conv1_r_out = x @ model.conv1.lin_r.weight.t()
                num_nodes = x.size(0)
                src, dst = edge_index
                conv1_r_agg = torch.zeros(num_nodes, conv1_r_out.size(1))
                conv1_r_agg.index_add_(0, dst, conv1_r_out[src])
                deg = torch.bincount(dst, minlength=num_nodes).float().clamp(min=1).view(-1, 1)
                conv1_r_agg = conv1_r_agg / deg
                h1 = torch.relu(conv1_l_out + conv1_r_agg + model.conv1.lin_l.bias)
                activation_stats['h1'].append(h1)
                
                conv2_l_out = h1 @ model.conv2.lin_l.weight.t()
                conv2_r_out = h1 @ model.conv2.lin_r.weight.t()
                conv2_r_agg = torch.zeros(num_nodes, conv2_r_out.size(1))
                conv2_r_agg.index_add_(0, dst, conv2_r_out[src])
                conv2_r_agg = conv2_r_agg / deg
                h2 = torch.relu(conv2_l_out + conv2_r_agg + model.conv2.lin_l.bias)
                activation_stats['h2'].append(h2)
                
                h3 = torch.relu(h2 @ model.mlp[0].weight.t() + model.mlp[0].bias)
                activation_stats['h3'].append(h3)
                
                out = h3 @ model.mlp[3].weight.t() + model.mlp[3].bias
                activation_stats['out'].append(out)
        
        for key, tensors in activation_stats.items():
            if tensors:
                all_tensor = torch.cat(tensors)
                min_val = all_tensor.min().item()
                max_val = all_tensor.max().item()
                quantized, scale, zero_point = self.quantize_tensor(all_tensor)
                self.activation_params[key] = {
                    'min': min_val,
                    'max': max_val,
                    'scale': float(scale),
                    'zero_point': int(zero_point),
                }
                print(f'    {key}: min={min_val:.4f}, max={max_val:.4f}, scale={scale:.6f}')
        
        return self.activation_params


class FullINT8Inference:
    def __init__(self, weight_params, activation_params):
        self.weight_params = weight_params
        self.activation_params = activation_params
        self.device = torch.device('cpu')
        
        self.q_weights = {}
        self.w_scales = {}
        self.w_zero_points = {}
        for name, param in weight_params.items():
            self.q_weights[name] = torch.tensor(param['data'], dtype=torch.int8)
            self.w_scales[name] = param['scale']
            self.w_zero_points[name] = param['zero_point']

    def quantize(self, tensor, key):
        if key not in self.activation_params:
            return tensor, 1.0, 0
        scale = self.activation_params[key]['scale']
        zero_point = self.activation_params[key]['zero_point']
        quantized = torch.clamp((tensor / scale).round(), -127, 127).to(torch.int8)
        return quantized, scale, zero_point

    def dequantize(self, quantized, scale, zero_point):
        return (quantized.float() - zero_point) * scale

    def matmul_int8(self, x_int8, w_int8, x_scale, x_zp, w_scale, w_zp):
        x_deq = (x_int8.float() - x_zp) * x_scale
        w_deq = (w_int8.float() - w_zp) * w_scale
        return x_deq @ w_deq.t()

    def forward_int8(self, x, edge_index):
        x = x.to(self.device)
        edge_index = edge_index.to(self.device)

        h0_q, h0_scale, h0_zp = self.quantize(x, 'h0')

        conv1_l_w = self.q_weights['conv1.lin_l.weight'].to(self.device)
        conv1_r_w = self.q_weights['conv1.lin_r.weight'].to(self.device)
        conv1_b_q = self.q_weights['conv1.lin_l.bias'].to(self.device)
        conv1_b_scale = self.w_scales['conv1.lin_l.bias']
        conv1_b_zp = self.w_zero_points['conv1.lin_l.bias']
        
        conv1_l_out = self.matmul_int8(h0_q, conv1_l_w, h0_scale, h0_zp, 
                                       self.w_scales['conv1.lin_l.weight'], 
                                       self.w_zero_points['conv1.lin_l.weight'])
        conv1_r_out = self.matmul_int8(h0_q, conv1_r_w, h0_scale, h0_zp,
                                       self.w_scales['conv1.lin_r.weight'],
                                       self.w_zero_points['conv1.lin_r.weight'])
        
        num_nodes = x.size(0)
        src, dst = edge_index
        conv1_r_agg = torch.zeros(num_nodes, conv1_r_out.size(1), device=self.device)
        conv1_r_agg.index_add_(0, dst, conv1_r_out[src])
        deg = torch.bincount(dst, minlength=num_nodes).float().clamp(min=1).view(-1, 1)
        conv1_r_agg = conv1_r_agg / deg
        
        conv1_b_deq = self.dequantize(conv1_b_q, conv1_b_scale, conv1_b_zp)
        h1 = torch.relu(conv1_l_out + conv1_r_agg + conv1_b_deq)
        h1_q, h1_scale, h1_zp = self.quantize(h1, 'h1')

        conv2_l_w = self.q_weights['conv2.lin_l.weight'].to(self.device)
        conv2_r_w = self.q_weights['conv2.lin_r.weight'].to(self.device)
        conv2_b_q = self.q_weights['conv2.lin_l.bias'].to(self.device)
        conv2_b_scale = self.w_scales['conv2.lin_l.bias']
        conv2_b_zp = self.w_zero_points['conv2.lin_l.bias']
        
        conv2_l_out = self.matmul_int8(h1_q, conv2_l_w, h1_scale, h1_zp,
                                       self.w_scales['conv2.lin_l.weight'],
                                       self.w_zero_points['conv2.lin_l.weight'])
        conv2_r_out = self.matmul_int8(h1_q, conv2_r_w, h1_scale, h1_zp,
                                       self.w_scales['conv2.lin_r.weight'],
                                       self.w_zero_points['conv2.lin_r.weight'])
        
        conv2_r_agg = torch.zeros(num_nodes, conv2_r_out.size(1), device=self.device)
        conv2_r_agg.index_add_(0, dst, conv2_r_out[src])
        conv2_r_agg = conv2_r_agg / deg
        
        conv2_b_deq = self.dequantize(conv2_b_q, conv2_b_scale, conv2_b_zp)
        h2 = torch.relu(conv2_l_out + conv2_r_agg + conv2_b_deq)
        h2_q, h2_scale, h2_zp = self.quantize(h2, 'h2')

        mlp0_w = self.q_weights['mlp.0.weight'].to(self.device)
        mlp0_b_q = self.q_weights['mlp.0.bias'].to(self.device)
        mlp0_b_scale = self.w_scales['mlp.0.bias']
        mlp0_b_zp = self.w_zero_points['mlp.0.bias']
        
        mlp0_out = self.matmul_int8(h2_q, mlp0_w, h2_scale, h2_zp,
                                    self.w_scales['mlp.0.weight'],
                                    self.w_zero_points['mlp.0.weight'])
        mlp0_b_deq = self.dequantize(mlp0_b_q, mlp0_b_scale, mlp0_b_zp)
        h3 = torch.relu(mlp0_out + mlp0_b_deq)
        h3_q, h3_scale, h3_zp = self.quantize(h3, 'h3')

        mlp3_w = self.q_weights['mlp.3.weight'].to(self.device)
        mlp3_b_q = self.q_weights['mlp.3.bias'].to(self.device)
        mlp3_b_scale = self.w_scales['mlp.3.bias']
        mlp3_b_zp = self.w_zero_points['mlp.3.bias']
        
        out = self.matmul_int8(h3_q, mlp3_w, h3_scale, h3_zp,
                               self.w_scales['mlp.3.weight'],
                               self.w_zero_points['mlp.3.weight'])
        mlp3_b_deq = self.dequantize(mlp3_b_q, mlp3_b_scale, mlp3_b_zp)
        out = out + mlp3_b_deq

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
    print('  Full INT8 Quantization Test - Normalized SAGE2-Lite-64')
    print('=' * 70)

    model = SAGE2Lite(in_channels=15, hidden_channels=64)
    model_path = os.path.join(MODEL_DIR, 'SAGE2-Lite-64-Normalized.pth')
    
    if not os.path.exists(model_path):
        print(f'  ⚠️ Model file not found: {model_path}')
        return

    model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
    model = model.to('cpu')
    model.eval()

    num_params = sum(p.numel() for p in model.parameters())
    print(f'\n  Model: SAGE2-Lite-64-Normalized')
    print(f'  Parameters: {num_params:,}')

    if not os.path.exists(DATA_PATH):
        print(f'  ⚠️ Data file not found: {DATA_PATH}')
        return

    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    val_data = raw['val']
    test_data = raw['test']
    print(f'\n  Val data: {len(val_data)} graphs')
    print(f'  Test data: {len(test_data)} graphs')

    print('\n  --- Quantizing Model ---')
    quantizer = FullINT8Quantizer(symmetric=True)
    weight_params = quantizer.quantize_model(model)

    print('\n  --- Calibrating Activations ---')
    activation_params = quantizer.calibrate_activations(model, val_data[:50])

    int8_infer = FullINT8Inference(weight_params, activation_params)

    print('\n  --- Running Validation for Threshold Tuning ---')
    val_fp32 = []
    val_int8 = []
    val_labels = []
    with torch.no_grad():
        for graph in val_data:
            graph = graph.to('cpu')
            val_fp32.append(model(graph.x, graph.edge_index))
            val_int8.append(int8_infer.forward_int8(graph.x, graph.edge_index).squeeze())
            val_labels.append(graph.y)
    val_fp32 = torch.cat(val_fp32)
    val_int8 = torch.cat(val_int8)
    val_labels = torch.cat(val_labels)

    fp32_th, fp32_val_f1 = find_best_threshold(val_fp32, val_labels)
    int8_th, int8_val_f1 = find_best_threshold(val_int8, val_labels)
    print(f'  FP32 Best Threshold: {fp32_th:.2f} (Val F1={fp32_val_f1:.4f})')
    print(f'  INT8 Best Threshold: {int8_th:.2f} (Val F1={int8_val_f1:.4f})')

    print('\n  --- Running Test Inference ---')
    test_fp32 = []
    test_int8 = []
    test_labels = []
    with torch.no_grad():
        for i, graph in enumerate(test_data):
            if i % 50 == 0:
                print(f'    Processing graph {i}/{len(test_data)}...')
            
            graph = graph.to('cpu')
            test_fp32.append(model(graph.x, graph.edge_index))
            test_int8.append(int8_infer.forward_int8(graph.x, graph.edge_index).squeeze())
            test_labels.append(graph.y)

    test_fp32 = torch.cat(test_fp32)
    test_int8 = torch.cat(test_int8)
    test_labels = torch.cat(test_labels)

    print('\n  --- Computing Metrics ---')
    fp32_metrics = compute_metrics(test_fp32, test_labels, threshold=fp32_th)
    int8_metrics_same_th = compute_metrics(test_int8, test_labels, threshold=fp32_th)
    int8_metrics_own_th = compute_metrics(test_int8, test_labels, threshold=int8_th)

    print('\n  FP32 Metrics (th=%s):' % fp32_th)
    print(f'    Precision: {fp32_metrics["precision"]:.4f}')
    print(f'    Recall:    {fp32_metrics["recall"]:.4f}')
    print(f'    F1:        {fp32_metrics["f1"]:.4f}')
    print(f'    Accuracy:  {fp32_metrics["accuracy"]:.4f}')

    print('\n  INT8 Metrics (same th=%s):' % fp32_th)
    print(f'    Precision: {int8_metrics_same_th["precision"]:.4f}')
    print(f'    Recall:    {int8_metrics_same_th["recall"]:.4f}')
    print(f'    F1:        {int8_metrics_same_th["f1"]:.4f}')
    print(f'    Accuracy:  {int8_metrics_same_th["accuracy"]:.4f}')

    print('\n  INT8 Metrics (own th=%s):' % int8_th)
    print(f'    Precision: {int8_metrics_own_th["precision"]:.4f}')
    print(f'    Recall:    {int8_metrics_own_th["recall"]:.4f}')
    print(f'    F1:        {int8_metrics_own_th["f1"]:.4f}')
    print(f'    Accuracy:  {int8_metrics_own_th["accuracy"]:.4f}')

    print('\n  --- Accuracy Loss Analysis ---')
    f1_loss = fp32_metrics['f1'] - int8_metrics_same_th['f1']
    acc_loss = fp32_metrics['accuracy'] - int8_metrics_same_th['accuracy']
    
    print(f'    F1 Loss:   {f1_loss*100:.4f}%')
    print(f'    Acc Loss:  {acc_loss*100:.4f}%')

    max_abs_diff = torch.max(torch.abs(test_fp32 - test_int8)).item()
    avg_abs_diff = torch.mean(torch.abs(test_fp32 - test_int8)).item()
    std_abs_diff = torch.std(torch.abs(test_fp32 - test_int8)).item()
    
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
    int8_bytes = sum(p.numel() for p in model.parameters())
    memory_saving = (1 - int8_bytes / fp32_bytes) * 100
    
    print(f'\n  --- Memory Analysis ---')
    print(f'    FP32 Memory: {fp32_bytes:,} bytes')
    print(f'    INT8 Memory: {int8_bytes:,} bytes')
    print(f'    Memory Saving: {memory_saving:.1f}%')

    results = {
        'model': 'SAGE2-Lite-64-Normalized',
        'num_params': num_params,
        'num_graphs': len(test_data),
        'fp32_metrics': fp32_metrics,
        'int8_metrics_same_th': int8_metrics_same_th,
        'int8_metrics_own_th': int8_metrics_own_th,
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
            'int8_bytes': int8_bytes,
            'memory_saving': memory_saving,
        },
        'activation_params': activation_params,
    }

    result_path = os.path.join(OUTPUT_DIR, 'int8_full_quantization_test_results.json')
    with open(result_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  Results saved to: {result_path}')

    return results


if __name__ == '__main__':
    test_quantization()
