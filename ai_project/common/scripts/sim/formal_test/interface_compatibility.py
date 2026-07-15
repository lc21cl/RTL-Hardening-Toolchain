import re
from typing import Dict, List, Any, Optional, Tuple
from logger import logger

_STRATEGY_COMPATIBILITY_MATRIX: Dict[str, Dict[str, str]] = {
    'tmr': {
        'tmr': 'compatible',
        'dice': 'compatible',
        'ecc': 'adapter_required',
        'parity': 'adapter_required',
        'cnt_comp': 'adapter_required',
        'onehot_fsm': 'adapter_required',
        'watchdog': 'compatible',
        'parity_bus': 'adapter_required',
    },
    'dice': {
        'tmr': 'compatible',
        'dice': 'compatible',
        'ecc': 'adapter_required',
        'parity': 'adapter_required',
        'cnt_comp': 'adapter_required',
        'onehot_fsm': 'adapter_required',
        'watchdog': 'compatible',
        'parity_bus': 'adapter_required',
    },
    'ecc': {
        'tmr': 'adapter_required',
        'dice': 'adapter_required',
        'ecc': 'compatible',
        'parity': 'compatible',
        'cnt_comp': 'compatible',
        'onehot_fsm': 'adapter_required',
        'watchdog': 'compatible',
        'parity_bus': 'compatible',
    },
    'parity': {
        'tmr': 'adapter_required',
        'dice': 'adapter_required',
        'ecc': 'compatible',
        'parity': 'compatible',
        'cnt_comp': 'compatible',
        'onehot_fsm': 'adapter_required',
        'watchdog': 'compatible',
        'parity_bus': 'compatible',
    },
    'cnt_comp': {
        'tmr': 'adapter_required',
        'dice': 'adapter_required',
        'ecc': 'compatible',
        'parity': 'compatible',
        'cnt_comp': 'compatible',
        'onehot_fsm': 'adapter_required',
        'watchdog': 'compatible',
        'parity_bus': 'compatible',
    },
    'onehot_fsm': {
        'tmr': 'adapter_required',
        'dice': 'adapter_required',
        'ecc': 'adapter_required',
        'parity': 'adapter_required',
        'cnt_comp': 'adapter_required',
        'onehot_fsm': 'compatible',
        'watchdog': 'compatible',
        'parity_bus': 'adapter_required',
    },
    'watchdog': {
        'tmr': 'compatible',
        'dice': 'compatible',
        'ecc': 'compatible',
        'parity': 'compatible',
        'cnt_comp': 'compatible',
        'onehot_fsm': 'compatible',
        'watchdog': 'compatible',
        'parity_bus': 'compatible',
    },
    'parity_bus': {
        'tmr': 'adapter_required',
        'dice': 'adapter_required',
        'ecc': 'compatible',
        'parity': 'compatible',
        'cnt_comp': 'compatible',
        'onehot_fsm': 'adapter_required',
        'watchdog': 'compatible',
        'parity_bus': 'compatible',
    },
}

_ADAPTER_TEMPLATES: Dict[str, Dict[str, str]] = {
    'tmr_to_ecc': {
        'name': 'tmr_to_ecc_adapter',
        'template': """module tmr_to_ecc_adapter #(
    parameter WIDTH = 32
)(
    input  [WIDTH-1:0] tmr_in_0,
    input  [WIDTH-1:0] tmr_in_1,
    input  [WIDTH-1:0] tmr_in_2,
    output [WIDTH-1:0] ecc_out
);
    wire [WIDTH-1:0] voted;
    assign voted = (tmr_in_0 & tmr_in_1) | (tmr_in_1 & tmr_in_2) | (tmr_in_0 & tmr_in_2);
    assign ecc_out = voted;
endmodule
""",
    },
    'ecc_to_tmr': {
        'name': 'ecc_to_tmr_adapter',
        'template': """module ecc_to_tmr_adapter #(
    parameter WIDTH = 32
)(
    input  [WIDTH-1:0] ecc_in,
    output [WIDTH-1:0] tmr_out_0,
    output [WIDTH-1:0] tmr_out_1,
    output [WIDTH-1:0] tmr_out_2
);
    assign tmr_out_0 = ecc_in;
    assign tmr_out_1 = ecc_in;
    assign tmr_out_2 = ecc_in;
endmodule
""",
    },
    'tmr_to_parity': {
        'name': 'tmr_to_parity_adapter',
        'template': """module tmr_to_parity_adapter #(
    parameter WIDTH = 32
)(
    input  [WIDTH-1:0] tmr_in_0,
    input  [WIDTH-1:0] tmr_in_1,
    input  [WIDTH-1:0] tmr_in_2,
    output [WIDTH-1:0] parity_out
);
    wire [WIDTH-1:0] voted;
    assign voted = (tmr_in_0 & tmr_in_1) | (tmr_in_1 & tmr_in_2) | (tmr_in_0 & tmr_in_2);
    assign parity_out = voted;
endmodule
""",
    },
    'parity_to_tmr': {
        'name': 'parity_to_tmr_adapter',
        'template': """module parity_to_tmr_adapter #(
    parameter WIDTH = 32
)(
    input  [WIDTH-1:0] parity_in,
    output [WIDTH-1:0] tmr_out_0,
    output [WIDTH-1:0] tmr_out_1,
    output [WIDTH-1:0] tmr_out_2
);
    assign tmr_out_0 = parity_in;
    assign tmr_out_1 = parity_in;
    assign tmr_out_2 = parity_in;
endmodule
""",
    },
    'fsm_to_tmr': {
        'name': 'fsm_to_tmr_adapter',
        'template': """module fsm_to_tmr_adapter #(
    parameter WIDTH = 32
)(
    input  [WIDTH-1:0] fsm_in,
    output [WIDTH-1:0] tmr_out_0,
    output [WIDTH-1:0] tmr_out_1,
    output [WIDTH-1:0] tmr_out_2
);
    assign tmr_out_0 = fsm_in;
    assign tmr_out_1 = fsm_in;
    assign tmr_out_2 = fsm_in;
endmodule
""",
    },
}


def detect_interface_connections(
    design_analysis: Dict[str, Any],
    module_strategy_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Detect connections between submodules with different strategies.

    Args:
        design_analysis: Output from analyze_design_for_hardening()
        module_strategy_map: Module strategy mapping

    Returns:
        List of interface connection dicts with source/destination modules
        and their strategies
    """
    connections = []
    top_module = design_analysis.get('module_name', 'top')
    submodules = design_analysis.get('submodules', {})

    logger.section("Interface Compatibility Analysis")
    logger.print("  [RAG] ===========================================")
    logger.print("  [RAG] Interface Compatibility Analysis Started")
    logger.print("  [RAG] ===========================================")
    logger.print(f"  [RAG] Top module: '{top_module}'")
    logger.print(f"  [RAG] Submodules: {list(submodules.keys())}")

    for source_mod, source_info in submodules.items():
        source_strategy = module_strategy_map.get(source_mod, 'tmr')
        source_signals = source_info.get('signals', [])

        for sink_mod, sink_info in submodules.items():
            if source_mod == sink_mod:
                continue

            sink_strategy = module_strategy_map.get(sink_mod, 'tmr')
            sink_signals = sink_info.get('signals', [])

            shared_signals = []
            for src_sig in source_signals:
                src_name = src_sig.get('name', '')
                src_dir = src_sig.get('direction', '')
                for sink_sig in sink_signals:
                    sink_name = sink_sig.get('name', '')
                    sink_dir = sink_sig.get('direction', '')
                    if src_name == sink_name and src_dir != sink_dir:
                        shared_signals.append({
                            'name': src_name,
                            'width': src_sig.get('width', 1),
                            'source_direction': src_dir,
                            'sink_direction': sink_dir,
                        })

            if shared_signals:
                connections.append({
                    'source_module': source_mod,
                    'source_strategy': source_strategy,
                    'sink_module': sink_mod,
                    'sink_strategy': sink_strategy,
                    'signals': shared_signals,
                    'connection_type': 'inter_module',
                })
                logger.print(f"  [RAG]   Connection: {source_mod} ({source_strategy}) → {sink_mod} ({sink_strategy})")
                for sig in shared_signals:
                    logger.print(f"  [RAG]     Signal: {sig['name']} ({sig['width']} bits)")

    connections_to_top = []
    for sub_mod, sub_info in submodules.items():
        sub_strategy = module_strategy_map.get(sub_mod, 'tmr')
        top_strategy = module_strategy_map.get(top_module, 'tmr')
        sub_signals = sub_info.get('signals', [])
        top_signals = design_analysis.get('signals', [])

        for sub_sig in sub_signals:
            sub_name = sub_sig.get('name', '')
            for top_sig in top_signals:
                top_name = top_sig.get('name', '')
                if sub_name == top_name:
                    connections_to_top.append({
                        'source_module': sub_mod,
                        'source_strategy': sub_strategy,
                        'sink_module': top_module,
                        'sink_strategy': top_strategy,
                        'signals': [{
                            'name': sub_name,
                            'width': sub_sig.get('width', 1),
                            'source_direction': sub_sig.get('direction', ''),
                            'sink_direction': top_sig.get('direction', ''),
                        }],
                        'connection_type': 'submodule_to_top',
                    })

    connections.extend(connections_to_top)

    logger.print(f"  [RAG] ")
    logger.print(f"  [RAG] ===========================================")
    logger.print(f"  [RAG] Found {len(connections)} interface connections")
    logger.print(f"  [RAG] ===========================================")

    return connections


def check_strategy_compatibility(
    strategy_a: str,
    strategy_b: str,
) -> Dict[str, Any]:
    """Check compatibility between two strategies.

    Args:
        strategy_a: First strategy
        strategy_b: Second strategy

    Returns:
        Compatibility result with status and adapter requirements
    """
    status = _STRATEGY_COMPATIBILITY_MATRIX.get(strategy_a, {}).get(strategy_b, 'unknown')

    return {
        'strategy_a': strategy_a,
        'strategy_b': strategy_b,
        'status': status,
        'needs_adapter': status == 'adapter_required',
    }


def analyze_interface_compatibility(
    design_analysis: Dict[str, Any],
    module_strategy_map: Dict[str, str],
) -> Dict[str, Any]:
    """Comprehensive interface compatibility analysis.

    Args:
        design_analysis: Output from analyze_design_for_hardening()
        module_strategy_map: Module strategy mapping

    Returns:
        Compatibility analysis result with conflicts and recommendations
    """
    connections = detect_interface_connections(design_analysis, module_strategy_map)

    conflicts = []
    compatible = []
    adapter_requirements = []

    for conn in connections:
        source_strategy = conn['source_strategy']
        sink_strategy = conn['sink_strategy']

        comp_result = check_strategy_compatibility(source_strategy, sink_strategy)

        if comp_result['status'] == 'compatible':
            compatible.append(conn)
        elif comp_result['status'] == 'adapter_required':
            adapter_requirements.append({
                **conn,
                'adapter_type': f"{source_strategy}_to_{sink_strategy}",
                'adapter_name': _ADAPTER_TEMPLATES.get(f"{source_strategy}_to_{sink_strategy}", {}).get('name', ''),
            })
            conflicts.append({
                **conn,
                'conflict_type': 'strategy_mismatch',
                'recommendation': f"Add adapter module '{conn['source_strategy']}_to_{conn['sink_strategy']}'",
            })
        else:
            conflicts.append({
                **conn,
                'conflict_type': 'unknown_strategy',
                'recommendation': f"Unknown strategy combination: {source_strategy} <-> {sink_strategy}",
            })

    logger.print("  [RAG] ")
    logger.print("  [RAG] --- Compatibility Summary ---")
    logger.print(f"  [RAG]   Compatible connections: {len(compatible)}")
    logger.print(f"  [RAG]   Adapter required: {len(adapter_requirements)}")
    logger.print(f"  [RAG]   Conflicts: {len(conflicts)}")

    for conflict in conflicts:
        logger.warning(f"  [RAG]   ⚠️  Conflict: {conflict['source_module']}({conflict['source_strategy']}) → {conflict['sink_module']}({conflict['sink_strategy']})")
        logger.warning(f"  [RAG]      Recommendation: {conflict['recommendation']}")

    return {
        'connections': connections,
        'compatible': compatible,
        'adapter_requirements': adapter_requirements,
        'conflicts': conflicts,
        'has_conflicts': len(conflicts) > 0,
    }


def generate_adapter_modules(
    adapter_requirements: List[Dict[str, Any]],
) -> str:
    """Generate adapter module Verilog code for incompatible interfaces.

    Args:
        adapter_requirements: List of adapter requirements from analyze_interface_compatibility()

    Returns:
        Verilog code for all required adapter modules
    """
    adapter_code = ""

    for req in adapter_requirements:
        adapter_type = req.get('adapter_type', '')
        template = _ADAPTER_TEMPLATES.get(adapter_type, {})

        if template:
            signals = req.get('signals', [])
            max_width = max(s.get('width', 32) for s in signals) if signals else 32

            code = template['template'].replace('WIDTH = 32', f'WIDTH = {max_width}')
            adapter_code += code + "\n\n"

            logger.print(f"  [RAG]   Generated adapter: {template['name']} (WIDTH={max_width})")

    return adapter_code.strip()


def resolve_compatibility_conflicts(
    design_analysis: Dict[str, Any],
    module_strategy_map: Dict[str, str],
    resolution_strategy: str = 'add_adapters',
) -> Dict[str, Any]:
    """Resolve compatibility conflicts between modules.

    Args:
        design_analysis: Output from analyze_design_for_hardening()
        module_strategy_map: Module strategy mapping
        resolution_strategy: Resolution method: 'add_adapters' (default), 'upgrade_strategy', 'downgrade_strategy'

    Returns:
        Result with updated strategy map and generated adapters
    """
    analysis = analyze_interface_compatibility(design_analysis, module_strategy_map)

    if not analysis['has_conflicts']:
        return {
            'updated_strategy_map': module_strategy_map,
            'adapter_code': '',
            'changes_made': False,
            'conflicts_resolved': 0,
        }

    updated_map = module_strategy_map.copy()
    adapter_code = ""
    conflicts_resolved = 0

    logger.section("Compatibility Conflict Resolution")
    logger.print(f"  [RAG] Resolution strategy: {resolution_strategy}")

    if resolution_strategy == 'add_adapters':
        adapter_code = generate_adapter_modules(analysis['adapter_requirements'])
        conflicts_resolved = len(analysis['adapter_requirements'])
        logger.print(f"  [RAG] Added {conflicts_resolved} adapter modules")

    elif resolution_strategy == 'upgrade_strategy':
        _STRATEGY_PRIORITY = {'tmr': 8, 'dice': 7, 'ecc': 6, 'parity': 5, 'cnt_comp': 4, 'onehot_fsm': 3, 'watchdog': 2, 'parity_bus': 1}

        for conflict in analysis['conflicts']:
            source_priority = _STRATEGY_PRIORITY.get(conflict['source_strategy'], 0)
            sink_priority = _STRATEGY_PRIORITY.get(conflict['sink_strategy'], 0)

            if source_priority < sink_priority:
                updated_map[conflict['source_module']] = conflict['sink_strategy']
                logger.print(f"  [RAG]   Upgraded {conflict['source_module']}: {conflict['source_strategy']} → {conflict['sink_strategy']}")
            else:
                updated_map[conflict['sink_module']] = conflict['source_strategy']
                logger.print(f"  [RAG]   Upgraded {conflict['sink_module']}: {conflict['sink_strategy']} → {conflict['source_strategy']}")
            conflicts_resolved += 1

    elif resolution_strategy == 'downgrade_strategy':
        _STRATEGY_PRIORITY = {'tmr': 8, 'dice': 7, 'ecc': 6, 'parity': 5, 'cnt_comp': 4, 'onehot_fsm': 3, 'watchdog': 2, 'parity_bus': 1}

        for conflict in analysis['conflicts']:
            source_priority = _STRATEGY_PRIORITY.get(conflict['source_strategy'], 0)
            sink_priority = _STRATEGY_PRIORITY.get(conflict['sink_strategy'], 0)

            if source_priority > sink_priority:
                updated_map[conflict['source_module']] = conflict['sink_strategy']
                logger.print(f"  [RAG]   Downgraded {conflict['source_module']}: {conflict['source_strategy']} → {conflict['sink_strategy']}")
            else:
                updated_map[conflict['sink_module']] = conflict['source_strategy']
                logger.print(f"  [RAG]   Downgraded {conflict['sink_module']}: {conflict['sink_strategy']} → {conflict['source_strategy']}")
            conflicts_resolved += 1

    return {
        'updated_strategy_map': updated_map,
        'adapter_code': adapter_code,
        'changes_made': conflicts_resolved > 0,
        'conflicts_resolved': conflicts_resolved,
        'original_conflicts': analysis['conflicts'],
    }