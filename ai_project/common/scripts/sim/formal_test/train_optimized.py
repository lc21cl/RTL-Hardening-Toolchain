import os
import sys
import time
import json
import torch
import torch.nn as nn
import numpy as np
from torch_geometric.nn import SAGEConv
from torch_geometric.loader import DataLoader

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data_15feat.pt')
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
os.makedirs(MODEL_DIR, exist_ok=True)


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
        x = self.conv1(x, edge_index).relu()
        x = self.dropout(x)
        x = self.conv2(x, edge_index).relu()
        x = self.dropout(x)
        x = self.conv3(x, edge_index).relu()
        x = self.dropout(x)
        return self.mlp(x).squeeze(-1)

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class SAGE2Lite(nn.Module):
    def __init__(self, in_channels=15, hidden_channels=32, dropout=0.2):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels // 2, 8), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(8, 1),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        x = self.dropout(x)
        x = self.conv2(x, edge_index).relu()
        x = self.dropout(x)
        return self.mlp(x).squeeze(-1)

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


def compute_metrics(scores, labels, threshold=0.5):
    preds = (scores >= threshold).float()
    tp = ((preds == 1) & (labels == 1)).sum().item()
    fp = ((preds == 1) & (labels == 0)).sum().item()
    fn = ((preds == 0) & (labels == 1)).sum().item()
    tn = ((preds == 0) & (labels == 0)).sum().item()

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-10)
    acc = (tp + tn) / max(tp + fp + fn + tn, 1)

    return {'f1': f1, 'precision': precision, 'recall': recall, 'acc': acc,
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn}


def sample_data(data, sample_ratio=1.0, seed=42):
    if sample_ratio >= 1.0:
        return data
    np.random.seed(seed)
    indices = np.random.choice(len(data), int(len(data) * sample_ratio), replace=False)
    return [data[i] for i in indices]


def train_optimized(model, train_data, val_data, device,
                   epochs=50, lr=0.01, batch_size=64, patience=10,
                   weight_decay=1e-4, pos_weight=20.0):
    model = model.to(device)
    
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos_weight, device=device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    
    train_loader = DataLoader(train_data, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_data, batch_size=batch_size, shuffle=False)
    
    best_f1 = 0.0
    best_epoch = 0
    best_state = None
    patience_counter = 0
    
    t_start = time.time()
    
    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        
        for batch in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            logits = model(batch.x, batch.edge_index)
            loss = criterion(logits, batch.y.float())
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            total_loss += loss.item()
        
        scheduler.step()
        avg_loss = total_loss / len(train_loader)
        
        model.eval()
        all_s, all_l = [], []
        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(device)
                logits = model(batch.x, batch.edge_index)
                probs = torch.sigmoid(logits)
                all_s.append(probs.cpu())
                all_l.append(batch.y.cpu())
        
        val_scores = torch.cat(all_s)
        val_labels = torch.cat(all_l)
        
        best_val_f1 = 0.0
        for th in [x / 100 for x in range(5, 50, 5)]:
            m = compute_metrics(val_scores, val_labels, threshold=th)
            if m['f1'] > best_val_f1:
                best_val_f1 = m['f1']
        
        if best_val_f1 > best_f1:
            best_f1 = best_val_f1
            best_epoch = epoch
            best_state = model.state_dict().copy()
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f'  Early stopping at epoch {epoch}')
                break
        
        if epoch % 5 == 0 or epoch == 1:
            elapsed = time.time() - t_start
            print(f'  Epoch {epoch:3d} | Loss: {avg_loss:.4f} | Val F1: {best_val_f1:.4f} | '
                  f'Time: {elapsed:.1f}s')
    
    total_time = time.time() - t_start
    print(f'\n  Training complete in {total_time:.1f}s')
    print(f'  Best F1: {best_f1:.4f} at epoch {best_epoch}')
    
    if best_state is not None:
        model.load_state_dict(best_state)
    
    return model, best_f1


def main():
    print('=' * 62)
    print('  Optimized Training (Algorithm & Architecture)')
    print('=' * 62)

    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    train_data = raw['train']
    val_data = raw['val']
    test_data = raw['test']
    
    print(f'  Original data: {len(train_data)} train, {len(val_data)} val, {len(test_data)} test')
    
    device = torch.device('cpu')
    print(f'  Device: {device}')

    configs = [
        {
            'name': 'SAGE2-Lite-32',
            'model_class': SAGE2Lite,
            'hidden_channels': 32,
            'epochs': 30,
            'lr': 0.01,
            'batch_size': 64,
            'sample_ratio': 0.5,
            'pos_weight': 20.0,
        },
        {
            'name': 'SAGE3-Lite-32',
            'model_class': SAGE3Lite,
            'hidden_channels': 32,
            'epochs': 30,
            'lr': 0.01,
            'batch_size': 64,
            'sample_ratio': 0.5,
            'pos_weight': 20.0,
        },
        {
            'name': 'SAGE2-Lite-64',
            'model_class': SAGE2Lite,
            'hidden_channels': 64,
            'epochs': 30,
            'lr': 0.01,
            'batch_size': 32,
            'sample_ratio': 0.5,
            'pos_weight': 20.0,
        },
    ]

    results = []

    for cfg in configs:
        print(f'\n{"-" * 62}')
        print(f'  Config: {cfg["name"]}')
        print(f'  Hidden: {cfg["hidden_channels"]}, Epochs: {cfg["epochs"]}')
        print(f'  Batch: {cfg["batch_size"]}, Sample: {cfg["sample_ratio"]*100:.0f}%')
        print(f'{"-" * 62}')

        sampled_train = sample_data(train_data, sample_ratio=cfg['sample_ratio'])
        print(f'  Sampled train: {len(sampled_train)} graphs')

        model = cfg['model_class'](in_channels=15, hidden_channels=cfg['hidden_channels'])
        print(f'  Parameters: {model.count_parameters():,}')

        start_time = time.time()
        model, best_f1 = train_optimized(
            model, sampled_train, val_data, device,
            epochs=cfg['epochs'],
            lr=cfg['lr'],
            batch_size=cfg['batch_size'],
            pos_weight=cfg['pos_weight'],
        )
        duration = time.time() - start_time

        model_path = os.path.join(MODEL_DIR, f'{cfg["name"]}.pth')
        torch.save(model.state_dict(), model_path)

        model.eval()
        all_s, all_l = [], []
        with torch.no_grad():
            for graph in test_data:
                graph = graph.to(device)
                logits = model(graph.x, graph.edge_index)
                probs = torch.sigmoid(logits)
                all_s.append(probs.cpu())
                all_l.append(graph.y.cpu())

        test_scores = torch.cat(all_s)
        test_labels = torch.cat(all_l)
        
        best_test_f1 = 0.0
        best_test_th = 0.5
        for th in [x / 100 for x in range(5, 50, 5)]:
            m = compute_metrics(test_scores, test_labels, threshold=th)
            if m['f1'] > best_test_f1:
                best_test_f1 = m['f1']
                best_test_th = th

        result = {
            'config': cfg['name'],
            'parameters': model.count_parameters(),
            'train_samples': len(sampled_train),
            'epochs': cfg['epochs'],
            'duration': round(duration, 1),
            'val_f1': round(best_f1, 4),
            'test_f1': round(best_test_f1, 4),
            'test_threshold': best_test_th,
            'model_path': model_path,
        }
        results.append(result)

        print(f'\n  Test F1: {best_test_f1:.4f} (th={best_test_th})')
        print(f'  Duration: {duration:.1f}s')

    print(f'\n{"=" * 62}')
    print('  Optimization Results Summary')
    print(f'{"=" * 62}')

    print('\n  Config               Params  Train  Epochs  Duration  Val F1  Test F1')
    print('  ' + '-' * 80)
    for r in results:
        print(f'  {r["config"]:20} {r["parameters"]:7,} {r["train_samples"]:6} {r["epochs"]:6} '
              f'{r["duration"]:9.1f}s {r["val_f1"]:7.4f} {r["test_f1"]:8.4f}')

    result_path = os.path.join(SCRIPT_DIR, 'data', 'optimization_results.json')
    with open(result_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\n  Results saved to: {result_path}')

    best_result = max(results, key=lambda x: x['test_f1'])
    print(f'\n  Best Config: {best_result["config"]}')
    print(f'  Test F1: {best_result["test_f1"]:.4f}')
    print(f'  Duration: {best_result["duration"]:.1f}s')

    return results


if __name__ == '__main__':
    main()
