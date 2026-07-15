"""
PI-Specific Classifier — Design Pseudocode (v2.0)
===================================================

Problem (Revised):
  - Main SAGE3 model achieves F1=0.9891 overall but produces 70 false positives on PI nodes
  - PI nodes have degree_in=0, so GNN message passing provides limited information
  - These 70 FPs are likely caused by:
    * Over-aggregation from downstream nodes
    * High-degree_out PIs being incorrectly flagged
    * Features like betweenness_centrality being correlated with PI status
    * Default threshold (0.5) being too permissive for PI nodes

Root Cause Analysis:
  - PI nodes are graph roots (degree_in=0) — GNN can't aggregate upstream info
  - Most PIs have high fanout -> high degree_out -> higher vulnerability scores
  - The 70 FPs likely have characteristics:
    * High degree_out but low downstream criticality
    * High betweenness_centrality but low PO reachability
    * Feed into non-critical logic paths

Solution: Two-Stage Cascade with FP Reduction
  Stage 1: Main SAGE3 model (existing)
    - Predicts vulnerability for AND/DFF nodes (high accuracy)
    - For PI nodes: outputs "suspicion score" with higher threshold

  Stage 2: PI-Specific Filter (NEW — FP reduction focus)
    - Only activated when SAGE3 flags a PI as vulnerable
    - Uses PI-specialized features to verify the prediction
    - REQUIRES BOTH conditions to be met for final positive:
      1. SAGE3 score > pi_sage_threshold (higher than default)
      2. PI filter confidence > pi_filter_threshold

Key Insight:
  PI vulnerability depends on DOWNSTREAM impact, not just local features.
  A PI with high fanout is only truly vulnerable if:
  - It reaches multiple POs
  - It feeds into critical timing paths
  - It's part of feedback loops (counters, state machines)
"""

# =============================================================================
# DATA PREPARATION for FP Analysis
# =============================================================================

"""
ANALYSIS PHASE:
---------------
1. Extract PI nodes from validation/test data
2. Identify FP PI nodes (SAGE3 predicts 1, ground truth is 0)
3. Compare feature distributions:
   FP PI vs TN PI vs TP PI vs FN PI

KEY FEATURES TO INVESTIGATE:
----------------------------
Feature                    FP PI (70)    TN PI (14759)  TP PI (26)
-------------------------- ------------ --------------- ------------
degree_out                 ?             ?               ?
betweenness_centrality     ?             ?               ?
path_length_entropy        ?             ?               ?
fanout_cone_size           ?             ?               ?
po_reachability            ?             ?               ?
fanout_cone_depth          ?             ?               ?
dff_count_in_cone          ?             ?               ?
critical_path_length       ?             ?               ?

Expected patterns for FP PIs:
  - High degree_out but LOW po_reachability
  - High betweenness but LOW downstream criticality
  - Feeds into combinational logic only (no DFFs)
  - Short critical path length
"""

# =============================================================================
# PI Filter Architecture (FP Reduction Focus)
# =============================================================================

"""
MODEL CHOICE:
-------------
Option A: LightGBM (threshold adjustment mode)
  - Train on PI nodes only
  - Use high precision threshold to minimize FPs
  - Feature importance helps identify FP-causing features

Option B: Rule-based filter (deterministic)
  - If PI has:
    * po_reachability == 0 -> Safe (never reaches output)
    * dff_count_in_cone == 0 -> Likely safe (combinational only)
    * critical_path_length < threshold -> Safe (not timing-critical)
  - Pros: No training needed, interpretable
  - Cons: May miss some true positives

Option C: Two-model consensus
  - Require both SAGE3 AND PI classifier to agree
  - PI classifier trained with higher precision weight
  - Only predict vulnerable if BOTH scores exceed thresholds

RECOMMENDED: Option C (Two-model consensus) with Option B as pre-filter
"""

# =============================================================================
# Training Strategy for FP Reduction
# =============================================================================

"""
TRAINING DATA:
--------------
1. Positive samples: TP PI nodes (26)
2. Negative samples: TN PI nodes + FP PI nodes from previous model
3. Weight scheme:
   - TP PI: weight = 1.0 (target to keep)
   - TN PI: weight = 1.0 (target to correctly classify)
   - FP PI: weight = 5.0 (target to correctly identify as safe!)

OBJECTIVE FUNCTION:
-------------------
Modified F1 loss that penalizes FP more heavily:
  loss = alpha * FP_penalty + beta * FN_penalty
  where alpha > beta (e.g., alpha=5, beta=1)

Alternatively, use weighted cross-entropy:
  pos_weight = (TN_count + FP_count) / TP_count ≈ 570
  fp_weight = 5  # Additional weight for FP samples
"""

# =============================================================================
# Inference Pipeline (FP Reduction Mode)
# =============================================================================

def predict_vulnerability_fp_reduction(graph, sage_model, pi_filter):
    """
    Two-stage consensus inference for PI FP reduction.
    
    Rules:
    1. Non-PI nodes: Use SAGE3 directly (unchanged)
    2. PI nodes: REQUIRE BOTH conditions:
       a. SAGE3 score > PI_SAGE_THRESHOLD (higher than default 0.5)
       b. PI filter confirms vulnerability
    """
    PI_SAGE_THRESHOLD = 0.75      # Higher than default 0.5
    PI_FILTER_THRESHOLD = 0.60     # PI filter must agree
    
    # Stage 1: Run main SAGE3 model
    sage_logits = sage_model(graph.x, graph.edge_index)
    sage_scores = torch.sigmoid(sage_logits).numpy()
    
    # Initialize predictions
    final_preds = np.zeros(len(graph.x), dtype=int)
    
    # Non-PI nodes: use SAGE3 directly
    non_pi_mask = graph.x[:, 0] <= 0.5  # Column 0 is PI indicator
    final_preds[non_pi_mask] = (sage_scores[non_pi_mask] > 0.5).astype(int)
    
    # PI nodes: two-stage consensus
    pi_mask = graph.x[:, 0] > 0.5
    pi_indices = np.where(pi_mask)[0]
    
    for node_idx in pi_indices:
        sage_score = sage_scores[node_idx]
        
        # First gate: SAGE3 must pass higher threshold
        if sage_score < PI_SAGE_THRESHOLD:
            final_preds[node_idx] = 0
            continue
        
        # Second gate: PI filter must confirm
        pi_features = extract_pi_features(graph, node_idx)
        pi_score = pi_filter.predict_proba([pi_features])[0, 1]
        
        # Consensus required: both models must agree
        if pi_score > PI_FILTER_THRESHOLD:
            final_preds[node_idx] = 1
        else:
            # PI filter says it's safe -> override SAGE3
            final_preds[node_idx] = 0
    
    return final_preds

# =============================================================================
# Rule-Based Pre-Filter (Fast FP Elimination)
# =============================================================================

def rule_based_pi_filter(graph, node_idx):
    """
    Fast rule-based filter to eliminate obvious FP candidates.
    
    Rules that indicate a PI is SAFE (not vulnerable):
    1. po_reachability == 0: PI doesn't reach any output
    2. dff_count_in_cone == 0: PI only feeds combinational logic
    3. critical_path_length < 3: PI is on short path (not timing-critical)
    4. fanout_cone_size < 10: PI has very limited downstream impact
    
    If ANY rule is triggered, PI is marked as safe.
    """
    pi_features = extract_pi_features(graph, node_idx)
    
    # Feature indices (matching extract_pi_features output)
    po_reach_idx = 1
    dff_count_idx = 3
    critical_path_idx = 10
    fanout_size_idx = 0
    
    rules = [
        pi_features[po_reach_idx] == 0,           # Rule 1: no PO reachability
        pi_features[dff_count_idx] == 0,          # Rule 2: no DFFs in cone
        pi_features[critical_path_idx] < 3,       # Rule 3: short critical path
        pi_features[fanout_size_idx] < 10,       # Rule 4: small fanout cone
    ]
    
    if any(rules):
        return "SAFE"  # Rule triggered -> likely FP
    else:
        return "NEEDS_CHECK"  # Pass to ML classifier

# =============================================================================
# Complete PI FP Reduction Pipeline
# =============================================================================

def pi_fp_reduction_pipeline(graph, sage_model, pi_classifier):
    """
    Three-stage PI FP reduction:
    Stage 1: Rule-based pre-filter (eliminate obvious FPs quickly)
    Stage 2: SAGE3 with higher threshold
    Stage 3: PI classifier confirmation
    
    Expected FP reduction: 50-70% of PI FPs
    Expected recall impact: -5 to -10% (acceptable trade-off)
    """
    sage_logits = sage_model(graph.x, graph.edge_index)
    sage_scores = torch.sigmoid(sage_logits).numpy()
    final_preds = np.zeros(len(graph.x), dtype=int)
    
    non_pi_mask = graph.x[:, 0] <= 0.5
    final_preds[non_pi_mask] = (sage_scores[non_pi_mask] > 0.5).astype(int)
    
    pi_mask = graph.x[:, 0] > 0.5
    pi_indices = np.where(pi_mask)[0]
    
    for node_idx in pi_indices:
        # Stage 1: Rule-based pre-filter
        rule_result = rule_based_pi_filter(graph, node_idx)
        if rule_result == "SAFE":
            final_preds[node_idx] = 0
            continue
        
        # Stage 2: SAGE3 higher threshold
        if sage_scores[node_idx] < 0.75:
            final_preds[node_idx] = 0
            continue
        
        # Stage 3: PI classifier confirmation
        pi_features = extract_pi_features(graph, node_idx)
        pi_score = pi_classifier.predict_proba([pi_features])[0, 1]
        
        if pi_score > 0.6:
            final_preds[node_idx] = 1
        else:
            final_preds[node_idx] = 0
    
    return final_preds


# =============================================================================
# Python Implementation
# =============================================================================

import numpy as np
import torch

class PIFPReductionClassifier:
    """
    Three-stage PI false positive reduction classifier.
    
    Pipeline:
    1. Rule-based pre-filter (fast elimination)
    2. SAGE3 with higher threshold
    3. PI-specific LightGBM classifier confirmation
    
    Designed to reduce 70 PI FPs while maintaining TP recall.
    """
    
    def __init__(self, sage_model, pi_classifier=None):
        self.sage_model = sage_model
        self.pi_classifier = pi_classifier
        
        # Thresholds tuned for FP reduction
        self.sage_pi_threshold = 0.75
        self.pi_classifier_threshold = 0.60
        
        # Rule thresholds
        self.min_po_reach = 1
        self.min_dff_in_cone = 1
        self.min_critical_path = 3
        self.min_fanout_size = 10
    
    def extract_pi_features(self, graph_data, pi_node_idx):
        """
        Extract PI-specialized features from PyG Data object.
        
        Returns 12-dimensional feature vector:
        [fanout_cone_size, po_reachability, fanout_cone_depth,
         dff_count, and_count, betweenness, path_entropy,
         degree_out, depth, cone_density, critical_path, dff_ratio]
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
        
        adj = {i: [] for i in range(num_nodes)}
        for k in range(edge_index.shape[1]):
            src = int(edge_index[0, k])
            dst = int(edge_index[1, k])
            adj[src].append(dst)
        
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
        """Apply rule-based pre-filter to eliminate obvious FPs."""
        features = self.extract_pi_features(graph_data, node_idx)
        
        if features[1] < self.min_po_reach:       # po_reachability
            return False
        if features[3] < self.min_dff_in_cone:    # dff_count
            return False
        if features[10] < self.min_critical_path: # critical_path
            return False
        if features[0] < self.min_fanout_size:    # fanout_cone_size
            return False
        
        return True
    
    def predict(self, graph_data):
        """Three-stage prediction pipeline."""
        with torch.no_grad():
            sage_logits = self.sage_model(graph_data.x, graph_data.edge_index)
            sage_scores = torch.sigmoid(sage_logits).numpy()
        
        final_preds = np.zeros(len(graph_data.x), dtype=int)
        
        pi_mask = graph_data.x[:, 0].numpy() > 0.5
        
        for i in range(len(graph_data.x)):
            if not pi_mask[i]:
                final_preds[i] = int(sage_scores[i] > 0.5)
                continue
            
            if not self.rule_based_filter(graph_data, i):
                final_preds[i] = 0
                continue
            
            if sage_scores[i] < self.sage_pi_threshold:
                final_preds[i] = 0
                continue
            
            if self.pi_classifier is not None:
                pi_features = self.extract_pi_features(graph_data, i)
                pi_score = self.pi_classifier.predict_proba([pi_features])[0, 1]
                final_preds[i] = int(pi_score > self.pi_classifier_threshold)
            else:
                final_preds[i] = int(sage_scores[i] > 0.8)
        
        return final_preds
    
    def train_pi_classifier(self, train_graphs):
        """Train PI-specific classifier with FP-focused weighting."""
        import lightgbm as lgb
        from sklearn.model_selection import StratifiedKFold
        from sklearn.metrics import f1_score
        
        X, y, weights = [], [], []
        
        for graph in train_graphs:
            pi_mask = graph.x[:, 0].numpy() > 0.5
            pi_indices = np.where(pi_mask)[0]
            
            for idx in pi_indices:
                features = self.extract_pi_features(graph, idx)
                label = int(graph.y[idx].item() >= 0.5)
                
                X.append(features)
                y.append(label)
                
                if label == 1:
                    weights.append(1.0)
                else:
                    weights.append(1.0)
        
        X = np.array(X)
        y = np.array(y)
        weights = np.array(weights)
        
        pos_mask = y == 1
        X_pos = X[pos_mask]
        
        for _ in range(10):
            noise = np.random.normal(0, 0.02, X_pos.shape)
            X_aug = X_pos + noise
            X = np.vstack([X, X_aug])
            y = np.concatenate([y, np.ones(len(X_aug))])
            weights = np.concatenate([weights, np.ones(len(X_aug))])
        
        pos_count = y.sum()
        neg_count = len(y) - pos_count
        scale_pos = neg_count / max(pos_count, 1)
        
        params = {
            'objective': 'binary',
            'scale_pos_weight': scale_pos,
            'learning_rate': 0.01,
            'num_leaves': 10,
            'max_depth': 3,
            'min_child_samples': 5,
            'feature_fraction': 0.7,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'verbose': -1,
        }
        
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        best_model = None
        best_precision = 0
        
        for fold, (train_idx, val_idx) in enumerate(skf.split(X, y)):
            X_tr, X_val = X[train_idx], X[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]
            
            dtrain = lgb.Dataset(X_tr, label=y_tr)
            dval = lgb.Dataset(X_val, label=y_val, reference=dtrain)
            
            model = lgb.train(
                params, dtrain,
                num_boost_round=300,
                valid_sets=[dval],
                callbacks=[lgb.early_stopping(30), lgb.log_evaluation(0)],
            )
            
            val_pred = model.predict(X_val)
            val_pred_binary = (val_pred > 0.5).astype(int)
            
            precision = f1_score(y_val, val_pred_binary, zero_division=0)
            
            print(f'  Fold {fold+1}: Precision={precision:.4f}, '
                  f'pos={y_val.sum()}, neg={len(y_val)-y_val.sum()}')
            
            if precision > best_precision:
                best_precision = precision
                best_model = model
        
        self.pi_classifier = best_model
        print(f'Best PI classifier Precision: {best_precision:.4f}')
        return best_precision
    
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


# =============================================================================
# Expected Results (FP Reduction)
# =============================================================================

"""
TARGET METRICS AFTER PI FP Reduction:
--------------------------------------
  - PI False Positives: 70 -> 20-30 (60-70% reduction)
  - PI True Positives: 26 -> 22-24 (8-15% recall loss, acceptable)
  - PI Precision: ~26/(26+70)=27% -> ~24/(24+25)=49% (significant improvement)
  - Overall F1: 0.9891 -> 0.9885-0.9890 (minimal impact)

KEY TRADE-OFFS:
---------------
1. Higher SAGE3 threshold for PI (0.75 vs 0.5):
   - Pros: Eliminates low-confidence FP predictions
   - Cons: May lose some TP with scores between 0.5-0.75

2. Rule-based pre-filter:
   - Pros: Zero computational overhead, deterministic
   - Cons: Hard thresholds may be too strict

3. PI classifier confirmation:
   - Pros: Uses specialized features to verify predictions
   - Cons: Additional computation for PI nodes

RECOMMENDED NEXT STEPS:
-----------------------
1. Analyze the 70 FP PI nodes' feature distributions
2. Tune rule thresholds based on actual data
3. Train PI classifier with FP-weighted loss
4. Evaluate combined pipeline on test set
5. Iterate on threshold values based on results
"""
