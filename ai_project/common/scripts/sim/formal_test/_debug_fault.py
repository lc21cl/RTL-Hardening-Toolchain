import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blif_to_pyg import BlifToAIG
import torch

script_dir = os.path.dirname(os.path.abspath(__file__))
blif_dir = os.path.abspath(os.path.join(script_dir, '..', '..', 'test_mock_data'))
blif_file = os.path.join(blif_dir, 'output_mixed_design.blif')

converter = BlifToAIG(blif_file)
print(converter.summary())

num_nodes = converter.num_nodes
src = converter.edge_index[0]
dst = converter.edge_index[1]
print('Total edges:', src.shape[0])
print('Edge examples (src->dst):')
for i in range(min(10, src.shape[0])):
    sn = converter.node_names[src[i].item()]
    dn = converter.node_names[dst[i].item()]
    print('  %d(%s) -> %d(%s)' % (src[i].item(), sn, dst[i].item(), dn))

# Check: what are the PIs and POs?
print('\nPI nodes:', [(i, converter.node_names[i]) for i in range(num_nodes) if converter.node_type[i] == converter.PI][:5])
print('PO nodes:', [(i, converter.node_names[i]) for i in range(num_nodes) if converter.node_type[i] == converter.PO][:5])

# Check edges FROM PIs
pi_indices = [i for i in range(num_nodes) if converter.node_type[i] == converter.PI]
print('\nEdges from PIs:')
for pi in pi_indices[:3]:
    out_edges = [(s.item(), d.item()) for s, d in zip(src, dst) if s == pi]
    print('  PI %d (%s) -> %s' % (pi, converter.node_names[pi], out_edges[:5]))

# Check edges TO POs
po_indices = [i for i in range(num_nodes) if converter.node_type[i] == converter.PO]
print('\nEdges to POs:')
for po in po_indices[:3]:
    in_edges = [(s.item(), d.item()) for s, d in zip(src, dst) if d == po]
    print('  PO %d (%s) <- %s' % (po, converter.node_names[po], in_edges[:5]))

# Build rev_adj and check backward reachability
rev_adj = [[] for _ in range(num_nodes)]
for s, d in zip(src.tolist(), dst.tolist()):
    rev_adj[d].append(s)

from collections import deque
can_reach_po = torch.zeros(num_nodes, dtype=torch.bool)
q = deque(po_indices)
for p in po_indices:
    can_reach_po[p] = True
visited = set(po_indices)
while q:
    u = q.popleft()
    for pred in rev_adj[u]:
        if pred not in visited:
            visited.add(pred)
            can_reach_po[pred] = True
            q.append(pred)

print('\nNodes that can reach PO (%d total):' % can_reach_po.sum().item())
for i in range(num_nodes):
    if can_reach_po[i]:
        print('  %d: %s (type=%d)' % (i, converter.node_names[i], converter.node_type[i].item()))
