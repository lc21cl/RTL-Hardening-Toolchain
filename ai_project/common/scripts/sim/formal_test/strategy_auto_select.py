#!/usr/bin/env python3
"""strategy_auto_select.py — 加固策略自动选择模块

基于设计特征和约束自动推荐最佳加固策略组合。

用法:
    from strategy_auto_select import StrategyAutoSelector

    selector = StrategyAutoSelector()
    recommendation = selector.recommend(rtl_content, constraints={"area_budget": 2.0})
    best_strategy = selector.select_best(rtl_content)
"""

import re
from typing import List, Dict, Any, Optional


class StrategyAutoSelector:
    """加固策略自动选择器。

    基于设计特征和约束自动推荐最佳加固策略组合。
    """

    def __init__(self):
        """初始化策略选择器。"""
        self._strategies = {
            "tmr": {
                "name": "Triple Modular Redundancy",
                "area_overhead": 3.0,
                "power_overhead": 3.0,
                "reliability": 5,
                "latency": 1,
                "best_for": ["register", "state_machine", "critical_path"],
                "description": "高可靠性，适合关键路径和状态机",
            },
            "ecc": {
                "name": "Error Correcting Code",
                "area_overhead": 1.4,
                "power_overhead": 1.5,
                "reliability": 4,
                "latency": 1,
                "best_for": ["memory", "data_path", "bus"],
                "description": "中等开销，适合数据路径和存储",
            },
            "dice": {
                "name": "Dual Interlocked Storage Cell",
                "area_overhead": 2.5,
                "power_overhead": 2.5,
                "reliability": 5,
                "latency": 0,
                "best_for": ["register", "memory_cell", "storage"],
                "description": "高可靠性，适合寄存器和存储单元",
            },
            "parity": {
                "name": "Parity Check",
                "area_overhead": 1.03,
                "power_overhead": 1.01,
                "reliability": 2,
                "latency": 0,
                "best_for": ["memory", "data_path", "non_critical"],
                "description": "低开销，适合非关键路径",
            },
            "tmr_ecc": {
                "name": "TMR with ECC",
                "area_overhead": 4.4,
                "power_overhead": 4.5,
                "reliability": 5,
                "latency": 2,
                "best_for": ["critical_path", "safety_critical", "high_reliability"],
                "description": "最高可靠性，适合安全关键应用",
            },
            "cnt_comp": {
                "name": "Counter Comparator",
                "area_overhead": 1.1,
                "power_overhead": 1.02,
                "reliability": 3,
                "latency": 0,
                "best_for": ["counter", "timer", "sequential_logic"],
                "description": "低开销，适合计数器和定时器",
            },
            "watchdog": {
                "name": "Watchdog Timer",
                "area_overhead": 1.05,
                "power_overhead": 1.03,
                "reliability": 2,
                "latency": 0,
                "best_for": ["controller", "processor", "state_machine"],
                "description": "监控异常，适合控制器",
            },
            "one_hot_fsm": {
                "name": "One-Hot FSM",
                "area_overhead": 1.1,
                "power_overhead": 1.2,
                "reliability": 4,
                "latency": 0,
                "best_for": ["state_machine", "controller"],
                "description": "高可靠性FSM，适合状态机",
            },
            "bch_ecc": {
                "name": "BCH ECC",
                "area_overhead": 1.8,
                "power_overhead": 1.8,
                "reliability": 4,
                "latency": 1,
                "best_for": ["memory", "data_path", "high_error_correction"],
                "description": "高纠错能力，适合存储",
            },
            "crc": {
                "name": "CRC",
                "area_overhead": 1.03,
                "power_overhead": 1.03,
                "reliability": 3,
                "latency": 0,
                "best_for": ["communication", "data_transfer", "bus"],
                "description": "检测错误，适合通信路径",
            },
            "tmr_dice": {
                "name": "TMR + DICE Hybrid",
                "area_overhead": 5.5,
                "power_overhead": 5.5,
                "reliability": 5,
                "latency": 1,
                "best_for": ["safety_critical", "high_reliability", "mission_critical"],
                "description": "最高可靠性混合方案",
            },
            "scrubbing": {
                "name": "Memory Scrubbing",
                "area_overhead": 1.02,
                "power_overhead": 1.015,
                "reliability": 3,
                "latency": 0,
                "best_for": ["memory", "storage", "large_data"],
                "description": "定期刷新，适合大容量存储",
            },
            "interleaving": {
                "name": "Bit Interleaving",
                "area_overhead": 1.01,
                "power_overhead": 1.005,
                "reliability": 2,
                "latency": 0,
                "best_for": ["memory", "bus", "data_path"],
                "description": "低开销，分散错误影响",
            },
        }

    def analyze_design(self, rtl_content: str) -> Dict[str, Any]:
        """分析 RTL 设计特征。

        Args:
            rtl_content: RTL 代码

        Returns:
            设计特征分析结果
        """
        features = {
            "num_modules": 0,
            "num_registers": 0,
            "num_always_blocks": 0,
            "num_assignments": 0,
            "has_memory": False,
            "has_fsm": False,
            "has_counter": False,
            "critical_path_length": 0,
            "total_bits": 0,
            "design_type": "unknown",
        }

        features["num_modules"] = len(re.findall(r"\bmodule\s+\w+", rtl_content))
        features["num_registers"] = len(re.findall(r"\breg\s+\[\d+:\d+\]\s+\w+", rtl_content))
        features["num_always_blocks"] = len(re.findall(r"\balways\s+@", rtl_content))
        features["num_assignments"] = len(re.findall(r"\bassign\s+\w+\s*=", rtl_content))

        features["has_memory"] = "memory" in rtl_content.lower() or "ram" in rtl_content.lower()
        features["has_fsm"] = "case" in rtl_content.lower() and "state" in rtl_content.lower()
        features["has_counter"] = "counter" in rtl_content.lower() or "count" in rtl_content.lower()

        width_matches = re.findall(r"\[(\d+):(\d+)\]", rtl_content)
        for msb, lsb in width_matches:
            features["total_bits"] += abs(int(msb) - int(lsb)) + 1

        if features["has_memory"]:
            features["design_type"] = "memory_intensive"
        elif features["has_fsm"]:
            features["design_type"] = "control_dominated"
        elif features["num_registers"] > 10:
            features["design_type"] = "register_intensive"
        else:
            features["design_type"] = "general_purpose"

        return features

    def score_strategy(
        self,
        strategy: str,
        design_features: Dict[str, Any],
        constraints: Dict[str, Any],
    ) -> float:
        """评估策略得分。

        Args:
            strategy: 策略名称
            design_features: 设计特征
            constraints: 约束条件

        Returns:
            策略得分
        """
        info = self._strategies.get(strategy, {})
        if not info:
            return 0.0

        score = 0.0

        area_budget = constraints.get("area_budget", float("inf"))
        if info["area_overhead"] <= area_budget:
            score += 30
        else:
            score += max(0, 30 - (info["area_overhead"] - area_budget) * 10)

        power_budget = constraints.get("power_budget", float("inf"))
        if info["power_overhead"] <= power_budget:
            score += 20
        else:
            score += max(0, 20 - (info["power_overhead"] - power_budget) * 10)

        reliability_requirement = constraints.get("reliability_requirement", 0)
        if info["reliability"] >= reliability_requirement:
            score += 30
        else:
            score += info["reliability"] * 5

        latency_budget = constraints.get("latency_budget", float("inf"))
        if info["latency"] <= latency_budget:
            score += 10
        else:
            score += max(0, 10 - (info["latency"] - latency_budget) * 5)

        design_type = design_features.get("design_type", "")
        if design_type in info["best_for"]:
            score += 10

        if design_features.get("has_memory") and "memory" in info["best_for"]:
            score += 5
        if design_features.get("has_fsm") and "state_machine" in info["best_for"]:
            score += 5
        if design_features.get("has_counter") and "counter" in info["best_for"]:
            score += 5

        return score

    def recommend(
        self,
        rtl_content: str,
        constraints: Optional[Dict[str, Any]] = None,
        top_n: int = 3,
    ) -> List[Dict[str, Any]]:
        """推荐最佳加固策略。

        Args:
            rtl_content: RTL 代码
            constraints: 约束条件（area_budget, power_budget, reliability_requirement, latency_budget）
            top_n: 返回前N个推荐策略

        Returns:
            推荐策略列表
        """
        constraints = constraints or {}
        design_features = self.analyze_design(rtl_content)

        scored_strategies = []
        for strategy, info in self._strategies.items():
            score = self.score_strategy(strategy, design_features, constraints)
            scored_strategies.append({
                "strategy": strategy,
                "name": info["name"],
                "score": score,
                "area_overhead": info["area_overhead"],
                "power_overhead": info["power_overhead"],
                "reliability": info["reliability"],
                "latency": info["latency"],
                "description": info["description"],
            })

        scored_strategies.sort(key=lambda x: x["score"], reverse=True)

        return scored_strategies[:top_n]

    def select_best(
        self,
        rtl_content: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """选择最佳策略。

        Args:
            rtl_content: RTL 代码
            constraints: 约束条件

        Returns:
            最佳策略信息
        """
        recommendations = self.recommend(rtl_content, constraints, top_n=1)
        return recommendations[0] if recommendations else {}

    def get_strategy_info(self, strategy: str) -> Dict[str, Any]:
        """获取策略详细信息。

        Args:
            strategy: 策略名称

        Returns:
            策略信息
        """
        return self._strategies.get(strategy, {})


if __name__ == "__main__":
    selector = StrategyAutoSelector()

    memory_rtl = """
module memory_module(
    input clk,
    input rst,
    input [7:0] addr,
    input [31:0] din,
    input we,
    output [31:0] dout
);
    reg [31:0] ram[0:255];
    always @(posedge clk) begin
        if (we) ram[addr] <= din;
        dout <= ram[addr];
    end
endmodule
"""

    fsm_rtl = """
module fsm_module(
    input clk,
    input rst,
    input start,
    input done,
    output reg [2:0] state
);
    parameter IDLE = 3'b001;
    parameter RUNNING = 3'b010;
    parameter FINISHED = 3'b100;
    always @(posedge clk or posedge rst) begin
        if (rst) state <= IDLE;
        else begin
            case(state)
                IDLE: if (start) state <= RUNNING;
                RUNNING: if (done) state <= FINISHED;
                FINISHED: state <= IDLE;
            endcase
        end
    end
endmodule
"""

    print("=== Memory Design Recommendation ===")
    design_features = selector.analyze_design(memory_rtl)
    print(f"Design type: {design_features['design_type']}")
    print(f"Has memory: {design_features['has_memory']}")
    recommendations = selector.recommend(memory_rtl, {"area_budget": 2.0})
    for rec in recommendations:
        print(f"  {rec['strategy']} ({rec['name']}): score={rec['score']:.1f}, area={rec['area_overhead']}x")

    print("\n=== FSM Design Recommendation ===")
    design_features = selector.analyze_design(fsm_rtl)
    print(f"Design type: {design_features['design_type']}")
    print(f"Has FSM: {design_features['has_fsm']}")
    recommendations = selector.recommend(fsm_rtl, {"reliability_requirement": 4})
    for rec in recommendations:
        print(f"  {rec['strategy']} ({rec['name']}): score={rec['score']:.1f}, reliability={rec['reliability']}")

    print("\n=== Best Strategy Selection ===")
    best = selector.select_best(memory_rtl)
    print(f"Best strategy: {best.get('strategy')} - {best.get('name')}")
