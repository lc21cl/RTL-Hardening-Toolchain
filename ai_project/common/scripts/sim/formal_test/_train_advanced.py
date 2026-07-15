"""Try advanced architectures: GAT and 3-layer SAGE."""
import torch, sys, time, json, os
import numpy as np
from graphsage_model import VulnerabilityPredictor, VulnerabilityTrainer, compute_metrics
from torch_geometric.data import Data, DataLoader
from torch_geometric.nn import GATv2Conv
import torch.nn as nn

os.makedirs('data/models', exist_ok=True)

# Load data
raw = torch.load('data/training_data.pt', map_location='cpu', weights_only=False)
train_data = raw['train']
val_data = raw['val']
test_data = raw['test']
print('Data: %d train, %d val, %d test' % (len(train_data), len(val_data), len(test_data)))

# Class weights
all_y = torch.cat([d.y for d in train_data])
pos = all_y.float().mean().item()
neg = 1 - pos
pos_weight_val = neg / max(pos, 1e-6)
print('Positive ratio: %.4f (pos_weight=%.4f)' % (pos, pos_weight_val))


# ── GAT Model ──
class GATPredictor(nn.Module):
    def __init__(self, in_channels=8, hidden_channels=64, dropout=0.3):
        super().__init__()
        self.conv1 = GATv2Conv(in_channels, hidden_channels, heads=4, concat=True)
        self.conv2 = GATv2Conv(hidden_channels * 4, hidden_channels, heads=1, concat=False)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )
        self.dropout = nn.Dropout(dropout)
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, (nn.Linear,)):
                nn.init.xavier_uniform_(m.weight, gain=nn.init.calculate_gain('relu'))

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        x = self.dropout(x)
        x = self.conv2(x, edge_index).relu()
        x = self.dropout(x)
        x = self.mlp(x)
        return x.squeeze(-1)  # [N,1] -> [N]

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ── 3-layer SAGE Model ──
class SAGE3Layer(nn.Module):
    def __init__(self, in_channels=8, hidden_channels=64, dropout=0.3):
        super().__init__()
        from torch_geometric.nn import SAGEConv
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.conv3 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels // 2, 16),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(16, 1),
        )
        self.dropout = nn.Dropout(dropout)
        self._init_weights()

    def _init_weights(self):
        for module in self.modules():
            if isinstance(module, (nn.Linear,)):
                nn.init.xavier_uniform_(module.weight, gain=nn.init.calculate_gain('relu'))

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        x = self.dropout(x)
        x = self.conv2(x, edge_index).relu()
        x = self.dropout(x)
        x = self.conv3(x, edge_index).relu()
        x = self.dropout(x)
        x = self.mlp(x)
        return x.squeeze(-1)  # [N,1] -> [N]

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# Train function
def train_model(model_class, hidden, label, data):
    model = model_class(in_channels=8, hidden_channels=hidden, dropout=0.3)
    trainer = VulnerabilityTrainer(model, device='cpu', lr=1e-3, weight_decay=5e-4)
    trainer.criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight_val]))
    
    print('\n' + '='*60)
    print('Model: %s (hidden=%d, params=%d)' % (label, hidden, model.count_parameters()))
    print('='*60)
    
    t0 = time.time()
    history = trainer.train(data=data, epochs=300, patience=30,
                             verbose=True, save_path='data/models/%s.pt' % label)
    t1 = time.time()
    print('  Training: %.1fs (%d epochs)' % (t1-t0, len(history['train_loss'])))
    
    # Evaluate
    model.eval()
    
    def eval_set(data_list):
        loader = DataLoader(data_list, batch_size=32, shuffle=False)
        all_s, all_l = [], []
        with torch.no_grad():
            for batch in loader:
                logits = model(batch.x, batch.edge_index)
                all_s.append(torch.sigmoid(logits).cpu())
                all_l.append(batch.y.cpu())
        return torch.cat(all_s).float(), torch.cat(all_l).float()
    
    val_s, val_l = eval_set(val_data)
    test_s, test_l = eval_set(test_data)
    
    # Tune threshold
    best_th = 0.5
    best_f1 = 0.0
    for th in [x/100 for x in range(5, 96, 1)]:
        m = compute_metrics(val_s, val_l, threshold=th)
        if m['f1'] > best_f1:
            best_f1 = m['f1']
            best_th = th
    
    test_m = compute_metrics(test_s, test_l, threshold=best_th)
    val_m = compute_metrics(val_s, val_l, threshold=best_th)
    
    print('  Best val th=%.3f (val F1=%.4f)' % (best_th, best_f1))
    print('  TEST: F1=%.4f, Prec=%.4f, Rec=%.4f, Acc=%.4f, AUC=%.4f' % (
        test_m['f1'], test_m['precision'], test_m['recall'], 
        test_m['accuracy'], test_m['auc_roc']))
    
    return {
        'model': label,
        'hidden': hidden,
        'params': model.count_parameters(),
        'best_threshold': best_th,
        'val_f1_best': max(history['val_f1']),
        'test_f1': test_m['f1'],
        'test_precision': test_m['precision'],
        'test_recall': test_m['recall'],
        'test_accuracy': test_m['accuracy'],
        'test_auc_roc': test_m['auc_roc'],
        'epochs': len(history['train_loss']),
        'train_time': t1-t0,
    }

# Run all configs
data = train_data + val_data
configs = [
    (SAGE3Layer, 64, 'sage3_64'),
    (SAGE3Layer, 128, 'sage3_128'),
    (GATPredictor, 64, 'gat_64'),
    (GATPredictor, 128, 'gat_128'),
]

all_results = []
for model_cls, hidden, label in configs:
    r = train_model(model_cls, hidden, label, data)
    all_results.append(r)

# Summary
print('\n\n' + '='*60)
print('FINAL RESULTS')
print('='*60)
for r in sorted(all_results, key=lambda x: -x['test_f1']):
    print('  %-15s  Test F1=%.4f  AUC=%.4f  Params=%d  Time=%.1fs' % (
        r['model'], r['test_f1'], r['test_auc_roc'], r['params'], r['train_time']))

# Save
with open('data/advanced_results.json', 'w') as f:
    json.dump({r['model']: r for r in all_results}, f, indent=2)
print('\nSaved to data/advanced_results.json')
