import os
import sys
import torch
import torch.nn.functional as F
import numpy as np
import matplotlib.pyplot as plt
from torch_geometric.nn import SAGEConv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data.pt')
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'data', 'figures')

OLD_FEATURE_NAMES = [
    'node_type_pi',
    'node_type_po',
    'node_type_and',
    'node_type_dff',
    'degree_in',
    'degree_out',
    'depth',
    'is_const',
    'local_clustering_coefficient',
    'structural_diversity',
]

NEW_FEATURE_NAMES = [
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

def compute_metrics(scores, labels, threshold=0.5):
    scores = scores.flatten().numpy()
    labels = labels.flatten().numpy()
    predictions = (scores >= threshold).astype(int)
    
    tp = np.sum((predictions == 1) & (labels >= threshold))
    fp = np.sum((predictions == 1) & (labels < threshold))
    fn = np.sum((predictions == 0) & (labels >= threshold))
    
    precision = tp / (tp + fp + 1e-6)
    recall = tp / (tp + fn + 1e-6)
    f1 = 2 * precision * recall / (precision + recall + 1e-6)
    
    mse = np.mean((scores - labels) ** 2)
    mae = np.mean(np.abs(scores - labels))
    r2 = 1 - np.sum((labels - scores) ** 2) / np.sum((labels - np.mean(labels)) ** 2)
    
    return {
        'f1': f1, 'precision': precision, 'recall': recall,
        'mse': mse, 'mae': mae, 'r2': r2,
    }

def load_model_and_data():
    if not os.path.exists(DATA_PATH):
        print(f'Error: Data not found at {DATA_PATH}')
        sys.exit(1)
    
    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    val_data = raw['val']
    
    model_paths = []
    for seed in [42, 456, 1111]:
        p1 = os.path.join(MODEL_DIR, f'local_seed{seed}.pt')
        p2 = os.path.join(MODEL_DIR, f'final_{seed}.pt')
        if os.path.exists(p1):
            model_paths.append(p1)
        elif os.path.exists(p2):
            model_paths.append(p2)
    
    if not model_paths:
        print('Error: No models found')
        sys.exit(1)
    
    model = SAGE3(in_channels=10, hidden_channels=128)
    model.load_state_dict(torch.load(model_paths[0], map_location='cpu', weights_only=True))
    model.eval()
    
    return model, val_data

def feature_permutation_importance(model, data_list, baseline_metrics):
    n_features = data_list[0].x.shape[1]
    importances = []
    
    for i in range(n_features):
        permuted_data = [data.clone() for data in data_list]
        for d in permuted_data:
            d.x[:, i] = d.x[:, i][torch.randperm(len(d.x))]
        
        all_s, all_l = [], []
        for data in permuted_data:
            with torch.no_grad():
                pred = model(data.x, data.edge_index)
            all_s.append(pred)
            all_l.append(data.y)
        scores = torch.cat(all_s)
        labels = torch.cat(all_l)
        
        best_f1 = 0.0
        best_th = 0.5
        for th in [x / 100 for x in range(5, 96, 2)]:
            m = compute_metrics(scores, labels, threshold=th)
            if m['f1'] > best_f1:
                best_f1 = m['f1']
                best_th = th
        
        m = compute_metrics(scores, labels, threshold=best_th)
        
        importances.append({
            'index': i,
            'name': NEW_FEATURE_NAMES[i],
            'f1_drop': baseline_metrics['f1'] - m['f1'],
            'mse_increase': m['mse'] - baseline_metrics['mse'],
            'r2_drop': baseline_metrics['r2'] - m['r2'],
        })
    
    return importances

def compute_baseline(model, data_list):
    all_s, all_l = [], []
    for data in data_list:
        with torch.no_grad():
            pred = model(data.x, data.edge_index)
        all_s.append(pred)
        all_l.append(data.y)
    scores = torch.cat(all_s)
    labels = torch.cat(all_l)
    
    best_f1 = 0.0
    best_th = 0.5
    for th in [x / 100 for x in range(5, 96, 2)]:
        m = compute_metrics(scores, labels, threshold=th)
        if m['f1'] > best_f1:
            best_f1 = m['f1']
            best_th = th
    
    return compute_metrics(scores, labels, threshold=best_th)

def compute_feature_correlation(data_list):
    features = []
    labels = []
    
    for data in data_list:
        features.append(data.x.numpy())
        labels.append(data.y.numpy())
    
    features = np.vstack(features)
    labels = np.concatenate(labels)
    
    correlations = []
    for i in range(features.shape[1]):
        corr = np.corrcoef(features[:, i], labels)[0, 1] if len(features) > 1 else 0.0
        correlations.append({
            'index': i,
            'name': NEW_FEATURE_NAMES[i],
            'correlation': corr,
        })
    
    return correlations

def generate_report():
    print('=' * 62)
    print('  Feature Importance Analysis Report')
    print('=' * 62)
    
    model, val_data = load_model_and_data()
    print(f'\n  Loaded model with {sum(p.numel() for p in model.parameters() if p.requires_grad):,} parameters')
    print(f'  Validation samples: {len(val_data)}')
    
    print('\n--- Baseline Evaluation ---')
    baseline = compute_baseline(model, val_data)
    print(f'  Baseline F1: {baseline["f1"]:.4f}')
    print(f'  Baseline MSE: {baseline["mse"]:.4f}')
    print(f'  Baseline R2: {baseline["r2"]:.4f}')
    
    print('\n--- Permutation Importance ---')
    importances = feature_permutation_importance(model, val_data, baseline)
    
    print('\n  Feature Importance (F1 Drop):')
    print('  ' + '-' * 70)
    print(f'  {"Feature":<30} {"F1 Drop":>10} {"MSE Inc":>10} {"R2 Drop":>10}')
    print('  ' + '-' * 70)
    
    for imp in sorted(importances, key=lambda x: x['f1_drop'], reverse=True):
        print(f'  {imp["name"]:<30} {imp["f1_drop"]:>10.4f} {imp["mse_increase"]:>10.4f} {imp["r2_drop"]:>10.4f}')
    
    print('\n--- Feature-Label Correlation ---')
    correlations = compute_feature_correlation(val_data)
    
    print('\n  Feature-Label Correlation:')
    print('  ' + '-' * 50)
    print(f'  {"Feature":<30} {"Correlation":>15}')
    print('  ' + '-' * 50)
    
    for corr in sorted(correlations, key=lambda x: abs(x['correlation']), reverse=True):
        print(f'  {corr["name"]:<30} {corr["correlation"]:>15.4f}')
    
    print('\n--- New vs Old Feature Comparison ---')
    print('\n  New Features (path_length_entropy, betweenness_centrality):')
    for imp in importances:
        if imp['name'] in ['path_length_entropy', 'betweenness_centrality']:
            corr = next(c for c in correlations if c['index'] == imp['index'])
            print(f'    {imp["name"]}:')
            print(f'      - F1 Drop: {imp["f1_drop"]:.4f}')
            print(f'      - MSE Increase: {imp["mse_increase"]:.4f}')
            print(f'      - R2 Drop: {imp["r2_drop"]:.4f}')
            print(f'      - Label Correlation: {corr["correlation"]:.4f}')
    
    print('\n--- Generating Visualizations ---')
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    f1_importances = sorted(importances, key=lambda x: x['f1_drop'], reverse=True)
    names = [i['name'] for i in f1_importances]
    values = [i['f1_drop'] for i in f1_importances]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.barh(names, values, color=['#f9e2af' if n in ['path_length_entropy', 'betweenness_centrality'] else '#89b4fa' for n in names])
    ax.set_xlabel('F1 Score Drop (higher = more important)')
    ax.set_title('Feature Importance by F1 Drop')
    ax.grid(True, alpha=0.3)
    
    for bar in bars:
        width = bar.get_width()
        ax.text(width + 0.0001, bar.get_y() + bar.get_height()/2,
                f'{width:.4f}', va='center', fontsize=8)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'feature_importance_f1.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('  Saved: feature_importance_f1.png')
    
    corr_sorted = sorted(correlations, key=lambda x: abs(x['correlation']), reverse=True)
    names_corr = [c['name'] for c in corr_sorted]
    values_corr = [c['correlation'] for c in corr_sorted]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = ['#f9e2af' if n in ['path_length_entropy', 'betweenness_centrality'] else '#89b4fa' for n in names_corr]
    ax.barh(names_corr, values_corr, color=colors)
    ax.axvline(0, color='black', linewidth=0.5)
    ax.set_xlabel('Correlation with Vulnerability Label')
    ax.set_title('Feature-Label Correlation')
    ax.grid(True, alpha=0.3)
    
    for i, v in enumerate(values_corr):
        ax.text(v + (0.01 if v > 0 else -0.05), i, f'{v:.4f}', va='center', fontsize=8)
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'feature_correlation.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('  Saved: feature_correlation.png')
    
    print('\n' + '=' * 62)
    print('  Feature Importance Report Complete')
    print('=' * 62)
    print(f'  Output directory: {OUTPUT_DIR}')

if __name__ == '__main__':
    generate_report()