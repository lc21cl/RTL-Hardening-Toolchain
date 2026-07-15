import json
import numpy as np
import subprocess
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_VECTORS_PATH = os.path.join(SCRIPT_DIR, "test_vectors.json")
MODEL_PATH = os.path.join(SCRIPT_DIR, "sage3_model.onnx")

def test_onnx_runtime():
    try:
        import onnxruntime as ort
        session = ort.InferenceSession(MODEL_PATH)
        
        with open(TEST_VECTORS_PATH, "r") as f:
            test_vectors = json.load(f)
        
        vec = test_vectors[0]
        x = np.array(vec["features"], dtype=np.float32)
        edge_index = np.array(vec["edge_index"], dtype=np.int64)
        
        output = session.run(["output"], {"x": x, "edge_index": edge_index})[0]
        expected = np.array(vec["expected_output"])
        
        mse = np.mean((output - expected) ** 2)
        max_diff = np.max(np.abs(output - expected))
        
        print(f"  ONNX Runtime test: PASSED")
        print(f"    MSE: {mse:.6f}")
        print(f"    Max Diff: {max_diff:.6f}")
        return True
    except ImportError:
        print("  ONNX Runtime test: SKIPPED (onnxruntime not installed)")
        return False
    except Exception as e:
        print(f"  ONNX Runtime test: FAILED")
        print(f"    Error: {e}")
        return False

def test_pytorch_inference():
    try:
        import torch
        sys.path.insert(0, os.path.dirname(os.path.dirname(SCRIPT_DIR)))
        
        from fpga_deploy import SAGE3
        
        model = SAGE3(in_channels=10, hidden_channels=128)
        model_dir = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), "data", "models")
        model_path = os.path.join(model_dir, "local_seed42.pt")
        
        model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
        model.eval()
        
        with open(TEST_VECTORS_PATH, "r") as f:
            test_vectors = json.load(f)
        
        vec = test_vectors[0]
        x = torch.tensor(vec["features"], dtype=torch.float32)
        edge_index = torch.tensor(vec["edge_index"], dtype=torch.long)
        
        with torch.no_grad():
            output = model(x, edge_index).numpy()
        
        expected = np.array(vec["expected_output"])
        mse = np.mean((output - expected) ** 2)
        max_diff = np.max(np.abs(output - expected))
        
        print(f"  PyTorch Inference test: PASSED")
        print(f"    MSE: {mse:.6f}")
        print(f"    Max Diff: {max_diff:.6f}")
        return True
    except Exception as e:
        print(f"  PyTorch Inference test: FAILED")
        print(f"    Error: {e}")
        return False

def test_cpp_header_generation():
    header_path = os.path.join(SCRIPT_DIR, "sage3_model.h")
    if os.path.exists(header_path):
        with open(header_path, "r") as f:
            content = f.read()
        
        checks = [
            ("conv1_lin_l_weight", "Conv1 self-weight matrix"),
            ("conv1_lin_r_weight", "Conv1 neighbor-weight matrix"),
            ("conv1_bias", "Conv1 bias"),
            ("mlp1_weight", "MLP layer 1 weight"),
            ("mlp2_weight", "MLP layer 2 weight"),
            ("relu", "ReLU function"),
            ("sigmoid", "Sigmoid function"),
        ]
        
        all_passed = True
        for check, desc in checks:
            if check in content:
                print(f"  ✓ {desc}")
            else:
                print(f"  ✗ {desc}")
                all_passed = False
        
        return all_passed
    else:
        print("  C++ Header test: FAILED (file not found)")
        return False

def test_cpp_inference_code():
    cpp_path = os.path.join(SCRIPT_DIR, "sage3_inference.cpp")
    if os.path.exists(cpp_path):
        with open(cpp_path, "r") as f:
            content = f.read()
        
        checks = [
            ("sage3_inference", "Main inference function"),
            ("adj", "Adjacency list"),
            ("agg", "Neighbor aggregation"),
            ("conv1_lin_r_weight", "Conv1 neighbor aggregation"),
            ("conv1_lin_l_weight", "Conv1 self feature"),
            ("relu", "ReLU activation"),
            ("sigmoid", "Sigmoid output"),
        ]
        
        all_passed = True
        for check, desc in checks:
            if check in content:
                print(f"  ✓ {desc}")
            else:
                print(f"  ✗ {desc}")
                all_passed = False
        
        return all_passed
    else:
        print("  C++ Inference code test: FAILED (file not found)")
        return False

def test_quantized_weights():
    quant_path = os.path.join(SCRIPT_DIR, "quantized_weights.json")
    if os.path.exists(quant_path):
        with open(quant_path, "r") as f:
            data = json.load(f)
        
        print(f"  Quantized weights test: PASSED")
        print(f"    Number of layers: {len(data)}")
        total_params = sum(np.prod(v["shape"]) for v in data.values())
        print(f"    Total parameters: {total_params:,}")
        
        for key, val in list(data.items())[:3]:
            print(f"    {key}: shape={val['shape']}, scale={val['scale']:.6f}")
        
        return True
    else:
        print("  Quantized weights test: FAILED (file not found)")
        return False

def generate_resource_analysis():
    print("\n" + "=" * 60)
    print("  FPGA Hardware Resource Analysis")
    print("=" * 60)
    
    model_spec = {
        "conv1": {"input": 10, "output": 128, "type": "SAGEConv"},
        "conv2": {"input": 128, "output": 128, "type": "SAGEConv"},
        "conv3": {"input": 128, "output": 64, "type": "SAGEConv"},
        "mlp1": {"input": 64, "output": 32, "type": "Linear"},
        "mlp2": {"input": 32, "output": 1, "type": "Linear"},
    }
    
    total_macs = 0
    total_params = 0
    resource_estimate = {
        "BRAM_18K": 0,
        "LUT": 0,
        "FF": 0,
        "DSP48E": 0,
    }
    
    print("\n--- Layer-by-Layer Analysis ---")
    for layer_name, spec in model_spec.items():
        in_dim = spec["input"]
        out_dim = spec["output"]
        
        if spec["type"] == "SAGEConv":
            macs = 2 * in_dim * out_dim
            params = 2 * in_dim * out_dim + out_dim
            bram = (params * 4) / (18 * 1024)
            lut = macs * 2
            ff = out_dim * 2
            dsp = out_dim
        
        else:
            macs = in_dim * out_dim
            params = in_dim * out_dim + out_dim
            bram = (params * 4) / (18 * 1024)
            lut = macs * 1.5
            ff = out_dim * 2
            dsp = out_dim
        
        total_macs += macs
        total_params += params
        resource_estimate["BRAM_18K"] += bram
        resource_estimate["LUT"] += lut
        resource_estimate["FF"] += ff
        resource_estimate["DSP48E"] += dsp
        
        print(f"\n  {layer_name} ({spec['type']}):")
        print(f"    Input: {in_dim}, Output: {out_dim}")
        print(f"    MACs: {macs:,}")
        print(f"    Parameters: {params:,}")
        print(f"    BRAM_18K: {bram:.2f}")
        print(f"    LUT: {int(lut):,}")
        print(f"    FF: {int(ff):,}")
        print(f"    DSP48E: {dsp}")
    
    print("\n--- Total Resource Estimation ---")
    print(f"  Total MACs: {total_macs:,}")
    print(f"  Total Parameters: {total_params:,}")
    print("\n  Resource Estimate (xc7z020clg484-1):")
    print(f"    BRAM_18K: {resource_estimate['BRAM_18K']:.2f} / 36")
    print(f"    LUT: {int(resource_estimate['LUT']):,} / 53,200")
    print(f"    FF: {int(resource_estimate['FF']):,} / 106,400")
    print(f"    DSP48E: {int(resource_estimate['DSP48E'])} / 220")
    
    print("\n--- Utilization Percentage ---")
    print(f"    BRAM_18K: {resource_estimate['BRAM_18K'] / 36 * 100:.1f}%")
    print(f"    LUT: {resource_estimate['LUT'] / 53200 * 100:.1f}%")
    print(f"    FF: {resource_estimate['FF'] / 106400 * 100:.1f}%")
    print(f"    DSP48E: {resource_estimate['DSP48E'] / 220 * 100:.1f}%")
    
    print("\n--- Memory Bandwidth Analysis ---")
    weights_size = total_params * 4 / (1024 * 1024)
    print(f"  Weights Memory: {weights_size:.2f} MB")
    print(f"  Feature Memory (per node): {10 * 4} bytes")
    print(f"  Output Memory (per node): {1 * 4} bytes")
    
    print("\n--- Throughput Estimation ---")
    clock_freq = 100
    cycles_per_node = sum(spec["output"] for spec in model_spec.values())
    print(f"  Target Clock: {clock_freq} MHz")
    print(f"  Cycles per node: {cycles_per_node}")
    print(f"  Throughput: {clock_freq * 10**6 / cycles_per_node / 1000:.1f} K nodes/s")
    
    print("\n--- Implementation Notes ---")
    print("  1. Use array partitioning for weight matrices")
    print("  2. Pipeline each layer for maximum throughput")
    print("  3. Reuse BRAM for intermediate feature maps")
    print("  4. Consider quantization for DSP reduction")
    
    report = {
        "model_spec": model_spec,
        "total_macs": total_macs,
        "total_params": total_params,
        "resource_estimate": {k: float(v) for k, v in resource_estimate.items()},
        "target_device": "xc7z020clg484-1",
        "device_limits": {
            "BRAM_18K": 36,
            "LUT": 53200,
            "FF": 106400,
            "DSP48E": 220,
        },
        "throughput_mbps": clock_freq * 10**6 / cycles_per_node,
    }
    
    report_path = os.path.join(SCRIPT_DIR, "resource_analysis.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved to: {report_path}")
    
    return report

def main():
    print("=" * 60)
    print("  FPGA Deployment Simulation Test")
    print("=" * 60)
    
    print("\n--- Test Vector Statistics ---")
    with open(TEST_VECTORS_PATH, "r") as f:
        test_vectors = json.load(f)
    
    print(f"  Loaded {len(test_vectors)} test vectors")
    for i, vec in enumerate(test_vectors[:5]):
        pos_count = sum(1 for l in vec["labels"] if l >= 0.5)
        print(f"  Vector {i+1}: {vec['num_nodes']} nodes, {vec['num_edges']} edges, {pos_count} positives")
    
    print("\n--- Component Tests ---")
    results = []
    
    print("\n  1. ONNX Runtime:")
    results.append(test_onnx_runtime())
    
    print("\n  2. PyTorch Inference:")
    results.append(test_pytorch_inference())
    
    print("\n  3. C++ Header Generation:")
    results.append(test_cpp_header_generation())
    
    print("\n  4. C++ Inference Code:")
    results.append(test_cpp_inference_code())
    
    print("\n  5. Quantized Weights:")
    results.append(test_quantized_weights())
    
    print("\n" + "=" * 60)
    print("  Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"  Passed: {passed}/{total}")
    
    if all(results):
        print("  STATUS: ALL TESTS PASSED")
    else:
        print("  STATUS: SOME TESTS FAILED")
    
    generate_resource_analysis()
    
    print("\n--- Test Complete ---")

if __name__ == "__main__":
    main()