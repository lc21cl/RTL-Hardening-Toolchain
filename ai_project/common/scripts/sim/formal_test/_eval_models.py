"""Evaluate all saved models on test set."""
import torch, json
from graphsage_model import VulnerabilityPredictor, compute_metrics
from torch_geometric.data import DataLoader

# Load data
raw = torch.load('data/training_data.pt', map_location='cpu', weights_only=False)
train_data, val_data, test_data = raw['train'], raw['val'], raw['test']

loader = DataLoader(test_data, batch_size=32, shuffle=False)

models_to_eval = [
    ('data/models/hidden128_weight.pt', 'SAGE2_128_weight'),
    ('data/models/big_data_model.pt', 'SAGE2_128_bigdata'),
    ('data/models/sage3_64.pt', 'SAGE3_64'),
    ('data/models/sage3_128.pt', 'SAGE3_128'),
    ('data/models/gat_64.pt', 'GAT_64'),
]

results = {}
for path, name in models_to_eval:
    try:
        # Determine model class from name
        if name.startswith('GAT'):
            from _train_advanced import GATPredictor
            model = GATPredictor(in_channels=8, hidden_channels=64, dropout=0.3)
        elif name.startswith('SAGE3'):
            from _train_advanced import SAGE3Layer
            hidden = 128 if '128' in name else 64
            model = SAGE3Layer(in_channels=8, hidden_channels=hidden, dropout=0.3)
        else:
            model = VulnerabilityPredictor(in_channels=8, hidden_channels=128, dropout=0.3)
        
        state = torch.load(path, map_location='cpu', weights_only=False)
        model.load_state_dict(state)
        model.eval()
        
        # Test
        all_s, all_l = [], []
        with torch.no_grad():
            for batch in loader:
                logits = model(batch.x, batch.edge_index)
                all_s.append(torch.sigmoid(logits).cpu())
                all_l.append(batch.y.cpu())
        scores = torch.cat(all_s).float()
        labels = torch.cat(all_l).float()
        
        # Tune threshold on val
        val_loader = DataLoader(val_data, batch_size=32, shuffle=False)
        val_s, val_l = [], []
        with torch.no_grad():
            for batch in val_loader:
                logits = model(batch.x, batch.edge_index)
                val_s.append(torch.sigmoid(logits).cpu())
                val_l.append(batch.y.cpu())
        val_scores = torch.cat(val_s).float()
        val_labels = torch.cat(val_l).float()
        
        best_th = 0.5
        best_f1 = 0.0
        for th in [x/100 for x in range(5, 96, 1)]:
            m = compute_metrics(val_scores, val_labels, threshold=th)
            if m['f1'] > best_f1:
                best_f1 = m['f1']
                best_th = th
        
        m = compute_metrics(scores, labels, threshold=best_th)
        print('%s: Test F1=%.4f (th=%.2f) Prec=%.4f Rec=%.4f AUC=%.4f | Params=%s' % (
            name, m['f1'], best_th, m['precision'], m['recall'], m['auc_roc'],
            sum(p.numel() for p in model.parameters() if p.requires_grad)))
        
        results[name] = {k: float(v) for k, v in m.items()}
        results[name]['best_threshold'] = float(best_th)
        
    except Exception as e:
        print('%s: ERROR - %s' % (name, e))

print('\nSummary (sorted by F1):')
for name, r in sorted(results.items(), key=lambda x: -x[1]['f1']):
    print('  %-25s  F1=%.4f  AUC=%.4f' % (name, r['f1'], r['auc_roc']))

with open('data/model_comparison.json', 'w') as f:
    json.dump(results, f, indent=2)
print('\nSaved to data/model_comparison.json')
