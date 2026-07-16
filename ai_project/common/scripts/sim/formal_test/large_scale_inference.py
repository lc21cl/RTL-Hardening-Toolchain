#!/usr/bin/env python3
"""
large_scale_inference.py — 大规模 GNN 推理支持（10 万+ 节点）

针对节点数超过 10 万的大规模电路设计，提供分块推理、半精度推理、
渐进式推理、内存估算和图优化能力，避免显存/内存溢出。

核心特性:
  - 分块推理 (chunked_infer): 将大图拆分为子图分批推理
  - 半精度推理 (memory_efficient_infer): torch.no_grad() + FP16/AMP
  - 渐进式推理 (progressive_infer): 支持提前停止 (max_nodes)
  - 子图采样 (Neighbor Sampling): 通过 NeighborLoader 减少计算量
  - 内存管理: torch.cuda.empty_cache() + gc.collect()
  - CPU/GPU 自动切换

用法:
    # Python API — 配合 GNNInference 使用
    from gnn_inference import GNNInference
    from large_scale_inference import LargeScaleInference

    engine = GNNInference(threshold=0.05)
    engine.load_model()

    large_engine = LargeScaleInference(
        model=engine, device='auto', max_neighbors=15,
    )

    # 1. 分块推理（自动启用 Neighbor Sampling）
    scores = large_engine.chunked_infer(data, chunk_size=10000)

    # 2. 半精度推理（显存占用减半）
    scores = large_engine.memory_efficient_infer(data)

    # 3. 渐进式推理（处理前 50000 节点后停止）
    result = large_engine.progressive_infer(
        'big_design.blif', max_nodes=50000,
    )

    # 4. 内存估算
    mem_info = large_engine.estimate_memory(data)

    # 5. 图优化（去除孤立节点、合并冗余边）
    optimized = large_engine.optimize_graph(data)

    # 命令行
    python large_scale_inference.py --input big_design.blif --chunk-size 10000
    python large_scale_inference.py --input big_design.aig --max-nodes 50000
"""

import os
import sys
import gc
import time
import json
import argparse
import warnings
from typing import List, Tuple, Dict, Optional, Union

import numpy as np
import torch
import torch.nn as nn
from torch_geometric.data import Data

warnings.filterwarnings("ignore", category=UserWarning, module="torch_geometric")

# ── tqdm 可选依赖 ────────────────────────────────────────────────────────
try:
    from tqdm import tqdm as _tqdm
except ImportError:  # pragma: no cover - tqdm 是可选依赖
    def _tqdm(iterable, **kwargs):
        desc = kwargs.get('desc', '')
        total = kwargs.get('total', None)
        if total is not None and hasattr(iterable, '__len__'):
            for i, item in enumerate(iterable):
                if desc:
                    print(f"\r  {desc}: {i+1}/{total}", end='', flush=True)
                yield item
            if desc:
                print()
        else:
            yield from iterable

# ── Logger setup (与 gnn_inference.py 风格一致) ──────────────────────────
try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ============================================================================
# 1. Large Scale Inference Engine
# ============================================================================

class LargeScaleInference:
    """大规模 GNN 推理引擎，支持 10 万+ 节点的图推理。

    通过分块推理、半精度计算、子图采样 (Neighbor Sampling) 等技术，
    避免大规模图的显存/内存溢出。

    支持两种模型输入方式:
      1. 传入 GNNInference 实例 (自动提取 .model 和 .model_info)
      2. 传入 nn.Module (直接使用)

    Args:
        model: GNNInference 实例或 nn.Module。若为 None，需后续调用 set_model()。
        device: 'cpu', 'cuda', 或 'auto' (自动检测)
        threshold: 脆弱性分类阈值
        num_hops: 子图采样的跳数 (消息传递层数)
        max_neighbors: 每跳每节点采样的最大邻居数 (Neighbor Sampling)
        use_amp: 是否启用自动混合精度 (AMP) 推理
    """

    # 当节点数超过此阈值时，自动启用分块模式
    AUTO_CHUNK_THRESHOLD = 50_000

    def __init__(self,
                 model: Optional[Union[nn.Module, object]] = None,
                 device: str = 'auto',
                 threshold: float = 0.05,
                 num_hops: int = 2,
                 max_neighbors: int = 15,
                 use_amp: bool = False):
        self.device = self._resolve_device(device)
        self.threshold = threshold
        self.num_hops = num_hops
        self.max_neighbors = max_neighbors
        self.use_amp = use_amp

        self.model: Optional[nn.Module] = None
        self.model_info: Dict = {}
        self.infer_engine = None

        if model is not None:
            self.set_model(model)

    # ── Device & Model Setup ──────────────────────────────────────────

    @staticmethod
    def _resolve_device(device: str) -> torch.device:
        """解析设备字符串，支持 'auto' 自动切换 CPU/GPU。"""
        if device != 'auto':
            return torch.device(device)
        if torch.cuda.is_available():
            return torch.device('cuda')
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return torch.device('mps')
        return torch.device('cpu')

    def set_model(self, model: Union[nn.Module, object]) -> None:
        """设置推理模型。

        Args:
            model: GNNInference 实例 (含 .model 属性) 或 nn.Module
        """
        # 检测是否为 GNNInference 引擎 (鸭子类型)
        if hasattr(model, 'model') and hasattr(model, 'load_model'):
            self.infer_engine = model
            self.model = model.model
            self.model_info = getattr(model, 'model_info', {})
            if 'threshold' in dir(model):
                self.threshold = getattr(model, 'threshold', self.threshold)
        else:
            self.model = model
            self.infer_engine = None

        if self.model is not None:
            self.model.to(self.device)
            self.model.eval()
            # 自动检测消息传递层数
            detected = self._detect_num_hops()
            if detected > 0:
                self.num_hops = detected
            logger.info(f"[LargeScale] Model loaded on {self.device}, "
                        f"num_hops={self.num_hops}")

    def _detect_num_hops(self) -> int:
        """检测模型的消息传递层数 (SAGEConv/GCNConv 等)。"""
        if self.model is None:
            return 0
        try:
            from torch_geometric.nn import MessagePassing
            count = sum(1 for m in self.model.modules()
                        if isinstance(m, MessagePassing))
            return max(count, 1)
        except Exception:
            return 0

    # ── Feature Preparation ────────────────────────────────────────────

    def _prepare_features(self, x: torch.Tensor) -> torch.Tensor:
        """对齐输入特征维度到模型期望维度 (填充/截断)。"""
        if not self.model_info:
            return x
        model_in = self.model_info.get('in_channels')
        if model_in is None:
            return x
        if x.shape[1] < model_in:
            pad = torch.zeros(x.shape[0], model_in - x.shape[1],
                              dtype=x.dtype, device=x.device)
            x = torch.cat([x, pad], dim=1)
        elif x.shape[1] > model_in:
            x = x[:, :model_in]
        return x

    # ── Memory Management ──────────────────────────────────────────────

    def _cleanup_memory(self) -> None:
        """释放显存和 Python 对象内存。"""
        if self.device.type == 'cuda' and torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
        gc.collect()

    # ── Public API ────────────────────────────────────────────────────

    def chunked_infer(self,
                      data: Data,
                      chunk_size: int = 10000,
                      use_neighbor_sampling: bool = True) -> torch.Tensor:
        """将大图分块推理，避免内存溢出。

        将所有节点拆分为 chunk_size 大小的块，对每块进行子图采样后
        独立推理，最后合并结果。当节点数低于 AUTO_CHUNK_THRESHOLD 时，
        自动回退到整图推理。

        Args:
            data: PyG Data 对象，需含 .x 和 .edge_index
            chunk_size: 每个分块的节点数
            use_neighbor_sampling: 是否启用 Neighbor Sampling。
                True  — 使用 NeighborLoader 采样 k-hop 邻域 (推荐)
                False — 使用 induced subgraph (仅保留块内边)

        Returns:
            脆弱性分数 [num_nodes]，范围 [0, 1]
        """
        self._ensure_model_loaded()

        num_nodes = data.num_nodes
        logger.info(f"[Chunked] {num_nodes} nodes, {data.edge_index.shape[1]} edges, "
                    f"chunk_size={chunk_size}, neighbor_sampling={use_neighbor_sampling}")

        # 小图直接推理
        if num_nodes <= self.AUTO_CHUNK_THRESHOLD:
            logger.info(f"[Chunked] Nodes <= {self.AUTO_CHUNK_THRESHOLD}, "
                        f"using direct inference")
            return self.memory_efficient_infer(data)

        # 选择推理路径
        if use_neighbor_sampling:
            try:
                scores = self._chunked_infer_neighbor_loader(data, chunk_size)
            except (ImportError, RuntimeError) as e:
                # NeighborLoader 需要 pyg-lib / torch-sparse，不可用时回退
                logger.warning(f"[Chunked] NeighborLoader unavailable ({e}), "
                               f"falling back to induced subgraph")
                scores = self._chunked_infer_induced(data, chunk_size)
        else:
            scores = self._chunked_infer_induced(data, chunk_size)

        n_vuln = int((scores >= self.threshold).sum().item())
        logger.metric("Chunked", n_vuln, "vulnerable nodes")
        return scores

    def memory_efficient_infer(self,
                                graph_data: Data,
                                half_precision: bool = True) -> torch.Tensor:
        """使用 torch.no_grad() 和半精度推理降低显存占用。

        在 GPU 上启用 AMP (自动混合精度)；在 CPU 上使用 FP16 计算。
        推理完成后自动清理显存。

        Args:
            graph_data: PyG Data 对象
            half_precision: 是否启用半精度 (FP16/AMP)

        Returns:
            脆弱性分数 [num_nodes]，范围 [0, 1]
        """
        self._ensure_model_loaded()

        x = self._prepare_features(graph_data.x).to(self.device)
        edge_index = graph_data.edge_index.to(self.device)

        logger.info(f"[MemoryEfficient] {x.shape[0]} nodes, "
                    f"half_precision={half_precision}, device={self.device}")

        use_half = half_precision and self.device.type in ('cuda', 'mps')

        with torch.no_grad():
            if use_half:
                # AMP: autocast 自动处理精度转换
                with torch.autocast(device_type=self.device.type, dtype=torch.float16):
                    logits = self.model(x, edge_index)
                scores = torch.sigmoid(logits.float())
            else:
                logits = self.model(x, edge_index)
                scores = torch.sigmoid(logits)

        self._cleanup_memory()
        return scores.cpu()

    def progressive_infer(self,
                          file_path: str,
                          max_nodes: Optional[int] = None,
                          chunk_size: int = 10000) -> Dict:
        """渐进式推理，支持提前停止。

        从文件加载图数据，分块渐进推理。当处理节点数达到 max_nodes 时
        提前停止，返回已处理部分的推理结果。

        Args:
            file_path: .blif / .aig / .pt 文件路径
            max_nodes: 最大处理节点数。None 表示处理全部。
            chunk_size: 每个分块的节点数

        Returns:
            推理结果字典，含 scores, processed_nodes, stopped_early 等字段
        """
        self._ensure_model_loaded()

        logger.section(f"Progressive Inference: {os.path.basename(file_path)}")

        # 加载图数据
        data = self._load_graph_data(file_path)
        num_nodes = data.num_nodes
        limit = min(max_nodes, num_nodes) if max_nodes is not None else num_nodes

        logger.info(f"[Progressive] Total nodes: {num_nodes}, "
                    f"limit: {limit}, chunk_size: {chunk_size}")

        # 截取前 limit 个节点及其子图
        if max_nodes is not None and max_nodes < num_nodes:
            data = self._truncate_graph(data, limit)
            logger.info(f"[Progressive] Truncated to {data.num_nodes} nodes")

        # 分块推理
        t0 = time.time()
        scores = self.chunked_infer(
            data, chunk_size=chunk_size,
            use_neighbor_sampling=True,
        )
        elapsed = time.time() - t0

        stopped_early = (max_nodes is not None and max_nodes < num_nodes)

        result = self._build_result(data, scores, file_path)
        result['total_nodes_in_file'] = num_nodes
        result['processed_nodes'] = data.num_nodes
        result['stopped_early'] = stopped_early
        result['inference_time_s'] = round(elapsed, 3)

        if stopped_early:
            logger.info(f"[Progressive] Stopped early at {max_nodes} nodes "
                        f"(total: {num_nodes})")
        logger.metric("Progressive", elapsed, "seconds")

        self._cleanup_memory()
        return result

    def estimate_memory(self,
                        graph_data: Data,
                        batch_size: Optional[int] = None) -> Dict[str, float]:
        """估算推理所需内存。

        基于节点数、边数、特征维度和模型参数进行解析估算。
        返回各组件的内存占用 (MB)。

        Args:
            graph_data: PyG Data 对象
            batch_size: 若指定，估算单批次推理内存；否则估算整图

        Returns:
            内存估算字典，单位 MB:
              - node_features: 节点特征内存
              - edge_index: 边索引内存
              - model_params: 模型参数内存
              - activations: 前向传播激活内存
              - total: 总估算内存
              - recommended_chunk_size: 推荐分块大小
        """
        num_nodes = graph_data.num_nodes
        num_edges = graph_data.edge_index.shape[1]
        feature_dim = graph_data.x.shape[1] if graph_data.x is not None else 0

        n = batch_size if batch_size is not None else num_nodes

        # 字节大小: FP32=4, FP16=2
        bytes_per_elem = 2 if self.use_amp else 4

        # 1. 节点特征内存
        node_features_mb = (num_nodes * feature_dim * bytes_per_elem) / (1024 ** 2)

        # 2. 边索引内存 (int64, 2 x num_edges)
        edge_index_mb = (2 * num_edges * 8) / (1024 ** 2)

        # 3. 模型参数内存
        num_params = self._count_params()
        model_params_mb = (num_params * bytes_per_elem) / (1024 ** 2)

        # 4. 前向传播激活内存 (估算: num_nodes * hidden_dim * num_layers)
        hidden_dim = self.model_info.get('hidden_channels', 64)
        num_layers = self.num_hops
        # 消息传递激活 + MLP 中间层
        activations_mb = (n * hidden_dim * num_layers * bytes_per_elem * 2) / (1024 ** 2)
        # 边聚合临时缓冲 (每条边一个 hidden_dim 向量)
        edge_buffer_mb = (min(num_edges, n * self.max_neighbors) * hidden_dim
                          * bytes_per_elem) / (1024 ** 2)

        # 5. 输出分数内存
        output_mb = (n * bytes_per_elem) / (1024 ** 2)

        total_mb = (node_features_mb + edge_index_mb + model_params_mb
                    + activations_mb + edge_buffer_mb + output_mb)

        # 推荐分块大小: 基于可用显存/内存
        available_mb = self._available_memory_mb()
        # 保留 30% 余量，每块约用 activations + edge_buffer
        per_node_mb = (hidden_dim * num_layers * bytes_per_elem * 2
                       + hidden_dim * self.max_neighbors * bytes_per_elem) / (1024 ** 2)
        if per_node_mb > 0 and available_mb > 0:
            recommended_chunk = int(available_mb * 0.7 / per_node_mb)
            recommended_chunk = max(1000, min(recommended_chunk, 50000))
        else:
            recommended_chunk = chunk_size_default()

        return {
            'num_nodes': num_nodes,
            'num_edges': num_edges,
            'feature_dim': feature_dim,
            'num_params': num_params,
            'node_features_mb': round(node_features_mb, 2),
            'edge_index_mb': round(edge_index_mb, 2),
            'model_params_mb': round(model_params_mb, 2),
            'activations_mb': round(activations_mb, 2),
            'edge_buffer_mb': round(edge_buffer_mb, 2),
            'output_mb': round(output_mb, 2),
            'total_mb': round(total_mb, 2),
            'available_mb': round(available_mb, 2),
            'recommended_chunk_size': recommended_chunk,
            'precision': 'FP16' if self.use_amp else 'FP32',
        }

    def optimize_graph(self,
                       graph_data: Data,
                       remove_isolated: bool = True,
                       merge_duplicates: bool = True,
                       to_undirected: bool = False) -> Data:
        """图优化：去除孤立节点、合并冗余边。

        Args:
            graph_data: PyG Data 对象
            remove_isolated: 是否移除孤立节点 (无边连接的节点)
            merge_duplicates: 是否合并重复边 (coalesce)
            to_undirected: 是否转为无向图

        Returns:
            优化后的 PyG Data 对象 (新对象，不修改原图)
        """
        from torch_geometric.utils import (
            remove_isolated_nodes,
            coalesce as coalesce_edges,
            to_undirected as to_undirected_edges,
        )

        data = graph_data.clone()
        original_nodes = data.num_nodes
        original_edges = data.edge_index.shape[1]

        # 1. 合并重复边
        if merge_duplicates:
            data.edge_index = coalesce_edges(
                data.edge_index, num_nodes=data.num_nodes,
            )

        # 2. 转为无向图
        if to_undirected:
            data.edge_index = to_undirected_edges(
                data.edge_index, num_nodes=data.num_nodes,
            )

        # 3. 移除孤立节点 (PyG 2.x 始终重标记节点)
        if remove_isolated:
            edge_index, _, mask = remove_isolated_nodes(
                data.edge_index, num_nodes=data.num_nodes,
            )
            data.edge_index = edge_index
            data.num_nodes = int(mask.sum().item())
            # 同步更新节点级属性 (仅当维度匹配 num_nodes 时)
            for attr in ['x', 'y', 'train_mask', 'val_mask',
                         'test_mask', 'node_type']:
                attr_val = getattr(data, attr, None)
                if attr_val is not None and attr_val.shape[0] == len(mask):
                    setattr(data, attr, attr_val[mask])

        removed_nodes = original_nodes - data.num_nodes
        removed_edges = original_edges - data.edge_index.shape[1]

        logger.info(f"[Optimize] Nodes: {original_nodes} → {data.num_nodes} "
                    f"(removed {removed_nodes} isolated)")
        logger.info(f"[Optimize] Edges: {original_edges} → "
                    f"{data.edge_index.shape[1]} (removed {removed_edges} duplicates)")

        return data

    # ── Internal: Chunked Inference via NeighborLoader ─────────────────

    def _chunked_infer_neighbor_loader(self, data: Data,
                                        chunk_size: int) -> torch.Tensor:
        """使用 NeighborLoader 进行分块采样推理。

        对每个节点块采样 k-hop 邻域子图，仅对种子节点收集预测结果。
        这是推荐的大规模推理方式 (Neighbor Sampling)。
        """
        from torch_geometric.loader import NeighborLoader

        num_nodes = data.num_nodes
        scores = torch.zeros(num_nodes, dtype=torch.float32)

        # 确保 edge_index 是无向的 (SAGE 需要双向消息传递)
        edge_index = data.edge_index
        num_hops = self.num_hops
        max_neighbors = self.max_neighbors

        # NeighborLoader 需要带 .x 的 Data
        loader_data = data
        if loader_data.x is None:
            loader_data.x = torch.zeros(num_nodes, 1, dtype=torch.float32)

        # 准备特征
        loader_data.x = self._prepare_features(loader_data.x)

        loader = NeighborLoader(
            loader_data,
            num_neighbors=[max_neighbors] * num_hops,
            batch_size=chunk_size,
            shuffle=False,
            num_workers=0,
        )

        total_chunks = (num_nodes + chunk_size - 1) // chunk_size
        processed = 0

        for batch in _tqdm(loader, desc="Chunked infer", total=total_chunks):
            batch = batch.to(self.device)
            batch_size = batch.batch_size

            with torch.no_grad():
                if self.use_amp and self.device.type == 'cuda':
                    with torch.autocast(device_type='cuda', dtype=torch.float16):
                        logits = self.model(batch.x, batch.edge_index)
                else:
                    logits = self.model(batch.x, batch.edge_index)
                batch_scores = torch.sigmoid(logits.float())

            # batch.n_id 映射回原图节点索引
            # 前 batch_size 个节点是种子节点
            seed_scores = batch_scores[:batch_size].cpu()
            seed_ids = batch.n_id[:batch_size].cpu()

            scores[seed_ids] = seed_scores
            processed += batch_size

            self._cleanup_memory()

        logger.info(f"[Chunked] Processed {processed}/{num_nodes} nodes "
                    f"via NeighborLoader")
        return scores

    # ── Internal: Chunked Inference via Induced Subgraph ───────────────

    def _chunked_infer_induced(self, data: Data,
                                chunk_size: int) -> torch.Tensor:
        """使用 induced subgraph 分块推理 (回退方案)。

        对每个节点块提取 k-hop 子图 (含全部邻居)，推理后收集种子节点结果。
        不做邻居采样，适合度数较小的稀疏图。
        """
        from torch_geometric.utils import k_hop_subgraph

        num_nodes = data.num_nodes
        edge_index = data.edge_index
        x = self._prepare_features(data.x)
        num_hops = self.num_hops

        scores = torch.zeros(num_nodes, dtype=torch.float32)

        node_indices = torch.arange(num_nodes)
        chunks = [node_indices[i:i + chunk_size]
                  for i in range(0, num_nodes, chunk_size)]

        for chunk in _tqdm(chunks, desc="Chunked infer", total=len(chunks)):
            # 提取 k-hop 子图
            subset, sub_edge_index, mapping, _ = k_hop_subgraph(
                node_idx=chunk,
                num_hops=num_hops,
                edge_index=edge_index,
                relabel_nodes=True,
                num_nodes=num_nodes,
            )

            sub_x = x[subset].to(self.device)
            sub_edge_index = sub_edge_index.to(self.device)

            with torch.no_grad():
                if self.use_amp and self.device.type == 'cuda':
                    with torch.autocast(device_type='cuda', dtype=torch.float16):
                        logits = self.model(sub_x, sub_edge_index)
                else:
                    logits = self.model(sub_x, sub_edge_index)
                sub_scores = torch.sigmoid(logits.float()).cpu()

            # mapping 映射种子节点到子图中的位置
            scores[chunk] = sub_scores[mapping]

            self._cleanup_memory()

        logger.info(f"[Chunked] Processed {num_nodes} nodes via induced subgraph")
        return scores

    # ── Internal: Graph Loading & Helpers ──────────────────────────────

    def _load_graph_data(self, file_path: str) -> Data:
        """从文件加载图数据，支持 .blif / .aig / .pt。"""
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.pt':
            data = torch.load(file_path, map_location='cpu', weights_only=False)
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            if not isinstance(data, Data):
                raise ValueError(f"Expected PyG Data, got {type(data)}")
            return data

        # BLIF / AIG: 使用 GraphConverter
        try:
            from gnn_inference import GraphConverter
            converter = GraphConverter()
            return converter.convert(file_path)
        except ImportError:
            raise ImportError(
                "Cannot import GraphConverter from gnn_inference. "
                "For .blif/.aig files, ensure gnn_inference.py is importable. "
                "For .pt files, use torch.load directly."
            )

    def _truncate_graph(self, data: Data, max_nodes: int) -> Data:
        """截取前 max_nodes 个节点的子图。"""
        from torch_geometric.utils import k_hop_subgraph

        target = torch.arange(min(max_nodes, data.num_nodes))
        subset, sub_edge_index, _, _ = k_hop_subgraph(
            node_idx=target,
            num_hops=self.num_hops,
            edge_index=data.edge_index,
            relabel_nodes=True,
            num_nodes=data.num_nodes,
        )

        new_data = Data()
        new_data.x = data.x[subset] if data.x is not None else None
        new_data.edge_index = sub_edge_index
        new_data.num_nodes = subset.size(0)

        # 复制元数据
        for attr in ['graph_type', 'original_file', 'design_name']:
            if hasattr(data, attr):
                setattr(new_data, attr, getattr(data, attr))

        return new_data

    def _build_result(self, data: Data, scores: torch.Tensor,
                       source_file: str) -> Dict:
        """构建推理结果字典 (与 GNNInference 风格一致)。"""
        vulnerable_mask = scores >= self.threshold
        vuln_indices = torch.where(vulnerable_mask)[0].tolist()

        vuln_list = sorted(
            [(int(idx), float(scores[idx])) for idx in vuln_indices],
            key=lambda x: x[1], reverse=True,
        )

        sorted_idx = torch.argsort(scores, descending=True)
        all_ranked = [(int(i), float(scores[i])) for i in sorted_idx]

        return {
            'source_file': source_file,
            'design_name': getattr(data, 'design_name',
                                    os.path.splitext(os.path.basename(source_file))[0]),
            'graph_type': getattr(data, 'graph_type', 'unknown'),
            'num_nodes': data.num_nodes,
            'num_edges': data.edge_index.shape[1],
            'threshold': self.threshold,
            'num_vulnerable': len(vuln_list),
            'vulnerability_ratio': len(vuln_list) / max(data.num_nodes, 1),
            'max_score': float(scores.max().item()) if len(scores) > 0 else 0.0,
            'mean_score': float(scores.mean().item()) if len(scores) > 0 else 0.0,
            'min_score': float(scores.min().item()) if len(scores) > 0 else 0.0,
            'std_score': float(scores.std().item()) if len(scores) > 0 else 0.0,
            'top_10_vulnerable': [
                {'node_id': nid, 'score': round(score, 6)}
                for nid, score in vuln_list[:10]
            ],
            'all_vulnerable_nodes': [
                {'node_id': nid, 'score': round(score, 6)}
                for nid, score in vuln_list
            ],
            'all_ranked_nodes': [
                {'node_id': nid, 'score': round(score, 6)}
                for nid, score in all_ranked
            ],
            'feature_dim': data.x.shape[1] if data.x is not None else 0,
            'model_path': self.model_info.get('path', ''),
            'device': str(self.device),
            'num_hops': self.num_hops,
            'max_neighbors': self.max_neighbors,
        }

    # ── Internal: Utilities ────────────────────────────────────────────

    def _ensure_model_loaded(self) -> None:
        """确认模型已加载。"""
        if self.model is None:
            raise RuntimeError(
                "Model not loaded. Pass a model to __init__() or call set_model()."
            )

    def _count_params(self) -> int:
        """统计模型可训练参数数。"""
        if self.model is None:
            return 0
        return sum(p.numel() for p in self.model.parameters() if p.requires_grad)

    def _available_memory_mb(self) -> float:
        """获取可用显存/内存 (MB)。"""
        if self.device.type == 'cuda' and torch.cuda.is_available():
            props = torch.cuda.get_device_properties(self.device)
            allocated = torch.cuda.memory_allocated(self.device)
            return (props.total_memory - allocated) / (1024 ** 2)
        # CPU: 使用 psutil 获取可用内存 (可选)
        try:
            import psutil
            return psutil.virtual_memory().available / (1024 ** 2)
        except ImportError:
            # 回退: 假设 8GB 可用
            return 8192.0

    # ── Result Output ──────────────────────────────────────────────────

    def export_results(self, result: Dict, output_path: str) -> str:
        """导出推理结果到 JSON 文件。

        Args:
            result: 推理结果字典
            output_path: 输出 JSON 路径

        Returns:
            保存的文件路径
        """
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        export_data = {
            'inference_engine': 'LargeScaleInference',
            'model_info': self.model_info,
            'threshold': self.threshold,
            'device': str(self.device),
            'num_hops': self.num_hops,
            'max_neighbors': self.max_neighbors,
            'results': result,
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        return output_path

    def print_result_summary(self, result: Dict) -> None:
        """打印推理结果摘要。"""
        print("=" * 62)
        print("  Large-Scale Inference Report")
        print("=" * 62)
        print(f"  File:     {os.path.basename(result.get('source_file', 'N/A'))}")
        print(f"  Type:     {result.get('graph_type', 'N/A')}")
        print(f"  Device:   {result.get('device', 'N/A')}")
        print(f"  Nodes:    {result['num_nodes']}")
        print(f"  Edges:    {result['num_edges']}")
        print(f"  Features: {result.get('feature_dim', 'N/A')}-dim")
        print("-" * 62)
        print(f"  Score Distribution:")
        print(f"    Max:   {result['max_score']:.4f}")
        print(f"    Mean:  {result['mean_score']:.4f}")
        print(f"    Min:   {result['min_score']:.4f}")
        print(f"    Std:   {result['std_score']:.4f}")
        print("-" * 62)
        print(f"  Threshold:         {result['threshold']}")
        print(f"  Vulnerable nodes:  {result['num_vulnerable']} / "
              f"{result['num_nodes']} ({result['vulnerability_ratio']*100:.1f}%)")
        if result.get('stopped_early'):
            print(f"  [STOPPED EARLY] at {result.get('processed_nodes', '?')}/"
                  f"{result.get('total_nodes_in_file', '?')} nodes")
        if result.get('inference_time_s'):
            print(f"  Inference time:    {result['inference_time_s']:.2f}s")
        print("-" * 62)
        if result.get('all_vulnerable_nodes'):
            print(f"  Top-5 Most Vulnerable Nodes:")
            for i, n in enumerate(result['all_vulnerable_nodes'][:5]):
                print(f"    {i+1:>3d}. Node {n['node_id']:>6d}  "
                      f"Score: {n['score']:.6f}")
        print("=" * 62)

    def benchmark(self, data: Data, chunk_size: int = 10000,
                   num_runs: int = 3) -> Dict:
        """基准测试分块推理延迟。

        Args:
            data: PyG Data 对象
            chunk_size: 分块大小
            num_runs: 重复次数

        Returns:
            延迟统计字典
        """
        self._ensure_model_loaded()
        latencies = []

        # 预热
        _ = self.chunked_infer(data, chunk_size=chunk_size)

        for _ in range(num_runs):
            t0 = time.perf_counter()
            _ = self.chunked_infer(data, chunk_size=chunk_size)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000)

        return {
            'num_nodes': data.num_nodes,
            'num_edges': data.edge_index.shape[1],
            'chunk_size': chunk_size,
            'num_runs': num_runs,
            'mean_latency_ms': float(np.mean(latencies)),
            'min_latency_ms': float(np.min(latencies)),
            'max_latency_ms': float(np.max(latencies)),
            'std_latency_ms': float(np.std(latencies)),
        }


# ============================================================================
# 2. Helpers
# ============================================================================

def chunk_size_default() -> int:
    """默认分块大小。"""
    return 10000


def create_mock_large_graph(num_nodes: int = 100000,
                             feature_dim: int = 12,
                             avg_degree: int = 6) -> Data:
    """生成模拟大规模图 (用于测试)。

    Args:
        num_nodes: 节点数
        feature_dim: 特征维度
        avg_degree: 平均度数

    Returns:
        PyG Data 对象
    """
    torch.manual_seed(42)
    num_edges = num_nodes * avg_degree

    # 随机边
    src = torch.randint(0, num_nodes, (num_edges,))
    dst = torch.randint(0, num_nodes, (num_edges,))
    edge_index = torch.stack([src, dst], dim=0)

    # 随机特征
    x = torch.randn(num_nodes, feature_dim)

    data = Data(x=x, edge_index=edge_index)
    data.num_nodes = num_nodes
    return data


# ============================================================================
# 3. CLI
# ============================================================================

def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="Large-Scale GNN Inference (100K+ nodes)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 分块推理
  python large_scale_inference.py --input big_design.blif --chunk-size 10000

  # 渐进式推理 (前 50000 节点)
  python large_scale_inference.py --input big_design.aig --max-nodes 50000

  # 内存估算
  python large_scale_inference.py --input big_design.blif --estimate-only

  # 半精度推理
  python large_scale_inference.py --input big_design.blif --half-precision
        """,
    )

    parser.add_argument("--input", type=str, required=True,
                        help="Path to .blif / .aig / .pt file")
    parser.add_argument("--model", type=str, default=None,
                        help="Path to trained model .pt file")
    parser.add_argument("--model-type", type=str, default=None,
                        choices=['SAGE3', 'SAGE2Lite', 'auto'],
                        help="Model architecture")
    parser.add_argument("--threshold", type=float, default=0.05,
                        help="Vulnerability threshold")
    parser.add_argument("--chunk-size", type=int, default=10000,
                        help="Chunk size for batched inference")
    parser.add_argument("--max-nodes", type=int, default=None,
                        help="Max nodes for progressive inference")
    parser.add_argument("--max-neighbors", type=int, default=15,
                        help="Max neighbors per hop (Neighbor Sampling)")
    parser.add_argument("--num-hops", type=int, default=None,
                        help="Number of hops for subgraph sampling (auto-detect)")
    parser.add_argument("--device", type=str, default='auto',
                        choices=['auto', 'cpu', 'cuda'],
                        help="Device")
    parser.add_argument("--half-precision", action="store_true",
                        help="Use half precision (FP16/AMP)")
    parser.add_argument("--no-neighbor-sampling", action="store_true",
                        help="Disable neighbor sampling (use induced subgraph)")
    parser.add_argument("--optimize-graph", action="store_true",
                        help="Optimize graph before inference")
    parser.add_argument("--estimate-only", action="store_true",
                        help="Only estimate memory, skip inference")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON path")

    return parser.parse_args()


def main():
    """命令行入口。"""
    args = parse_args()

    if not os.path.exists(args.input):
        print(f"[ERROR] File not found: {args.input}")
        sys.exit(1)

    print("=" * 62)
    print("  Large-Scale GNN Inference")
    print("=" * 62)

    # 加载图数据
    print(f"\n[1] Loading graph: {args.input}")
    try:
        from gnn_inference import GNNInference, GraphConverter
        converter = GraphConverter()
        data = converter.convert(args.input)
    except ImportError:
        ext = os.path.splitext(args.input)[1].lower()
        if ext == '.pt':
            data = torch.load(args.input, map_location='cpu', weights_only=False)
            if isinstance(data, list):
                data = data[0]
        else:
            print(f"[ERROR] Cannot load {ext} without gnn_inference.py")
            sys.exit(1)

    print(f"  Nodes: {data.num_nodes}")
    print(f"  Edges: {data.edge_index.shape[1]}")
    print(f"  Features: {data.x.shape[1] if data.x is not None else 0}-dim")

    # 图优化
    if args.optimize_graph:
        print(f"\n[2] Optimizing graph...")
        engine_tmp = LargeScaleInference(device=args.device)
        data = engine_tmp.optimize_graph(data)
        print(f"  Optimized: {data.num_nodes} nodes, "
              f"{data.edge_index.shape[1]} edges")

    # 仅估算内存
    if args.estimate_only:
        print(f"\n[*] Estimating memory...")
        engine_tmp = LargeScaleInference(device=args.device)
        mem = engine_tmp.estimate_memory(data)
        print(f"\n  Memory Estimation:")
        print(f"    Node features:  {mem['node_features_mb']:.2f} MB")
        print(f"    Edge index:      {mem['edge_index_mb']:.2f} MB")
        print(f"    Model params:    {mem['model_params_mb']:.2f} MB")
        print(f"    Activations:     {mem['activations_mb']:.2f} MB")
        print(f"    Edge buffer:     {mem['edge_buffer_mb']:.2f} MB")
        print(f"    Total:           {mem['total_mb']:.2f} MB")
        print(f"    Available:       {mem['available_mb']:.2f} MB")
        print(f"    Precision:       {mem['precision']}")
        print(f"    Recommended chunk size: {mem['recommended_chunk_size']}")
        return

    # 加载模型
    print(f"\n[3] Loading model...")
    from gnn_inference import GNNInference
    gnn_engine = GNNInference(model_path=args.model, device=args.device,
                               threshold=args.threshold)
    model_type = args.model_type if args.model_type != 'auto' else None
    if not gnn_engine.load_model(args.model, model_type=model_type):
        print("  [FAIL] Model not found. Train first: python _train_local.py")
        sys.exit(1)

    num_hops = args.num_hops if args.num_hops is not None else 2
    large_engine = LargeScaleInference(
        model=gnn_engine,
        device=args.device,
        threshold=args.threshold,
        num_hops=num_hops,
        max_neighbors=args.max_neighbors,
        use_amp=args.half_precision,
    )

    # 推理
    print(f"\n[4] Running inference...")
    t0 = time.time()

    if args.max_nodes is not None:
        result = large_engine.progressive_infer(
            args.input, max_nodes=args.max_nodes,
            chunk_size=args.chunk_size,
        )
    else:
        use_sampling = not args.no_neighbor_sampling
        scores = large_engine.chunked_infer(
            data, chunk_size=args.chunk_size,
            use_neighbor_sampling=use_sampling,
        )
        result = large_engine._build_result(data, scores, args.input)
        result['inference_time_s'] = round(time.time() - t0, 3)

    elapsed = time.time() - t0
    large_engine.print_result_summary(result)
    print(f"\n  Total time: {elapsed:.2f}s")

    # 保存结果
    output_path = args.output or (
        os.path.splitext(args.input)[0] + '_large_scale_vulnerability.json'
    )
    large_engine.export_results(result, output_path)
    print(f"\n  Results saved to: {output_path}")


if __name__ == "__main__":
    main()
