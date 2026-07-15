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


class SAGE3Lite(nn.Module):
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

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class INT8Quantizer:
    def __init__(self):
        self.scale_factor = {}
        self.zero_point = {}

    def quantize_tensor(self, tensor):
        min_val = tensor.min().item()
        max_val = tensor.max().item()
        if max_val == min_val:
            scale = 1.0
            zero_point = 0
        else:
            scale = (max_val - min_val) / 255.0
            zero_point = int(-min_val / scale)
            zero_point = max(0, min(255, zero_point))
        quantized = torch.clamp((tensor / scale + zero_point).round(), 0, 255).byte()
        return quantized, scale, zero_point

    def quantize_model(self, model):
        quantized_params = {}
        for name, param in model.state_dict().items():
            quantized, scale, zero_point = self.quantize_tensor(param)
            quantized_params[name] = {
                'data': quantized.numpy().tolist(),
                'scale': float(scale),
                'zero_point': int(zero_point),
                'shape': list(param.shape),
            }
            self.scale_factor[name] = scale
            self.zero_point[name] = zero_point
        return quantized_params

    def generate_cpp_header(self, model, quantized_params):
        header = []
        header.append('#ifndef SAGE3_LITE_MODEL_H')
        header.append('#define SAGE3_LITE_MODEL_H')
        header.append('')
        header.append('#include <cstdint>')
        header.append('#include <vector>')
        header.append('#include <cmath>')
        header.append('')
        header.append('namespace sage3_lite {')
        header.append('')

        in_channels = 15
        hidden_channels = 32

        header.append(f'const int IN_CHANNELS = {in_channels};')
        header.append(f'const int HIDDEN_CHANNELS = {hidden_channels};')
        header.append('')

        def add_weight(name, param):
            arr = np.array(param['data'], dtype=np.uint8)
            scale = param['scale']
            zero_point = param['zero_point']
            header.append(f'// {name} (scale={scale:.6f}, zero_point={zero_point})')
            header.append(f'const uint8_t {name}[{arr.size}] = {{')
            flat = arr.flatten()
            line_len = 16
            for i in range(0, len(flat), line_len):
                line = ', '.join(f'0x{val:02x}' for val in flat[i:i+line_len])
                header.append(f'    {line},')
            header.append('};')
            header.append(f'const float {name}_scale = {scale:.6f}f;')
            header.append(f'const int {name}_zero_point = {zero_point};')
            header.append('')

        add_weight('conv1_lin_l_weight', quantized_params['conv1.lin_l.weight'])
        add_weight('conv1_lin_r_weight', quantized_params['conv1.lin_r.weight'])
        add_weight('conv1_bias', quantized_params['conv1.lin_l.bias'])

        add_weight('conv2_lin_l_weight', quantized_params['conv2.lin_l.weight'])
        add_weight('conv2_lin_r_weight', quantized_params['conv2.lin_r.weight'])
        add_weight('conv2_bias', quantized_params['conv2.lin_l.bias'])

        add_weight('conv3_lin_l_weight', quantized_params['conv3.lin_l.weight'])
        add_weight('conv3_lin_r_weight', quantized_params['conv3.lin_r.weight'])
        add_weight('conv3_bias', quantized_params['conv3.lin_l.bias'])

        add_weight('mlp1_weight', quantized_params['mlp.0.weight'])
        add_weight('mlp1_bias', quantized_params['mlp.0.bias'])

        add_weight('mlp2_weight', quantized_params['mlp.3.weight'])
        add_weight('mlp2_bias', quantized_params['mlp.3.bias'])

        header.append('inline int8_t dequantize(uint8_t q, float scale, int zero_point) {')
        header.append('    return (int8_t)((int)q - zero_point);')
        header.append('}')
        header.append('')
        header.append('inline float relu(float x) { return x > 0 ? x : 0; }')
        header.append('inline float sigmoid(float x) { return 1.0f / (1.0f + exp(-x)); }')
        header.append('')
        header.append('} // namespace sage3_lite')
        header.append('')
        header.append('#endif // SAGE3_LITE_MODEL_H')

        return '\n'.join(header)

    def generate_cpp_inference(self):
        code = []
        code.append('#include "sage3_lite_model.h"')
        code.append('#include <iostream>')
        code.append('#include <vector>')
        code.append('#include <cmath>')
        code.append('#include <numeric>')
        code.append('')
        code.append('using namespace sage3_lite;')
        code.append('')
        code.append('void matmul_int8(const uint8_t* weight, float w_scale, int w_zp,')
        code.append('               const float* input, int in_dim, int out_dim, float* output) {')
        code.append('    for (int i = 0; i < out_dim; i++) {')
        code.append('        float sum = 0;')
        code.append('        for (int j = 0; j < in_dim; j++) {')
        code.append('            int8_t w_q = dequantize(weight[i * in_dim + j], w_scale, w_zp);')
        code.append('            sum += (float)w_q * input[j];')
        code.append('        }')
        code.append('        output[i] = sum * w_scale;')
        code.append('    }')
        code.append('}')
        code.append('')
        code.append('void sage3_lite_inference(const float* features, const int* edge_index,')
        code.append('                         int num_nodes, int num_edges, float* output) {')
        code.append('')
        code.append('    std::vector<std::vector<int>> adj(num_nodes);')
        code.append('    for (int i = 0; i < num_edges; i++) {')
        code.append('        int src = edge_index[i];')
        code.append('        int dst = edge_index[i + num_edges];')
        code.append('        adj[dst].push_back(src);')
        code.append('    }')
        code.append('')
        code.append('    std::vector<std::vector<float>> h0(num_nodes, std::vector<float>(IN_CHANNELS));')
        code.append('    for (int i = 0; i < num_nodes; i++) {')
        code.append('        for (int j = 0; j < IN_CHANNELS; j++) {')
        code.append('            h0[i][j] = features[i * IN_CHANNELS + j];')
        code.append('        }')
        code.append('    }')
        code.append('')
        code.append('    // Layer 1')
        code.append('    std::vector<std::vector<float>> h1(num_nodes, std::vector<float>(HIDDEN_CHANNELS, 0));')
        code.append('    for (int i = 0; i < num_nodes; i++) {')
        code.append('        std::vector<float> agg(HIDDEN_CHANNELS, 0);')
        code.append('        int deg = adj[i].size();')
        code.append('        if (deg > 0) {')
        code.append('            std::vector<float> tmp(HIDDEN_CHANNELS, 0);')
        code.append('            for (int idx : adj[i]) {')
        code.append('                matmul_int8(conv1_lin_r_weight, conv1_lin_r_weight_scale, conv1_lin_r_weight_zero_point,')
        code.append('                           h0[idx].data(), IN_CHANNELS, HIDDEN_CHANNELS, tmp.data());')
        code.append('                for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
        code.append('                    agg[j] += tmp[j];')
        code.append('                }')
        code.append('            }')
        code.append('            for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
        code.append('                agg[j] /= deg;')
        code.append('            }')
        code.append('        }')
        code.append('        std::vector<float> lin_out(HIDDEN_CHANNELS, 0);')
        code.append('        matmul_int8(conv1_lin_l_weight, conv1_lin_l_weight_scale, conv1_lin_l_weight_zero_point,')
        code.append('                   h0[i].data(), IN_CHANNELS, HIDDEN_CHANNELS, lin_out.data());')
        code.append('        for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
        code.append('            h1[i][j] = relu(lin_out[j] + agg[j] + conv1_bias_scale * (float)dequantize(conv1_bias[j], conv1_bias_scale, conv1_bias_zero_point));')
        code.append('        }')
        code.append('    }')
        code.append('')
        code.append('    // Layer 2')
        code.append('    std::vector<std::vector<float>> h2(num_nodes, std::vector<float>(HIDDEN_CHANNELS, 0));')
        code.append('    for (int i = 0; i < num_nodes; i++) {')
        code.append('        std::vector<float> agg(HIDDEN_CHANNELS, 0);')
        code.append('        int deg = adj[i].size();')
        code.append('        if (deg > 0) {')
        code.append('            std::vector<float> tmp(HIDDEN_CHANNELS, 0);')
        code.append('            for (int idx : adj[i]) {')
        code.append('                matmul_int8(conv2_lin_r_weight, conv2_lin_r_weight_scale, conv2_lin_r_weight_zero_point,')
        code.append('                           h1[idx].data(), HIDDEN_CHANNELS, HIDDEN_CHANNELS, tmp.data());')
        code.append('                for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
        code.append('                    agg[j] += tmp[j];')
        code.append('                }')
        code.append('            }')
        code.append('            for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
        code.append('                agg[j] /= deg;')
        code.append('            }')
        code.append('        }')
        code.append('        std::vector<float> lin_out(HIDDEN_CHANNELS, 0);')
        code.append('        matmul_int8(conv2_lin_l_weight, conv2_lin_l_weight_scale, conv2_lin_l_weight_zero_point,')
        code.append('                   h1[i].data(), HIDDEN_CHANNELS, HIDDEN_CHANNELS, lin_out.data());')
        code.append('        for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
        code.append('            h2[i][j] = relu(lin_out[j] + agg[j] + conv2_bias_scale * (float)dequantize(conv2_bias[j], conv2_bias_scale, conv2_bias_zero_point));')
        code.append('        }')
        code.append('    }')
        code.append('')
        code.append('    // Layer 3')
        code.append('    std::vector<std::vector<float>> h3(num_nodes, std::vector<float>(HIDDEN_CHANNELS / 2, 0));')
        code.append('    for (int i = 0; i < num_nodes; i++) {')
        code.append('        std::vector<float> agg(HIDDEN_CHANNELS / 2, 0);')
        code.append('        int deg = adj[i].size();')
        code.append('        if (deg > 0) {')
        code.append('            std::vector<float> tmp(HIDDEN_CHANNELS / 2, 0);')
        code.append('            for (int idx : adj[i]) {')
        code.append('                matmul_int8(conv3_lin_r_weight, conv3_lin_r_weight_scale, conv3_lin_r_weight_zero_point,')
        code.append('                           h2[idx].data(), HIDDEN_CHANNELS, HIDDEN_CHANNELS / 2, tmp.data());')
        code.append('                for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {')
        code.append('                    agg[j] += tmp[j];')
        code.append('                }')
        code.append('            }')
        code.append('            for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {')
        code.append('                agg[j] /= deg;')
        code.append('            }')
        code.append('        }')
        code.append('        std::vector<float> lin_out(HIDDEN_CHANNELS / 2, 0);')
        code.append('        matmul_int8(conv3_lin_l_weight, conv3_lin_l_weight_scale, conv3_lin_l_weight_zero_point,')
        code.append('                   h2[i].data(), HIDDEN_CHANNELS, HIDDEN_CHANNELS / 2, lin_out.data());')
        code.append('        for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {')
        code.append('            h3[i][j] = relu(lin_out[j] + agg[j] + conv3_bias_scale * (float)dequantize(conv3_bias[j], conv3_bias_scale, conv3_bias_zero_point));')
        code.append('        }')
        code.append('    }')
        code.append('')
        code.append('    // MLP Layer 1')
        code.append('    std::vector<std::vector<float>> mlp1_out(num_nodes, std::vector<float>(8, 0));')
        code.append('    for (int i = 0; i < num_nodes; i++) {')
        code.append('        matmul_int8(mlp1_weight, mlp1_weight_scale, mlp1_weight_zero_point,')
        code.append('                   h3[i].data(), HIDDEN_CHANNELS / 2, 8, mlp1_out[i].data());')
        code.append('        for (int j = 0; j < 8; j++) {')
        code.append('            mlp1_out[i][j] = relu(mlp1_out[i][j] + mlp1_bias_scale * (float)dequantize(mlp1_bias[j], mlp1_bias_scale, mlp1_bias_zero_point));')
        code.append('        }')
        code.append('    }')
        code.append('')
        code.append('    // MLP Layer 2 + Sigmoid')
        code.append('    for (int i = 0; i < num_nodes; i++) {')
        code.append('        float sum_val = 0;')
        code.append('        matmul_int8(mlp2_weight, mlp2_weight_scale, mlp2_weight_zero_point,')
        code.append('                   mlp1_out[i].data(), 8, 1, &sum_val);')
        code.append('        output[i] = sigmoid(sum_val + mlp2_bias_scale * (float)dequantize(mlp2_bias[0], mlp2_bias_scale, mlp2_bias_zero_point));')
        code.append('    }')
        code.append('}')
        code.append('')
        code.append('int main() {')
        code.append('    std::cout << "SAGE3-Lite FPGA Inference - INT8 Quantized GraphSAGE" << std::endl;')
        code.append('    return 0;')
        code.append('}')

        return '\n'.join(code)


def generate_resource_analysis(model):
    params = model.state_dict()
    
    total_params = sum(p.numel() for p in params.values())
    total_bytes = sum(p.numel() * p.element_size() for p in params.values())
    int8_bytes = total_params * 1
    
    bram_18k = int8_bytes / (18 * 1024)
    
    macs = 0
    macs += params['conv1.lin_l.weight'].numel() + params['conv1.lin_r.weight'].numel()
    macs += params['conv2.lin_l.weight'].numel() + params['conv2.lin_r.weight'].numel()
    macs += params['conv3.lin_l.weight'].numel() + params['conv3.lin_r.weight'].numel()
    macs += params['mlp.0.weight'].numel()
    macs += params['mlp.3.weight'].numel()
    
    dsp48e = macs / 64
    
    lut = total_params * 2
    ff = 32 + 32 + 16 + 8 + 1
    
    analysis = {
        'model_spec': {
            'name': 'SAGE3-Lite',
            'in_channels': 15,
            'hidden_channels': 32,
            'quantization': 'INT8',
        },
        'total_params': int(total_params),
        'total_macs': int(macs),
        'resource_estimate': {
            'BRAM_18K': round(bram_18k, 2),
            'DSP48E': round(dsp48e, 2),
            'LUT': int(lut),
            'FF': int(ff),
        },
        'memory_savings': {
            'original_fp32_bytes': int(total_bytes),
            'quantized_int8_bytes': int(int8_bytes),
            'reduction_ratio': round(1 - int8_bytes / total_bytes, 2),
        },
        'target_device': 'xc7z020clg484-1',
        'device_limits': {
            'BRAM_18K': 36,
            'LUT': 53200,
            'FF': 106400,
            'DSP48E': 220,
        },
        'utilization': {
            'BRAM_18K': round(bram_18k / 36 * 100, 2),
            'DSP48E': round(dsp48e / 220 * 100, 2),
            'LUT': round(lut / 53200 * 100, 2),
            'FF': round(ff / 106400 * 100, 2),
        },
    }
    
    return analysis


def main():
    print('=' * 62)
    print('  SAGE3-Lite FPGA Deployment (INT8 + Hidden=32)')
    print('=' * 62)

    model = SAGE3Lite(in_channels=15, hidden_channels=32)
    print(f'  Model: SAGE3-Lite (15→32→32→16→8→1)')
    print(f'  Parameters: {model.count_parameters():,}')

    if os.path.exists(DATA_PATH):
        raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
        test_data = raw['test']
        print(f'  Test data: {len(test_data)} graphs')

    print('\n--- Generating INT8 Quantized Model ---')
    quantizer = INT8Quantizer()
    quantized_params = quantizer.quantize_model(model)

    print('\n--- Generating C++ Header ---')
    header_content = quantizer.generate_cpp_header(model, quantized_params)
    header_path = os.path.join(OUTPUT_DIR, 'sage3_lite_model.h')
    with open(header_path, 'w') as f:
        f.write(header_content)
    print(f'  C++ header saved to: {header_path}')

    print('\n--- Generating C++ Inference Code ---')
    cpp_content = quantizer.generate_cpp_inference()
    cpp_path = os.path.join(OUTPUT_DIR, 'sage3_lite_inference.cpp')
    with open(cpp_path, 'w') as f:
        f.write(cpp_content)
    print(f'  C++ inference code saved to: {cpp_path}')

    print('\n--- Generating Quantized Weights JSON ---')
    quant_path = os.path.join(OUTPUT_DIR, 'quantized_weights_lite.json')
    with open(quant_path, 'w') as f:
        json.dump(quantized_params, f, indent=2)
    print(f'  Quantized weights saved to: {quant_path}')

    print('\n--- Generating Resource Analysis ---')
    resource_analysis = generate_resource_analysis(model)
    resource_path = os.path.join(OUTPUT_DIR, 'resource_analysis_lite.json')
    with open(resource_path, 'w') as f:
        json.dump(resource_analysis, f, indent=2)
    print(f'  Resource analysis saved to: {resource_path}')

    print('\n' + '=' * 62)
    print('  SAGE3-Lite FPGA Deployment Files Generated')
    print('=' * 62)
    
    print('\n--- Resource Estimation ---')
    print(f'  BRAM_18K: {resource_analysis["resource_estimate"]["BRAM_18K"]:.2f} ({resource_analysis["utilization"]["BRAM_18K"]:.1f}%)')
    print(f'  DSP48E: {resource_analysis["resource_estimate"]["DSP48E"]:.2f} ({resource_analysis["utilization"]["DSP48E"]:.1f}%)')
    print(f'  LUT: {resource_analysis["resource_estimate"]["LUT"]:,} ({resource_analysis["utilization"]["LUT"]:.1f}%)')
    print(f'  FF: {resource_analysis["resource_estimate"]["FF"]:,} ({resource_analysis["utilization"]["FF"]:.1f}%)')
    
    print('\n--- Memory Savings ---')
    print(f'  Original (FP32): {resource_analysis["memory_savings"]["original_fp32_bytes"]:,} bytes')
    print(f'  Quantized (INT8): {resource_analysis["memory_savings"]["quantized_int8_bytes"]:,} bytes')
    print(f'  Reduction: {resource_analysis["memory_savings"]["reduction_ratio"]*100:.0f}%')
    
    print('\n--- Deployment Status ---')
    if resource_analysis["utilization"]["DSP48E"] <= 100:
        print('  ✓ DSP48E: SUFFICIENT')
    else:
        print('  ✗ DSP48E: INSUFFICIENT')
    if resource_analysis["utilization"]["BRAM_18K"] <= 100:
        print('  ✓ BRAM_18K: SUFFICIENT')
    else:
        print('  ✗ BRAM_18K: INSUFFICIENT')


if __name__ == '__main__':
    main()
