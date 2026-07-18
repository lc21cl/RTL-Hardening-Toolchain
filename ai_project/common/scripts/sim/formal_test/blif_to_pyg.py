"""
BLIF to PyTorch Geometric graph data converter.

Parses Yosys-generated BLIF files and converts them into PyG Data objects
for GNN-based hardware analysis (fault propagation, vulnerability prediction, etc.).
"""

import re
import numpy as np
from collections import deque

# ── Dependency check ──────────────────────────────────────────────────────────

try:
    import torch
except ImportError:
    raise ImportError(
        "PyTorch is required. Install it via: pip install torch"
    )

try:
    from torch_geometric.data import Data
except ImportError:
    raise ImportError(
        "PyTorch Geometric is required. Install it via: pip install torch_geometric"
    )

# ── BLIF Parser ───────────────────────────────────────────────────────────────


class BlifParser:
    """Parse Yosys BLIF output into structured data."""

    DIRECTIVES = {'.model', '.inputs', '.outputs', '.names', '.latch',
                  '.subckt', '.end', '.attr', '.param'}

    def __init__(self, blif_path):
        self.path = blif_path
        self.model_name = ""
        self.inputs = []          # primary input signal names
        self.outputs = []         # primary output signal names
        self.names_tables = []    # list of (inputs_list, output, truth_table_rows)
        self.latches = []         # list of (input, output, type, control)
        self.subckts = []         # list of (model, pin_map)

        self._parse()

    # ------------------------------------------------------------------
    def _parse(self):
        with open(self.path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Strip comments (lines starting with #) and blank lines
        cleaned = []
        for line in lines:
            stripped = line.split('#')[0].strip()
            if stripped:
                cleaned.append(stripped)

        i = 0
        while i < len(cleaned):
            line = cleaned[i]
            tokens = line.split()

            if not tokens:
                i += 1
                continue

            directive = tokens[0]

            if directive == '.model':
                self.model_name = tokens[1] if len(tokens) > 1 else ""

            elif directive == '.inputs':
                self.inputs.extend(tokens[1:])

            elif directive == '.outputs':
                self.outputs.extend(tokens[1:])

            elif directive == '.names':
                output = tokens[-1]
                inputs = tokens[1:-1]
                rows = []
                i += 1
                while i < len(cleaned) and cleaned[i][0] not in '.$':
                    # Could be a truth table row (e.g. "11 1") or just "1" for const
                    row_line = cleaned[i]
                    if re.match(r'^[01!? ]+$', row_line) or re.match(r'^[01]$', row_line):
                        rows.append(row_line)
                    else:
                        break
                    i += 1
                self.names_tables.append((inputs, output, rows))
                continue  # skip the i += 1 below

            elif directive == '.latch':
                # .latch <input> <output> [<type> <control>]
                if len(tokens) >= 3:
                    inp = tokens[1]
                    out = tokens[2]
                    typ = tokens[3] if len(tokens) > 3 else None
                    ctrl = tokens[4] if len(tokens) > 4 else None
                    self.latches.append((inp, out, typ, ctrl))

            elif directive in ('.subckt', '.gate'):
                # .subckt <model> <pin1>=<sig1> <pin2>=<sig2> ...
                # .gate <model> <pin1>=<sig1> <pin2>=<sig2> ...
                if len(tokens) >= 2:
                    model = tokens[1]
                    pin_map = {}
                    for kv in tokens[2:]:
                        if '=' in kv:
                            pin, sig = kv.split('=', 1)
                            pin_map[pin.strip()] = sig.strip()
                    self.subckts.append((model, pin_map))

            elif directive == '.end':
                break

            i += 1

    def get_all_signals(self):
        """Return the set of every signal name appearing in the design."""
        sigs = set()
        sigs.update(self.inputs)
        sigs.update(self.outputs)
        for ins, out, _ in self.names_tables:
            sigs.add(out)
            sigs.update(ins)
        for inp, out, _, _ in self.latches:
            sigs.add(inp)
            sigs.add(out)
        for _, pin_map in self.subckts:
            sigs.update(pin_map.values())
        return sigs

    def signal_to_node_name(self, sig):
        """Normalize a signal name for use as a graph node key."""
        return sig

    def summary(self):
        """Return a short text summary of the parsed design."""
        return (f"model={self.model_name}, "
                f"PI={len(self.inputs)}, PO={len(self.outputs)}, "
                f"names={len(self.names_tables)}, "
                f"subckts={len(self.subckts)}")


# ── AIG Graph Builder ─────────────────────────────────────────────────────────


class BlifToAIG:
    """Convert parsed BLIF data into a PyTorch Geometric graph."""

    # Node types
    PI = 0
    PO = 1
    AND = 2
    DFF = 3
    CONST0 = 4
    CONST1 = 5

    def __init__(self, blif_path):
        self.parser = BlifParser(blif_path)
        self._build_graph()

    # ------------------------------------------------------------------
    def _build_graph(self):
        p = self.parser

        # ── 1. Collect all signals and classify nodes ──
        pi_set = set(self._clean_sig(s) for s in p.inputs)
        po_set = set(self._clean_sig(s) for s in p.outputs)
        const0_set = set()
        const1_set = set()
        dff_q_set = set()
        dff_d_map = {}       # Q -> D signal
        and_outputs = set()   # signals that are AND gate outputs

        # Constants (names with no inputs or a bare "1" truth table)
        for ins, out, rows in p.names_tables:
            out_clean = self._clean_sig(out)
            if not ins:
                if rows and rows[0].strip() == '1':
                    const1_set.add(out_clean)
                else:
                    const0_set.add(out_clean)

        # DFFs from .subckt
        for model, pin_map in p.subckts:
            if model.startswith('$_DFF'):
                q = self._clean_sig(pin_map.get('Q', ''))
                d = self._clean_sig(pin_map.get('D', ''))
                if q:
                    dff_q_set.add(q)
                    dff_d_map[q] = d

        # DFFs from .latch
        for inp, out, typ, ctrl in p.latches:
            out_clean = self._clean_sig(out)
            dff_q_set.add(out_clean)
            dff_d_map[out_clean] = self._clean_sig(inp)

        # AND gates: .names with truth table rows matching "11...1 1"
        for ins, out, rows in p.names_tables:
            out_clean = self._clean_sig(out)
            if not ins:
                continue  # already handled as constant
            if out_clean in dff_q_set:
                continue  # DFF outputs are not AND nodes
            if rows and self._is_and_gate(rows, len(ins)):
                and_outputs.add(out_clean)

        # All signals in the design
        all_sigs_set = set()
        all_sigs_set.update(pi_set)
        all_sigs_set.update(po_set)
        for ins, out, _ in p.names_tables:
            all_sigs_set.add(self._clean_sig(out))
            for s in ins:
                all_sigs_set.add(self._clean_sig(s))
        for _, pin_map in p.subckts:
            for v in pin_map.values():
                all_sigs_set.add(self._clean_sig(v))
        all_sigs = sorted(all_sigs_set)

        # ── 2. Assign node indices and types ──
        node_name_to_idx = {name: i for i, name in enumerate(all_sigs)}
        num_nodes = len(all_sigs)
        node_type = [self.AND] * num_nodes  # default

        for i, name in enumerate(all_sigs):
            if name in pi_set:
                node_type[i] = self.PI
            elif name in po_set:
                node_type[i] = self.PO
            elif name in const0_set:
                node_type[i] = self.CONST0
            elif name in const1_set:
                node_type[i] = self.CONST1
            elif name in dff_q_set:
                node_type[i] = self.DFF
            elif name in and_outputs:
                node_type[i] = self.AND
            else:
                # Unclassified: treat as internal AND node (AIG buffer)
                node_type[i] = self.AND

        # ── 3. Build edges ──
        edge_index_src = []
        edge_index_dst = []
        edge_attr = []

        def add_edge(src_name, dst_name, inverted):
            src_idx = node_name_to_idx.get(self._clean_sig(src_name))
            dst_idx = node_name_to_idx.get(self._clean_sig(dst_name))
            if src_idx is not None and dst_idx is not None:
                edge_index_src.append(src_idx)
                edge_index_dst.append(dst_idx)
                edge_attr.append([1.0 if inverted else 0.0])

        # AND / INV gates from .names
        for ins, out, rows in p.names_tables:
            out_clean = self._clean_sig(out)
            if not ins:
                continue
            inverted_mask = self._get_inversion_mask(rows, len(ins))
            for j, inp in enumerate(ins):
                inv = inverted_mask[j] if j < len(inverted_mask) else False
                add_edge(inp, out_clean, inv)

        # DFF edges: D -> Q
        for q, d in dff_d_map.items():
            add_edge(d, q, False)

        self.num_nodes = num_nodes
        self.node_names = all_sigs
        self.node_type = torch.tensor(node_type, dtype=torch.long)
        self.edge_index = torch.tensor([edge_index_src, edge_index_dst],
                                        dtype=torch.long)
        self.edge_attr = torch.tensor(edge_attr, dtype=torch.float) \
            if edge_attr else torch.empty((0, 1), dtype=torch.float)

        # ── 4. Compute fan-in / fan-out / depth ──
        fan_in = [0] * num_nodes
        fan_out = [0] * num_nodes
        for s, d in zip(edge_index_src, edge_index_dst):
            fan_in[d] += 1
            fan_out[s] += 1

        # Logic depth (topological order from PIs, CONSTs, and DFFs)
        adj = [[] for _ in range(num_nodes)]
        rev_adj = [[] for _ in range(num_nodes)]
        for s, d in zip(edge_index_src, edge_index_dst):
            adj[s].append(d)
            rev_adj[d].append(s)

        in_deg = [0] * num_nodes
        for s, d in zip(edge_index_src, edge_index_dst):
            in_deg[d] += 1

        depth = [0] * num_nodes
        q = deque()
        for i in range(num_nodes):
            if in_deg[i] == 0:
                q.append(i)
                depth[i] = 0
        while q:
            u = q.popleft()
            for v in adj[u]:
                depth[v] = max(depth[v], depth[u] + 1)
                in_deg[v] -= 1
                if in_deg[v] == 0:
                    q.append(v)

        # Reverse depth (distance to PO)
        rev_depth = [0] * num_nodes
        out_deg = [0] * num_nodes
        for s, d in zip(edge_index_src, edge_index_dst):
            out_deg[s] += 1
        q = deque()
        for i in range(num_nodes):
            if out_deg[i] == 0:
                q.append(i)
                rev_depth[i] = 0
        while q:
            u = q.popleft()
            for p in rev_adj[u]:
                rev_depth[p] = max(rev_depth[p], rev_depth[u] + 1)
                out_deg[p] -= 1
                if out_deg[p] == 0:
                    q.append(p)

        # ── 5. Build node feature matrix (10-dim) ──
        # [is_PI, is_PO, is_AND, is_DFF,
        #  fan_in/max_fan_in, fan_out/max_fan_out,
        #  depth/max_depth, is_const,
        #  local_clustering_coeff,
        #  path_length_entropy]
        # NOTE: rev_depth and rel_position are REMOVED to avoid data leakage
        # NOTE: structural_diversity and fanout_distribution replaced with path_length_entropy
        max_fan_in = max(max(fan_in), 1)
        max_fan_out = max(max(fan_out), 1)
        max_depth = max(max(depth), 1)

        # Build adjacency lists for efficient neighbor lookup
        adj_list = [set() for _ in range(num_nodes)]
        for s, d in zip(edge_index_src, edge_index_dst):
            adj_list[s].add(d)
            adj_list[d].add(s)

        # Local clustering coefficient: fraction of neighbors connected to each other
        clustering = [0.0] * num_nodes
        max_degree_for_cc = 50
        for i in range(num_nodes):
            neighbors = adj_list[i]
            k = len(neighbors)
            if k >= 2 and k <= max_degree_for_cc:
                closed_triangles = 0
                neighbor_list = list(neighbors)
                for j in range(k):
                    for m in range(j + 1, k):
                        if neighbor_list[m] in adj_list[neighbor_list[j]]:
                            closed_triangles += 1
                clustering[i] = 2.0 * closed_triangles / (k * (k - 1))

        # Path length entropy: measure of path diversity from node to POs
        # Higher entropy means more diverse path lengths (more robust)
        po_indices = [i for i in range(num_nodes) if node_type[i] == self.PO]
        path_length_entropy = [0.0] * num_nodes
        max_dist_for_entropy = 30
        
        for i in range(num_nodes):
            dist_counts = {}
            visited = {i: 0}
            q = deque([(i, 0)])
            while q:
                u, dist = q.popleft()
                if dist > max_dist_for_entropy:
                    continue
                for v in adj[u]:
                    if v not in visited or visited[v] > dist + 1:
                        visited[v] = dist + 1
                        if node_type[v] == self.PO:
                            dist_counts[dist + 1] = dist_counts.get(dist + 1, 0) + 1
                        q.append((v, dist + 1))
            
            total = sum(dist_counts.values())
            if total > 0 and len(dist_counts) > 1:
                entropy = 0.0
                log_total = np.log(total)
                for cnt in dist_counts.values():
                    p = cnt / total
                    if p > 0:
                        entropy -= p * np.log(p)
                max_possible = np.log(len(dist_counts))
                if max_possible > 0:
                    path_length_entropy[i] = entropy / max_possible
                else:
                    path_length_entropy[i] = 0.0
            else:
                path_length_entropy[i] = 0.0

        # Betweenness centrality approximation: fraction of shortest paths that go through this node
        # Nodes with high betweenness are critical for signal propagation
        betweenness = [0.0] * num_nodes
        max_dist_for_betweenness = 8
        
        for i in range(num_nodes):
            if node_type[i] in (self.CONST0, self.CONST1):
                continue
            
            reachable = set()
            dist_from_i = {}
            q = deque([(i, 0)])
            dist_from_i[i] = 0
            while q:
                u, d = q.popleft()
                if d >= max_dist_for_betweenness:
                    continue
                reachable.add(u)
                for v in adj[u]:
                    if v not in dist_from_i or dist_from_i[v] > d + 1:
                        dist_from_i[v] = d + 1
                        q.append((v, d + 1))
            
            count = 0
            for s in reachable:
                if s == i:
                    continue
                for t in reachable:
                    if t == i or t == s:
                        continue
                    if s in dist_from_i and t in dist_from_i:
                        via_i_dist = dist_from_i[s] + dist_from_i[t]
                        if via_i_dist <= max_dist_for_betweenness * 2:
                            count += 1
            betweenness[i] = count / max(1, len(reachable) * (len(reachable) - 1))

        max_clustering = max(clustering) if clustering else 1.0
        max_entropy = max(path_length_entropy) if path_length_entropy else 1.0
        max_betweenness = max(betweenness) if betweenness else 1.0

        # Fanout cone size: number of downstream nodes reachable from this node
        # PI nodes with large fanout cones affect more circuit logic
        fanout_cone_size = [0] * num_nodes
        max_cone_bfs = 500  # limit BFS size for large graphs
        
        for i in range(num_nodes):
            visited = {i}
            q = deque([i])
            count = 0
            while q and count < max_cone_bfs:
                u = q.popleft()
                for v in adj[u]:
                    if v not in visited:
                        visited.add(v)
                        count += 1
                        q.append(v)
            fanout_cone_size[i] = count
        
        max_fanout_cone = max(fanout_cone_size) if fanout_cone_size else 1.0
        
        # PO reachability: number of POs reachable from this node
        # PIs that reach more POs are more critical for circuit outputs
        po_reachability = [0] * num_nodes
        po_set = set(i for i in range(num_nodes) if node_type[i] == self.PO)
        
        for i in range(num_nodes):
            visited = {i}
            q = deque([i])
            po_count = 0
            while q:
                u = q.popleft()
                if u in po_set and u != i:
                    po_count += 1
                for v in adj[u]:
                    if v not in visited:
                        visited.add(v)
                        q.append(v)
            po_reachability[i] = po_count
        
        max_po_reach = max(po_reachability) if po_reachability else 1.0

        feat = torch.zeros((num_nodes, 12), dtype=torch.float)
        for i in range(num_nodes):
            nt = node_type[i]
            feat[i, 0] = 1.0 if nt == self.PI else 0.0
            feat[i, 1] = 1.0 if nt == self.PO else 0.0
            feat[i, 2] = 1.0 if nt == self.AND else 0.0
            feat[i, 3] = 1.0 if nt == self.DFF else 0.0
            feat[i, 4] = fan_in[i] / max_fan_in
            feat[i, 5] = fan_out[i] / max_fan_out
            feat[i, 6] = depth[i] / max_depth
            feat[i, 7] = 1.0 if nt in (self.CONST0, self.CONST1) else 0.0
            feat[i, 8] = path_length_entropy[i] / (max_entropy + 1e-6)
            feat[i, 9] = betweenness[i] / (max_betweenness + 1e-6)
            feat[i, 10] = fanout_cone_size[i] / (max_fanout_cone + 1e-6)
            feat[i, 11] = po_reachability[i] / (max_po_reach + 1e-6)

        self.x = feat
        self.fan_in = fan_in
        self.fan_out = fan_out
        self.depth = depth
        self.rev_depth = rev_depth

    # ------------------------------------------------------------------
    @staticmethod
    def _clean_sig(sig):
        """Remove surrounding whitespace from a signal name."""
        return sig.strip()

    @staticmethod
    def _is_and_gate(rows, num_inputs):
        """Check if a truth table represents an AND gate (all-1s cube)."""
        for row in rows:
            parts = row.split()
            if len(parts) < 2:
                continue
            pattern = parts[0]
            out_val = parts[-1]
            if out_val == '1' and all(ch == '1' for ch in pattern):
                return True
        return False

    @staticmethod
    def _get_inversion_mask(rows, num_inputs):
        """
        Return a list of booleans indicating which inputs are negated.
        For an AND gate with pattern '11...1', all are False (positive).
        For a NOT gate with '0 1', the first input is inverted (True).
        For more general cubes, parse the input pattern.
        """
        mask = [False] * num_inputs
        for row in rows:
            parts = row.split()
            if len(parts) < 2:
                continue
            pattern = parts[0]
            out_val = parts[-1]
            if out_val == '1':
                for j, ch in enumerate(pattern):
                    if ch == '0':
                        mask[j] = True
        return mask

    # ------------------------------------------------------------------
    def build_pyg_data(self) -> Data:
        """Return a torch_geometric.data.Data object."""
        return Data(
            x=self.x,
            edge_index=self.edge_index,
            edge_attr=self.edge_attr,
            node_type=self.node_type,
            num_nodes=self.num_nodes,
        )

    # ------------------------------------------------------------------
    def to_networkx(self):
        """Convert to a NetworkX graph for visualization."""
        try:
            import networkx as nx
        except ImportError:
            raise ImportError("networkx is required. Install via: pip install networkx")

        G = nx.DiGraph()
        for i, name in enumerate(self.node_names):
            nt = self.node_type[i].item()
            type_labels = {0: 'PI', 1: 'PO', 2: 'AND', 3: 'DFF', 4: 'CONST0', 5: 'CONST1'}
            G.add_node(i, name=name, type=type_labels.get(nt, 'UNK'))

        src = self.edge_index[0].tolist()
        dst = self.edge_index[1].tolist()
        attr = self.edge_attr.tolist()
        for s, d, a in zip(src, dst, attr):
            G.add_edge(s, d, inverted=bool(a[0]))

        return G

    # ------------------------------------------------------------------
    def generate_fault_labels(self, seed=None, fault_prob=0.1,
                               fault_targets=None, deterministic=False,
                               label_mode='prob_decay'):
        """
        Generate per-node vulnerability labels.

        Three modes (controlled by label_mode):
          - 'prob_decay' (DEFAULT): Probabilistic decay propagation.
            Each node's vulnerability = sum of path weights from node to POs,
            where path weight decays with distance (1/hop^2) and fanout.
            Returns continuous [0,1] vulnerability scores.
          - 'path_count': Fraction of all PI->PO paths that pass through this node.
          - 'binary': Legacy deterministic binary labels (is_target & can_reach_po).
          - 'stochastic': Legacy random injection mode (kept for comparison).

        Args:
            seed: Used for stochastic mode.
            fault_prob: Used for stochastic mode.
            fault_targets: Set of node types to consider. Default: (PI, AND, DFF).
            deterministic: If True, excludes stochastic mode.
            label_mode: 'prob_decay', 'path_count', 'binary', or 'stochastic'.

        Returns:
            labels: Tensor [num_nodes] with vulnerability scores.
        """
        if fault_targets is None:
            fault_targets = (self.PI, self.AND, self.DFF)

        num_nodes = self.num_nodes
        src = self.edge_index[0].tolist()
        dst = self.edge_index[1].tolist()

        # ── Build reverse adjacency ──
        rev_adj = [[] for _ in range(num_nodes)]
        for s, d in zip(src, dst):
            rev_adj[d].append(s)

        po_indices = [i for i in range(num_nodes)
                      if self.node_type[i].item() == self.PO]

        # ── Backward reachability (used by all modes) ──
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

        # ── Mode 1: Probabilistic decay propagation (default) ──
        # Path weight = product of 1/fanout along the path * 1/distance^2
        # This captures both structural importance and distance to PO
        if label_mode == 'prob_decay' or (deterministic and label_mode != 'binary'):
            fan_out = [0] * num_nodes
            for s, d in zip(src, dst):
                fan_out[s] += 1

            vulnerability = [0.0] * num_nodes

            q = deque()
            for po in po_indices:
                vulnerability[po] = 1.0
                q.append((po, 1.0, 0))

            seen = {}
            for po in po_indices:
                seen[po] = 1.0

            eps = 1e-8
            max_dist = 50

            while q:
                u, weight, dist = q.popleft()
                if dist >= max_dist or weight < eps:
                    continue
                for pred in rev_adj[u]:
                    fo = max(fan_out[pred], 1)
                    new_weight = weight * (1.0 / fo) * (1.0 / (dist + 1) ** 2)
                    if new_weight < eps:
                        continue
                    if pred not in seen or new_weight > seen[pred]:
                        seen[pred] = new_weight
                        vulnerability[pred] += new_weight
                        q.append((pred, new_weight, dist + 1))

            max_vuln = max(vulnerability) if vulnerability else 1.0
            labels = torch.tensor([v / max_vuln for v in vulnerability],
                                   dtype=torch.float)

            for i in range(num_nodes):
                nt = self.node_type[i].item()
                if nt not in fault_targets:
                    labels[i] = 0.0

            return labels

        # ── Mode 2: Path count fraction ──
        # What fraction of all PI->PO paths go through this node?
        if label_mode == 'path_count':
            adj = [[] for _ in range(num_nodes)]
            for s, d in zip(src, dst):
                adj[s].append(d)

            def count_paths(start, end, memo):
                if start == end:
                    return 1
                if (start, end) in memo:
                    return memo[(start, end)]
                total = 0
                for neighbor in adj[start]:
                    total += count_paths(neighbor, end, memo)
                memo[(start, end)] = total
                return total

            pi_indices = [i for i in range(num_nodes)
                          if self.node_type[i].item() == self.PI]

            total_paths = 0
            node_path_counts = [0] * num_nodes

            for pi in pi_indices:
                for po in po_indices:
                    memo = {}
                    pc = count_paths(pi, po, memo)
                    total_paths += pc

                    visited_pc = set()
                    q = deque([pi])
                    visited_pc.add(pi)
                    while q:
                        u = q.popleft()
                        node_path_counts[u] += pc
                        for v in adj[u]:
                            if v not in visited_pc:
                                visited_pc.add(v)
                                q.append(v)

            if total_paths > 0:
                labels = torch.tensor([c / total_paths for c in node_path_counts],
                                       dtype=torch.float)
            else:
                labels = torch.zeros(num_nodes, dtype=torch.float)

            for i in range(num_nodes):
                nt = self.node_type[i].item()
                if nt not in fault_targets:
                    labels[i] = 0.0

            return labels

        # ── Mode 3: Legacy binary deterministic ──
        if label_mode == 'binary' or (deterministic and label_mode == 'binary'):
            labels = torch.zeros(num_nodes, dtype=torch.float)
            for i in range(num_nodes):
                nt = self.node_type[i].item()
                if nt in fault_targets and can_reach_po[i]:
                    labels[i] = 1.0
            return labels

        # ── Mode 4: Legacy stochastic ──
        if seed is not None:
            torch.manual_seed(seed)

        fault = torch.zeros(num_nodes, dtype=torch.bool)
        for i in range(num_nodes):
            nt = self.node_type[i].item()
            if nt in fault_targets:
                fault[i] = torch.rand(1).item() < fault_prob

        order = sorted(range(num_nodes), key=lambda i: self.depth[i])
        for u in order:
            if fault[u]:
                for s, d in zip(src, dst):
                    if s == u:
                        fault[d] = True

        labels = (fault & can_reach_po).float()
        return labels

    # ------------------------------------------------------------------
    def summary(self):
        """Return a text summary of the parsed design."""
        num_nodes = self.num_nodes
        type_counts = {}
        for i in range(num_nodes):
            nt = self.node_type[i].item()
            type_counts[nt] = type_counts.get(nt, 0) + 1
        type_labels = {0: 'PI', 1: 'PO', 2: 'AND', 3: 'DFF', 4: 'CONST0', 5: 'CONST1'}
        desc = ', '.join(f"{type_labels.get(k, str(k))}={v}"
                         for k, v in sorted(type_counts.items()))
        return (f"model={self.parser.model_name}, "
                f"nodes={num_nodes}, edges={self.edge_index.size(1)}, "
                f"{desc}")


# ── Bulk Generation ───────────────────────────────────────────────────────────


def batch_generate(designs_dir, output_file, scenarios_per_design=15, seed=42):
    """
    Scan *.blif files in designs_dir, generate fault-injection scenarios,
    and save as a single .pt file.

    The saved object is a list of (Data, label) tuples.
    """
    import glob
    import os

    blif_files = glob.glob(os.path.join(designs_dir, '*.blif'))
    if not blif_files:
        print(f"Warning: No .blif files found in {designs_dir}")
        return

    all_samples = []
    base_seed = seed

    for blif_path in sorted(blif_files):
        print(f"Processing: {blif_path}")
        converter = BlifToAIG(blif_path)
        data = converter.build_pyg_data()

        for scenario_idx in range(scenarios_per_design):
            s = base_seed + hash(blif_path) % (2 ** 31) + scenario_idx
            label = converter.generate_fault_labels(seed=s)
            all_samples.append((data.clone(), label.clone()))

        print(f"  -> {converter.summary()}")
        print(f"  -> Generated {scenarios_per_design} scenarios")

    torch.save(all_samples, output_file)
    print(f"\nSaved {len(all_samples)} samples to {output_file}")
    return all_samples


# ── CLI Entry Point ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python blif_to_pyg.py <blif_file>")
        sys.exit(1)

    path = sys.argv[1]
    converter = BlifToAIG(path)
    print(converter.summary())

    data = converter.build_pyg_data()
    print(f"PyG Data: x={data.x.shape}, edge_index={data.edge_index.shape}")

    # Show a few node features
    print("\nSample node features (first 5 nodes):")
    for i in range(min(5, converter.num_nodes)):
        nt = converter.node_type[i].item()
        type_labels = {0: 'PI', 1: 'PO', 2: 'AND', 3: 'DFF', 4: 'CONST0', 5: 'CONST1'}
        print(f"  [{i}] name='{converter.node_names[i]}' "
              f"type={type_labels.get(nt, '?')} "
              f"feat={converter.x[i].tolist()}")

    # Fault label demo
    label = converter.generate_fault_labels(seed=42)
    vuln_count = label.sum().item()
    print(f"\nFault injection: {vuln_count:.0f}/{converter.num_nodes} nodes vulnerable")
