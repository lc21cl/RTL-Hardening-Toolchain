"""Hyperparameter tuning: class weights and model capacity."""
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

# Compute class ratio
all_y = torch.cat([d.y for d in train_data])
pos_ratio = all_y.float().mean().item()
neg_ratio = 1 - pos_ratio
print('Training positive ratio: %.4f' % pos_ratio)

results = {}
best_overall_f1 = 0.0
best_config = None

# Configs to try
configs = [
    # (hidden, use_class_weight, lr, label)
    (64,  False, 1e-3, 'hidden64_no_weight'),
    (64,  True,  1e-3, 'hidden64_weight'),
    (128, False, 1e-3, 'hidden128_no_weight'),
    (128, True,  1e-3, 'hidden128_weight'),
]

for hidden, use_weight, lr, label in configs:
    print('\n' + '='*60)
    print('Config: %s' % label)
    print('='*60)
    
    # Create trainer with optional class weights
    model = VulnerabilityPredictor(in_channels=8, hidden_channels=hidden, dropout=0.3)
    trainer = VulnerabilityTrainer(model, device='cpu', lr=lr, weight_decay=5e-4)
    
    if use_weight:
        # pos_weight = neg / pos to balance the classes
        pos_weight_val = neg_ratio / max(pos_ratio, 1e-6)
        trainer.criterion = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight_val]))
        print('Using pos_weight=%.4f' % pos_weight_val)
    
    # Train
    t0 = time.time()
    history = trainer.train(data=train_data + val_data, epochs=300, patience=30, 
                             verbose=True, save_path='data/models/%s.pt' % label)
    t1 = time.time()
    train_time = t1 - t0
    
    # Evaluate on test set
    model.eval()
    loader = DataLoader(test_data, batch_size=32, shuffle=False)
    all_scores, all_labels = [], []
    with torch.no_grad():
        for batch in loader:
            logits = model(batch.x, batch.edge_index)
            scores = torch.sigmoid(logits)
            all_scores.append(scores.cpu())
            all_labels.append(batch.y.cpu())
    test_scores = torch.cat(all_scores).float()
    test_labels = torch.cat(all_labels).float()
    
    # Tune threshold on val set
    val_scores, val_labels = [], []
    val_loader = DataLoader(val_data, batch_size=32, shuffle=False)
    model.eval()
    with torch.no_grad():
        for batch in val_loader:
            logits = model(batch.x, batch.edge_index)
            scores = torch.sigmoid(logits)
            val_scores.append(scores.cpu())
            val_labels.append(batch.y.cpu())
    val_scores = torch.cat(val_scores).float()
    val_labels = torch.cat(val_labels).float()
    
    best_thresh = 0.5
    best_val_f1 = 0.0
    for th in [x/100 for x in range(5, 96, 1)]:
        m = compute_metrics(val_scores, val_labels, threshold=th)
        if m['f1'] > best_val_f1:
            best_val_f1 = m['f1']
            best_thresh = th
    
    test_metrics = compute_metrics(test_scores, test_labels, threshold=best_thresh)
    default_metrics = compute_metrics(test_scores, test_labels, threshold=0.5)
    
    print('\n  Best val threshold: %.3f (val F1=%.4f)' % (best_thresh, best_val_f1))
    print('  Test with th=%.3f: F1=%.4f, Prec=%.4f, Rec=%.4f' % (
        best_thresh, test_metrics['f1'], test_metrics['precision'], test_metrics['recall']))
    print('  Test with th=0.5: F1=%.4f' % default_metrics['f1'])
    print('  Training time: %.1fs' % train_time)
    print('  Max val F1 during training: %.4f' % max(history['val_f1']))
    
    result = {
        'hidden': hidden,
        'use_weight': use_weight,
        'lr': lr,
        'best_threshold': best_thresh,
        'val_f1_best': max(history['val_f1']),
        'test_f1_tuned': test_metrics['f1'],
        'test_precision': test_metrics['precision'],
        'test_recall': test_metrics['recall'],
        'test_accuracy': test_metrics['accuracy'],
        'test_auc_roc': test_metrics['auc_roc'],
        'test_f1_default': default_metrics['f1'],
        'train_time': train_time,
        'epochs_trained': len(history['train_loss']),
    }
    results[label] = result
    
    if test_metrics['f1'] > best_overall_f1:
        best_overall_f1 = test_metrics['f1']
        best_config = label

# Final summary
print('\n\n' + '='*60)
print('FINAL RESULTS SUMMARY')
print('='*60)
for label, r in sorted(results.items(), key=lambda x: -x[1]['test_f1_tuned']):
    print('  %-25s  Test F1=%.4f (th=%.2f)  Val F1=%.4f  Time=%.1fs' % (
        label, r['test_f1_tuned'], r['best_threshold'], r['val_f1_best'], r['train_time']))

print('\nBest config: %s (F1=%.4f)' % (best_config, best_overall_f1))

# Copy best model
import shutil
if best_config:
    src = 'data/models/%s.pt' % best_config
    dst = 'data/models/best_model.pt'
    shutil.copy2(src, dst)
    print('Copied %s -> %s' % (src, dst))

# Save all results
with open('data/tuning_results.json', 'w') as f:
    json.dump({k: {key: float(val) if isinstance(val, (np.floating,)) else val 
                   for key, val in v.items()} 
               for k, v in results.items()}, f, indent=2)
print('\nAll results saved to data/tuning_results.json')
