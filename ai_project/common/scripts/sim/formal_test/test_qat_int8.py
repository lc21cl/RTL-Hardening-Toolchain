import os
import sys
import json
import torch
import torch.nn as nn
from torch_geometric.nn import SAGEConv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data_15feat.pt')
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
FPGA_DIR = os.path.join(SCRIPT_DIR, 'data', 'fpga')


class SAGE2LiteQAT(nn.Module):
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
        h0 = x
        
        conv1_l_out = h0 @ self.conv1.lin_l.weight.t()
        conv1_r_out = h0 @ self.conv1.lin_r.weight.t()
        
        num_nodes = h0.size(0)
        src, dst = edge_index
        conv1_r_agg = torch.zeros(num_nodes, conv1_r_out.size(1), device=x.device)
        conv1_r_agg.index_add_(0, dst, conv1_r_out[src])
        deg = torch.bincount(dst, minlength=num_nodes).float().clamp(min=1).view(-1, 1)
        conv1_r_agg = conv1_r_agg / deg
        
        h1 = torch.relu(conv1_l_out + conv1_r_agg + self.conv1.lin_l.bias)
        h1 = self.dropout(h1)

        conv2_l_out = h1 @ self.conv2.lin_l.weight.t()
        conv2_r_out = h1 @ self.conv2.lin_r.weight.t()
        
        conv2_r_agg = torch.zeros(num_nodes, conv2_r_out.size(1), device=x.device)
        conv2_r_agg.index_add_(0, dst, conv2_r_out[src])
        conv2_r_agg = conv2_r_agg / deg
        
        h2 = torch.relu(conv2_l_out + conv2_r_agg + self.conv2.lin_l.bias)
        h2 = self.dropout(h2)

        h3 = torch.relu(h2 @ self.mlp[0].weight.t() + self.mlp[0].bias)
        h3 = self.dropout(h3)
        
        out = torch.sigmoid(h3 @ self.mlp[3].weight.t() + self.mlp[3].bias)

        return out

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class INT8Quantizer:
    def __init__(self, symmetric=True):
        self.symmetric = symmetric
        self.weight_params = {}
        self.activation_params = {}

    def quantize_weight(self, weight):
        min_val = weight.min().item()
        max_val = weight.max().item()
        
        if self.symmetric:
            abs_max = max(abs(min_val), abs(max_val))
            if abs_max == 0:
                scale = 1.0
            else:
                scale = abs_max / 127.0
            zero_point = 0
            quantized = torch.clamp((weight / scale).round(), -127, 127).to(torch.int8)
        else:
            range_val = max_val - min_val
            if range_val == 0:
                scale = 1.0
            else:
                scale = range_val / 255.0
            zero_point = int(-min_val / scale)
            zero_point = max(0, min(255, zero_point))
            quantized = torch.clamp((weight / scale + zero_point).round(), 0, 255).to(torch.uint8)
        
        return quantized, scale, zero_point

    def dequantize_weight(self, quantized, scale, zero_point):
        if self.symmetric:
            return quantized.float() * scale
        else:
            return (quantized.float() - zero_point) * scale

    def quantize_activation(self, tensor, key):
        if key not in self.activation_params:
            return tensor, 1.0, 0
        
        scale = self.activation_params[key]['scale']
        zero_point = self.activation_params[key]['zero_point']
        quantized = torch.clamp((tensor / scale).round(), -127, 127).to(torch.int8)
        return quantized, scale, zero_point

    def dequantize_activation(self, quantized, scale, zero_point):
        return (quantized.float() - zero_point) * scale

    def calibrate_activations(self, model, data_loader):
        model.eval()
        activation_stats = {'h0': [], 'h1': [], 'h2': [], 'h3': [], 'out': []}
        
        with torch.no_grad():
            for graph in data_loader:
                x = graph.x
                edge_index = graph.edge_index
                
                activation_stats['h0'].append(x)
                
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
                
                out = torch.sigmoid(h3 @ model.mlp[3].weight.t() + model.mlp[3].bias)
                activation_stats['out'].append(out)
        
        for key, tensors in activation_stats.items():
            if tensors:
                all_tensor = torch.cat(tensors)
                min_val = all_tensor.min().item()
                max_val = all_tensor.max().item()
                abs_max = max(abs(min_val), abs(max_val))
                if abs_max == 0:
                    scale = 1.0
                else:
                    scale = abs_max / 127.0
                self.activation_params[key] = {'min': min_val, 'max': max_val, 'scale': scale, 'zero_point': 0}
                print(f'    {key}: min={min_val:.4f}, max={max_val:.4f}, scale={scale:.6f}')


class INT8QATInference:
    def __init__(self, model, quantizer):
        self.quantized_weights = {}
        self.weight_params = {}
        
        for name, param in model.state_dict().items():
            if 'weight' in name:
                q, scale, zp = quantizer.quantize_weight(param)
                self.quantized_weights[name] = q
                self.weight_params[name] = {'scale': scale, 'zero_point': zp}
                print(f'  {name}: scale={scale:.6f}, zp={zp}')
        
        self.activation_params = quantizer.activation_params

    def forward_int8(self, x, edge_index):
        h0_q, h0_scale, h0_zp = self._quantize_act(x, 'h0')
        
        conv1_l_out = self._matmul_int8(h0_q, 'conv1.lin_l.weight', h0_scale)
        conv1_r_out = self._matmul_int8(h0_q, 'conv1.lin_r.weight', h0_scale)
        
        num_nodes = x.size(0)
        src, dst = edge_index
        conv1_r_agg = torch.zeros(num_nodes, conv1_r_out.size(1))
        conv1_r_agg.index_add_(0, dst, conv1_r_out[src])
        deg = torch.bincount(dst, minlength=num_nodes).float().clamp(min=1).view(-1, 1)
        conv1_r_agg = conv1_r_agg / deg
        
        h1 = torch.relu(conv1_l_out + conv1_r_agg + self._get_bias('conv1.lin_l.bias'))
        h1_q, h1_scale, h1_zp = self._quantize_act(h1, 'h1')

        conv2_l_out = self._matmul_int8(h1_q, 'conv2.lin_l.weight', h1_scale)
        conv2_r_out = self._matmul_int8(h1_q, 'conv2.lin_r.weight', h1_scale)
        
        conv2_r_agg = torch.zeros(num_nodes, conv2_r_out.size(1))
        conv2_r_agg.index_add_(0, dst, conv2_r_out[src])
        conv2_r_agg = conv2_r_agg / deg
        
        h2 = torch.relu(conv2_l_out + conv2_r_agg + self._get_bias('conv2.lin_l.bias'))
        h2_q, h2_scale, h2_zp = self._quantize_act(h2, 'h2')

        h3 = torch.relu(self._matmul_int8(h2_q, 'mlp.0.weight', h2_scale) + self._get_bias('mlp.0.bias'))
        h3_q, h3_scale, h3_zp = self._quantize_act(h3, 'h3')

        out = torch.sigmoid(self._matmul_int8(h3_q, 'mlp.3.weight', h3_scale) + self._get_bias('mlp.3.bias'))

        return out

    def _quantize_act(self, tensor, key):
        if key not in self.activation_params:
            return tensor, 1.0, 0
        scale = self.activation_params[key]['scale']
        zero_point = self.activation_params[key]['zero_point']
        quantized = torch.clamp((tensor / scale).round(), -127, 127).to(torch.int8)
        return quantized, scale, zero_point

    def _matmul_int8(self, x_q, weight_name, x_scale):
        w_q = self.quantized_weights[weight_name]
        w_scale = self.weight_params[weight_name]['scale']
        
        x_deq = (x_q.float()) * x_scale
        w_deq = (w_q.float()) * w_scale
        
        return x_deq @ w_deq.t()

    def _get_bias(self, name):
        return self.biases.get(name, torch.zeros(1))

    def set_biases(self, biases):
        self.biases = biases


def compute_metrics(scores, labels, threshold=0.5):
    preds = (scores.squeeze() >= threshold).float()
    labels = labels.float()
    tp = (preds * labels).sum().item()
    fp = (preds * (1 - labels)).sum().item()
    fn = ((1 - preds) * labels).sum().item()
    tn = ((1 - preds) * (1 - labels)).sum().item()

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-10)
    acc = (tp + tn) / max(tp + fp + fn + tn, 1)

    return {'precision': precision, 'recall': recall, 'f1': f1, 'accuracy': acc}


def test_quantization():
    print('=' * 62)
    print('  INT8 Quantization Test - QAT Model')
    print('=' * 62)

    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    val_data = raw['val']
    test_data = raw['test']
    
    print(f'  Val data: {len(val_data)} graphs')
    print(f'  Test data: {len(test_data)} graphs')

    model = SAGE2LiteQAT(in_channels=15, hidden_channels=64)
    model_path = os.path.join(MODEL_DIR, 'SAGE2-Lite-64-QAT.pth')
    
    if os.path.exists(model_path):
        state_dict = torch.load(model_path, map_location='cpu', weights_only=True)
        model.load_state_dict(state_dict)
        print(f'\n  Model loaded from: {model_path}')
    else:
        print(f'\n  ERROR: QAT model not found at {model_path}')
        return

    print(f'  Parameters: {model.count_parameters():,}')

    print('\n  --- Quantizing Model ---')
    quantizer = INT8Quantizer(symmetric=True)
    quantizer.calibrate_activations(model, val_data)

    int8_infer = INT8QATInference(model, quantizer)
    
    biases = {}
    for name, param in model.state_dict().items():
        if 'bias' in name:
            biases[name] = param
    
    int8_infer.set_biases(biases)

    print('\n  --- Running Validation for Threshold Tuning ---')
    model.eval()
    
    fp32_scores = []
    int8_scores = []
    all_labels = []
    
    with torch.no_grad():
        for i, graph in enumerate(val_data):
            fp32_out = model(graph.x, graph.edge_index)
            int8_out = int8_infer.forward_int8(graph.x, graph.edge_index)
            
            fp32_scores.append(fp32_out.squeeze())
            int8_scores.append(int8_out.squeeze())
            all_labels.append(graph.y)
    
    fp32_scores = torch.cat(fp32_scores)
    int8_scores = torch.cat(int8_scores)
    all_labels = torch.cat(all_labels)
    
    best_fp32_th = 0.5
    best_fp32_f1 = 0.0
    for th in [x / 100 for x in range(5, 50, 5)]:
        m = compute_metrics(fp32_scores, all_labels, threshold=th)
        if m['f1'] > best_fp32_f1:
            best_fp32_f1 = m['f1']
            best_fp32_th = th
    
    best_int8_th = 0.5
    best_int8_f1 = 0.0
    for th in [x / 100 for x in range(5, 50, 5)]:
        m = compute_metrics(int8_scores, all_labels, threshold=th)
        if m['f1'] > best_int8_f1:
            best_int8_f1 = m['f1']
            best_int8_th = th
    
    print(f'  FP32 Best Threshold: {best_fp32_th} (Val F1={best_fp32_f1:.4f})')
    print(f'  INT8 Best Threshold: {best_int8_th} (Val F1={best_int8_f1:.4f})')

    print('\n  --- Running Test Inference ---')
    fp32_test = []
    int8_test = []
    test_labels = []
    
    with torch.no_grad():
        for i, graph in enumerate(test_data):
            if i % 50 == 0:
                print(f'    Processing graph {i}/{len(test_data)}...')
            
            fp32_out = model(graph.x, graph.edge_index)
            int8_out = int8_infer.forward_int8(graph.x, graph.edge_index)
            
            fp32_test.append(fp32_out.squeeze())
            int8_test.append(int8_out.squeeze())
            test_labels.append(graph.y)
    
    fp32_test = torch.cat(fp32_test)
    int8_test = torch.cat(int8_test)
    test_labels = torch.cat(test_labels)

    print('\n  --- Computing Metrics ---')
    
    fp32_metrics = compute_metrics(fp32_test, test_labels, threshold=best_fp32_th)
    int8_metrics_same = compute_metrics(int8_test, test_labels, threshold=best_fp32_th)
    int8_metrics_own = compute_metrics(int8_test, test_labels, threshold=best_int8_th)
    
    print(f'\n  FP32 Metrics (th={best_fp32_th}):')
    print(f'    Precision: {fp32_metrics["precision"]:.4f}')
    print(f'    Recall:    {fp32_metrics["recall"]:.4f}')
    print(f'    F1:        {fp32_metrics["f1"]:.4f}')
    print(f'    Accuracy:  {fp32_metrics["accuracy"]:.4f}')
    
    print(f'\n  INT8 Metrics (same th={best_fp32_th}):')
    print(f'    Precision: {int8_metrics_same["precision"]:.4f}')
    print(f'    Recall:    {int8_metrics_same["recall"]:.4f}')
    print(f'    F1:        {int8_metrics_same["f1"]:.4f}')
    print(f'    Accuracy:  {int8_metrics_same["accuracy"]:.4f}')
    
    print(f'\n  INT8 Metrics (own th={best_int8_th}):')
    print(f'    Precision: {int8_metrics_own["precision"]:.4f}')
    print(f'    Recall:    {int8_metrics_own["recall"]:.4f}')
    print(f'    F1:        {int8_metrics_own["f1"]:.4f}')
    print(f'    Accuracy:  {int8_metrics_own["accuracy"]:.4f}')

    f1_loss = (fp32_metrics['f1'] - int8_metrics_own['f1']) / fp32_metrics['f1'] * 100
    acc_loss = (fp32_metrics['accuracy'] - int8_metrics_own['accuracy']) / fp32_metrics['accuracy'] * 100
    
    print(f'\n  --- Accuracy Loss Analysis ---')
    print(f'    F1 Loss:   {f1_loss:.4f}%')
    print(f'    Acc Loss:  {acc_loss:.4f}%')

    diff = torch.abs(fp32_test - int8_test)
    print(f'\n  --- Output Difference Analysis ---')
    print(f'    Max Absolute Difference: {diff.max().item():.6f}')
    print(f'    Avg Absolute Difference: {diff.mean().item():.6f}')
    print(f'    Std Absolute Difference: {diff.std().item():.6f}')

    print(f'\n  --- Quantization Acceptance Check ---')
    checks = [
        ('F1 Loss < 1%', f1_loss < 1),
        ('Accuracy Loss < 1%', acc_loss < 1),
        ('Max Diff < 0.1', diff.max().item() < 0.1),
    ]
    
    all_pass = all(c[1] for c in checks)
    for name, passed in checks:
        print(f'    {name}:       {"✅ PASS" if passed else "❌ FAIL"}')
    
    print(f'\n    Overall:            {"✅ ALL CHECKS PASSED" if all_pass else "❌ SOME CHECKS FAILED"}')

    print(f'\n  --- Memory Analysis ---')
    fp32_memory = sum(p.numel() * 4 for p in model.parameters())
    int8_memory = sum(p.numel() for p in model.parameters())
    print(f'    FP32 Memory: {fp32_memory:,} bytes')
    print(f'    INT8 Memory: {int8_memory:,} bytes')
    print(f'    Memory Saving: {((fp32_memory - int8_memory) / fp32_memory * 100):.1f}%')

    result = {
        'model': 'SAGE2-Lite-64-QAT',
        'quantization': 'INT8',
        'fp32_metrics': fp32_metrics,
        'int8_metrics_same_threshold': int8_metrics_same,
        'int8_metrics_own_threshold': int8_metrics_own,
        'fp32_threshold': best_fp32_th,
        'int8_threshold': best_int8_th,
        'f1_loss_pct': round(f1_loss, 4),
        'acc_loss_pct': round(acc_loss, 4),
        'max_diff': round(diff.max().item(), 6),
        'avg_diff': round(diff.mean().item(), 6),
        'std_diff': round(diff.std().item(), 6),
        'fp32_memory_bytes': fp32_memory,
        'int8_memory_bytes': int8_memory,
        'memory_saving_pct': round(((fp32_memory - int8_memory) / fp32_memory * 100), 1),
        'acceptance': all_pass,
        'activation_params': quantizer.activation_params,
    }

    result_path = os.path.join(FPGA_DIR, 'qat_int8_quantization_test_results.json')
    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f'\n  Results saved to: {result_path}')

    return result


if __name__ == '__main__':
    test_quantization()
