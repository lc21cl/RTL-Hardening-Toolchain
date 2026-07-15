"""Train with full 3040-sample dataset using best config (hidden128 + class weight)."""
import torch, sys, time, json, os
import numpy as np
from graphsage_model import VulnerabilityPredictor, VulnerabilityTrainer, compute_metrics
from torch_geometric.data import DataLoader

os.makedirs('data/models', exist_ok=True)

# Load data
raw = torch.load('data/training_data.pt', map_location='cpu', weights_only=False)
train_data = raw['train']
val_data = raw['val']
test_data = raw['test']
print('Data: %d train, %d val, %d test' % (len(train_data), len(val_data), len(test_data)))

# Compute class weights
all_y = torch.cat([d.y for d in train_data])
pos = all_y.float().mean().item()
neg = 1 - pos
print('Positive ratio: %.4f (neg/pos=%.4f)' % (pos, neg/pos))

# Best config: hidden=128, class weights
model = VulnerabilityPredictor(in_channels=8, hidden_channels=128, dropout=0.3)
trainer = VulnerabilityTrainer(model, device='cpu', lr=1e-3, weight_decay=5e-4)
pos_weight_val = neg / max(pos, 1e-6)
trainer.criterion = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight_val]))
print('Using pos_weight=%.4f' % pos_weight_val)
print('Model params: %d' % model.count_parameters())

# Train
t0 = time.time()
history = trainer.train(data=train_data + val_data, epochs=500, patience=50,
                         verbose=True, save_path='data/models/big_data_model.pt')
t1 = time.time()
print('\nTraining took %.1fs (%d epochs)' % (t1 - t0, len(history['train_loss'])))

# Evaluate
model.eval()

def evaluate(data_list, name):
    loader = DataLoader(data_list, batch_size=32, shuffle=False)
    all_scores, all_labels = [], []
    with torch.no_grad():
        for batch in loader:
            logits = model(batch.x, batch.edge_index)
            scores = torch.sigmoid(logits)
            all_scores.append(scores.cpu())
            all_labels.append(batch.y.cpu())
    scores = torch.cat(all_scores).float()
    labels = torch.cat(all_labels).float()
    
    # Tune threshold on val set
    if 'val' in name.lower():
        best_thresh = 0.5
        best_f1 = 0.0
        for th in [x/100 for x in range(5, 96, 1)]:
            m = compute_metrics(scores, labels, threshold=th)
            if m['f1'] > best_f1:
                best_f1 = m['f1']
                best_thresh = th
        return scores, labels, best_thresh
    
    return scores, labels, 0.5

val_scores, val_labels, best_thresh = evaluate(val_data, 'val')
print('\nBest val threshold: %.3f (val F1=%.4f)' % (best_thresh, 
    compute_metrics(val_scores, val_labels, threshold=best_thresh)['f1']))

test_scores, test_labels, _ = evaluate(test_data, 'test')
test_metrics = compute_metrics(test_scores, test_labels, threshold=best_thresh)

print('\n===== TEST SET RESULTS =====')
for k, v in test_metrics.items():
    print('  %s: %.4f' % (k, v))

# Train set metrics for comparison
train_loader = DataLoader(train_data, batch_size=32, shuffle=False)
all_s, all_l = [], []
model.eval()
with torch.no_grad():
    for batch in train_loader:
        logits = model(batch.x, batch.edge_index)
        all_s.append(torch.sigmoid(logits).cpu())
        all_l.append(batch.y.cpu())
train_s = torch.cat(all_s).float()
train_l = torch.cat(all_l).float()
train_metrics = compute_metrics(train_s, train_l, threshold=best_thresh)
print('\nTrain set metrics (th=%.3f):' % best_thresh)
for k, v in train_metrics.items():
    print('  %s: %.4f' % (k, v))

# Save results
results = {
    'test': {k: float(v) for k, v in test_metrics.items()},
    'train': {k: float(v) for k, v in train_metrics.items()},
    'config': {
        'hidden_channels': 128,
        'pos_weight': float(pos_weight_val),
        'best_threshold': float(best_thresh),
        'epochs': len(history['train_loss']),
        'params': model.count_parameters(),
    },
    'val_f1_best': float(max(history['val_f1'])),
}
with open('data/big_data_results.json', 'w') as f:
    json.dump(results, f, indent=2)
print('\nResults saved to data/big_data_results.json')

# Threshold sweep
print('\nThreshold sweep on test set:')
for th in [x/100 for x in range(5, 96, 5)]:
    m = compute_metrics(test_scores, test_labels, threshold=th)
    print('  th=%.2f  F1=%.4f  Prec=%.4f  Rec=%.4f' % (th, m['f1'], m['precision'], m['recall']))
