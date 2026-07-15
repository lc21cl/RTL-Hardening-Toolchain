from typing import Dict, List, Any, Optional
from logger import logger

_MODULE_TYPE_PATTERNS: Dict[str, List[str]] = {
    'fsm': ['fsm', 'state_machine', 'controller', 'control_fsm'],
    'counter': ['counter', 'timer', 'cnt', 'count'],
    'data_path': ['data_path', 'datapath', 'alu', 'dsp', 'processor'],
    'control': ['control', 'ctrl', 'manager'],
    'memory': ['memory', 'ram', 'rom', 'cache', 'fifo'],
    'bus': ['bus', 'interface', 'bridge'],
    'io': ['io', 'input', 'output', 'uart', 'spi', 'i2c'],
    'watchdog': ['watchdog', 'wdt', 'timeout'],
}

_STRATEGY_PROPERTIES: Dict[str, Dict[str, Any]] = {
    'tmr': {
        'area_overhead': 3.0,
        'reliability': 5,
        'latency': 1,
        'power_overhead': 3.0,
        'complexity': 'medium',
        'description': 'Triple Modular Redundancy',
    },
    'dice': {
        'area_overhead': 2.5,
        'reliability': 5,
        'latency': 0,
        'power_overhead': 2.5,
        'complexity': 'medium',
        'description': 'Dual Interlocked Storage Cell',
    },
    'ecc': {
        'area_overhead': 1.4,
        'reliability': 4,
        'latency': 1,
        'power_overhead': 1.5,
        'complexity': 'high',
        'description': 'Error Correcting Code',
    },
    'parity': {
        'area_overhead': 0.03,
        'reliability': 2,
        'latency': 0,
        'power_overhead': 0.1,
        'complexity': 'low',
        'description': 'Parity Check',
    },
    'cnt_comp': {
        'area_overhead': 0.1,
        'reliability': 3,
        'latency': 0,
        'power_overhead': 0.2,
        'complexity': 'low',
        'description': 'Counter Comparator',
    },
    'onehot_fsm': {
        'area_overhead': 1.1,
        'reliability': 4,
        'latency': 0,
        'power_overhead': 1.2,
        'complexity': 'medium',
        'description': 'One-Hot FSM',
    },
    'watchdog': {
        'area_overhead': 0.5,
        'reliability': 2,
        'latency': 0,
        'power_overhead': 0.3,
        'complexity': 'low',
        'description': 'Watchdog Timer',
    },
    'parity_bus': {
        'area_overhead': 0.03,
        'reliability': 2,
        'latency': 0,
        'power_overhead': 0.1,
        'complexity': 'low',
        'description': 'Bus Parity',
    },
}

_MODULE_STRATEGY_MAP: Dict[str, List[str]] = {
    'fsm': ['onehot_fsm', 'tmr', 'dice'],
    'counter': ['cnt_comp', 'parity', 'tmr'],
    'data_path': ['ecc', 'tmr', 'dice'],
    'control': ['parity', 'tmr', 'dice'],
    'memory': ['ecc', 'parity_bus'],
    'bus': ['parity_bus', 'ecc', 'parity'],
    'io': ['parity', 'watchdog'],
    'watchdog': ['watchdog', 'parity'],
    'default': ['tmr', 'parity', 'ecc'],
}

_OPTIMIZATION_GOALS: Dict[str, Dict[str, float]] = {
    'reliability': {'reliability': 1.0, 'area_overhead': -0.3, 'latency': -0.2},
    'area': {'reliability': 0.5, 'area_overhead': -1.0, 'latency': -0.3},
    'balanced': {'reliability': 0.7, 'area_overhead': -0.7, 'latency': -0.5},
    'performance': {'reliability': 0.5, 'area_overhead': -0.5, 'latency': -1.0},
}


def classify_module_type(module_name: str, module_info: Dict[str, Any]) -> str:
    """Classify module type based on name patterns and content analysis.

    Args:
        module_name: Name of the module
        module_info: Module information from design analysis

    Returns:
        Module type classification
    """
    lower_name = module_name.lower()

    for mod_type, patterns in _MODULE_TYPE_PATTERNS.items():
        for pattern in patterns:
            if pattern in lower_name:
                logger.print(f"  [RAG]   Module '{module_name}' classified as '{mod_type}' (name pattern: '{pattern}')")
                return mod_type

    reg_count = len(module_info.get('registers', []))
    sig_count = len(module_info.get('signals', []))

    if reg_count == 1 and sig_count >= 4:
        logger.print(f"  [RAG]   Module '{module_name}' classified as 'fsm' (single register, multiple signals)")
        return 'fsm'
    elif reg_count >= 2 and any(r.get('name', '').lower() in ['count', 'cnt'] for r in module_info.get('registers', [])):
        logger.print(f"  [RAG]   Module '{module_name}' classified as 'counter' (register name pattern)")
        return 'counter'
    elif sig_count >= 8:
        logger.print(f"  [RAG]   Module '{module_name}' classified as 'data_path' (many signals)")
        return 'data_path'

    logger.print(f"  [RAG]   Module '{module_name}' classified as 'default'")
    return 'default'


def score_strategy(strategy: str, optimization_goal: str, module_type: str) -> float:
    """Score a strategy based on optimization goals and module type.

    Args:
        strategy: Strategy name
        optimization_goal: Optimization goal ('reliability', 'area', 'balanced', 'performance')
        module_type: Module type classification

    Returns:
        Strategy score (higher is better)
    """
    props = _STRATEGY_PROPERTIES.get(strategy, {})
    weights = _OPTIMIZATION_GOALS.get(optimization_goal, _OPTIMIZATION_GOALS['balanced'])

    score = 0.0
    for key, weight in weights.items():
        value = props.get(key, 0)
        score += value * weight

    if module_type in _MODULE_STRATEGY_MAP:
        preferred_strategies = _MODULE_STRATEGY_MAP[module_type]
        if strategy in preferred_strategies:
            position = preferred_strategies.index(strategy)
            score += (3 - position) * 0.5

    return score


def recommend_strategy_for_module(
    module_name: str,
    module_info: Dict[str, Any],
    optimization_goal: str = 'balanced',
) -> Dict[str, Any]:
    """Recommend best strategy for a single module.

    Args:
        module_name: Name of the module
        module_info: Module information from design analysis
        optimization_goal: Optimization goal

    Returns:
        Recommendation result with top strategies and scores
    """
    module_type = classify_module_type(module_name, module_info)

    scores = []
    for strategy in _STRATEGY_PROPERTIES.keys():
        score = score_strategy(strategy, optimization_goal, module_type)
        scores.append({
            'strategy': strategy,
            'score': score,
            'properties': _STRATEGY_PROPERTIES[strategy],
        })

    scores.sort(key=lambda x: -x['score'])

    top_3 = scores[:3]
    best = top_3[0]

    logger.print(f"  [RAG]   Best strategy for '{module_name}' ({module_type}): {best['strategy']} (score={best['score']:.2f})")
    for s in top_3[1:]:
        logger.print(f"  [RAG]     Alternative: {s['strategy']} (score={s['score']:.2f})")

    return {
        'module_name': module_name,
        'module_type': module_type,
        'optimization_goal': optimization_goal,
        'recommended_strategy': best['strategy'],
        'top_strategies': top_3,
        'all_scores': scores,
    }


def recommend_strategies(
    design_analysis: Dict[str, Any],
    optimization_goal: str = 'balanced',
    exclude_strategies: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Recommend strategies for all modules in the design.

    Args:
        design_analysis: Output from analyze_design_for_hardening()
        optimization_goal: Optimization goal ('reliability', 'area', 'balanced', 'performance')
        exclude_strategies: List of strategies to exclude from recommendations

    Returns:
        Complete recommendation result
    """
    logger.section("Automatic Strategy Recommendation")
    logger.print("  [RAG] ===========================================")
    logger.print("  [RAG] Strategy Recommendation Engine Started")
    logger.print("  [RAG] ===========================================")
    logger.print(f"  [RAG] Optimization goal: '{optimization_goal}'")

    if exclude_strategies:
        logger.print(f"  [RAG] Excluded strategies: {exclude_strategies}")

    top_module_name = design_analysis.get('module_name', 'top')
    submodules = design_analysis.get('submodules', {})

    recommendations = {}
    module_strategy_map = {}

    top_info = {
        'registers': design_analysis.get('registers', []),
        'signals': design_analysis.get('signals', []),
    }
    top_rec = recommend_strategy_for_module(top_module_name, top_info, optimization_goal)
    recommendations[top_module_name] = top_rec
    if exclude_strategies is None or top_rec['recommended_strategy'] not in exclude_strategies:
        module_strategy_map[top_module_name] = top_rec['recommended_strategy']
    else:
        for s in top_rec['top_strategies']:
            if s['strategy'] not in exclude_strategies:
                module_strategy_map[top_module_name] = s['strategy']
                break

    for sub_name, sub_info in submodules.items():
        rec = recommend_strategy_for_module(sub_name, sub_info, optimization_goal)
        recommendations[sub_name] = rec
        if exclude_strategies is None or rec['recommended_strategy'] not in exclude_strategies:
            module_strategy_map[sub_name] = rec['recommended_strategy']
        else:
            for s in rec['top_strategies']:
                if s['strategy'] not in exclude_strategies:
                    module_strategy_map[sub_name] = s['strategy']
                    break

    logger.print("  [RAG] ")
    logger.print("  [RAG] --- Final Recommendations ---")
    for module_name, strategy in sorted(module_strategy_map.items()):
        logger.print(f"  [RAG]   {module_name}: {strategy}")

    logger.print("  [RAG] ")
    logger.print("  [RAG] ===========================================")
    logger.print("  [RAG] Strategy Recommendation Completed")
    logger.print("  [RAG] ===========================================")

    return {
        'module_strategy_map': module_strategy_map,
        'recommendations': recommendations,
        'optimization_goal': optimization_goal,
        'total_modules': len(module_strategy_map),
    }


def get_strategy_comparison(
    strategies: List[str],
) -> List[Dict[str, Any]]:
    """Get comparison data for multiple strategies.

    Args:
        strategies: List of strategy names

    Returns:
        List of strategy property dicts for comparison
    """
    comparison = []
    for strategy in strategies:
        props = _STRATEGY_PROPERTIES.get(strategy, {})
        comparison.append({
            'strategy': strategy,
            **props,
        })
    return comparison


def explain_recommendation(
    recommendation: Dict[str, Any],
) -> str:
    """Generate a human-readable explanation for a recommendation.

    Args:
        recommendation: Recommendation result from recommend_strategy_for_module()

    Returns:
        Text explanation
    """
    module_name = recommendation['module_name']
    module_type = recommendation['module_type']
    best = recommendation['recommended_strategy']
    props = recommendation['top_strategies'][0]['properties']

    explanation = f"模块 '{module_name}' 被识别为 {module_type} 类型。\n"
    explanation += f"推荐策略: {best} ({props['description']})\n"
    explanation += f"面积开销: {props['area_overhead']}×\n"
    explanation += f"可靠性等级: {'★' * props['reliability']}\n"
    explanation += f"延迟开销: {props['latency']} 周期\n"

    if len(recommendation['top_strategies']) > 1:
        explanation += "\n备选方案:\n"
        for s in recommendation['top_strategies'][1:]:
            explanation += f"  • {s['strategy']}: 面积{s['properties']['area_overhead']}×, 可靠性{'★' * s['properties']['reliability']}\n"

    return explanation