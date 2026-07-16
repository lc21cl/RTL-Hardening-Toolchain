#!/usr/bin/env python3
"""model_fusion.py — 多模型融合模块

集成多种 GNN 架构（GAT、GCN、GraphSAGE）进行集成学习。

用法:
    from model_fusion import ModelFusion

    fusion = ModelFusion(models=[model1, model2, model3])
    result = fusion.predict(graph_data)
    ensemble_prediction = fusion.ensemble(graph_data)
"""

import torch
import torch.nn as nn
from typing import List, Dict, Any, Optional


class ModelFusion:
    """多模型融合器。

    支持多种 GNN 架构的集成学习。
    """

    def __init__(self, models: Optional[List[nn.Module]] = None):
        """初始化模型融合器。

        Args:
            models: 模型列表
        """
        self._models = models or []
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._weights = None

    def add_model(self, model: nn.Module, weight: float = 1.0):
        """添加模型。

        Args:
            model: 模型
            weight: 模型权重
        """
        model.to(self._device)
        model.eval()
        self._models.append((model, weight))

    def set_weights(self, weights: List[float]):
        """设置模型权重。

        Args:
            weights: 权重列表
        """
        if len(weights) == len(self._models):
            self._weights = weights

    def predict(self, graph_data) -> List[torch.Tensor]:
        """使用所有模型进行预测。

        Args:
            graph_data: 图数据

        Returns:
            各模型预测结果列表
        """
        data = graph_data.to(self._device)
        predictions = []

        with torch.no_grad():
            for model, _ in self._models:
                out = model(data.x, data.edge_index)
                predictions.append(out.cpu())

        return predictions

    def ensemble(self, graph_data, method: str = "weighted") -> torch.Tensor:
        """集成预测。

        Args:
            graph_data: 图数据
            method: 集成方法 (weighted/voting/stacking)

        Returns:
            集成预测结果
        """
        predictions = self.predict(graph_data)

        if len(predictions) == 0:
            return torch.tensor([])

        if method == "voting":
            return self._voting_ensemble(predictions)
        elif method == "stacking":
            return self._stacking_ensemble(predictions)
        else:
            return self._weighted_ensemble(predictions)

    def _weighted_ensemble(self, predictions: List[torch.Tensor]) -> torch.Tensor:
        """加权集成。

        Args:
            predictions: 预测结果列表

        Returns:
            集成结果
        """
        if self._weights is None:
            weights = torch.ones(len(predictions)) / len(predictions)
        else:
            weights = torch.tensor(self._weights)

        weighted_sum = torch.zeros_like(predictions[0])
        for pred, weight in zip(predictions, weights):
            weighted_sum += pred * weight

        return weighted_sum

    def _voting_ensemble(self, predictions: List[torch.Tensor]) -> torch.Tensor:
        """投票集成。

        Args:
            predictions: 预测结果列表

        Returns:
            集成结果
        """
        preds = torch.stack(predictions)
        pred_labels = preds.argmax(dim=-1)
        vote_counts = torch.zeros(pred_labels.shape[1], preds.shape[-1])

        for pred in pred_labels:
            for i, label in enumerate(pred):
                vote_counts[i, label] += 1

        return vote_counts.argmax(dim=-1)

    def _stacking_ensemble(self, predictions: List[torch.Tensor]) -> torch.Tensor:
        """堆叠集成。

        Args:
            predictions: 预测结果列表

        Returns:
            集成结果
        """
        stacked = torch.cat(predictions, dim=-1)
        hidden = nn.Linear(stacked.shape[-1], 64)(stacked)
        hidden = nn.ReLU()(hidden)
        output = nn.Linear(64, predictions[0].shape[-1])(hidden)

        return output

    def train_weights(self, dataloader, epochs: int = 10, lr: float = 1e-3) -> Dict[str, Any]:
        """训练集成权重。

        Args:
            dataloader: 数据加载器
            epochs: 训练轮数
            lr: 学习率

        Returns:
            训练结果
        """
        if len(self._models) == 0:
            return {"error": "No models added"}

        self._weights = torch.ones(len(self._models), requires_grad=True)
        optimizer = torch.optim.Adam([self._weights], lr=lr)
        criterion = nn.CrossEntropyLoss()

        losses = []

        for epoch in range(epochs):
            epoch_loss = 0.0

            for batch in dataloader:
                data = batch.to(self._device)
                optimizer.zero_grad()

                predictions = []
                with torch.no_grad():
                    for model, _ in self._models:
                        out = model(data.x, data.edge_index)
                        predictions.append(out)

                weighted_sum = torch.zeros_like(predictions[0])
                for pred, weight in zip(predictions, self._weights):
                    weighted_sum += pred * weight

                loss = criterion(weighted_sum[data.train_mask], data.y[data.train_mask])
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()

            losses.append(epoch_loss / len(dataloader))

        self._weights = torch.nn.functional.softmax(self._weights, dim=0).tolist()

        return {
            "losses": losses,
            "final_loss": losses[-1] if losses else 0,
            "weights": self._weights,
        }

    def get_fusion_info(self) -> Dict[str, Any]:
        """获取融合信息。

        Returns:
            融合信息
        """
        model_names = [type(model).__name__ for model, _ in self._models]

        return {
            "num_models": len(self._models),
            "model_names": model_names,
            "weights": self._weights,
            "device": str(self._device),
        }


if __name__ == "__main__":
    from torch_geometric.nn import GraphSAGE

    model1 = GraphSAGE(in_channels=64, hidden_channels=64, out_channels=2, num_layers=2)
    model2 = GraphSAGE(in_channels=64, hidden_channels=32, out_channels=2, num_layers=3)
    model3 = GraphSAGE(in_channels=64, hidden_channels=128, out_channels=2, num_layers=2)

    fusion = ModelFusion()
    fusion.add_model(model1, weight=0.3)
    fusion.add_model(model2, weight=0.4)
    fusion.add_model(model3, weight=0.3)

    print("=== Model Fusion Test ===")
    info = fusion.get_fusion_info()
    print(f"Fusion info: {info}")

    print("\nSetting custom weights...")
    fusion.set_weights([0.2, 0.5, 0.3])
    info = fusion.get_fusion_info()
    print(f"Updated weights: {info['weights']}")
