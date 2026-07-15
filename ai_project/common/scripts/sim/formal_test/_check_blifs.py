import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blif_to_pyg import BlifToAIG
import torch

script_dir = os.path.dirname(os.path.abspath(__file__))
blif_dir = os.path.abspath(os.path.join(script_dir, '..', '..', 'test_mock_data'))

# Exclude duplicates and broken designs
exclude = {'output_counter_demo_input.blif', 'output_mixed_design.blif'}

for blif_name in sorted(os.listdir(blif_dir)):
    if not blif_name.endswith('.blif') or blif_name in exclude:
        continue
    blif_file = os.path.join(blif_dir, blif_name)
    size = os.path.getsize(blif_file)
    
    try:
        converter = BlifToAIG(blif_file)
        summary = converter.summary()
        
        # Check connectivity
        src = converter.edge_index[0]
        num_nodes = converter.num_nodes
        
        pi_nodes = [i for i in range(num_nodes) if converter.node_type[i] == converter.PI]
        dff_nodes = [i for i in range(num_nodes) if converter.node_type[i] == converter.DFF]
        and_nodes = [i for i in range(num_nodes) if converter.node_type[i] == converter.AND]
        
        pi_with_edges = sum(1 for pi in pi_nodes if (src == pi).any().item())
        dff_with_edges = sum(1 for d in dff_nodes if (src == d).any().item())
        
        # Test fault injection
        labels = converter.generate_fault_labels(seed=42, fault_prob=0.1)
        pos = labels.sum().item()
        density = pos / num_nodes if num_nodes else 0
        
        print('%s: %s' % (blif_name, summary))
        print('  Size: %dKB, PI:%d(%d edge), DFF:%d(%d edge), AND:%d' % 
              (size//1024, len(pi_nodes), pi_with_edges, len(dff_nodes), dff_with_edges, len(and_nodes)))
        print('  Fault pos: %d/%d (%.1f%%)' % (pos, num_nodes, density*100))
        
    except Exception as e:
        print('%s: ERROR - %s' % (blif_name, e))
