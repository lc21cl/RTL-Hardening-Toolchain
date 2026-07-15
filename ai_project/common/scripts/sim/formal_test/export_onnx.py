import os
import sys
import torch
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
ONNX_DIR = os.path.join(SCRIPT_DIR, 'data', 'onnx')

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

class SAGE3Inference(torch.nn.Module):
    def __init__(self, in_channels=10, hidden_channels=128):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.conv3 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = torch.nn.Sequential(
            torch.nn.Linear(hidden_channels // 2, 32), torch.nn.ReLU(),
            torch.nn.Linear(32, 1),
        )

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        x = self.conv2(x, edge_index).relu()
        x = self.conv3(x, edge_index).relu()
        return torch.sigmoid(self.mlp(x).squeeze(-1))

def export_model(seed, batch_size=32, hidden_channels=128):
    os.makedirs(ONNX_DIR, exist_ok=True)
    
    model_path = os.path.join(MODEL_DIR, f'local_seed{seed}.pt')
    if not os.path.exists(model_path):
        model_path = os.path.join(MODEL_DIR, f'final_{seed}.pt')
    if not os.path.exists(model_path):
        print(f'  Warning: Model not found: {model_path}')
        return None
    
    original_model = SAGE3(in_channels=10, hidden_channels=hidden_channels)
    original_model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
    original_model.eval()

    dummy_node_features = torch.randn(batch_size, 10)
    dummy_edge_index = torch.randint(0, batch_size, (2, batch_size * 3))

    onnx_path = os.path.join(ONNX_DIR, f'vulnerability_seed{seed}.onnx')
    
    torch.onnx.export(
        original_model,
        (dummy_node_features, dummy_edge_index),
        onnx_path,
        input_names=['node_features', 'edge_index'],
        output_names=['vulnerability_scores'],
        dynamic_axes={
            'node_features': {0: 'num_nodes'},
            'edge_index': {1: 'num_edges'},
            'vulnerability_scores': {0: 'num_nodes'}
        },
        opset_version=18,
        do_constant_folding=True,
        verbose=False,
        export_params=True,
        training=torch.onnx.TrainingMode.EVAL,
    )
    
    print(f'  Exported: {onnx_path}')
    return onnx_path

def test_onnx_export(seed):
    import onnxruntime as ort
    import numpy as np
    
    onnx_path = os.path.join(ONNX_DIR, f'vulnerability_seed{seed}.onnx')
    if not os.path.exists(onnx_path):
        return False
    
    original_model = SAGE3(in_channels=10, hidden_channels=128)
    model_path = os.path.join(MODEL_DIR, f'local_seed{seed}.pt')
    if not os.path.exists(model_path):
        model_path = os.path.join(MODEL_DIR, f'final_{seed}.pt')
    original_model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
    original_model.eval()
    
    ort_session = ort.InferenceSession(onnx_path)
    
    test_nodes = torch.randn(100, 10)
    test_edges = torch.randint(0, 100, (2, 200))
    
    with torch.no_grad():
        torch_output = original_model(test_nodes, test_edges)
    
    onnx_output = ort_session.run(
        ['vulnerability_scores'],
        {
            'node_features': test_nodes.numpy(),
            'edge_index': test_edges.numpy().astype(np.int64)
        }
    )[0]
    
    torch_output = torch_output.cpu().numpy()
    
    max_diff = np.max(np.abs(torch_output - onnx_output))
    print(f'  ONNX vs PyTorch max diff: {max_diff:.8f}')
    
    return max_diff < 1e-5

def export_ensemble_onnx(seeds, weights):
    os.makedirs(ONNX_DIR, exist_ok=True)
    
    all_models = []
    for seed in seeds:
        model_path = os.path.join(MODEL_DIR, f'local_seed{seed}_final.pt')
        if os.path.exists(model_path):
            model = SAGE3Inference(in_channels=10, hidden_channels=128)
            model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
            model.eval()
            all_models.append(model)
    
    if len(all_models) == 0:
        print('  Error: No models found for ensemble export')
        return None
    
    class EnsembleModel(torch.nn.Module):
        def __init__(self, models, weights):
            super().__init__()
            self.models = torch.nn.ModuleList(models)
            self.weights = torch.tensor(weights)
        
        def forward(self, x, edge_index):
            outputs = []
            for model in self.models:
                out = model(x, edge_index)
                outputs.append(out)
            stacked = torch.stack(outputs, dim=1)
            weighted = stacked * self.weights.view(1, -1, 1)
            return weighted.sum(dim=1)
    
    ensemble_model = EnsembleModel(all_models, weights)
    
    dummy_node_features = torch.randn(32, 10)
    dummy_edge_index = torch.randint(0, 32, (2, 96))
    
    onnx_path = os.path.join(ONNX_DIR, 'vulnerability_ensemble.onnx')
    
    torch.onnx.export(
        ensemble_model,
        (dummy_node_features, dummy_edge_index),
        onnx_path,
        input_names=['node_features', 'edge_index'],
        output_names=['vulnerability_scores'],
        dynamic_axes={
            'node_features': {0: 'num_nodes'},
            'edge_index': {1: 'num_edges'},
            'vulnerability_scores': {0: 'num_nodes'}
        },
        opset_version=15,
        do_constant_folding=True,
        verbose=False,
        export_params=True,
    )
    
    print(f'  Exported ensemble: {onnx_path}')
    return onnx_path

def main():
    print('=' * 62)
    print('  ONNX Export — Vulnerability Predictor')
    print('=' * 62)

    os.makedirs(ONNX_DIR, exist_ok=True)
    seeds = [42, 456, 1111]

    print('\n--- Exporting Individual Models ---')
    for seed in seeds:
        export_model(seed)

    print('\n--- Testing ONNX Exports ---')
    import numpy as np
    for seed in seeds:
        success = test_onnx_export(seed)
        print(f'  Seed {seed}: {"PASS" if success else "FAIL"}')

    print('\n--- Exporting Ensemble Model ---')
    ensemble_config_path = os.path.join(MODEL_DIR, 'ensemble_config.pt')
    if os.path.exists(ensemble_config_path):
        config = torch.load(ensemble_config_path, map_location='cpu', weights_only=False)
        weights = config.get('weights', [1.0/len(seeds)] * len(seeds))
        export_ensemble_onnx(seeds, weights)
    else:
        print('  Warning: Ensemble config not found, using uniform weights')
        export_ensemble_onnx(seeds, [1.0/len(seeds)] * len(seeds))

    print('\n--- Generating Deployment Info ---')
    deployment_info = {
        'model_name': 'VulnerabilityPredictor_SAGE3',
        'input_dimensions': {
            'node_features': {'shape': ['num_nodes', 10], 'dtype': 'float32'},
            'edge_index': {'shape': [2, 'num_edges'], 'dtype': 'int64'},
        },
        'output_dimensions': {
            'vulnerability_scores': {'shape': ['num_nodes', 1], 'dtype': 'float32'},
        },
        'feature_names': [
            'node_type_pi', 'node_type_po', 'node_type_and', 'node_type_dff',
            'degree_in', 'degree_out', 'depth', 'is_const',
            'path_length_entropy', 'betweenness_centrality',
        ],
        'scaling': {
            'degree_in': {'normalization': 'divide_by_max', 'max_value': 'per_graph'},
            'degree_out': {'normalization': 'divide_by_max', 'max_value': 'per_graph'},
            'depth': {'normalization': 'divide_by_max', 'max_value': 'per_graph'},
            'path_length_entropy': {'normalization': 'divide_by_max', 'max_value': 'per_graph'},
            'betweenness_centrality': {'normalization': 'divide_by_max', 'max_value': 'per_graph'},
        },
        'onnx_models': {
            'individual': [f'vulnerability_seed{s}.onnx' for s in seeds],
            'ensemble': 'vulnerability_ensemble.onnx',
        },
        'opsets': 15,
    }
    
    info_path = os.path.join(ONNX_DIR, 'deployment_info.json')
    import json
    with open(info_path, 'w') as f:
        json.dump(deployment_info, f, indent=2)
    print(f'  Saved deployment info: {info_path}')

    print('\n' + '=' * 62)
    print('  ONNX Export Complete')
    print('=' * 62)

if __name__ == '__main__':
    main()