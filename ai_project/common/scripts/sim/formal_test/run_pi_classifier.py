import os
import sys
import json
import torch
import numpy as np
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, 'data', 'training_data_15feat.pt')
MODEL_DIR = os.path.join(SCRIPT_DIR, 'data', 'models')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'data', 'pi_classifier')
os.makedirs(OUTPUT_DIR, exist_ok=True)


class PIFPReductionClassifier:
    def __init__(self, sage_model=None):
        self.sage_model = sage_model
        self.sage_pi_threshold = 0.75
        self.pi_classifier_threshold = 0.60
        self.min_po_reach = 1
        self.min_dff_in_cone = 1
        self.min_critical_path = 3
        self.min_fanout_size = 10

    def extract_node_types(self, graph_data):
        num_nodes = graph_data.x.shape[0]
        node_types = np.zeros(num_nodes, dtype=int)
        for i in range(num_nodes):
            if graph_data.x[i, 0] > 0.5:
                node_types[i] = 1
            elif graph_data.x[i, 1] > 0.5:
                node_types[i] = 2
            elif graph_data.x[i, 2] > 0.5:
                node_types[i] = 3
            elif graph_data.x[i, 3] > 0.5:
                node_types[i] = 4
            elif graph_data.x[i, 7] > 0.5:
                node_types[i] = 5
        return node_types

    def build_adjacency(self, edge_index):
        adj = defaultdict(list)
        for k in range(edge_index.shape[1]):
            src = int(edge_index[0, k])
            dst = int(edge_index[1, k])
            adj[src].append(dst)
        return adj

    def _bfs_downstream(self, adj, start, max_nodes=500):
        visited = set()
        queue = [start]
        visited.add(start)
        while queue and len(visited) < max_nodes:
            node = queue.pop(0)
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited

    def _compute_depth(self, adj, start, cone):
        depth = {start: 0}
        queue = [start]
        while queue:
            node = queue.pop(0)
            for neighbor in adj.get(node, []):
                if neighbor in cone and neighbor not in depth:
                    depth[neighbor] = depth[node] + 1
                    queue.append(neighbor)
        return max(depth.values(), default=0)

    def _count_cone_edges(self, adj, cone):
        count = 0
        for node in cone:
            for neighbor in adj.get(node, []):
                if neighbor in cone:
                    count += 1
        return count

    def _critical_path_length(self, adj, start, node_types):
        longest = 0
        visited = set()

        def dfs(node, current_length):
            nonlocal longest
            if node in visited:
                return
            visited.add(node)
            if node_types[node] == 2:
                longest = max(longest, current_length)
            for neighbor in adj.get(node, []):
                dfs(neighbor, current_length + 1)

        dfs(start, 0)
        return longest

    def extract_pi_features(self, graph_data, pi_node_idx):
        num_nodes = graph_data.x.shape[0]
        edge_index = graph_data.edge_index.numpy()
        node_types = self.extract_node_types(graph_data)
        adj = self.build_adjacency(edge_index)

        cone = self._bfs_downstream(adj, pi_node_idx, max_nodes=500)
        po_count = sum(1 for n in cone if node_types[n] == 2)
        dff_count = sum(1 for n in cone if node_types[n] == 4)
        and_count = sum(1 for n in cone if node_types[n] == 3)
        max_depth = self._compute_depth(adj, pi_node_idx, cone)
        cone_density = self._count_cone_edges(adj, cone) / max(len(cone), 1)
        critical_path = self._critical_path_length(adj, pi_node_idx, node_types)
        dff_ratio = dff_count / max(dff_count + and_count, 1)

        existing_features = graph_data.x[pi_node_idx].numpy()
        betweenness = existing_features[8] if len(existing_features) > 8 else 0.0
        path_entropy = existing_features[9] if len(existing_features) > 9 else 0.0
        degree_out = len(adj[pi_node_idx])
        depth = existing_features[7] if len(existing_features) > 7 else 0.0

        return np.array([
            len(cone), po_count, max_depth,
            dff_count, and_count, betweenness,
            path_entropy, degree_out, depth,
            cone_density, critical_path, dff_ratio
        ], dtype=np.float32)

    def rule_based_filter(self, graph_data, node_idx):
        features = self.extract_pi_features(graph_data, node_idx)
        if features[1] < self.min_po_reach:
            return False
        if features[3] < self.min_dff_in_cone:
            return False
        if features[10] < self.min_critical_path:
            return False
        if features[0] < self.min_fanout_size:
            return False
        return True

    def predict_single(self, graph_data, sage_scores, node_idx, pi_mask):
        if not pi_mask[node_idx]:
            return int(sage_scores[node_idx] > 0.5)

        if not self.rule_based_filter(graph_data, node_idx):
            return 0

        if sage_scores[node_idx] < self.sage_pi_threshold:
            return 0

        features = self.extract_pi_features(graph_data, node_idx)
        pi_score = self.predict_pi_classifier(features)

        return int(pi_score > self.pi_classifier_threshold)

    def predict_pi_classifier(self, features):
        fanout_size = features[0]
        po_reach = features[1]
        critical_path = features[10]
        dff_count = features[3]

        score = 0.0
        if fanout_size > 50:
            score += 0.3
        if po_reach >= 2:
            score += 0.25
        if critical_path >= 5:
            score += 0.25
        if dff_count >= 5:
            score += 0.2

        return min(1.0, score)

    def predict(self, graph_data, sage_scores):
        n = len(graph_data.x)
        pi_mask = graph_data.x[:, 0].numpy() > 0.5
        preds = np.zeros(n, dtype=int)

        for i in range(n):
            if not pi_mask[i]:
                preds[i] = int(sage_scores[i] > 0.5)
                continue

            if not self.rule_based_filter(graph_data, i):
                preds[i] = 0
                continue

            if sage_scores[i] < self.sage_pi_threshold:
                preds[i] = 0
                continue

            features = self.extract_pi_features(graph_data, i)
            pi_score = self.predict_pi_classifier(features)
            preds[i] = int(pi_score > self.pi_classifier_threshold)

        return preds


def analyze_fp_reduction(data, pi_classifier):
    print('\n' + '=' * 62)
    print('  PI False Positive Reduction Analysis')
    print('=' * 62)

    all_preds_base = []
    all_preds_cascade = []
    all_labels = []
    all_pi_masks = []

    for graph in data:
        with torch.no_grad():
            logits = pi_classifier.sage_model(graph.x, graph.edge_index)
            sage_scores = torch.sigmoid(logits).numpy()

        base_preds = (sage_scores > 0.5).astype(int)
        cascade_preds = pi_classifier.predict(graph, sage_scores)

        all_preds_base.extend(base_preds)
        all_preds_cascade.extend(cascade_preds)
        all_labels.extend(graph.y.numpy())
        all_pi_masks.extend(graph.x[:, 0].numpy() > 0.5)

    all_preds_base = np.array(all_preds_base)
    all_preds_cascade = np.array(all_preds_cascade)
    all_labels = np.array(all_labels)
    all_pi_masks = np.array(all_pi_masks)

    pi_mask = all_pi_masks

    base_fp_pi = np.sum((all_preds_base == 1) & (all_labels == 0) & pi_mask)
    base_tp_pi = np.sum((all_preds_base == 1) & (all_labels == 1) & pi_mask)
    base_fn_pi = np.sum((all_preds_base == 0) & (all_labels == 1) & pi_mask)
    base_tn_pi = np.sum((all_preds_base == 0) & (all_labels == 0) & pi_mask)

    cascade_fp_pi = np.sum((all_preds_cascade == 1) & (all_labels == 0) & pi_mask)
    cascade_tp_pi = np.sum((all_preds_cascade == 1) & (all_labels == 1) & pi_mask)
    cascade_fn_pi = np.sum((all_preds_cascade == 0) & (all_labels == 1) & pi_mask)
    cascade_tn_pi = np.sum((all_preds_cascade == 0) & (all_labels == 0) & pi_mask)

    base_fp_non_pi = np.sum((all_preds_base == 1) & (all_labels == 0) & ~pi_mask)
    base_tp_non_pi = np.sum((all_preds_base == 1) & (all_labels == 1) & ~pi_mask)
    cascade_fp_non_pi = np.sum((all_preds_cascade == 1) & (all_labels == 0) & ~pi_mask)
    cascade_tp_non_pi = np.sum((all_preds_cascade == 1) & (all_labels == 1) & ~pi_mask)

    def compute_f1(tp, fp, fn):
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-10)
        return precision, recall, f1

    pi_base_prec, pi_base_rec, pi_base_f1 = compute_f1(base_tp_pi, base_fp_pi, base_fn_pi)
    pi_casc_prec, pi_casc_rec, pi_casc_f1 = compute_f1(cascade_tp_pi, cascade_fp_pi, cascade_fn_pi)

    non_pi_base_prec, non_pi_base_rec, non_pi_base_f1 = compute_f1(base_tp_non_pi, base_fp_non_pi, 0)
    non_pi_casc_prec, non_pi_casc_rec, non_pi_casc_f1 = compute_f1(cascade_tp_non_pi, cascade_fp_non_pi, 0)

    overall_base_prec, overall_base_rec, overall_base_f1 = compute_f1(
        base_tp_pi + base_tp_non_pi,
        base_fp_pi + base_fp_non_pi,
        base_fn_pi
    )
    overall_casc_prec, overall_casc_rec, overall_casc_f1 = compute_f1(
        cascade_tp_pi + cascade_tp_non_pi,
        cascade_fp_pi + cascade_fp_non_pi,
        cascade_fn_pi
    )

    print('\n--- PI Nodes (Fan-out=0) ---')
    print(f'  Total PI nodes: {np.sum(pi_mask)}')
    print(f'  Base model:')
    print(f'    TP: {base_tp_pi}, FP: {base_fp_pi}, FN: {base_fn_pi}, TN: {base_tn_pi}')
    print(f'    Precision: {pi_base_prec:.4f}, Recall: {pi_base_rec:.4f}, F1: {pi_base_f1:.4f}')
    print(f'  Cascade model:')
    print(f'    TP: {cascade_tp_pi}, FP: {cascade_fp_pi}, FN: {cascade_fn_pi}, TN: {cascade_tn_pi}')
    print(f'    Precision: {pi_casc_prec:.4f}, Recall: {pi_casc_rec:.4f}, F1: {pi_casc_f1:.4f}')
    print(f'  FP Reduction: {base_fp_pi} -> {cascade_fp_pi} ({(1 - cascade_fp_pi / max(base_fp_pi, 1)) * 100:.1f}%)')
    print(f'  TP Loss: {base_tp_pi} -> {cascade_tp_pi} ({(1 - cascade_tp_pi / max(base_tp_pi, 1)) * 100:.1f}%)')

    print('\n--- Non-PI Nodes ---')
    print(f'  Base model: TP={base_tp_non_pi}, FP={base_fp_non_pi}, F1={non_pi_base_f1:.4f}')
    print(f'  Cascade model: TP={cascade_tp_non_pi}, FP={cascade_fp_non_pi}, F1={non_pi_casc_f1:.4f}')

    print('\n--- Overall ---')
    print(f'  Base model: F1={overall_base_f1:.4f}')
    print(f'  Cascade model: F1={overall_casc_f1:.4f}')
    print(f'  F1 Change: {(overall_casc_f1 - overall_base_f1) * 100:.2f}%')

    result = {
        'pi_nodes': int(np.sum(pi_mask)),
        'base_pi': {
            'tp': int(base_tp_pi),
            'fp': int(base_fp_pi),
            'fn': int(base_fn_pi),
            'precision': float(pi_base_prec),
            'recall': float(pi_base_rec),
            'f1': float(pi_base_f1),
        },
        'cascade_pi': {
            'tp': int(cascade_tp_pi),
            'fp': int(cascade_fp_pi),
            'fn': int(cascade_fn_pi),
            'precision': float(pi_casc_prec),
            'recall': float(pi_casc_rec),
            'f1': float(pi_casc_f1),
        },
        'fp_reduction': {
            'original': int(base_fp_pi),
            'reduced': int(cascade_fp_pi),
            'reduction_ratio': float(1 - cascade_fp_pi / max(base_fp_pi, 1)),
        },
        'overall': {
            'base_f1': float(overall_base_f1),
            'cascade_f1': float(overall_casc_f1),
        },
    }

    result_path = os.path.join(OUTPUT_DIR, 'pi_fp_reduction_result.json')
    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f'\n  Result saved to: {result_path}')

    return result


def main():
    print('=' * 62)
    print('  PI False Positive Reduction Verification')
    print('=' * 62)

    if not os.path.exists(DATA_PATH):
        print(f'  Error: Data file not found at {DATA_PATH}')
        return

    raw = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
    test_data = raw['test']
    print(f'  Test data: {len(test_data)} graphs')

    from _train_local import SAGE3
    feature_dim = test_data[0].x.shape[1]
    print(f'  Feature dimension: {feature_dim}')

    model_files = []
    if os.path.exists(MODEL_DIR):
        for f in os.listdir(MODEL_DIR):
            if f.endswith('.pth') and 'seed' in f.lower():
                model_files.append(os.path.join(MODEL_DIR, f))

    if not model_files:
        print('  No trained models found. Training a quick model...')
        sys.path.insert(0, SCRIPT_DIR)
        from _train_local import train_model
        
        raw_train = torch.load(DATA_PATH, map_location='cpu', weights_only=False)
        train_data = raw_train['train']
        val_data = raw_train['val']
        
        device = torch.device('cpu')
        model = SAGE3(in_channels=feature_dim)
        
        class DummyMonitor:
            def update(self, *args, **kwargs):
                pass
            def save(self):
                pass
        
        monitor = DummyMonitor()
        best_f1, _ = train_model(model, train_data, val_data, device, monitor, 
                                epochs=20, lr=0.01, patience=10)
        
        model_path = os.path.join(MODEL_DIR, 'sage3_pi_classifier.pth')
        torch.save(model.state_dict(), model_path)
        model_files = [model_path]
        print(f'  Model saved to: {model_path}')

    for model_path in model_files[:1]:
        print(f'\n--- Loading model: {os.path.basename(model_path)} ---')

        model = SAGE3(in_channels=feature_dim)
        model.load_state_dict(torch.load(model_path, map_location='cpu', weights_only=True))
        model.eval()

        pi_classifier = PIFPReductionClassifier(sage_model=model)
        result = analyze_fp_reduction(test_data, pi_classifier)

        fp_reduction = result['fp_reduction']
        if fp_reduction['reduction_ratio'] >= 0.5:
            print(f'\n  ✓ SUCCESS: FP reduced from {fp_reduction["original"]} to {fp_reduction["reduced"]}')
        else:
            print(f'\n  ✗ PARTIAL: FP reduction ratio is {fp_reduction["reduction_ratio"]*100:.1f}%')


if __name__ == '__main__':
    main()
