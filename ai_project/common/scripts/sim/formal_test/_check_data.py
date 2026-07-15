import torch

data = torch.load('data/training_data.pt', weights_only=False)
print('Keys:', list(data.keys()))
total_samples = 0
for split in ['train', 'val', 'test']:
    samples = data[split]
    total_samples += len(samples)
    total_nodes = 0
    total_pos = 0
    total_edges = 0
    for g, label in samples:
        total_nodes += label.shape[0]
        total_pos += label.sum().item()
        total_edges += g.edge_index.shape[1]
    print('  %s: %d samples, %d nodes, %d edges, pos=%.0f/%.0f (%.3f)' % (
        split, len(samples), total_nodes, total_edges,
        total_pos, total_nodes, total_pos/total_nodes))
print('Total: %d samples' % total_samples)
print('File size: %.1f MB' % (3.3))
