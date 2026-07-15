"""Verify new prob_decay labels and clustering/diversity features."""
import sys
sys.path.insert(0, '.')
from blif_to_pyg import BlifToAIG
import torch

c = BlifToAIG(r'd:\learning\AI_RESEARCH\ai_project\common\scripts\test_mock_data\output_counter.blif')
d = c.build_pyg_data()
print(f'Nodes: {c.num_nodes}, Features: {d.x.shape[1]}')
print(f'Feature dim: {d.x.shape}')

label_bin = c.generate_fault_labels(deterministic=True, label_mode='binary')
label_decay = c.generate_fault_labels(deterministic=True, label_mode='prob_decay')

print(f'\nBinary labels: {label_bin.sum().item():.0f} ones ({label_bin.sum().item()/c.num_nodes*100:.1f}%)')
print(f'Prob_decay labels: mean={label_decay.mean().item():.4f}, '
      f'max={label_decay.max().item():.4f}, min={label_decay.min().item():.4f}')
print(f'Unique values: {len(torch.unique(label_decay))}')

print(f'\nFeature[8] (clustering): min={d.x[:,8].min().item():.4f}, '
      f'max={d.x[:,8].max().item():.4f}, mean={d.x[:,8].mean().item():.4f}')
print(f'Feature[9] (diversity): min={d.x[:,9].min().item():.4f}, '
      f'max={d.x[:,9].max().item():.4f}, mean={d.x[:,9].mean().item():.4f}')

corr = torch.corrcoef(torch.stack([d.x[:,8], label_decay]))[0,1].item()
print(f'\nCorrelation between feature[8] and prob_decay label: {corr:.4f}')
print('(Should be low, unlike previous rev_depth which was ~1.0)')

# Test on larger BLIF
print('\n' + '='*50)
print('Testing on rv32i_cpu_core.blif')
c2 = BlifToAIG(r'd:\learning\AI_RESEARCH\ai_project\common\scripts\test_mock_data\output_rv32i_cpu_core.blif')
d2 = c2.build_pyg_data()
label2 = c2.generate_fault_labels(deterministic=True, label_mode='prob_decay')
print(f'Nodes: {c2.num_nodes}, Features: {d2.x.shape[1]}')
print(f'Prob_decay labels: mean={label2.mean().item():.4f}, '
      f'max={label2.max().item():.4f}, min={label2.min().item():.4f}')
corr2 = torch.corrcoef(torch.stack([d2.x[:,8], label2]))[0,1].item()
print(f'Correlation feature[8] vs label: {corr2:.4f}')
print('\nVerification complete!')
