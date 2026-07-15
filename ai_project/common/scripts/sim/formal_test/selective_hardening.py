#!/usr/bin/env python3
"""selective_hardening.py — 选择性加固策略模块。

根据脆弱性评分选择性加固寄存器，参考FT-Pilot方法。

功能:
  - 根据脆弱性评分选择加固策略
  - 实现多策略混合加固
  - 优化面积和可靠性的权衡
"""

from typing import Dict, List, Optional, Tuple


class SelectiveHardeningStrategy:
    """选择性加固策略类。"""

    def __init__(self):
        self.vulnerability_thresholds = {
            'tmr': 0.7,
            'dice': 0.5,
            'ecc': 0.3,
            'none': 0.0
        }
        self.strategy_priority = ['tmr', 'dice', 'ecc', 'none']

    def select_strategy(self, vulnerability_score: float) -> str:
        """根据脆弱性评分选择加固策略。

        Args:
            vulnerability_score: 脆弱性评分 (0-1)。

        Returns:
            加固策略名称。
        """
        for strategy in self.strategy_priority:
            threshold = self.vulnerability_thresholds[strategy]
            if vulnerability_score >= threshold:
                return strategy
        return 'none'

    def update_thresholds(self, thresholds: Dict[str, float]) -> None:
        """更新阈值配置。

        Args:
            thresholds: 新的阈值配置。
        """
        self.vulnerability_thresholds.update(thresholds)

    def set_priority(self, priority: List[str]) -> None:
        """设置策略优先级。

        Args:
            priority: 策略优先级列表。
        """
        self.strategy_priority = priority


def apply_selective_hardening(
    vulnerability_results: Dict[str, Dict],
    strategy_map: Dict[str, str],
    strategy: Optional[SelectiveHardeningStrategy] = None
) -> Dict[str, str]:
    """应用选择性加固策略。

    Args:
        vulnerability_results: 脆弱性预测结果。
        strategy_map: 原始策略映射。
        strategy: 选择性加固策略（可选）。

    Returns:
        更新后的策略映射。
    """
    if strategy is None:
        strategy = SelectiveHardeningStrategy()

    for reg_name, data in vulnerability_results.items():
        score = data['vulnerability_score']
        selected_strategy = strategy.select_strategy(score)
        if selected_strategy != 'none':
            strategy_map[reg_name] = selected_strategy

    return strategy_map


def optimize_hardening_budget(
    vulnerability_results: Dict[str, Dict],
    max_area_overhead: float = 200.0,
    min_reliability: float = 0.95
) -> Dict[str, str]:
    """根据面积预算优化加固策略。

    Args:
        vulnerability_results: 脆弱性预测结果。
        max_area_overhead: 最大面积开销百分比。
        min_reliability: 最小可靠性要求。

    Returns:
        优化后的策略映射。
    """
    strategy_cost = {
        'tmr': 3.0,
        'dice': 2.0,
        'ecc': 1.5,
        'none': 1.0
    }

    strategy_reliability = {
        'tmr': 0.999,
        'dice': 0.99,
        'ecc': 0.98,
        'none': 0.90
    }

    sorted_results = sorted(
        vulnerability_results.items(),
        key=lambda x: -x[1]['vulnerability_score']
    )

    strategy_map = {}
    current_overhead = 100.0
    current_reliability = 0.0

    for reg_name, data in sorted_results:
        best_strategy = None
        best_score = float('-inf')

        for strat in ['tmr', 'dice', 'ecc', 'none']:
            new_overhead = current_overhead * (strategy_cost[strat] / strategy_cost.get('none', 1.0))
            if new_overhead <= max_area_overhead:
                weighted_score = (data['vulnerability_score'] * strategy_reliability[strat] * 100)
                if weighted_score > best_score:
                    best_score = weighted_score
                    best_strategy = strat

        if best_strategy:
            strategy_map[reg_name] = best_strategy
            current_overhead *= (strategy_cost[best_strategy] / strategy_cost.get('none', 1.0))

    return strategy_map


def generate_hybrid_strategy(
    vulnerability_results: Dict[str, Dict],
    tmr_ratio: float = 0.3,
    dice_ratio: float = 0.4,
    ecc_ratio: float = 0.3
) -> Dict[str, str]:
    """生成混合加固策略。

    Args:
        vulnerability_results: 脆弱性预测结果。
        tmr_ratio: TMR加固比例。
        dice_ratio: DICE加固比例。
        ecc_ratio: ECC加固比例。

    Returns:
        混合策略映射。
    """
    sorted_results = sorted(
        vulnerability_results.items(),
        key=lambda x: -x[1]['vulnerability_score']
    )

    total = len(sorted_results)
    tmr_count = int(total * tmr_ratio)
    dice_count = int(total * dice_ratio)
    ecc_count = int(total * ecc_ratio)

    strategy_map = {}

    for i, (reg_name, data) in enumerate(sorted_results):
        if i < tmr_count:
            strategy_map[reg_name] = 'tmr'
        elif i < tmr_count + dice_count:
            strategy_map[reg_name] = 'dice'
        elif i < tmr_count + dice_count + ecc_count:
            strategy_map[reg_name] = 'ecc'

    return strategy_map


def calculate_effectiveness(
    vulnerability_results: Dict[str, Dict],
    strategy_map: Dict[str, str]
) -> Dict[str, float]:
    """计算加固效果。

    Args:
        vulnerability_results: 脆弱性预测结果。
        strategy_map: 策略映射。

    Returns:
        效果统计。
    """
    strategy_reliability = {
        'tmr': 0.999,
        'dice': 0.99,
        'ecc': 0.98,
        'none': 0.90
    }

    strategy_cost = {
        'tmr': 3.0,
        'dice': 2.0,
        'ecc': 1.5,
        'none': 1.0
    }

    total_registers = len(vulnerability_results)
    protected_count = len(strategy_map)

    weighted_reliability = 0.0
    total_cost = 0.0

    for reg_name, data in vulnerability_results.items():
        strat = strategy_map.get(reg_name, 'none')
        weighted_reliability += data['vulnerability_score'] * strategy_reliability[strat]
        total_cost += strategy_cost[strat]

    avg_reliability = weighted_reliability / total_registers if total_registers > 0 else 0.0
    avg_cost = total_cost / total_registers if total_registers > 0 else 0.0

    return {
        'total_registers': total_registers,
        'protected_registers': protected_count,
        'protection_ratio': protected_count / total_registers if total_registers > 0 else 0.0,
        'average_reliability': avg_reliability,
        'average_area_overhead': (avg_cost - 1.0) * 100,
        'effectiveness_score': avg_reliability * (1 - (avg_cost - 1.0))
    }


def generate_strategy_report(
    vulnerability_results: Dict[str, Dict],
    strategy_map: Dict[str, str],
    effectiveness: Optional[Dict[str, float]] = None
) -> str:
    """生成策略报告。

    Args:
        vulnerability_results: 脆弱性预测结果。
        strategy_map: 策略映射。
        effectiveness: 效果统计（可选）。

    Returns:
        报告文本。
    """
    if effectiveness is None:
        effectiveness = calculate_effectiveness(vulnerability_results, strategy_map)

    report_lines = [
        "=" * 70,
        "选择性加固策略报告",
        "=" * 70,
        ""
    ]

    report_lines.append(f"寄存器总数: {effectiveness['total_registers']}")
    report_lines.append(f"加固寄存器数: {effectiveness['protected_registers']}")
    report_lines.append(f"加固比例: {effectiveness['protection_ratio'] * 100:.1f}%")
    report_lines.append(f"平均可靠性: {effectiveness['average_reliability']:.4f}")
    report_lines.append(f"平均面积开销: {effectiveness['average_area_overhead']:.1f}%")
    report_lines.append(f"效果评分: {effectiveness['effectiveness_score']:.4f}")
    report_lines.append("")

    report_lines.append("-" * 70)
    report_lines.append("寄存器加固策略详情:")
    report_lines.append("-" * 70)

    sorted_results = sorted(
        vulnerability_results.items(),
        key=lambda x: -x[1]['vulnerability_score']
    )

    for reg_name, data in sorted_results:
        strat = strategy_map.get(reg_name, 'none')
        status = {
            'tmr': '🔴 TMR',
            'dice': '🟠 DICE',
            'ecc': '🟡 ECC',
            'none': '⚪ 未加固'
        }.get(strat, '⚪ 未加固')

        report_lines.append(
            f"{reg_name:20s} | 评分: {data['vulnerability_score']:.4f} | {status}"
        )

    report_lines.append("")
    report_lines.append("-" * 70)
    report_lines.append("策略分布统计:")
    report_lines.append("-" * 70)

    strategy_counts = {}
    for strat in strategy_map.values():
        strategy_counts[strat] = strategy_counts.get(strat, 0) + 1

    for strat, count in strategy_counts.items():
        percentage = count / effectiveness['total_registers'] * 100 if effectiveness['total_registers'] > 0 else 0
        report_lines.append(f"  {strat.upper()}: {count} ({percentage:.1f}%)")

    report_lines.append("")
    report_lines.append("=" * 70)

    return '\n'.join(report_lines)


def find_optimal_strategy(
    vulnerability_results: Dict[str, Dict],
    objectives: Dict[str, float] = None
) -> Dict[str, str]:
    """寻找最优加固策略。

    Args:
        vulnerability_results: 脆弱性预测结果。
        objectives: 目标权重 {'reliability': 0.5, 'area': 0.5}。

    Returns:
        最优策略映射。
    """
    if objectives is None:
        objectives = {'reliability': 0.7, 'area': 0.3}

    best_strategy_map = None
    best_score = float('-inf')

    ratios = [
        (0.2, 0.3, 0.5),
        (0.3, 0.4, 0.3),
        (0.4, 0.4, 0.2),
        (0.2, 0.5, 0.3),
        (0.3, 0.3, 0.4),
    ]

    for tmr_ratio, dice_ratio, ecc_ratio in ratios:
        strategy_map = generate_hybrid_strategy(
            vulnerability_results,
            tmr_ratio,
            dice_ratio,
            ecc_ratio
        )
        effectiveness = calculate_effectiveness(vulnerability_results, strategy_map)

        score = (objectives['reliability'] * effectiveness['average_reliability'] +
                 objectives['area'] * (1 - effectiveness['average_area_overhead'] / 300))

        if score > best_score:
            best_score = score
            best_strategy_map = strategy_map

    return best_strategy_map


def compare_strategies(
    vulnerability_results: Dict[str, Dict],
    strategies: List[Dict[str, str]]
) -> List[Dict[str, float]]:
    """比较多种加固策略。

    Args:
        vulnerability_results: 脆弱性预测结果。
        strategies: 策略映射列表。

    Returns:
        各策略效果统计列表。
    """
    results = []
    for i, strategy_map in enumerate(strategies):
        effectiveness = calculate_effectiveness(vulnerability_results, strategy_map)
        effectiveness['strategy_index'] = i
        results.append(effectiveness)

    results.sort(key=lambda x: -x['effectiveness_score'])
    return results