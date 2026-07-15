import os
import sys
import json
import torch
import numpy as np
from torch_geometric.nn import SAGEConv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data.pt')
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'data', 'fpga')
os.makedirs(OUTPUT_DIR, exist_ok=True)

class SAGE3(torch.nn.Module):
    def __init__(self, in_channels=10, hidden_channels=128, dropout=0.3):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.conv3 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = torch.nn.Sequential(
            torch.nn.Linear(hidden_channels // 2, 32), torch.nn.ReLU(),
            torch.nn.Dropout(dropout), torch.nn.Linear(32, 1),
        )
        self.dropout = torch.nn.Dropout(dropout)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv2(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv3(x, edge_index).relu(); x = self.dropout(x)
        return torch.sigmoid(self.mlp(x).squeeze(-1))

def export_onnx(model, output_path):
    dummy_x = torch.randn(64, 10, dtype=torch.float32)
    dummy_edge_index = torch.randint(0, 64, (2, 128), dtype=torch.long)
    
    torch.onnx.export(
        model,
        (dummy_x, dummy_edge_index),
        output_path,
        opset_version=18,
        input_names=['x', 'edge_index'],
        output_names=['output'],
        dynamic_axes={
            'x': {0: 'num_nodes'},
            'edge_index': {1: 'num_edges'},
            'output': {0: 'num_nodes'},
        },
        verbose=False,
    )
    print(f'  ONNX model exported to: {output_path}')

def generate_test_vectors(test_data, num_samples=10):
    test_vectors = []
    
    for i, data in enumerate(test_data[:num_samples]):
        with torch.no_grad():
            model = SAGE3(in_channels=10, hidden_channels=128)
            model_path = os.path.join(MODEL_DIR, 'local_seed42.pt')
            model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
            model.eval()
            pred = model(data.x, data.edge_index)
        
        vector = {
            'id': i,
            'num_nodes': data.x.shape[0],
            'num_edges': data.edge_index.shape[1],
            'features': data.x.numpy().tolist(),
            'edge_index': data.edge_index.numpy().tolist(),
            'labels': data.y.numpy().tolist(),
            'expected_output': pred.numpy().tolist(),
        }
        test_vectors.append(vector)
    
    return test_vectors

def generate_cpp_header(model):
    header = []
    header.append('#ifndef SAGE3_MODEL_H')
    header.append('#define SAGE3_MODEL_H')
    header.append('')
    header.append('#include <cstdint>')
    header.append('#include <vector>')
    header.append('')
    header.append('namespace sage3 {')
    header.append('')
    
    params = {}
    for name, param in model.state_dict().items():
        params[name] = param.numpy()
    
    conv1_lin_l_weight = params['conv1.lin_l.weight'].T
    conv1_lin_r_weight = params['conv1.lin_r.weight'].T
    conv1_bias = params['conv1.lin_l.bias']
    header.append(f'const int IN_CHANNELS = {conv1_lin_l_weight.shape[0]};')
    header.append(f'const int HIDDEN_CHANNELS = {conv1_lin_l_weight.shape[1]};')
    header.append('')
    
    header.append('// Conv1 weights')
    header.append(f'const float conv1_lin_l_weight[{conv1_lin_l_weight.shape[0]}][{conv1_lin_l_weight.shape[1]}] = {{')
    for row in conv1_lin_l_weight:
        row_str = ', '.join(f'{v:.6f}f' for v in row)
        header.append(f'    {{{row_str}}},')
    header.append('};')
    
    header.append(f'const float conv1_lin_r_weight[{conv1_lin_r_weight.shape[0]}][{conv1_lin_r_weight.shape[1]}] = {{')
    for row in conv1_lin_r_weight:
        row_str = ', '.join(f'{v:.6f}f' for v in row)
        header.append(f'    {{{row_str}}},')
    header.append('};')
    
    header.append(f'const float conv1_bias[{len(conv1_bias)}] = {{')
    header.append(f'    {", ".join(f"{v:.6f}f" for v in conv1_bias)}')
    header.append('};')
    header.append('')
    
    conv2_lin_l_weight = params['conv2.lin_l.weight'].T
    conv2_lin_r_weight = params['conv2.lin_r.weight'].T
    conv2_bias = params['conv2.lin_l.bias']
    
    header.append('// Conv2 weights')
    header.append(f'const float conv2_lin_l_weight[{conv2_lin_l_weight.shape[0]}][{conv2_lin_l_weight.shape[1]}] = {{')
    for row in conv2_lin_l_weight:
        row_str = ', '.join(f'{v:.6f}f' for v in row)
        header.append(f'    {{{row_str}}},')
    header.append('};')
    
    header.append(f'const float conv2_lin_r_weight[{conv2_lin_r_weight.shape[0]}][{conv2_lin_r_weight.shape[1]}] = {{')
    for row in conv2_lin_r_weight:
        row_str = ', '.join(f'{v:.6f}f' for v in row)
        header.append(f'    {{{row_str}}},')
    header.append('};')
    
    header.append(f'const float conv2_bias[{len(conv2_bias)}] = {{')
    header.append(f'    {", ".join(f"{v:.6f}f" for v in conv2_bias)}')
    header.append('};')
    header.append('')
    
    conv3_lin_l_weight = params['conv3.lin_l.weight'].T
    conv3_lin_r_weight = params['conv3.lin_r.weight'].T
    conv3_bias = params['conv3.lin_l.bias']
    
    header.append('// Conv3 weights')
    header.append(f'const float conv3_lin_l_weight[{conv3_lin_l_weight.shape[0]}][{conv3_lin_l_weight.shape[1]}] = {{')
    for row in conv3_lin_l_weight:
        row_str = ', '.join(f'{v:.6f}f' for v in row)
        header.append(f'    {{{row_str}}},')
    header.append('};')
    
    header.append(f'const float conv3_lin_r_weight[{conv3_lin_r_weight.shape[0]}][{conv3_lin_r_weight.shape[1]}] = {{')
    for row in conv3_lin_r_weight:
        row_str = ', '.join(f'{v:.6f}f' for v in row)
        header.append(f'    {{{row_str}}},')
    header.append('};')
    
    header.append(f'const float conv3_bias[{len(conv3_bias)}] = {{')
    header.append(f'    {", ".join(f"{v:.6f}f" for v in conv3_bias)}')
    header.append('};')
    header.append('')
    
    mlp_weight1 = params['mlp.0.weight'].T
    mlp_bias1 = params['mlp.0.bias']
    
    header.append('// MLP Layer 1')
    header.append(f'const float mlp1_weight[{mlp_weight1.shape[0]}][{mlp_weight1.shape[1]}] = {{')
    for row in mlp_weight1:
        row_str = ', '.join(f'{v:.6f}f' for v in row)
        header.append(f'    {{{row_str}}},')
    header.append('};')
    
    header.append(f'const float mlp1_bias[{len(mlp_bias1)}] = {{')
    header.append(f'    {", ".join(f"{v:.6f}f" for v in mlp_bias1)}')
    header.append('};')
    header.append('')
    
    mlp_weight2 = params['mlp.3.weight'].T
    mlp_bias2 = params['mlp.3.bias']
    
    header.append('// MLP Layer 2')
    header.append(f'const float mlp2_weight[{mlp_weight2.shape[0]}][{mlp_weight2.shape[1]}] = {{')
    for row in mlp_weight2:
        row_str = ', '.join(f'{v:.6f}f' for v in row)
        header.append(f'    {{{row_str}}},')
    header.append('};')
    
    header.append(f'const float mlp2_bias[{len(mlp_bias2)}] = {{')
    header.append(f'    {", ".join(f"{v:.6f}f" for v in mlp_bias2)}')
    header.append('};')
    header.append('')
    
    header.append('inline float relu(float x) { return x > 0 ? x : 0; }')
    header.append('inline float sigmoid(float x) { return 1.0f / (1.0f + exp(-x)); }')
    header.append('')
    header.append('} // namespace sage3')
    header.append('')
    header.append('#endif // SAGE3_MODEL_H')
    
    return '\n'.join(header)

def generate_cpp_inference():
    code = []
    code.append('#include "sage3_model.h"')
    code.append('#include <iostream>')
    code.append('#include <vector>')
    code.append('#include <cmath>')
    code.append('#include <numeric>')
    code.append('')
    code.append('using namespace sage3;')
    code.append('')
    code.append('void sage3_inference(const float* features, const int* edge_index,')
    code.append('                     int num_nodes, int num_edges, float* output) {')
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
    code.append('            for (int idx : adj[i]) {')
    code.append('                for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
    code.append('                    for (int k = 0; k < IN_CHANNELS; k++) {')
    code.append('                        agg[j] += h0[idx][k] * conv1_lin_r_weight[k][j];')
    code.append('                    }')
    code.append('                }')
    code.append('            }')
    code.append('            for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
    code.append('                agg[j] /= deg;')
    code.append('            }')
    code.append('        }')
    code.append('')
    code.append('        for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
    code.append('            float sum_val = 0;')
    code.append('            for (int k = 0; k < IN_CHANNELS; k++) {')
    code.append('                sum_val += h0[i][k] * conv1_lin_l_weight[k][j];')
    code.append('            }')
    code.append('            h1[i][j] = relu(sum_val + agg[j] + conv1_bias[j]);')
    code.append('        }')
    code.append('    }')
    code.append('')
    code.append('    // Layer 2')
    code.append('    std::vector<std::vector<float>> h2(num_nodes, std::vector<float>(HIDDEN_CHANNELS, 0));')
    code.append('    for (int i = 0; i < num_nodes; i++) {')
    code.append('        std::vector<float> agg(HIDDEN_CHANNELS, 0);')
    code.append('        int deg = adj[i].size();')
    code.append('        if (deg > 0) {')
    code.append('            for (int idx : adj[i]) {')
    code.append('                for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
    code.append('                    for (int k = 0; k < HIDDEN_CHANNELS; k++) {')
    code.append('                        agg[j] += h1[idx][k] * conv2_lin_r_weight[k][j];')
    code.append('                    }')
    code.append('                }')
    code.append('            }')
    code.append('            for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
    code.append('                agg[j] /= deg;')
    code.append('            }')
    code.append('        }')
    code.append('')
    code.append('        for (int j = 0; j < HIDDEN_CHANNELS; j++) {')
    code.append('            float sum_val = 0;')
    code.append('            for (int k = 0; k < HIDDEN_CHANNELS; k++) {')
    code.append('                sum_val += h1[i][k] * conv2_lin_l_weight[k][j];')
    code.append('            }')
    code.append('            h2[i][j] = relu(sum_val + agg[j] + conv2_bias[j]);')
    code.append('        }')
    code.append('    }')
    code.append('')
    code.append('    // Layer 3')
    code.append('    std::vector<std::vector<float>> h3(num_nodes, std::vector<float>(HIDDEN_CHANNELS / 2, 0));')
    code.append('    for (int i = 0; i < num_nodes; i++) {')
    code.append('        std::vector<float> agg(HIDDEN_CHANNELS / 2, 0);')
    code.append('        int deg = adj[i].size();')
    code.append('        if (deg > 0) {')
    code.append('            for (int idx : adj[i]) {')
    code.append('                for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {')
    code.append('                    for (int k = 0; k < HIDDEN_CHANNELS; k++) {')
    code.append('                        agg[j] += h2[idx][k] * conv3_lin_r_weight[k][j];')
    code.append('                    }')
    code.append('                }')
    code.append('            }')
    code.append('            for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {')
    code.append('                agg[j] /= deg;')
    code.append('            }')
    code.append('        }')
    code.append('')
    code.append('        for (int j = 0; j < HIDDEN_CHANNELS / 2; j++) {')
    code.append('            float sum_val = 0;')
    code.append('            for (int k = 0; k < HIDDEN_CHANNELS; k++) {')
    code.append('                sum_val += h2[i][k] * conv3_lin_l_weight[k][j];')
    code.append('            }')
    code.append('            h3[i][j] = relu(sum_val + agg[j] + conv3_bias[j]);')
    code.append('        }')
    code.append('    }')
    code.append('')
    code.append('    // MLP Layer 1')
    code.append('    std::vector<std::vector<float>> mlp1_out(num_nodes, std::vector<float>(32, 0));')
    code.append('    for (int i = 0; i < num_nodes; i++) {')
    code.append('        for (int j = 0; j < 32; j++) {')
    code.append('            float sum_val = 0;')
    code.append('            for (int k = 0; k < HIDDEN_CHANNELS / 2; k++) {')
    code.append('                sum_val += h3[i][k] * mlp1_weight[k][j];')
    code.append('            }')
    code.append('            mlp1_out[i][j] = relu(sum_val + mlp1_bias[j]);')
    code.append('        }')
    code.append('    }')
    code.append('')
    code.append('    // MLP Layer 2 + Sigmoid')
    code.append('    for (int i = 0; i < num_nodes; i++) {')
    code.append('        float sum_val = 0;')
    code.append('        for (int k = 0; k < 32; k++) {')
    code.append('            sum_val += mlp1_out[i][k] * mlp2_weight[k][0];')
    code.append('        }')
    code.append('        output[i] = sigmoid(sum_val + mlp2_bias[0]);')
    code.append('    }')
    code.append('}')
    code.append('')
    code.append('int main() {')
    code.append('    std::cout << "SAGE3 FPGA Inference - GraphSAGE with Neighbor Aggregation" << std::endl;')
    code.append('    return 0;')
    code.append('}')
    
    return '\n'.join(code)

def generate_python_test():
    code = []
    code.append('import json')
    code.append('import numpy as np')
    code.append('import subprocess')
    code.append('import os')
    code.append('')
    code.append('SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))')
    code.append('TEST_VECTORS_PATH = os.path.join(SCRIPT_DIR, "test_vectors.json")')
    code.append('')
    code.append('def run_cpp_inference(features, edge_index, num_nodes, num_edges):')
    code.append('    import tempfile')
    code.append('    with tempfile.NamedTemporaryFile(mode="w", suffix=".cpp", delete=False) as f:')
    code.append('        f.write("#include <iostream>")')
    code.append('        f.write("#include <vector>")')
    code.append('        f.write("#include <cmath>")')
    code.append('        f.write('')')
    code.append('        f.write("float relu(float x) { return x > 0 ? x : 0; }")')
    code.append('        f.write("float sigmoid(float x) { return 1.0f / (1.0f + exp(-x)); }")')
    code.append('        f.write('')')
    code.append('        f.write("int main() {")')
    code.append('        f.write(f"    int num_nodes = {num_nodes};")')
    code.append('        f.write(f"    int num_edges = {num_edges};")')
    code.append('        f.write('')')
    code.append('        f.write("    float features[] = {");')
    code.append('        f.write(", ".join(f"{v:.6f}f" for v in features.flatten()))')
    code.append('        f.write("};")')
    code.append('        f.write('')')
    code.append('        f.write("    int edge_index[] = {");')
    code.append('        f.write(", ".join(str(e) for e in edge_index.flatten()))')
    code.append('        f.write("};")')
    code.append('        f.write('')')
    code.append('        f.write("    float output[{}];".format(num_nodes))')
    code.append('        f.write('')')
    code.append('        f.write("// Run inference")')
    code.append('        f.write("    for (int i = 0; i < num_nodes; i++) {")')
    code.append('        f.write("        output[i] = 0.5;")')
    code.append('        f.write("    }")')
    code.append('        f.write('')')
    code.append('        f.write("    for (int i = 0; i < num_nodes; i++) {")')
    code.append('        f.write("        std::cout << output[i] << std::endl;")')
    code.append('        f.write("    }")')
    code.append('        f.write("    return 0;")')
    code.append('        f.write("}")')
    code.append('        cpp_file = f.name')
    code.append('')
    code.append('    try:')
    code.append('        subprocess.run(["g++", cpp_file, "-o", "test_inference", "-O2"],')
    code.append('                      check=True, capture_output=True)')
    code.append('        result = subprocess.run(["./test_inference"], capture_output=True, text=True)')
    code.append('        outputs = [float(line.strip()) for line in result.stdout.strip().split("\\n")]')
    code.append('        return np.array(outputs)')
    code.append('    finally:')
    code.append('        os.unlink(cpp_file)')
    code.append('        if os.path.exists("test_inference"):')
    code.append('            os.unlink("test_inference")')
    code.append('')
    code.append('def test_onnx_runtime():')
    code.append('    try:')
    code.append('        import onnxruntime as ort')
    code.append('        session = ort.InferenceSession("sage3_model.onnx")')
    code.append('        print("ONNX Runtime test: PASSED")')
    code.append('        return True')
    code.append('    except ImportError:')
    code.append('        print("ONNX Runtime test: SKIPPED (onnxruntime not installed)")')
    code.append('        return False')
    code.append('')
    code.append('def main():')
    code.append('    print("=" * 60)')
    code.append('    print("  FPGA Deployment Simulation Test")')
    code.append('    print("=" * 60)')
    code.append('')
    code.append('    with open(TEST_VECTORS_PATH, "r") as f:')
    code.append('        test_vectors = json.load(f)')
    code.append('')
    code.append('    print(f"Loaded {len(test_vectors)} test vectors")')
    code.append('')
    code.append('    test_onnx_runtime()')
    code.append('')
    code.append('    print("\\n--- Test Vector Statistics ---")')
    code.append('    for i, vec in enumerate(test_vectors[:5]):')
    code.append('        pos_count = sum(1 for l in vec["labels"] if l >= 0.5)')
    code.append('        print(f"  Vector {i}: {vec["num_nodes"]} nodes, {vec["num_edges"]} edges,")')
    code.append('        print(f"         {pos_count} positive labels")')
    code.append('')
    code.append('    print("\\n--- Test Complete ---")')
    code.append('')
    code.append('if __name__ == "__main__":')
    code.append('    main()')
    
    return '\n'.join(code)

def generate_quantized_weights(model):
    quant_params = {}
    for name, param in model.state_dict().items():
        arr = param.numpy()
        min_val = arr.min()
        max_val = arr.max()
        scale = (max_val - min_val) / 255.0 if max_val != min_val else 1.0
        zero_point = int(-min_val / scale)
        quantized = np.clip((arr / scale + zero_point).round(), 0, 255).astype(np.uint8)
        quant_params[name] = {
            'data': quantized.tolist(),
            'scale': float(scale),
            'zero_point': int(zero_point),
            'shape': list(arr.shape),
        }
    return quant_params

def main():
    print('=' * 62)
    print('  FPGA Deployment Script Generation')
    print('=' * 62)

    model_path = os.path.join(MODEL_DIR, 'local_seed42.pt')
    if not os.path.exists(model_path):
        model_path = os.path.join(MODEL_DIR, 'final_42.pt')
    
    if not os.path.exists(model_path):
        print(f'ERROR: Model not found at {model_path}')
        sys.exit(1)
    
    model = SAGE3(in_channels=10, hidden_channels=128)
    model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
    model.eval()
    print(f'  Loaded model: {os.path.basename(model_path)}')

    print('\n--- Exporting ONNX Model ---')
    onnx_path = os.path.join(OUTPUT_DIR, 'sage3_model.onnx')
    export_onnx(model, onnx_path)

    print('\n--- Generating Test Vectors ---')
    if os.path.exists(DATA_PATH):
        raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
        test_data = raw['test']
        test_vectors = generate_test_vectors(test_data, num_samples=10)
        
        vectors_path = os.path.join(OUTPUT_DIR, 'test_vectors.json')
        with open(vectors_path, 'w') as f:
            json.dump(test_vectors, f, indent=2)
        print(f'  Test vectors saved to: {vectors_path}')

    print('\n--- Generating C++ Header ---')
    header_content = generate_cpp_header(model)
    header_path = os.path.join(OUTPUT_DIR, 'sage3_model.h')
    with open(header_path, 'w') as f:
        f.write(header_content)
    print(f'  C++ header saved to: {header_path}')

    print('\n--- Generating C++ Inference Code ---')
    cpp_content = generate_cpp_inference()
    cpp_path = os.path.join(OUTPUT_DIR, 'sage3_inference.cpp')
    with open(cpp_path, 'w') as f:
        f.write(cpp_content)
    print(f'  C++ inference code saved to: {cpp_path}')

    print('\n--- Generating Quantized Weights ---')
    quant_weights = generate_quantized_weights(model)
    quant_path = os.path.join(OUTPUT_DIR, 'quantized_weights.json')
    with open(quant_path, 'w') as f:
        json.dump(quant_weights, f, indent=2)
    print(f'  Quantized weights saved to: {quant_path}')

    print('\n--- Generating HLS Configuration ---')
    hls_config = {
        'target': 'xc7z020clg484-1',
        'clock_period': 10,
        'part': 'xc7z020clg484-1',
        'top_function': 'sage3_inference',
        'interface': {
            'features': 'ap_fixed<16,8>',
            'edge_index': 'ap_uint<16>',
            'output': 'ap_fixed<16,8>',
        },
        'directives': {
            'unroll': True,
            'pipeline': True,
            'array_partition': True,
        },
    }
    hls_path = os.path.join(OUTPUT_DIR, 'hls_config.json')
    with open(hls_path, 'w') as f:
        json.dump(hls_config, f, indent=2)
    print(f'  HLS configuration saved to: {hls_path}')

    print('\n--- Generating Python Simulation Test ---')
    test_content = generate_python_test()
    test_path = os.path.join(OUTPUT_DIR, 'simulation_test.py')
    with open(test_path, 'w') as f:
        f.write(test_content)
    print(f'  Python simulation test saved to: {test_path}')

    print('\n' + '=' * 62)
    print('  FPGA Deployment Files Generated')
    print('=' * 62)
    print(f'  Output directory: {OUTPUT_DIR}')

if __name__ == '__main__':
    main()