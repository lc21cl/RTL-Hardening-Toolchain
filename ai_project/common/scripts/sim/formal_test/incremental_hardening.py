import os
import json
import hashlib
from typing import Dict, List, Any, Optional
from logger import logger

_INCREMENTAL_DATA_FILE = '.incremental_hardening.json'


def _compute_module_hash(module_info: Dict[str, Any]) -> str:
    """Compute a hash for a module to detect changes.

    Args:
        module_info: Module information

    Returns:
        Hash string
    """
    data_str = json.dumps(module_info, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(data_str.encode('utf-8')).hexdigest()


def _compute_design_hash(design_analysis: Dict[str, Any]) -> str:
    """Compute a hash for the entire design.

    Args:
        design_analysis: Design analysis output

    Returns:
        Hash string
    """
    relevant_data = {
        'module_name': design_analysis.get('module_name'),
        'registers': design_analysis.get('registers'),
        'signals': design_analysis.get('signals'),
        'submodules': {
            name: {
                'registers': info.get('registers', []),
                'signals': info.get('signals', []),
            }
            for name, info in design_analysis.get('submodules', {}).items()
        },
    }
    data_str = json.dumps(relevant_data, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(data_str.encode('utf-8')).hexdigest()


def save_incremental_data(
    output_dir: str,
    design_hash: str,
    module_strategy_map: Dict[str, str],
    hardened_signals: Dict[str, str],
    compatibility_info: Optional[Dict[str, Any]] = None,
) -> None:
    """Save incremental hardening data for future reuse.

    Args:
        output_dir: Output directory
        design_hash: Design hash string
        module_strategy_map: Module strategy mapping
        hardened_signals: Hardened signal mapping
        compatibility_info: Compatibility resolution info
    """
    incremental_data = {
        'design_hash': design_hash,
        'module_strategy_map': module_strategy_map,
        'hardened_signals': hardened_signals,
        'compatibility_info': compatibility_info or {},
        'timestamp': json.dumps({'__timestamp__': 'auto'}, default=str),
    }

    data_path = os.path.join(output_dir, _INCREMENTAL_DATA_FILE)
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(incremental_data, f, indent=2, ensure_ascii=False)

    logger.print(f"  [RAG]   Incremental data saved to: {data_path}")


def load_incremental_data(output_dir: str) -> Optional[Dict[str, Any]]:
    """Load previously saved incremental hardening data.

    Args:
        output_dir: Output directory

    Returns:
        Incremental data dict if exists, None otherwise
    """
    data_path = os.path.join(output_dir, _INCREMENTAL_DATA_FILE)
    if not os.path.exists(data_path):
        logger.print(f"  [RAG]   No incremental data found at: {data_path}")
        return None

    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.print(f"  [RAG]   Incremental data loaded from: {data_path}")
        return data
    except Exception as e:
        logger.print(f"  [RAG]   Failed to load incremental data: {e}")
        return None


def detect_design_changes(
    design_analysis: Dict[str, Any],
    previous_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Detect changes between current and previous design.

    Args:
        design_analysis: Current design analysis
        previous_data: Previously saved incremental data

    Returns:
        Change detection result
    """
    logger.section("Incremental Design Change Detection")
    logger.print("  [RAG] ===========================================")
    logger.print("  [RAG] Change Detection Started")
    logger.print("  [RAG] ===========================================")

    current_hash = _compute_design_hash(design_analysis)
    previous_hash = previous_data.get('design_hash', '') if previous_data else ''

    changes = {
        'design_changed': current_hash != previous_hash,
        'current_hash': current_hash,
        'previous_hash': previous_hash,
        'new_modules': [],
        'modified_modules': [],
        'removed_modules': [],
        'unchanged_modules': [],
    }

    if not previous_data:
        logger.print("  [RAG]   No previous data found - full hardening required")
        changes['design_changed'] = True
        return changes

    if current_hash == previous_hash:
        logger.print("  [RAG]   Design unchanged - using cached results")
        changes['design_changed'] = False
        return changes

    logger.print("  [RAG]   Design has changed - analyzing changes...")

    previous_strategy_map = previous_data.get('module_strategy_map', {})
    current_submodules = design_analysis.get('submodules', {})
    current_top_regs = design_analysis.get('registers', [])

    previous_modules = set(previous_strategy_map.keys())
    current_modules = set(current_submodules.keys())
    current_modules.add(design_analysis.get('module_name', 'top'))

    changes['new_modules'] = sorted(list(current_modules - previous_modules))
    changes['removed_modules'] = sorted(list(previous_modules - current_modules))

    for module_name in current_modules & previous_modules:
        if module_name == design_analysis.get('module_name', 'top'):
            current_info = {'registers': current_top_regs}
        else:
            current_info = current_submodules.get(module_name, {})

        current_hash = _compute_module_hash(current_info)

        prev_info = {
            'registers': [
                r for r in previous_data.get('hardened_signals', {}).keys()
                if module_name + '.' in r or (module_name == design_analysis.get('module_name', 'top') and '.' not in r)
            ]
        }
        prev_hash = _compute_module_hash(prev_info)

        if current_hash != prev_hash:
            changes['modified_modules'].append(module_name)
        else:
            changes['unchanged_modules'].append(module_name)

    logger.print(f"  [RAG]   New modules: {changes['new_modules']}")
    logger.print(f"  [RAG]   Modified modules: {changes['modified_modules']}")
    logger.print(f"  [RAG]   Removed modules: {changes['removed_modules']}")
    logger.print(f"  [RAG]   Unchanged modules: {changes['unchanged_modules']}")

    logger.print("  [RAG] ")
    logger.print("  [RAG] ===========================================")
    logger.print("  [RAG] Change Detection Completed")
    logger.print("  [RAG] ===========================================")

    return changes


def apply_incremental_hardening(
    design_analysis: Dict[str, Any],
    previous_data: Dict[str, Any],
    changes: Dict[str, Any],
    default_strategy: str = 'tmr',
) -> Dict[str, Any]:
    """Apply incremental hardening, reusing previous results where possible.

    Args:
        design_analysis: Current design analysis
        previous_data: Previously saved incremental data
        changes: Change detection result
        default_strategy: Default strategy for new modules

    Returns:
        Updated strategy mapping
    """
    logger.section("Incremental Hardening Application")
    logger.print("  [RAG] ===========================================")
    logger.print("  [RAG] Incremental Hardening Started")
    logger.print("  [RAG] ===========================================")

    previous_map = previous_data.get('module_strategy_map', {})
    new_map = previous_map.copy()

    for module in changes['removed_modules']:
        if module in new_map:
            del new_map[module]
            logger.print(f"  [RAG]   Removed module: {module}")

    for module in changes['modified_modules']:
        if module in previous_map:
            new_map[module] = previous_map[module]
            logger.print(f"  [RAG]   Reused strategy for modified module '{module}': {previous_map[module]}")
        else:
            new_map[module] = default_strategy
            logger.print(f"  [RAG]   Applied default strategy for modified module '{module}': {default_strategy}")

    for module in changes['new_modules']:
        new_map[module] = default_strategy
        logger.print(f"  [RAG]   Applied default strategy for new module '{module}': {default_strategy}")

    for module in changes['unchanged_modules']:
        if module in previous_map:
            new_map[module] = previous_map[module]
            logger.print(f"  [RAG]   Reused strategy for unchanged module '{module}': {previous_map[module]}")

    logger.print("  [RAG] ")
    logger.print("  [RAG] --- Final Strategy Map ---")
    for module_name, strategy in sorted(new_map.items()):
        logger.print(f"  [RAG]   {module_name}: {strategy}")

    logger.print("  [RAG] ")
    logger.print("  [RAG] ===========================================")
    logger.print("  [RAG] Incremental Hardening Completed")
    logger.print("  [RAG] ===========================================")

    return {
        'module_strategy_map': new_map,
        'reused_modules': len(changes['unchanged_modules']) + len(changes['modified_modules']),
        'new_modules': len(changes['new_modules']),
        'removed_modules': len(changes['removed_modules']),
    }


def run_incremental_hardening(
    design_analysis: Dict[str, Any],
    output_dir: str,
    default_strategy: str = 'tmr',
) -> Dict[str, Any]:
    """Run the complete incremental hardening pipeline.

    Args:
        design_analysis: Design analysis output
        output_dir: Output directory for incremental data
        default_strategy: Default strategy for new modules

    Returns:
        Result dict with strategy map and change info
    """
    previous_data = load_incremental_data(output_dir)
    changes = detect_design_changes(design_analysis, previous_data)

    if not changes['design_changed'] and previous_data:
        return {
            'module_strategy_map': previous_data.get('module_strategy_map', {}),
            'hardened_signals': previous_data.get('hardened_signals', {}),
            'design_changed': False,
            'reused_all': True,
        }

    result = apply_incremental_hardening(design_analysis, previous_data or {}, changes, default_strategy)

    current_hash = _compute_design_hash(design_analysis)
    save_incremental_data(
        output_dir,
        current_hash,
        result['module_strategy_map'],
        {},
    )

    return {
        'module_strategy_map': result['module_strategy_map'],
        'design_changed': True,
        'reused_modules': result['reused_modules'],
        'new_modules': result['new_modules'],
        'removed_modules': result['removed_modules'],
    }