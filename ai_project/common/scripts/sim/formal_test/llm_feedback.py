#!/usr/bin/env python3
"""
llm_feedback.py — LLM 反馈循环模块

让 LLM 评估自己的输出质量，通过迭代优化提升加固代码质量。

核心功能：
  1. 代码质量评估 — LLM 对生成的 RTL 代码进行自我评估
  2. 迭代优化 — 根据评估结果重新生成改进版本
  3. 多维度评分 — 语法正确性、逻辑完整性、加固有效性、代码风格
  4. 置信度阈值 — 设置质量门槛，低于阈值自动重试

设计原则：
  - 独立于具体 LLM 后端，支持 mock/OpenAI/DeepSeek
  - 可配置的评估维度和权重
  - 支持最大迭代次数限制
  - 详细的评估日志和统计

用法:
    from llm_feedback import LLMFeedbackLoop

    feedback = LLMFeedbackLoop(llm_backend='mock')

    # 单次评估
    result = feedback.evaluate(rtl_code, design_info)
    # result: {quality_score: 0.85, dimensions: {...}, suggestions: [...]}

    # 迭代优化直到满足质量要求
    final_code = feedback.optimize(
        rtl_code, design_info,
        target_score=0.8,
        max_iterations=3
    )
"""

import os
import re
import json
import time
from typing import Dict, List, Optional, Tuple, Any, Callable

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("llm_feedback")


# ============================================================================
# LLM Backend Adapter
# ============================================================================

try:
    from rag_integration import OpenAIBackend
    _HAVE_BACKEND = True
except ImportError:
    _HAVE_BACKEND = False


class LLMBackendAdapter:
    """LLM 后端适配器，统一不同后端的接口。"""

    def __init__(self, backend: str = 'mock', api_key: Optional[str] = None):
        self.backend = backend.lower()
        self._backend = None

        if self.backend == 'mock':
            self._backend = _MockFeedbackLLM()
        elif _HAVE_BACKEND:
            self._backend = OpenAIBackend(
                api_key=api_key,
                base_url=None,
                model_name='deepseek-chat',
            )
        else:
            logger.warning("No LLM backend available, using mock")
            self._backend = _MockFeedbackLLM()

    def generate(self, prompt: str) -> str:
        """生成文本响应。"""
        if hasattr(self._backend, 'generate'):
            return self._backend.generate(prompt)
        elif hasattr(self._backend, 'chat'):
            return self._backend.chat(prompt)
        return ""


class _MockFeedbackLLM:
    """模拟反馈 LLM，用于测试和离线环境。"""

    def generate(self, prompt: str) -> str:
        if "evaluate" in prompt.lower() or "评估" in prompt:
            return json.dumps({
                "quality_score": 0.75 + (hash(prompt) % 20) / 100,
                "dimensions": {
                    "syntax_correctness": 0.85,
                    "logic_complete": 0.72,
                    "hardening_effective": 0.78,
                    "code_style": 0.80,
                    "signal_coverage": 0.75,
                },
                "suggestions": [
                    "建议添加更多的注释说明加固逻辑",
                    "检查投票器输出是否正确连接",
                    "考虑添加复位信号的处理",
                ],
                "errors_found": [],
                "warnings_found": [],
            })
        elif "improve" in prompt.lower() or "改进" in prompt:
            return "// 改进后的代码\n// - 添加了复位保护\n// - 优化了投票器逻辑"
        return ""


# ============================================================================
# Evaluation Prompts
# ============================================================================

EVALUATION_SYSTEM_PROMPT = """
你是一位专业的数字集成电路设计工程师和形式验证专家。
请对以下 RTL 代码进行全面评估，给出详细的质量评分和改进建议。

评估维度（每个维度 0-1 分）：
1. syntax_correctness — 语法正确性：是否符合 Verilog/SystemVerilog 语法规范
2. logic_complete — 逻辑完整性：功能是否完整，是否有缺失的逻辑
3. hardening_effective — 加固有效性：加固策略是否正确实现，是否能抵御目标故障
4. code_style — 代码风格：命名规范、缩进、可读性、注释完整性
5. signal_coverage — 信号覆盖率：所有信号是否都被正确处理和加固

输出格式必须为 JSON：
{
    "quality_score": 0.85,
    "dimensions": {
        "syntax_correctness": 0.9,
        "logic_complete": 0.8,
        "hardening_effective": 0.85,
        "code_style": 0.8,
        "signal_coverage": 0.8
    },
    "suggestions": ["建议1", "建议2", "建议3"],
    "errors_found": ["错误1", "错误2"],
    "warnings_found": ["警告1", "警告2"],
    "confidence": 0.9
}
"""

IMPROVEMENT_PROMPT_TEMPLATE = """
你是一位专业的数字集成电路设计工程师。
请根据以下评估结果和建议，改进 RTL 代码。

原始代码：
{original_code}

评估结果：
{evaluation_result}

改进要求：
1. 修复所有检测到的错误
2. 解决所有警告
3. 实施建议的改进
4. 保持代码功能不变
5. 提高整体质量评分

请直接输出改进后的完整 RTL 代码，不要包含任何解释或额外文本。
"""


# ============================================================================
# LLMFeedbackLoop
# ============================================================================

class LLMFeedbackLoop:
    """LLM 反馈循环类。

    让 LLM 评估自己生成的代码质量，并通过迭代优化提升代码质量。
    """

    def __init__(
        self,
        llm_backend: str = 'mock',
        api_key: Optional[str] = None,
        target_score: float = 0.8,
        max_iterations: int = 3,
        evaluation_weight: Dict[str, float] = None,
    ):
        """初始化反馈循环。

        Args:
            llm_backend: LLM 后端类型 ('mock', 'openai', 'deepseek')
            api_key: API 密钥（如果需要）
            target_score: 目标质量分数（0-1）
            max_iterations: 最大迭代次数
            evaluation_weight: 各评估维度的权重
        """
        self._llm = LLMBackendAdapter(llm_backend, api_key)
        self.target_score = target_score
        self.max_iterations = max_iterations
        self.evaluation_weight = evaluation_weight or {
            "syntax_correctness": 0.25,
            "logic_complete": 0.25,
            "hardening_effective": 0.25,
            "code_style": 0.15,
            "signal_coverage": 0.10,
        }

    def evaluate(
        self,
        rtl_code: str,
        design_info: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """评估 RTL 代码质量。

        Args:
            rtl_code: RTL 代码字符串
            design_info: 设计信息（可选）

        Returns:
            评估结果字典，包含质量分数、各维度评分和改进建议
        """
        logger.print(f"  [FEEDBACK] Evaluating RTL code quality...")

        if design_info:
            design_desc = json.dumps(design_info, indent=2, ensure_ascii=False)
        else:
            design_desc = "{}"

        prompt = (
            f"{EVALUATION_SYSTEM_PROMPT}\n\n"
            f"设计信息：\n{design_desc}\n\n"
            f"待评估的 RTL 代码：\n```verilog\n{rtl_code}\n```\n"
        )

        response = self._llm.generate(prompt)

        try:
            result = json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"  [FEEDBACK] Failed to parse evaluation JSON, using fallback")
            result = self._parse_fallback_evaluation(response)

        computed_score = self._compute_weighted_score(result.get("dimensions", {}))
        if "quality_score" not in result or not isinstance(result["quality_score"], float):
            result["quality_score"] = computed_score

        logger.print(f"  [FEEDBACK]   Quality score: {result['quality_score']:.2f}")
        for dim, score in result.get("dimensions", {}).items():
            logger.print(f"  [FEEDBACK]     - {dim}: {score:.2f}")

        if result.get("errors_found"):
            for err in result["errors_found"]:
                logger.print(f"  [FEEDBACK]   ❌ Error: {err}")
        if result.get("warnings_found"):
            for warn in result["warnings_found"]:
                logger.print(f"  [FEEDBACK]   ⚠️ Warning: {warn}")

        return result

    def _compute_weighted_score(self, dimensions: Dict[str, float]) -> float:
        """计算加权质量分数。"""
        total_weight = sum(self.evaluation_weight.values())
        score = 0.0
        for dim, weight in self.evaluation_weight.items():
            score += dimensions.get(dim, 0.0) * weight
        return score / total_weight if total_weight > 0 else 0.0

    def _parse_fallback_evaluation(self, text: str) -> Dict[str, Any]:
        """解析非 JSON 格式的评估结果（fallback）。"""
        score = 0.70
        errors = []
        warnings = []
        suggestions = []

        if "error" in text.lower() or "错误" in text:
            errors.append("检测到语法或逻辑错误")
            score -= 0.1

        if "warning" in text.lower() or "警告" in text:
            warnings.append("检测到潜在问题")
            score -= 0.05

        if "建议" in text or "suggest" in text.lower():
            suggestions.append("需要改进")

        return {
            "quality_score": score,
            "dimensions": {
                "syntax_correctness": 0.8,
                "logic_complete": 0.75,
                "hardening_effective": 0.75,
                "code_style": 0.75,
                "signal_coverage": 0.70,
            },
            "suggestions": suggestions,
            "errors_found": errors,
            "warnings_found": warnings,
            "confidence": 0.6,
        }

    def optimize(
        self,
        rtl_code: str,
        design_info: Optional[Dict] = None,
        target_score: Optional[float] = None,
        max_iterations: Optional[int] = None,
        on_iteration: Optional[Callable] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """迭代优化 RTL 代码直到满足质量要求。

        Args:
            rtl_code: 初始 RTL 代码
            design_info: 设计信息
            target_score: 目标质量分数（覆盖初始化时的值）
            max_iterations: 最大迭代次数（覆盖初始化时的值）
            on_iteration: 每轮迭代后的回调函数

        Returns:
            (最终代码, 最终评估结果)
        """
        target = target_score or self.target_score
        max_it = max_iterations or self.max_iterations

        logger.print(f"  [FEEDBACK] Starting optimization loop (target={target:.2f}, max={max_it})")

        current_code = rtl_code
        iteration = 0
        final_result = None

        while iteration < max_it:
            iteration += 1
            logger.print(f"  [FEEDBACK] === Iteration {iteration}/{max_it} ===")

            result = self.evaluate(current_code, design_info)
            final_result = result

            if result["quality_score"] >= target:
                logger.print(f"  [FEEDBACK] ✓ Target score reached at iteration {iteration}")
                break

            logger.print(f"  [FEEDBACK] Improving code based on evaluation...")
            current_code = self._improve_code(current_code, result)

            if on_iteration:
                on_iteration(iteration, result["quality_score"], current_code)

        if iteration >= max_it and final_result and final_result["quality_score"] < target:
            logger.print(f"  [FEEDBACK] ⚠️ Max iterations reached without meeting target")

        return current_code, final_result

    def _improve_code(self, rtl_code: str, evaluation: Dict[str, Any]) -> str:
        """根据评估结果改进代码。"""
        eval_json = json.dumps(evaluation, indent=2, ensure_ascii=False)

        prompt = IMPROVEMENT_PROMPT_TEMPLATE.format(
            original_code=rtl_code,
            evaluation_result=eval_json,
        )

        response = self._llm.generate(prompt)

        code_block_match = re.search(r'```(?:verilog)?\s*\n(.*?)\n```', response, re.DOTALL)
        if code_block_match:
            return code_block_match.group(1).strip()

        return response.strip()

    def batch_evaluate(
        self,
        code_list: List[str],
        design_info_list: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        """批量评估多个 RTL 代码。

        Args:
            code_list: RTL 代码列表
            design_info_list: 设计信息列表（与代码列表对应）

        Returns:
            评估结果列表
        """
        results = []
        for i, code in enumerate(code_list):
            design_info = design_info_list[i] if design_info_list else None
            logger.print(f"  [FEEDBACK] Evaluating code {i+1}/{len(code_list)}")
            result = self.evaluate(code, design_info)
            result["index"] = i
            results.append(result)
        return results

    def get_statistics(self, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """从多次评估中计算统计信息。

        Args:
            evaluations: 评估结果列表

        Returns:
            统计信息字典
        """
        if not evaluations:
            return {}

        scores = [e.get("quality_score", 0) for e in evaluations]
        dimensions = evaluations[0].get("dimensions", {})

        dim_stats = {}
        for dim in dimensions:
            dim_scores = [e.get("dimensions", {}).get(dim, 0) for e in evaluations]
            dim_stats[dim] = {
                "mean": sum(dim_scores) / len(dim_scores),
                "min": min(dim_scores),
                "max": max(dim_scores),
                "std": (sum((s - sum(dim_scores)/len(dim_scores))**2 for s in dim_scores) / len(dim_scores))**0.5,
            }

        return {
            "total_evaluations": len(evaluations),
            "quality_score_mean": sum(scores) / len(scores),
            "quality_score_min": min(scores),
            "quality_score_max": max(scores),
            "quality_score_std": (sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores))**0.5,
            "dimensions": dim_stats,
        }


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="LLM Feedback Loop")
    parser.add_argument("--code", type=str, help="Path to RTL file")
    parser.add_argument("--evaluate", action="store_true", help="Evaluate mode")
    parser.add_argument("--optimize", action="store_true", help="Optimize mode")
    parser.add_argument("--target", type=float, default=0.8, help="Target quality score")
    parser.add_argument("--max-iter", type=int, default=3, help="Max iterations")
    parser.add_argument("--backend", type=str, default="mock", help="LLM backend")
    parser.add_argument("--output", type=str, help="Output path for optimized code")
    args = parser.parse_args()

    if not args.code or not os.path.isfile(args.code):
        logger.error("Please provide a valid RTL file with --code")
        return

    with open(args.code, "r", encoding="utf-8") as f:
        rtl_code = f.read()

    feedback = LLMFeedbackLoop(
        llm_backend=args.backend,
        target_score=args.target,
        max_iterations=args.max_iter,
    )

    if args.evaluate:
        result = feedback.evaluate(rtl_code)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.optimize:
        final_code, result = feedback.optimize(rtl_code)
        print(f"\nFinal quality score: {result['quality_score']:.2f}")
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(final_code)
            print(f"Optimized code written to: {args.output}")
        else:
            print("\nOptimized code:")
            print("=" * 60)
            print(final_code)


if __name__ == "__main__":
    main()
