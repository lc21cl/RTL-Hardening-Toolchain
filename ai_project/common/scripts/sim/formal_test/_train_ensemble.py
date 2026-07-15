"""Train ensemble of 5 models with different seeds to boost F1."""
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
pos_weight_val = neg / max(pos, 1e-6)
print('Positive ratio: %.4f (pos_weight=%.4f)' % (pos, pos_weight_val))

# Train 3 models with different seeds (ensemble)
NUM_MODELS = 3
seeds = [42, 456, 1111]
models = []

for i, seed in enumerate(seeds):
    print('\n' + '='*60)
    print('Training model %d/%d (seed=%d)' % (i+1, NUM_MODELS, seed))
    print('='*60)
    
    torch.manual_seed(seed)
    np.random.seed(seed)
    
    model = VulnerabilityPredictor(in_channels=8, hidden_channels=128, dropout=0.3)
    trainer = VulnerabilityTrainer(model, device='cpu', lr=1e-3, weight_decay=5e-4)
    trainer.criterion = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight_val]))
    
    t0 = time.time()
    history = trainer.train(data=train_data + val_data, epochs=300, patience=30,
                             verbose=True, save_path='data/models/ensemble_%d.pt' % seed)
    t1 = time.time()
    print('  Model %d done in %.1fs (%d epochs)' % (i+1, t1-t0, len(history['train_loss'])))
    
    model.eval()
    models.append(model)

# Evaluate ensemble on test set
print('\n' + '='*60)
print('ENSEMBLE EVALUATION')
print('='*60)

# Get predictions from all models
test_loader = DataLoader(test_data, batch_size=32, shuffle=False)
val_loader = DataLoader(val_data, batch_size=32, shuffle=False)

def get_predictions(models, loader):
    all_preds = []
    all_labels = []
    with torch.no_grad():
        for batch in loader:
            batch_preds = []
            for model in models:
                logits = model(batch.x, batch.edge_index)
                scores = torch.sigmoid(logits)
                batch_preds.append(scores.cpu())
            # Average predictions
            avg_scores = torch.stack(batch_preds).mean(dim=0)
            all_preds.append(avg_scores)
            all_labels.append(batch.y.cpu())
    return torch.cat(all_preds).float(), torch.cat(all_labels).float()

# Tune threshold on val ensemble
val_preds, val_labels = get_predictions(models, val_loader)
best_thresh = 0.5
best_f1 = 0.0
for th in [x/100 for x in range(5, 96, 1)]:
    m = compute_metrics(val_preds, val_labels, threshold=th)
    if m['f1'] > best_f1:
        best_f1 = m['f1']
        best_thresh = th
print('\nValidation ensemble (tuned):')
print('  Best threshold: %.3f (F1=%.4f)' % (best_thresh, best_f1))

# Test set
test_preds, test_labels = get_predictions(models, test_loader)
test_metrics = compute_metrics(test_preds, test_labels, threshold=best_thresh)
print('\nTest set ensemble (th=%.3f):' % best_thresh)
for k, v in test_metrics.items():
    print('  %s: %.4f' % (k, v))

# Also eval individual models on test for comparison
print('\nIndividual model performance (test set, th=0.5):')
for i, model in enumerate(models):
    preds, labels = get_predictions([model], test_loader)
    m = compute_metrics(preds, labels, threshold=0.5)
    print('  Model %d (seed=%d): F1=%.4f' % (i+1, seeds[i], m['f1']))

# Save results
results = {
    'ensemble_test': {k: float(v) for k, v in test_metrics.items()},
    'ensemble_val_best_threshold': float(best_thresh),
    'ensemble_val_f1': float(best_f1),
    'num_models': NUM_MODELS,
    'seeds': seeds,
    'config': {
        'hidden_channels': 128,
        'pos_weight': float(pos_weight_val),
    },
}
with open('data/ensemble_results.json', 'w') as f:
    json.dump(results, f, indent=2)
print('\nResults saved to data/ensemble_results.json')

# Final threshold sweep on ensemble
print('\nEnsemble threshold sweep:')
for th in [x/100 for x in range(5, 96, 5)]:
    m = compute_metrics(test_preds, test_labels, threshold=th)
    print('  th=%.2f  F1=%.4f  Prec=%.4f  Rec=%.4f' % (th, m['f1'], m['precision'], m['recall']))
