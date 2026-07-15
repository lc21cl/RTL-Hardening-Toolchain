#!/usr/bin/env python3
"""
Generate synthetic training data from BLIF designs for GNN-based fault analysis.

Scans BLIF files from test_mock_data, generates fault-injection scenarios,
creates graph-structure variants, and saves a train/val/test split.
"""

import os
import sys
import glob
import math
import random
from collections import Counter

import torch

# Import the BLIF-to-PyG converter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blif_to_pyg import BlifToAIG, BlifParser

# ── Configuration ─────────────────────────────────────────────────────────────

# Paths (relative to this script's directory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..', '..'))
MOCK_DATA_DIR = os.path.join(PROJECT_ROOT, 'common', 'scripts', 'test_mock_data')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'data')

TRAIN_RATIO = 0.8
VAL_RATIO = 0.1
TEST_RATIO = 0.1
NUM_VARIANTS = 16       # variants per design
SCENARIOS_PER_VARIANT = 10  # fault-injection scenarios per variant


# ── Graph Variants ────────────────────────────────────────────────────────────


def create_variants(converter, num_variants=NUM_VARIANTS):
    """
    Create variants of a circuit graph by:
      1. Slightly perturbing node features (Gaussian noise).
      2. Using different fault-injection probabilities.
      3. Optionally dropping a small fraction of edges.

    Each variant is a (Data, fault_prob) pair.
    """
    base_data = converter.build_pyg_data()
    variants = []

    fault_probs = [0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20]

    for v_idx in range(num_variants):
        data = base_data.clone()

        # ── Perturb node features ──
        # Add small Gaussian noise (std = 0.02) to non-binary features
        noise = torch.randn_like(data.x) * 0.02
        # Don't perturb the one-hot binary features (columns 0-3, 7)
        for col in (4, 5, 6):
            data.x[:, col] = (data.x[:, col] + noise[:, col]).clamp(0.0, 1.0)

        # ── Optionally drop a tiny fraction of edges for diversity ──
        if v_idx >= 2 and data.edge_index.size(1) > 5:
            num_edges = data.edge_index.size(1)
            drop_count = max(1, int(num_edges * 0.03))
            keep_mask = torch.ones(num_edges, dtype=torch.bool)
            drop_indices = random.sample(range(num_edges), drop_count)
            keep_mask[drop_indices] = False
            data.edge_index = data.edge_index[:, keep_mask]
            data.edge_attr = data.edge_attr[keep_mask]

        fp = fault_probs[v_idx % len(fault_probs)]
        variants.append((data, fp))

    return variants


def generate_samples(converter, data, fault_prob, num_scenarios, base_seed):
    """Generate samples with probabilistic decay fault labels.

    Uses label_mode='prob_decay' for continuous vulnerability scores.
    Labels are computed based on structural path weights from node to POs,
    with decay based on fanout and distance. This avoids data leakage from
    rev_depth features and produces non-trivial training targets.
    """
    label = converter.generate_fault_labels(
        deterministic=True,
        label_mode='prob_decay',
        fault_targets=(converter.PI, converter.AND, converter.DFF)
    )
    samples = []
    for s_idx in range(num_scenarios):
        sample = data.clone()
        sample.y = label.clone()
        samples.append(sample)
    return samples


# ── Main Pipeline ─────────────────────────────────────────────────────────────


def main():
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Discover BLIF files
    blif_files = sorted(glob.glob(os.path.join(MOCK_DATA_DIR, '*.blif')))
    if not blif_files:
        print(f"Error: No .blif files found in {MOCK_DATA_DIR}")
        sys.exit(1)

    print(f"Found {len(blif_files)} BLIF file(s):")
    for bf in blif_files:
        print(f"  {os.path.basename(bf)}")

    all_samples = []
    global_sample_idx = 0

    for blif_path in blif_files:
        blif_name = os.path.splitext(os.path.basename(blif_path))[0]
        print(f"\n{'=' * 60}")
        print(f"Processing: {blif_name}")

        # Parse and build the graph
        converter = BlifToAIG(blif_path)
        print(f"  {converter.summary()}")

        # Create variants
        variants = create_variants(converter, NUM_VARIANTS)
        print(f"  Created {len(variants)} graph variants")

        for v_idx, (data, fault_prob) in enumerate(variants):
            # Update converter's fault probability for this variant
            scenarios = generate_samples(
                converter, data, fault_prob,
                SCENARIOS_PER_VARIANT, global_sample_idx
            )
            for sample in scenarios:
                all_samples.append(sample)

            v_faulty = sum(l.y.sum().item() for l in scenarios)
            v_total = sum(l.y.size(0) for l in scenarios)
            print(f"    Variant {v_idx + 1} (fp={fault_prob}): "
                  f"{len(scenarios)} scenarios, "
                  f"avg {v_faulty / len(scenarios):.1f} vulnerable nodes")

        global_sample_idx += 1

    # ── Train / Val / Test Split ──
    n_total = len(all_samples)
    random.shuffle(all_samples)

    n_train = int(n_total * TRAIN_RATIO)
    n_val = int(n_total * VAL_RATIO)
    n_test = n_total - n_train - n_val

    train_data = all_samples[:n_train]
    val_data = all_samples[n_train:n_train + n_val]
    test_data = all_samples[n_train + n_val:]

    split = {
        'train': train_data,
        'val': val_data,
        'test': test_data,
    }

    # ── Save ──
    output_path = os.path.join(OUTPUT_DIR, 'training_data.pt')
    torch.save(split, output_path)
    print(f"\n{'=' * 60}")
    print(f"Saved to: {output_path}")

    # ── Statistics ──
    _report_statistics(split, os.path.basename(output_path))


def _report_statistics(split, filename):
    """Print detailed dataset statistics."""

    def _stats(samples, name):
        if not samples:
            print(f"  {name}: 0 samples")
            return
        n_samples = len(samples)
        n_nodes_total = 0
        n_edges_total = 0
        n_faulty_total = 0
        node_types_total = Counter()

        for data in samples:
            n_nodes_total += data.num_nodes
            n_edges_total += data.edge_index.size(1)
            n_faulty_total += data.y.sum().item()
            if hasattr(data, 'node_type'):
                for nt in data.node_type.tolist():
                    node_types_total[nt] += 1

        avg_nodes = n_nodes_total / n_samples
        avg_edges = n_edges_total / n_samples
        avg_faulty = n_faulty_total / n_samples
        fault_density = n_faulty_total / n_nodes_total if n_nodes_total else 0.0

        type_labels = {0: 'PI', 1: 'PO', 2: 'AND', 3: 'DFF', 4: 'CONST0', 5: 'CONST1'}
        type_desc = ', '.join(
            f"{type_labels.get(k, str(k))}={v // n_samples}"
            for k, v in sorted(node_types_total.items())
        )

        print(f"  {name}: {n_samples} samples | "
              f"avg {avg_nodes:.0f} nodes, {avg_edges:.0f} edges | "
              f"avg {avg_faulty:.1f} faulty | "
              f"density {fault_density:.3f}")
        print(f"    Node types (avg/sample): {type_desc}")

    print(f"\n{'=' * 60}")
    print(f"Dataset: {filename}")
    print(f"{'=' * 60}")
    _stats(split.get('train', []), 'Train')
    _stats(split.get('val', []), 'Val')
    _stats(split.get('test', []), 'Test')

    total = sum(len(v) for v in split.values())
    print(f"\n  Total: {total} samples")
    print(f"  Split: {[f'{k}={len(v)}' for k, v in split.items()]}")
    print(f"{'=' * 60}")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    main()
