import os
import json
from typing import Dict, List, Any, Optional
from logger import logger

_STRATEGY_AREA_OVERHEAD: Dict[str, float] = {
    'tmr': 3.0,
    'dice': 2.5,
    'ecc': 1.4,
    'parity': 0.03,
    'cnt_comp': 0.1,
    'onehot_fsm': 1.1,
    'watchdog': 0.5,
    'parity_bus': 0.03,
}

_STRATEGY_LATENCY_OVERHEAD: Dict[str, int] = {
    'tmr': 1,
    'dice': 0,
    'ecc': 1,
    'parity': 0,
    'cnt_comp': 0,
    'onehot_fsm': 0,
    'watchdog': 0,
    'parity_bus': 0,
}

_STRATEGY_RELIABILITY: Dict[str, int] = {
    'tmr': 5,
    'dice': 5,
    'ecc': 4,
    'parity': 2,
    'cnt_comp': 3,
    'onehot_fsm': 4,
    'watchdog': 2,
    'parity_bus': 2,
}


def calculate_hardening_metrics(
    design_analysis: Dict[str, Any],
    module_strategy_map: Dict[str, str],
) -> Dict[str, Any]:
    """Calculate hardening metrics including area, latency, and reliability.

    Args:
        design_analysis: Output from analyze_design_for_hardening()
        module_strategy_map: Module strategy mapping

    Returns:
        Metrics dict with area increase, latency overhead, and reliability estimates
    """
    logger.section("Hardening Metrics Calculation")
    logger.print("  [RAG] ===========================================")
    logger.print("  [RAG] Metrics Calculation Started")
    logger.print("  [RAG] ===========================================")

    top_module = design_analysis.get('module_name', 'top')
    all_registers = design_analysis.get('all_registers', [])
    submodules = design_analysis.get('submodules', {})

    total_registers = len(all_registers)
    total_signal_bits = sum(r.get('width', 1) for r in all_registers)

    area_by_module = {}
    latency_by_module = {}
    reliability_by_module = {}

    total_area_overhead = 0.0
    max_latency_overhead = 0
    avg_reliability = 0.0

    for module_name, strategy in module_strategy_map.items():
        if module_name == top_module:
            mod_registers = design_analysis.get('registers', [])
        else:
            mod_registers = submodules.get(module_name, {}).get('registers', [])

        mod_bit_count = sum(r.get('width', 1) for r in mod_registers)
        mod_reg_count = len(mod_registers)

        area_overhead = _STRATEGY_AREA_OVERHEAD.get(strategy, 1.0)
        latency_overhead = _STRATEGY_LATENCY_OVERHEAD.get(strategy, 0)
        reliability = _STRATEGY_RELIABILITY.get(strategy, 3)

        area_by_module[module_name] = {
            'strategy': strategy,
            'base_bits': mod_bit_count,
            'hardened_bits': mod_bit_count * area_overhead,
            'area_overhead': area_overhead,
            'register_count': mod_reg_count,
        }

        latency_by_module[module_name] = {
            'strategy': strategy,
            'latency_cycles': latency_overhead,
        }

        reliability_by_module[module_name] = {
            'strategy': strategy,
            'reliability_level': reliability,
            'reliability_stars': '★' * reliability + '☆' * (5 - reliability),
        }

        total_area_overhead += mod_bit_count * (area_overhead - 1)
        max_latency_overhead = max(max_latency_overhead, latency_overhead)

    avg_reliability = sum(
        _STRATEGY_RELIABILITY.get(s, 3) for s in module_strategy_map.values()
    ) / len(module_strategy_map) if module_strategy_map else 0

    area_increase_percent = (total_area_overhead / total_signal_bits * 100) if total_signal_bits > 0 else 0

    logger.print(f"  [RAG]   Total registers: {total_registers}")
    logger.print(f"  [RAG]   Total signal bits: {total_signal_bits}")
    logger.print(f"  [RAG]   Area increase: {area_increase_percent:.1f}% ({total_area_overhead:.0f} extra bits)")
    logger.print(f"  [RAG]   Max latency overhead: {max_latency_overhead} cycles")
    logger.print(f"  [RAG]   Avg reliability: {'★' * int(avg_reliability)}{'☆' * (5 - int(avg_reliability))} ({avg_reliability:.1f}/5)")

    logger.print("  [RAG] ")
    logger.print("  [RAG] --- Per-Module Metrics ---")
    for module_name, metrics in sorted(area_by_module.items()):
        logger.print(f"  [RAG]   {module_name}:")
        logger.print(f"  [RAG]     Strategy: {metrics['strategy']}")
        logger.print(f"  [RAG]     Area overhead: {metrics['area_overhead']}×")
        logger.print(f"  [RAG]     Registers: {metrics['register_count']}")

    logger.print("  [RAG] ")
    logger.print("  [RAG] ===========================================")
    logger.print("  [RAG] Metrics Calculation Completed")
    logger.print("  [RAG] ===========================================")

    return {
        'summary': {
            'total_modules': len(module_strategy_map),
            'total_registers': total_registers,
            'total_signal_bits': total_signal_bits,
            'area_increase_percent': area_increase_percent,
            'area_increase_bits': total_area_overhead,
            'max_latency_cycles': max_latency_overhead,
            'avg_reliability': avg_reliability,
            'avg_reliability_stars': '★' * int(avg_reliability) + '☆' * (5 - int(avg_reliability)),
        },
        'by_module': {
            'area': area_by_module,
            'latency': latency_by_module,
            'reliability': reliability_by_module,
        },
        'strategy_map': module_strategy_map,
    }


def generate_hardening_report(
    metrics: Dict[str, Any],
    output_path: Optional[str] = None,
) -> str:
    """Generate a human-readable hardening report.

    Args:
        metrics: Output from calculate_hardening_metrics()
        output_path: Optional path to save the report

    Returns:
        Report content as string
    """
    summary = metrics['summary']
    area_by_module = metrics['by_module']['area']
    reliability_by_module = metrics['by_module']['reliability']

    report = "# RTL Hardening Effect Report\n\n"
    report += "## 1. Summary\n\n"
    report += f"| Metric | Value |\n"
    report += f"|:-------|:------|\n"
    report += f"| Total Modules | {summary['total_modules']} |\n"
    report += f"| Total Registers | {summary['total_registers']} |\n"
    report += f"| Total Signal Bits | {summary['total_signal_bits']} |\n"
    report += f"| Area Increase | {summary['area_increase_percent']:.1f}% ({summary['area_increase_bits']:.0f} extra bits) |\n"
    report += f"| Max Latency Overhead | {summary['max_latency_cycles']} cycles |\n"
    report += f"| Average Reliability | {summary['avg_reliability_stars']} ({summary['avg_reliability']:.1f}/5) |\n"

    report += "\n## 2. Per-Module Analysis\n\n"

    report += "### 2.1 Area Overhead\n\n"
    report += "| Module | Strategy | Registers | Area Overhead |\n"
    report += "|:-------|:---------|:----------|:-------------|\n"
    for module_name, metrics in sorted(area_by_module.items()):
        report += f"| {module_name} | {metrics['strategy']} | {metrics['register_count']} | {metrics['area_overhead']}× |\n"

    report += "\n### 2.2 Reliability\n\n"
    report += "| Module | Strategy | Reliability |\n"
    report += "|:-------|:---------|:------------|\n"
    for module_name, metrics in sorted(reliability_by_module.items()):
        report += f"| {module_name} | {metrics['strategy']} | {metrics['reliability_stars']} |\n"

    report += "\n## 3. Strategy Distribution\n\n"
    strategy_counts = {}
    for strategy in metrics['strategy_map'].values():
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

    report += "| Strategy | Modules |\n"
    report += "|:---------|:--------|\n"
    for strategy, count in sorted(strategy_counts.items(), key=lambda x: -x[1]):
        report += f"| {strategy} | {count} |\n"

    report += "\n## 4. Key Metrics\n\n"
    report += f"- **Area Impact**: {'High' if summary['area_increase_percent'] > 100 else 'Medium' if summary['area_increase_percent'] > 50 else 'Low'}\n"
    report += f"- **Performance Impact**: {'High' if summary['max_latency_cycles'] > 2 else 'Medium' if summary['max_latency_cycles'] > 0 else 'Low'}\n"
    report += f"- **Reliability Level**: {'Excellent' if summary['avg_reliability'] >= 4 else 'Good' if summary['avg_reliability'] >= 3 else 'Basic'}\n"

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.print(f"  [RAG]   Report saved to: {output_path}")

    return report


def generate_metrics_json(
    metrics: Dict[str, Any],
    output_path: str,
) -> None:
    """Generate JSON format metrics for programmatic access.

    Args:
        metrics: Output from calculate_hardening_metrics()
        output_path: Path to save the JSON file
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    logger.print(f"  [RAG]   Metrics JSON saved to: {output_path}")


def generate_visualization_html(
    metrics: Dict[str, Any],
    output_path: str,
) -> None:
    """Generate HTML visualization of hardening metrics.

    Args:
        metrics: Output from calculate_hardening_metrics()
        output_path: Path to save the HTML file
    """
    summary = metrics['summary']
    area_by_module = metrics['by_module']['area']
    strategy_map = metrics['strategy_map']

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RTL Hardening Effect Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; border-bottom: 3px solid #2196F3; padding-bottom: 10px; }}
        .summary-card {{ background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .metric-row {{ display: flex; flex-wrap: wrap; gap: 20px; }}
        .metric-box {{ flex: 1; min-width: 150px; background: #e3f2fd; border-radius: 8px; padding: 15px; text-align: center; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #1976D2; }}
        .metric-label {{ font-size: 12px; color: #666; margin-top: 5px; }}
        .table-container {{ background: white; border-radius: 8px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #2196F3; color: white; }}
        tr:hover {{ background: #f1f1f1; }}
        .bar-chart {{ height: 20px; background: #e0e0e0; border-radius: 10px; overflow: hidden; }}
        .bar-fill {{ height: 100%; border-radius: 10px; transition: width 0.3s; }}
        .tmr {{ background: #f44336; }}
        .dice {{ background: #FF9800; }}
        .ecc {{ background: #2196F3; }}
        .parity {{ background: #4CAF50; }}
        .cnt_comp {{ background: #8BC34A; }}
        .onehot_fsm {{ background: #9C27B0; }}
        .watchdog {{ background: #FFEB3B; }}
        .parity_bus {{ background: #CDDC39; }}
        .strategy-badge {{ padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .reliability-stars {{ color: #FFC107; font-size: 18px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔧 RTL Hardening Effect Report</h1>
        
        <div class="summary-card">
            <h2>📊 Summary</h2>
            <div class="metric-row">
                <div class="metric-box">
                    <div class="metric-value">{summary['total_modules']}</div>
                    <div class="metric-label">Total Modules</div>
                </div>
                <div class="metric-box">
                    <div class="metric-value">{summary['total_registers']}</div>
                    <div class="metric-label">Total Registers</div>
                </div>
                <div class="metric-box">
                    <div class="metric-value">{summary['total_signal_bits']}</div>
                    <div class="metric-label">Total Signal Bits</div>
                </div>
                <div class="metric-box">
                    <div class="metric-value">{summary['area_increase_percent']:.1f}%</div>
                    <div class="metric-label">Area Increase</div>
                </div>
                <div class="metric-box">
                    <div class="metric-value">{summary['max_latency_cycles']} cycles</div>
                    <div class="metric-label">Max Latency Overhead</div>
                </div>
                <div class="metric-box">
                    <div class="metric-value reliability-stars">{summary['avg_reliability_stars']}</div>
                    <div class="metric-label">Avg Reliability</div>
                </div>
            </div>
        </div>
        
        <div class="table-container">
            <h2>📈 Per-Module Area Overhead</h2>
            <table>
                <tr><th>Module</th><th>Strategy</th><th>Registers</th><th>Area Overhead</th><th>Visualization</th></tr>"""

    for module_name, metrics_item in sorted(area_by_module.items()):
        percent = (metrics_item['area_overhead'] / 3.0) * 100
        html += f"""
                <tr>
                    <td><strong>{module_name}</strong></td>
                    <td><span class="strategy-badge {metrics_item['strategy']}">{metrics_item['strategy']}</span></td>
                    <td>{metrics_item['register_count']}</td>
                    <td>{metrics_item['area_overhead']}×</td>
                    <td><div class="bar-chart"><div class="bar-fill {metrics_item['strategy']}" style="width:{percent}%"></div></div></td>
                </tr>"""

    html += """
            </table>
        </div>
        
        <div class="table-container">
            <h2>🎯 Strategy Distribution</h2>
            <table>
                <tr><th>Strategy</th><th>Count</th><th>Percentage</th></tr>"""

    total_modules = len(strategy_map)
    strategy_counts = {}
    for strategy in strategy_map.values():
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

    for strategy, count in sorted(strategy_counts.items(), key=lambda x: -x[1]):
        percent = (count / total_modules) * 100
        html += f"""
                <tr>
                    <td><span class="strategy-badge {strategy}">{strategy}</span></td>
                    <td>{count}</td>
                    <td><div class="bar-chart"><div class="bar-fill {strategy}" style="width:{percent}%"></div></div></td>
                </tr>"""

    html += """
            </table>
        </div>
    </div>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    logger.print(f"  [RAG]   Visualization HTML saved to: {output_path}")


def visualize_hardening_effect(
    design_analysis: Dict[str, Any],
    module_strategy_map: Dict[str, str],
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Complete visualization pipeline.

    Args:
        design_analysis: Output from analyze_design_for_hardening()
        module_strategy_map: Module strategy mapping
        output_dir: Output directory for reports

    Returns:
        Metrics and report paths
    """
    metrics = calculate_hardening_metrics(design_analysis, module_strategy_map)

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'reports')
    os.makedirs(output_dir, exist_ok=True)

    report_path = os.path.join(output_dir, 'hardening_effect_report.md')
    json_path = os.path.join(output_dir, 'hardening_metrics.json')
    html_path = os.path.join(output_dir, 'hardening_effect_report.html')

    generate_hardening_report(metrics, report_path)
    generate_metrics_json(metrics, json_path)
    generate_visualization_html(metrics, html_path)

    return {
        'metrics': metrics,
        'report_path': report_path,
        'json_path': json_path,
        'html_path': html_path,
    }


# ======================================================================
# Matplotlib charting utilities (radar & trend charts)
# ======================================================================

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from matplotlib.spines import Spine
    from matplotlib.path import Path
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

_CHART_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'output', 'charts')


def _ensure_chart_dir():
    """Create the chart output directory if it does not exist."""
    if not os.path.exists(_CHART_DIR):
        os.makedirs(_CHART_DIR, exist_ok=True)


def _sanitize_filename(title: str) -> str:
    """Convert a title string to a safe filename."""
    safe = ''.join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in title)
    return safe.replace(' ', '_').lower()


def plot_radar_chart(metrics: dict, title: str = "Hardening Effect Radar") -> str:
    """Plot a radar chart for the given metrics dict.

    The dict should contain exactly 5 keys representing the dimensions:
    e.g. {"面积开销": 3.0, "延迟开销": 1, "可靠性得分": 5, "策略多样性": 4, "覆盖率": 0.85}

    Args:
        metrics: A dictionary of dimension -> value.
        title:  Chart title.

    Returns:
        Saved PNG file path, or None on failure.
    """
    if not MATPLOTLIB_AVAILABLE:
        print("[WARNING] matplotlib is not installed. Unable to plot radar chart.")
        return None

    try:
        _ensure_chart_dir()

        labels = list(metrics.keys())
        values = list(metrics.values())
        num_vars = len(labels)

        # Compute angle for each axis and close the loop
        angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
        values += values[:1]
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
        ax.fill(angles, values, alpha=0.3)
        ax.plot(angles, values, linewidth=2)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, fontsize=12)
        ax.set_ylim(0, max(values) * 1.15 if max(values) > 0 else 1)
        ax.set_title(title, fontsize=16, pad=20)

        plt.tight_layout()

        _ensure_chart_dir()
        safe_name = _sanitize_filename(title) + '.png'
        save_path = os.path.join(_CHART_DIR, safe_name)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        return save_path

    except Exception as e:
        print(f"[ERROR] Failed to plot radar chart: {e}")
        return None


def plot_trend_chart(history_data: list, title: str = "Hardening Effect Trend") -> str:
    """Plot a trend line chart from history data.

    Each element in history_data should be a dict like:
        {"timestamp": "2026-07-18", "area": 3.0, "reliability": 5, "latency": 1}

    Args:
        history_data: List of data points with timestamp and metric keys.
        title:        Chart title.

    Returns:
        Saved PNG file path, or None on failure.
    """
    if not MATPLOTLIB_AVAILABLE:
        print("[WARNING] matplotlib is not installed. Unable to plot trend chart.")
        return None

    try:
        _ensure_chart_dir()

        timestamps = [d['timestamp'] for d in history_data]
        area_values = [d.get('area', 0) for d in history_data]
        reliability_values = [d.get('reliability', 0) for d in history_data]
        latency_values = [d.get('latency', 0) for d in history_data]

        fig, ax = plt.subplots(figsize=(12, 6))

        x = range(len(timestamps))
        ax.plot(x, area_values, marker='o', label='Area', linewidth=2)
        ax.plot(x, reliability_values, marker='s', label='Reliability', linewidth=2)
        ax.plot(x, latency_values, marker='^', label='Latency', linewidth=2)

        ax.set_xticks(x)
        ax.set_xticklabels(timestamps, fontsize=10)
        plt.xticks(rotation=45, ha='right')
        ax.set_xlabel('Timestamp', fontsize=12)
        ax.set_ylabel('Value', fontsize=12)
        ax.set_title(title, fontsize=16)
        ax.legend(fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.6)

        plt.tight_layout()

        safe_name = _sanitize_filename(title) + '.png'
        save_path = os.path.join(_CHART_DIR, safe_name)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        return save_path

    except Exception as e:
        print(f"[ERROR] Failed to plot trend chart: {e}")
        return None


def plot_multi_radar_comparison(records: list, title: str = "Multi-Design Comparison") -> str:
    """Overlay multiple radar charts on the same axes for comparison.

    Each record in records is a metrics dict with the same keys, e.g.:
        {"面积开销": 3.0, "延迟开销": 1, "可靠性得分": 5, "策略多样性": 4, "覆盖率": 0.85}

    Args:
        records: A list of metrics dicts.
        title:   Chart title.

    Returns:
        Saved PNG file path, or None on failure.
    """
    if not MATPLOTLIB_AVAILABLE:
        print("[WARNING] matplotlib is not installed. Unable to plot multi-radar comparison.")
        return None

    try:
        _ensure_chart_dir()

        if not records:
            print("[ERROR] Empty records list provided for multi-radar comparison.")
            return None

        labels = list(records[0].keys())
        num_vars = len(labels)
        angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
        angles += angles[:1]

        colors = ['#2196F3', '#FF5722', '#4CAF50', '#9C27B0', '#FFC107', '#00BCD4']

        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

        for i, rec in enumerate(records):
            values = list(rec.values())
            values += values[:1]
            color = colors[i % len(colors)]
            ax.fill(angles, values, alpha=0.08, color=color)
            ax.plot(angles, values, linewidth=2, color=color, label=f'Design {i + 1}')

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, fontsize=12)

        all_values = [v for rec in records for v in rec.values()]
        ax.set_ylim(0, max(all_values) * 1.15 if max(all_values) > 0 else 1)
        ax.set_title(title, fontsize=16, pad=20)
        ax.legend(fontsize=11, loc='upper right', bbox_to_anchor=(1.3, 1.0))

        plt.tight_layout()

        safe_name = _sanitize_filename(title) + '.png'
        save_path = os.path.join(_CHART_DIR, safe_name)
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        return save_path

    except Exception as e:
        print(f"[ERROR] Failed to plot multi-radar comparison: {e}")
        return None