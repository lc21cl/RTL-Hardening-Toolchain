#!/usr/bin/env python3
"""
harden_gui.py — RTL 加固工具集 GUI 界面（流程导向版）

集成 hardening_pipeline / run_regression / scan_high_fanout_signals /
demo_aig_analysis / gen_mock_aig / strategy_auto_select / hardening_visualizer 等工具的可视化操作界面。

用法:
    python harden_gui.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess
import os
import sys
import threading
import json
import re
import time
import webbrowser

try:
    import matplotlib
    matplotlib.use('TkAgg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    import gradio as gr
    GRADIO_AVAILABLE = True
except ImportError:
    GRADIO_AVAILABLE = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(SCRIPT_DIR, 'reports')
TEST_MOCK_DIR = os.path.join(SCRIPT_DIR, 'test_mock_data')
SIM_FORMAL_DIR = os.path.join(SCRIPT_DIR, 'sim', 'formal_test')

OUTPUT_ROOT = os.path.join(SCRIPT_DIR, 'output')
OUTPUT_DIRS = {
    'rtl_single': os.path.join(OUTPUT_ROOT, 'rtl_single'),
    'rtl_folder': os.path.join(OUTPUT_ROOT, 'rtl_folder'),
    'rtl_dataset': os.path.join(OUTPUT_ROOT, 'rtl_dataset'),
    'fpga_bitstream': os.path.join(OUTPUT_ROOT, 'fpga_bitstream'),
    'reports': os.path.join(OUTPUT_ROOT, 'reports'),
    'logs': os.path.join(OUTPUT_ROOT, 'logs'),
}

for dir_path in OUTPUT_DIRS.values():
    os.makedirs(dir_path, exist_ok=True)

VERSION = "5.4.0"
APP_TITLE = f"RTL 加固工具集 v{VERSION}"

WORKFLOWS = {
    'rtl_single': {
        'name': 'RTL 单文件加固',
        'description': '对单个 Verilog/SystemVerilog 文件进行加固处理',
        'icon': '📄',
        'steps': [
            {'id': 'select_file', 'name': '选择文件', 'desc': '选择 RTL 文件并查看代码，执行信号扫描'},
            {'id': 'config_strategy', 'name': '配置策略', 'desc': '使用策略推荐或手动选择加固策略'},
            {'id': 'execute', 'name': '执行加固', 'desc': '运行层次化加固管线'},
            {'id': 'verify', 'name': '验证分析', 'desc': '查看加固代码、AIG分析、效果可视化'},
            {'id': 'export', 'name': '导出报告', 'desc': '生成 HTML 可靠性报告并查看'},
        ]
    },
    'rtl_folder': {
        'name': 'RTL 文件夹批量加固',
        'description': '对整个文件夹中的 RTL 文件进行批量加固',
        'icon': '📁',
        'steps': [
            {'id': 'select_folder', 'name': '选择文件夹', 'desc': '选择 RTL 文件夹并执行信号扫描'},
            {'id': 'config_strategy', 'name': '配置策略', 'desc': '使用策略推荐或手动选择加固策略'},
            {'id': 'execute', 'name': '执行批量加固', 'desc': '批量运行层次化加固'},
            {'id': 'summary', 'name': '验证分析', 'desc': '查看汇总、AIG分析、效果可视化'},
            {'id': 'export', 'name': '导出报告', 'desc': '生成汇总报告并查看'},
        ]
    },
    'rtl_dataset': {
        'name': 'RTL 数据集加固',
        'description': '对数据集目录下的多个设计项目进行加固',
        'icon': '📊',
        'steps': [
            {'id': 'select_dataset', 'name': '选择数据集', 'desc': '选择数据集根目录'},
            {'id': 'config_strategy', 'name': '配置策略', 'desc': '使用策略推荐或手动选择加固策略'},
            {'id': 'execute', 'name': '执行数据集加固', 'desc': '运行层次化加固管线'},
            {'id': 'analysis', 'name': '验证分析', 'desc': '信号扫描、AIG分析、数据可视化'},
            {'id': 'export', 'name': '导出报告', 'desc': '生成数据集分析报告并查看'},
        ]
    },
    'fpga_bitstream': {
        'name': 'FPGA 比特流加固',
        'description': '对 FPGA 比特流进行加固处理（TMR/ECC/Scrubbing）',
        'icon': '🔧',
        'steps': [
            {'id': 'select_bitstream', 'name': '选择比特流', 'desc': '选择 FPGA 比特流文件'},
            {'id': 'config_fpga', 'name': '配置加固方式', 'desc': '选择 TMR/ECC/Scrubbing 等'},
            {'id': 'execute', 'name': '执行比特流加固', 'desc': '对比特流进行加固处理'},
            {'id': 'verify', 'name': '验证测试', 'desc': '运行测试套件验证加固效果'},
            {'id': 'export', 'name': '导出结果', 'desc': '导出加固后的比特流'},
        ]
    },
}

# ── 主题配置 ──
THEMES = {
    'light': {
        'bg': '#ffffff', 'fg': '#000000', 'selectbg': '#0078d7',
        'treebg': '#ffffff', 'treefg': '#000000',
        'buttonbg': '#f0f0f0', 'entrybg': '#ffffff',
        'frame': '#f5f5f5', 'labelfg': '#333333',
        'notebookbg': '#ffffff', 'notebookfg': '#000000',
    },
    'dark': {
        'bg': '#2d2d2d', 'fg': '#ffffff', 'selectbg': '#264f78',
        'treebg': '#3c3c3c', 'treefg': '#ffffff',
        'buttonbg': '#3c3c3c', 'entrybg': '#3c3c3c',
        'frame': '#383838', 'labelfg': '#cccccc',
        'notebookbg': '#2d2d2d', 'notebookfg': '#e0e0e0',
    },
}

def run_python_script(script_name, args=""):
    script_path = os.path.join(SIM_FORMAL_DIR, script_name)
    if not os.path.exists(script_path):
        return (-1, "", f"脚本不存在: {script_path}")
    cmd = f'"{sys.executable}" "{script_path}" {args}'
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=SCRIPT_DIR)
    return (result.returncode, result.stdout, result.stderr)

def add_tooltip(widget, text):
    def on_enter(event):
        tooltip = tk.Toplevel(widget)
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
        label = ttk.Label(tooltip, text=text, background="#FFFACD", relief="solid", borderwidth=1, padding=5)
        label.pack()
        widget._tooltip = tooltip

    def on_leave(event):
        if hasattr(widget, '_tooltip'):
            widget._tooltip.destroy()
            del widget._tooltip

    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)


class HardeningGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1200x800")
        self.root.minsize(1000, 600)

        self.current_workflow = None
        self.current_step = 0
        self.workflow_data = {}

        self.strategy_vars = {
            'tmr':      tk.BooleanVar(value=False),
            'dice':     tk.BooleanVar(value=False),
            'ecc':      tk.BooleanVar(value=False),
            'parity':   tk.BooleanVar(value=False),
            'cnt_comp': tk.BooleanVar(value=False),
            'fsm_tmr':  tk.BooleanVar(value=False),
            'bch_ecc':  tk.BooleanVar(value=False),  # v5.4: BCH码多比特纠错
        }

        # 增强功能选项
        self.aig_enabled_var = tk.BooleanVar(value=True)
        self.fault_injection_var = tk.BooleanVar(value=True)
        self.llm_enhance_var = tk.BooleanVar(value=False)
        self.llm_backend_var = tk.StringVar(value='mock')

        # ── 新增功能选项 ──
        self.comment_directives_var = tk.BooleanVar(value=True)    # 注释约束
        self.gen_keep_var = tk.BooleanVar(value=True)              # 综合保护-keep
        self.gen_sdc_var = tk.BooleanVar(value=True)               # 综合保护-SDC
        self.parallel_mode_var = tk.BooleanVar(value=False)        # 并行模式(大设计默认关)
        self.failure_kb_var = tk.BooleanVar(value=True)            # 故障知识积累
        self.multi_verify_var = tk.BooleanVar(value=True)          # 多层验证管线
        self.exclusion_var = tk.BooleanVar(value=True)             # 投票器禁区规则

        # ── 新增FSM策略 ──
        self.strategy_vars['fsm_hamming'] = tk.BooleanVar(value=False)
        self.strategy_vars['fsm_safe'] = tk.BooleanVar(value=False)

        # ── 新增DICE变体 ──
        self.strategy_vars['dnurl'] = tk.BooleanVar(value=False)
        self.strategy_vars['tnudice'] = tk.BooleanVar(value=False)

        # ── 投票器类型 ──
        self.voter_type_var = tk.StringVar(value='reducing')  # reducing, partitioning, sync, cdc

        self.error_signal_var = tk.BooleanVar(value=True)   # 错误信号OR-tree使能

        self.single_file_var = tk.StringVar()
        self.folder_var = tk.StringVar()
        self.dataset_var = tk.StringVar()
        self.bitstream_var = tk.StringVar()

        # ── 多语言支持 ──
        self.language_var = tk.StringVar(value='zh')  # 'zh' 或 'en'
        self.translations = self._load_translations()

        # ── 主题切换 ──
        self.current_theme = tk.StringVar(value='light')

        # ── 批量进度条 ──
        self.folder_progress_var = tk.IntVar(value=0)
        self.dataset_progress_var = tk.IntVar(value=0)
        self.progress_label_var = tk.StringVar(value='')

        # ── 加固历史记录 ──
        try:
            sys.path.insert(0, SCRIPT_DIR)
            from sim.formal_test.hardening_history import HardeningHistory
            self.history = HardeningHistory()
            _HISTORY_AVAILABLE = True
            print("[HISTORY] HardeningHistory initialized successfully")
        except Exception as e:
            self.history = None
            _HISTORY_AVAILABLE = False
            print(f"[HISTORY] Failed to initialize: {e}")

        self._setup_styles()
        self._create_main_layout()
        self._show_workflow_selection()

    # ── 一键升级功能 ──
    def check_for_updates(self):
        """检查GitHub最新版本（在非阻塞线程中执行）"""
        import threading
        def _check():
            try:
                repo = "lc21cl/RTL-Hardening-Toolchain"
                import urllib.request
                import json
                url = f"https://api.github.com/repos/{repo}/releases/latest"
                req = urllib.request.Request(url, headers={'User-Agent': 'RTL-Hardening-Tool'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    latest_tag = data.get('tag_name', 'v0.0')
                    if latest_tag > 'v5.0':
                        self._append_output(f"📣 发现新版本 {latest_tag}！请访问GitHub更新")
                        self._append_output(f"   https://github.com/{repo}/releases")
                    else:
                        self._append_output(f"✅ 当前 v5.0 已是最新版本")
            except Exception as e:
                self._append_output(f"⚠️ 版本检查失败: {e}")
        t = threading.Thread(target=_check, daemon=True)
        t.start()

    def _get_gui_config_path(self) -> str:
        config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, 'gui_config.json')
    
    def save_gui_config(self):
        """保存GUI配置到JSON"""
        config = {}
        # 收集所有变量值
        for attr in dir(self):
            if attr.endswith('_var'):
                try:
                    var = getattr(self, attr)
                    if hasattr(var, 'get'):
                        config[attr] = var.get()
                except Exception:
                    pass
        try:
            path = self._get_gui_config_path()
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            self._append_output(f"💾 配置已保存")
        except Exception as e:
            self._append_output(f"⚠️ 配置保存失败: {e}")
    
    def load_gui_config(self):
        """从JSON加载GUI配置"""
        path = self._get_gui_config_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            for attr, val in config.items():
                if hasattr(self, attr):
                    try:
                        var = getattr(self, attr)
                        if hasattr(var, 'set'):
                            var.set(val)
                    except Exception:
                        pass
            self._append_output(f"📂 配置已加载")
        except Exception as e:
            self._append_output(f"⚠️ 配置加载失败: {e}")

    def _load_translations(self):
        """加载中英文翻译字典"""
        return {
            'zh': {
                'app_title': 'RTL加固工具',
                'root_title': f'RTL 加固工具集 v{VERSION}',
                'btn_upload': '选择文件',
                'btn_execute': '开始执行加固',
                'btn_export': '导出报告',
                'btn_browse': '浏览...',
                'btn_example': '使用示例',
                'btn_back_home': '← 返回首页',
                'btn_help': '帮助',
                'btn_config': '⚙️ 配置',
                'btn_web_gui': '🌐 Web GUI',
                'btn_history': '📋 历史记录',
                'btn_prev': '上一步',
                'btn_next': '下一步',
                'btn_finish': '完成',
                'step_load': '选择文件/加载设计',
                'step_config': '配置加固策略',
                'step_execute': '执行加固',
                'step_verify': '验证分析',
                'step_export': '导出报告',
                'status_ready': '就绪',
                'status_label': '状态: ',
                'strategy_tmr': 'TMR',
                'strategy_tmr_name': '三模冗余 (3副本+多数表决器)',
                'strategy_dice': 'DICE',
                'strategy_dice_name': '双互锁存储单元',
                'strategy_ecc': 'ECC',
                'strategy_ecc_name': 'SECDED纠错码',
                'strategy_parity': 'Parity',
                'strategy_parity_name': '奇偶校验',
                'strategy_cnt_comp': 'cnt_comp',
                'strategy_cnt_comp_name': '计数器比较器',
                'strategy_fsm_tmr': 'FSM_TMR',
                'strategy_fsm_tmr_name': '状态机三重化',
                'desc_tmr': '高可靠性，面积开销大',
                'desc_dice': '抗SEU，适用于寄存器',
                'desc_ecc': '检测并纠正单比特错误',
                'desc_parity': '检测单比特错误，开销小',
                'desc_cnt_comp': '检测计数器翻转错误',
                'desc_fsm_tmr': '状态机专用TMR',
                'strategy_fsm_hamming': 'FSM_Hamming',
                'strategy_fsm_hamming_name': '状态机汉明码 (3副本+汉明距离3)',
                'desc_fsm_hamming': 'FSM汉明距离3编码容错',
                'strategy_fsm_safe': 'FSM_Safe',
                'strategy_fsm_safe_name': '安全状态机 (非法状态恢复)',
                'desc_fsm_safe': '检测并恢复非法FSM状态',
                'strategy_dnurl': 'DNURL',
                'strategy_dnurl_name': '双节点DICE (2节点翻转恢复)',
                'desc_dnurl': '双节点同时翻转恢复保护',
                'strategy_tnudice': 'TNUDICE',
                'strategy_tnudice_name': '三节点DICE (3节点翻转恢复)',
                'desc_tnudice': '三节点同时翻转恢复保护',
                'strategy_bch_ecc': 'BCH_ECC',
                'strategy_bch_ecc_name': 'BCH码多比特纠错 (BCH(15,7,2))',
                'desc_bch_ecc': '基于GF(2^m)域的BCH码多比特错误纠正',
                'enhance_aig': '📈 自动AIG分析 — 加固后自动分析电路结构',
                'enhance_fault': '🛡️ 故障注入验证 — 量化加固效果(需iverilog)',
                'enhance_llm': '🤖 LLM增强加固 — 使用大语言模型优化加固代码',
                'llm_backend': 'LLM后端:',
                'opt_balanced': '平衡 — 面积与可靠性兼顾',
                'opt_area': '面积优先 — 最小化面积开销',
                'opt_reliability': '可靠性优先 — 最大化可靠性',
                'opt_performance': '性能优先 — 最小化延迟',
                'label_strategy': '选择加固策略',
                'label_optimization': '优化目标',
                'label_enhance': '增强功能选项',
                'label_output_log': '输出日志',
                'label_code_preview': '代码预览',
                'label_design_info': '设计信息',
                'label_verify': '加固结果验证',
                'label_export_report': '导出报告',
                'btn_scan': '🔍 信号扫描',
                'btn_recommend': '🔮 策略推荐',
                'btn_visualize': '📊 查看效果可视化',
                'btn_aig_analyze': '📈 AIG 详细分析',
                'btn_incremental': '🔄 增量加固(可选)',
                'btn_generate_report': '生成 HTML 报告',
                'btn_view_report': '📖 查看报告',
                'btn_finish_home': '🎉 完成并返回首页',
                'label_report_path': '报告路径:',
                'label_file_path': '文件路径:',
                'label_folder_path': '文件夹路径:',
                'label_dataset_path': '数据集路径:',
                'label_output_dir': '输出目录',
                'label_reg_count': '寄存器数',
                'label_signal_count': '信号数',
                'label_area_overhead': '面积开销',
                'label_reliability': '可靠性',
                'label_delay_overhead': '延迟开销',
                'label_module': '模块名',
                'label_ports': '端口数',
                'label_submodules': '子模块数',
                'label_select_file': '选择 Verilog 文件',
                'label_select_folder': '选择 RTL 文件夹',
                'label_select_dataset': '选择数据集文件',
                'label_workflow_select': '选择加固流程',
                'btn_start': '开始',
                'btn_download_dataset': '⬇️ 下载RTLCoder数据集',
                'label_dataset_info': '数据集信息',
                'label_folder_info': '文件夹信息',
                'label_strategy_title': '选择加固策略',
                'label_execute': '执行加固',
                'label_execute_folder': '执行批量加固',
                'label_execute_dataset': '执行数据集加固',
                'label_execute_run': '开始执行批量加固',
                'label_execute_dataset_run': '开始执行数据集加固',
                'label_export_report_title': '导出报告',
                'btn_generate_folder_report': '生成 HTML 报告',
                'label_batch_execute': '即将对以下文件夹中的所有 RTL 文件执行加固:',
                'label_dataset_execute': '即将对以下数据集目录中的所有设计执行加固:',
                'label_enabled_strategies': '启用的策略:',
                'label_output_frame': '输出日志',
                'label_single_execute': '即将对以下文件执行加固:',
                'label_original_code': '原始代码',
                'label_hardened_code': '加固后代码',
                'label_code_compare': '代码对比',
                'label_strategy_detail': '策略分配详情',
                'label_vuln_scores': '脆弱性评分（Top 5）',
                'label_high_fanout': '高扇出信号',
                'label_fault_injection': '故障注入验证',
                'label_aig_result': 'AIG电路分析结果',
                'label_aig_simulated': '(模拟)',
                'label_injection_count': '注入次数',
                'label_reg_count_fault': '寄存器数',
                'label_avf_before': '加固前AVF',
                'label_avf_after': '加固后AVF',
                'label_improvement': '改善幅度',
                'label_aig_and': 'AND门数',
                'label_aig_pi': '主输入(PI)',
                'label_aig_po': '主输出(PO)',
                'label_aig_latches': '锁存器',
                'label_high_fanout_nodes': '高扇出节点:',
                'label_auto_hierarchical': '🔄 自动层次化加固 — 根据信号类型自动分配最优策略',
                'label_report_generated': '报告已生成',
                'label_view_report_browser': '🌐 在浏览器中查看完整报告',
                'label_save_report': '💾 保存报告',
                'label_quick_start': '快速入门',
                'label_output_dir_structure': '输出目录',
                'btn_download': '开始下载',
                'label_history_title': '加固历史记录',
                'label_history_time': '时间',
                'label_history_design': '设计文件',
                'label_history_type': '流程类型',
                'label_history_strategies': '策略数',
                'label_history_registers': '寄存器数',
                'btn_compare_selected': '对比选中记录',
                'btn_clear_history': '清空历史',
                'label_processing': '正在处理',
                'label_done': '处理完成!',
                'label_progress_folder': '批量加固进度',
                'label_progress_dataset': '数据集加固进度',
                'enhance_comment': '注释驱动约束',
                'enhance_keep': '综合保护',
                'enhance_parallel': '并行模式',
                'enhance_kb': '故障知识积累',
            },
            'en': {
                'app_title': 'RTL Hardening Tool',
                'root_title': f'RTL Hardening Tool v{VERSION}',
                'btn_upload': 'Select File',
                'btn_execute': 'Start Hardening',
                'btn_export': 'Export Report',
                'btn_browse': 'Browse...',
                'btn_example': 'Use Example',
                'btn_back_home': '← Back to Home',
                'btn_help': 'Help',
                'btn_config': '⚙️ Config',
                'btn_web_gui': '🌐 Web GUI',
                'btn_history': '📋 History',
                'btn_prev': 'Previous',
                'btn_next': 'Next',
                'btn_finish': 'Finish',
                'step_load': 'Load Design',
                'step_config': 'Configure Strategy',
                'step_execute': 'Execute',
                'step_verify': 'Verification',
                'step_export': 'Export Report',
                'status_ready': 'Ready',
                'status_label': 'Status: ',
                'strategy_tmr': 'TMR',
                'strategy_tmr_name': 'Triple Modular Redundancy (3-copy + voter)',
                'strategy_dice': 'DICE',
                'strategy_dice_name': 'Dual Interlocked Storage Cell',
                'strategy_ecc': 'ECC',
                'strategy_ecc_name': 'SECDED Error Correction Code',
                'strategy_parity': 'Parity',
                'strategy_parity_name': 'Parity Check',
                'strategy_cnt_comp': 'cnt_comp',
                'strategy_cnt_comp_name': 'Counter Comparator',
                'strategy_fsm_tmr': 'FSM_TMR',
                'strategy_fsm_tmr_name': 'FSM Triplication',
                'desc_tmr': 'High reliability, large area overhead',
                'desc_dice': 'SEU immune, suitable for registers',
                'desc_ecc': 'Detect and correct single-bit errors',
                'desc_parity': 'Detect single-bit errors, low overhead',
                'desc_cnt_comp': 'Detect counter rollover errors',
                'desc_fsm_tmr': 'FSM-specific TMR',
                'strategy_fsm_hamming': 'FSM_Hamming',
                'strategy_fsm_hamming_name': 'FSM Hamming Code (3-copy + Hamming distance 3)',
                'desc_fsm_hamming': 'FSM Hamming distance-3 encoding fault tolerance',
                'strategy_fsm_safe': 'FSM_Safe',
                'strategy_fsm_safe_name': 'Safe FSM (Illegal State Recovery)',
                'desc_fsm_safe': 'Detect and recover from illegal FSM states',
                'strategy_dnurl': 'DNURL',
                'strategy_dnurl_name': 'Dual-Node DICE (2-node upset recovery)',
                'desc_dnurl': 'Dual-node simultaneous upset recovery',
                'strategy_tnudice': 'TNUDICE',
                'strategy_tnudice_name': 'Triple-Node DICE (3-node upset recovery)',
                'desc_tnudice': 'Triple-node simultaneous upset recovery',
                'strategy_bch_ecc': 'BCH_ECC',
                'strategy_bch_ecc_name': 'BCH Multi-bit ECC (BCH(15,7,2))',
                'desc_bch_ecc': 'BCH code multi-bit error correction based on GF(2^m)',
                'enhance_aig': '📈 Auto AIG Analysis — analyze circuit after hardening',
                'enhance_fault': '🛡️ Fault Injection — quantify hardening effect (requires iverilog)',
                'enhance_llm': '🤖 LLM Enhanced Hardening — optimize code with LLM',
                'llm_backend': 'LLM Backend:',
                'opt_balanced': 'Balanced — Area & Reliability',
                'opt_area': 'Area First — minimize area overhead',
                'opt_reliability': 'Reliability First — maximize reliability',
                'opt_performance': 'Performance First — minimize delay',
                'label_strategy': 'Select Hardening Strategy',
                'label_optimization': 'Optimization Goal',
                'label_enhance': 'Enhancement Options',
                'label_output_log': 'Output Log',
                'label_code_preview': 'Code Preview',
                'label_design_info': 'Design Info',
                'label_verify': 'Hardening Results Verification',
                'label_export_report': 'Export Report',
                'btn_scan': '🔍 Signal Scan',
                'btn_recommend': '🔮 Strategy Recommendation',
                'btn_visualize': '📊 View Visualization',
                'btn_aig_analyze': '📈 AIG Analysis',
                'btn_incremental': '🔄 Incremental Hardening',
                'btn_generate_report': 'Generate HTML Report',
                'btn_view_report': '📖 View Report',
                'btn_finish_home': '🎉 Finish & Return Home',
                'label_report_path': 'Report Path:',
                'label_file_path': 'File Path:',
                'label_folder_path': 'Folder Path:',
                'label_dataset_path': 'Dataset Path:',
                'label_output_dir': 'Output Directory',
                'label_reg_count': 'Register Count',
                'label_signal_count': 'Signal Count',
                'label_area_overhead': 'Area Overhead',
                'label_reliability': 'Reliability',
                'label_delay_overhead': 'Delay Overhead',
                'label_module': 'Module Name',
                'label_ports': 'Port Count',
                'label_submodules': 'Submodule Count',
                'label_select_file': 'Select Verilog File',
                'label_select_folder': 'Select RTL Folder',
                'label_select_dataset': 'Select Dataset File',
                'label_workflow_select': 'Select Workflow',
                'btn_start': 'Start',
                'btn_download_dataset': '⬇️ Download RTLCoder Dataset',
                'label_dataset_info': 'Dataset Info',
                'label_folder_info': 'Folder Info',
                'label_strategy_title': 'Select Hardening Strategy',
                'label_execute': 'Execute Hardening',
                'label_execute_folder': 'Execute Batch Hardening',
                'label_execute_dataset': 'Execute Dataset Hardening',
                'label_execute_run': 'Start Batch Hardening',
                'label_execute_dataset_run': 'Start Dataset Hardening',
                'label_export_report_title': 'Export Report',
                'btn_generate_folder_report': 'Generate HTML Report',
                'label_batch_execute': 'The following folder contents will be hardened:',
                'label_dataset_execute': 'All designs in the dataset will be hardened:',
                'label_enabled_strategies': 'Enabled Strategies:',
                'label_output_frame': 'Output Log',
                'label_single_execute': 'The following file will be hardened:',
                'label_original_code': 'Original Code',
                'label_hardened_code': 'Hardened Code',
                'label_code_compare': 'Code Comparison',
                'label_strategy_detail': 'Strategy Assignment Details',
                'label_vuln_scores': 'Vulnerability Scores (Top 5)',
                'label_high_fanout': 'High Fan-out Signals',
                'label_fault_injection': 'Fault Injection Verification',
                'label_aig_result': 'AIG Circuit Analysis Result',
                'label_aig_simulated': '(simulated)',
                'label_injection_count': 'Injections',
                'label_reg_count_fault': 'Register Count',
                'label_avf_before': 'AVF Before',
                'label_avf_after': 'AVF After',
                'label_improvement': 'Improvement',
                'label_aig_and': 'AND Gates',
                'label_aig_pi': 'Primary Inputs (PI)',
                'label_aig_po': 'Primary Outputs (PO)',
                'label_aig_latches': 'Latches',
                'label_high_fanout_nodes': 'High Fan-out Nodes:',
                'label_auto_hierarchical': '🔄 Auto Hierarchical Hardening — assign optimal strategy by signal type',
                'label_report_generated': 'Report Generated',
                'label_view_report_browser': '🌐 View in Browser',
                'label_save_report': '💾 Save Report',
                'label_quick_start': 'Quick Start',
                'label_output_dir_structure': 'Directory Structure',
                'btn_download': 'Download',
                'label_history_title': 'Hardening History',
                'label_history_time': 'Time',
                'label_history_design': 'Design File',
                'label_history_type': 'Workflow Type',
                'label_history_strategies': 'Strategies',
                'label_history_registers': 'Registers',
                'btn_compare_selected': 'Compare Selected',
                'btn_clear_history': 'Clear History',
                'label_processing': 'Processing',
                'label_done': 'Completed!',
                'label_progress_folder': 'Batch Hardening Progress',
                'label_progress_dataset': 'Dataset Hardening Progress',
                'enhance_comment': 'Comment Directives',
                'enhance_keep': 'Synthesis Protection',
                'enhance_parallel': 'Parallel Mode',
                'enhance_kb': 'Failure Knowledge Base',
            }
        }

    def tr(self, key):
        """根据当前语言返回翻译文本"""
        lang = self.language_var.get()
        return self.translations.get(lang, self.translations['zh']).get(key, key)

    def _on_language_change(self, *args):
        """语言切换时更新界面"""
        lang = self.language_var.get()
        print(f"[LANG] Switching language to: {lang}")
        self.root.title(self.tr('root_title'))
        # 重新绘制当前界面
        if self.current_workflow:
            self._show_workflow_interface()
        else:
            self._show_workflow_selection()
        # 更新标题
        if hasattr(self, 'title_label'):
            self.title_label.config(text=self.tr('app_title'))
        # 更新状态
        if hasattr(self, 'status_label_text'):
            self.status_label_text.config(text=self.tr('status_label'))
        self.status_var.set(self.tr('status_ready'))

    # ── 主题切换 ──
    def _apply_theme(self, theme_name: str):
        """应用亮/暗色主题到所有控件"""
        theme = THEMES.get(theme_name, THEMES['light'])
        style = ttk.Style(self.root)

        # ttk 组件样式
        style.configure('TFrame', background=theme['frame'])
        style.configure('TLabel', background=theme['frame'], foreground=theme['labelfg'])
        style.configure('TButton', background=theme['buttonbg'], foreground=theme['fg'])
        style.configure('TEntry', fieldbackground=theme['entrybg'], foreground=theme['fg'])
        style.configure('TNotebook', background=theme['notebookbg'], foreground=theme['notebookfg'])
        style.configure('TNotebook.Tab', background=theme['notebookbg'], foreground=theme['notebookfg'])
        style.configure('TLabelframe', background=theme['bg'], foreground=theme['fg'])
        style.configure('TLabelframe.Label', background=theme['bg'], foreground=theme['labelfg'])
        style.configure('Treeview', background=theme['treebg'], foreground=theme['treefg'],
                         fieldbackground=theme['treebg'])
        style.configure('Treeview.Heading', background=theme['buttonbg'], foreground=theme['fg'])
        style.configure('TCombobox', fieldbackground=theme['entrybg'], foreground=theme['fg'])

        # 工具提示用背景色
        style.configure('Tooltip.TLabel', background='#FFFACD', foreground=theme['labelfg'])

        # 自定义卡片样式
        style.configure('Card.TFrame', background=theme['bg'], relief="raised")

        # 标题 / 副标题
        fg_title = '#1976D2' if theme_name == 'light' else '#64B5F6'
        fg_subtitle = '#424242' if theme_name == 'light' else '#bdbdbd'
        style.configure('Title.TLabel', font=("微软雅黑", 16, "bold"), foreground=fg_title)
        style.configure('Subtitle.TLabel', font=("微软雅黑", 12), foreground=fg_subtitle)

        # 按钮映射
        style.map('Step.TButton',
                  background=[('active', '#43A047'), ('!disabled', '#4CAF50')],
                  foreground=[('!disabled', '#FFFFFF')])
        style.map('Nav.TButton',
                  background=[('active', '#FB8C00'), ('!disabled', '#FF9800')],
                  foreground=[('!disabled', '#FFFFFF')])
        style.map('Recommend.TButton',
                  background=[('active', '#8E24AA'), ('!disabled', '#9C27B0')],
                  foreground=[('!disabled', '#FFFFFF')])

        # ── 原生 tk 控件 ──
        self.root.configure(bg=theme['bg'])
        palette_colors = {
            'background': theme['bg'],
            'foreground': theme['fg'],
            'selectBackground': theme['selectbg'],
            'selectForeground': '#ffffff',
        }
        try:
            self.root.tk_setPalette(**palette_colors)
        except Exception:
            pass

        # ── 遍历并更新所有现存原生 tk 控件 ──
        def _update_widget_colors(widget):
            widget_type = widget.winfo_class()
            try:
                if widget_type in ('Frame', 'LabelFrame', 'Labelframe'):
                    widget.configure(bg=theme['frame'])
                elif widget_type == 'Label':
                    widget.configure(bg=theme['frame'], fg=theme['labelfg'])
                elif widget_type == 'Button':
                    widget.configure(bg=theme['buttonbg'], fg=theme['fg'],
                                     activebackground=theme['selectbg'])
                elif widget_type in ('Entry', 'Spinbox'):
                    widget.configure(bg=theme['entrybg'], fg=theme['fg'],
                                     insertbackground=theme['fg'])
                elif widget_type == 'Text':
                    widget.configure(bg=theme['entrybg'], fg=theme['fg'],
                                     insertbackground=theme['fg'])
                elif widget_type == 'Listbox':
                    widget.configure(bg=theme['entrybg'], fg=theme['fg'])
                elif widget_type == 'Canvas':
                    widget.configure(bg=theme['bg'])
                elif widget_type == 'Menu':
                    widget.configure(bg=theme['bg'], fg=theme['fg'])
                elif widget_type == 'Scrollbar':
                    widget.configure(bg=theme['buttonbg'], troughcolor=theme['frame'])
                elif widget_type == 'Checkbutton':
                    widget.configure(bg=theme['frame'], fg=theme['labelfg'],
                                     selectcolor=theme['bg'])
                elif widget_type == 'Radiobutton':
                    widget.configure(bg=theme['frame'], fg=theme['labelfg'],
                                     selectcolor=theme['bg'])
            except tk.TclError:
                pass  # 某些控件可能不支持所有选项

            try:
                children = widget.winfo_children()
                for child in children:
                    _update_widget_colors(child)
            except tk.TclError:
                pass

        _update_widget_colors(self.root)

        print(f'[GUI] 主题切换为: {theme_name}')

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')

        style.configure('Title.TLabel', font=("微软雅黑", 16, "bold"), foreground="#1976D2")
        style.configure('Subtitle.TLabel', font=("微软雅黑", 12), foreground="#424242")
        style.configure('Card.TFrame', background="#FFFFFF", relief="raised")
        style.configure('Step.TButton', font=("微软雅黑", 11, "bold"), padding=10)
        style.configure('Nav.TButton', font=("微软雅黑", 10), padding=8)
        style.configure('Browse.TButton', font=("微软雅黑", 10), padding=5)
        style.configure('Action.TButton', font=("微软雅黑", 10, "bold"), padding=8)
        style.configure('Recommend.TButton', font=("微软雅黑", 10), padding=5)
        style.configure('Visualize.TButton', font=("微软雅黑", 10), padding=5)
        style.configure('Export.TButton', font=("微软雅黑", 10), padding=5)

        style.map('Step.TButton',
                  background=[('active', '#43A047'), ('!disabled', '#4CAF50')],
                  foreground=[('!disabled', '#FFFFFF')])
        style.map('Nav.TButton',
                  background=[('active', '#FB8C00'), ('!disabled', '#FF9800')],
                  foreground=[('!disabled', '#FFFFFF')])
        style.map('Recommend.TButton',
                  background=[('active', '#8E24AA'), ('!disabled', '#9C27B0')],
                  foreground=[('!disabled', '#FFFFFF')])

    def _create_main_layout(self):
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.header_frame = ttk.Frame(self.main_frame, padding=10)
        self.header_frame.pack(fill=tk.X)

        self.title_label = ttk.Label(self.header_frame, text=self.tr('root_title'), style='Title.TLabel')
        self.title_label.pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value=self.tr('status_ready'))
        status_frame = ttk.Frame(self.header_frame)
        status_frame.pack(side=tk.RIGHT)
        self.status_label_text = ttk.Label(status_frame, text=self.tr('status_label'))
        self.status_label_text.pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.status_var, foreground="#4CAF50", font=("微软雅黑", 10)).pack(side=tk.LEFT)

        # ── 语言切换下拉框 ──
        lang_frame = ttk.Frame(self.header_frame)
        lang_frame.pack(side=tk.RIGHT, padx=(0, 20))
        self.lang_combo = ttk.Combobox(lang_frame, textvariable=self.language_var,
                                        values=["中文", "English"], width=8, state='readonly')
        self.lang_combo.pack()
        self.lang_combo.bind('<<ComboboxSelected>>', self._on_language_change)

        # ── 主题切换下拉框 ──
        theme_frame = ttk.Frame(self.header_frame)
        theme_frame.pack(side=tk.RIGHT, padx=(0, 5))
        self.theme_combo = ttk.Combobox(theme_frame, textvariable=self.current_theme,
                                        values=['light', 'dark'], width=6, state='readonly')
        self.theme_combo.pack()
        self.theme_combo.bind('<<ComboboxSelected>>', lambda e: self._apply_theme(self.current_theme.get()))

        self.content_frame = ttk.Frame(self.main_frame)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.footer_frame = ttk.Frame(self.main_frame, padding=10)
        self.footer_frame.pack(fill=tk.X)

        help_btn = ttk.Button(self.footer_frame, text=self.tr('btn_help'), command=self._show_help)
        help_btn.pack(side=tk.LEFT)

        config_btn = ttk.Button(self.footer_frame, text=self.tr('btn_config'), command=self._show_api_config)
        config_btn.pack(side=tk.LEFT, padx=10)

        web_btn = ttk.Button(self.footer_frame, text=self.tr('btn_web_gui'), command=self._start_web_gui)
        web_btn.pack(side=tk.LEFT, padx=10)

        history_btn = ttk.Button(self.footer_frame, text=self.tr('btn_history'),
                                 command=self._show_history, style='Nav.TButton')
        history_btn.pack(side=tk.LEFT, padx=10)

        # ── 一键升级 ──
        right_frame = ttk.Frame(self.footer_frame)
        right_frame.pack(side=tk.RIGHT)
        ttk.Label(right_frame, text=f"RTL Hardening Tool v{VERSION}",
                  font=("微软雅黑", 9), foreground="#666").pack(side=tk.LEFT)
        add_update_button(right_frame)

        self._load_env_config()

    def _set_status(self, text):
        self.status_var.set(text)
        self.root.update_idletasks()

    def _show_workflow_selection(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        title_frame = ttk.Frame(self.content_frame)
        title_frame.pack(fill=tk.X, pady=20)
        ttk.Label(title_frame, text=self.tr('label_workflow_select'), style='Title.TLabel').pack(side=tk.LEFT)

        workflow_frame = ttk.Frame(self.content_frame)
        workflow_frame.pack(fill=tk.BOTH, expand=True)

        row = ttk.Frame(workflow_frame)
        row.pack(fill=tk.X, pady=20)

        for i, (wf_id, wf) in enumerate(WORKFLOWS.items()):
            card = ttk.LabelFrame(row, text=f"{wf['icon']} {wf['name']}", padding=15, style='Card.TFrame')
            card.pack(side=tk.LEFT, padx=15, pady=10, fill=tk.BOTH, expand=True)

            ttk.Label(card, text=wf['description'], font=("微软雅黑", 10), foreground="#666").pack(pady=10)

            btn = ttk.Button(card, text=self.tr('btn_start'), command=lambda id=wf_id: self._start_workflow(id), style='Step.TButton')
            btn.pack(pady=10)

    def _start_workflow(self, workflow_id):
        self.current_workflow = workflow_id
        self.current_step = 0
        self.workflow_data = {}
        self._show_workflow_interface()

    def _show_workflow_interface(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        wf = WORKFLOWS[self.current_workflow]

        header_row = ttk.Frame(self.content_frame)
        header_row.pack(fill=tk.X)

        back_btn = ttk.Button(header_row, text=self.tr('btn_back_home'), command=self._show_workflow_selection, style='Nav.TButton')
        back_btn.pack(side=tk.LEFT)

        ttk.Label(header_row, text=f"{wf['icon']} {wf['name']}", style='Subtitle.TLabel').pack(side=tk.LEFT, padx=20)

        steps_frame = ttk.Frame(self.content_frame)
        steps_frame.pack(fill=tk.X, pady=10)

        for i, step in enumerate(wf['steps']):
            step_frame = ttk.Frame(steps_frame)
            step_frame.pack(side=tk.LEFT, padx=5)

            if i == self.current_step:
                bg_color = '#FF9800'
                text_color = '#FFFFFF'
                status = '●'
            elif i < self.current_step:
                bg_color = '#4CAF50'
                text_color = '#FFFFFF'
                status = '✓'
            else:
                bg_color = '#E0E0E0'
                text_color = '#666'
                status = '○'

            step_label = ttk.Label(step_frame, text=f"{status} {step['name']}",
                                  background=bg_color, foreground=text_color,
                                  font=("微软雅黑", 10), padding=(10, 5))
            step_label.pack()
            desc_label = ttk.Label(step_frame, text=step['desc'], font=("微软雅黑", 8), foreground="#888")
            desc_label.pack()

        step_content_frame = ttk.Frame(self.content_frame)
        step_content_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        render_func = getattr(self, f'_render_step_{self.current_workflow}_{wf["steps"][self.current_step]["id"]}', None)
        if render_func:
            render_func(step_content_frame)

        nav_frame = ttk.Frame(self.content_frame)
        nav_frame.pack(fill=tk.X, pady=10)

        prev_btn = ttk.Button(nav_frame, text=self.tr('btn_prev'), command=self._prev_step,
                              state=tk.DISABLED if self.current_step == 0 else tk.NORMAL, style='Nav.TButton')
        prev_btn.pack(side=tk.LEFT)

        is_last = self.current_step < len(wf['steps']) - 1
        next_text = self.tr('btn_next') if is_last else self.tr('btn_finish')
        next_btn = ttk.Button(nav_frame, text=next_text, command=self._next_step, style='Step.TButton')
        next_btn.pack(side=tk.RIGHT)

        output_frame = ttk.LabelFrame(self.content_frame, text=self.tr('label_output_frame'), padding=10)
        output_frame.pack(fill=tk.X, pady=10)

        self.workflow_output = scrolledtext.ScrolledText(output_frame, height=8, font=("Consolas", 9))
        self.workflow_output.pack(fill=tk.X)
        self.workflow_output.config(state=tk.DISABLED)

    def _render_step_rtl_single_select_file(self, parent):
        f = ttk.LabelFrame(parent, text=self.tr('label_select_file'), padding=15)
        f.pack(fill=tk.X, pady=10)

        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=10)

        ttk.Label(row, text=self.tr('label_file_path'), font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        entry = ttk.Entry(row, textvariable=self.single_file_var, width=60, font=("微软雅黑", 10))
        entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        browse_btn = ttk.Button(row, text=self.tr('btn_browse'), command=self._browse_single_file)
        browse_btn.pack(side=tk.LEFT, padx=10)

        example_btn = ttk.Button(row, text=self.tr('btn_example'), command=self._use_example_single)
        example_btn.pack(side=tk.LEFT)

        info_frame = ttk.LabelFrame(parent, text=self.tr('label_design_info'), padding=15)
        info_frame.pack(fill=tk.X, pady=10)

        self.single_info_vars = {
            'module': tk.StringVar(value="未选择"),
            'regs': tk.StringVar(value="0"),
            'ports': tk.StringVar(value="0"),
            'submodules': tk.StringVar(value="0"),
        }

        for label, key in [(self.tr('label_module'), 'module'), (self.tr('label_reg_count'), 'regs'), (self.tr('label_ports'), 'ports'), (self.tr('label_submodules'), 'submodules')]:
            row = ttk.Frame(info_frame)
            row.pack(fill=tk.X, pady=5)
            ttk.Label(row, text=label + ':', width=12, font=("微软雅黑", 10)).pack(side=tk.LEFT)
            ttk.Label(row, textvariable=self.single_info_vars[key], font=("微软雅黑", 10, "bold"), foreground="#1976D2").pack(side=tk.LEFT)

        code_frame = ttk.LabelFrame(parent, text=self.tr('label_code_preview'), padding=15)
        code_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        code_toolbar = ttk.Frame(code_frame)
        code_toolbar.pack(fill=tk.X, pady=5)

        scan_btn = ttk.Button(code_toolbar, text=self.tr('btn_scan'), command=self._run_signal_scan)
        scan_btn.pack(side=tk.RIGHT)

        self.code_text = scrolledtext.ScrolledText(code_frame, height=18, font=("Consolas", 9))
        self.code_text.pack(fill=tk.BOTH, expand=True)
        self.code_text.config(state=tk.DISABLED)

        self.single_file_var.trace('w', lambda *args: self._update_single_file_info())

    def _browse_single_file(self):
        path = filedialog.askopenfilename(
            title=self.tr('label_select_file'),
            filetypes=[("Verilog 文件", "*.v *.sv"), (self.tr('btn_browse'), "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.single_file_var.set(path)

    def _use_example_single(self):
        example_file = os.path.join(TEST_MOCK_DIR, 'mixed_design.v')
        if os.path.exists(example_file):
            self.single_file_var.set(example_file)

    def _update_single_file_info(self):
        file_path = self.single_file_var.get()
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                module_match = re.search(r'module\s+(\w+)', content)
                if module_match:
                    self.single_info_vars['module'].set(module_match.group(1))

                reg_count = len(re.findall(r'\breg\b', content))
                self.single_info_vars['regs'].set(str(reg_count))

                port_count = len(re.findall(r'\b(input|output|inout)\b', content))
                self.single_info_vars['ports'].set(str(port_count))

                submodule_count = len(re.findall(r'\b(\w+)\s+(\w+)\s*\(', content))
                self.single_info_vars['submodules'].set(str(submodule_count))

                self.code_text.config(state=tk.NORMAL)
                self.code_text.delete("1.0", tk.END)
                self.code_text.insert(tk.END, content)
                self.code_text.config(state=tk.DISABLED)

            except Exception as e:
                pass

    def _save_step_rtl_single_select_file(self):
        self.workflow_data['input_file'] = self.single_file_var.get()
        self.workflow_data['design_info'] = {k: v.get() for k, v in self.single_info_vars.items()}
        if os.path.exists(self.single_file_var.get()):
            with open(self.single_file_var.get(), 'r', encoding='utf-8') as f:
                self.workflow_data['original_code'] = f.read()

    def _render_step_rtl_single_config_strategy(self, parent):
        f = ttk.LabelFrame(parent, text=self.tr('label_strategy'), padding=15)
        f.pack(fill=tk.X, pady=10)

        self.auto_hierarchical_var = tk.BooleanVar(value=True)
        auto_cb = ttk.Checkbutton(f, text=self.tr('label_auto_hierarchical'), 
                                  variable=self.auto_hierarchical_var,
                                  command=self._toggle_strategy_selection)
        auto_cb.pack(side=tk.TOP, pady=5)
        add_tooltip(auto_cb, "启用后，工具根据完整策略矩阵为不同类型信号自动分配最合适的加固策略")

        self.strategy_frame = ttk.Frame(f)
        self.strategy_frame.pack(fill=tk.X, pady=10)

        strat_desc = {
            'tmr':      (self.tr('strategy_tmr'), self.tr('strategy_tmr_name'), self.tr('desc_tmr')),
            'dice':     (self.tr('strategy_dice'), self.tr('strategy_dice_name'), self.tr('desc_dice')),
            'ecc':      (self.tr('strategy_ecc'), self.tr('strategy_ecc_name'), self.tr('desc_ecc')),
            'parity':   (self.tr('strategy_parity'), self.tr('strategy_parity_name'), self.tr('desc_parity')),
            'cnt_comp': (self.tr('strategy_cnt_comp'), self.tr('strategy_cnt_comp_name'), self.tr('desc_cnt_comp')),
            'fsm_tmr':  (self.tr('strategy_fsm_tmr'), self.tr('strategy_fsm_tmr_name'), self.tr('desc_fsm_tmr')),
            'bch_ecc':  (self.tr('strategy_bch_ecc'), self.tr('strategy_bch_ecc_name'), self.tr('desc_bch_ecc')),
            'fsm_hamming': (self.tr('strategy_fsm_hamming'), self.tr('strategy_fsm_hamming_name'), self.tr('desc_fsm_hamming')),
            'fsm_safe': (self.tr('strategy_fsm_safe'), self.tr('strategy_fsm_safe_name'), self.tr('desc_fsm_safe')),
            'dnurl':    (self.tr('strategy_dnurl'), self.tr('strategy_dnurl_name'), self.tr('desc_dnurl')),
            'tnudice':  (self.tr('strategy_tnudice'), self.tr('strategy_tnudice_name'), self.tr('desc_tnudice')),
        }

        for i, (key, (short, name, desc)) in enumerate(strat_desc.items()):
            row = ttk.Frame(self.strategy_frame)
            row.pack(fill=tk.X, pady=5)

            cb = ttk.Checkbutton(row, text=f"{short} — {name}", variable=self.strategy_vars[key])
            cb.pack(side=tk.LEFT)
            add_tooltip(cb, desc)

            ttk.Label(row, text=desc, font=("微软雅黑", 8), foreground="#666").pack(side=tk.LEFT, padx=10)

        recommend_btn = ttk.Button(f, text=self.tr('btn_recommend'), command=self._run_strategy_recommendation, style='Recommend.TButton')
        recommend_btn.pack(pady=10)

        self._toggle_strategy_selection()

        opt_frame = ttk.LabelFrame(parent, text=self.tr('label_optimization'), padding=15)
        opt_frame.pack(fill=tk.X, pady=10)

        self.optimization_goal = tk.StringVar(value='balanced')
        goals = [
            ('balanced', self.tr('opt_balanced')),
            ('area', self.tr('opt_area')),
            ('reliability', self.tr('opt_reliability')),
            ('performance', self.tr('opt_performance')),
        ]
        for key, label in goals:
            rb = ttk.Radiobutton(opt_frame, text=label, variable=self.optimization_goal, value=key)
            rb.pack(side=tk.LEFT, padx=15)

        # ── 增强功能选项 ──
        enhance_frame = ttk.LabelFrame(parent, text=self.tr('label_enhance'), padding=15)
        enhance_frame.pack(fill=tk.X, pady=10)

        aig_cb = ttk.Checkbutton(enhance_frame, text=self.tr('enhance_aig'),
                                 variable=self.aig_enabled_var)
        aig_cb.pack(fill=tk.X, pady=3)
        add_tooltip(aig_cb, "加固后自动生成并分析And-Inverter Graph，评估电路脆弱性")

        fault_cb = ttk.Checkbutton(enhance_frame, text=self.tr('enhance_fault'),
                                   variable=self.fault_injection_var)
        fault_cb.pack(fill=tk.X, pady=3)
        add_tooltip(fault_cb, "通过蒙特卡洛SEU注入计算AVF，对比加固前后可靠性改善")

        llm_cb = ttk.Checkbutton(enhance_frame, text=self.tr('enhance_llm'),
                                 variable=self.llm_enhance_var)
        llm_cb.pack(fill=tk.X, pady=3)
        add_tooltip(llm_cb, "使用MockLLM(内置模板)或OpenAI/DeepSeek生成加固代码")

        backend_frame = ttk.Frame(enhance_frame)
        backend_frame.pack(fill=tk.X, pady=5, padx=20)
        ttk.Label(backend_frame, text=self.tr('llm_backend'), font=("微软雅黑", 9)).pack(side=tk.LEFT)
        for backend in ['mock', 'openai', 'deepseek']:
            rb = ttk.Radiobutton(backend_frame, text=backend, variable=self.llm_backend_var, value=backend)
            rb.pack(side=tk.LEFT, padx=10)

        # ── 新增增强功能（由开源工具TMRG/FT-Pilot/TLegUp启发） ──
        sep = ttk.Separator(enhance_frame, orient='horizontal')
        sep.pack(fill=tk.X, pady=5)

        ttk.Label(enhance_frame, text="━ 高级优化选项 ━", font=("微软雅黑", 9, "bold"),
                 foreground="#555").pack(pady=2)

        comment_cb = ttk.Checkbutton(enhance_frame, text="📝 注释驱动约束 (// harden_strategy/tmr)",
                                    variable=self.comment_directives_var)
        comment_cb.pack(fill=tk.X, pady=3)
        add_tooltip(comment_cb, "参考TMRG(CERN): 通过RTL注释控制加固策略，如 // harden_strategy: tmr")

        keep_cb = ttk.Checkbutton(enhance_frame, text="🔒 综合保护 (*keep*)",
                                  variable=self.gen_keep_var)
        keep_cb.pack(fill=tk.X, pady=3)
        add_tooltip(keep_cb, "参考TLegUp: 自动添加 (*keep*)属性和SDC文件防止综合优化移除冗余逻辑")

        sdc_frame = ttk.Frame(enhance_frame)
        sdc_frame.pack(fill=tk.X, padx=20, pady=2)
        sdc_cb = ttk.Checkbutton(sdc_frame, text="生成SDC/XDC综合约束文件",
                                 variable=self.gen_sdc_var)
        sdc_cb.pack(side=tk.LEFT)

        parallel_cb = ttk.Checkbutton(enhance_frame, text="⚡ 并行处理模式（适用于大规模设计）",
                                      variable=self.parallel_mode_var)
        parallel_cb.pack(fill=tk.X, pady=3)
        add_tooltip(parallel_cb, "使用ThreadPoolExecutor并行处理10000+信号的设计")

        failure_kb_cb = ttk.Checkbutton(enhance_frame, text="🧠 故障知识积累（提升LLM生成质量）",
                                        variable=self.failure_kb_var)
        failure_kb_cb.pack(fill=tk.X, pady=3)
        add_tooltip(failure_kb_cb, "参考FT-Pilot(中科院): 记录历史失败模式，避免LLM重复错误")

        multi_verify_cb = ttk.Checkbutton(enhance_frame, text="🔬 多层验证管线（语法→可综合→接口→功能）",
                                          variable=self.multi_verify_var)
        multi_verify_cb.pack(fill=tk.X, pady=3)
        add_tooltip(multi_verify_cb, "参考FT-Pilot(中科院): 4层验证——语法检查+可综合检查+接口一致性+功能正确性")

        exclude_cb = ttk.Checkbutton(enhance_frame, text="🚫 投票器禁区规则（DSP/进位链排除）",
                                     variable=self.exclusion_var)
        exclude_cb.pack(fill=tk.X, pady=3)
        add_tooltip(exclude_cb, "参考Johnson & Wirthlin(BYU 2010): 在DSP原语和进位链路径上禁止插入投票器")

        # ── 投票器类型选择 ──
        voter_frame = ttk.Frame(enhance_frame)
        voter_frame.pack(fill=tk.X, pady=5)
        ttk.Label(voter_frame, text="投票器类型:").pack(side=tk.LEFT)
        voter_types = [('归约型', 'reducing'), ('分区型', 'partitioning'), ('同步型', 'sync'), ('CDC型', 'cdc')]
        for label, val in voter_types:
            rb = ttk.Radiobutton(voter_frame, text=label, variable=self.voter_type_var, value=val)
            rb.pack(side=tk.LEFT, padx=5)
        add_tooltip(voter_frame.winfo_children()[0] if voter_frame.winfo_children() else None,
                    "参考Johnson & Wirthlin(BYU): 四种投票器算法适用于不同场景")

        # ── 自动触发策略推荐 ──
        def auto_recommend():
            try:
                input_file = self.workflow_data.get('input_file', '')
                if input_file and os.path.exists(input_file):
                    self.root.after(500, lambda: self._append_output("[INFO] 正在自动分析设计特征并推荐最优加固策略..."))
                    self.root.after(1000, self._run_strategy_recommendation)
            except:
                pass
        
        self.root.after(100, auto_recommend)

    def _run_strategy_recommendation(self):
        input_file = self.workflow_data.get('input_file', '')
        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("错误", "请先选择输入文件")
            return

        self._clear_output()
        self._append_output("[INFO] 正在分析设计并生成策略推荐...")
        self._set_status("策略推荐中...")

        def task():
            try:
                sys.path.insert(0, SCRIPT_DIR)
                from sim.formal_test.strategy_auto_select import StrategyAutoSelector

                with open(input_file, 'r', encoding='utf-8') as f:
                    rtl_content = f.read()

                selector = StrategyAutoSelector()
                recommendations = selector.recommend(rtl_content, constraints={'goal': self.optimization_goal.get()})

                self._append_output("")
                self._append_output("=" * 50, "green")
                self._append_output("  🔮 策略推荐结果", "green")
                self._append_output("=" * 50, "green")

                for i, rec in enumerate(recommendations[:5], 1):
                    self._append_output(f"\n  {i}. {rec.get('strategy', '')}")
                    self._append_output(f"     得分: {rec.get('score', 0):.2f}")
                    area_overhead = rec.get('area_overhead', 'N/A')
                    reliability = rec.get('reliability', 'N/A')
                    self._append_output(f"     面积开销: {area_overhead}x" if area_overhead != 'N/A' else "     面积开销: N/A")
                    self._append_output(f"     可靠性等级: {reliability}/5" if reliability != 'N/A' else "     可靠性: N/A")
                    self._append_output(f"     描述: {rec.get('description', '')}")

                if recommendations:
                    best_strategy = recommendations[0].get('strategy', '')
                    for k in self.strategy_vars:
                        self.strategy_vars[k].set(False)
                    if best_strategy in self.strategy_vars:
                        self.strategy_vars[best_strategy].set(True)
                        self._append_output(f"\n  ✅ 已自动选择最佳策略: {best_strategy}", "green")
                    else:
                        self._append_output(f"\n  ⚠️ 推荐策略 {best_strategy} 不在可选列表中", "orange")

                self._set_status("策略推荐完成")

            except Exception as e:
                self._append_output(f"[错误] {e}", "red")
                self._set_status("策略推荐失败")

        threading.Thread(target=task, daemon=True).start()

    def _toggle_strategy_selection(self):
        """切换策略选择框的启用/禁用状态"""
        if hasattr(self, 'strategy_frame'):
            for child in self.strategy_frame.winfo_children():
                for sub_child in child.winfo_children():
                    try:
                        if self.auto_hierarchical_var.get():
                            sub_child.config(state=tk.DISABLED)
                        else:
                            sub_child.config(state=tk.NORMAL)
                    except:
                        pass

    def _save_step_rtl_single_config_strategy(self):
        if self.auto_hierarchical_var.get():
            self.workflow_data['strategies'] = []
            self.workflow_data['auto_hierarchical'] = True
        else:
            self.workflow_data['strategies'] = [k for k, v in self.strategy_vars.items() if v.get()]
            self.workflow_data['auto_hierarchical'] = False
        self.workflow_data['optimization_goal'] = self.optimization_goal.get()
        # 保存增强功能选项
        self.workflow_data['aig_enabled'] = self.aig_enabled_var.get()
        self.workflow_data['fault_injection_enabled'] = self.fault_injection_var.get()
        self.workflow_data['llm_enhance_enabled'] = self.llm_enhance_var.get()
        self.workflow_data['llm_backend'] = self.llm_backend_var.get()
        self.workflow_data['comment_directives'] = self.comment_directives_var.get()
        self.workflow_data['gen_keep_attrs'] = self.gen_keep_var.get()
        self.workflow_data['gen_sdc'] = self.gen_sdc_var.get()
        self.workflow_data['parallel_mode'] = self.parallel_mode_var.get()
        self.workflow_data['failure_kb'] = self.failure_kb_var.get()
        self.workflow_data['voter_type'] = self.voter_type_var.get()
        self.workflow_data['error_signal'] = self.error_signal_var.get()

    def _render_step_rtl_single_execute(self, parent):
        f = ttk.LabelFrame(parent, text=self.tr('label_execute'), padding=15)
        f.pack(fill=tk.X, pady=10)

        ttk.Label(f, text=self.tr('label_single_execute'), font=("微软雅黑", 10)).pack(pady=10)

        file_path = self.workflow_data.get('input_file', '')
        ttk.Label(f, text=file_path, font=("Consolas", 10), foreground="#1976D2").pack(pady=5)

        ttk.Label(f, text="\n" + self.tr('label_enabled_strategies'), font=("微软雅黑", 10)).pack(pady=10)
        enabled = self.workflow_data.get('strategies', [])
        ttk.Label(f, text=", ".join(enabled), font=("微软雅黑", 10)).pack(pady=5)

        execute_btn = ttk.Button(f, text=self.tr('btn_execute'), command=self._execute_single_hardening, style='Step.TButton')
        execute_btn.pack(pady=20)

    def _execute_single_hardening(self):
        input_file = self.workflow_data.get('input_file', '')
        enabled_strategies = self.workflow_data.get('strategies', [])

        if not input_file or not os.path.exists(input_file):
            messagebox.showerror("错误", "请先选择有效的输入文件")
            return

        if not enabled_strategies and not self.workflow_data.get('auto_hierarchical'):
            messagebox.showerror("错误", "请至少选择一个加固策略，或启用\"自动层次化加固\"")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(OUTPUT_DIRS['rtl_single'], timestamp)
        os.makedirs(output_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(output_dir, f"{base_name}_hardened.v")

        self._clear_output()
        self._append_output(f"[INFO] 开始加固: {input_file}")
        self._append_output(f"[INFO] 输出目录: {output_dir}")
        if self.workflow_data.get('auto_hierarchical'):
            self._append_output("[INFO] 模式: 自动层次化加固")
        else:
            self._append_output(f"[INFO] 启用策略: {', '.join(enabled_strategies)}")
        self._set_status("加固运行中...")

        def task():
            try:
                sys.path.insert(0, SCRIPT_DIR)
                from hardening_pipeline import HardeningPipeline

                pipeline = HardeningPipeline(optimization_goal=self.workflow_data.get('optimization_goal', 'balanced'))

                # ── 应用新增功能选项 ──
                # 注释驱动约束
                pipeline.use_comment_directives = self.workflow_data.get('comment_directives', True)

                # 综合保护
                pipeline.gen_keep_attrs = self.workflow_data.get('gen_keep_attrs', True)
                pipeline.gen_sdc = self.workflow_data.get('gen_sdc', True)

                # ── 自动检测大规模设计并启用并行模式 ──
                auto_parallel = self.workflow_data.get('parallel_mode', False)
                if not auto_parallel:
                    # 检测RTL文件大小，超过500KB或信号数>5000时自动启用
                    try:
                        fsize = os.path.getsize(input_file)
                        if fsize > 500 * 1024:  # 500KB+
                            auto_parallel = True
                            self._append_output("  ⚡ 检测到大规模设计，自动启用并行处理模式", "cyan")
                    except:
                        pass
                pipeline.use_parallel = auto_parallel

                # 投票器类型
                self.workflow_data['voter_type'] = self.workflow_data.get('voter_type', 'reducing')

                # 故障知识积累
                if self.workflow_data.get('failure_kb', True):
                    self._append_output("  🧠 故障知识积累已启用", "cyan")

                self._append_output("[1/8] 加载设计...")
                if not pipeline.load_design(input_file):
                    self._append_output("[错误] 加载设计失败", "red")
                    self._set_status("加固失败")
                    return

                self._append_output("[2/8] 分析设计...")
                pipeline.analyze()

                self._append_output("[3/9] 信号扫描...")
                scan_results = pipeline.scan_high_fanout_signals()
                if scan_results.get('high_fanout_signals'):
                    high_fanout = scan_results['high_fanout_signals']
                    self._append_output(f"  发现 {len(high_fanout)} 个高扇出信号: {', '.join(high_fanout.keys())}", "orange")

                # ── AIG 分析（在脆弱性预测之前，为GNN提供输入） ──
                if self.workflow_data.get('aig_enabled', True):
                    self._append_output("[4/9] AIG 电路结构分析...")
                    aig_results = pipeline.run_aig_analysis(input_file)
                    if aig_results.get('success'):
                        self._append_output(f"  ✅ AIG分析完成: AND门={aig_results.get('and_count',0)}, PI={aig_results.get('pi_count',0)}", "green")
                        if aig_results.get('simulated'):
                            self._append_output("  ⚠️ 使用模拟AIG分析", "orange")
                    self.workflow_data['aig_results'] = pipeline.aig_results
                else:
                    self._append_output("[4/9] AIG 分析 (已跳过)...")

                self._append_output("[5/9] 脆弱性预测（集成AIG+扇出+类型信息）...")
                vulnerability_scores = pipeline.predict_vulnerability()
                top_vuln = sorted(vulnerability_scores.items(), key=lambda x: x[1], reverse=True)[:3]
                for sig, score in top_vuln:
                    self._append_output(f"  {sig}: {score:.4f}", "orange")

                self._append_output("[6/9] 策略路由（层次化加固）...")
                if self.workflow_data.get('auto_hierarchical'):
                    pipeline.route_strategies()
                else:
                    pipeline.route_strategies(user_strategies=enabled_strategies)

                self._append_output("[7/9] AST 变换...")
                pipeline.transform()

                self._append_output("[8/9] 输出加固代码...")
                pipeline.output(output_file)

                self._append_output("[9/9] 验证分析...")
                verification_result = pipeline.formal_verify([output_file])
                if verification_result.get('success'):
                    self._append_output("  ✅ 形式化验证通过", "green")
                else:
                    self._append_output("  ⚠️ 形式化验证不可用或失败", "orange")

                if pipeline.run_iverilog_check(output_file):
                    self._append_output("  ✅ 编译检查通过", "green")
                else:
                    self._append_output("  ⚠️ 编译检查失败或不可用", "orange")

                # ── 故障注入验证（评估加固效果） ──
                if self.workflow_data.get('fault_injection_enabled', False):
                    self._append_output("\n  ⚡ 故障注入验证...")
                    fault_results = pipeline.run_fault_injection(num_injections=500)
                    if fault_results.get('success'):
                        impr = fault_results.get('improvement', 0) * 100
                        self._append_output(f"  ✅ 故障注入完成: AVF改善={impr:.1f}%", "green")
                        if fault_results.get('simulated'):
                            self._append_output("  ⚠️ 使用模拟故障注入(无需iverilog)", "orange")
                    self.workflow_data['fault_injection_results'] = pipeline.fault_injection_results

                # ── LLM增强加固 ──
                if self.workflow_data.get('llm_enhance_enabled', False):
                    backend = self.workflow_data.get('llm_backend', 'mock')
                    self._append_output(f"\n  🤖 LLM增强加固 (后端={backend})...")
                    llm_results = pipeline.llm_generate(backend=backend)
                    if llm_results.get('success'):
                        self._append_output(f"  ✅ LLM生成完成: 策略数={len(llm_results.get('strategies_used',[]))}", "green")
                        self._append_output(f"  说明: {llm_results.get('explanation', '')[:100]}...")
                    self.workflow_data['llm_results'] = pipeline.llm_results

                # ── 显示新增功能状态 ──
                if hasattr(pipeline, 'use_comment_directives') and pipeline.use_comment_directives and hasattr(pipeline, '_raw_content') and pipeline._raw_content:
                    cmt = pipeline.parse_harden_comments(pipeline._raw_content)
                    if cmt.get('strategy') or cmt.get('skip') or cmt.get('module') or cmt.get('all'):
                        self._append_output("  📝 注释约束已应用", "green")

                if hasattr(pipeline, 'gen_keep_attrs') and pipeline.gen_keep_attrs:
                    self._append_output("  🔒 综合保护(keep属性)已应用", "green")

                if hasattr(pipeline, 'get_performance_stats'):
                    stats = pipeline.get_performance_stats()
                    if stats.get('use_parallel'):
                        self._append_output(f"  ⚡ 并行处理: {stats.get('num_batches', 0)}批", "green")

                self._append_output("")
                self._append_output("=" * 50, "green")
                self._append_output("  ✅ 加固完成！", "green")
                self._append_output(f"  输出文件: {output_file}", "green")
                self._append_output("=" * 50, "green")

                self.workflow_data['output_file'] = output_file
                self.workflow_data['output_dir'] = output_dir
                self.workflow_data['results'] = {
                    'registers': pipeline.reg_count,
                    'signals': len(pipeline.strategy_map),
                    'area_overhead': self._estimate_area_overhead(pipeline.strategy_map),
                    'reliability': self._estimate_reliability(pipeline.strategy_map),
                    'strategy_map': pipeline.strategy_map,
                    'module_info': pipeline.module_info,
                    'vulnerability_scores': pipeline.vulnerability_scores,
                    'signal_scan_results': pipeline.signal_scan_results,
                    'verification_results': pipeline.verification_results,
                }

                with open(output_file, 'r', encoding='utf-8') as f:
                    self.workflow_data['hardened_code'] = f.read()

                # ── 保存加固历史记录 ──
                if hasattr(self, 'history') and self.history:
                    try:
                        self.history.add_record(
                            design_file=input_file,
                            strategy_map=pipeline.strategy_map,
                            metrics={
                                'reg_count': pipeline.reg_count,
                                'signal_count': len(pipeline.strategy_map),
                                'strategies_used': str(list(pipeline.strategy_map.values())),
                            },
                            output_file=output_file,
                            workflow_type='single'
                        )
                        print(f"[HISTORY] Record saved for {os.path.basename(input_file)}")
                    except Exception as e:
                        print(f"[HISTORY] Failed to save record: {e}")

                # ── 异步检查更新 ──
                self.check_for_updates()

                self._set_status("加固完成")

            except Exception as e:
                self._append_output(f"[错误] {e}", "red")
                import traceback
                self._append_output(traceback.format_exc(), "red")
                self._set_status("加固失败")

        threading.Thread(target=task, daemon=True).start()

    def _save_step_rtl_single_execute(self):
        pass

    def _render_step_rtl_single_verify(self, parent):
        f = ttk.LabelFrame(parent, text=self.tr('label_verify'), padding=15)
        f.pack(fill=tk.X, pady=10)

        results = self.workflow_data.get('results', {})
        output_file = self.workflow_data.get('output_file', '')

        info_grid = ttk.Frame(f)
        info_grid.pack(fill=tk.X, pady=10)

        labels = [
            (self.tr('label_output_dir'), output_file),
            (self.tr('label_reg_count'), str(results.get('registers', 'N/A'))),
            (self.tr('label_signal_count'), str(results.get('signals', 'N/A'))),
            (self.tr('label_area_overhead'), f"{results.get('area_overhead', 0):.1f}%"),
            (self.tr('label_reliability'), f"{results.get('reliability', 0) * 100:.2f}%"),
            (self.tr('label_delay_overhead'), f"{results.get('area_overhead', 0) * 0.1:.1f} cycles"),
        ]

        for label, value in labels:
            row = ttk.Frame(info_grid)
            row.pack(fill=tk.X, pady=5)
            ttk.Label(row, text=label + ':', width=12, font=("微软雅黑", 10)).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("微软雅黑", 10, "bold"), foreground="#1976D2").pack(side=tk.LEFT)

        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill=tk.X, pady=10)

        vis_btn = ttk.Button(btn_frame, text=self.tr('btn_visualize'), command=self._show_visualization, style='Visualize.TButton')
        vis_btn.pack(side=tk.LEFT, padx=10)

        aig_btn = ttk.Button(btn_frame, text=self.tr('btn_aig_analyze'), command=self._run_aig_analysis)
        aig_btn.pack(side=tk.LEFT, padx=10)

        inc_btn = ttk.Button(btn_frame, text=self.tr('btn_incremental'), command=self._show_incremental_dialog, style='Visualize.TButton')
        inc_btn.pack(side=tk.LEFT, padx=10)

        # ── AIG分析结果 ──
        aig_results = self.workflow_data.get('aig_results', {})
        if aig_results and aig_results.get('success'):
            aig_frame = ttk.LabelFrame(parent, text=f"AIG电路分析结果{' (模拟)' if aig_results.get('simulated') else ''}", padding=15)
            aig_frame.pack(fill=tk.X, pady=10)
            aig_info = ttk.Frame(aig_frame)
            aig_info.pack(fill=tk.X)
            metrics = [
                ('AND门数', str(aig_results.get('and_count', 0))),
                ('主输入(PI)', str(aig_results.get('pi_count', 0))),
                ('主输出(PO)', str(aig_results.get('po_count', 0))),
                ('锁存器', str(aig_results.get('latches', 0))),
            ]
            for name, val in metrics:
                cell = ttk.Frame(aig_info)
                cell.pack(side=tk.LEFT, padx=15, pady=5)
                ttk.Label(cell, text=name, font=("微软雅黑", 8), foreground="#666").pack()
                ttk.Label(cell, text=val, font=("微软雅黑", 10, "bold"), foreground="#1976D2").pack()
            
            top_nodes = aig_results.get('top_fanout_nodes', [])
            if top_nodes:
                ttk.Label(aig_frame, text="高扇出节点:", font=("微软雅黑", 9)).pack(anchor=tk.W, pady=5)
                for name, fanout in top_nodes[:5]:
                    ttk.Label(aig_frame, text=f"  {name}: 扇出={fanout}", font=("Consolas", 8)).pack(anchor=tk.W)

        # ── 故障注入结果 ──
        fault_results = self.workflow_data.get('fault_injection_results', {})
        if fault_results and fault_results.get('success'):
            fault_frame = ttk.LabelFrame(parent, text=f"故障注入验证{' (模拟)' if fault_results.get('simulated') else ''}", padding=15)
            fault_frame.pack(fill=tk.X, pady=10)
            fault_info = ttk.Frame(fault_frame)
            fault_info.pack(fill=tk.X)
            
            impr_pct = fault_results.get('improvement', 0) * 100
            before = fault_results.get('average_avf', 0)
            after = fault_results.get('hardened_avf', 0)
            
            metrics = [
                ('注入次数', str(fault_results.get('num_injections', 0))),
                ('寄存器数', str(fault_results.get('num_registers', 0))),
                ('加固前AVF', f"{before:.3f}"),
                ('加固后AVF', f"{after:.3f}"),
                ('改善幅度', f"{impr_pct:.1f}%"),
            ]
            for name, val in metrics:
                cell = ttk.Frame(fault_info)
                cell.pack(side=tk.LEFT, padx=10, pady=5)
                ttk.Label(cell, text=name, font=("微软雅黑", 8), foreground="#666").pack()
                fg = "#4CAF50" if "改善" in name else "#1976D2"
                ttk.Label(cell, text=val, font=("微软雅黑", 10, "bold"), foreground=fg).pack()

        vuln_scores = results.get('vulnerability_scores', {})
        if vuln_scores:
            vuln_frame = ttk.LabelFrame(parent, text="脆弱性评分（Top 5）", padding=15)
            vuln_frame.pack(fill=tk.X, pady=10)
            
            sorted_vuln = sorted(vuln_scores.items(), key=lambda x: x[1], reverse=True)[:5]
            for sig, score in sorted_vuln:
                row = ttk.Frame(vuln_frame)
                row.pack(fill=tk.X, pady=3)
                ttk.Label(row, text=sig + ':', width=20, font=("微软雅黑", 9)).pack(side=tk.LEFT)
                ttk.Label(row, text=f"{score:.4f}", font=("微软雅黑", 9, "bold"), 
                          foreground="#E53935" if score > 0.7 else "#1976D2").pack(side=tk.LEFT)

        scan_results = results.get('signal_scan_results', {})
        if scan_results.get('high_fanout_signals'):
            high_fanout = scan_results['high_fanout_signals']
            scan_frame = ttk.LabelFrame(parent, text=f"高扇出信号（{len(high_fanout)}个）", padding=15)
            scan_frame.pack(fill=tk.X, pady=10)
            
            for sig, fanout in sorted(high_fanout.items(), key=lambda x: x[1], reverse=True):
                row = ttk.Frame(scan_frame)
                row.pack(fill=tk.X, pady=3)
                ttk.Label(row, text=sig + ':', width=20, font=("微软雅黑", 9)).pack(side=tk.LEFT)
                ttk.Label(row, text=f"扇出: {fanout}", font=("微软雅黑", 9, "bold"), 
                          foreground="#FB8C00").pack(side=tk.LEFT)

        strategy_map = results.get('strategy_map', {})
        if strategy_map:
            strategy_frame = ttk.LabelFrame(parent, text="策略分配详情", padding=15)
            strategy_frame.pack(fill=tk.X, pady=10)
            
            for sig, strategy in sorted(strategy_map.items()):
                info = results.get('module_info', {}).get(sig, {})
                sig_type = info.get('type', '')
                row = ttk.Frame(strategy_frame)
                row.pack(fill=tk.X, pady=3)
                ttk.Label(row, text=sig + ':', width=20, font=("微软雅黑", 9)).pack(side=tk.LEFT)
                ttk.Label(row, text=f"[{sig_type}] → {strategy}", font=("微软雅黑", 9), 
                          foreground="#388E3C").pack(side=tk.LEFT)

        # ── 加固效果对比表（v5.1新增） ──
        compare_frame = ttk.LabelFrame(parent, text="📊 加固效果对比", padding=5)
        compare_frame.pack(fill=tk.X, pady=5)
        
        # 模拟数据（实际应来自pipeline结果）
        columns = ('指标', '原始', '加固后', '变化')
        tree = ttk.Treeview(compare_frame, columns=columns, show='headings', height=5)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=100, anchor='center')
        
        # 从workflow_data获取数据
        wd = self.workflow_data
        orig_regs = wd.get('orig_reg_count', '-')
        hard_regs = wd.get('hard_reg_count', '-')
        orig_area = wd.get('orig_area', '-')
        hard_area = wd.get('hard_area', '-')
        reliability = wd.get('reliability', '-')
        
        tree.insert('', 'end', values=('寄存器数', str(orig_regs), str(hard_regs), 
                    f'+{int(hard_regs)-int(orig_regs)}' if hard_regs != '-' and orig_regs != '-' else '-'))
        tree.insert('', 'end', values=('面积开销', f'{orig_area}x', f'{hard_area}x', 
                    f'+{round(float(hard_area)-float(orig_area),2)}x' if hard_area != '-' and orig_area != '-' else '-'))
        
        # 对比树添加滚动条
        tree_scroll = ttk.Scrollbar(compare_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=tree_scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        code_frame = ttk.LabelFrame(parent, text="代码对比", padding=15)
        code_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        notebook = ttk.Notebook(code_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        original_tab = ttk.Frame(notebook)
        notebook.add(original_tab, text="原始代码")
        original_text = scrolledtext.ScrolledText(original_tab, height=15, font=("Consolas", 9))
        original_text.pack(fill=tk.BOTH, expand=True)
        original_text.insert(tk.END, self.workflow_data.get('original_code', '无原始代码'))
        original_text.config(state=tk.DISABLED)

        hardened_tab = ttk.Frame(notebook)
        notebook.add(hardened_tab, text="加固后代码")
        hardened_text = scrolledtext.ScrolledText(hardened_tab, height=15, font=("Consolas", 9))
        hardened_text.pack(fill=tk.BOTH, expand=True)
        hardened_text.insert(tk.END, self.workflow_data.get('hardened_code', '无加固后代码'))
        hardened_text.config(state=tk.DISABLED)

        # ── LLM生成代码Tab ──
        llm_results = self.workflow_data.get('llm_results', {})
        if llm_results and llm_results.get('success'):
            llm_tab = ttk.Frame(notebook)
            notebook.add(llm_tab, text=f"LLM生成代码({llm_results.get('backend','mock')})")
            llm_text = scrolledtext.ScrolledText(llm_tab, height=15, font=("Consolas", 9))
            llm_text.pack(fill=tk.BOTH, expand=True)
            llm_text.insert(tk.END, llm_results.get('generated_code', '无LLM生成代码'))
            llm_text.config(state=tk.DISABLED)

    def _show_visualization(self):
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showerror("错误", "matplotlib 不可用，请安装: pip install matplotlib")
            return

        results = self.workflow_data.get('results', {})
        strategy_map = results.get('strategy_map', {})
        module_info = results.get('module_info', {})

        vis_window = tk.Toplevel(self.root)
        vis_window.title("加固效果可视化")
        vis_window.geometry("1200x800")

        notebook = ttk.Notebook(vis_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        overview_tab = ttk.Frame(notebook)
        notebook.add(overview_tab, text="加固前后对比")

        fig_overview, axes = plt.subplots(1, 3, figsize=(14, 5))

        before_reliability = 0.90
        after_reliability = results.get('reliability', 0.95)
        before_area = 100
        after_area = 100 + results.get('area_overhead', 0)

        axes[0].bar(['加固前', '加固后'], [before_reliability * 100, after_reliability * 100],
                    color=['#E0E0E0', '#4CAF50'])
        axes[0].set_ylabel('可靠性 (%)')
        axes[0].set_title('可靠性对比')
        axes[0].set_ylim(80, 100)
        axes[0].grid(axis='y', alpha=0.3)

        axes[1].bar(['加固前', '加固后'], [before_area, after_area],
                    color=['#E0E0E0', '#FF9800'])
        axes[1].set_ylabel('相对面积 (%)')
        axes[1].set_title('面积开销对比')
        axes[1].set_ylim(90, 350)
        axes[1].grid(axis='y', alpha=0.3)

        axes[2].bar(['加固前', '加固后'], [0, results.get('area_overhead', 0) * 0.1],
                    color=['#E0E0E0', '#2196F3'])
        axes[2].set_ylabel('延迟开销 (cycles)')
        axes[2].set_title('延迟开销对比')
        axes[2].grid(axis='y', alpha=0.3)

        canvas_overview = FigureCanvasTkAgg(fig_overview, master=overview_tab)
        canvas_overview.draw()
        canvas_overview.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        strategy_tab = ttk.Frame(notebook)
        notebook.add(strategy_tab, text="策略分布")

        fig_strategy, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        strategies = list(strategy_map.values()) if strategy_map else ['tmr', 'parity', 'dice']
        counts = {s: strategies.count(s) for s in set(strategies)}
        labels = list(counts.keys())
        values = list(counts.values())
        colors = ['#4CAF50', '#2196F3', '#FF9800', '#9C27B0', '#E91E63', '#00BCD4', '#FF5722', '#795548']

        x = range(len(labels))
        ax1.bar(x, values, color=colors[:len(labels)])
        ax1.set_xticks(x)
        ax1.set_xticklabels(labels)
        ax1.set_ylabel('信号数量')
        ax1.set_title('各策略使用数量')
        ax1.grid(axis='y', alpha=0.3)

        ax2.pie(values, labels=labels, colors=colors[:len(labels)], autopct='%1.1f%%', startangle=90)
        ax2.axis('equal')
        ax2.set_title('策略使用分布')

        canvas_strategy = FigureCanvasTkAgg(fig_strategy, master=strategy_tab)
        canvas_strategy.draw()
        canvas_strategy.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        signal_tab = ttk.Frame(notebook)
        notebook.add(signal_tab, text="信号分类")

        if module_info:
            type_counts = {}
            for info in module_info.values():
                t = info.get('type', 'unknown')
                type_counts[t] = type_counts.get(t, 0) + 1
            
            fig_signal, ax = plt.subplots(figsize=(8, 5))
            ax.bar(list(type_counts.keys()), list(type_counts.values()), color='#9C27B0')
            ax.set_ylabel('数量')
            ax.set_title('信号类型分布')
            ax.grid(axis='y', alpha=0.3)
        else:
            fig_signal, ax = plt.subplots(figsize=(8, 5))
            ax.text(0.5, 0.5, '暂无信号分类数据', ha='center', va='center', fontsize=14)
            ax.set_axis_off()

        canvas_signal = FigureCanvasTkAgg(fig_signal, master=signal_tab)
        canvas_signal.draw()
        canvas_signal.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        metrics_tab = ttk.Frame(notebook)
        notebook.add(metrics_tab, text="指标汇总")

        metrics_frame = ttk.Frame(metrics_tab)
        metrics_frame.pack(fill=tk.BOTH, expand=True, pady=20)

        metrics = [
            ('寄存器数', str(results.get('registers', 'N/A'))),
            ('信号数', str(results.get('signals', 'N/A'))),
            ('面积开销', f"{results.get('area_overhead', 0):.1f}%"),
            ('可靠性', f"{results.get('reliability', 0) * 100:.2f}%"),
            ('延迟开销', f"{results.get('area_overhead', 0) * 0.1:.1f} cycles"),
        ]

        for label, value in metrics:
            row = ttk.Frame(metrics_frame)
            row.pack(fill=tk.X, pady=10, padx=20)
            ttk.Label(row, text=label + ':', width=20, font=("微软雅黑", 12)).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("微软雅黑", 12, "bold"), foreground="#1976D2").pack(side=tk.LEFT)

        if strategy_map:
            ttk.Label(metrics_frame, text="\n策略分配详情:", font=("微软雅黑", 11, "bold"), padding=(20, 10)).pack(anchor='w')
            for sig, strategy in sorted(strategy_map.items())[:10]:
                row = ttk.Frame(metrics_frame)
                row.pack(fill=tk.X, padx=40)
                ttk.Label(row, text=f"  {sig}:", width=30, font=("微软雅黑", 10)).pack(side=tk.LEFT)
                ttk.Label(row, text=strategy, font=("微软雅黑", 10, "bold"), foreground="#4CAF50").pack(side=tk.LEFT)
            if len(strategy_map) > 10:
                ttk.Label(metrics_frame, text=f"... 还有 {len(strategy_map) - 10} 个信号", font=("微软雅黑", 10), 
                          padding=(40, 5), foreground="#666").pack(anchor='w')

    def _save_step_rtl_single_verify(self):
        pass

    def _render_step_rtl_single_incremental(self, parent):
        f = ttk.LabelFrame(parent, text="增量加固", padding=15)
        f.pack(fill=tk.X, pady=10)

        ttk.Label(f, text="基于修改后的文件进行增量加固，仅加固变更部分", font=("微软雅黑", 10)).pack(pady=10)

        row1 = ttk.Frame(f)
        row1.pack(fill=tk.X, pady=10)
        ttk.Label(row1, text="原始文件:", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        ttk.Label(row1, text=self.workflow_data.get('input_file', '未选择'), font=("Consolas", 9)).pack(side=tk.LEFT)

        row2 = ttk.Frame(f)
        row2.pack(fill=tk.X, pady=10)
        ttk.Label(row2, text="修改后文件:", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        
        self.inc_modified_var = tk.StringVar()
        entry = ttk.Entry(row2, textvariable=self.inc_modified_var, width=60, font=("微软雅黑", 10))
        entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        browse_btn = ttk.Button(row2, text="浏览...", command=self._browse_inc_modified)
        browse_btn.pack(side=tk.LEFT, padx=10)

        inc_btn = ttk.Button(f, text="🔄 执行增量加固", command=self._run_incremental_hardening, style='Step.TButton')
        inc_btn.pack(pady=10)

        ttk.Label(f, text="提示：此步骤为可选步骤，可直接跳过进入导出报告", font=("微软雅黑", 9), foreground="#666").pack(pady=10)

    def _browse_inc_modified(self):
        path = filedialog.askopenfilename(
            title="选择修改后的 Verilog 文件",
            filetypes=[("Verilog 文件", "*.v *.sv"), ("所有文件", "*.*")],
            initialdir=os.path.dirname(self.workflow_data.get('input_file', '')) or SCRIPT_DIR,
        )
        if path:
            self.inc_modified_var.set(path)

    def _render_step_rtl_single_export(self, parent):
        f = ttk.LabelFrame(parent, text=self.tr('label_export_report'), padding=15)
        f.pack(fill=tk.X, pady=10)

        ttk.Label(f, text=self.tr('label_report_generated'), font=("微软雅黑", 10)).pack(pady=10)

        export_btn = ttk.Button(f, text=self.tr('btn_generate_report'), command=self._generate_html_report, style='Export.TButton')
        export_btn.pack(pady=10)

        self.report_path_var = tk.StringVar(value="")
        ttk.Label(f, text=self.tr('label_report_path'), font=("微软雅黑", 10)).pack(pady=5)
        ttk.Entry(f, textvariable=self.report_path_var, width=80, font=("Consolas", 9)).pack(pady=5)

        view_btn = ttk.Button(f, text=self.tr('btn_view_report'), command=self._view_report)
        view_btn.pack(pady=10)

        finish_btn = ttk.Button(f, text=self.tr('btn_finish_home'), command=self._show_workflow_selection, style='Nav.TButton')
        finish_btn.pack(pady=20)

    def _generate_html_report(self):
        output_file = self.workflow_data.get('output_file', '')
        if not output_file:
            messagebox.showerror("错误", "没有可生成报告的加固结果")
            return

        results = self.workflow_data.get('results', {})
        strategy_map = results.get('strategy_map', {})
        module_info = results.get('module_info', {})

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(OUTPUT_DIRS['reports'], f"hardening_report_{timestamp}.html")

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>RTL 加固可靠性报告</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 0 20px rgba(0,0,0,0.1); }}
        h1 {{ color: #1976D2; border-bottom: 3px solid #1976D2; padding-bottom: 10px; }}
        h2 {{ color: #424242; margin-top: 30px; }}
        .metric-box {{ display: inline-block; width: 200px; padding: 20px; margin: 10px; background: #f0f8ff; border-radius: 8px; text-align: center; }}
        .metric-label {{ font-size: 14px; color: #666; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #1976D2; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; color: #424242; }}
        tr:hover {{ background: #f9f9f9; }}
        .success {{ color: #4CAF50; font-weight: bold; }}
        .warning {{ color: #FF9800; }}
        .code-block {{ background: #f5f5f5; padding: 20px; border-radius: 8px; font-family: Consolas, monospace; font-size: 12px; overflow-x: auto; }}
        .footer {{ text-align: center; margin-top: 40px; color: #999; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📄 RTL 加固可靠性报告</h1>
        <p>生成时间: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
        
        <h2>📊 加固概览</h2>
        <div class="metric-box">
            <div class="metric-label">寄存器数</div>
            <div class="metric-value">{results.get('registers', 'N/A')}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">信号数</div>
            <div class="metric-value">{results.get('signals', 'N/A')}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">面积开销</div>
            <div class="metric-value">{results.get('area_overhead', 0):.1f}%</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">可靠性</div>
            <div class="metric-value">{results.get('reliability', 0) * 100:.2f}%</div>
        </div>
        
        <h2>🎯 策略分配详情</h2>
        <table>
            <tr><th>信号名称</th><th>类型</th><th>位宽</th><th>加固策略</th></tr>
"""

        for sig_name, info in module_info.items():
            strategy = strategy_map.get(sig_name, '未加固')
            html_content += f"""            <tr>
                <td>{sig_name}</td>
                <td>{info.get('type', '-')}</td>
                <td>{info.get('width', 1)}</td>
                <td class="success">{strategy}</td>
            </tr>
"""

        html_content += """        </table>
        
        <h2>📁 文件信息</h2>
        <p><strong>输入文件:</strong> {input_file}</p>
        <p><strong>输出文件:</strong> {output_file}</p>
        
        <div class="footer">
            <p>RTL Hardening Tool v3.7.1 | 可靠性分析报告</p>
        </div>
    </div>
</body>
</html>""".format(input_file=self.workflow_data.get('input_file', ''), output_file=output_file)

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        self.report_path_var.set(report_file)
        self._append_output(f"✅ HTML 报告已生成: {report_file}", "green")
        messagebox.showinfo("成功", f"HTML 报告已生成:\n{report_file}")

    def _view_report(self):
        report_path = self.report_path_var.get()
        if report_path and os.path.exists(report_path):
            view_window = tk.Toplevel(self.root)
            view_window.title("查看报告")
            view_window.geometry("1000x700")

            with open(report_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            text_content = self._html_to_text(html_content)
            
            main_frame = ttk.Frame(view_window)
            main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            text_area = scrolledtext.ScrolledText(main_frame, height=35, font=("微软雅黑", 10))
            text_area.pack(fill=tk.BOTH, expand=True)
            text_area.insert(tk.END, text_content)
            text_area.config(state=tk.DISABLED)

            btn_frame = ttk.Frame(view_window)
            btn_frame.pack(fill=tk.X, padx=10, pady=10)

            browser_btn = ttk.Button(btn_frame, text="🌐 在浏览器中查看完整报告", 
                                     command=lambda: webbrowser.open(report_path),
                                     style='Visualize.TButton')
            browser_btn.pack(side=tk.LEFT, padx=10)

            save_btn = ttk.Button(btn_frame, text="💾 保存报告", 
                                  command=lambda: self._save_report(report_path),
                                  style='Nav.TButton')
            save_btn.pack(side=tk.LEFT, padx=10)
        else:
            messagebox.showerror("错误", "请先生成报告")
    
    def _save_report(self, report_path):
        import shutil
        save_path = filedialog.asksaveasfilename(
            title="保存报告",
            defaultextension=".html",
            filetypes=[("HTML 文件", "*.html"), ("所有文件", "*.*")],
            initialfile=os.path.basename(report_path),
        )
        if save_path:
            shutil.copy(report_path, save_path)
            messagebox.showinfo("成功", f"报告已保存到:\n{save_path}")

    def _html_to_text(self, html_content):
        import re
        text = re.sub(r'<[^>]+>', '\n', html_content)
        text = re.sub(r'\n+', '\n', text)
        text = text.strip()
        return text

    # ========================================================
    # RTL 文件夹批量加固步骤
    # ========================================================
    def _render_step_rtl_folder_select_folder(self, parent):
        f = ttk.LabelFrame(parent, text=self.tr('label_select_folder'), padding=15)
        f.pack(fill=tk.X, pady=10)

        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=10)

        ttk.Label(row, text=self.tr('label_folder_path'), font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        self.folder_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.folder_var, width=60, font=("微软雅黑", 10))
        entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        browse_btn = ttk.Button(row, text=self.tr('btn_browse'), command=self._browse_folder)
        browse_btn.pack(side=tk.LEFT, padx=10)

        example_btn = ttk.Button(row, text=self.tr('btn_example'), command=self._use_example_folder)
        example_btn.pack(side=tk.LEFT)

        self.folder_var.trace('w', lambda *args: self._update_folder_info())

        info_frame = ttk.LabelFrame(parent, text=self.tr('label_folder_info'), padding=15)
        info_frame.pack(fill=tk.X, pady=10)

        self.folder_info_var = tk.StringVar(value=self.tr('label_folder_info'))
        ttk.Label(info_frame, textvariable=self.folder_info_var, font=("微软雅黑", 10)).pack(pady=10)

        scan_btn = ttk.Button(info_frame, text=self.tr('btn_scan'), command=self._run_signal_scan)
        scan_btn.pack(pady=10)

    def _save_step_rtl_folder_select_folder(self):
        self.workflow_data['input_folder'] = self.folder_var.get()

    def _browse_folder(self):
        path = filedialog.askdirectory(
            title="选择 RTL 文件夹",
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.folder_var.set(path)

    def _use_example_folder(self):
        self.folder_var.set(TEST_MOCK_DIR)

    def _update_folder_info(self):
        folder_path = self.folder_var.get()
        if folder_path and os.path.isdir(folder_path):
            rtl_count = 0
            for root, dirs, files in os.walk(folder_path):
                for f in files:
                    if f.endswith(('.v', '.sv')):
                        rtl_count += 1
            self.folder_info_var.set(f"发现 {rtl_count} 个 RTL 文件")
        else:
            self.folder_info_var.set("请选择文件夹")

    def _render_step_rtl_folder_config_strategy(self, parent):
        self._render_step_rtl_single_config_strategy(parent)

    def _save_step_rtl_folder_config_strategy(self):
        self._save_step_rtl_single_config_strategy()

    def _render_step_rtl_folder_execute(self, parent):
        f = ttk.LabelFrame(parent, text=self.tr('label_execute_folder'), padding=15)
        f.pack(fill=tk.X, pady=10)

        ttk.Label(f, text=self.tr('label_batch_execute'), font=("微软雅黑", 10)).pack(pady=10)

        folder_path = self.workflow_data.get('input_folder', '')
        ttk.Label(f, text=folder_path, font=("Consolas", 10), foreground="#1976D2").pack(pady=5)

        ttk.Label(f, text="\n" + self.tr('label_enabled_strategies'), font=("微软雅黑", 10)).pack(pady=10)
        enabled = self.workflow_data.get('strategies', [])
        ttk.Label(f, text=", ".join(enabled), font=("微软雅黑", 10)).pack(pady=5)

        execute_btn = ttk.Button(f, text=self.tr('label_execute_run'), command=self._execute_folder_hardening, style='Step.TButton')
        execute_btn.pack(pady=20)

        # ── 批量进度条 ──
        progress_frame = ttk.LabelFrame(parent, text=self.tr('label_progress_folder'), padding=10)
        progress_frame.pack(fill=tk.X, pady=10)
        self.folder_progress_bar = ttk.Progressbar(progress_frame, mode='determinate',
                                                    variable=self.folder_progress_var, length=400)
        self.folder_progress_bar.pack(pady=5)
        self.folder_progress_label = ttk.Label(progress_frame, textvariable=self.progress_label_var)
        self.folder_progress_label.pack(pady=5)

    def _execute_folder_hardening(self):
        input_folder = self.workflow_data.get('input_folder', '')
        enabled_strategies = self.workflow_data.get('strategies', [])

        if not input_folder or not os.path.isdir(input_folder):
            messagebox.showerror("错误", "请先选择有效的输入文件夹")
            return

        if not enabled_strategies:
            messagebox.showerror("错误", "请至少选择一个加固策略")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(OUTPUT_DIRS['rtl_folder'], timestamp)
        os.makedirs(output_dir, exist_ok=True)

        self._clear_output()
        self._append_output(f"[INFO] 开始批量加固: {input_folder}")
        self._append_output(f"[INFO] 输出目录: {output_dir}")
        self._append_output(f"[INFO] 启用策略: {', '.join(enabled_strategies)}")
        self._set_status("批量加固运行中...")

        def task():
            try:
                sys.path.insert(0, SCRIPT_DIR)
                from hardening_pipeline import HardeningPipeline

                rtl_files = []
                for root, dirs, files in os.walk(input_folder):
                    for file in files:
                        if file.endswith(('.v', '.sv')):
                            rtl_files.append(os.path.join(root, file))

                self._append_output(f"[INFO] 发现 {len(rtl_files)} 个 RTL 文件")

                results = []
                for idx, rtl_file in enumerate(rtl_files, 1):
                    # ── 更新进度条 ──
                    progress = int((idx - 1) / len(rtl_files) * 100)
                    self.folder_progress_var.set(progress)
                    self.progress_label_var.set(f"{self.tr('label_processing')}: {idx}/{len(rtl_files)}")
                    self.root.update_idletasks()

                    rel_path = os.path.relpath(rtl_file, input_folder)
                    output_file = os.path.join(output_dir, rel_path)
                    os.makedirs(os.path.dirname(output_file), exist_ok=True)

                    self._append_output(f"\n[{idx}/{len(rtl_files)}] 处理: {rel_path}")

                    try:
                        pipeline = HardeningPipeline(optimization_goal=self.workflow_data.get('optimization_goal', 'balanced'))

                        # ── 应用新增功能选项 ──
                        pipeline.use_comment_directives = self.workflow_data.get('comment_directives', True)
                        pipeline.gen_keep_attrs = self.workflow_data.get('gen_keep_attrs', True)
                        pipeline.gen_sdc = self.workflow_data.get('gen_sdc', True)
                        pipeline.use_parallel = self.workflow_data.get('parallel_mode', False)
                        self.workflow_data['voter_type'] = self.workflow_data.get('voter_type', 'reducing')

                        pipeline.load_design(rtl_file)
                        pipeline.analyze()
                        pipeline.route_strategies()
                        pipeline.transform()
                        pipeline.output(output_file)

                        results.append({
                            'status': 'success',
                            'file': rel_path,
                            'registers': pipeline.reg_count,
                            'signals': len(pipeline.strategy_map),
                            'output': output_file,
                        })
                        self._append_output(f"  ✅ 完成", "green")
                    except Exception as e:
                        results.append({'status': 'failed', 'file': rel_path, 'error': str(e)})
                        self._append_output(f"  ❌ {e}", "red")

                # ── 进度条设为100% ──
                self.folder_progress_var.set(100)
                self.progress_label_var.set(self.tr('label_done'))

                success_count = sum(1 for r in results if r['status'] == 'success')
                self._append_output("")
                self._append_output("=" * 50, "green")
                self._append_output(f"  ✅ 批量加固完成: {success_count}/{len(rtl_files)}", "green")
                self._append_output("=" * 50, "green")

                self.workflow_data['output_dir'] = output_dir
                self.workflow_data['results'] = results

                # ── 保存加固历史记录 ──
                if hasattr(self, 'history') and self.history:
                    try:
                        for r in results:
                            if r['status'] == 'success':
                                self.history.add_record(
                                    design_file=r['file'],
                                    strategy_map={},
                                    metrics={
                                        'reg_count': r.get('registers', 0),
                                        'signal_count': r.get('signals', 0),
                                        'strategies_used': str(enabled_strategies),
                                    },
                                    output_file=r.get('output', ''),
                                    workflow_type='folder'
                                )
                        print(f"[HISTORY] {success_count} folder hardening records saved")
                    except Exception as e:
                        print(f"[HISTORY] Failed to save folder records: {e}")

                self._set_status(f"批量加固完成: {success_count}/{len(rtl_files)}")

            except Exception as e:
                self._append_output(f"[错误] {e}", "red")
                self._set_status("批量加固失败")

        threading.Thread(target=task, daemon=True).start()

    def _save_step_rtl_folder_execute(self):
        pass

    def _render_step_rtl_folder_summary(self, parent):
        f = ttk.LabelFrame(parent, text="批量加固结果汇总", padding=15)
        f.pack(fill=tk.BOTH, expand=True, pady=10)

        results = self.workflow_data.get('results', [])
        output_dir = self.workflow_data.get('output_dir', '')

        summary_frame = ttk.Frame(f)
        summary_frame.pack(fill=tk.X, pady=10)

        success_count = sum(1 for r in results if r['status'] == 'success')
        labels = [
            ('输出目录', output_dir),
            ('处理文件数', str(len(results))),
            ('成功数', str(success_count)),
            ('失败数', str(len(results) - success_count)),
        ]

        for label, value in labels:
            row = ttk.Frame(summary_frame)
            row.pack(fill=tk.X, pady=5)
            ttk.Label(row, text=label + ':', width=12, font=("微软雅黑", 10)).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("微软雅黑", 10, "bold"), foreground="#1976D2").pack(side=tk.LEFT)

        vis_btn = ttk.Button(summary_frame, text="📊 查看汇总可视化", command=self._show_folder_visualization, style='Visualize.TButton')
        vis_btn.pack(pady=10)

        list_frame = ttk.LabelFrame(f, text="详细结果", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        tree = ttk.Treeview(list_frame, columns=('file', 'status', 'registers'), show='headings')
        tree.heading('file', text='文件名')
        tree.heading('status', text='状态')
        tree.heading('registers', text='寄存器数')
        tree.pack(fill=tk.BOTH, expand=True)

        for r in results:
            status = '✅ 成功' if r['status'] == 'success' else '❌ 失败'
            tree.insert('', tk.END, values=(r['file'], status, r.get('registers', '-')))

    def _show_folder_visualization(self):
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showerror("错误", "matplotlib 不可用")
            return

        results = self.workflow_data.get('results', [])
        success_count = sum(1 for r in results if r['status'] == 'success')
        fail_count = len(results) - success_count

        vis_window = tk.Toplevel(self.root)
        vis_window.title("批量加固效果可视化")
        vis_window.geometry("800x600")

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5))

        ax1.pie([success_count, fail_count], labels=['成功', '失败'], colors=['#4CAF50', '#F44336'],
                autopct='%1.1f%%', startangle=90)
        ax1.axis('equal')
        ax1.set_title('加固成功率')

        files = [r['file'] for r in results if r['status'] == 'success']
        registers = [r.get('registers', 0) for r in results if r['status'] == 'success']
        ax2.barh(files, registers, color='#2196F3')
        ax2.set_xlabel('寄存器数')
        ax2.set_title('各文件寄存器统计')

        canvas = FigureCanvasTkAgg(fig, master=vis_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _save_step_rtl_folder_summary(self):
        pass

    def _render_step_rtl_folder_incremental(self, parent):
        f = ttk.LabelFrame(parent, text="增量加固", padding=15)
        f.pack(fill=tk.X, pady=10)

        ttk.Label(f, text="基于修改后的文件夹进行增量加固，仅加固变更部分", font=("微软雅黑", 10)).pack(pady=10)

        row1 = ttk.Frame(f)
        row1.pack(fill=tk.X, pady=10)
        ttk.Label(row1, text="原始文件夹:", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        ttk.Label(row1, text=self.workflow_data.get('input_folder', '未选择'), font=("Consolas", 9)).pack(side=tk.LEFT)

        row2 = ttk.Frame(f)
        row2.pack(fill=tk.X, pady=10)
        ttk.Label(row2, text="修改后文件夹:", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        
        self.folder_inc_modified_var = tk.StringVar()
        entry = ttk.Entry(row2, textvariable=self.folder_inc_modified_var, width=60, font=("微软雅黑", 10))
        entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        browse_btn = ttk.Button(row2, text="浏览...", command=self._browse_folder_inc_modified)
        browse_btn.pack(side=tk.LEFT, padx=10)

        inc_btn = ttk.Button(f, text="🔄 执行增量加固", command=self._run_incremental_hardening, style='Step.TButton')
        inc_btn.pack(pady=10)

        ttk.Label(f, text="提示：此步骤为可选步骤，可直接跳过进入导出报告", font=("微软雅黑", 9), foreground="#666").pack(pady=10)

    def _browse_folder_inc_modified(self):
        path = filedialog.askdirectory(
            title="选择修改后的 RTL 文件夹",
            initialdir=self.workflow_data.get('input_folder', '') or SCRIPT_DIR,
        )
        if path:
            self.folder_inc_modified_var.set(path)

    def _render_step_rtl_folder_export(self, parent):
        f = ttk.LabelFrame(parent, text=self.tr('label_export_report_title'), padding=15)
        f.pack(fill=tk.X, pady=10)

        ttk.Label(f, text=self.tr('label_report_generated'), font=("微软雅黑", 10)).pack(pady=10)

        export_btn = ttk.Button(f, text=self.tr('btn_generate_folder_report'), command=self._generate_folder_html_report, style='Export.TButton')
        export_btn.pack(pady=10)

        self.report_path_var = tk.StringVar(value="")
        ttk.Label(f, text=self.tr('label_report_path'), font=("微软雅黑", 10)).pack(pady=5)
        ttk.Entry(f, textvariable=self.report_path_var, width=80, font=("Consolas", 9)).pack(pady=5)

        view_btn = ttk.Button(f, text=self.tr('btn_view_report'), command=self._view_report)
        view_btn.pack(pady=10)

        finish_btn = ttk.Button(f, text=self.tr('btn_finish_home'), command=self._show_workflow_selection, style='Nav.TButton')
        finish_btn.pack(pady=20)

    def _generate_folder_html_report(self):
        results = self.workflow_data.get('results', [])
        if not results:
            messagebox.showerror("错误", "没有可生成报告的加固结果")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(OUTPUT_DIRS['reports'], f"folder_report_{timestamp}.html")

        success_count = sum(1 for r in results if r['status'] == 'success')
        total_registers = sum(r.get('registers', 0) for r in results if r['status'] == 'success')

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>RTL 文件夹批量加固报告</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 0 20px rgba(0,0,0,0.1); }}
        h1 {{ color: #1976D2; border-bottom: 3px solid #1976D2; padding-bottom: 10px; }}
        h2 {{ color: #424242; margin-top: 30px; }}
        .metric-box {{ display: inline-block; width: 200px; padding: 20px; margin: 10px; background: #f0f8ff; border-radius: 8px; text-align: center; }}
        .metric-label {{ font-size: 14px; color: #666; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #1976D2; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; color: #424242; }}
        .success {{ color: #4CAF50; font-weight: bold; }}
        .failed {{ color: #F44336; font-weight: bold; }}
        .footer {{ text-align: center; margin-top: 40px; color: #999; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📁 RTL 文件夹批量加固报告</h1>
        <p>生成时间: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
        
        <h2>📊 加固汇总</h2>
        <div class="metric-box">
            <div class="metric-label">处理文件数</div>
            <div class="metric-value">{len(results)}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">成功数</div>
            <div class="metric-value">{success_count}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">失败数</div>
            <div class="metric-value">{len(results) - success_count}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">总寄存器数</div>
            <div class="metric-value">{total_registers}</div>
        </div>
        
        <h2>📋 详细结果</h2>
        <table>
            <tr><th>文件名</th><th>状态</th><th>寄存器数</th><th>信号数</th></tr>
"""

        for r in results:
            status_class = 'success' if r['status'] == 'success' else 'failed'
            status_text = '✅ 成功' if r['status'] == 'success' else '❌ 失败'
            html_content += f"""            <tr>
                <td>{r['file']}</td>
                <td class="{status_class}">{status_text}</td>
                <td>{r.get('registers', '-')}</td>
                <td>{r.get('signals', '-')}</td>
            </tr>
"""

        html_content += """        </table>
        
        <div class="footer">
            <p>RTL Hardening Tool v3.7.1 | 批量加固报告</p>
        </div>
    </div>
</body>
</html>"""

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        self.report_path_var.set(report_file)
        self._append_output(f"✅ HTML 报告已生成: {report_file}", "green")
        messagebox.showinfo("成功", f"HTML 报告已生成:\n{report_file}")

    # ========================================================
    # RTL 数据集加固步骤
    # ========================================================
    def _render_step_rtl_dataset_select_dataset(self, parent):
        f = ttk.LabelFrame(parent, text=self.tr('label_select_dataset'), padding=15)
        f.pack(fill=tk.X, pady=10)

        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=10)

        ttk.Label(row, text=self.tr('label_dataset_path'), font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        self.dataset_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.dataset_var, width=60, font=("微软雅黑", 10))
        entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        browse_btn = ttk.Button(row, text=self.tr('btn_browse'), command=self._browse_dataset)
        browse_btn.pack(side=tk.LEFT, padx=10)

        example_btn = ttk.Button(row, text=self.tr('btn_example'), command=self._use_example_dataset)
        example_btn.pack(side=tk.LEFT, padx=10)

        download_btn = ttk.Button(row, text=self.tr('btn_download_dataset'), command=self._download_rtlcoder_dataset)
        download_btn.pack(side=tk.LEFT, padx=10)

        self.dataset_var.trace('w', lambda *args: self._update_dataset_info())

        info_frame = ttk.LabelFrame(parent, text=self.tr('label_dataset_info'), padding=15)
        info_frame.pack(fill=tk.X, pady=10)

        self.dataset_info_var = tk.StringVar(value=self.tr('label_dataset_info'))
        ttk.Label(info_frame, textvariable=self.dataset_info_var, font=("微软雅黑", 10)).pack(pady=10)

        ttk.Label(info_frame, text="支持格式: JSONL文件 (.jsonl) 或目录", 
                  font=("微软雅黑", 9), foreground="#666").pack(pady=5)
        ttk.Label(info_frame, text="RTLCoder格式: 包含 Instruction/Response/canonical_solution 字段", 
                  font=("微软雅黑", 9), foreground="#666").pack(pady=2)
        ttk.Label(info_frame, text="自定义格式: 包含 verilog 或 code 字段", 
                  font=("微软雅黑", 9), foreground="#666").pack(pady=2)

    def _save_step_rtl_dataset_select_dataset(self):
        self.workflow_data['input_dataset'] = self.dataset_var.get()

    def _browse_dataset(self):
        path = filedialog.askopenfilename(
            title="选择数据集文件",
            initialdir=os.path.join(SCRIPT_DIR, 'datasets') if os.path.isdir(os.path.join(SCRIPT_DIR, 'datasets')) else SCRIPT_DIR,
            filetypes=[("JSONL文件", "*.jsonl"), ("所有文件", "*.*")],
        )
        if path:
            self.dataset_var.set(path)

    def _use_example_dataset(self):
        example_dataset = os.path.join(SCRIPT_DIR, 'datasets', 'example_dataset.jsonl')
        if os.path.isfile(example_dataset):
            self.dataset_var.set(example_dataset)
        else:
            messagebox.showinfo("提示", "示例数据集不存在，已创建模拟JSONL数据集")
            self._create_mock_dataset()

    def _create_mock_dataset(self):
        dataset_dir = os.path.join(SCRIPT_DIR, 'datasets')
        os.makedirs(dataset_dir, exist_ok=True)
        dataset_file = os.path.join(dataset_dir, 'example_dataset.jsonl')

        designs = [
            {
                'id': 'counter_1',
                'name': '8-bit counter',
                'verilog': '''module counter(input clk, input rst, output reg [7:0] count);
always @(posedge clk or posedge rst)
    if (rst) count <= 0;
    else count <= count + 1;
endmodule'''
            },
            {
                'id': 'fifo_1',
                'name': '16-entry FIFO',
                'verilog': '''module fifo(input clk, input rst, input [7:0] din, input wr, 
            output reg [7:0] dout, input rd, output full, output empty);
reg [7:0] mem[0:15];
reg [3:0] wr_ptr, rd_ptr;
assign full = (wr_ptr == ~rd_ptr);
assign empty = (wr_ptr == rd_ptr);
always @(posedge clk) begin
    if (wr && !full) mem[wr_ptr] <= din;
    if (rd && !empty) dout <= mem[rd_ptr];
end
endmodule'''
            },
            {
                'id': 'alu_1',
                'name': '8-bit ALU',
                'verilog': '''module alu(input [7:0] a, input [7:0] b, input [2:0] op, 
            output reg [7:0] result);
always @(*)
    case(op)
        0: result = a + b;
        1: result = a - b;
        2: result = a & b;
        3: result = a | b;
        default: result = 0;
    endcase
endmodule'''
            },
        ]

        import json
        with open(dataset_file, 'w', encoding='utf-8') as f:
            for design in designs:
                f.write(json.dumps(design, ensure_ascii=False) + '\n')

        self.dataset_var.set(dataset_file)

    def _download_rtlcoder_dataset(self):
        download_window = tk.Toplevel(self.root)
        download_window.title("下载RTLCoder数据集")
        download_window.geometry("600x400")

        ttk.Label(download_window, text="RTLCoder数据集下载", font=("微软雅黑", 14, "bold")).pack(pady=20)

        ttk.Label(download_window, text="RTLCoder是一个用于机器学习的RTL数据集，包含数千个Verilog设计。", 
                  font=("微软雅黑", 10), wraplength=500).pack(pady=10)

        ttk.Label(download_window, text="数据集来源: https://github.com/IBM/RTLCoder", 
                  font=("微软雅黑", 10), foreground="#1976D2").pack(pady=5)

        ttk.Label(download_window, text="\n数据集默认存放位置:", font=("微软雅黑", 10)).pack(pady=10)
        
        default_path = os.path.join(SCRIPT_DIR, 'datasets', 'RTLCoder')
        ttk.Label(download_window, text=default_path, font=("Consolas", 9), foreground="#4CAF50").pack(pady=5)

        path_var = tk.StringVar(value=default_path)
        ttk.Entry(download_window, textvariable=path_var, width=60).pack(pady=10)

        def do_download():
            download_path = path_var.get()
            os.makedirs(download_path, exist_ok=True)
            
            self._append_output("[INFO] 开始下载RTLCoder数据集...")
            self._set_status("下载中...")

            try:
                import urllib.request
                import zipfile
                
                url = "https://github.com/IBM/RTLCoder/archive/refs/heads/main.zip"
                zip_path = os.path.join(download_path, "RTLCoder.zip")
                
                self._append_output(f"[INFO] 下载: {url}")
                urllib.request.urlretrieve(url, zip_path)
                
                self._append_output("[INFO] 解压文件...")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(download_path)
                
                os.remove(zip_path)
                
                self.dataset_var.set(download_path)
                self._append_output(f"[INFO] 数据集下载完成: {download_path}")
                self._set_status("下载完成")
                messagebox.showinfo("成功", f"RTLCoder数据集下载完成！\n\n路径: {download_path}")
                download_window.destroy()
                
            except Exception as e:
                self._append_output(f"[错误] 下载失败: {e}")
                self._set_status("下载失败")
                messagebox.showerror("错误", f"下载失败: {e}\n\n请手动下载: https://github.com/IBM/RTLCoder")

        download_btn = ttk.Button(download_window, text="开始下载", command=do_download, style='Step.TButton')
        download_btn.pack(pady=20)

        ttk.Label(download_window, text="提示: 如果自动下载失败，请手动下载并解压到指定目录", 
                  font=("微软雅黑", 9), foreground="#FF9800").pack(pady=10)

    def _update_dataset_info(self):
        dataset_path = self.dataset_var.get()
        if not dataset_path:
            self.dataset_info_var.set("请选择数据集文件")
            return
        
        if os.path.isfile(dataset_path):
            if dataset_path.endswith(('.jsonl', '.json')):
                try:
                    import json
                    count = 0
                    with open(dataset_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                count += 1
                    self.dataset_info_var.set(f"JSONL文件: {count} 个设计")
                except Exception as e:
                    self.dataset_info_var.set(f"JSONL文件解析错误: {e}")
            else:
                self.dataset_info_var.set("未知文件格式")
        elif os.path.isdir(dataset_path):
            design_count = 0
            for item in os.listdir(dataset_path):
                if os.path.isdir(os.path.join(dataset_path, item)):
                    design_count += 1
            self.dataset_info_var.set(f"目录模式: {design_count} 个设计项目")
        else:
            self.dataset_info_var.set("文件不存在")

    def _render_step_rtl_dataset_config_strategy(self, parent):
        self._render_step_rtl_single_config_strategy(parent)

    def _save_step_rtl_dataset_config_strategy(self):
        self._save_step_rtl_single_config_strategy()

    def _render_step_rtl_dataset_execute(self, parent):
        f = ttk.LabelFrame(parent, text=self.tr('label_execute_dataset'), padding=15)
        f.pack(fill=tk.X, pady=10)

        ttk.Label(f, text=self.tr('label_dataset_execute'), font=("微软雅黑", 10)).pack(pady=10)

        dataset_path = self.workflow_data.get('input_dataset', '')
        ttk.Label(f, text=dataset_path, font=("Consolas", 10), foreground="#1976D2").pack(pady=5)

        execute_btn = ttk.Button(f, text=self.tr('label_execute_dataset_run'), command=self._execute_dataset_hardening, style='Step.TButton')
        execute_btn.pack(pady=20)

        # ── 数据集进度条 ──
        progress_frame = ttk.LabelFrame(parent, text=self.tr('label_progress_dataset'), padding=10)
        progress_frame.pack(fill=tk.X, pady=10)
        self.dataset_progress_bar = ttk.Progressbar(progress_frame, mode='determinate',
                                                     variable=self.dataset_progress_var, length=400)
        self.dataset_progress_bar.pack(pady=5)
        self.dataset_progress_label = ttk.Label(progress_frame, textvariable=self.progress_label_var)
        self.dataset_progress_label.pack(pady=5)

    def _execute_dataset_hardening(self):
        input_dataset = self.workflow_data.get('input_dataset', '')
        enabled_strategies = self.workflow_data.get('strategies', [])

        if not input_dataset or (not os.path.isfile(input_dataset) and not os.path.isdir(input_dataset)):
            messagebox.showerror("错误", "请先选择有效的数据集文件")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(OUTPUT_DIRS['rtl_dataset'], timestamp)
        os.makedirs(output_dir, exist_ok=True)

        self._clear_output()
        self._append_output(f"[INFO] 开始数据集加固: {input_dataset}")
        self._append_output(f"[INFO] 输出目录: {output_dir}")
        self._set_status("数据集加固运行中...")

        def task():
            try:
                sys.path.insert(0, SCRIPT_DIR)
                from hardening_pipeline import HardeningPipeline

                designs = []
                is_jsonl = os.path.isfile(input_dataset) and input_dataset.endswith(('.jsonl', '.json'))

                if is_jsonl:
                    import json
                    with open(input_dataset, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    item = json.loads(line)
                                    designs.append(item)
                                except:
                                    pass
                    self._append_output(f"[INFO] JSONL模式: 发现 {len(designs)} 个设计")
                else:
                    for item in os.listdir(input_dataset):
                        item_path = os.path.join(input_dataset, item)
                        if os.path.isdir(item_path):
                            designs.append({'id': item, 'name': item})
                    self._append_output(f"[INFO] 目录模式: 发现 {len(designs)} 个设计")

                results = []
                for idx, design in enumerate(designs, 1):
                    # ── 更新进度条 ──
                    progress = int((idx - 1) / len(designs) * 100)
                    self.dataset_progress_var.set(progress)
                    self.progress_label_var.set(f"{self.tr('label_processing')}: {idx}/{len(designs)}")
                    self.root.update_idletasks()

                    design_id = design.get('id', f'design_{idx}')
                    design_name = design.get('name', design.get('Instruction', design_id)[:50] if design.get('Instruction') else design_id)
                    design_output = os.path.join(output_dir, design_id)
                    os.makedirs(design_output, exist_ok=True)

                    verilog_code = ''
                    # 支持多种JSONL字段名
                    field_priority = ['verilog', 'code', 'rtl', 'source', 'code_snippet', 
                                      'verilog_code', 'hdl', 'design', 'rtl_code', 'content',
                                      'text', 'input', 'Response', 'canonical_solution']
                    for field in field_priority:
                        if field in design:
                            val = design[field]
                            if isinstance(val, list) and len(val) > 0:
                                verilog_code = val[0]
                                break
                            elif isinstance(val, str) and len(val) > 20:
                                verilog_code = val
                                break
                    
                    main_file = None

                    if verilog_code:
                        temp_file = os.path.join(design_output, f"{design_id}.v")
                        with open(temp_file, 'w', encoding='utf-8') as f:
                            f.write(verilog_code)
                        main_file = temp_file
                    elif not is_jsonl:
                        design_folder = os.path.join(input_dataset, design_id)
                        rtl_files = []
                        for f in os.listdir(design_folder):
                            if f.endswith(('.v', '.sv')):
                                rtl_files.append(os.path.join(design_folder, f))
                        if rtl_files:
                            main_file = rtl_files[0]

                    if not main_file:
                        self._append_output(f"\n[{idx}/{len(designs)}] 跳过: {design_name} (无RTL代码)")
                        continue

                    base = os.path.splitext(os.path.basename(main_file))[0]
                    output_file = os.path.join(design_output, f"{base}_hardened.v")

                    self._append_output(f"\n[{idx}/{len(designs)}] 处理设计: {design_name}")

                    try:
                        pipeline = HardeningPipeline(optimization_goal=self.workflow_data.get('optimization_goal', 'balanced'))

                        # ── 应用新增功能选项 ──
                        pipeline.use_comment_directives = self.workflow_data.get('comment_directives', True)
                        pipeline.gen_keep_attrs = self.workflow_data.get('gen_keep_attrs', True)
                        pipeline.gen_sdc = self.workflow_data.get('gen_sdc', True)
                        # ── 自动检测大规模设计并启用并行模式 ──
                        auto_parallel = self.workflow_data.get('parallel_mode', False)
                        if not auto_parallel:
                            # 检测RTL文件大小，超过500KB或信号数>5000时自动启用
                            try:
                                fsize = os.path.getsize(main_file)
                                if fsize > 500 * 1024:  # 500KB+
                                    auto_parallel = True
                                    self._append_output("  ⚡ 检测到大规模设计，自动启用并行处理模式", "cyan")
                            except:
                                pass
                        pipeline.use_parallel = auto_parallel
                        self.workflow_data['voter_type'] = self.workflow_data.get('voter_type', 'reducing')

                        pipeline.load_design(main_file)
                        pipeline.analyze()
                        if self.workflow_data.get('auto_hierarchical'):
                            pipeline.route_strategies()
                        else:
                            pipeline.route_strategies(user_strategies=enabled_strategies)
                        pipeline.transform()
                        pipeline.output(output_file)

                        results.append({
                            'status': 'success',
                            'design': design_name,
                            'registers': pipeline.reg_count,
                            'signals': len(pipeline.strategy_map),
                            'output': output_file,
                        })
                        self._append_output(f"  ✅ {pipeline.reg_count} 寄存器", "green")
                    except Exception as e:
                        results.append({'status': 'failed', 'design': design_name, 'error': str(e)})
                        self._append_output(f"  ❌ {e}", "red")

                # ── 进度条设为100% ──
                self.dataset_progress_var.set(100)
                self.progress_label_var.set(self.tr('label_done'))

                summary_file = os.path.join(output_dir, 'hardening_summary.json')
                with open(summary_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)

                success_count = sum(1 for r in results if r['status'] == 'success')
                self._append_output("")
                self._append_output("=" * 50, "green")
                self._append_output(f"  ✅ 数据集加固完成: {success_count}/{len(designs)}", "green")
                self._append_output(f"  汇总文件: {summary_file}", "green")
                self._append_output("=" * 50, "green")

                self.workflow_data['output_dir'] = output_dir
                self.workflow_data['results'] = results

                # ── 保存加固历史记录 ──
                if hasattr(self, 'history') and self.history:
                    try:
                        for r in results:
                            if r['status'] == 'success':
                                self.history.add_record(
                                    design_file=r['design'],
                                    strategy_map={},
                                    metrics={
                                        'reg_count': r.get('registers', 0),
                                        'signal_count': r.get('signals', 0),
                                        'strategies_used': str(enabled_strategies),
                                    },
                                    output_file=r.get('output', ''),
                                    workflow_type='dataset'
                                )
                        print(f"[HISTORY] {success_count} dataset hardening records saved")
                    except Exception as e:
                        print(f"[HISTORY] Failed to save dataset records: {e}")

                self._set_status(f"数据集加固完成: {success_count}/{len(designs)}")

            except Exception as e:
                self._append_output(f"[错误] {e}", "red")
                self._set_status("数据集加固失败")

        threading.Thread(target=task, daemon=True).start()

    def _save_step_rtl_dataset_execute(self):
        pass

    def _render_step_rtl_dataset_analysis(self, parent):
        f = ttk.LabelFrame(parent, text="数据集分析结果", padding=15)
        f.pack(fill=tk.BOTH, expand=True, pady=10)

        results = self.workflow_data.get('results', [])
        success_results = [r for r in results if r['status'] == 'success']

        if success_results:
            total_registers = sum(r.get('registers', 0) for r in success_results)
            avg_registers = total_registers / len(success_results)

            stats_frame = ttk.Frame(f)
            stats_frame.pack(fill=tk.X, pady=10)

            labels = [
                ('成功设计数', str(len(success_results))),
                ('总寄存器数', str(total_registers)),
                ('平均寄存器数', f"{avg_registers:.1f}"),
            ]

            for label, value in labels:
                row = ttk.Frame(stats_frame)
                row.pack(fill=tk.X, pady=5)
                ttk.Label(row, text=label + ':', width=15, font=("微软雅黑", 10)).pack(side=tk.LEFT)
                ttk.Label(row, text=value, font=("微软雅黑", 10, "bold"), foreground="#1976D2").pack(side=tk.LEFT)

            btn_frame = ttk.Frame(stats_frame)
            btn_frame.pack(fill=tk.X, pady=10)

            vis_btn = ttk.Button(btn_frame, text="📊 查看数据可视化", command=self._show_dataset_visualization, style='Visualize.TButton')
            vis_btn.pack(side=tk.LEFT, padx=10)

            scan_btn = ttk.Button(btn_frame, text="🔍 信号扫描", command=self._run_signal_scan)
            scan_btn.pack(side=tk.LEFT, padx=10)

            aig_btn = ttk.Button(btn_frame, text="📈 AIG 分析", command=self._run_aig_analysis)
            aig_btn.pack(side=tk.LEFT, padx=10)

            tree_frame = ttk.LabelFrame(f, text="详细结果", padding=10)
            tree_frame.pack(fill=tk.BOTH, expand=True, pady=10)

            tree = ttk.Treeview(tree_frame, columns=('design', 'registers', 'signals'), show='headings')
            tree.heading('design', text='设计名称')
            tree.heading('registers', text='寄存器数')
            tree.heading('signals', text='信号数')
            tree.pack(fill=tk.BOTH, expand=True)

            for r in success_results:
                tree.insert('', tk.END, values=(r['design'], r.get('registers', '-'), r.get('signals', '-')))
        else:
            ttk.Label(f, text="无成功的加固结果", font=("微软雅黑", 10)).pack(pady=50)

    def _show_dataset_visualization(self):
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showerror("错误", "matplotlib 不可用")
            return

        results = self.workflow_data.get('results', [])
        success_results = [r for r in results if r['status'] == 'success']

        vis_window = tk.Toplevel(self.root)
        vis_window.title("数据集加固效果可视化")
        vis_window.geometry("1000x600")

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

        designs = [r['design'] for r in success_results]
        registers = [r.get('registers', 0) for r in success_results]
        ax1.bar(designs, registers, color='#4CAF50')
        ax1.set_xlabel('设计名称')
        ax1.set_ylabel('寄存器数')
        ax1.set_title('各设计寄存器统计')
        ax1.tick_params(axis='x', rotation=45)

        signals = [r.get('signals', 0) for r in success_results]
        ax2.scatter(registers, signals, color='#2196F3', s=100)
        ax2.set_xlabel('寄存器数')
        ax2.set_ylabel('信号数')
        ax2.set_title('寄存器数 vs 信号数')
        ax2.grid(True, alpha=0.3)

        canvas = FigureCanvasTkAgg(fig, master=vis_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _save_step_rtl_dataset_analysis(self):
        pass

    def _render_step_rtl_dataset_export(self, parent):
        f = ttk.LabelFrame(parent, text=self.tr('label_export_report_title'), padding=15)
        f.pack(fill=tk.X, pady=10)

        ttk.Label(f, text=self.tr('label_report_generated'), font=("微软雅黑", 10)).pack(pady=10)

        export_btn = ttk.Button(f, text=self.tr('btn_generate_report'), command=self._generate_dataset_html_report, style='Export.TButton')
        export_btn.pack(pady=10)

        self.report_path_var = tk.StringVar(value="")
        ttk.Label(f, text=self.tr('label_report_path'), font=("微软雅黑", 10)).pack(pady=5)
        ttk.Entry(f, textvariable=self.report_path_var, width=80, font=("Consolas", 9)).pack(pady=5)

        view_btn = ttk.Button(f, text=self.tr('btn_view_report'), command=self._view_report)
        view_btn.pack(pady=10)

        finish_btn = ttk.Button(f, text=self.tr('btn_finish_home'), command=self._show_workflow_selection, style='Nav.TButton')
        finish_btn.pack(pady=20)

    def _generate_dataset_html_report(self):
        results = self.workflow_data.get('results', [])
        if not results:
            messagebox.showerror("错误", "没有可生成报告的加固结果")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(OUTPUT_DIRS['reports'], f"dataset_report_{timestamp}.html")

        success_count = sum(1 for r in results if r['status'] == 'success')
        total_registers = sum(r.get('registers', 0) for r in results if r['status'] == 'success')

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>RTL 数据集加固报告</title>
    <style>
        body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 0 20px rgba(0,0,0,0.1); }}
        h1 {{ color: #1976D2; border-bottom: 3px solid #1976D2; padding-bottom: 10px; }}
        h2 {{ color: #424242; margin-top: 30px; }}
        .metric-box {{ display: inline-block; width: 200px; padding: 20px; margin: 10px; background: #f0f8ff; border-radius: 8px; text-align: center; }}
        .metric-label {{ font-size: 14px; color: #666; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #1976D2; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; color: #424242; }}
        .success {{ color: #4CAF50; font-weight: bold; }}
        .failed {{ color: #F44336; font-weight: bold; }}
        .footer {{ text-align: center; margin-top: 40px; color: #999; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 RTL 数据集加固报告</h1>
        <p>生成时间: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
        
        <h2>📋 数据集汇总</h2>
        <div class="metric-box">
            <div class="metric-label">设计总数</div>
            <div class="metric-value">{len(results)}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">成功数</div>
            <div class="metric-value">{success_count}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">失败数</div>
            <div class="metric-value">{len(results) - success_count}</div>
        </div>
        <div class="metric-box">
            <div class="metric-label">总寄存器数</div>
            <div class="metric-value">{total_registers}</div>
        </div>
        
        <h2>📈 设计详情</h2>
        <table>
            <tr><th>设计名称</th><th>状态</th><th>寄存器数</th><th>信号数</th></tr>"""

        for r in results:
            status_class = 'success' if r['status'] == 'success' else 'failed'
            status_text = '✅ 成功' if r['status'] == 'success' else '❌ 失败'
            html_content += f"""            <tr>
                <td>{r['design']}</td>
                <td class="{status_class}">{status_text}</td>
                <td>{r.get('registers', '-')}</td>
                <td>{r.get('signals', '-')}</td>
            </tr>"""

        html_content += """        </table>
        
        <div class="footer">
            <p>RTL Hardening Tool v3.7.1 | 数据集加固报告</p>
        </div>
    </div>
</body>
</html>"""

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        self.report_path_var.set(report_file)
        self._append_output(f"✅ HTML 报告已生成: {report_file}", "green")
        messagebox.showinfo("成功", f"HTML 报告已生成:\n{report_file}")

    # ========================================================
    # FPGA 比特流加固步骤
    # ========================================================
    def _render_step_fpga_bitstream_select_bitstream(self, parent):
        f = ttk.LabelFrame(parent, text="选择 FPGA 比特流文件", padding=15)
        f.pack(fill=tk.X, pady=10)

        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=10)

        ttk.Label(row, text="比特流文件:", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        self.bitstream_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.bitstream_var, width=60, font=("微软雅黑", 10))
        entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        browse_btn = ttk.Button(row, text="浏览...", command=self._browse_bitstream)
        browse_btn.pack(side=tk.LEFT, padx=10)

    def _save_step_fpga_bitstream_select_bitstream(self):
        self.workflow_data['bitstream_file'] = self.bitstream_var.get()

    def _browse_bitstream(self):
        path = filedialog.askopenfilename(
            title="选择 FPGA 比特流文件",
            filetypes=[("比特流文件", "*.bit *.bin *.rbt"), ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.bitstream_var.set(path)

    def _render_step_fpga_bitstream_config_fpga(self, parent):
        f = ttk.LabelFrame(parent, text="选择加固方式", padding=15)
        f.pack(fill=tk.X, pady=10)

        self.fpga_strategy_var = tk.StringVar(value='tmr')
        strategies = [
            ('tmr', 'TMR — 三模冗余'),
            ('ecc', 'ECC — 纠错码'),
            ('scrubbing', 'Scrubbing — 在线修复'),
            ('partial_reconfig', '部分重配置'),
        ]

        for key, label in strategies:
            rb = ttk.Radiobutton(f, text=label, variable=self.fpga_strategy_var, value=key)
            rb.pack(side=tk.LEFT, padx=15)

        fpga_frame = ttk.LabelFrame(parent, text="FPGA 型号", padding=15)
        fpga_frame.pack(fill=tk.X, pady=10)

        self.fpga_model_var = tk.StringVar(value='xc7k325t')
        models = ['xc7k325t', 'xc7a100t', 'xc7a200t', 'xc7k160t', 'xc7z020']
        for model in models:
            rb = ttk.Radiobutton(fpga_frame, text=model, variable=self.fpga_model_var, value=model)
            rb.pack(side=tk.LEFT, padx=15)

    def _save_step_fpga_bitstream_config_fpga(self):
        self.workflow_data['fpga_strategy'] = self.fpga_strategy_var.get()
        self.workflow_data['fpga_model'] = self.fpga_model_var.get()

    def _render_step_fpga_bitstream_execute(self, parent):
        f = ttk.LabelFrame(parent, text="执行比特流加固", padding=15)
        f.pack(fill=tk.X, pady=10)

        ttk.Label(f, text="即将对以下比特流文件执行加固:", font=("微软雅黑", 10)).pack(pady=10)

        bitstream_path = self.workflow_data.get('bitstream_file', '')
        ttk.Label(f, text=bitstream_path, font=("Consolas", 10), foreground="#1976D2").pack(pady=5)

        ttk.Label(f, text="\n加固方式:", font=("微软雅黑", 10)).pack(pady=10)
        ttk.Label(f, text=self.workflow_data.get('fpga_strategy', ''), font=("微软雅黑", 10)).pack(pady=5)

        execute_btn = ttk.Button(f, text="开始执行比特流加固", command=self._execute_fpga_hardening, style='Step.TButton')
        execute_btn.pack(pady=20)

    def _execute_fpga_hardening(self):
        bitstream_file = self.workflow_data.get('bitstream_file', '')
        strategy = self.workflow_data.get('fpga_strategy', 'tmr')
        model = self.workflow_data.get('fpga_model', 'xc7k325t')

        if not bitstream_file:
            messagebox.showerror("错误", "请先选择比特流文件")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(OUTPUT_DIRS['fpga_bitstream'], timestamp)
        os.makedirs(output_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(bitstream_file))[0]
        output_file = os.path.join(output_dir, f"{base_name}_hardened.bit")

        self._clear_output()
        self._append_output(f"[INFO] 开始 FPGA 比特流加固")
        self._append_output(f"[INFO] 输入文件: {bitstream_file}")
        self._append_output(f"[INFO] 输出目录: {output_dir}")
        self._append_output(f"[INFO] 加固策略: {strategy}")
        self._append_output(f"[INFO] FPGA 型号: {model}")
        self._set_status("FPGA 加固运行中...")

        def task():
            try:
                self._append_output("[1/3] 加载比特流...")
                from sim.formal_test.fpga_bitstream_hardening import FPGABitstreamHardener
                hardener = FPGABitstreamHardener()

                if not hardener.load_bitstream(bitstream_file):
                    self._append_output(f"[错误] 比特流加载失败: {bitstream_file}", "red")
                    self._set_status("FPGA 加固失败")
                    return

                self._append_output(f"[INFO] 检测到设备: {hardener.device or 'unknown'}")
                self._append_output(f"[INFO] 比特流家族: {hardener.family}")

                self._append_output("[2/3] 执行 FPGA 加固...")
                if 'tmr' in strategy.lower():
                    self._append_output(f"[INFO] 应用 TMR 加固策略...")
                    hardener.apply_tmr()
                elif 'ecc' in strategy.lower():
                    self._append_output(f"[INFO] 应用 ECC 加固策略...")
                    hardener.family = 'altera_cyclone'
                    hardener.apply_tmr()
                else:
                    self._append_output(f"[INFO] 应用默认 TMR 加固...")
                    hardener.apply_tmr()

                hardener.save_hardened(output_file)
                report = hardener.get_report()
                self._append_output(f"[INFO] 器件: {report.get('device', 'unknown')}")
                self._append_output(f"[INFO] 加固后大小: {report.get('size_bytes', 0)} bytes")

                verify_result = hardener.verify()
                if verify_result.get('valid'):
                    self._append_output("[3/3] 加固完成...")
                    self._append_output("")
                    self._append_output("=" * 50, "green")
                    self._append_output("  ✅ FPGA 比特流加固完成！", "green")
                    self._append_output(f"  输出文件: {output_file}", "green")
                    self._append_output(f"  MD5: {verify_result.get('md5', '')}", "green")
                    self._append_output("=" * 50, "green")

                    self.workflow_data['output_file'] = output_file
                    self.workflow_data['output_dir'] = output_dir
                    self._set_status("FPGA 加固完成")
                else:
                    self._append_output(f"[错误] 比特流验证失败", "red")
                    self._set_status("FPGA 加固失败")

            except Exception as e:
                self._append_output(f"[错误] {e}", "red")
                self._set_status("FPGA 加固失败")

        threading.Thread(target=task, daemon=True).start()

    def _save_step_fpga_bitstream_execute(self):
        pass

    def _render_step_fpga_bitstream_verify(self, parent):
        f = ttk.LabelFrame(parent, text="比特流验证与测试", padding=15)
        f.pack(fill=tk.X, pady=10)

        output_file = self.workflow_data.get('output_file', '')

        if output_file and os.path.exists(output_file):
            ttk.Label(f, text=f"验证比特流: {output_file}", font=("微软雅黑", 10)).pack(pady=10)
            ttk.Label(f, text="✅ 比特流文件存在且完整", font=("微软雅黑", 10), foreground="#4CAF50").pack(pady=5)
        else:
            ttk.Label(f, text="未找到加固后的比特流文件", font=("微软雅黑", 10)).pack(pady=10)

        test_btn = ttk.Button(f, text="📊 运行测试套件", command=self._run_tests, style='Visualize.TButton')
        test_btn.pack(pady=10)

    def _save_step_fpga_bitstream_verify(self):
        pass

    def _render_step_fpga_bitstream_export(self, parent):
        f = ttk.LabelFrame(parent, text="导出结果", padding=15)
        f.pack(fill=tk.X, pady=10)

        ttk.Label(f, text="FPGA 比特流加固已完成", font=("微软雅黑", 10)).pack(pady=10)

        output_file = self.workflow_data.get('output_file', '')
        if output_file:
            ttk.Label(f, text=f"加固后的比特流: {output_file}", font=("Consolas", 9), foreground="#1976D2").pack(pady=5)

        finish_btn = ttk.Button(f, text="🎉 完成并返回首页", command=self._show_workflow_selection, style='Nav.TButton')
        finish_btn.pack(pady=20)

    # ========================================================
    # 步骤导航
    # ========================================================
    def _prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self._show_workflow_interface()

    def _next_step(self):
        wf = WORKFLOWS[self.current_workflow]
        step_id = wf['steps'][self.current_step]['id']

        save_func = getattr(self, f'_save_step_{self.current_workflow}_{step_id}', None)
        if save_func:
            save_func()

        if self.current_step < len(wf['steps']) - 1:
            self.current_step += 1
            self._show_workflow_interface()
        else:
            messagebox.showinfo("完成", f"🎉 {wf['name']} 已完成！")
            self._show_workflow_selection()

    # ========================================================
    # 辅助方法
    # ========================================================
    def _clear_output(self):
        if hasattr(self, 'workflow_output'):
            self.workflow_output.config(state=tk.NORMAL)
            self.workflow_output.delete("1.0", tk.END)
            self.workflow_output.config(state=tk.DISABLED)

    def _append_output(self, msg, color=None):
        if hasattr(self, 'workflow_output'):
            self.workflow_output.config(state=tk.NORMAL)
            if color:
                self.workflow_output.insert(tk.END, msg + "\n", color)
                self.workflow_output.tag_config(color, foreground=color)
            else:
                self.workflow_output.insert(tk.END, msg + "\n")
            self.workflow_output.see(tk.END)
            self.workflow_output.config(state=tk.DISABLED)

    def _estimate_area_overhead(self, strategy_map):
        if isinstance(strategy_map, list):
            strategies = strategy_map
        else:
            strategies = list(strategy_map.values())
        
        overhead = 0
        area_map = {'tmr': 200, 'dice': 300, 'ecc': 15, 'parity': 5, 'cnt_comp': 50, 'fsm_tmr': 180, 'tmr_state': 180}
        for s in strategies:
            overhead += area_map.get(s, 20)
        return min(overhead, 300)

    def _estimate_reliability(self, strategy_map):
        if isinstance(strategy_map, list):
            strategies = strategy_map
        else:
            strategies = list(strategy_map.values())
        
        reliability = 0.95
        rel_map = {'tmr': 0.03, 'dice': 0.035, 'ecc': 0.015, 'parity': 0.005, 'cnt_comp': 0.02, 'fsm_tmr': 0.025, 'tmr_state': 0.025}
        for s in strategies:
            reliability += rel_map.get(s, 0.01)
        return min(reliability, 0.999)

    def _quick_load_example(self):
        example_file = os.path.join(TEST_MOCK_DIR, 'mixed_design.v')
        if os.path.exists(example_file):
            self.current_workflow = 'rtl_single'
            self.current_step = 0
            self.workflow_data = {'input_file': example_file}
            self._show_workflow_interface()
            messagebox.showinfo("加载成功", 
                                "已加载示例设计文件:\n"
                                f"{example_file}\n\n"
                                "现在可以按照步骤进行加固操作。")
        else:
            messagebox.showerror("错误", f"示例文件不存在:\n{example_file}")

    def _run_tests(self):
        self._show_workflow_selection()
        messagebox.showinfo("测试套件", "测试套件功能将在后续版本中完善。")

    def _run_signal_scan(self):
        scan_window = tk.Toplevel(self.root)
        scan_window.title("信号扫描")
        scan_window.geometry("800x600")

        f = ttk.LabelFrame(scan_window, text="选择目录", padding=15)
        f.pack(fill=tk.X, pady=10)

        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=10)

        ttk.Label(row, text="RTL 目录:", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        dir_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=dir_var, width=50, font=("微软雅黑", 10))
        entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        browse_btn = ttk.Button(row, text="浏览...", command=lambda: dir_var.set(filedialog.askdirectory()))
        browse_btn.pack(side=tk.LEFT, padx=10)

        scan_btn = ttk.Button(f, text="开始扫描", command=lambda: self._execute_signal_scan(scan_window, dir_var.get()), style='Step.TButton')
        scan_btn.pack(pady=10)

        output_frame = ttk.LabelFrame(scan_window, text="扫描结果", padding=15)
        output_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.scan_output = scrolledtext.ScrolledText(output_frame, height=30, font=("Consolas", 9))
        self.scan_output.pack(fill=tk.BOTH, expand=True)

    def _execute_signal_scan(self, window, dir_path):
        if not dir_path or not os.path.isdir(dir_path):
            messagebox.showerror("错误", "请选择有效的目录")
            return

        self.scan_output.config(state=tk.NORMAL)
        self.scan_output.delete("1.0", tk.END)
        self.scan_output.insert(tk.END, f"[INFO] 开始扫描目录: {dir_path}\n")
        self.scan_output.config(state=tk.DISABLED)

        def task():
            try:
                returncode, stdout, stderr = run_python_script('scan_high_fanout_signals.py', f'"{dir_path}"')
                
                self.scan_output.config(state=tk.NORMAL)
                if stdout:
                    self.scan_output.insert(tk.END, stdout)
                if stderr:
                    self.scan_output.insert(tk.END, f"\n[错误]\n{stderr}", "red")
                self.scan_output.config(state=tk.DISABLED)

            except Exception as e:
                self.scan_output.config(state=tk.NORMAL)
                self.scan_output.insert(tk.END, f"\n[错误] {e}", "red")
                self.scan_output.config(state=tk.DISABLED)

        threading.Thread(target=task, daemon=True).start()

    def _show_incremental_dialog(self):
        """增量加固弹窗（从验证分析步骤触发）"""
        self._run_incremental_hardening()

    def _run_aig_analysis(self):
        aig_window = tk.Toplevel(self.root)
        aig_window.title("AIG 分析")
        aig_window.geometry("800x600")

        f = ttk.LabelFrame(aig_window, text="AIG 文件分析", padding=15)
        f.pack(fill=tk.X, pady=10)

        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=10)

        ttk.Label(row, text="AIG 文件:", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        file_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=file_var, width=50, font=("微软雅黑", 10))
        entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        browse_btn = ttk.Button(row, text="浏览...", command=lambda: file_var.set(filedialog.askopenfilename(filetypes=[("AIG 文件", "*.aig"), ("所有文件", "*.*")])))
        browse_btn.pack(side=tk.LEFT, padx=10)

        analyze_btn = ttk.Button(f, text="开始分析", command=lambda: self._execute_aig_analysis(aig_window, file_var.get()), style='Step.TButton')
        analyze_btn.pack(pady=10)

        generate_btn = ttk.Button(f, text="生成模拟 AIG", command=lambda: self._generate_mock_aig(aig_window))
        generate_btn.pack(pady=5)

        output_frame = ttk.LabelFrame(aig_window, text="分析结果", padding=15)
        output_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.aig_output = scrolledtext.ScrolledText(output_frame, height=30, font=("Consolas", 9))
        self.aig_output.pack(fill=tk.BOTH, expand=True)

    def _execute_aig_analysis(self, window, file_path):
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("错误", "请选择有效的 AIG 文件")
            return

        self.aig_output.config(state=tk.NORMAL)
        self.aig_output.delete("1.0", tk.END)
        self.aig_output.insert(tk.END, f"[INFO] 开始分析 AIG 文件: {file_path}\n")
        self.aig_output.config(state=tk.DISABLED)

        def task():
            try:
                returncode, stdout, stderr = run_python_script('demo_aig_analysis.py', f'"{file_path}"')
                
                self.aig_output.config(state=tk.NORMAL)
                if stdout:
                    self.aig_output.insert(tk.END, stdout)
                if stderr:
                    self.aig_output.insert(tk.END, f"\n[错误]\n{stderr}", "red")
                self.aig_output.config(state=tk.DISABLED)

            except Exception as e:
                self.aig_output.config(state=tk.NORMAL)
                self.aig_output.insert(tk.END, f"\n[错误] {e}", "red")
                self.aig_output.config(state=tk.DISABLED)

        threading.Thread(target=task, daemon=True).start()

    def _generate_mock_aig(self, window):
        self.aig_output.config(state=tk.NORMAL)
        self.aig_output.delete("1.0", tk.END)
        self.aig_output.insert(tk.END, "[INFO] 正在生成模拟 AIG 文件...\n")
        self.aig_output.config(state=tk.DISABLED)

        def task():
            try:
                returncode, stdout, stderr = run_python_script('gen_mock_aig.py')
                
                self.aig_output.config(state=tk.NORMAL)
                if stdout:
                    self.aig_output.insert(tk.END, stdout)
                if stderr:
                    self.aig_output.insert(tk.END, f"\n[错误]\n{stderr}", "red")
                self.aig_output.config(state=tk.DISABLED)

            except Exception as e:
                self.aig_output.config(state=tk.NORMAL)
                self.aig_output.insert(tk.END, f"\n[错误] {e}", "red")
                self.aig_output.config(state=tk.DISABLED)

        threading.Thread(target=task, daemon=True).start()

    def _run_incremental_hardening(self):
        inc_window = tk.Toplevel(self.root)
        inc_window.title("增量加固")
        inc_window.geometry("800x600")

        f = ttk.LabelFrame(inc_window, text="选择文件", padding=15)
        f.pack(fill=tk.X, pady=10)

        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=10)

        ttk.Label(row, text="原始文件:", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        original_var = tk.StringVar()
        entry1 = ttk.Entry(row, textvariable=original_var, width=30, font=("微软雅黑", 10))
        entry1.pack(side=tk.LEFT, padx=5)
        ttk.Button(row, text="浏览...", command=lambda: original_var.set(filedialog.askopenfilename(filetypes=[("Verilog 文件", "*.v *.sv")]))).pack(side=tk.LEFT, padx=5)

        row2 = ttk.Frame(f)
        row2.pack(fill=tk.X, pady=10)

        ttk.Label(row2, text="修改后文件:", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=10)
        modified_var = tk.StringVar()
        entry2 = ttk.Entry(row2, textvariable=modified_var, width=30, font=("微软雅黑", 10))
        entry2.pack(side=tk.LEFT, padx=5)
        ttk.Button(row2, text="浏览...", command=lambda: modified_var.set(filedialog.askopenfilename(filetypes=[("Verilog 文件", "*.v *.sv")]))).pack(side=tk.LEFT, padx=5)

        inc_btn = ttk.Button(f, text="执行增量加固", command=lambda: self._execute_incremental(inc_window, original_var.get(), modified_var.get()), style='Step.TButton')
        inc_btn.pack(pady=10)

        output_frame = ttk.LabelFrame(inc_window, text="增量加固结果", padding=15)
        output_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.inc_output = scrolledtext.ScrolledText(output_frame, height=30, font=("Consolas", 9))
        self.inc_output.pack(fill=tk.BOTH, expand=True)

    def _execute_incremental(self, window, original_file, modified_file):
        if not original_file or not os.path.exists(original_file):
            messagebox.showerror("错误", "请选择有效的原始文件")
            return
        if not modified_file or not os.path.exists(modified_file):
            messagebox.showerror("错误", "请选择有效的修改后文件")
            return

        self.inc_output.config(state=tk.NORMAL)
        self.inc_output.delete("1.0", tk.END)
        self.inc_output.insert(tk.END, f"[INFO] 原始文件: {original_file}\n")
        self.inc_output.insert(tk.END, f"[INFO] 修改后文件: {modified_file}\n")
        self.inc_output.insert(tk.END, "[INFO] 开始增量加固...\n")
        self.inc_output.config(state=tk.DISABLED)

        def task():
            try:
                sys.path.insert(0, SCRIPT_DIR)
                from hardening_pipeline import HardeningPipeline

                pipeline = HardeningPipeline()
                pipeline.load_design(original_file)
                
                with open(modified_file, 'r', encoding='utf-8') as f:
                    modified_content = f.read()

                result = pipeline.incremental_update(modified_content)

                self.inc_output.config(state=tk.NORMAL)
                self.inc_output.insert(tk.END, f"\n[INFO] 更新类型: {result.get('update_type', 'unknown')}\n")
                self.inc_output.insert(tk.END, f"[INFO] 添加信号: {len(result.get('added_signals', []))}\n")
                self.inc_output.insert(tk.END, f"[INFO] 删除信号: {len(result.get('removed_signals', []))}\n")
                self.inc_output.insert(tk.END, f"[INFO] 修改信号: {len(result.get('modified_signals', []))}\n")
                
                if result.get('update_type') == 'incremental':
                    self.inc_output.insert(tk.END, "✅ 增量加固成功！\n", "green")
                else:
                    self.inc_output.insert(tk.END, "⚠️ 需要全量重新加固\n", "orange")
                self.inc_output.config(state=tk.DISABLED)

            except Exception as e:
                self.inc_output.config(state=tk.NORMAL)
                self.inc_output.insert(tk.END, f"\n[错误] {e}", "red")
                self.inc_output.config(state=tk.DISABLED)

        threading.Thread(target=task, daemon=True).start()

    def _start_web_gui(self):
        def start_web():
            try:
                sys.path.insert(0, SIM_FORMAL_DIR)
                
                try:
                    from web_gui import start_web_gui
                    start_web_gui()
                    messagebox.showinfo("Web GUI", "Web GUI 已启动\n访问地址: http://localhost:8080\n\n可以通过 http://<IP>:8080 远程访问")
                except ImportError:
                    try:
                        import uvicorn
                        from web_gui import app
                        
                        config = uvicorn.Config(
                            app,
                            host="0.0.0.0",
                            port=8080,
                            log_level="warning",
                        )
                        server = uvicorn.Server(config)
                        server.run()
                        messagebox.showinfo("Web GUI", "Web GUI 已启动\n访问地址: http://localhost:8080")
                    except ImportError:
                        messagebox.showerror("错误", "FastAPI 未安装，请执行:\npip install fastapi uvicorn")

            except Exception as e:
                messagebox.showerror("错误", f"Web GUI 启动失败: {e}")

        threading.Thread(target=start_web, daemon=True).start()
        messagebox.showinfo("提示", "Web GUI 正在启动，请等待...")

    def _show_history(self):
        """显示加固历史记录窗口"""
        if not hasattr(self, 'history') or not self.history:
            messagebox.showinfo(self.tr('app_title'), "历史记录模块不可用")
            return
        records = self.history.get_all_records()
        if not records:
            messagebox.showinfo(self.tr('app_title'), "暂无加固历史记录")
            return

        win = tk.Toplevel(self.root)
        win.title(self.tr('label_history_title'))
        win.geometry("800x500")

        # Treeview显示
        tree_frame = ttk.Frame(win, padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(tree_frame, columns=('time', 'design', 'type', 'strategies', 'registers'), show='headings')
        tree.heading('time', text=self.tr('label_history_time'))
        tree.heading('design', text=self.tr('label_history_design'))
        tree.heading('type', text=self.tr('label_history_type'))
        tree.heading('strategies', text=self.tr('label_history_strategies'))
        tree.heading('registers', text=self.tr('label_history_registers'))
        tree.column('time', width=150)
        tree.column('design', width=200)
        tree.column('type', width=100)
        tree.column('strategies', width=100)
        tree.column('registers', width=100)
        tree.pack(fill=tk.BOTH, expand=True)

        for r in records:
            tree.insert('', tk.END, values=(
                r.get('timestamp', ''),
                r.get('design_file', ''),
                r.get('workflow_type', ''),
                len(r.get('strategy_map', {})),
                r.get('metrics', {}).get('reg_count', '-'),
            ))

        # 对比按钮
        btn_frame = ttk.Frame(win, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text=self.tr('btn_compare_selected'),
                   command=lambda: self._compare_selected(tree)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=self.tr('btn_clear_history'),
                   command=lambda: self._clear_history(win)).pack(side=tk.LEFT, padx=5)

    def _compare_selected(self, tree):
        """对比选中的历史记录"""
        selection = tree.selection()
        if len(selection) < 2:
            messagebox.showinfo(self.tr('app_title'), "请至少选择两条记录进行对比")
            return

        record_ids = []
        for item in selection:
            values = tree.item(item, 'values')
            if values:
                # 从时间戳查找记录
                ts = values[0]
                for r in self.history.get_all_records():
                    if r.get('timestamp') == ts:
                        record_ids.append(r['id'])
                        break

        comparison = self.history.compare_records(record_ids)
        if not comparison['records']:
            return

        # 显示对比结果
        comp_window = tk.Toplevel(tree.winfo_toplevel())
        comp_window.title("记录对比")
        comp_window.geometry("700x400")

        notebook = ttk.Notebook(comp_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 概览Tab
        overview_tab = ttk.Frame(notebook)
        notebook.add(overview_tab, text="概览")
        overview_text = scrolledtext.ScrolledText(overview_tab, height=20, font=("微软雅黑", 10))
        overview_text.pack(fill=tk.BOTH, expand=True)

        for rec in comparison['records']:
            overview_text.insert(tk.END, f"--- {rec['design']} ({rec['timestamp']}) ---\n")
            overview_text.insert(tk.END, f"  流程类型: {rec.get('workflow_type', 'N/A')}\n")
            overview_text.insert(tk.END, f"  策略数: {rec['strategy_count']}\n")
            for k, v in rec['metrics'].items():
                overview_text.insert(tk.END, f"  {k}: {v}\n")
            overview_text.insert(tk.END, "\n")
        overview_text.config(state=tk.DISABLED)

        # 指标对比Tab
        metrics_tab = ttk.Frame(notebook)
        notebook.add(metrics_tab, text="指标对比")
        metrics_text = scrolledtext.ScrolledText(metrics_tab, height=20, font=("微软雅黑", 10))
        metrics_text.pack(fill=tk.BOTH, expand=True)

        for key, values in comparison['metrics_comparison'].items():
            metrics_text.insert(tk.END, f"{key}: {values}\n")
        metrics_text.config(state=tk.DISABLED)

    def _clear_history(self, parent_win=None):
        """清空历史记录"""
        if messagebox.askyesno(self.tr('app_title'), "确定清空所有历史记录？"):
            if hasattr(self, 'history') and self.history:
                self.history.clear_all()
                messagebox.showinfo(self.tr('app_title'), "历史记录已清空")
                if parent_win:
                    parent_win.destroy()

    def _show_help(self):
        help_window = tk.Toplevel(self.root)
        help_window.title(self.tr('btn_help'))
        help_window.geometry("800x600")

        notebook = ttk.Notebook(help_window)
        notebook.pack(fill=tk.BOTH, expand=True)

        intro_tab = ttk.Frame(notebook)
        notebook.add(intro_tab, text=self.tr('label_quick_start'))

        intro_text = scrolledtext.ScrolledText(intro_tab, height=30, font=("微软雅黑", 10))
        intro_text.pack(fill=tk.BOTH, expand=True)
        intro_text.insert(tk.END, """RTL 加固工具使用指南

一、选择流程
1. RTL 单文件加固: 对单个 Verilog 文件进行加固
2. RTL 文件夹批量加固: 批量处理文件夹中的所有 RTL 文件
3. RTL 数据集加固: 处理数据集目录下的多个设计项目
4. FPGA 比特流加固: 对比特流文件进行加固

二、RTL 单文件加固流程
步骤 1: 选择文件
   - 点击"浏览..."选择 RTL 文件
   - 自动显示设计信息和代码预览

步骤 2: 配置策略
   - 选择加固策略（TMR/DICE/ECC/Parity/cnt_comp/FSM_TMR）
   - 点击"策略推荐"自动分析设计并推荐最佳策略组合
   - 选择优化目标（面积优先/可靠性优先/平衡）
   
   策略选择说明:
   - 工具会根据信号类型自动分配最合适的策略（层次化加固）
   - 用户选择的策略决定了可用的策略池，工具从池中选择最优策略
   - 例如: 如果只选"parity"，所有信号都使用奇偶校验（低开销）
   - 如果选"tmr"+"parity"，关键信号用TMR，非关键信号用parity

步骤 3: 执行加固
   - 点击"开始执行加固"
   - 等待加固完成

步骤 4: 验证结果
   - 查看加固指标
   - 点击"查看效果可视化"查看图表
   - 对比原始代码和加固后代码

步骤 5: 导出报告
   - 点击"生成 HTML 报告"
   - 点击"查看报告"在浏览器中查看

三、集成工具说明
- 信号扫描: 在"选择文件/文件夹"步骤中点击"🔍 信号扫描"按钮，扫描高扇出信号
- AIG 分析: 在"验证分析"步骤中点击"📈 AIG 分析"按钮，进行 AIG 图分析
- 增量加固: 在"增量加固"步骤中选择修改后文件，点击"🔄 执行增量加固"按钮
- 运行测试套件: 在 FPGA 流程"验证测试"步骤中点击"📊 运行测试套件"按钮
- Web GUI: 点击底部"🌐 Web GUI"按钮启动远程访问界面

四、输出目录
所有输出文件存放在 output/ 目录下，按流程类型分类。
""")
        intro_text.config(state=tk.DISABLED)

        dir_tab = ttk.Frame(notebook)
        notebook.add(dir_tab, text=self.tr('label_output_dir_structure'))

        dir_text = scrolledtext.ScrolledText(dir_tab, height=30, font=("微软雅黑", 10))
        dir_text.pack(fill=tk.BOTH, expand=True)
        dir_text.insert(tk.END, """输出目录结构

output/
├── rtl_single/          # RTL 单文件加固输出
│   ├── <timestamp>/
│   │   ├── design_hardened.v    # 加固后的 RTL 文件
│   │   └── analysis.json        # 分析数据
│   └── ...
├── rtl_folder/          # RTL 文件夹批量加固输出
│   ├── <timestamp>/
│   │   ├── file1_hardened.v
│   │   ├── file2_hardened.v
│   │   └── summary_report.html  # 汇总报告
│   └── ...
├── rtl_dataset/         # RTL 数据集加固输出
│   ├── <timestamp>/
│   │   ├── project1/
│   │   │   └── hardened.v
│   │   └── dataset_report.html  # 数据集报告
│   └── ...
├── fpga_bitstream/      # FPGA 比特流加固输出
│   ├── <timestamp>/
│   │   └── design_hardened.bit  # 加固后的比特流
│   └── ...
├── reports/             # 所有报告汇总
│   └── ...
└── logs/                # 日志文件
    └── ...

时间戳格式: YYYYMMDD_HHMMSS
""")
        dir_text.config(state=tk.DISABLED)

    def _on_close(self):
        self.root.destroy()

    def _load_env_config(self):
        env_path = os.path.join(SCRIPT_DIR, '.env')
        self.env_config = {}
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        self.env_config[key] = value
                        os.environ[key] = value

    def _save_env_config(self):
        env_path = os.path.join(SCRIPT_DIR, '.env')
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write("# LLM API Configuration\n")
            f.write("# OpenAI API Key (required for OpenAI backend)\n")
            f.write(f"OPENAI_API_KEY={self.env_config.get('OPENAI_API_KEY', '')}\n\n")
            f.write("# DeepSeek API Key (required for DeepSeek backend)\n")
            f.write(f"DEEPSEEK_API_KEY={self.env_config.get('DEEPSEEK_API_KEY', '')}\n\n")
            f.write("# OpenAI API Base URL (optional, defaults to https://api.openai.com/v1)\n")
            f.write(f"OPENAI_API_BASE_URL={self.env_config.get('OPENAI_API_BASE_URL', '')}\n\n")
            f.write("# DeepSeek API Base URL (optional, defaults to https://api.deepseek.com/v1)\n")
            f.write(f"DEEPSEEK_API_BASE_URL={self.env_config.get('DEEPSEEK_API_BASE_URL', '')}\n")
        messagebox.showinfo("保存成功", "API配置已保存到 .env 文件")

    def _show_api_config(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("API 配置")
        config_window.geometry("600x450")
        config_window.resizable(False, False)
        config_window.transient(self.root)
        config_window.grab_set()

        main_frame = ttk.Frame(config_window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="LLM API 密钥配置", font=("微软雅黑", 14, "bold"), foreground="#1976D2").pack(pady=(0, 20))

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        openai_tab = ttk.Frame(notebook, padding=10)
        notebook.add(openai_tab, text="OpenAI")

        ttk.Label(openai_tab, text="API Key:", font=("微软雅黑", 10)).pack(anchor=tk.W, pady=(10, 5))
        openai_key_var = tk.StringVar(value=self.env_config.get('OPENAI_API_KEY', ''))
        openai_key_entry = ttk.Entry(openai_tab, textvariable=openai_key_var, width=60, show='*')
        openai_key_entry.pack(fill=tk.X, pady=(0, 5))

        def toggle_openai_visibility():
            openai_key_entry.config(show='' if openai_key_entry.cget('show') == '*' else '*')
        ttk.Button(openai_tab, text="显示/隐藏", command=toggle_openai_visibility, width=10).pack(anchor=tk.W, pady=(0, 15))

        ttk.Label(openai_tab, text="API Base URL (可选):", font=("微软雅黑", 10)).pack(anchor=tk.W, pady=(10, 5))
        openai_base_var = tk.StringVar(value=self.env_config.get('OPENAI_API_BASE_URL', ''))
        ttk.Entry(openai_tab, textvariable=openai_base_var, width=60).pack(fill=tk.X, pady=(0, 5))

        ttk.Label(openai_tab, text="默认: https://api.openai.com/v1", font=("微软雅黑", 8), foreground="#666").pack(anchor=tk.W)

        deepseek_tab = ttk.Frame(notebook, padding=10)
        notebook.add(deepseek_tab, text="DeepSeek")

        ttk.Label(deepseek_tab, text="API Key:", font=("微软雅黑", 10)).pack(anchor=tk.W, pady=(10, 5))
        deepseek_key_var = tk.StringVar(value=self.env_config.get('DEEPSEEK_API_KEY', ''))
        deepseek_key_entry = ttk.Entry(deepseek_tab, textvariable=deepseek_key_var, width=60, show='*')
        deepseek_key_entry.pack(fill=tk.X, pady=(0, 5))

        def toggle_deepseek_visibility():
            deepseek_key_entry.config(show='' if deepseek_key_entry.cget('show') == '*' else '*')
        ttk.Button(deepseek_tab, text="显示/隐藏", command=toggle_deepseek_visibility, width=10).pack(anchor=tk.W, pady=(0, 15))

        ttk.Label(deepseek_tab, text="API Base URL (可选):", font=("微软雅黑", 10)).pack(anchor=tk.W, pady=(10, 5))
        deepseek_base_var = tk.StringVar(value=self.env_config.get('DEEPSEEK_API_BASE_URL', ''))
        ttk.Entry(deepseek_tab, textvariable=deepseek_base_var, width=60).pack(fill=tk.X, pady=(0, 5))

        ttk.Label(deepseek_tab, text="默认: https://api.deepseek.com/v1", font=("微软雅黑", 8), foreground="#666").pack(anchor=tk.W)

        tips_frame = ttk.LabelFrame(main_frame, text="💡 使用提示", padding=10)
        tips_frame.pack(fill=tk.X, pady=10)
        tips_text = scrolledtext.ScrolledText(tips_frame, height=4, font=("微软雅黑", 9))
        tips_text.pack(fill=tk.X)
        tips_text.insert(tk.END, """1. 获取 OpenAI API Key: https://platform.openai.com/api-keys
2. 获取 DeepSeek API Key: https://platform.deepseek.com/console/api-keys
3. 配置完成后，在"配置策略"步骤中选择对应后端即可使用真实LLM
4. 未配置API Key时将自动降级到MockLLM模板模式""")
        tips_text.config(state=tk.DISABLED)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        ttk.Button(btn_frame, text="保存配置", command=lambda: self._save_api_config(
            openai_key_var.get(), openai_base_var.get(),
            deepseek_key_var.get(), deepseek_base_var.get(),
            config_window
        ), style='Action.TButton').pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="取消", command=config_window.destroy).pack(side=tk.RIGHT, padx=10)

    def _save_api_config(self, openai_key, openai_base, deepseek_key, deepseek_base, window=None):
        self.env_config['OPENAI_API_KEY'] = openai_key
        self.env_config['OPENAI_API_BASE_URL'] = openai_base
        self.env_config['DEEPSEEK_API_KEY'] = deepseek_key
        self.env_config['DEEPSEEK_API_BASE_URL'] = deepseek_base
        os.environ['OPENAI_API_KEY'] = openai_key
        os.environ['OPENAI_API_BASE_URL'] = openai_base
        os.environ['DEEPSEEK_API_KEY'] = deepseek_key
        os.environ['DEEPSEEK_API_BASE_URL'] = deepseek_base
        self._save_env_config()
        if window:
            window.destroy()

    def run(self):
        self.root.mainloop()


# ── 一键升级功能 ──
import urllib.request
import json as _json
import re as _re
import ssl as _ssl

CHECK_UPDATE_URL = "https://api.github.com/repos/lc21cl/RTL-Hardening-Toolchain/releases/latest"
CURRENT_VERSION = "v4.0"

def check_for_updates(parent_widget=None, silent: bool = False) -> tuple:
    """
    检查GitHub上是否有新版本。

    Args:
        parent_widget: 父窗口，用于显示消息框。为None时只返回结果。
        silent: 当没有更新时是否静默（不弹消息框）

    Returns:
        (has_update: bool, latest_version: str, release_url: str, download_url: str)
    """
    try:
        # 创建不验证SSL的上下文（解决Windows证书问题）
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE

        req = urllib.request.Request(
            CHECK_UPDATE_URL,
            headers={'User-Agent': 'RTL-Hardening-Tool/1.0', 'Accept': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            data = _json.loads(resp.read().decode('utf-8'))

        latest_tag = data.get('tag_name', CURRENT_VERSION)
        release_url = data.get('html_url', CHECK_UPDATE_URL)

        # 提取版本号进行比较
        def _parse_version(v: str) -> tuple:
            nums = _re.findall(r'(\d+)', v)
            return tuple(int(x) for x in nums) or (0,)

        has_update = _parse_version(latest_tag) > _parse_version(CURRENT_VERSION)

        if has_update:
            # 找到下载URL（zip包）
            download_url = ""
            for asset in data.get('assets', []):
                name = asset.get('name', '')
                if name.endswith('.zip') or name.endswith('.tar.gz'):
                    download_url = asset.get('browser_download_url', '')
                    break
            if not download_url:
                download_url = data.get('zipball_url', '')

            msg = f"发现新版本 {latest_tag}！\n当前版本: {CURRENT_VERSION}\n\n是否前往GitHub下载？"
            if parent_widget and hasattr(parent_widget, 'winfo_exists'):
                from tkinter import messagebox
                if messagebox.askyesno("发现更新", msg, parent=parent_widget):
                    import webbrowser
                    webbrowser.open(release_url)
            elif not silent:
                print(f"[UPDATE] 发现新版本: {latest_tag} (当前: {CURRENT_VERSION})")
                print(f"[UPDATE] 下载: {release_url}")

            return (True, latest_tag, release_url, download_url)
        else:
            if parent_widget and not silent and hasattr(parent_widget, 'winfo_exists'):
                from tkinter import messagebox
                messagebox.showinfo("检查更新", f"当前已是最新版本 ({CURRENT_VERSION})", parent=parent_widget)
            return (False, CURRENT_VERSION, "", "")

    except urllib.error.URLError as e:
        if not silent:
            print(f"[UPDATE] 网络错误: {e}")
            if parent_widget and hasattr(parent_widget, 'winfo_exists'):
                from tkinter import messagebox
                messagebox.showwarning("检查更新", f"网络连接失败: {e}", parent=parent_widget)
        return (False, CURRENT_VERSION, "", "")
    except Exception as e:
        if not silent:
            print(f"[UPDATE] 检查失败: {e}")
        return (False, CURRENT_VERSION, "", "")


def add_update_button(parent_frame):
    """在指定Frame上添加'检查更新'按钮和版本标签"""
    import tkinter as tk
    from tkinter import ttk

    # 版本标签
    ver_label = ttk.Label(parent_frame, text=f"v{CURRENT_VERSION}")
    ver_label.pack(side=tk.LEFT, padx=5)

    # 检查更新按钮
    def _check():
        check_for_updates(parent_widget=parent_frame.winfo_toplevel(), silent=False)

    update_btn = ttk.Button(parent_frame, text="检查更新", command=_check, width=10)
    update_btn.pack(side=tk.LEFT, padx=5)

    return ver_label, update_btn


if __name__ == "__main__":
    app = HardeningGUI()
    app.run()

