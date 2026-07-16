#!/usr/bin/env python3
"""multi_objective_optimization.py — 多目标优化策略模块。

实现基于NSGA-II的多目标优化算法，用于面积、可靠性、性能的权衡。

功能:
  - NSGA-II算法实现
  - 帕累托前沿计算
  - 多目标策略选择
"""

import random
import numpy as np
from typing import Dict, List, Optional, Tuple


class Solution:
    """优化解类。"""

    def __init__(self, strategy_map: Dict[str, str], objectives: List[float]):
        """初始化解。

        Args:
            strategy_map: 策略映射。
            objectives: 目标函数值列表。
        """
        self.strategy_map = strategy_map
        self.objectives = objectives
        self.rank = 0
        self.crowding_distance = 0.0


class NSGAII:
    """NSGA-II多目标优化算法。"""

    def __init__(
        self,
        population_size: int = 50,
        generations: int = 100,
        crossover_rate: float = 0.8,
        mutation_rate: float = 0.1
    ):
        """初始化NSGA-II。

        Args:
            population_size: 种群大小。
            generations: 迭代代数。
            crossover_rate: 交叉概率。
            mutation_rate: 变异概率。
        """
        self.population_size = population_size
        self.generations = generations
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate

    def _dominates(self, a: Solution, b: Solution) -> bool:
        """判断解a是否支配解b。

        Args:
            a: 解a。
            b: 解b。

        Returns:
            True如果a支配b。
        """
        better_in_all = True
        better_in_at_least_one = False

        for i in range(len(a.objectives)):
            if a.objectives[i] > b.objectives[i]:
                better_in_all = False
            elif a.objectives[i] < b.objectives[i]:
                better_in_at_least_one = True

        return better_in_all and better_in_at_least_one

    def _fast_non_dominated_sort(self, population: List[Solution]) -> List[List[Solution]]:
        """快速非支配排序。

        Args:
            population: 种群。

        Returns:
            分层后的种群列表。
        """
        fronts = [[]]

        for p in population:
            p.domination_count = 0
            p.dominated_solutions = []

            for q in population:
                if self._dominates(p, q):
                    p.dominated_solutions.append(q)
                elif self._dominates(q, p):
                    p.domination_count += 1

            if p.domination_count == 0:
                p.rank = 0
                fronts[0].append(p)

        i = 0
        while len(fronts[i]) > 0:
            next_front = []

            for p in fronts[i]:
                for q in p.dominated_solutions:
                    q.domination_count -= 1
                    if q.domination_count == 0:
                        q.rank = i + 1
                        next_front.append(q)

            i += 1
            fronts.append(next_front)

        return fronts

    def _calculate_crowding_distance(self, front: List[Solution]) -> None:
        """计算拥挤度距离。

        Args:
            front: 前沿解列表。
        """
        if len(front) == 0:
            return

        num_objectives = len(front[0].objectives)

        for p in front:
            p.crowding_distance = 0.0

        for i in range(num_objectives):
            front.sort(key=lambda x: x.objectives[i])
            front[0].crowding_distance = float('inf')
            front[-1].crowding_distance = float('inf')

            obj_range = front[-1].objectives[i] - front[0].objectives[i]
            if obj_range == 0:
                continue

            for j in range(1, len(front) - 1):
                front[j].crowding_distance += (
                    front[j + 1].objectives[i] - front[j - 1].objectives[i]
                ) / obj_range

    def _crowding_comparison(self, a: Solution, b: Solution) -> bool:
        """拥挤度比较。

        Args:
            a: 解a。
            b: 解b。

        Returns:
            True如果a优于b。
        """
        if a.rank < b.rank:
            return True
        elif a.rank == b.rank and a.crowding_distance > b.crowding_distance:
            return True
        return False

    def _crossover(self, parent1: Solution, parent2: Solution, signals: List[str]) -> Solution:
        """交叉操作。

        Args:
            parent1: 父代1。
            parent2: 父代2。
            signals: 信号列表。

        Returns:
            子代解。
        """
        child_map = {}
        for sig in signals:
            if random.random() < 0.5:
                child_map[sig] = parent1.strategy_map.get(sig, 'none')
            else:
                child_map[sig] = parent2.strategy_map.get(sig, 'none')
        return Solution(child_map, [0.0, 0.0, 0.0])

    def _mutate(self, solution: Solution, strategies: List[str]) -> Solution:
        """变异操作。

        Args:
            solution: 解。
            strategies: 可用策略列表。

        Returns:
            变异后的解。
        """
        for sig in solution.strategy_map:
            if random.random() < self.mutation_rate:
                solution.strategy_map[sig] = random.choice(strategies)
        return solution

    def optimize(
        self,
        signals: List[str],
        strategies: List[str],
        evaluate_func
    ) -> List[Solution]:
        """执行优化。

        Args:
            signals: 信号列表。
            strategies: 可用策略列表。
            evaluate_func: 评估函数。

        Returns:
            帕累托前沿解列表。
        """
        population = []

        for _ in range(self.population_size):
            strategy_map = {sig: random.choice(strategies) for sig in signals}
            objectives = evaluate_func(strategy_map)
            population.append(Solution(strategy_map, objectives))

        for gen in range(self.generations):
            fronts = self._fast_non_dominated_sort(population)

            for front in fronts:
                self._calculate_crowding_distance(front)

            new_population = []
            i = 0

            while i < len(fronts) and len(new_population) + len(fronts[i]) <= self.population_size:
                new_population.extend(fronts[i])
                i += 1

            if len(new_population) < self.population_size and i < len(fronts):
                fronts[i].sort(key=lambda x: (-x.crowding_distance, x.rank))
                remaining = self.population_size - len(new_population)
                new_population.extend(fronts[i][:remaining])

            parents = new_population.copy()
            offspring = []

            while len(offspring) < self.population_size:
                if random.random() < self.crossover_rate:
                    parent1 = random.choice(parents)
                    parent2 = random.choice(parents)
                    child = self._crossover(parent1, parent2, signals)
                    child.objectives = evaluate_func(child.strategy_map)
                    offspring.append(child)

                if len(offspring) < self.population_size and random.random() < self.mutation_rate:
                    parent = random.choice(parents)
                    child = Solution(parent.strategy_map.copy(), parent.objectives.copy())
                    child = self._mutate(child, strategies)
                    child.objectives = evaluate_func(child.strategy_map)
                    offspring.append(child)

            population = new_population + offspring

        final_fronts = self._fast_non_dominated_sort(population)

        return final_fronts[0]


def evaluate_hardening_strategy(
    strategy_map: Dict[str, str],
    vulnerability_scores: Dict[str, float],
    area_weights: Dict[str, float] = None,
    reliability_weights: Dict[str, float] = None
) -> List[float]:
    """评估加固策略。

    Args:
        strategy_map: 策略映射。
        vulnerability_scores: 脆弱性评分。
        area_weights: 面积权重。
        reliability_weights: 可靠性权重。

    Returns:
        目标函数值列表 [area_overhead, reliability_loss, performance_impact]。
    """
    if area_weights is None:
        area_weights = {'tmr': 3.0, 'dice': 2.5, 'ecc': 1.5, 'parity': 0.1, 'none': 1.0}

    if reliability_weights is None:
        reliability_weights = {'tmr': 0.999, 'dice': 0.99, 'ecc': 0.98, 'parity': 0.95, 'none': 0.90}

    total_area = 0.0
    total_reliability = 0.0
    total_performance = 0.0

    for sig, strat in strategy_map.items():
        score = vulnerability_scores.get(sig, 0.5)
        total_area += area_weights.get(strat, 1.0) * score
        total_reliability += (1 - reliability_weights.get(strat, 0.9)) * score
        total_performance += area_weights.get(strat, 1.0) * 0.1

    avg_area = total_area / len(strategy_map) if strategy_map else 1.0
    avg_reliability = total_reliability / len(strategy_map) if strategy_map else 0.0
    avg_performance = total_performance / len(strategy_map) if strategy_map else 0.0

    return [avg_area, avg_reliability, avg_performance]


def find_pareto_optimal_strategies(
    signals: List[str],
    vulnerability_scores: Dict[str, float],
    strategies: List[str] = None
) -> List[Dict[str, str]]:
    """寻找帕累托最优策略。

    Args:
        signals: 信号列表。
        vulnerability_scores: 脆弱性评分。
        strategies: 可用策略列表。

    Returns:
        帕累托最优策略列表。
    """
    if strategies is None:
        strategies = ['tmr', 'dice', 'ecc', 'parity', 'none']

    def evaluate_func(strategy_map):
        return evaluate_hardening_strategy(strategy_map, vulnerability_scores)

    nsga = NSGAII(population_size=30, generations=50)
    pareto_front = nsga.optimize(signals, strategies, evaluate_func)

    return [sol.strategy_map for sol in pareto_front]


def select_best_strategy(
    pareto_strategies: List[Dict[str, str]],
    vulnerability_scores: Dict[str, float],
    objective_weights: List[float] = None
) -> Dict[str, str]:
    """根据目标权重选择最优策略。

    Args:
        pareto_strategies: 帕累托最优策略列表。
        vulnerability_scores: 脆弱性评分。
        objective_weights: 目标权重 [area, reliability, performance]。

    Returns:
        最优策略映射。
    """
    if objective_weights is None:
        objective_weights = [0.3, 0.5, 0.2]

    best_strategy = None
    best_score = float('inf')

    for strategy_map in pareto_strategies:
        objectives = evaluate_hardening_strategy(strategy_map, vulnerability_scores)
        weighted_score = sum(w * o for w, o in zip(objective_weights, objectives))

        if weighted_score < best_score:
            best_score = weighted_score
            best_strategy = strategy_map

    return best_strategy


def generate_pareto_report(
    pareto_strategies: List[Dict[str, str]],
    vulnerability_scores: Dict[str, float]
) -> str:
    """生成帕累托前沿报告。

    Args:
        pareto_strategies: 帕累托最优策略列表。
        vulnerability_scores: 脆弱性评分。

    Returns:
        报告文本。
    """
    report_lines = [
        "=" * 70,
        "多目标优化帕累托前沿报告",
        "=" * 70,
        ""
    ]

    report_lines.append(f"帕累托最优解数量: {len(pareto_strategies)}")
    report_lines.append("")

    for i, strategy_map in enumerate(pareto_strategies):
        objectives = evaluate_hardening_strategy(strategy_map, vulnerability_scores)
        report_lines.append(f"解 {i+1}:")
        report_lines.append(f"  面积开销: {objectives[0]:.4f}")
        report_lines.append(f"  可靠性损失: {objectives[1]:.4f}")
        report_lines.append(f"  性能影响: {objectives[2]:.4f}")

        strategy_counts = {}
        for strat in strategy_map.values():
            strategy_counts[strat] = strategy_counts.get(strat, 0) + 1

        report_lines.append(f"  策略分布: {strategy_counts}")
        report_lines.append("")

    report_lines.append("=" * 70)

    return '\n'.join(report_lines)