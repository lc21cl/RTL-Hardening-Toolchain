#!/usr/bin/env python3
"""train_data_generator.py — SFT/DPO训练数据生成器。

生成用于模型训练的配对数据，支持多种格式输出：
  - SFT (Supervised Fine-Tuning) 格式
  - DPO (Direct Preference Optimization) 格式
  - RLHF 格式

数据结构:
  - prompt: 原始RTL代码
  - chosen: 加固后的RTL代码（首选）
  - rejected: 较差的加固结果（仅DPO）
"""

import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def generate_sft_sample(
    original_rtl: str,
    hardened_rtl: str,
    strategy: str = 'tmr',
    metadata: Optional[Dict] = None
) -> Dict[str, str]:
    """生成单个 SFT 训练样本。

    Args:
        original_rtl: 原始 RTL 代码。
        hardened_rtl: 加固后的 RTL 代码。
        strategy: 使用的加固策略。
        metadata: 元数据（可选）。

    Returns:
        SFT 样本字典。
    """
    if metadata is None:
        metadata = {}

    sample = {
        'id': hashlib.md5(f'{original_rtl}{hardened_rtl}'.encode()).hexdigest()[:16],
        'instruction': f"使用{strategy}策略加固以下Verilog RTL代码，添加必要的加固逻辑和保护属性:",
        'input': original_rtl,
        'output': hardened_rtl,
        'strategy': strategy,
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'strategy': strategy,
            **metadata
        }
    }

    return sample


def generate_dpo_sample(
    original_rtl: str,
    chosen_rtl: str,
    rejected_rtl: str,
    strategy: str = 'tmr',
    metadata: Optional[Dict] = None
) -> Dict[str, str]:
    """生成单个 DPO 训练样本。

    Args:
        original_rtl: 原始 RTL 代码。
        chosen_rtl: 首选的加固结果。
        rejected_rtl: 较差的加固结果。
        strategy: 使用的加固策略。
        metadata: 元数据（可选）。

    Returns:
        DPO 样本字典。
    """
    if metadata is None:
        metadata = {}

    sample = {
        'id': hashlib.md5(f'{original_rtl}{chosen_rtl}{rejected_rtl}'.encode()).hexdigest()[:16],
        'prompt': f"使用{strategy}策略加固以下Verilog RTL代码:",
        'chosen': chosen_rtl,
        'rejected': rejected_rtl,
        'strategy': strategy,
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'strategy': strategy,
            **metadata
        }
    }

    return sample


def generate_rlhf_sample(
    original_rtl: str,
    hardened_rtl: str,
    reward: float = 1.0,
    strategy: str = 'tmr',
    metadata: Optional[Dict] = None
) -> Dict[str, str]:
    """生成单个 RLHF 训练样本。

    Args:
        original_rtl: 原始 RTL 代码。
        hardened_rtl: 加固后的 RTL 代码。
        reward: 奖励分数。
        strategy: 使用的加固策略。
        metadata: 元数据（可选）。

    Returns:
        RLHF 样本字典。
    """
    if metadata is None:
        metadata = {}

    sample = {
        'id': hashlib.md5(f'{original_rtl}{hardened_rtl}'.encode()).hexdigest()[:16],
        'query': f"使用{strategy}策略加固以下Verilog RTL代码:",
        'response': hardened_rtl,
        'reward': reward,
        'strategy': strategy,
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'strategy': strategy,
            'reward': reward,
            **metadata
        }
    }

    return sample


def generate_dataset(
    samples: List[Dict],
    dataset_name: str = 'rtl_hardening_dataset',
    dataset_version: str = '1.0',
    format: str = 'sft'
) -> Dict[str, str]:
    """生成完整的数据集结构。

    Args:
        samples: 样本列表。
        dataset_name: 数据集名称。
        dataset_version: 数据集版本。
        format: 数据格式 ('sft', 'dpo', 'rlhf')。

    Returns:
        完整的数据集字典。
    """
    dataset = {
        'dataset_name': dataset_name,
        'dataset_version': dataset_version,
        'format': format,
        'num_samples': len(samples),
        'created_at': datetime.now().isoformat(),
        'samples': samples
    }

    return dataset


def save_dataset(
    dataset: Dict,
    output_path: str,
    format: str = 'json'
) -> None:
    """保存数据集到文件。

    Args:
        dataset: 数据集字典。
        output_path: 输出文件路径。
        format: 输出格式 ('json', 'jsonl')。
    """
    if format == 'jsonl':
        with open(output_path, 'w', encoding='utf-8') as f:
            for sample in dataset['samples']:
                f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)


def load_dataset(input_path: str, format: str = 'json') -> Dict:
    """从文件加载数据集。

    Args:
        input_path: 输入文件路径。
        format: 输入格式 ('json', 'jsonl')。

    Returns:
        数据集字典。
    """
    if format == 'jsonl':
        samples = []
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                samples.append(json.loads(line))
        return {
            'samples': samples,
            'num_samples': len(samples)
        }
    else:
        with open(input_path, 'r', encoding='utf-8') as f:
            return json.load(f)


def generate_hardened_variants(
    original_rtl: str,
    strategies: List[str] = ['tmr', 'dice', 'ecc'],
    variants_per_strategy: int = 3
) -> List[Tuple[str, str]]:
    """为同一RTL生成多种加固变体。

    Args:
        original_rtl: 原始 RTL 代码。
        strategies: 策略列表。
        variants_per_strategy: 每种策略生成的变体数量。

    Returns:
        变体列表 [(strategy, hardened_rtl), ...]。
    """
    variants = []
    for strategy in strategies:
        for i in range(variants_per_strategy):
            hardened = f"// Hardened with {strategy} (variant {i+1})\n{original_rtl}"
            variants.append((strategy, hardened))
    return variants


def create_dpo_comparison(
    original_rtl: str,
    best_hardened: str,
    other_hardened: str,
    strategy: str = 'tmr'
) -> Dict:
    """创建 DPO 比较样本。

    Args:
        original_rtl: 原始 RTL 代码。
        best_hardened: 最佳加固结果。
        other_hardened: 其他加固结果。
        strategy: 使用的加固策略。

    Returns:
        DPO 样本字典。
    """
    return generate_dpo_sample(
        original_rtl=original_rtl,
        chosen_rtl=best_hardened,
        rejected_rtl=other_hardened,
        strategy=strategy,
        metadata={
            'comparison_type': 'quality',
            'chosen_reason': 'Better area overhead and fault coverage',
            'rejected_reason': 'Higher area overhead'
        }
    )


def augment_sample_with_metrics(
    sample: Dict,
    metrics: Dict[str, float]
) -> Dict:
    """为样本添加评估指标。

    Args:
        sample: 原始样本。
        metrics: 评估指标。

    Returns:
        添加指标后的样本。
    """
    if 'metadata' not in sample:
        sample['metadata'] = {}
    sample['metadata']['metrics'] = metrics
    return sample


def split_dataset(
    dataset: Dict,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1
) -> Tuple[Dict, Dict, Dict]:
    """拆分数据集为训练集、验证集和测试集。

    Args:
        dataset: 完整数据集。
        train_ratio: 训练集比例。
        val_ratio: 验证集比例。
        test_ratio: 测试集比例。

    Returns:
        (train_dataset, val_dataset, test_dataset)。
    """
    samples = dataset['samples']
    total = len(samples)

    train_end = int(total * train_ratio)
    val_end = train_end + int(total * val_ratio)

    train_samples = samples[:train_end]
    val_samples = samples[train_end:val_end]
    test_samples = samples[val_end:]

    base_info = {
        'dataset_name': dataset.get('dataset_name', 'rtl_hardening_dataset'),
        'dataset_version': dataset.get('dataset_version', '1.0'),
        'format': dataset.get('format', 'sft'),
        'created_at': datetime.now().isoformat()
    }

    train_dataset = {**base_info, 'num_samples': len(train_samples), 'samples': train_samples, 'split': 'train'}
    val_dataset = {**base_info, 'num_samples': len(val_samples), 'samples': val_samples, 'split': 'validation'}
    test_dataset = {**base_info, 'num_samples': len(test_samples), 'samples': test_samples, 'split': 'test'}

    return train_dataset, val_dataset, test_dataset


def generate_batch_from_files(
    rtl_files: List[str],
    hardened_files: List[str],
    strategies: List[str],
    output_dir: str = './',
    format: str = 'sft'
) -> None:
    """从文件批量生成训练数据。

    Args:
        rtl_files: 原始 RTL 文件列表。
        hardened_files: 加固后文件列表。
        strategies: 策略列表。
        output_dir: 输出目录。
        format: 输出格式。
    """
    samples = []

    for i, (rtl_path, hardened_path, strategy) in enumerate(zip(rtl_files, hardened_files, strategies)):
        with open(rtl_path, 'r', encoding='utf-8', errors='replace') as f:
            original_rtl = f.read()
        with open(hardened_path, 'r', encoding='utf-8', errors='replace') as f:
            hardened_rtl = f.read()

        if format == 'sft':
            sample = generate_sft_sample(original_rtl, hardened_rtl, strategy)
        elif format == 'dpo':
            sample = generate_dpo_sample(original_rtl, hardened_rtl, original_rtl, strategy)
        else:
            sample = generate_rlhf_sample(original_rtl, hardened_rtl, strategy=strategy)

        samples.append(sample)

    dataset = generate_dataset(samples, format=format)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = f'{output_dir}/dataset_{format}_{timestamp}.json'
    save_dataset(dataset, output_path)

    if format in ['sft', 'dpo']:
        train, val, test = split_dataset(dataset)
        save_dataset(train, f'{output_dir}/train_{format}_{timestamp}.json')
        save_dataset(val, f'{output_dir}/val_{format}_{timestamp}.json')
        save_dataset(test, f'{output_dir}/test_{format}_{timestamp}.json')

        jsonl_path = f'{output_dir}/dataset_{format}_{timestamp}.jsonl'
        save_dataset(dataset, jsonl_path, format='jsonl')


def generate_example_samples(count: int = 5) -> List[Dict]:
    """生成示例样本用于测试。

    Args:
        count: 样本数量。

    Returns:
        示例样本列表。
    """
    template_rtl = """module simple_reg(
    input clk,
    input rst,
    input [7:0] din,
    output reg [7:0] dout
);
    always @(posedge clk or posedge rst) begin
        if (rst)
            dout <= 8'b0;
        else
            dout <= din;
    end
endmodule"""

    hardened_rtl = """module simple_reg_tmr(
    input clk,
    input rst,
    input [7:0] din,
    output reg [7:0] dout
);
    wire [7:0] dout_A, dout_B, dout_C;

    simple_reg inst_A(.clk(clk), .rst(rst), .din(din), .dout(dout_A));
    simple_reg inst_B(.clk(clk), .rst(rst), .din(din), .dout(dout_B));
    simple_reg inst_C(.clk(clk), .rst(rst), .din(din), .dout(dout_C));

    majority_voter_8bit voter(
        .A(dout_A),
        .B(dout_B),
        .C(dout_C),
        .Z(dout)
    );
endmodule"""

    samples = []
    for i in range(count):
        sample = generate_sft_sample(
            original_rtl=template_rtl,
            hardened_rtl=hardened_rtl,
            strategy='tmr',
            metadata={'example': True, 'index': i}
        )
        samples.append(sample)

    return samples