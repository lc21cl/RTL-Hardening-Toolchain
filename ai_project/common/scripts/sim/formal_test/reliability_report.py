#!/usr/bin/env python3
"""reliability_report.py — 可靠性分析报告模块

生成完整的可靠性分析报告，包含 AVF、MTBF、故障率等指标。

用法:
    from reliability_report import ReliabilityAnalyzer

    analyzer = ReliabilityAnalyzer()
    report = analyzer.generate_report(vulnerability_results, hardened_rtl)
"""

import json
from typing import List, Dict, Any


class ReliabilityAnalyzer:
    """可靠性分析器。

    计算 AVF、MTBF、故障率等可靠性指标，生成分析报告。
    """

    def __init__(self):
        """初始化可靠性分析器。"""
        self._reports: List[Dict[str, Any]] = []

    def _calculate_avf(self, vulnerability_score: float) -> float:
        """计算架构脆弱性因子 (AVF)。

        Args:
            vulnerability_score: 脆弱性分数

        Returns:
            AVF 值
        """
        base_avf = vulnerability_score * 0.8
        return min(max(base_avf, 0.01), 0.99)

    def _calculate_failure_rate(self, avf: float, node_count: int) -> float:
        """计算故障率。

        Args:
            avf: 架构脆弱性因子
            node_count: 节点数

        Returns:
            故障率 (FIT)
        """
        base_rate = 100.0
        return avf * node_count * base_rate

    def _calculate_mtbf(self, failure_rate: float) -> float:
        """计算平均无故障时间 (MTBF)。

        Args:
            failure_rate: 故障率 (FIT)

        Returns:
            MTBF (小时)
        """
        if failure_rate <= 0:
            return float("inf")
        return 1e9 / (failure_rate * 8760)

    def _estimate_area_overhead(self, strategy: str) -> float:
        """估算面积开销。

        Args:
            strategy: 加固策略

        Returns:
            面积开销比例
        """
        overheads = {
            "tmr": 3.0,
            "ecc": 1.4,
            "dice": 2.5,
            "parity": 1.03,
            "tmr_ecc": 4.4,
            "cnt_comp": 1.1,
            "watchdog": 1.05,
            "one_hot_fsm": 1.1,
            "bch_ecc": 1.8,
            "crc": 1.03,
            "tmr_dice": 5.5,
            "scrubbing": 1.02,
            "interleaving": 1.01,
        }
        return overheads.get(strategy, 1.0)

    def _estimate_power_overhead(self, strategy: str) -> float:
        """估算功耗开销。

        Args:
            strategy: 加固策略

        Returns:
            功耗开销比例
        """
        overheads = {
            "tmr": 3.0,
            "ecc": 1.5,
            "dice": 2.5,
            "parity": 1.01,
            "tmr_ecc": 4.5,
            "cnt_comp": 1.02,
            "watchdog": 1.03,
            "one_hot_fsm": 1.2,
            "bch_ecc": 1.8,
            "crc": 1.03,
            "tmr_dice": 5.5,
            "scrubbing": 1.015,
            "interleaving": 1.005,
        }
        return overheads.get(strategy, 1.0)

    def analyze_vulnerability(self, vulnerability_results: Dict[str, Any]) -> Dict[str, Any]:
        """分析脆弱性结果。

        Args:
            vulnerability_results: 脆弱性分析结果

        Returns:
            分析结果
        """
        analysis = {
            "high_vulnerability_nodes": [],
            "medium_vulnerability_nodes": [],
            "low_vulnerability_nodes": [],
            "total_avf": 0.0,
            "total_failure_rate": 0.0,
            "total_mtbf": 0.0,
            "vulnerability_distribution": {},
        }

        total_avf = 0.0
        node_count = 0

        if isinstance(vulnerability_results, dict):
            items = vulnerability_results.items()
        elif isinstance(vulnerability_results, list):
            items = [(str(i), item) for i, item in enumerate(vulnerability_results)]
        else:
            items = []

        for node_name, node_data in items:
            if isinstance(node_data, dict):
                score = node_data.get("vulnerability_score", 0)
                avf = self._calculate_avf(score)
                total_avf += avf
                node_count += 1

                if score > 0.7:
                    analysis["high_vulnerability_nodes"].append({
                        "name": node_name,
                        "score": score,
                        "avf": avf,
                        "node_type": node_data.get("node_type", "unknown"),
                    })
                elif score > 0.4:
                    analysis["medium_vulnerability_nodes"].append({
                        "name": node_name,
                        "score": score,
                        "avf": avf,
                        "node_type": node_data.get("node_type", "unknown"),
                    })
                else:
                    analysis["low_vulnerability_nodes"].append({
                        "name": node_name,
                        "score": score,
                        "avf": avf,
                        "node_type": node_data.get("node_type", "unknown"),
                    })

        if node_count > 0:
            avg_avf = total_avf / node_count
            analysis["total_avf"] = avg_avf
            analysis["total_failure_rate"] = self._calculate_failure_rate(avg_avf, node_count)
            analysis["total_mtbf"] = self._calculate_mtbf(analysis["total_failure_rate"])

        analysis["vulnerability_distribution"] = {
            "high": len(analysis["high_vulnerability_nodes"]),
            "medium": len(analysis["medium_vulnerability_nodes"]),
            "low": len(analysis["low_vulnerability_nodes"]),
            "total": node_count,
        }

        return analysis

    def analyze_hardened_design(
        self,
        vulnerability_results: Dict[str, Any],
        strategy: str,
    ) -> Dict[str, Any]:
        """分析加固后的设计。

        Args:
            vulnerability_results: 脆弱性分析结果
            strategy: 使用的加固策略

        Returns:
            加固分析结果
        """
        vuln_analysis = self.analyze_vulnerability(vulnerability_results)

        area_overhead = self._estimate_area_overhead(strategy)
        power_overhead = self._estimate_power_overhead(strategy)

        hardened_failure_rate = vuln_analysis["total_failure_rate"] / area_overhead
        hardened_mtbf = vuln_analysis["total_mtbf"] * area_overhead

        return {
            "strategy": strategy,
            "area_overhead": area_overhead,
            "power_overhead": power_overhead,
            "hardened_failure_rate": hardened_failure_rate,
            "hardened_mtbf": hardened_mtbf,
            "reliability_improvement": vuln_analysis["total_mtbf"] / max(hardened_mtbf, 1),
            "vulnerability_analysis": vuln_analysis,
        }

    def generate_report(
        self,
        vulnerability_results: Dict[str, Any],
        strategy: str = "",
    ) -> Dict[str, Any]:
        """生成完整的可靠性分析报告。

        Args:
            vulnerability_results: 脆弱性分析结果
            strategy: 使用的加固策略

        Returns:
            可靠性报告
        """
        if strategy:
            analysis = self.analyze_hardened_design(vulnerability_results, strategy)
        else:
            analysis = self.analyze_vulnerability(vulnerability_results)
            analysis["strategy"] = "none"
            analysis["area_overhead"] = 1.0
            analysis["power_overhead"] = 1.0

        report = {
            "report_type": "reliability_analysis",
            "generated_at": "2026-07-16",
            "analysis": analysis,
            "recommendations": self._generate_recommendations(analysis),
            "summary": self._generate_summary(analysis),
        }

        self._reports.append(report)
        return report

    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """生成加固建议。

        Args:
            analysis: 分析结果

        Returns:
            建议列表
        """
        recommendations = []

        if analysis.get("vulnerability_analysis", {}).get("total_avf", 0) > 0.5:
            recommendations.append("建议对高脆弱性节点实施 TMR 或 DICE 加固")

        if analysis.get("area_overhead", 1.0) > 4.0:
            recommendations.append("当前策略面积开销较大，考虑使用 ECC 或 Parity 替代")

        high_nodes = analysis.get("vulnerability_analysis", {}).get("high_vulnerability_nodes", [])
        if len(high_nodes) > 5:
            recommendations.append(f"发现 {len(high_nodes)} 个高脆弱性节点，建议优先加固")

        mtbf = analysis.get("hardened_mtbf", analysis.get("total_mtbf", 0))
        if mtbf < 100000:
            recommendations.append("MTBF 低于 10 万小时，建议增加加固强度")

        return recommendations

    def _generate_summary(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """生成摘要。

        Args:
            analysis: 分析结果

        Returns:
            摘要信息
        """
        vuln_analysis = analysis.get("vulnerability_analysis", analysis)

        return {
            "total_nodes": vuln_analysis.get("vulnerability_distribution", {}).get("total", 0),
            "high_vulnerability_count": vuln_analysis.get("vulnerability_distribution", {}).get("high", 0),
            "medium_vulnerability_count": vuln_analysis.get("vulnerability_distribution", {}).get("medium", 0),
            "low_vulnerability_count": vuln_analysis.get("vulnerability_distribution", {}).get("low", 0),
            "average_avf": round(vuln_analysis.get("total_avf", 0), 4),
            "failure_rate_fit": round(analysis.get("hardened_failure_rate", vuln_analysis.get("total_failure_rate", 0)), 2),
            "mtbf_hours": round(analysis.get("hardened_mtbf", vuln_analysis.get("total_mtbf", 0)), 2),
            "area_overhead": analysis.get("area_overhead", 1.0),
            "power_overhead": analysis.get("power_overhead", 1.0),
        }

    def get_report_history(self) -> List[Dict[str, Any]]:
        """获取报告历史。

        Returns:
            报告列表
        """
        return self._reports


if __name__ == "__main__":
    sample_vuln_results = {
        "buffer_0": {"vulnerability_score": 0.85, "node_type": "register"},
        "buffer_1": {"vulnerability_score": 0.82, "node_type": "register"},
        "buffer_2": {"vulnerability_score": 0.78, "node_type": "register"},
        "voter_out": {"vulnerability_score": 0.65, "node_type": "logic"},
        "din": {"vulnerability_score": 0.30, "node_type": "input"},
        "dout": {"vulnerability_score": 0.25, "node_type": "output"},
        "clk": {"vulnerability_score": 0.10, "node_type": "clock"},
        "rst": {"vulnerability_score": 0.15, "node_type": "reset"},
    }

    analyzer = ReliabilityAnalyzer()

    print("=== Vulnerability Analysis ===")
    vuln_analysis = analyzer.analyze_vulnerability(sample_vuln_results)
    print(json.dumps(vuln_analysis, indent=2))

    print("\n=== Hardened Design Analysis ===")
    hardened_analysis = analyzer.analyze_hardened_design(sample_vuln_results, "tmr")
    print(json.dumps(hardened_analysis, indent=2))

    print("\n=== Full Reliability Report ===")
    report = analyzer.generate_report(sample_vuln_results, "tmr")
    print(json.dumps(report, indent=2))
