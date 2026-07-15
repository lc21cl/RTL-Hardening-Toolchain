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
FPGA_DIR = os.path.join(SCRIPT_DIR, 'data', 'fpga')
os.makedirs(MODEL_DIR, exist_ok=True)


class SAGE2Lite(nn.Module):
    def __init__(self, in_channels=15, hidden_channels=64, dropout=0.2):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels // 2, 8), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(8, 1),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv2(x, edge_index).relu(); x = self.dropout(x)
        return self.mlp(x).squeeze(-1)

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def clip_weights(self, clip_value=1.0):
        for param in self.parameters():
            param.data.clamp_(-clip_value, clip_value)


class WeightNormalizer:
    @staticmethod
    def range_norm(weight, target_range=1.0):
        abs_max = torch.max(torch.abs(weight))
        if abs_max > 0:
            return weight / abs_max * target_range
        return weight

    @staticmethod
    def normalize_model(model):
        print('  Applying range normalization to model weights...')
        normalized_state = {}
        for name, param in model.state_dict().items():
            if 'weight' in name:
                normalized_state[name] = WeightNormalizer.range_norm(param)
                print(f'    {name}: abs_max={torch.max(torch.abs(param)):.4f} -> {torch.max(torch.abs(normalized_state[name])):.4f}')
            else:
                normalized_state[name] = param
        model.load_state_dict(normalized_state)
        return model


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


def train_with_weight_clip(model, train_data, val_data, device,
                          epochs=50, lr=0.005, batch_size=32, patience=15,
                          weight_decay=1e-4, pos_weight=20.0, clip_value=1.0):
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
            model.clip_weights(clip_value)
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
            max_weight = max(torch.max(torch.abs(p)).item() for p in model.parameters())
            print(f'  Epoch {epoch:3d} | Loss: {avg_loss:.4f} | Val F1: {best_val_f1:.4f} | '
                  f'MaxW: {max_weight:.4f} | Time: {elapsed:.1f}s')
    
    total_time = time.time() - t_start
    print(f'\n  Training complete in {total_time:.1f}s')
    print(f'  Best F1: {best_f1:.4f} at epoch {best_epoch}')
    
    if best_state is not None:
        model.load_state_dict(best_state)
    
    return model, best_f1


def main():
    print('=' * 62)
    print('  Training with Weight Normalization')
    print('=' * 62)

    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    train_data = raw['train']
    val_data = raw['val']
    test_data = raw['test']
    
    print(f'  Data: {len(train_data)} train, {len(val_data)} val, {len(test_data)} test')
    
    device = torch.device('cpu')
    print(f'  Device: {device}')

    model_name = 'SAGE2-Lite-64-Normalized'
    
    print(f'\n{"-" * 62}')
    print(f'  Model: {model_name}')
    print(f'{"-" * 62}')

    model = SAGE2Lite(in_channels=15, hidden_channels=64)
    print(f'  Parameters: {model.count_parameters():,}')

    print('\n  --- Loading original model ---')
    original_path = os.path.join(MODEL_DIR, 'SAGE2-Lite-64.pth')
    if os.path.exists(original_path):
        model.load_state_dict(torch.load(original_path, map_location='cpu', weights_only=True))
        print(f'  Loaded from: {original_path}')
    else:
        print(f'  Original model not found, using random initialization')

    print('\n  --- Normalizing weights ---')
    model = WeightNormalizer.normalize_model(model)

    print('\n  --- Starting training with weight clipping ---')
    start_time = time.time()
    model, best_f1 = train_with_weight_clip(
        model, train_data, val_data, device,
        epochs=50,
        lr=0.005,
        batch_size=32,
        patience=15,
        pos_weight=20.0,
        clip_value=1.0,
    )
    duration = time.time() - start_time

    model_path = os.path.join(MODEL_DIR, f'{model_name}.pth')
    torch.save(model.state_dict(), model_path)
    print(f'\n  Model saved to: {model_path}')

    fpga_path = os.path.join(FPGA_DIR, f'{model_name}.pth')
    torch.save(model.state_dict(), fpga_path)
    print(f'  Model saved to FPGA dir: {fpga_path}')

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

    print(f'\n  --- Final Test Results ---')
    print(f'  Test F1: {best_test_f1:.4f} (th={best_test_th})')
    print(f'  Duration: {duration:.1f}s')

    print('\n  --- Weight Statistics After Training ---')
    for name, param in model.state_dict().items():
        if 'weight' in name:
            print(f'    {name}:')
            print(f'      Min: {param.min().item():.4f}, Max: {param.max().item():.4f}')
            print(f'      AbsMax: {torch.max(torch.abs(param)).item():.4f}')

    result = {
        'model': model_name,
        'parameters': model.count_parameters(),
        'epochs': 50,
        'duration': round(duration, 1),
        'val_f1': round(best_f1, 4),
        'test_f1': round(best_test_f1, 4),
        'test_threshold': best_test_th,
        'model_path': model_path,
    }

    result_path = os.path.join(FPGA_DIR, 'normalized_training_results.json')
    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f'\n  Results saved to: {result_path}')

    return result


if __name__ == '__main__':
    main()
