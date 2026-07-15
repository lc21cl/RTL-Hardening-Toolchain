import os
import sys
import torch
import numpy as np
import matplotlib.pyplot as plt
from torch_geometric.nn import SAGEConv
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data.pt')
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'data', 'figures')
os.makedirs(OUTPUT_DIR, exist_ok=True)

FEATURE_NAMES = [
    'node_type_pi', 'node_type_po', 'node_type_and', 'node_type_dff',
    'degree_in', 'degree_out', 'depth', 'is_const',
    'path_length_entropy', 'betweenness_centrality',
]

class SAGE3(torch.nn.Module):
    def __init__(self, in_channels=12, hidden_channels=128, dropout=0.3):
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
        return self.mlp(x).squeeze(-1)

def load_model_and_data():
    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    test_data = raw['test']
    
    feature_dim = test_data[0].x.shape[1]
    
    model_path = os.path.join(MODEL_DIR, 'local_seed42.pt')
    if not os.path.exists(model_path):
        model_path = os.path.join(MODEL_DIR, 'final_42.pt')
    
    model = SAGE3(in_channels=feature_dim, hidden_channels=128)
    model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
    model.eval()
    
    return model, test_data

def get_predictions(model, data_list):
    all_features = []
    all_scores = []
    all_labels = []
    all_graph_ids = []
    
    for graph_id, data in enumerate(data_list):
        with torch.no_grad():
            logits = model(data.x, data.edge_index)
            scores = torch.sigmoid(logits)
        
        all_features.append(data.x.numpy())
        all_scores.append(scores.numpy())
        all_labels.append(data.y.numpy())
        all_graph_ids.extend([graph_id] * len(data.x))
    
    return {
        'features': np.vstack(all_features),
        'scores': np.concatenate(all_scores),
        'labels': np.concatenate(all_labels),
        'graph_ids': np.array(all_graph_ids),
    }

def analyze_errors(preds, threshold=0.95):
    scores = preds['scores']
    labels = preds['labels']
    features = preds['features']
    graph_ids = preds['graph_ids']
    
    binary_labels = (labels >= 0.5).astype(int)
    binary_preds = (scores >= threshold).astype(int)
    
    tp_mask = (binary_preds == 1) & (binary_labels == 1)
    fp_mask = (binary_preds == 1) & (binary_labels == 0)
    fn_mask = (binary_preds == 0) & (binary_labels == 1)
    tn_mask = (binary_preds == 0) & (binary_labels == 0)
    
    print('=' * 70)
    print('  Error Analysis Report')
    print('=' * 70)
    
    print(f'\n  Threshold: {threshold}')
    print(f'  Total samples: {len(scores):,}')
    print(f'  Positive samples: {binary_labels.sum():,} ({binary_labels.mean()*100:.1f}%)')
    print(f'  Predicted positive: {binary_preds.sum():,} ({binary_preds.mean()*100:.1f}%)')
    
    print(f'\n--- Confusion Matrix ---')
    print(f'  {"":>20} {"Pred Negative":>15} {"Pred Positive":>15}')
    print(f'  {"Actual Negative":>20} {tn_mask.sum():>15,} {fp_mask.sum():>15,}')
    print(f'  {"Actual Positive":>20} {fn_mask.sum():>15,} {tp_mask.sum():>15,}')
    
    tp = tp_mask.sum()
    fp = fp_mask.sum()
    fn = fn_mask.sum()
    tn = tn_mask.sum()
    
    precision = tp / (tp + fp + 1e-6)
    recall = tp / (tp + fn + 1e-6)
    f1 = 2 * precision * recall / (precision + recall + 1e-6)
    
    print(f'\n--- Metrics ---')
    print(f'  Precision: {precision:.4f}')
    print(f'  Recall: {recall:.4f}')
    print(f'  F1: {f1:.4f}')
    print(f'  FPR (False Positive Rate): {fp/(fp+tn+1e-6):.4f}')
    print(f'  FNR (False Negative Rate): {fn/(fn+tp+1e-6):.4f}')
    
    print(f'\n--- False Positive Analysis (Predicted vulnerable, actually safe) ---')
    print(f'  Count: {fp.sum()}')
    if fp.sum() > 0:
        fp_features = features[fp_mask]
        tp_features = features[tp_mask]
        tn_features = features[tn_mask]
        
        print(f'\n  Feature comparison (FP vs TP vs TN):')
        print(f'  {"Feature":<30} {"FP mean":>10} {"TP mean":>10} {"TN mean":>10} {"FP std":>10}')
        print('  ' + '-' * 75)
        for i, name in enumerate(FEATURE_NAMES):
            fp_mean = fp_features[:, i].mean()
            tp_mean = tp_features[:, i].mean()
            tn_mean = tn_features[:, i].mean()
            fp_std = fp_features[:, i].std()
            print(f'  {name:<30} {fp_mean:>10.4f} {tp_mean:>10.4f} {tn_mean:>10.4f} {fp_std:>10.4f}')
    
    print(f'\n--- False Negative Analysis (Predicted safe, actually vulnerable) ---')
    print(f'  Count: {fn.sum()}')
    if fn.sum() > 0:
        fn_features = features[fn_mask]
        tp_features = features[tp_mask]
        
        print(f'\n  Feature comparison (FN vs TP):')
        print(f'  {"Feature":<30} {"FN mean":>10} {"TP mean":>10} {"Diff":>10} {"Sig":>5}')
        print('  ' + '-' * 70)
        for i, name in enumerate(FEATURE_NAMES):
            fn_mean = fn_features[:, i].mean()
            tp_mean = tp_features[:, i].mean()
            diff = fn_mean - tp_mean
            fn_std = fn_features[:, i].std() + 1e-6
            tp_std = tp_features[:, i].std() + 1e-6
            pooled_std = np.sqrt((fn_std**2 + tp_std**2) / 2)
            sig = abs(diff) / pooled_std if pooled_std > 0 else 0
            sig_mark = '***' if sig > 2 else '**' if sig > 1.5 else '*' if sig > 1 else ''
            print(f'  {name:<30} {fn_mean:>10.4f} {tp_mean:>10.4f} {diff:>+10.4f} {sig_mark:>5}')
    
    print(f'\n--- Score Distribution Analysis ---')
    print(f'  TP scores: mean={scores[tp_mask].mean():.4f}, std={scores[tp_mask].std():.4f}')
    print(f'  FP scores: mean={scores[fp_mask].mean():.4f}, std={scores[fp_mask].std():.4f}')
    print(f'  FN scores: mean={scores[fn_mask].mean():.4f}, std={scores[fn_mask].std():.4f}')
    print(f'  TN scores: mean={scores[tn_mask].mean():.4f}, std={scores[tn_mask].std():.4f}')
    
    print(f'\n--- Node Type Analysis ---')
    node_types = ['PI', 'PO', 'AND', 'DFF']
    type_indices = [0, 1, 2, 3]
    
    print(f'  {"Type":<6} {"Total":>8} {"Pos":>8} {"Pred":>8} {"TP":>6} {"FP":>6} {"FN":>6} {"TN":>6} {"Recall":>8} {"Precision":>10}')
    print('  ' + '-' * 90)
    for name, idx in zip(node_types, type_indices):
        type_mask = features[:, idx] > 0.5
        total = type_mask.sum()
        pos = (type_mask & (binary_labels == 1)).sum()
        pred = (type_mask & (binary_preds == 1)).sum()
        tp_t = (type_mask & tp_mask).sum()
        fp_t = (type_mask & fp_mask).sum()
        fn_t = (type_mask & fn_mask).sum()
        tn_t = (type_mask & tn_mask).sum()
        rec = tp_t / (tp_t + fn_t + 1e-6)
        prec = tp_t / (tp_t + fp_t + 1e-6)
        print(f'  {name:<6} {total:>8,} {pos:>8,} {pred:>8,} {tp_t:>6,} {fp_t:>6,} {fn_t:>6,} {tn_t:>6,} {rec:>8.4f} {prec:>10.4f}')
    
    print(f'\n--- Graph-level Error Distribution ---')
    unique_graphs = np.unique(graph_ids)
    graph_errors = []
    for gid in unique_graphs:
        g_mask = graph_ids == gid
        g_fp = (g_mask & fp_mask).sum()
        g_fn = (g_mask & fn_mask).sum()
        g_pos = (g_mask & (binary_labels == 1)).sum()
        graph_errors.append({
            'graph_id': gid,
            'total_nodes': g_mask.sum(),
            'positive': g_pos,
            'fp': g_fp,
            'fn': g_fn,
            'error_rate': (g_fp + g_fn) / (g_mask.sum() + 1e-6),
        })
    
    graph_errors.sort(key=lambda x: x['error_rate'], reverse=True)
    
    print(f'  Top 10 graphs with highest error rates:')
    print(f'  {"Graph":>6} {"Nodes":>8} {"Pos":>6} {"FP":>6} {"FN":>6} {"Error Rate":>12}')
    print('  ' + '-' * 50)
    for g in graph_errors[:10]:
        print(f'  {g["graph_id"]:>6} {g["total_nodes"]:>8,} {g["positive"]:>6} {g["fp"]:>6} {g["fn"]:>6} {g["error_rate"]:>12.4f}')
    
    print(f'\n--- Failure Mode Summary ---')
    
    if fp.sum() > fn.sum():
        print(f'  Dominant error type: FALSE POSITIVES ({fp.sum()} vs {fn.sum()} FN)')
        print(f'  Issue: Model over-predicts vulnerability')
        print(f'  Recommendation: Increase threshold or improve feature discrimination')
    else:
        print(f'  Dominant error type: FALSE NEGATIVES ({fn.sum()} vs {fp.sum()} FP)')
        print(f'  Issue: Model misses vulnerable nodes')
        print(f'  Recommendation: Lower threshold or add features that capture missed patterns')
    
    fn_ratio = fn.sum() / (fn.sum() + tp.sum() + 1e-6)
    fp_ratio = fp.sum() / (fp.sum() + tn.sum() + 1e-6)
    print(f'\n  False Negative Rate: {fn_ratio:.4f} ({fn_ratio*100:.1f}% of positives missed)')
    print(f'  False Positive Rate: {fp_ratio:.4f} ({fp_ratio*100:.1f}% of negatives flagged)')
    
    return {
        'tp_mask': tp_mask, 'fp_mask': fp_mask,
        'fn_mask': fn_mask, 'tn_mask': tn_mask,
        'precision': precision, 'recall': recall, 'f1': f1,
    }

def plot_error_analysis(preds, errors):
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    
    scores = preds['scores']
    labels = preds['labels']
    features = preds['features']
    
    tp_mask = errors['tp_mask']
    fp_mask = errors['fp_mask']
    fn_mask = errors['fn_mask']
    tn_mask = errors['tn_mask']
    
    ax = axes[0, 0]
    categories = ['TP', 'FP', 'FN', 'TN']
    counts = [tp_mask.sum(), fp_mask.sum(), fn_mask.sum(), tn_mask.sum()]
    colors = ['#2ecc71', '#e74c3c', '#f39c12', '#3498db']
    ax.bar(categories, counts, color=colors)
    ax.set_title('Prediction Category Counts')
    ax.set_ylabel('Count')
    for i, v in enumerate(counts):
        ax.text(i, v + max(counts)*0.01, str(v), ha='center', fontweight='bold')
    
    ax = axes[0, 1]
    ax.hist(scores[tp_mask], bins=30, alpha=0.6, label='TP', color='#2ecc71', density=True)
    ax.hist(scores[fp_mask], bins=30, alpha=0.6, label='FP', color='#e74c3c', density=True)
    ax.hist(scores[fn_mask], bins=30, alpha=0.6, label='FN', color='#f39c12', density=True)
    ax.axvline(0.95, color='black', linestyle='--', label='Threshold')
    ax.set_title('Score Distribution by Category')
    ax.set_xlabel('Prediction Score')
    ax.set_ylabel('Density')
    ax.legend()
    
    ax = axes[0, 2]
    bc_idx = FEATURE_NAMES.index('betweenness_centrality')
    ple_idx = FEATURE_NAMES.index('path_length_entropy')
    
    ax.scatter(features[tn_mask, bc_idx], features[tn_mask, ple_idx], 
               alpha=0.1, s=5, c='#3498db', label='TN')
    ax.scatter(features[tp_mask, bc_idx], features[tp_mask, ple_idx], 
               alpha=0.5, s=10, c='#2ecc71', label='TP')
    ax.scatter(features[fp_mask, bc_idx], features[fp_mask, ple_idx], 
               alpha=0.5, s=10, c='#e74c3c', label='FP')
    ax.scatter(features[fn_mask, bc_idx], features[fn_mask, ple_idx], 
               alpha=0.8, s=20, c='#f39c12', label='FN', marker='X')
    ax.set_xlabel('betweenness_centrality')
    ax.set_ylabel('path_length_entropy')
    ax.set_title('Feature Space: BC vs PLE')
    ax.legend()
    
    ax = axes[1, 0]
    node_types = ['PI', 'PO', 'AND', 'DFF']
    type_idx = [0, 1, 2, 3]
    error_rates = []
    for idx in type_idx:
        type_mask = features[:, idx] > 0.5
        type_fn = (type_mask & fn_mask).sum()
        type_pos = (type_mask & (labels >= 0.5)).sum()
        error_rates.append(type_fn / (type_pos + 1e-6) if type_pos > 0 else 0)
    
    ax.bar(node_types, error_rates, color='#e74c3c')
    ax.set_title('False Negative Rate by Node Type')
    ax.set_ylabel('FN Rate')
    for i, v in enumerate(error_rates):
        ax.text(i, v + 0.01, f'{v:.3f}', ha='center')
    
    ax = axes[1, 1]
    deg_out_idx = FEATURE_NAMES.index('degree_out')
    deg_in_idx = FEATURE_NAMES.index('degree_in')
    
    max_deg = int(max(features[:, deg_out_idx].max(), features[:, deg_in_idx].max())) + 1
    deg_fn_rates = []
    deg_ranges = []
    for d in range(0, min(max_deg, 20)):
        deg_mask = (features[:, deg_out_idx] >= d) & (features[:, deg_out_idx] < d+1)
        deg_fn = (deg_mask & fn_mask).sum()
        deg_pos = (deg_mask & (labels >= 0.5)).sum()
        if deg_pos > 0:
            deg_fn_rates.append(deg_fn / (deg_pos + 1e-6))
            deg_ranges.append(f'{d}')
    
    if deg_ranges:
        ax.bar(deg_ranges, deg_fn_rates, color='#f39c12')
        ax.set_title('False Negative Rate by Out-Degree')
        ax.set_xlabel('Out-Degree')
        ax.set_ylabel('FN Rate')
        plt.setp(ax.get_xticklabels(), rotation=45)
    
    ax = axes[1, 2]
    bc_values = features[:, bc_idx]
    bc_bins = np.linspace(bc_values.min(), bc_values.max(), 10)
    bc_centers = (bc_bins[:-1] + bc_bins[1:]) / 2
    bc_fn_rates = []
    
    for i in range(len(bc_bins) - 1):
        bc_mask = (bc_values >= bc_bins[i]) & (bc_values < bc_bins[i+1])
        bc_fn = (bc_mask & fn_mask).sum()
        bc_pos = (bc_mask & (labels >= 0.5)).sum()
        bc_fn_rates.append(bc_fn / (bc_pos + 1e-6) if bc_pos > 0 else 0)
    
    ax.bar(range(len(bc_centers)), bc_fn_rates, color='#9b59b6')
    ax.set_title('False Negative Rate by Betweenness Centrality')
    ax.set_xlabel('BC Bin (low to high)')
    ax.set_ylabel('FN Rate')
    
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'error_analysis.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print(f'\n  Saved: error_analysis.png')

def main():
    print('Loading model and data...')
    model, test_data = load_model_and_data()
    
    print('Running predictions...')
    preds = get_predictions(model, test_data)
    
    errors = analyze_errors(preds, threshold=0.95)
    
    plot_error_analysis(preds, errors)
    
    print('\n' + '=' * 70)
    print('  Error Analysis Complete')
    print('=' * 70)

if __name__ == '__main__':
    main()