#!/usr/bin/env python3
"""
model_compression.py — GraphSAGE 模型压缩与优化工具

提供模型量化、剪枝、推理优化和性能基准测试功能，
用于减小 GraphSAGE 模型体积并加速推理部署。

支持:
    - 动态量化（int8 / float16）
    - 结构化剪枝（按 L1 范数去除不重要的权重通道）
    - 推理优化（融合 BN、关闭梯度、TorchScript 图优化）
    - 性能基准测试（推理时间、内存占用、模型大小）
    - 压缩模型保存/加载
    - 压缩前后对比报告

用法:
    # Python API
    from model_compression import ModelCompressor
    compressor = ModelCompressor(device='cpu')

    # 量化
    quantized = compressor.quantize_model(model, precision='int8')

    # 剪枝
    pruned = compressor.prune_model(model, amount=0.3)

    # 推理优化
    optimized = compressor.optimize_for_inference(model)

    # 基准测试
    stats = compressor.benchmark_model(
        model, input_shape=(100, 12), num_runs=100)

    # 对比并生成报告
    report = compressor.compare_models(original_model, compressed_model)
    print(compressor.generate_report(report))

    # 保存/加载
    compressor.save_compressed(model, 'compressed_model.pt')
    model = compressor.load_compressed('compressed_model.pt',
                                        model_cls=VulnerabilityPredictor)

    # 一键压缩管线
    from model_compression import full_compression_pipeline
    compressed, report = full_compression_pipeline(
        model, quantize='int8', prune_amount=0.3)
"""

import os
import time
from typing import Dict, List, Tuple, Optional, Union

import numpy as np

import torch
import torch.nn as nn
import torch.nn.utils.prune as prune

# Logger setup
try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ============================================================================
# 1. Model Compressor
# ============================================================================


class ModelCompressor:
    """GraphSAGE 模型压缩与优化工具类。

    集成量化、剪枝、推理优化和性能基准测试，
    生成完整的压缩报告用于部署决策。

    典型流程:
        compressor = ModelCompressor()
        quantized = compressor.quantize_model(model, 'int8')
        pruned = compressor.prune_model(model, 0.3)
        report = compressor.compare_models(model, quantized)
        print(compressor.generate_report(report))
    """

    def __init__(self, device: str = 'cpu'):
        """初始化压缩器。

        Args:
            device: 目标设备 ('cpu' 或 'cuda')
        """
        self.device = torch.device(device)
        self._report_history: List[Dict] = []

    # ── 量化 ──────────────────────────────────────────────────────────────

    def quantize_model(self, model: nn.Module,
                       precision: str = 'int8') -> nn.Module:
        """动态量化模型。

        使用 torch.quantization.quantize_dynamic 进行动态量化，
        仅量化 Linear 层权重（GraphSAGE 的 SAGEConv 内部也含 Linear）。

        Args:
            model: 待量化的模型
            precision: 量化精度 ('int8' 或 'float16')

        Returns:
            量化后的模型副本
        """
        model = model.to(self.device).eval()
        precision = precision.lower()

        if precision not in ('int8', 'float16'):
            raise ValueError(f"Unsupported precision: {precision} "
                             f"(use 'int8' or 'float16')")

        qconfig_spec = {nn.Linear}
        q_dtype = torch.qint8 if precision == 'int8' else torch.float16

        try:
            quantized = torch.quantization.quantize_dynamic(
                model,
                qconfig_spec,
                dtype=q_dtype,
            )
        except Exception as e:
            logger.warning(f"[Quantize] {precision} quantization failed: {e}")
            print(f"  [WARN] Quantization ({precision}) failed, "
                  f"returning original model: {e}")
            return model

        logger.info(f"[Quantize] {precision} quantization applied "
                    f"to Linear layers")
        return quantized

    # ── 剪枝 ──────────────────────────────────────────────────────────────

    def prune_model(self, model: nn.Module,
                    amount: float = 0.3) -> nn.Module:
        """结构化剪枝：去除不重要的权重通道。

        对模型中所有 Linear 层按 L1 范数进行结构化剪枝（dim=0），
        整行移除不重要的输出通道，剪枝比例由 amount 指定。
        剪枝后固化掩码，将零值永久写入权重。

        Args:
            model: 待剪枝的模型
            amount: 剪枝比例 (0.0 ~ 1.0)

        Returns:
            剪枝后的模型（原地修改并返回）
        """
        if not 0.0 <= amount < 1.0:
            raise ValueError(f"amount must be in [0, 1), got {amount}")

        if amount == 0.0:
            logger.info(f"[Prune] amount=0, skipping pruning")
            return model

        model = model.to(self.device).eval()
        pruned_modules = 0
        total_zeroed = 0

        for name, module in model.named_modules():
            if isinstance(module, nn.Linear):
                # 结构化剪枝：按 L1 范数移除整行输出通道 (dim=0)
                prune.ln_structured(
                    module, name='weight', amount=amount, n=1, dim=0
                )
                pruned_modules += 1

                # 统计被剪掉的权重数
                mask = module.weight_mask
                zeroed = int((mask == 0).sum().item())
                total_zeroed += zeroed
                sparsity = (mask == 0).float().mean().item()
                logger.debug(f"[Prune] {name}: sparsity={sparsity:.2%} "
                             f"({zeroed} weights zeroed)")

        # 固化剪枝（移除 mask，将零值永久写入 weight）
        for name, module in model.named_modules():
            if isinstance(module, nn.Linear) and hasattr(module, 'weight_mask'):
                prune.remove(module, 'weight')

        logger.info(f"[Prune] Structured-pruned {pruned_modules} Linear "
                    f"layers (amount={amount:.2f}), "
                    f"zeroed ~{total_zeroed} weights")
        return model

    # ── 推理优化 ──────────────────────────────────────────────────────────

    def optimize_for_inference(self, model: nn.Module) -> nn.Module:
        """推理优化：融合 BN、关闭梯度、TorchScript 图优化。

        优化步骤:
            1. 切换到 eval 模式
            2. 关闭所有参数梯度（节省内存）
            3. 融合 BatchNorm 层（若存在）
            4. 尝试 TorchScript 编译（兼容 Python 3.14 异常时回退）

        Args:
            model: 待优化的模型

        Returns:
            优化后的模型
        """
        model = model.to(self.device)
        model.eval()

        # 1. 关闭梯度
        for param in model.parameters():
            param.requires_grad_(False)

        # 2. 融合 BatchNorm（如有）
        model = self._fuse_modules(model)

        # 3. TorchScript 图优化（注意 Python 3.14 兼容性）
        model = self._try_script(model)

        logger.info(f"[Optimize] Inference optimization applied "
                    f"(eval + no_grad + BN-fuse + script)")
        return model

    @staticmethod
    def _fuse_modules(model: nn.Module) -> nn.Module:
        """融合 BatchNorm 层到前序卷积/线性层。"""
        try:
            fusion_pairs = []
            modules = list(model.named_modules())

            for i, (name, module) in enumerate(modules):
                if isinstance(module, (nn.BatchNorm1d, nn.BatchNorm2d)):
                    if i > 0:
                        prev_name, prev_mod = modules[i - 1]
                        if isinstance(prev_mod,
                                      (nn.Linear, nn.Conv1d, nn.Conv2d)):
                            fusion_pairs.append([prev_name, name])

            if fusion_pairs:
                torch.quantization.fuse_modules(
                    model, fusion_pairs, inplace=True)
                logger.debug(f"[Fuse] Fused {len(fusion_pairs)} BN layers")
        except Exception as e:
            logger.debug(f"[Fuse] BN fusion skipped: {e}")

        return model

    @staticmethod
    def _try_script(model: nn.Module) -> nn.Module:
        """尝试 TorchScript 编译，失败则回退到原始模型。

        注意: Python 3.14 中 torch.jit.script 可能存在兼容性问题，
        这里使用 try-except 保证鲁棒性。trace 需要示例输入，
        此处仅尝试 script（无需输入）。
        """
        try:
            with torch.no_grad():
                scripted = torch.jit.script(model)
                logger.debug(f"[Script] torch.jit.script succeeded")
                return scripted
        except Exception as e:
            logger.debug(f"[Script] torch.jit.script failed: {e}")

        # 回退：返回原始 eager 模型
        logger.debug(f"[Script] Skipped TorchScript, using eager model")
        return model

    # ── 基准测试 ──────────────────────────────────────────────────────────

    def benchmark_model(self, model: nn.Module,
                        input_shape: Tuple[int, ...],
                        num_runs: int = 100,
                        edge_index: Optional[torch.Tensor] = None) -> Dict:
        """性能基准测试。

        记录推理时间、内存占用和模型大小。

        Args:
            model: 待测试的模型
            input_shape: 输入特征形状 (num_nodes, feature_dim)
            num_runs: 测试运行次数
            edge_index: 图连接关系 [2, num_edges]。
                        若为 None，使用随机生成的简单图。

        Returns:
            包含性能指标的字典
        """
        model = model.to(self.device).eval()
        if len(input_shape) < 2:
            raise ValueError(f"input_shape must be (num_nodes, feature_dim), "
                             f"got {input_shape}")

        num_nodes, feature_dim = input_shape[0], input_shape[1]

        # 构造输入
        x = torch.randn(num_nodes, feature_dim, device=self.device)

        if edge_index is None:
            # 生成随机简单图（无自环）
            num_edges = max(num_nodes, 10)
            src = torch.randint(0, num_nodes, (num_edges,),
                                device=self.device)
            dst = torch.randint(0, num_nodes, (num_edges,),
                                device=self.device)
            edge_index = torch.stack([src, dst], dim=0)
        else:
            edge_index = edge_index.to(self.device)

        # 预热（保证测量稳定）
        warmup_runs = min(5, num_runs)
        with torch.no_grad():
            for _ in range(warmup_runs):
                try:
                    _ = model(x, edge_index)
                except Exception as e:
                    logger.warning(f"[Bench] Warmup forward failed: {e}")
                    break

        # 基准测试
        latencies = []
        with torch.no_grad():
            for _ in range(num_runs):
                if self.device.type == 'cuda':
                    torch.cuda.synchronize()

                t0 = time.perf_counter()
                try:
                    _ = model(x, edge_index)
                except Exception as e:
                    logger.warning(f"[Bench] Forward failed: {e}")
                    break

                if self.device.type == 'cuda':
                    torch.cuda.synchronize()

                t1 = time.perf_counter()
                latencies.append((t1 - t0) * 1000)  # ms

        # 内存占用
        if self.device.type == 'cuda':
            mem_alloc = torch.cuda.memory_allocated() / 1024 / 1024  # MB
            mem_reserved = torch.cuda.memory_reserved() / 1024 / 1024
        else:
            # CPU: 估算模型参数+缓冲区内存
            mem_alloc = (sum(p.numel() * p.element_size()
                             for p in model.parameters())
                         + sum(b.numel() * b.element_size()
                               for b in model.buffers())) / 1024 / 1024
            mem_reserved = mem_alloc

        stats = {
            'num_nodes': num_nodes,
            'feature_dim': feature_dim,
            'num_edges': int(edge_index.shape[1]),
            'num_runs': num_runs,
            'mean_latency_ms': float(np.mean(latencies)) if latencies else 0.0,
            'min_latency_ms': float(np.min(latencies)) if latencies else 0.0,
            'max_latency_ms': float(np.max(latencies)) if latencies else 0.0,
            'std_latency_ms': float(np.std(latencies)) if latencies else 0.0,
            'p50_latency_ms': float(np.percentile(latencies, 50))
                              if latencies else 0.0,
            'p95_latency_ms': float(np.percentile(latencies, 95))
                              if latencies else 0.0,
            'throughput_nodes_per_sec': (num_nodes /
                                          (np.mean(latencies) / 1000)
                                          if latencies else 0.0),
            'memory_allocated_mb': float(mem_alloc),
            'memory_reserved_mb': float(mem_reserved),
            'model_size_mb': self.get_model_size(model),
            'device': str(self.device),
        }

        logger.info(f"[Bench] {num_runs} runs: "
                    f"mean={stats['mean_latency_ms']:.3f}ms, "
                    f"p95={stats['p95_latency_ms']:.3f}ms, "
                    f"size={stats['model_size_mb']:.3f}MB")
        return stats

    # ── 模型大小 ──────────────────────────────────────────────────────────

    @staticmethod
    def get_model_size(model: nn.Module) -> float:
        """获取模型大小（MB）。

        基于参数和缓冲区的字节数估算实际内存占用。

        Args:
            model: PyTorch 模型

        Returns:
            模型大小（MB）
        """
        total_bytes = 0
        for param in model.parameters():
            total_bytes += param.numel() * param.element_size()
        for buf in model.buffers():
            total_bytes += buf.numel() * buf.element_size()

        return total_bytes / (1024 * 1024)

    # ── 保存/加载 ─────────────────────────────────────────────────────────

    def save_compressed(self, model: nn.Module, path: str,
                        metadata: Optional[Dict] = None) -> str:
        """保存压缩后的模型。

        Args:
            model: 待保存的模型
            path: 保存路径
            metadata: 附加元数据（量化精度、剪枝比例等）

        Returns:
            实际保存路径
        """
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)

        # TorchScript 模型使用 torch.jit.save
        if isinstance(model, torch.jit.ScriptModule):
            torch.jit.save(model, path)
            logger.info(f"[Save] TorchScript model saved to {path}")
            return path

        save_data = {
            'state_dict': model.state_dict(),
            'model_class': model.__class__.__name__,
            'metadata': metadata or {},
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'model_size_mb': self.get_model_size(model),
        }

        torch.save(save_data, path)
        logger.info(f"[Save] Model saved to {path} "
                    f"({save_data['model_size_mb']:.3f} MB)")
        return path

    def load_compressed(self, path: str,
                        model_cls: Optional[type] = None,
                        map_location: Optional[str] = None) -> nn.Module:
        """加载压缩模型。

        Args:
            path: 模型文件路径
            model_cls: 模型类（用于重建模型结构）。
                       若为 None，则尝试 TorchScript 加载或要求后续提供。
            map_location: 加载设备，默认使用 self.device

        Returns:
            加载的模型
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found: {path}")

        loc = str(map_location) if map_location else str(self.device)

        # 优先尝试 TorchScript 加载（无需模型类）
        try:
            model = torch.jit.load(path, map_location=loc)
            model.eval()
            logger.info(f"[Load] TorchScript model loaded from {path}")
            return model
        except Exception:
            pass

        # 普通 checkpoint 加载（需要模型类）
        checkpoint = torch.load(path, map_location=loc, weights_only=False)

        if isinstance(checkpoint, dict) and 'state_dict' in checkpoint:
            if model_cls is None:
                raise ValueError(
                    "model_cls must be provided to rebuild model structure "
                    "(checkpoint contains state_dict only)"
                )
            model = model_cls()
            model.load_state_dict(checkpoint['state_dict'])
            model.to(self.device).eval()
            logger.info(f"[Load] Model loaded from {path} "
                        f"(class={checkpoint.get('model_class', 'N/A')})")
            return model
        else:
            # 直接是 state_dict
            if model_cls is None:
                raise ValueError(
                    "model_cls must be provided (checkpoint is a raw state_dict)"
                )
            model = model_cls()
            model.load_state_dict(checkpoint)
            model.to(self.device).eval()
            logger.info(f"[Load] Model loaded from {path}")
            return model

    # ── 对比报告 ──────────────────────────────────────────────────────────

    def compare_models(self, original: nn.Module,
                       compressed: nn.Module,
                       input_shape: Tuple[int, ...] = (100, 12),
                       num_runs: int = 100) -> Dict:
        """对比原始模型与压缩模型的大小和推理速度。

        Args:
            original: 原始模型
            compressed: 压缩后的模型
            input_shape: 基准测试输入形状
            num_runs: 基准测试运行次数

        Returns:
            对比报告字典
        """
        # 使用相同的 edge_index 保证公平对比
        if len(input_shape) < 2:
            raise ValueError(f"input_shape must be (num_nodes, feature_dim), "
                             f"got {input_shape}")
        num_nodes = input_shape[0]
        num_edges = max(num_nodes, 10)
        src = torch.randint(0, num_nodes, (num_edges,))
        dst = torch.randint(0, num_nodes, (num_edges,))
        edge_index = torch.stack([src, dst], dim=0)

        orig_stats = self.benchmark_model(
            original, input_shape, num_runs, edge_index=edge_index)
        comp_stats = self.benchmark_model(
            compressed, input_shape, num_runs, edge_index=edge_index)

        orig_size = orig_stats['model_size_mb']
        comp_size = comp_stats['model_size_mb']
        orig_lat = orig_stats['mean_latency_ms']
        comp_lat = comp_stats['mean_latency_ms']

        compression_ratio = orig_size / max(comp_size, 1e-8)
        speedup = orig_lat / max(comp_lat, 1e-8)
        size_reduction = (1 - comp_size / max(orig_size, 1e-8)) * 100
        latency_reduction = (1 - comp_lat / max(orig_lat, 1e-8)) * 100

        report = {
            'original': orig_stats,
            'compressed': comp_stats,
            'compression_ratio': float(compression_ratio),
            'speedup': float(speedup),
            'size_reduction_percent': float(size_reduction),
            'latency_reduction_percent': float(latency_reduction),
            'original_size_mb': float(orig_size),
            'compressed_size_mb': float(comp_size),
            'original_latency_ms': float(orig_lat),
            'compressed_latency_ms': float(comp_lat),
            'verdict': self._make_verdict(compression_ratio, speedup),
        }

        self._report_history.append(report)
        logger.info(f"[Compare] size: {orig_size:.3f}→{comp_size:.3f}MB "
                    f"({size_reduction:+.1f}%), "
                    f"latency: {orig_lat:.3f}→{comp_lat:.3f}ms "
                    f"(speedup={speedup:.2f}x)")
        return report

    @staticmethod
    def _make_verdict(compression_ratio: float, speedup: float) -> str:
        """根据压缩比和加速比生成评估结论。"""
        if compression_ratio > 2 and speedup > 1.5:
            return 'excellent'
        elif compression_ratio > 1.5 or speedup > 1.2:
            return 'good'
        elif compression_ratio > 1.1 or speedup > 1.05:
            return 'moderate'
        else:
            return 'minimal'

    def generate_report(self, report: Dict) -> str:
        """生成人类可读的压缩报告字符串。

        Args:
            report: compare_models 返回的报告字典

        Returns:
            格式化的报告字符串
        """
        lines = []
        lines.append("=" * 68)
        lines.append("  Model Compression Report")
        lines.append("=" * 68)
        lines.append(f"  Verdict:           {report['verdict'].upper()}")
        lines.append("-" * 68)
        lines.append(f"  Model Size:")
        lines.append(f"    Original:        {report['original_size_mb']:.4f} MB")
        lines.append(f"    Compressed:      {report['compressed_size_mb']:.4f} MB")
        lines.append(f"    Reduction:       {report['size_reduction_percent']:.2f}%")
        lines.append(f"    Compression:     {report['compression_ratio']:.2f}x")
        lines.append("-" * 68)
        lines.append(f"  Inference Latency:")
        lines.append(f"    Original:        {report['original_latency_ms']:.4f} ms")
        lines.append(f"    Compressed:      {report['compressed_latency_ms']:.4f} ms")
        lines.append(f"    Reduction:       {report['latency_reduction_percent']:.2f}%")
        lines.append(f"    Speedup:         {report['speedup']:.2f}x")
        lines.append("-" * 68)
        lines.append(f"  Original Stats:")
        lines.append(f"    p50 latency:     {report['original']['p50_latency_ms']:.4f} ms")
        lines.append(f"    p95 latency:     {report['original']['p95_latency_ms']:.4f} ms")
        lines.append(f"    memory:          {report['original']['memory_allocated_mb']:.4f} MB")
        lines.append("-" * 68)
        lines.append(f"  Compressed Stats:")
        lines.append(f"    p50 latency:     {report['compressed']['p50_latency_ms']:.4f} ms")
        lines.append(f"    p95 latency:     {report['compressed']['p95_latency_ms']:.4f} ms")
        lines.append(f"    memory:          {report['compressed']['memory_allocated_mb']:.4f} MB")
        lines.append("=" * 68)
        return "\n".join(lines)

    @property
    def report_history(self) -> List[Dict]:
        """历史对比报告列表（按时间顺序）。"""
        return self._report_history


# ============================================================================
# 2. Convenience Pipeline
# ============================================================================


def full_compression_pipeline(model: nn.Module,
                              quantize: Optional[str] = 'int8',
                              prune_amount: float = 0.3,
                              input_shape: Tuple[int, ...] = (100, 12),
                              num_runs: int = 100,
                              device: str = 'cpu'
                              ) -> Tuple[nn.Module, Dict]:
    """完整压缩管线：剪枝 → 量化 → 推理优化 → 对比。

    Args:
        model: 原始模型
        quantize: 量化精度 ('int8', 'float16', 或 None 跳过)
        prune_amount: 剪枝比例
        input_shape: 基准测试输入形状
        num_runs: 基准测试运行次数
        device: 设备

    Returns:
        (压缩后模型, 对比报告)
    """
    compressor = ModelCompressor(device=device)

    # 1. 剪枝
    print(f"[1/3] Pruning (amount={prune_amount})...")
    compressed = compressor.prune_model(model, amount=prune_amount)

    # 2. 量化
    if quantize is not None:
        print(f"[2/3] Quantizing (precision={quantize})...")
        compressed = compressor.quantize_model(compressed, precision=quantize)
    else:
        print(f"[2/3] Skipping quantization")

    # 3. 推理优化
    print(f"[3/3] Optimizing for inference...")
    compressed = compressor.optimize_for_inference(compressed)

    # 对比报告
    report = compressor.compare_models(
        model, compressed,
        input_shape=input_shape,
        num_runs=num_runs,
    )
    print(compressor.generate_report(report))

    return compressed, report


# ============================================================================
# 3. CLI
# ============================================================================


def _parse_args():
    """解析命令行参数。"""
    import argparse

    parser = argparse.ArgumentParser(
        description="GraphSAGE 模型压缩与优化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python model_compression.py --model model.pt --quantize int8 --prune 0.3
  python model_compression.py --model model.pt --benchmark --runs 200
  python model_compression.py --model model.pt --compare --quantize int8
        """,
    )

    parser.add_argument("--model", type=str, required=True,
                        help="模型文件路径 (.pt)")
    parser.add_argument("--quantize", type=str, default=None,
                        choices=['int8', 'float16'],
                        help="量化精度")
    parser.add_argument("--prune", type=float, default=0.0,
                        help="剪枝比例 (0.0~1.0)")
    parser.add_argument("--optimize", action="store_true",
                        help="推理优化")
    parser.add_argument("--benchmark", action="store_true",
                        help="运行性能基准测试")
    parser.add_argument("--compare", action="store_true",
                        help="对比压缩前后性能")
    parser.add_argument("--save", type=str, default=None,
                        help="保存压缩后模型的路径")
    parser.add_argument("--runs", type=int, default=100,
                        help="基准测试运行次数")
    parser.add_argument("--nodes", type=int, default=100,
                        help="基准测试图节点数")
    parser.add_argument("--features", type=int, default=12,
                        help="基准测试特征维度")
    parser.add_argument("--device", type=str, default="cpu",
                        help="设备 (cpu/cuda)")

    return parser.parse_args()


def main():
    """主入口。

    注意: 命令行模式仅支持 TorchScript 模型或可裸加载的 checkpoint。
    对于需要重建模型结构的场景，请使用 Python API。
    """
    args = _parse_args()

    if not os.path.exists(args.model):
        print(f"[ERROR] Model not found: {args.model}")
        return

    print("=" * 68)
    print("  GraphSAGE Model Compression Tool")
    print("=" * 68)

    compressor = ModelCompressor(device=args.device)
    input_shape = (args.nodes, args.features)

    # 尝试加载模型（优先 TorchScript）
    print(f"\n[Load] {args.model}")
    try:
        model = torch.jit.load(args.model, map_location=str(args.device))
        model.eval()
        print(f"  [OK] Loaded as TorchScript model")
    except Exception:
        print(f"  [WARN] Not a TorchScript model. "
              f"CLI mode requires ScriptModule for full functionality.")
        print(f"  [HINT] Use Python API for state_dict-based checkpoints:")
        print(f"         from model_compression import ModelCompressor")
        print(f"         compressor = ModelCompressor()")
        print(f"         model = compressor.load_compressed("
              f"'{args.model}', model_cls=YourModelClass)")
        if not (args.benchmark or args.compare):
            return
        # 无法继续加载，退出
        print(f"\n[ERROR] Cannot proceed without loadable model.")
        return

    # 性能基准测试
    if args.benchmark:
        print(f"\n[Benchmark] {args.runs} runs on "
              f"{args.nodes} nodes, {args.features} features...")
        stats = compressor.benchmark_model(
            model, input_shape, num_runs=args.runs)
        print(f"  Mean latency:    {stats['mean_latency_ms']:.3f} ms")
        print(f"  p50 latency:     {stats['p50_latency_ms']:.3f} ms")
        print(f"  p95 latency:     {stats['p95_latency_ms']:.3f} ms")
        print(f"  Model size:      {stats['model_size_mb']:.4f} MB")
        print(f"  Memory alloc:    {stats['memory_allocated_mb']:.4f} MB")
        print(f"  Throughput:      {stats['throughput_nodes_per_sec']:.1f} nodes/s")

    # 压缩 + 对比
    if args.compare or args.quantize or args.prune > 0:
        print(f"\n[Compress] Applying compression...")
        compressed = model
        if args.prune > 0:
            print(f"  - Prune (amount={args.prune})")
            compressed = compressor.prune_model(compressed, amount=args.prune)
        if args.quantize:
            print(f"  - Quantize (precision={args.quantize})")
            compressed = compressor.quantize_model(
                compressed, precision=args.quantize)
        if args.optimize:
            print(f"  - Optimize for inference")
            compressed = compressor.optimize_for_inference(compressed)

        report = compressor.compare_models(
            model, compressed,
            input_shape=input_shape,
            num_runs=args.runs,
        )
        print(compressor.generate_report(report))

        if args.save:
            compressor.save_compressed(
                compressed, args.save,
                metadata={
                    'quantize': args.quantize,
                    'prune_amount': args.prune,
                    'optimized': args.optimize,
                })
            print(f"\n[Save] Compressed model → {args.save}")


if __name__ == "__main__":
    main()
