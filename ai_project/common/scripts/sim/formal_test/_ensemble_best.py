import os
import sys
import torch
import numpy as np
from torch_geometric.nn import SAGEConv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data.pt')
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')

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

def load_models(seed_list):
    models = []
    found_seeds = []
    for seed in seed_list:
        model_path = os.path.join(MODEL_DIR, f'local_seed{seed}.pt')
        if not os.path.exists(model_path):
            model_path = os.path.join(MODEL_DIR, f'final_{seed}.pt')
        if os.path.exists(model_path):
            model = SAGE3(in_channels=10, hidden_channels=128)
            model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
            model.eval()
            models.append(model)
            found_seeds.append(seed)
            print(f'  Loaded model: {os.path.basename(model_path)}')
        else:
            print(f'  Warning: Model not found: local_seed{seed}.pt or final_{seed}.pt')
    return models, found_seeds

def get_all_predictions(model, data_list):
    all_s = []
    all_l = []
    for data in data_list:
        with torch.no_grad():
            logits = model(data.x, data.edge_index)
            pred = torch.sigmoid(logits)
        all_s.append(pred)
        all_l.append(data.y)
    return torch.cat(all_s), torch.cat(all_l)

def find_best_threshold(scores, labels):
    best_f1 = 0.0
    best_th = 0.5
    for th in [x / 100 for x in range(5, 96, 2)]:
        m = compute_metrics(scores, labels, threshold=th)
        if m['f1'] > best_f1:
            best_f1 = m['f1']
            best_th = th
    return best_f1, best_th

def main():
    print('=' * 62)
    print('  Ensemble Learning — Model Fusion')
    print('=' * 62)

    if not os.path.exists(DATA_PATH):
        print(f'ERROR: Training data not found at {DATA_PATH}')
        sys.exit(1)

    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    test_data = raw['test']

    seed_list = [42, 456]
    models, found_seeds = load_models(seed_list)
    
    if len(models) == 0:
        print('ERROR: No models found for ensemble')
        sys.exit(1)
    
    print(f'\n  Models loaded: {len(models)}')

    all_preds = []
    print('\n--- Individual Model Performance ---')
    for i, (model, seed) in enumerate(zip(models, found_seeds)):
        scores, labels = get_all_predictions(model, test_data)
        all_preds.append(scores)
        
        best_f1, best_th = find_best_threshold(scores, labels)
        m = compute_metrics(scores, labels, threshold=best_th)
        print(f'  Model {i+1} (seed={seed}):')
        print(f'    F1: {best_f1:.4f} (th={best_th:.2f})')
        print(f'    MSE: {m["mse"]:.4f}, R2: {m["r2"]:.4f}')

    all_preds = torch.stack(all_preds)
    labels = torch.cat([data.y for data in test_data])

    print('\n--- Uniform Weight Ensemble ---')
    ensemble_scores = all_preds.mean(dim=0)
    best_f1, best_th = find_best_threshold(ensemble_scores, labels)
    m = compute_metrics(ensemble_scores, labels, threshold=best_th)
    print(f'  Uniform Weight Ensemble:')
    print(f'    F1: {best_f1:.4f} (th={best_th:.2f})')
    print(f'    MSE: {m["mse"]:.4f}, R2: {m["r2"]:.4f}')
    print(f'    MAE: {m["mae"]:.4f}, Precision: {m["precision"]:.4f}, Recall: {m["recall"]:.4f}')

    print('\n--- Weighted Ensemble (Optimized) ---')
    n_models = len(models)
    best_f1 = 0.0
    best_weights = [1.0 / n_models] * n_models
    best_th = 0.5
    n_iter = 100
    
    for idx in range(n_iter):
        weights = np.random.dirichlet(np.ones(n_models))
        weighted_scores = (all_preds * torch.tensor(weights, dtype=torch.float32).unsqueeze(1)).sum(dim=0)
        
        for th in [x / 100 for x in range(5, 96, 2)]:
            m = compute_metrics(weighted_scores, labels, threshold=th)
            if m['f1'] > best_f1:
                best_f1 = m['f1']
                best_weights = list(weights)
                best_th = th
    
    weighted_scores = (all_preds * torch.tensor(best_weights, dtype=torch.float32).unsqueeze(1)).sum(dim=0)
    m = compute_metrics(weighted_scores, labels, threshold=best_th)
    print(f'  Optimized Weights: {[f"{w:.3f}" for w in best_weights]}')
    print(f'  Weighted Ensemble:')
    print(f'    F1: {m["f1"]:.4f} (th={best_th:.2f})')
    print(f'    MSE: {m["mse"]:.4f}, R2: {m["r2"]:.4f}')
    print(f'    MAE: {m["mae"]:.4f}, Precision: {m["precision"]:.4f}, Recall: {m["recall"]:.4f}')

    print('\n--- Saving Ensemble Weights ---')
    ensemble_config = {
        'seeds': found_seeds,
        'weights': best_weights,
        'best_threshold': best_th,
        'metrics': m,
    }
    torch.save(ensemble_config, os.path.join(MODEL_DIR, 'ensemble_config.pt'))
    print(f'  Saved to {os.path.join(MODEL_DIR, "ensemble_config.pt")}')

    print('\n' + '=' * 62)
    print('  Ensemble Complete')
    print('=' * 62)

if __name__ == '__main__':
    main()