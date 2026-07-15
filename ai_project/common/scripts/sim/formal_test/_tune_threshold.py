"""Tune classification threshold on validation set to maximize F1."""
import torch, sys, json
from graphsage_model import VulnerabilityPredictor, compute_metrics
from torch_geometric.data import DataLoader

# Load data
raw = torch.load('data/training_data.pt', map_location='cpu', weights_only=False)
train_data = raw['train']
val_data = raw['val']
test_data = raw['test']
print('Data: %d train, %d val, %d test' % (len(train_data), len(val_data), len(test_data)))

# Load best model
model = VulnerabilityPredictor(in_channels=8, hidden_channels=64, dropout=0.3)
state = torch.load('data/models/best_model.pt', map_location='cpu', weights_only=False)
model.load_state_dict({k: v for k, v in state.items()})
model.eval()
print('Loaded model with %d params' % model.count_parameters())

# Get scores for val and test
def get_scores(model, data_list):
    loader = DataLoader(data_list, batch_size=32, shuffle=False)
    all_scores, all_labels = [], []
    with torch.no_grad():
        for batch in loader:
            logits = model(batch.x, batch.edge_index)
            scores = torch.sigmoid(logits)
            all_scores.append(scores.cpu())
            all_labels.append(batch.y.cpu())
    return torch.cat(all_scores).float(), torch.cat(all_labels).float()

val_scores, val_labels = get_scores(model, val_data)
test_scores, test_labels = get_scores(model, test_data)

# Tune threshold on val set
best_f1 = 0.0
best_threshold = 0.5
results = []
for thresh in [x / 100 for x in range(5, 96, 2)]:  # 0.05 to 0.95 step 0.02
    metrics = compute_metrics(val_scores, val_labels, threshold=thresh)
    f1 = metrics['f1']
    results.append((thresh, f1, metrics['precision'], metrics['recall']))
    if f1 > best_f1:
        best_f1 = f1
        best_threshold = thresh

print('\nThreshold tuning on validation set:')
print('  Best threshold: %.3f (F1=%.4f)' % (best_threshold, best_f1))
print('\nTop 5 thresholds:')
for th, f1, p, r in sorted(results, key=lambda x: -x[1])[:5]:
    print('  th=%.3f  F1=%.4f  Prec=%.4f  Rec=%.4f' % (th, f1, p, r))

# Evaluate test set with best threshold
test_metrics = compute_metrics(test_scores, test_labels, threshold=best_threshold)
print('\nTest set with th=%.3f:' % best_threshold)
for k, v in test_metrics.items():
    print('  %s: %.4f' % (k, v))

# Compare with default threshold
default_metrics = compute_metrics(test_scores, test_labels, threshold=0.5)
print('\nTest set with th=0.5 (default):')
for k, v in default_metrics.items():
    print('  %s: %.4f' % (k, v))
