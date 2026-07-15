import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blif_to_pyg import BlifToAIG

# Correct path: scripts/test_mock_data
script_dir = os.path.dirname(os.path.abspath(__file__))
blif_dir = os.path.abspath(os.path.join(script_dir, '..', '..', 'test_mock_data'))
print('BLIF dir:', blif_dir)
print('Exists:', os.path.exists(blif_dir))
blif_files = sorted([f for f in os.listdir(blif_dir) if f.endswith('.blif')])
print('Found BLIF files:', blif_files)

for blif_name in blif_files:
    blif_file = os.path.join(blif_dir, blif_name)
    print('\n=== Testing:', blif_name)
    converter = BlifToAIG(blif_file)
    print(converter.summary())

    for fp in [0.05, 0.1, 0.2, 0.5]:
        for seed in [0, 42, 1234]:
            labels = converter.generate_fault_labels(seed=seed, fault_prob=fp)
            pos = labels.sum().item()
            print('  fp=%.2f seed=%d: pos=%d/%d (%.3f)' % (fp, seed, pos, labels.shape[0], pos/labels.shape[0]))
