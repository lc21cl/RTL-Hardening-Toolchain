"""
DFF-Specific Feature Engineering
================================

Problem:
  - DFF nodes have 93.83% recall (204 FN out of 3,306 positives)
  - FN DFF nodes share characteristics:
    * High betweenness_centrality (0.9441 vs 0.5563 for TP)
    * High path_length_entropy (0.7763 vs 0.4403)
    * Low degree_in (0.4227 vs 0.7065)
    * Low depth (0.1099 vs 0.3008)

  Root cause: DFFs are state-holding elements with unique structure:
  - They often form pipeline chains (DFF -> DFF -> DFF)
  - They can be part of feedback loops (counters, state machines)
  - Their vulnerability depends on timing/context, not just topology

Solution: Add 3 DFF-specialized features to the existing 12:
  13. dff_chain_length  — pipeline depth of consecutive DFFs
  14. dff_loop_participation — whether DFF is in a feedback cycle
  15. dff_input_diversity — number of distinct source types feeding this DFF
"""

import os
import sys
import time
from collections import deque, defaultdict
from pathlib import Path

import numpy as np
import torch
from torch_geometric.data import Data

SCRIPT_DIR = Path(__file__).parent.resolve()

class DFFFeatureExtractor:
    """Extract DFF-specialized features from circuit graphs."""

    def __init__(self):
        self.feature_names = [
            'dff_chain_length',
            'dff_loop_participation',
            'dff_input_diversity',
        ]

    def compute_dff_chain_length(self, num_nodes, adj, node_types, dff_flag):
        """
        DFF chain length: longest consecutive DFF-to-DFF path through this node.

        A DFF chain is: DFF -> (combinational logic) -> DFF -> ... -> DFF
        Longer chains = deeper pipelines = potentially more vulnerable to SEU.

        Computed via memoized DFS following forward edges,
        counting only DFF-to-DFF hops.
        """
        chain_length = np.zeros(num_nodes, dtype=np.float32)
        memo = {}

        def dfs(node, visited):
            if node in memo:
                return memo[node]
            if node in visited:
                return 0
            visited.add(node)

            max_downstream = 0
            for neighbor in adj[node]:
                hops = dfs(neighbor, visited.copy())
                if dff_flag[neighbor]:
                    hops += 1
                max_downstream = max(max_downstream, hops)

            memo[node] = max_downstream
            return max_downstream

        for i in range(num_nodes):
            if dff_flag[i]:
                chain_length[i] = dfs(i, set())

        max_chain = chain_length.max()
        if max_chain > 0:
            chain_length /= max_chain

        return chain_length

    def compute_dff_loop_participation(self, num_nodes, adj, dff_flag):
        """
        DFF loop participation: whether a DFF is part of a feedback cycle.

        Feedback loops in DFFs indicate:
        - Counters (state feedback)
        - State machines (next-state logic)
        - These are often more vulnerability-critical

        Uses Tarjan's SCC algorithm to find strongly connected components.
        A DFF in an SCC with >1 node (or self-loop) participates in a loop.
        """
        loop_score = np.zeros(num_nodes, dtype=np.float32)

        index_counter = [0]
        stack = []
        lowlink = [0] * num_nodes
        index = [0] * num_nodes
        on_stack = [False] * num_nodes
        sccs = []

        def strongconnect(v):
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack[v] = True

            for w in adj[v]:
                if index[w] == 0 and w != v:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif on_stack[w]:
                    lowlink[v] = min(lowlink[v], index[w])

            if lowlink[v] == index[v]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    scc.append(w)
                    if w == v:
                        break
                sccs.append(scc)

        sys.setrecursionlimit(max(10000, num_nodes * 2))
        for v in range(num_nodes):
            if index[v] == 0:
                strongconnect(v)

        for scc in sccs:
            scc_set = set(scc)
            has_dff = any(dff_flag[n] for n in scc)
            is_cycle = len(scc) > 1 or (len(scc) == 1 and scc[0] in adj[scc[0]])

            if has_dff and is_cycle:
                cycle_size = len(scc)
                for node in scc:
                    if dff_flag[node]:
                        loop_score[node] = min(cycle_size / 20.0, 1.0)

        return loop_score

    def compute_dff_input_diversity(self, num_nodes, rev_adj, node_types, dff_flag):
        """
        DFF input diversity: variety of source types feeding into this DFF.

        High input diversity = DFF driven by many different logic paths
        Low input diversity = DFF driven by single source (more vulnerable?)

        Measures the Shannon entropy of predecessor node types.
        """
        diversity = np.zeros(num_nodes, dtype=np.float32)

        for i in range(num_nodes):
            if not dff_flag[i]:
                continue

            type_counts = defaultdict(int)
            total = 0

            queue = deque(rev_adj[i])
            visited = set(rev_adj[i])
            visited.add(i)
            bfs_depth = 0

            while queue and bfs_depth < 3:
                level_size = len(queue)
                for _ in range(level_size):
                    node = queue.popleft()
                    nt = node_types[node]
                    type_counts[nt] += 1
                    total += 1

                    for pred in rev_adj[node]:
                        if pred not in visited:
                            visited.add(pred)
                            queue.append(pred)
                bfs_depth += 1

            if total > 0 and len(type_counts) > 1:
                entropy = 0.0
                for count in type_counts.values():
                    p = count / total
                    if p > 0:
                        entropy -= p * np.log(p)
                max_entropy = np.log(len(type_counts))
                if max_entropy > 0:
                    diversity[i] = entropy / max_entropy

        return diversity

    def extract_features(self, graph_data):
        """
        Extract 3 DFF-specific features for a single graph.

        Args:
            graph_data: PyG Data object with x [num_nodes, 12], edge_index [2, num_edges]

        Returns:
            dff_features: np.array [num_nodes, 3]
        """
        num_nodes = graph_data.x.shape[0]
        edge_index = graph_data.edge_index.numpy()

        node_types = np.zeros(num_nodes, dtype=int)
        for i in range(num_nodes):
            if graph_data.x[i, 0] > 0.5: node_types[i] = 1  # PI
            elif graph_data.x[i, 1] > 0.5: node_types[i] = 2  # PO
            elif graph_data.x[i, 2] > 0.5: node_types[i] = 3  # AND
            elif graph_data.x[i, 3] > 0.5: node_types[i] = 4  # DFF
            elif graph_data.x[i, 7] > 0.5: node_types[i] = 5  # CONST

        dff_flag = (node_types == 4)

        adj = defaultdict(list)
        rev_adj = defaultdict(list)
        for k in range(edge_index.shape[1]):
            src = int(edge_index[0, k])
            dst = int(edge_index[1, k])
            adj[src].append(dst)
            rev_adj[dst].append(src)

        chain_length = self.compute_dff_chain_length(
            num_nodes, adj, node_types, dff_flag)

        loop_participation = self.compute_dff_loop_participation(
            num_nodes, adj, dff_flag)

        input_diversity = self.compute_dff_input_diversity(
            num_nodes, rev_adj, node_types, dff_flag)

        features = np.stack([
            chain_length,
            loop_participation,
            input_diversity,
        ], axis=1)

        return features

    def augment_dataset(self, data_dict, save_path=None):
        """
        Augment existing 12-feature dataset with 3 DFF features -> 15 features.

        Args:
            data_dict: {'train': [...], 'val': [...], 'test': [...]}
            save_path: optional path to save augmented data

        Returns:
            augmented data_dict with 15-feature graphs
        """
        print('=' * 60)
        print('  DFF Feature Augmentation')
        print('=' * 60)

        for split_name in ['train', 'val', 'test']:
            if split_name not in data_dict:
                continue

            data_list = data_dict[split_name]
            print(f'\n  Processing {split_name}: {len(data_list)} graphs')

            t0 = time.time()
            for i, data in enumerate(data_list):
                dff_features = self.extract_features(data)

                new_x = torch.zeros(data.x.shape[0], data.x.shape[1] + 3,
                                    dtype=data.x.dtype)
                new_x[:, :data.x.shape[1]] = data.x
                new_x[:, data.x.shape[1]:] = torch.from_numpy(dff_features)

                data.x = new_x

                if (i + 1) % 500 == 0:
                    elapsed = time.time() - t0
                    print(f'    {i+1}/{len(data_list)} '
                          f'({elapsed:.1f}s, {elapsed/(i+1):.3f}s/graph)')

            elapsed = time.time() - t0
            print(f'  {split_name} done: {elapsed:.1f}s '
                  f'({elapsed/len(data_list):.3f}s/graph)')

        if save_path:
            torch.save(data_dict, save_path)
            print(f'\n  Saved to: {save_path}')

        print('\n  Feature dimension: 12 -> 15')
        print('  New features: dff_chain_length, dff_loop_participation, '
              'dff_input_diversity')

        return data_dict


def main():
    DATA_PATH = SCRIPT_DIR / 'data' / 'training_data.pt'
    SAVE_PATH = SCRIPT_DIR / 'data' / 'training_data_15feat.pt'

    print('Loading existing 12-feature dataset...')
    data = torch.load(DATA_PATH, map_location='cpu', weights_only=False)

    extractor = DFFFeatureExtractor()
    data_15 = extractor.augment_dataset(data, save_path=str(SAVE_PATH))

    print('\n' + '=' * 60)
    print('  DFF Feature Engineering Complete')
    print('=' * 60)
    print(f'  Original features: 12')
    print(f'  New features: +3 (dff_chain_length, dff_loop_participation, '
          f'dff_input_diversity)')
    print(f'  Total features: 15')
    print(f'  Output: {SAVE_PATH}')

    print('\n--- Feature Statistics ---')
    for split in ['train', 'val', 'test']:
        if split not in data_15:
            continue
        all_feats = torch.cat([d.x for d in data_15[split]])
        dff_mask = all_feats[:, 3] > 0.5

        print(f'\n  {split} ({len(data_15[split])} graphs, '
              f'{all_feats.shape[0]} nodes, {dff_mask.sum().item()} DFFs):')
        for j, name in enumerate(['dff_chain_length', 'dff_loop_participation',
                                   'dff_input_diversity']):
            feat_idx = 12 + j
            all_vals = all_feats[:, feat_idx]
            dff_vals = all_feats[dff_mask, feat_idx]
            print(f'    {name}:')
            print(f'      All nodes: mean={all_vals.mean():.4f}, '
                  f'std={all_vals.std():.4f}, '
                  f'nonzero={(all_vals > 0).sum().item()}')
            print(f'      DFF only:  mean={dff_vals.mean():.4f}, '
                  f'std={dff_vals.std():.4f}, '
                  f'nonzero={(dff_vals > 0).sum().item()}')


if __name__ == '__main__':
    main()