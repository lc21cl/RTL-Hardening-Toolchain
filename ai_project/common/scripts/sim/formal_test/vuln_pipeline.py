#!/usr/bin/env python3
"""
vuln_pipeline.py — 统一 CLI 工具 (graph_pipeline + gnn_inference)

合并 AIG/BLIF 管线转换和 GNN 脆弱性推理为一体，提供统一的命令行入口。

用法:
    # 推理子命令
    python vuln_pipeline.py infer --blif design.blif
    python vuln_pipeline.py infer --aig design.aig --model data/models/SAGE2-Lite-64.pth
    python vuln_pipeline.py infer --batch blifs/ --output results.json

    # 转换子命令
    python vuln_pipeline.py convert --blif design.blif --stats
    python vuln_pipeline.py convert --batch blifs/ --output data/training_data.pt

    # 基准测试
    python vuln_pipeline.py benchmark --blif design.blif

    # 列举可用模型
    python vuln_pipeline.py list-models

    # 端到端演示
    python vuln_pipeline.py demo
"""

import os
import sys
import json
import time
import argparse
import glob as glob_mod

# ── Lazy imports ──────────────────────────────────────────────────────────
# Avoid import errors if optional dependencies are missing

def _import_gnn():
    from gnn_inference import GNNInference, GraphConverter, SAGE3, SAGE2Lite, MODEL_REGISTRY
    return GNNInference, GraphConverter, SAGE3, SAGE2Lite, MODEL_REGISTRY

def _import_pipeline():
    from graph_pipeline import GraphPipeline
    return GraphPipeline

def _import_config():
    try:
        from config import config
        return config
    except ImportError:
        return None

def _import_logger():
    try:
        from logger import logger
        return logger
    except ImportError:
        return None


# ============================================================================
# Model Registry (list-models subcommand)
# ============================================================================

def list_available_models():
    """Scan the models directory and list all available models."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_dir = os.path.join(script_dir, 'data', 'models')

    if not os.path.isdir(model_dir):
        print(f"[ERROR] Models directory not found: {model_dir}")
        return

    model_files = sorted([
        f for f in os.listdir(model_dir)
        if f.endswith('.pt') or f.endswith('.pth')
    ])

    if not model_files:
        print(f"  No models found in {model_dir}")
        return

    print(f"\n{'=' * 68}")
    print(f"  Available Models")
    print(f"{'=' * 68}")
    print(f"  {'Model':35s} {'Type':12s} {'Params':>10s} {'Detected':>8s}")
    print(f"  {'-'*35} {'-'*12} {'-'*10} {'-'*8}")

    GNNInference, _, _, _, reg = _import_gnn()

    for fname in model_files:
        fpath = os.path.join(model_dir, fname)
        try:
            import torch
            ckpt = torch.load(fpath, map_location='cpu', weights_only=True)
            if isinstance(ckpt, dict):
                keys = set(ckpt.keys())
                arch = 'SAGE3'
                for name, cfg in reg.items():
                    if cfg['keys'](keys):
                        arch = name
                        break
                n = sum(p.numel() for p in ckpt.values()
                        if hasattr(p, 'numel'))
                in_ch = '?'
                for k in ['conv1.lin_l.weight', 'conv1.lin.weight']:
                    if k in ckpt:
                        in_ch = str(ckpt[k].shape[1])
                        break
                detected = 'auto' if arch else '?'
                print(f"  {fname:35s} {arch:12s} {n:>10,d} {detected:>8s}")
            else:
                print(f"  {fname:35s} {'OTHER':12s} {'N/A':>10s} {'?':>8s}")
        except Exception as e:
            print(f"  {fname:35s} {'ERROR':12s} {'':>10s} {'?':>8s}")
    print(f"{'=' * 68}")


# ============================================================================
# Infer subcommand
# ============================================================================

def cmd_infer(args):
    """Run GNN vulnerability inference."""
    GNNInference, _, _, _, _ = _import_gnn()

    engine = GNNInference(
        model_path=args.model,
        device=args.device,
        threshold=args.threshold,
    )

    model_type = args.model_type if args.model_type != 'auto' else None
    if not engine.load_model(args.model, model_type=model_type):
        sys.exit(1)

    print(f"\n  Model: {os.path.basename(engine.model_info['path'])}")
    print(f"  Architecture: {engine.model_info['architecture']}")
    print(f"  Parameters: {engine.model_info['num_params']:,}")
    print(f"  Input channels: {engine.model_info['in_channels']}")

    if args.blif or args.aig or args.input:
        file_path = args.input or args.blif or args.aig
        if not os.path.exists(file_path):
            print(f"[ERROR] File not found: {file_path}")
            sys.exit(1)

        print(f"\n[Inference] {file_path}")
        t0 = time.time()
        result = engine.infer_from_file(file_path)
        t_elapsed = time.time() - t0

        engine.print_result_summary(result)
        print(f"\n  Inference time: {t_elapsed*1000:.1f} ms")

        if args.output:
            engine.export_results(result, args.output)
            print(f"\n  Results -> {args.output}")

    elif args.batch:
        if not os.path.isdir(args.batch):
            print(f"[ERROR] Directory not found: {args.batch}")
            sys.exit(1)

        supported = ['.blif', '.aig']
        file_list = sorted([
            os.path.join(args.batch, f) for f in os.listdir(args.batch)
            if os.path.splitext(f)[1].lower() in supported
        ])

        if not file_list:
            print(f"[ERROR] No .blif/.aig files found in {args.batch}")
            sys.exit(1)

        print(f"\n[Batch] Running inference on {len(file_list)} files...")
        t0 = time.time()
        results = engine.batch_infer(file_list)
        t_elapsed = time.time() - t0

        successful = [r for r in results if 'error' not in r]
        total_vuln = sum(r['num_vulnerable'] for r in successful)
        total_nodes = sum(r['num_nodes'] for r in successful)

        print(f"\n  Batch Summary:")
        print(f"    Total files:      {len(file_list)}")
        print(f"    Successful:       {len(successful)}")
        print(f"    Total nodes:      {total_vuln}")
        print(f"    Total vulnerable: {total_vuln}")
        print(f"    Time:             {t_elapsed:.2f}s")

        output_path = args.output or os.path.join(
            args.batch, 'batch_inference_results.json')
        engine.export_results(results, output_path)
        print(f"\n  Results -> {output_path}")

    else:
        print("[ERROR] Specify --blif, --aig, --input, or --batch")
        sys.exit(1)


# ============================================================================
# Convert subcommand
# ============================================================================

def cmd_convert(args):
    """Convert BLIF/AIG files to PyG Data objects."""
    GraphPipeline = _import_pipeline()

    pipeline = GraphPipeline(
        target_features=args.target_features,
        verbose=not args.quiet,
    )

    if args.blif:
        data = pipeline.from_blif(
            args.blif,
            generate_labels=args.labels,
            label_mode=args.label_mode,
        )
        if args.stats:
            pipeline.print_stats(data)
        if args.output:
            import torch
            torch.save(data, args.output)
            print(f"\n  Saved to: {args.output}")

    elif args.aig:
        data = pipeline.from_aig(args.aig, map_path=args.map)
        if args.stats:
            pipeline.print_stats(data)
        if args.output:
            import torch
            torch.save(data, args.output)
            print(f"\n  Saved to: {args.output}")

    elif args.batch:
        file_type = 'all' if args.all_types else 'blif'
        samples = pipeline.batch_convert(
            args.batch,
            file_type=file_type,
            output_file=args.output,
            generate_labels=args.labels,
            label_mode=args.label_mode,
        )
        print(f"\n  Converted {len(samples)} samples")

    else:
        print("[ERROR] Specify --blif, --aig, or --batch")
        sys.exit(1)


# ============================================================================
# Benchmark subcommand
# ============================================================================

def cmd_benchmark(args):
    """Benchmark inference latency."""
    GNNInference, _, _, _, _ = _import_gnn()

    engine = GNNInference(
        model_path=args.model,
        device=args.device,
        threshold=args.threshold,
    )

    model_type = args.model_type if args.model_type != 'auto' else None
    if not engine.load_model(args.model, model_type=model_type):
        sys.exit(1)

    file_path = args.blif or args.input
    if not file_path or not os.path.exists(file_path):
        print("[ERROR] Specify --blif or --input with an existing file")
        sys.exit(1)

    num_runs = args.runs or 10
    print(f"\n[Benchmark] Model: {engine.model_info['architecture']}")
    print(f"[Benchmark] File: {file_path}")
    print(f"[Benchmark] Runs: {num_runs}")

    try:
        import numpy as np
    except ImportError:
        np = None

    # Prepare data
    from gnn_inference import GraphConverter
    converter = GraphConverter()
    data = converter.convert(file_path)
    x = data.x.to(engine.device)
    edge_index = data.edge_index.to(engine.device)

    # Warm-up
    with torch.no_grad():
        for _ in range(3):
            _ = engine.model(x, edge_index)

    # Benchmark
    latencies = []
    import torch
    with torch.no_grad():
        for i in range(num_runs):
            t0 = time.perf_counter()
            logits = engine.model(x, edge_index)
            _ = torch.sigmoid(logits)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000)  # ms
            print(f"  Run {i+1:3d}/{num_runs}: {latencies[-1]:.3f} ms")

    stats = {
        'file': file_path,
        'model': engine.model_info['architecture'],
        'num_nodes': data.num_nodes,
        'num_edges': data.edge_index.shape[1],
        'num_runs': num_runs,
        'mean_latency_ms': float(np.mean(latencies)) if np else sum(latencies)/len(latencies),
        'min_latency_ms': float(np.min(latencies)),
        'max_latency_ms': float(np.max(latencies)),
        'std_latency_ms': float(np.std(latencies)) if np else 0.0,
    }

    print(f"\n  Results ({num_runs} runs):")
    print(f"    Mean:   {stats['mean_latency_ms']:.3f} ms")
    print(f"    Min:    {stats['min_latency_ms']:.3f} ms")
    print(f"    Max:    {stats['max_latency_ms']:.3f} ms")
    print(f"    Std:    {stats['std_latency_ms']:.3f} ms")

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(stats, f, indent=2)
        print(f"\n  Results -> {args.output}")


# ============================================================================
# Demo subcommand
# ============================================================================

def cmd_demo(args):
    """Run end-to-end demo."""
    from gnn_inference import run_demo
    run_demo()


# ============================================================================
# CLI Parser
# ============================================================================

def build_parser():
    """Build the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description="vuln_pipeline — Unified GNN Vulnerability Pipeline CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Inference
  python vuln_pipeline.py infer --blif blifs/design.blif
  python vuln_pipeline.py infer --batch blifs/ --model data/models/SAGE2-Lite-64.pth

  # Convert (graph pipeline)
  python vuln_pipeline.py convert --blif blifs/design.blif --stats
  python vuln_pipeline.py convert --batch blifs/ --output data/dataset.pt

  # Benchmark
  python vuln_pipeline.py benchmark --blif blifs/design.blif --runs 50

  # List models
  python vuln_pipeline.py list-models

  # Demo
  python vuln_pipeline.py demo
        """,
    )

    subparsers = parser.add_subparsers(
        dest='command', help='Available subcommands')

    # ── infer ──────────────────────────────────────────────────────────
    p_infer = subparsers.add_parser(
        'infer', help='Run GNN vulnerability inference on design files')
    p_infer.add_argument('--blif', type=str, default=None,
                          help='Path to single BLIF file')
    p_infer.add_argument('--aig', type=str, default=None,
                          help='Path to single AIG file')
    p_infer.add_argument('--input', type=str, default=None,
                          help='Path to BLIF or AIG file (auto-detect)')
    p_infer.add_argument('--batch', type=str, default=None,
                          help='Directory of BLIF/AIG files for batch inference')
    p_infer.add_argument('--model', type=str, default=None,
                          help='Path to trained model .pt file')
    p_infer.add_argument('--model-type', type=str, default='auto',
                          choices=['SAGE3', 'SAGE2Lite', 'auto'],
                          help='Model architecture (auto = detect from checkpoint)')
    p_infer.add_argument('--threshold', type=float, default=0.05,
                          help='Vulnerability classification threshold')
    p_infer.add_argument('--device', type=str, default='cpu',
                          help='Device (cpu or cuda)')
    p_infer.add_argument('--output', type=str, default=None,
                          help='Path to save results JSON')

    # ── convert ────────────────────────────────────────────────────────
    p_conv = subparsers.add_parser(
        'convert', help='Convert BLIF/AIG files to PyG Data objects')
    p_conv.add_argument('--blif', type=str, default=None,
                         help='Path to single BLIF file')
    p_conv.add_argument('--aig', type=str, default=None,
                         help='Path to single AIG file')
    p_conv.add_argument('--batch', type=str, default=None,
                         help='Directory of design files for batch conversion')
    p_conv.add_argument('--all-types', action='store_true',
                         help='In batch mode, include both .blif and .aig files')
    p_conv.add_argument('--map', type=str, default=None,
                         help='Port mapping file for AIG')
    p_conv.add_argument('--target-features', type=int, default=12,
                         help='Target feature dimension (default: 12)')
    p_conv.add_argument('--labels', action='store_true',
                         help='Generate fault injection labels')
    p_conv.add_argument('--label-mode', type=str, default='prob_decay',
                         help='Label generation mode (prob_decay, etc.)')
    p_conv.add_argument('--stats', action='store_true',
                         help='Print graph statistics')
    p_conv.add_argument('--quiet', action='store_true',
                         help='Suppress verbose output')
    p_conv.add_argument('--output', type=str, default=None,
                         help='Output path for .pt file')

    # ── benchmark ──────────────────────────────────────────────────────
    p_bench = subparsers.add_parser(
        'benchmark', help='Benchmark GNN inference latency')
    p_bench.add_argument('--blif', type=str, default=None,
                          help='Path to BLIF file for benchmarking')
    p_bench.add_argument('--input', type=str, default=None,
                          help='Path to design file for benchmarking')
    p_bench.add_argument('--model', type=str, default=None,
                          help='Path to trained model .pt file')
    p_bench.add_argument('--model-type', type=str, default='auto',
                          choices=['SAGE3', 'SAGE2Lite', 'auto'],
                          help='Model architecture')
    p_bench.add_argument('--threshold', type=float, default=0.05,
                          help='Classification threshold')
    p_bench.add_argument('--device', type=str, default='cpu',
                          help='Device (cpu or cuda)')
    p_bench.add_argument('--runs', type=int, default=10,
                          help='Number of benchmark runs')
    p_bench.add_argument('--output', type=str, default=None,
                          help='Path to save benchmark results JSON')

    # ── list-models ────────────────────────────────────────────────────
    subparsers.add_parser(
        'list-models', help='List all available trained models')

    # ── demo ───────────────────────────────────────────────────────────
    subparsers.add_parser(
        'demo', help='Run end-to-end demo (inference + hardening integration)')

    return parser


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Route to subcommand handler
    handlers = {
        'infer': cmd_infer,
        'convert': cmd_convert,
        'benchmark': cmd_benchmark,
        'list-models': lambda a: list_available_models(),
        'demo': cmd_demo,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
