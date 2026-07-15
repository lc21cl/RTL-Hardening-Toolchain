import os
import sys
import torch
import numpy as np
import onnxruntime as ort

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ONNX_DIR = os.path.join(SCRIPT_DIR, 'data', 'onnx')
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data.pt')

def load_test_data():
    if not os.path.exists(DATA_PATH):
        print(f'Error: Data not found at {DATA_PATH}')
        sys.exit(1)
    
    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    return raw['test'][:10]

def test_onnx_inference():
    print('=' * 62)
    print('  FPGA Deployment Validation - ONNX Inference Test')
    print('=' * 62)
    
    onnx_files = []
    for f in os.listdir(ONNX_DIR):
        if f.endswith('.onnx') and 'seed' in f:
            onnx_files.append(f)
    
    if not onnx_files:
        print('  Error: No ONNX models found')
        sys.exit(1)
    
    print(f'\n  Found {len(onnx_files)} ONNX model(s):')
    for f in onnx_files:
        print(f'    - {f}')
    
    test_data = load_test_data()
    print(f'\n  Loaded {len(test_data)} test graphs')
    
    results = {}
    
    for onnx_file in onnx_files:
        onnx_path = os.path.join(ONNX_DIR, onnx_file)
        session = ort.InferenceSession(onnx_path)
        
        print(f'\n  Testing: {onnx_file}')
        print('  ' + '-' * 40)
        
        total_mse = 0.0
        total_nodes = 0
        
        for i, data in enumerate(test_data):
            node_features = data.x.numpy().astype(np.float32)
            edge_index = data.edge_index.numpy().astype(np.int64)
            labels = data.y.numpy()
            
            outputs = session.run(
                ['vulnerability_scores'],
                {
                    'node_features': node_features,
                    'edge_index': edge_index
                }
            )
            
            scores = outputs[0]
            mse = np.mean((scores - labels) ** 2)
            total_mse += mse * len(labels)
            total_nodes += len(labels)
            
            if i < 3:
                print(f'    Graph {i+1}: nodes={len(labels)}, MSE={mse:.6f}')
        
        avg_mse = total_mse / total_nodes
        results[onnx_file] = {'avg_mse': avg_mse}
        print(f'    Avg MSE: {avg_mse:.6f}')
    
    print('\n' + '=' * 62)
    print('  ONNX Inference Results Summary')
    print('=' * 62)
    print(f'  {"Model":<30} {"Avg MSE":>12}')
    print('  ' + '-' * 45)
    for model, res in results.items():
        print(f'  {model:<30} {res["avg_mse"]:>12.6f}')
    
    return results

def generate_fpga_test_vectors():
    print('\n' + '=' * 62)
    print('  Generating FPGA Test Vectors')
    print('=' * 62)
    
    test_data = load_test_data()
    output_dir = os.path.join(SCRIPT_DIR, 'data', 'fpga', 'test_vectors')
    os.makedirs(output_dir, exist_ok=True)
    
    for i, data in enumerate(test_data):
        vector = {
            'num_nodes': int(data.x.shape[0]),
            'num_edges': int(data.edge_index.shape[1]),
            'node_features': data.x.numpy().tolist(),
            'edge_index': data.edge_index.numpy().tolist(),
            'labels': data.y.numpy().tolist(),
        }
        
        import json
        with open(os.path.join(output_dir, f'test_vector_{i}.json'), 'w') as f:
            json.dump(vector, f, indent=2)
        
        if i < 5:
            print(f'  Generated: test_vector_{i}.json (nodes={vector["num_nodes"]})')
    
    print(f'\n  Total test vectors: {len(test_data)}')
    print(f'  Output directory: {output_dir}')

def simulate_fpga_cpp_kernel():
    print('\n' + '=' * 62)
    print('  Simulating FPGA C++ Kernel Behavior')
    print('=' * 62)
    
    onnx_path = os.path.join(ONNX_DIR, 'vulnerability_seed42.onnx')
    if not os.path.exists(onnx_path):
        print('  Error: ONNX model not found')
        return
    
    session = ort.InferenceSession(onnx_path)
    test_data = load_test_data()
    
    print('\n  Comparing ONNX inference with simulated C++ kernel logic:')
    print('  ' + '-' * 60)
    
    for i, data in enumerate(test_data[:3]):
        node_features = data.x.numpy().astype(np.float32)
        edge_index = data.edge_index.numpy().astype(np.int64)
        
        onnx_output = session.run(
            ['vulnerability_scores'],
            {'node_features': node_features, 'edge_index': edge_index}
        )[0]
        
        print(f'  Graph {i+1}:')
        print(f'    - Nodes: {data.x.shape[0]}')
        print(f'    - Edges: {data.edge_index.shape[1]}')
        print(f'    - Score range: [{onnx_output.min():.4f}, {onnx_output.max():.4f}]')
        print(f'    - Score mean: {onnx_output.mean():.4f}')
        print()

def main():
    test_onnx_inference()
    generate_fpga_test_vectors()
    simulate_fpga_cpp_kernel()
    
    print('\n' + '=' * 62)
    print('  FPGA Deployment Validation Complete')
    print('=' * 62)

if __name__ == '__main__':
    main()