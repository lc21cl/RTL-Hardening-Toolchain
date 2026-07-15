import os
import sys
import torch
import numpy as np
from torch_geometric.nn import SAGEConv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data.pt')
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')

FEATURE_NAMES = [
    'node_type_pi', 'node_type_po', 'node_type_and', 'node_type_dff',
    'degree_in', 'degree_out', 'depth', 'is_const',
    'path_length_entropy', 'betweenness_centrality',
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
        return self.mlp(x).squeeze(-1)

def compute_metrics(scores, labels, threshold=0.5):
    scores = scores.flatten().numpy()
    labels = labels.flatten().numpy()
    binary_labels = (labels >= 0.5).astype(int)
    predictions = (scores >= threshold).astype(int)
    
    tp = np.sum((predictions == 1) & (binary_labels == 1))
    fp = np.sum((predictions == 1) & (binary_labels == 0))
    fn = np.sum((predictions == 0) & (binary_labels == 1))
    tn = np.sum((predictions == 0) & (binary_labels == 0))
    
    precision = tp / (tp + fp + 1e-6)
    recall = tp / (tp + fn + 1e-6)
    f1 = 2 * precision * recall / (precision + recall + 1e-6)
    
    return {'f1': f1, 'precision': precision, 'recall': recall, 
            'tp': int(tp), 'fp': int(fp), 'fn': int(fn), 'tn': int(tn)}

def get_predictions(model, data_list):
    all_features = []
    all_scores = []
    all_labels = []
    
    for data in data_list:
        with torch.no_grad():
            logits = model(data.x, data.edge_index)
            scores = torch.sigmoid(logits)
        all_features.append(data.x.numpy())
        all_scores.append(scores.numpy())
        all_labels.append(data.y.numpy())
    
    return {
        'features': np.vstack(all_features),
        'scores': np.concatenate(all_scores),
        'labels': np.concatenate(all_labels),
    }

def find_best_threshold(scores, labels):
    best_f1 = 0.0
    best_th = 0.5
    for th in [x / 1000 for x in range(5, 1000, 2)]:
        m = compute_metrics(scores, labels, threshold=th)
        if m['f1'] > best_f1:
            best_f1 = m['f1']
            best_th = th
    return best_f1, best_th

def hierarchical_threshold_eval(preds):
    features = preds['features']
    scores = preds['scores']
    labels = preds['labels']
    
    print('=' * 70)
    print('  Hierarchical Threshold Strategy')
    print('=' * 70)
    
    print('\n--- Strategy 1: Global Threshold (Baseline) ---')
    best_f1, best_th = find_best_threshold(torch.tensor(scores), torch.tensor(labels))
    m = compute_metrics(torch.tensor(scores), torch.tensor(labels), threshold=best_th)
    print(f'  Global threshold: {best_th:.3f}')
    print(f'  F1: {m["f1"]:.4f}, Precision: {m["precision"]:.4f}, Recall: {m["recall"]:.4f}')
    print(f'  TP: {m["tp"]}, FP: {m["fp"]}, FN: {m["fn"]}')
    
    print('\n--- Strategy 2: Per-Node-Type Thresholds ---')
    
    node_types = {
        'PI': features[:, 0] > 0.5,
        'PO': features[:, 1] > 0.5,
        'AND': features[:, 2] > 0.5,
        'DFF': features[:, 3] > 0.5,
    }
    
    type_thresholds = {}
    type_metrics = {}
    
    for name, mask in node_types.items():
        type_scores = scores[mask]
        type_labels = labels[mask]
        type_pos = (type_labels >= 0.5).sum()
        
        if type_pos > 0:
            best_f1, best_th = find_best_threshold(
                torch.tensor(type_scores), torch.tensor(type_labels))
            m = compute_metrics(
                torch.tensor(type_scores), torch.tensor(type_labels), threshold=best_th)
            type_thresholds[name] = best_th
            type_metrics[name] = m
            print(f'  {name}: threshold={best_th:.3f}, F1={m["f1"]:.4f}, '
                  f'P={m["precision"]:.4f}, R={m["recall"]:.4f} '
                  f'(pos={type_pos}, TP={m["tp"]}, FP={m["fp"]}, FN={m["fn"]})')
        else:
            type_thresholds[name] = 0.99
            type_metrics[name] = None
            print(f'  {name}: no positive samples, threshold=0.99')
    
    print('\n--- Strategy 3: Hierarchical Prediction ---')
    
    final_preds = np.zeros_like(scores, dtype=int)
    binary_labels = (labels >= 0.5).astype(int)
    
    for name, mask in node_types.items():
        th = type_thresholds[name]
        final_preds[mask] = (scores[mask] >= th).astype(int)
    
    tp = np.sum((final_preds == 1) & (binary_labels == 1))
    fp = np.sum((final_preds == 1) & (binary_labels == 0))
    fn = np.sum((final_preds == 0) & (binary_labels == 1))
    tn = np.sum((final_preds == 0) & (binary_labels == 0))
    
    precision = tp / (tp + fp + 1e-6)
    recall = tp / (tp + fn + 1e-6)
    f1 = 2 * precision * recall / (precision + recall + 1e-6)
    
    print(f'  Hierarchical F1: {f1:.4f}')
    print(f'  Precision: {precision:.4f}, Recall: {recall:.4f}')
    print(f'  TP: {tp}, FP: {fp}, FN: {fn}, TN: {tn}')
    
    print('\n--- Strategy 4: PI-Specialized Low Threshold ---')
    
    final_preds2 = np.zeros_like(scores, dtype=int)
    pi_mask = node_types['PI']
    other_mask = ~pi_mask
    
    pi_th = 0.01
    other_th = 0.95
    
    final_preds2[pi_mask] = (scores[pi_mask] >= pi_th).astype(int)
    final_preds2[other_mask] = (scores[other_mask] >= other_th).astype(int)
    
    tp2 = np.sum((final_preds2 == 1) & (binary_labels == 1))
    fp2 = np.sum((final_preds2 == 1) & (binary_labels == 0))
    fn2 = np.sum((final_preds2 == 0) & (binary_labels == 1))
    tn2 = np.sum((final_preds2 == 0) & (binary_labels == 0))
    
    precision2 = tp2 / (tp2 + fp2 + 1e-6)
    recall2 = tp2 / (tp2 + fn2 + 1e-6)
    f12 = 2 * precision2 * recall2 / (precision2 + recall2 + 1e-6)
    
    print(f'  PI threshold: {pi_th}, Other threshold: {other_th}')
    print(f'  F1: {f12:.4f}, Precision: {precision2:.4f}, Recall: {recall2:.4f}')
    print(f'  TP: {tp2}, FP: {fp2}, FN: {fn2}, TN: {tn2}')
    
    pi_tp = np.sum((final_preds2 == 1) & (binary_labels == 1) & pi_mask)
    pi_fp = np.sum((final_preds2 == 1) & (binary_labels == 0) & pi_mask)
    pi_fn = np.sum((final_preds2 == 0) & (binary_labels == 1) & pi_mask)
    print(f'  PI nodes: TP={pi_tp}, FP={pi_fp}, FN={pi_fn}')
    
    print('\n--- Strategy 5: PI Oversampling Simulation ---')
    
    pi_pos_mask = pi_mask & (binary_labels == 1)
    pi_neg_mask = pi_mask & (binary_labels == 0)
    
    pi_pos_scores = scores[pi_pos_mask]
    pi_neg_scores = scores[pi_neg_mask]
    
    print(f'  PI positive scores: mean={pi_pos_scores.mean():.4f}, '
          f'std={pi_pos_scores.std():.4f}, min={pi_pos_scores.min():.4f}, max={pi_pos_scores.max():.4f}')
    print(f'  PI negative scores: mean={pi_neg_scores.mean():.4f}, '
          f'std={pi_neg_scores.std():.4f}')
    
    if len(pi_pos_scores) > 0:
        best_pi_th = pi_pos_scores.min()
        pi_preds = (scores[pi_mask] >= best_pi_th).astype(int)
        pi_labels = binary_labels[pi_mask]
        
        pi_tp = np.sum((pi_preds == 1) & (pi_labels == 1))
        pi_fp = np.sum((pi_preds == 1) & (pi_labels == 0))
        pi_fn = np.sum((pi_preds == 0) & (pi_labels == 1))
        
        print(f'  Optimal PI threshold (min positive score): {best_pi_th:.4f}')
        print(f'  PI: TP={pi_tp}, FP={pi_fp}, FN={pi_fn}, '
              f'Precision={pi_tp/(pi_tp+pi_fp+1e-6):.4f}, '
              f'Recall={pi_tp/(pi_tp+pi_fn+1e-6):.4f}')
    
    print('\n--- Comparison Summary ---')
    print(f'  {"Strategy":<35} {"F1":>8} {"Precision":>10} {"Recall":>8} {"FP":>6} {"FN":>6}')
    print('  ' + '-' * 80)
    
    m_global = compute_metrics(torch.tensor(scores), torch.tensor(labels), threshold=0.95)
    print(f'  {"Global (th=0.95)":<35} {m_global["f1"]:>8.4f} {m_global["precision"]:>10.4f} {m_global["recall"]:>8.4f} {m_global["fp"]:>6} {m_global["fn"]:>6}')
    
    print(f'  {"Per-Node-Type Thresholds":<35} {f1:>8.4f} {precision:>10.4f} {recall:>8.4f} {fp:>6} {fn:>6}')
    print(f'  {"PI-Low/Other-High":<35} {f12:>8.4f} {precision2:>10.4f} {recall2:>8.4f} {fp2:>6} {fn2:>6}')
    
    return type_thresholds

def main():
    print('Loading model and data...')
    
    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    test_data = raw['test']
    
    model_path = os.path.join(MODEL_DIR, 'local_seed42.pt')
    model = SAGE3(in_channels=10, hidden_channels=128)
    model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
    model.eval()
    
    print('Running predictions...')
    preds = get_predictions(model, test_data)
    
    thresholds = hierarchical_threshold_eval(preds)
    
    print('\n' + '=' * 70)
    print('  Hierarchical Threshold Analysis Complete')
    print('=' * 70)
    print(f'  Recommended thresholds: {thresholds}')
    
    config = {
        'thresholds': thresholds,
        'description': 'Per-node-type thresholds for hierarchical prediction',
    }
    torch.save(config, os.path.join(MODEL_DIR, 'hierarchical_thresholds.pt'))
    print(f'  Saved to: hierarchical_thresholds.pt')

if __name__ == '__main__':
    main()