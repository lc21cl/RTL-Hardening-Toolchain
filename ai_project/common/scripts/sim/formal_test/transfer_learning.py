#!/usr/bin/env python3
"""transfer_learning.py — 迁移学习模块

支持从预训练模型进行迁移学习，减少训练数据需求。

用法:
    from transfer_learning import TransferLearner

    learner = TransferLearner()
    learner.load_pretrained("pretrained_model.pt")
    learner.fine_tune(new_dataset)
    learner.save_model("fine_tuned_model.pt")
"""

import os
import sys
import torch
import torch.nn as nn
from typing import Dict, Any, Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


class TransferLearner:
    """迁移学习器。

    支持从预训练模型进行迁移学习。
    """

    def __init__(self, model: Optional[nn.Module] = None):
        """初始化迁移学习器。

        Args:
            model: 可选的基础模型
        """
        self._model = model
        self._pretrained_model = None
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def load_pretrained(self, model_path: str) -> bool:
        """加载预训练模型。

        Args:
            model_path: 预训练模型路径

        Returns:
            是否加载成功
        """
        if not os.path.isfile(model_path):
            return False

        try:
            checkpoint = torch.load(model_path, map_location=self._device, weights_only=True)

            if isinstance(checkpoint, nn.Module):
                self._pretrained_model = checkpoint
                self._model = checkpoint
            elif isinstance(checkpoint, dict):
                if self._model is None:
                    from graphsage_model import GraphSAGE
                    self._model = GraphSAGE(
                        in_channels=checkpoint.get("in_channels", 64),
                        hidden_channels=checkpoint.get("hidden_channels", 64),
                        out_channels=checkpoint.get("out_channels", 2),
                        num_layers=checkpoint.get("num_layers", 2),
                    )

                if "model_state_dict" in checkpoint:
                    self._model.load_state_dict(checkpoint["model_state_dict"])
                elif "state_dict" in checkpoint:
                    self._model.load_state_dict(checkpoint["state_dict"])
                else:
                    self._model.load_state_dict(checkpoint)

                self._pretrained_model = self._model

            self._model.to(self._device)
            return True
        except Exception:
            return False

    def freeze_layers(self, num_layers_to_freeze: int = 1):
        """冻结模型层。

        Args:
            num_layers_to_freeze: 要冻结的层数
        """
        if self._model is None:
            return

        layers = list(self._model.children())
        for i, layer in enumerate(layers[:num_layers_to_freeze]):
            for param in layer.parameters():
                param.requires_grad = False

    def unfreeze_layers(self):
        """解冻所有模型层。"""
        if self._model is None:
            return

        for param in self._model.parameters():
            param.requires_grad = True

    def fine_tune(
        self,
        dataloader,
        epochs: int = 10,
        lr: float = 1e-4,
        freeze_layers: int = 1,
    ) -> Dict[str, Any]:
        """微调模型。

        Args:
            dataloader: 数据加载器
            epochs: 训练轮数
            lr: 学习率
            freeze_layers: 冻结的层数

        Returns:
            训练结果
        """
        if self._model is None:
            return {"error": "No model loaded"}

        self.freeze_layers(freeze_layers)

        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(
            filter(lambda p: p.requires_grad, self._model.parameters()),
            lr=lr,
        )

        self._model.train()
        losses = []
        accuracies = []

        for epoch in range(epochs):
            epoch_loss = 0.0
            correct = 0
            total = 0

            for batch in dataloader:
                data = batch.to(self._device)
                optimizer.zero_grad()

                out = self._model(data.x, data.edge_index)
                loss = criterion(out[data.train_mask], data.y[data.train_mask])
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()
                pred = out.argmax(dim=1)
                correct += int((pred[data.train_mask] == data.y[data.train_mask]).sum())
                total += int(data.train_mask.sum())

            losses.append(epoch_loss / len(dataloader))
            accuracies.append(correct / total if total > 0 else 0)

        self.unfreeze_layers()

        return {
            "losses": losses,
            "accuracies": accuracies,
            "final_loss": losses[-1] if losses else 0,
            "final_accuracy": accuracies[-1] if accuracies else 0,
            "epochs": epochs,
        }

    def feature_extraction(self, dataloader) -> torch.Tensor:
        """特征提取。

        Args:
            dataloader: 数据加载器

        Returns:
            提取的特征
        """
        if self._model is None:
            return torch.tensor([])

        self._model.eval()
        features = []

        with torch.no_grad():
            for batch in dataloader:
                data = batch.to(self._device)
                out = self._model(data.x, data.edge_index)
                features.append(out.cpu())

        return torch.cat(features)

    def save_model(self, path: str):
        """保存模型。

        Args:
            path: 保存路径
        """
        if self._model is not None:
            torch.save({
                "model_state_dict": self._model.state_dict(),
            }, path)

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息。

        Returns:
            模型信息
        """
        if self._model is None:
            return {"error": "No model loaded"}

        params = sum(p.numel() for p in self._model.parameters())
        trainable_params = sum(p.numel() for p in self._model.parameters() if p.requires_grad)

        return {
            "model_type": type(self._model).__name__,
            "total_params": params,
            "trainable_params": trainable_params,
            "device": str(self._device),
            "has_pretrained": self._pretrained_model is not None,
        }


if __name__ == "__main__":
    learner = TransferLearner()

    print("=== Transfer Learner Test ===")

    learner_info = learner.get_model_info()
    print(f"Initial state: {learner_info}")

    print("\nLoading pretrained model...")
    success = learner.load_pretrained("test_model.pt")
    print(f"Load success: {success}")

    learner_info = learner.get_model_info()
    print(f"Model info: {learner_info}")

    print("\nFreezing layers...")
    learner.freeze_layers(1)
    learner_info = learner.get_model_info()
    print(f"After freeze: {learner_info}")
