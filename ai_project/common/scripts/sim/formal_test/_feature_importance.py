#!/usr/bin/env python3
"""Feature Importance Analysis for Vulnerability Predictor"""

import os, sys, json
import torch
import torch.nn as nn
import numpy as np
from torch_geometric.nn import SAGEConv
from torch_geometric.data import DataLoader

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data.pt')
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')

FEATURE_NAMES = [
    'node_type_pi',
    'node_type_po',
    'node_type_and',
    'node_type_dff',
    'degree_in',
    'degree_out',
    'depth',
    'is_const',
    'path_length_entropy',
    'betweenness_centrality',
]


class SAGE3(nn.Module):
    def __init__(self, in_channels=10, hidden_channels=128, dropout=0.3):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.conv3 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels // 2, 32), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(32, 1),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv2(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv3(x, edge_index).relu(); x = self.dropout(x)
        return torch.sigmoid(self.mlp(x).squeeze(-1))


def compute_metrics(scores, labels, threshold=0.5):
    from sklearn.metrics import f1_score, mean_squared_error, r2_score
    preds = (scores >= threshold).float()
    binary_labels = (labels >= threshold).float()
    r2 = r2_score(labels.numpy(), scores.numpy())
    return {
        'f1': f1_score(binary_labels.numpy(), preds.numpy(), zero_division=0),
        'mse': mean_squared_error(labels.numpy(), scores.numpy()),
        'r2': r2,
    }


def evaluate(model, data_list, threshold=0.5):
    loader = DataLoader(data_list, batch_size=32, shuffle=False)
    all_scores, all_labels = [], []
    model.eval()
    with torch.no_grad():
        for batch in loader:
            scores = model(batch.x, batch.edge_index)
            all_scores.append(scores.cpu())
            all_labels.append(batch.y.cpu())
    scores = torch.cat(all_scores).float()
    labels = torch.cat(all_labels).float()
    return compute_metrics(scores, labels, threshold)


def feature_permutation_importance(model, data_list, baseline_metrics, threshold=0.5):
    n_features = data_list[0].x.shape[1]
    importances = []
    
    for i in range(n_features):
        print(f'  Permuting feature {i} ({FEATURE_NAMES[i]})...')
        permuted_data = []
        for data in data_list:
            d = data.clone()
            col = d.x[:, i].clone()
            col = col[torch.randperm(len(col))]
            d.x[:, i] = col
            permuted_data.append(d)
        
        metrics = evaluate(model, permuted_data, threshold)
        f1_drop = baseline_metrics['f1'] - metrics['f1']
        mse_increase = metrics['mse'] - baseline_metrics['mse']
        r2_drop = baseline_metrics['r2'] - metrics['r2']
        
        importances.append({
            'feature': FEATURE_NAMES[i],
            'index': i,
            'f1_drop': f1_drop,
            'mse_increase': mse_increase,
            'r2_drop': r2_drop,
            'permuted_f1': metrics['f1'],
            'permuted_mse': metrics['mse'],
            'permuted_r2': metrics['r2'],
        })
        print(f'    F1: {baseline_metrics["f1"]:.4f} -> {metrics["f1"]:.4f} (drop={f1_drop:.4f})')
        print(f'    MSE: {baseline_metrics["mse"]:.4f} -> {metrics["mse"]:.4f} (inc={mse_increase:.4f})')
    
    return importances


def gradient_based_importance(model, data_list):
    n_features = data_list[0].x.shape[1]
    grad_importances = np.zeros(n_features)
    n_samples = 0
    
    model.train()
    for data in data_list[:50]:
        data.x.requires_grad = True
        model.zero_grad()
        scores = model(data.x, data.edge_index)
        loss = nn.MSELoss()(scores, data.y.float())
        loss.backward()
        
        if data.x.grad is not None:
            grad_importances += data.x.grad.abs().mean(dim=0).cpu().numpy()
            n_samples += 1
    
    grad_importances /= n_samples
    return grad_importances


def main():
    print('=' * 70)
    print('  Feature Importance Analysis')
    print('=' * 70)

    model_path = os.path.join(MODEL_DIR, 'local_best_model.pt')
    if not os.path.exists(model_path):
        model_path = os.path.join(MODEL_DIR, 'local_seed42.pt')
    print(f'  Model: {model_path}')

    state = torch.load(model_path, map_location='cpu', weights_only=False)
    model = SAGE3(in_channels=10, hidden_channels=128, dropout=0.3)
    model.load_state_dict(state)

    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    val_data = raw['val']
    print(f'  Validation samples: {len(val_data)}')

    print('\n--- Baseline Evaluation ---')
    baseline = evaluate(model, val_data)
    print(f'  Baseline F1: {baseline["f1"]:.4f}')
    print(f'  Baseline MSE: {baseline["mse"]:.4f}')
    print(f'  Baseline R2: {baseline["r2"]:.4f}')

    print('\n--- Permutation Importance ---')
    perm_importances = feature_permutation_importance(model, val_data, baseline)

    print('\n--- Gradient-Based Importance ---')
    grad_importances = gradient_based_importance(model, val_data)

    print('\n' + '=' * 70)
    print('  Summary: Feature Importance')
    print('=' * 70)
    print(f'  {"Feature":<30} {"F1 Drop":>10} {"MSE Inc":>10} {"R2 Drop":>10} {"Grad Imp":>10}')
    print('  ' + '-' * 70)
    
    for imp, grad in zip(perm_importances, grad_importances):
        print(f'  {imp["feature"]:<30} {imp["f1_drop"]:>10.4f} {imp["mse_increase"]:>10.4f} '
              f'{imp["r2_drop"]:>10.4f} {grad:>10.4f}')

    print('\n--- Top Features by F1 Drop ---')
    for i, imp in enumerate(sorted(perm_importances, key=lambda x: -x['f1_drop'])[:5]):
        print(f'  {i+1}. {imp["feature"]}: F1 drop = {imp["f1_drop"]:.4f}')

    results = {
        'baseline': baseline,
        'permutation_importance': perm_importances,
        'gradient_importance': {
            'feature_names': FEATURE_NAMES,
            'values': grad_importances.tolist(),
        },
    }
    with open(os.path.join(SCRIPT_DIR, 'data', 'feature_importance.json'), 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  Results saved to data/feature_importance.json')
    print('=' * 70)


if __name__ == '__main__':
    main()
