"""Fast evaluation of all saved models."""
import torch, json, sys
from graphsage_model import VulnerabilityPredictor, compute_metrics
from torch_geometric.data import DataLoader
from torch_geometric.nn import SAGEConv, GATv2Conv
import torch.nn as nn

# Define model classes locally
class SAGE3Layer(nn.Module):
    def __init__(self, in_channels=8, hidden_channels=64, dropout=0.3):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.conv3 = SAGEConv(hidden_channels, hidden_channels // 2)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels // 2, 16), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(16, 1),
        )
        self.dropout = nn.Dropout(dropout)
    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv2(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv3(x, edge_index).relu(); x = self.dropout(x)
        return self.mlp(x).squeeze(-1)
    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

class GATPredictor(nn.Module):
    def __init__(self, in_channels=8, hidden_channels=64, dropout=0.3):
        super().__init__()
        self.conv1 = GATv2Conv(in_channels, hidden_channels, heads=4, concat=True)
        self.conv2 = GATv2Conv(hidden_channels*4, hidden_channels, heads=1, concat=False)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_channels, 32), nn.ReLU(),
            nn.Dropout(dropout), nn.Linear(32, 1),
        )
        self.dropout = nn.Dropout(dropout)
    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu(); x = self.dropout(x)
        x = self.conv2(x, edge_index).relu(); x = self.dropout(x)
        return self.mlp(x).squeeze(-1)
    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

# Load data
raw = torch.load('data/training_data.pt', map_location='cpu', weights_only=False)
train_data, val_data, test_data = raw['train'], raw['val'], raw['test']
val_loader = DataLoader(val_data, batch_size=32, shuffle=False)
test_loader = DataLoader(test_data, batch_size=32, shuffle=False)

configs = [
    ('data/models/hidden128_weight.pt', VulnerabilityPredictor, {'in_channels':8,'hidden_channels':128,'dropout':0.3}),
    ('data/models/big_data_model.pt', VulnerabilityPredictor, {'in_channels':8,'hidden_channels':128,'dropout':0.3}),
    ('data/models/sage3_64.pt', SAGE3Layer, {'in_channels':8,'hidden_channels':64,'dropout':0.3}),
    ('data/models/sage3_128.pt', SAGE3Layer, {'in_channels':8,'hidden_channels':128,'dropout':0.3}),
    ('data/models/gat_64.pt', GATPredictor, {'in_channels':8,'hidden_channels':64,'dropout':0.3}),
]

results = {}
for path, model_cls, kwargs in configs:
    name = path.split('/')[-1].replace('.pt','')
    try:
        model = model_cls(**kwargs)
        state = torch.load(path, map_location='cpu', weights_only=False)
        # Handle different state dict formats
        if any(k.startswith('model.') for k in state):
            state = {k.replace('model.', ''): v for k, v in state.items()}
        model.load_state_dict(state, strict=False)
        model.eval()
        
        # Eval on val (threshold tuning) and test
        with torch.no_grad():
            val_s, val_l = [], []
            for batch in val_loader:
                logits = model(batch.x, batch.edge_index)
                val_s.append(torch.sigmoid(logits).cpu()); val_l.append(batch.y.cpu())
            val_scores = torch.cat(val_s).float(); val_labels = torch.cat(val_l).float()
            
            test_s, test_l = [], []
            for batch in test_loader:
                logits = model(batch.x, batch.edge_index)
                test_s.append(torch.sigmoid(logits).cpu()); test_l.append(batch.y.cpu())
            test_scores = torch.cat(test_s).float(); test_labels = torch.cat(test_l).float()
        
        best_th = max([(th, compute_metrics(val_scores, val_labels, threshold=th)['f1']) 
                       for th in [x/100 for x in range(5, 96, 1)]], key=lambda x: x[1])[0]
        m = compute_metrics(test_scores, test_labels, threshold=best_th)
        
        print(f'{name:30s} Test F1={m["f1"]:.4f} (th={best_th:.2f}) '
              f'Prec={m["precision"]:.4f} Rec={m["recall"]:.4f} AUC={m["auc_roc"]:.4f} '
              f'Params={model.count_parameters()}')
        results[name] = {k: float(v) for k, v in m.items()}
        results[name]['best_threshold'] = float(best_th)
        results[name]['params'] = model.count_parameters()
    except Exception as e:
        print(f'{name:30s} ERROR: {e}')

print('\n=== Sorted Results ===')
for name, r in sorted(results.items(), key=lambda x: -x[1]['f1']):
    print(f'  {name:30s} F1={r["f1"]:.4f} AUC={r["auc_roc"]:.4f}')

with open('data/model_comparison.json', 'w') as f:
    json.dump(results, f, indent=2)
print('\nSaved to data/model_comparison.json')
