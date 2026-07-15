"""Full training with hidden=64 for speed."""
import torch, sys, time, json, os
from graphsage_model import VulnerabilityPredictor, VulnerabilityTrainer
from torch_geometric.data import DataLoader

raw = torch.load('data/training_data.pt', map_location='cpu', weights_only=False)
data = raw['train'] + raw['val']
test_data = raw['test']
print('Loaded %d train+val, %d test' % (len(data), len(test_data)))

model = VulnerabilityPredictor(in_channels=8, hidden_channels=64, dropout=0.3)
print('Model params: %d' % model.count_parameters())

trainer = VulnerabilityTrainer(model, device='cpu', lr=1e-3, weight_decay=5e-4)
os.makedirs('data/models', exist_ok=True)

print('Starting training (300 epochs, patience=30)...')
sys.stdout.flush()
t0 = time.time()
history = trainer.train(data=data, epochs=300, patience=30, verbose=True,
                         save_path='data/models/best_model.pt')
t1 = time.time()
print('Training took %.1fs (%d epochs)' % (t1 - t0, len(history['train_loss'])))
print('Best val loss: %.4f' % trainer.best_val_loss)
sys.stdout.flush()

# Evaluate on test set
model.eval()
all_scores = []
all_labels = []
loader = DataLoader(test_data, batch_size=32, shuffle=False)
with torch.no_grad():
    for batch in loader:
        logits = model(batch.x, batch.edge_index)
        scores = torch.sigmoid(logits)
        all_scores.append(scores.cpu())
        all_labels.append(batch.y.cpu())
scores = torch.cat(all_scores).float()
labels = torch.cat(all_labels).float()

from graphsage_model import compute_metrics
metrics = compute_metrics(scores, labels)
print('\nTest set metrics:')
for k, v in metrics.items():
    print('  %s: %.4f' % (k, v))

# Also evaluate on train+val for comparison
train_loader = DataLoader(data, batch_size=32, shuffle=False)
all_scores, all_labels = [], []
model.eval()
with torch.no_grad():
    for batch in train_loader:
        logits = model(batch.x, batch.edge_index)
        scores = torch.sigmoid(logits)
        all_scores.append(scores.cpu())
        all_labels.append(batch.y.cpu())
train_scores = torch.cat(all_scores).float()
train_labels = torch.cat(all_labels).float()
train_metrics = compute_metrics(train_scores, train_labels)
print('\nTrain+Val set metrics:')
for k, v in train_metrics.items():
    print('  %s: %.4f' % (k, v))

results = {
    'test_metrics': {k: float(v) for k, v in metrics.items()},
    'train_metrics': {k: float(v) for k, v in train_metrics.items()},
    'epochs_trained': len(history['train_loss']),
    'best_val_loss': float(trainer.best_val_loss),
    'val_f1_best': float(max(history['val_f1'])),
    'model_params': model.count_parameters(),
}
with open('data/training_results.json', 'w') as f:
    json.dump(results, f, indent=2)
print('\nResults saved to data/training_results.json')
print(json.dumps(results, indent=2))
