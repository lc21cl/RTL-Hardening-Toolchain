#!/usr/bin/env python3
"""
harden_gui.py — RTL 加固工具集 GUI 界面

集成 hardening_pipeline / run_regression / scan_high_fanout_signals /
demo_aig_analysis / gen_mock_aig 等工具的可视化操作界面。

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

# ============================================================
# 路径配置
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(SCRIPT_DIR, 'reports')
TEST_MOCK_DIR = os.path.join(SCRIPT_DIR, 'test_mock_data')
SIM_FORMAL_DIR = os.path.join(SCRIPT_DIR, 'sim', 'formal_test')

VERSION = "2.0.0"
APP_TITLE = f"RTL 加固工具集 v{VERSION}"


# ============================================================
# 工具提示 Mixin
# ============================================================
class ToolTip:
    """为控件添加悬浮提示"""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind('<Enter>', self.show_tip)
        widget.bind('<Leave>', self.hide_tip)

    def show_tip(self, _event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f'+{x}+{y}')
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID,
                         borderwidth=1, font=("微软雅黑", 9))
        label.pack()

    def hide_tip(self, _event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


def add_tooltip(widget, text):
    """便捷添加工具提示"""
    ToolTip(widget, text)


# ============================================================
# 子进程调用工具
# ============================================================
def run_subprocess(cmd, cwd=None, capture=True):
    """运行外部命令，返回 (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            shell=True,
            cwd=cwd or SCRIPT_DIR,
            timeout=300,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "执行超时（300 秒）"
    except FileNotFoundError as e:
        return -1, "", f"找不到可执行文件: {e}"
    except Exception as e:
        return -1, "", str(e)


def run_python_script(script_rel, args="", cwd=None):
    """调用同级目录下的 Python 脚本"""
    script_path = os.path.join(SCRIPT_DIR, script_rel)
    if not os.path.exists(script_path):
        # 尝试 sim/formal_test 下
        alt = os.path.join(SIM_FORMAL_DIR, script_rel)
        if os.path.exists(alt):
            script_path = alt
        else:
            return -1, "", f"脚本不存在: {script_rel}"
    cmd = f'"{sys.executable}" "{script_path}" {args}'
    return run_subprocess(cmd, cwd=cwd)


# ============================================================
# 主应用
# ============================================================
class HardeningGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1200x800")
        self.root.minsize(1000, 650)

        # 尝试设置图标（若有）
        try:
            self.root.iconbitmap(default='')
        except Exception:
            pass

        # ---------- 样式配置 ----------
        self._configure_styles()

        # ---------- 变量 ----------
        self.pipeline_file = tk.StringVar()
        self.pipeline_output = tk.StringVar()
        self.strategy_vars = {
            'tmr':       tk.BooleanVar(value=True),
            'dice':      tk.BooleanVar(value=False),
            'ecc':       tk.BooleanVar(value=False),
            'parity':    tk.BooleanVar(value=True),
            'cnt_comp':  tk.BooleanVar(value=True),
            'fsm_tmr':   tk.BooleanVar(value=False),
        }
        self.scan_dir = tk.StringVar()
        self.scan_threshold = tk.IntVar(value=3)
        self.aig_file = tk.StringVar()

        # ---------- 状态 ----------
        self.status_text = tk.StringVar(value="就绪")
        self.last_action = tk.StringVar(value="—")

        # 构建 UI
        self._build_menu()
        self._build_main()
        self._build_statusbar()

        # 窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self):
        """配置ttk样式，为不同功能按钮添加颜色区分"""
        style = ttk.Style()
        style.theme_use('clam')

        style.configure('.', font=("微软雅黑", 9))
        style.configure('Title.TLabel', font=("微软雅黑", 11, "bold"), foreground="#1976D2")
        style.configure('Info.TLabel', font=("微软雅黑", 9), foreground="#666")
        style.configure('Success.TLabel', font=("微软雅黑", 9), foreground="#388E3C")
        style.configure('Warning.TLabel', font=("微软雅黑", 9), foreground="#F57C00")
        style.configure('Error.TLabel', font=("微软雅黑", 9), foreground="#D32F2F")

        style.configure('Browse.TButton', padding=6, font=("微软雅黑", 9))
        style.map('Browse.TButton',
                  background=[('active', '#E3F2FD'), ('!active', '#BBDEFB')],
                  foreground=[('active', '#1976D2'), ('!active', '#1565C0')])

        style.configure('Action.TButton', padding=6, font=("微软雅黑", 9, "bold"))
        style.map('Action.TButton',
                  background=[('active', '#C8E6C9'), ('!active', '#A5D6A7')],
                  foreground=[('active', '#2E7D32'), ('!active', '#1B5E20')])

        style.configure('Run.TButton', padding=6, font=("微软雅黑", 9, "bold"))
        style.map('Run.TButton',
                  background=[('active', '#FFCDD2'), ('!active', '#EF9A9A')],
                  foreground=[('active', '#C62828'), ('!active', '#B71C1C')])

        style.configure('Export.TButton', padding=6, font=("微软雅黑", 9))
        style.map('Export.TButton',
                  background=[('active', '#FFF3E0'), ('!active', '#FFE0B2')],
                  foreground=[('active', '#E65100'), ('!active', '#E65100')])

        style.configure('Recommend.TButton', padding=6, font=("微软雅黑", 9, "bold"))
        style.map('Recommend.TButton',
                  background=[('active', '#E1BEE7'), ('!active', '#CE93D8')],
                  foreground=[('active', '#6A1B9A'), ('!active', '#6A1B9A')])

        style.configure('Visualize.TButton', padding=6, font=("微软雅黑", 9))
        style.map('Visualize.TButton',
                  background=[('active', '#B2EBF2'), ('!active', '#80DEEA')],
                  foreground=[('active', '#006064'), ('!active', '#006064')])

        style.configure('LabelFrame.TLabelframe', font=("微软雅黑", 10, "bold"), foreground="#333")
        style.configure('LabelFrame.TLabelframe.Label', font=("微软雅黑", 10, "bold"), foreground="#1976D2")

        style.configure('Treeview', font=("微软雅黑", 9), rowheight=24)
        style.configure('Treeview.Heading', font=("微软雅黑", 9, "bold"), foreground="#1976D2")
        style.map('Treeview',
                  background=[('selected', '#1976D2'), ('!selected', '#FFFFFF')],
                  foreground=[('selected', '#FFFFFF'), ('!selected', '#333333')])

    # ========================================================
    # 菜单栏
    # ========================================================
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于 (About)", command=self._show_about)
        menubar.add_cascade(label="帮助 (Help)", menu=help_menu)

    def _show_about(self):
        messagebox.showinfo(
            "关于 RTL 加固工具集",
            f"RTL 加固工具集 v{VERSION}\n\n"
            "集成以下工具:\n"
            "  • 加固管线 (Hardening Pipeline)\n"
            "  • 回归测试 (Test Runner)\n"
            "  • 信号扫描 (Signal Scan)\n"
            "  • AIG 分析 (AIG Analysis)\n"
            "  • 报告查看 (Reports)\n\n"
            f"脚本目录: {SCRIPT_DIR}\n"
            "Python " + sys.version.split()[0]
        )

    # ========================================================
    # 主区域 — EDA风格布局
    # ========================================================
    def _build_main(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

        self._build_toolbar(main_frame)

        center_frame = ttk.Frame(main_frame)
        center_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        self._build_left_panel(center_frame)

        self._build_center_workspace(center_frame)

        self._build_right_panel(center_frame)

        self._build_bottom_output(main_frame)

    def _build_toolbar(self, parent):
        toolbar = ttk.Frame(parent, style='Toolbar.TFrame')
        toolbar.pack(fill=tk.X, padx=2, pady=2)

        style = ttk.Style()
        style.configure('Toolbar.TFrame', background='#f5f5f5', relief=tk.RAISED)

        tools = [
            ('加固管线', self._switch_to_tab_pipeline, 'Browse.TButton'),
            ('测试运行', self._switch_to_tab_testrunner, 'Action.TButton'),
            ('信号扫描', self._switch_to_tab_signalscan, 'Action.TButton'),
            ('AIG分析', self._switch_to_tab_aig, 'Action.TButton'),
        ]

        for text, cmd, btn_style in tools:
            btn = ttk.Button(toolbar, text=text, command=cmd, style=btn_style)
            btn.pack(side=tk.LEFT, padx=3, pady=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        new_tools = [
            ('层次化加固', self._switch_to_tab_hierarchical, 'Run.TButton'),
            ('策略推荐', self._switch_to_tab_strategy_recommend, 'Recommend.TButton'),
            ('效果可视化', self._switch_to_tab_visualization, 'Visualize.TButton'),
            ('增量加固', self._switch_to_tab_incremental, 'Action.TButton'),
            ('FPGA加固', self._switch_to_tab_fpga, 'Action.TButton'),
            ('可靠性报告', self._switch_to_tab_reliability, 'Export.TButton'),
            ('形式化验证', self._switch_to_tab_formal, 'Run.TButton'),
            ('Web GUI', self._switch_to_tab_web_gui, 'Export.TButton'),
        ]

        for text, cmd, btn_style in new_tools:
            btn = ttk.Button(toolbar, text=text, command=cmd, style=btn_style)
            btn.pack(side=tk.LEFT, padx=3, pady=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        report_btn = ttk.Button(toolbar, text='报告', command=self._switch_to_tab_reports, style='Export.TButton')
        report_btn.pack(side=tk.RIGHT, padx=3, pady=2)

    def _build_left_panel(self, parent):
        left_panel = ttk.Frame(parent, width=220)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 3))
        left_panel.pack_propagate(False)

        project_frame = ttk.LabelFrame(left_panel, text="项目资源", padding=5)
        project_frame.pack(fill=tk.X, padx=3, pady=3)

        self.project_tree = ttk.Treeview(project_frame, show='tree')
        self.project_tree.pack(fill=tk.BOTH, expand=True)

        project_root = self.project_tree.insert('', tk.END, text='RTL 设计', open=True)
        self.project_tree.insert(project_root, tk.END, text='未选择文件', tags=('file',))

        strategy_frame = ttk.LabelFrame(left_panel, text="加固策略", padding=5)
        strategy_frame.pack(fill=tk.X, padx=3, pady=3)

        strategies = ['tmr', 'dice', 'ecc', 'parity', 'cnt_comp', 'onehot_fsm', 'watchdog', 'parity_bus']
        for strat in strategies:
            cb = ttk.Checkbutton(strategy_frame, text=strat, variable=self.strategy_vars.get(strat))
            cb.pack(anchor=tk.W, pady=1)

    def _build_center_workspace(self, parent):
        center_frame = ttk.Frame(parent)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(center_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._build_tab_pipeline()
        self._build_tab_testrunner()
        self._build_tab_signalscan()
        self._build_tab_aig()
        self._build_tab_hierarchical()
        self._build_tab_strategy_recommend()
        self._build_tab_visualization()
        self._build_tab_incremental()
        self._build_tab_fpga()
        self._build_tab_reliability()
        self._build_tab_formal()
        self._build_tab_web_gui()
        self._build_tab_reports()

    def _build_right_panel(self, parent):
        right_panel = ttk.Frame(parent, width=200)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(3, 0))
        right_panel.pack_propagate(False)

        info_frame = ttk.LabelFrame(right_panel, text="设计信息", padding=5)
        info_frame.pack(fill=tk.X, padx=3, pady=3)

        self.design_info_vars = {
            'module': tk.StringVar(value="未选择"),
            'regs': tk.StringVar(value="0"),
            'ports': tk.StringVar(value="0"),
            'submodules': tk.StringVar(value="0"),
        }

        for label, key in [('模块', 'module'), ('寄存器', 'regs'), ('端口', 'ports'), ('子模块', 'submodules')]:
            row = ttk.Frame(info_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=label + ':', width=8).pack(side=tk.LEFT)
            ttk.Label(row, textvariable=self.design_info_vars[key], font=("微软雅黑", 9, "bold"),
                      foreground="#1976D2").pack(side=tk.LEFT)

        quick_actions = ttk.LabelFrame(right_panel, text="快捷操作", padding=5)
        quick_actions.pack(fill=tk.X, padx=3, pady=3)

        quick_btns = [
            ('快速加固', self._quick_harden, 'Run.TButton'),
            ('分析设计', self._quick_analyze, 'Action.TButton'),
            ('查看报告', self._quick_report, 'Export.TButton'),
        ]

        for text, cmd, style in quick_btns:
            btn = ttk.Button(quick_actions, text=text, command=cmd, style=style)
            btn.pack(fill=tk.X, pady=2)

    def _build_bottom_output(self, parent):
        bottom_frame = ttk.Frame(parent, height=120)
        bottom_frame.pack(fill=tk.X, padx=2, pady=(5, 0))
        bottom_frame.pack_propagate(False)

        output_notebook = ttk.Notebook(bottom_frame)
        output_notebook.pack(fill=tk.BOTH, expand=True)

        output_frame = ttk.Frame(output_notebook)
        output_notebook.add(output_frame, text="输出")
        self.bottom_output = scrolledtext.ScrolledText(output_frame, height=5, font=("Consolas", 9))
        self.bottom_output.pack(fill=tk.BOTH, expand=True)

        log_frame = ttk.Frame(output_notebook)
        output_notebook.add(log_frame, text="日志")
        self.bottom_log = scrolledtext.ScrolledText(log_frame, height=5, font=("Consolas", 9))
        self.bottom_log.pack(fill=tk.BOTH, expand=True)

    def _switch_to_tab_pipeline(self):
        self.notebook.select(0)

    def _switch_to_tab_testrunner(self):
        self.notebook.select(1)

    def _switch_to_tab_signalscan(self):
        self.notebook.select(2)

    def _switch_to_tab_aig(self):
        self.notebook.select(3)

    def _switch_to_tab_hierarchical(self):
        self.notebook.select(4)

    def _switch_to_tab_strategy_recommend(self):
        self.notebook.select(5)

    def _switch_to_tab_visualization(self):
        self.notebook.select(6)

    def _switch_to_tab_incremental(self):
        self.notebook.select(7)

    def _switch_to_tab_fpga(self):
        self.notebook.select(8)

    def _switch_to_tab_reliability(self):
        self.notebook.select(9)

    def _switch_to_tab_formal(self):
        self.notebook.select(10)

    def _switch_to_tab_web_gui(self):
        self.notebook.select(11)

    def _switch_to_tab_reports(self):
        self.notebook.select(12)

    def _quick_harden(self):
        self.notebook.select(4)

    def _quick_analyze(self):
        self.notebook.select(5)

    def _quick_report(self):
        self.notebook.select(9)

    # ========================================================
    # 状态栏
    # ========================================================
    def _build_statusbar(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        lbl_version = ttk.Label(frame, text=APP_TITLE, font=("微软雅黑", 8))
        lbl_version.pack(side=tk.LEFT, padx=(0, 10))

        lbl_status = ttk.Label(frame, textvariable=self.status_text,
                                font=("微软雅黑", 8), foreground="#555")
        lbl_status.pack(side=tk.LEFT, padx=(0, 10))

        lbl_action_label = ttk.Label(frame, text="上次操作:", font=("微软雅黑", 8))
        lbl_action_label.pack(side=tk.LEFT, padx=(0, 2))
        lbl_action = ttk.Label(frame, textvariable=self.last_action,
                                font=("微软雅黑", 8), foreground="#888")
        lbl_action.pack(side=tk.LEFT)

    def _set_status(self, text, action=None):
        self.status_text.set(text)
        if action:
            self.last_action.set(action)
        self.root.update_idletasks()

    # ========================================================
    # 辅助方法
    # ========================================================
    @staticmethod
    def _make_label(frame, text, **kwargs):
        """创建带样式的标签"""
        return ttk.Label(frame, text=text, font=("微软雅黑", 9), **kwargs)

    def _add_output_area(self, parent, height=12):
        """添加带滚动条的文本输出区域"""
        frame = ttk.Frame(parent)
        text = scrolledtext.ScrolledText(
            frame, wrap=tk.WORD, height=height,
            font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white"
        )
        text.pack(fill=tk.BOTH, expand=True)
        frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        return text

    def _append_output(self, text_widget, msg, color=None):
        """向输出区域追加文本（线程安全）"""
        def _do():
            text_widget.config(state=tk.NORMAL)
            if color:
                text_widget.insert(tk.END, msg + "\n", color)
                text_widget.tag_config(color, foreground=color)
            else:
                text_widget.insert(tk.END, msg + "\n")
            text_widget.see(tk.END)
            text_widget.config(state=tk.DISABLED)
        self.root.after(0, _do)

    def _clear_output(self, text_widget):
        """清空输出区域"""
        def _do():
            text_widget.config(state=tk.NORMAL)
            text_widget.delete("1.0", tk.END)
            text_widget.config(state=tk.DISABLED)
        self.root.after(0, _do)

    # ========================================================
    # Tab 1: 加固管线 (Pipeline)
    # ========================================================
    def _build_tab_pipeline(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 加固管线 (Pipeline) ")

        # -- 文件选择区 --
        f_file = ttk.LabelFrame(tab, text="输入 / 输出文件", padding=5)
        f_file.pack(fill=tk.X, pady=(5, 0), padx=5)

        row1 = ttk.Frame(f_file)
        row1.pack(fill=tk.X, pady=2)
        self._make_label(row1, "选择输入 Verilog 文件:").pack(side=tk.LEFT)
        ent_in = ttk.Entry(row1, textvariable=self.pipeline_file, width=60)
        ent_in.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_browse = ttk.Button(row1, text="浏览...", command=self._pipeline_browse_in)
        btn_browse.pack(side=tk.LEFT)
        add_tooltip(btn_browse, "选择待加固的 Verilog/SystemVerilog 文件")

        row2 = ttk.Frame(f_file)
        row2.pack(fill=tk.X, pady=2)
        self._make_label(row2, "保存加固后文件:").pack(side=tk.LEFT)
        ent_out = ttk.Entry(row2, textvariable=self.pipeline_output, width=60)
        ent_out.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_out = ttk.Button(row2, text="选择路径...", command=self._pipeline_browse_out)
        btn_out.pack(side=tk.LEFT)
        add_tooltip(btn_out, "加固后输出文件保存路径")

        # -- 策略配置区 --
        f_strat = ttk.LabelFrame(tab, text="加固策略配置", padding=5)
        f_strat.pack(fill=tk.X, pady=(5, 0), padx=5)

        strat_desc = {
            'tmr':      'TMR — 三模冗余 (3 副本 + 多数表决)',
            'dice':     'DICE — 4 节点交叉耦合存储',
            'ecc':      'ECC — SECDED 纠错码',
            'parity':   'Parity — 奇偶校验',
            'cnt_comp': 'cnt_comp — 计数器比较器',
            'fsm_tmr':  'FSM_TMR — 状态机三重化',
        }
        row_strat = ttk.Frame(f_strat)
        row_strat.pack(fill=tk.X, pady=2)
        for i, (key, desc) in enumerate(strat_desc.items()):
            cb = ttk.Checkbutton(row_strat, text=desc,
                                 variable=self.strategy_vars[key])
            cb.pack(side=tk.LEFT, padx=(0, 15))
            add_tooltip(cb, f"启用 {desc.split('—')[0].strip()} 加固策略")
            if (i + 1) % 3 == 0:
                row_strat = ttk.Frame(f_strat)
                row_strat.pack(fill=tk.X, pady=2)

        # -- 执行区 --
        f_action = ttk.Frame(tab)
        f_action.pack(fill=tk.X, pady=5, padx=5)
        btn_run = ttk.Button(f_action, text="执行加固",
                             command=self._pipeline_run)
        btn_run.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_run, "按所选策略执行加固管线")

        # -- 输出区 --
        self.pipeline_output_text = self._add_output_area(tab, height=14)

    def _pipeline_browse_in(self):
        path = filedialog.askopenfilename(
            title="选择 Verilog 文件",
            filetypes=[("Verilog 文件", "*.v *.sv"), ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.pipeline_file.set(path)
            # 自动填充输出文件名
            base, ext = os.path.splitext(path)
            self.pipeline_output.set(base + "_hardened" + ext)

    def _pipeline_browse_out(self):
        path = filedialog.asksaveasfilename(
            title="保存加固后文件",
            defaultextension=".v",
            filetypes=[("Verilog 文件", "*.v *.sv"), ("所有文件", "*.*")],
        )
        if path:
            self.pipeline_output.set(path)

    def _pipeline_run(self):
        in_file = self.pipeline_file.get()
        out_file = self.pipeline_output.get()
        if not in_file or not os.path.isfile(in_file):
            messagebox.showerror("错误", "请先选择有效的输入 Verilog 文件")
            return
        if not out_file:
            messagebox.showerror("错误", "请指定输出文件路径")
            return

        # 收集启用的策略
        enabled = [k for k, v in self.strategy_vars.items() if v.get()]
        if not enabled:
            messagebox.showerror("错误", "请至少选择一个加固策略")
            return

        self._clear_output(self.pipeline_output_text)
        self._set_status("加固管线运行中...", "执行加固管线")

        def task():
            self._append_output(self.pipeline_output_text,
                                f"[INFO] 输入文件: {in_file}")
            self._append_output(self.pipeline_output_text,
                                f"[INFO] 输出文件: {out_file}")
            self._append_output(self.pipeline_output_text,
                                f"[INFO] 启用策略: {', '.join(enabled)}")
            self._append_output(self.pipeline_output_text, "")

            try:
                # 动态导入 hardening_pipeline
                sys.path.insert(0, SCRIPT_DIR)
                from hardening_pipeline import HardeningPipeline

                pipeline = HardeningPipeline(optimization_goal='balanced')

                # 步骤 1: 加载
                self._append_output(self.pipeline_output_text, "[1/5] 加载设计...")
                if not pipeline.load_design(in_file):
                    self._append_output(self.pipeline_output_text,
                                        "[错误] 加载设计失败", "red")
                    self._set_status("加固失败")
                    return

                # 步骤 2: 分析
                self._append_output(self.pipeline_output_text, "[2/5] 分析设计...")
                info = pipeline.analyze()
                for name, meta in info.items():
                    self._append_output(self.pipeline_output_text,
                                        f"    - {name:20s} type={meta['type']:10s} width={meta['width']}")

                # 步骤 3: 策略路由
                self._append_output(self.pipeline_output_text, "[3/5] 策略路由...")
                pipeline.route_strategies()

                # 步骤 4: 变换
                self._append_output(self.pipeline_output_text, "[4/5] AST 变换...")
                pipeline.transform()

                # 步骤 5: 输出
                self._append_output(self.pipeline_output_text, "[5/5] 输出加固代码...")
                pipeline.output(out_file)

                # 摘要
                self._append_output(self.pipeline_output_text, "")
                self._append_output(self.pipeline_output_text,
                                    "=" * 50, "green")
                self._append_output(self.pipeline_output_text,
                                    "  加固完成！", "green")
                self._append_output(self.pipeline_output_text,
                                    f"  输出: {out_file}", "green")
                self._append_output(self.pipeline_output_text,
                                    "=" * 50, "green")

                self._set_status("加固完成", f"加固 {os.path.basename(in_file)}")

                # 运行 iverilog 检查
                self._append_output(self.pipeline_output_text, "")
                self._append_output(self.pipeline_output_text,
                                    "[可选] 运行 iverilog 编译检查...")
                if pipeline.run_iverilog_check(out_file):
                    self._append_output(self.pipeline_output_text,
                                        "✅ 编译检查通过", "green")
                else:
                    self._append_output(self.pipeline_output_text,
                                        "⚠️ 编译检查失败或不可用", "orange")

            except Exception as e:
                self._append_output(self.pipeline_output_text,
                                    f"[错误] {e}", "red")
                self._set_status("加固失败")

        threading.Thread(target=task, daemon=True).start()

    # ========================================================
    # Tab 2: 测试运行 (Test Runner)
    # ========================================================
    def _build_tab_testrunner(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 测试运行 (Test Runner) ")

        # -- 套件选择 --
        f_suite = ttk.LabelFrame(tab, text="测试套件选择", padding=5)
        f_suite.pack(fill=tk.X, pady=(5, 0), padx=5)

        self.test_suite_vars = {}
        suites = [
            ('cnt_comp',     'cnt_comp — 计数器比较器测试'),
            ('parity',       'Parity — 奇偶校验测试'),
            ('dice',         'DICE — 4 节点存储测试'),
            ('ecc',          'ECC — 纠错码测试'),
            ('mixed_ecc',    'mixed_ecc — 混合 ECC 设计测试'),
            ('voter_debug',  'voter_debug — 表决器调试日志测试'),
            ('python_unit',  'python_unit — Python 单元测试'),
        ]
        for key, label in suites:
            var = tk.BooleanVar(value=(key == 'cnt_comp'))
            self.test_suite_vars[key] = var
            cb = ttk.Checkbutton(f_suite, text=label, variable=var)
            cb.pack(anchor=tk.W, padx=10)
            add_tooltip(cb, f"运行 {label.split('—')[0].strip()} 测试套件")

        # -- 操作按钮 --
        f_btn = ttk.Frame(tab)
        f_btn.pack(fill=tk.X, pady=5, padx=5)
        btn_run_sel = ttk.Button(f_btn, text="运行选定套件",
                                 command=self._test_run_selected)
        btn_run_sel.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_run_sel, "运行勾选的测试套件")

        btn_run_all = ttk.Button(f_btn, text="运行全部",
                                 command=self._test_run_all)
        btn_run_all.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_run_all, "运行所有测试套件")

        # -- 输出区 --
        self.test_output_text = self._add_output_area(tab, height=12)

        # 配置颜色 tag
        self.test_output_text.tag_config("green", foreground="#6a9955")
        self.test_output_text.tag_config("red", foreground="#f44747")
        self.test_output_text.tag_config("orange", foreground="#ce9178")

        # -- 摘要栏 --
        f_summary = ttk.Frame(tab)
        f_summary.pack(fill=tk.X, pady=(2, 5), padx=5)
        self._make_label(f_summary, "测试摘要:").pack(side=tk.LEFT, padx=(0, 5))
        self.test_summary_var = tk.StringVar(value="就绪")
        lbl_summary = ttk.Label(f_summary, textvariable=self.test_summary_var,
                                 font=("微软雅黑", 9, "bold"))
        lbl_summary.pack(side=tk.LEFT)

    def _test_run_selected(self):
        selected = [k for k, v in self.test_suite_vars.items() if v.get()]
        if not selected:
            messagebox.showwarning("提示", "请至少选择一个测试套件")
            return
        self._run_tests(selected)

    def _test_run_all(self):
        self._run_tests(list(self.test_suite_vars.keys()))

    def _run_tests(self, suite_keys):
        self._clear_output(self.test_output_text)
        self.test_summary_var.set("运行中...")
        self._set_status("测试运行中...", "运行测试")

        def task():
            total = len(suite_keys)
            passed = 0
            failed = 0

            for key in suite_keys:
                self._append_output(self.test_output_text,
                                    f"\n{'=' * 60}")
                self._append_output(self.test_output_text,
                                    f"  运行: {key}")
                self._append_output(self.test_output_text,
                                    f"{'=' * 60}")

                if key == 'voter_debug':
                    rc, out, err = run_subprocess(
                        f'"{sys.executable}" -c "import sys; sys.path.insert(0, {repr(SCRIPT_DIR)}); '
                        f'from run_regression import test_voter_debug_regression; '
                        f'print(\'PASS\' if test_voter_debug_regression() else \'FAIL\')"'
                    )
                elif key == 'python_unit':
                    rc, out, err = run_subprocess(
                        f'"{sys.executable}" -c "import sys; sys.path.insert(0, {repr(SCRIPT_DIR)}); '
                        f'from run_regression import test_python_regression; '
                        f'print(\'PASS\' if test_python_regression() else \'FAIL\')"'
                    )
                elif key == 'mixed_ecc':
                    # 运行 mixed_design_ecc 仿真
                    tb_file = os.path.join(TEST_MOCK_DIR, "tb_mixed_design_ecc.v")
                    if os.path.exists(tb_file):
                        # 使用 iverilog 编译运行
                        sim_dir = os.path.join(SCRIPT_DIR, 'sim')
                        iverilog = r'D:\software\pango\iverilog\bin\iverilog.exe'
                        vvp = r'D:\software\pango\iverilog\bin\vvp.exe'
                        vvp_out = os.path.join(sim_dir, f'tb_{key}.vvp')
                        cmd_comp = f'cd /d "{sim_dir}" && "{iverilog}" -o "{vvp_out}" "{tb_file}"'
                        rc1, out1, err1 = run_subprocess(cmd_comp)
                        if rc1 == 0:
                            cmd_run = f'cd /d "{sim_dir}" && "{vvp}" "{vvp_out}"'
                            rc, out, err = run_subprocess(cmd_run)
                        else:
                            out, err = out1, err1
                            rc = rc1
                    else:
                        out, err = "", f"测试文件不存在: {tb_file}"
                        rc = -1
                else:
                    # cnt_comp, parity, dice, ecc — 使用 iverilog 直接运行
                    tb_map = {
                        'cnt_comp': 'tb_cnt_comp.v',
                        'parity':   'tb_parity.v',
                        'dice':     'tb_dice.v',
                        'ecc':      'tb_ecc.v',
                    }
                    tb_file = tb_map.get(key)
                    if not tb_file:
                        self._append_output(self.test_output_text,
                                            f"[跳过] 未知套件: {key}", "orange")
                        continue

                    tb_path = os.path.join(TEST_MOCK_DIR, tb_file)
                    if not os.path.exists(tb_path):
                        # 尝试 sim 目录
                        tb_path = os.path.join(SCRIPT_DIR, 'sim', tb_file)
                    if not os.path.exists(tb_path):
                        self._append_output(self.test_output_text,
                                            f"[错误] 找不到 {tb_file}", "red")
                        failed += 1
                        continue

                    sim_dir = os.path.join(SCRIPT_DIR, 'sim')
                    iverilog = r'D:\software\pango\iverilog\bin\iverilog.exe'
                    vvp = r'D:\software\pango\iverilog\bin\vvp.exe'
                    vvp_out = os.path.join(sim_dir, f'tb_{key}.vvp')
                    cmd_comp = f'cd /d "{sim_dir}" && "{iverilog}" -o "{vvp_out}" "{tb_path}"'
                    rc1, out1, err1 = run_subprocess(cmd_comp)
                    if rc1 == 0:
                        cmd_run = f'cd /d "{sim_dir}" && "{vvp}" "{vvp_out}"'
                        rc, out, err = run_subprocess(cmd_run)
                    else:
                        out, err = out1, err1
                        rc = rc1

                # 分析结果
                combined = (out or "") + (err or "")
                is_pass = 'PASS' in combined and 'FAIL' not in combined
                # 更细致的判断
                if rc == 0 and is_pass:
                    status = "PASS"
                    color = "green"
                    passed += 1
                elif rc != 0:
                    status = "FAIL (编译错误)"
                    color = "red"
                    failed += 1
                else:
                    status = "FAIL"
                    color = "red"
                    failed += 1

                self._append_output(self.test_output_text,
                                    f"结果: {status}", color)

                # 显示输出摘要
                lines = combined.split('\n')
                summary_lines = [l for l in lines if l.strip() and
                                 any(kw in l for kw in
                                     ['PASS', 'FAIL', 'Test', '测试', '通过',
                                      '错误', 'error', 'Error', 'ERROR',
                                      '[TMR-VOTER]'])]
                for l in summary_lines[:20]:
                    lc = "green" if 'PASS' in l else ("red" if 'FAIL' in l or '错误' in l else None)
                    self._append_output(self.test_output_text, f"  {l.strip()}", lc)

            # 汇总
            self._append_output(self.test_output_text, "")
            self._append_output(self.test_output_text, "=" * 50)
            total_run = passed + failed
            summary = f"总计: {total_run} 套件 | ✅ {passed} 通过 | ❌ {failed} 失败"
            self._append_output(self.test_output_text, summary,
                                "green" if failed == 0 else "red")
            self._append_output(self.test_output_text, "=" * 50)

            self.test_summary_var.set(summary)
            self._set_status("测试完成", f"通过 {passed}/{total_run}")

        threading.Thread(target=task, daemon=True).start()

    # ========================================================
    # Tab 3: 信号扫描 (Signal Scan)
    # ========================================================
    def _build_tab_signalscan(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 信号扫描 (Signal Scan) ")

        # -- 配置区 --
        f_cfg = ttk.LabelFrame(tab, text="扫描配置", padding=5)
        f_cfg.pack(fill=tk.X, pady=(5, 0), padx=5)

        row1 = ttk.Frame(f_cfg)
        row1.pack(fill=tk.X, pady=2)
        self._make_label(row1, "选择 RTL 目录:").pack(side=tk.LEFT)
        ent_dir = ttk.Entry(row1, textvariable=self.scan_dir, width=60)
        ent_dir.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_dir = ttk.Button(row1, text="选择目录...", command=self._scan_browse_dir)
        btn_dir.pack(side=tk.LEFT)
        add_tooltip(btn_dir, "选择包含 Verilog/SystemVerilog 源文件的目录进行扫描")

        row2 = ttk.Frame(f_cfg)
        row2.pack(fill=tk.X, pady=2)
        self._make_label(row2, "扇入/扇出阈值:").pack(side=tk.LEFT)
        spn = ttk.Spinbox(row2, from_=1, to=20, textvariable=self.scan_threshold,
                          width=5)
        spn.pack(side=tk.LEFT, padx=5)
        add_tooltip(spn, "活跃度（扇入+扇出）超过此值的信号被列为候选")

        # -- 操作按钮 --
        f_btn = ttk.Frame(tab)
        f_btn.pack(fill=tk.X, pady=5, padx=5)
        btn_scan = ttk.Button(f_btn, text="开始扫描",
                              command=self._scan_run)
        btn_scan.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_scan, "扫描目录中所有未加固的高扇出信号")

        btn_export = ttk.Button(f_btn, text="导出报告",
                                command=self._scan_export)
        btn_export.pack(side=tk.LEFT)
        add_tooltip(btn_export, "将扫描结果导出为 Markdown 报告文件")

        # -- 结果表格 --
        f_result = ttk.LabelFrame(tab, text="扫描结果", padding=5)
        f_result.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        columns = ('signal', 'width', 'activity', 'strategy', 'priority')
        self.scan_tree = ttk.Treeview(f_result, columns=columns,
                                       show='headings', height=10)
        self.scan_tree.heading('signal', text='信号名')
        self.scan_tree.heading('width', text='位宽')
        self.scan_tree.heading('activity', text='活跃度')
        self.scan_tree.heading('strategy', text='推荐策略')
        self.scan_tree.heading('priority', text='优先级')

        self.scan_tree.column('signal', width=200)
        self.scan_tree.column('width', width=60, anchor=tk.CENTER)
        self.scan_tree.column('activity', width=80, anchor=tk.CENTER)
        self.scan_tree.column('strategy', width=150, anchor=tk.CENTER)
        self.scan_tree.column('priority', width=80, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(f_result, orient=tk.VERTICAL,
                                   command=self.scan_tree.yview)
        self.scan_tree.configure(yscrollcommand=scrollbar.set)
        self.scan_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._scan_results_data = []

    def _scan_browse_dir(self):
        path = filedialog.askdirectory(
            title="选择 RTL 目录",
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.scan_dir.set(path)

    def _scan_run(self):
        scan_dir = self.scan_dir.get()
        if not scan_dir or not os.path.isdir(scan_dir):
            messagebox.showerror("错误", "请选择有效的 RTL 目录")
            return

        # 清空表格
        for item in self.scan_tree.get_children():
            self.scan_tree.delete(item)
        self._scan_results_data = []
        self._set_status("信号扫描中...", f"扫描 {scan_dir}")

        threshold = self.scan_threshold.get()

        def task():
            # 使用 scan_high_fanout_signals.py 的 --output 参数
            import tempfile
            tmp_file = os.path.join(tempfile.gettempdir(),
                                    f"scan_report_{int(time.time())}.md")
            rc, out, err = run_python_script(
                'scan_high_fanout_signals.py',
                f'--dir "{scan_dir}" --threshold {threshold} --output "{tmp_file}"'
            )

            if rc != 0:
                self._set_status("扫描失败")
                messagebox.showerror("扫描错误",
                                     f"扫描脚本返回错误:\n{err[:500]}")
                return

            # 从临时文件读取结果
            if os.path.exists(tmp_file):
                with open(tmp_file, 'r', encoding='utf-8') as f:
                    report = f.read()
                self._parse_scan_report_to_tree(report)
                os.unlink(tmp_file)

            self._set_status(f"扫描完成: {len(self._scan_results_data)} 个候选信号",
                             "信号扫描完成")

        threading.Thread(target=task, daemon=True).start()

    def _parse_scan_report_to_tree(self, report_text):
        """解析 Markdown 报告并填充到 Treeview"""
        # 匹配表格行: | 优先级 | 信号名 | 位宽 | 扇入 | 扇出 | 活跃度 | 推荐策略 | ...
        table_pattern = re.compile(
            r'\|\s*([🔴🟡🟢]?\s*[高低中]?)\s*\|\s*(\w+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\w+)\s*\|',
            re.MULTILINE
        )
        rows = []
        for m in table_pattern.finditer(report_text):
            priority = m.group(1).strip()
            signal = m.group(2)
            width = m.group(3)
            activity = m.group(6)
            strategy = m.group(7).strip()
            rows.append((signal, width, activity, strategy, priority))

        # 去重（按信号名）
        seen = set()
        for row in rows:
            if row[0] not in seen:
                seen.add(row[0])
                self._scan_results_data.append(row)
                self.scan_tree.insert('', tk.END, values=row)

    def _scan_export(self):
        if not self._scan_results_data:
            messagebox.showwarning("提示", "没有可导出的扫描结果。请先运行扫描。")
            return

        path = filedialog.asksaveasfilename(
            title="导出报告",
            defaultextension=".md",
            filetypes=[("Markdown 文件", "*.md"), ("所有文件", "*.*")],
            initialdir=REPORTS_DIR,
        )
        if not path:
            return

        try:
            lines = [
                "# 高扇出信号加固建议报告",
                "",
                f"## 扫描配置",
                f"- 扫描目录: {self.scan_dir.get()}",
                f"- 阈值: {self.scan_threshold.get()}",
                f"- 导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "## 候选信号列表",
                "",
                "| 优先级 | 信号名 | 位宽 | 活跃度 | 推荐策略 |",
                "|:------|:-------|:----:|:------:|:---------|",
            ]
            for row in self._scan_results_data:
                lines.append(f"| {row[4]} | {row[0]} | {row[1]} | {row[2]} | {row[3]} |")

            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))

            self._set_status(f"报告已导出: {path}", "导出扫描报告")
            messagebox.showinfo("导出成功", f"报告已保存至:\n{path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ========================================================
    # Tab 4: AIG 分析 (AIG Analysis)
    # ========================================================
    def _build_tab_aig(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" AIG 分析 (AIG Analysis) ")

        # -- 文件选择 --
        f_file = ttk.LabelFrame(tab, text="AIG 文件", padding=5)
        f_file.pack(fill=tk.X, pady=(5, 0), padx=5)

        row1 = ttk.Frame(f_file)
        row1.pack(fill=tk.X, pady=2)
        self._make_label(row1, "选择 AIG 文件:").pack(side=tk.LEFT)
        ent_aig = ttk.Entry(row1, textvariable=self.aig_file, width=60)
        ent_aig.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_aig = ttk.Button(row1, text="浏览...", command=self._aig_browse)
        btn_aig.pack(side=tk.LEFT)
        add_tooltip(btn_aig, "选择 .aig 格式的 AIG 文件进行分析")

        # -- 操作按钮 --
        f_btn = ttk.Frame(tab)
        f_btn.pack(fill=tk.X, pady=5, padx=5)
        btn_gen = ttk.Button(f_btn, text="生成模拟 AIG",
                             command=self._aig_generate_mock)
        btn_gen.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_gen, "调用 gen_mock_aig.py 生成模拟 AIG 文件用于演示")

        btn_parse = ttk.Button(f_btn, text="解析并分析",
                               command=self._aig_analyze)
        btn_parse.pack(side=tk.LEFT)
        add_tooltip(btn_parse, "解析 AIG 文件并显示统计、高扇出节点等信息")

        # -- 结果显示 --
        f_result = ttk.LabelFrame(tab, text="分析结果", padding=5)
        f_result.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # 统计摘要
        self.aig_stats_var = tk.StringVar(value="等待分析...")
        lbl_stats = ttk.Label(f_result, textvariable=self.aig_stats_var,
                               font=("Consolas", 9),
                               background="#1e1e1e", foreground="#d4d4d4",
                               anchor=tk.NW, justify=tk.LEFT,
                               relief=tk.SUNKEN, padding=5)
        lbl_stats.pack(fill=tk.X, pady=(0, 5))

        # 详细输出
        self.aig_output_text = self._add_output_area(f_result, height=10)

    def _aig_browse(self):
        path = filedialog.askopenfilename(
            title="选择 AIG 文件",
            filetypes=[("AIG 文件", "*.aig"), ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.aig_file.set(path)

    def _aig_generate_mock(self):
        self._clear_output(self.aig_output_text)
        self._set_status("生成模拟 AIG...", "生成模拟 AIG")

        def task():
            output_path = os.path.join(TEST_MOCK_DIR, "synth_output.aig")
            rc, out, err = run_python_script(
                os.path.join('sim', 'formal_test', 'gen_mock_aig.py'),
                f'"{output_path}"'
            )
            combined = (out or "") + (err or "")
            self._append_output(self.aig_output_text, combined)
            if rc == 0 and os.path.exists(output_path):
                self.aig_file.set(output_path)
                self._append_output(self.aig_output_text,
                                    f"\n✅ 模拟 AIG 已生成: {output_path}", "green")
                self._set_status("模拟 AIG 生成完成", "生成模拟 AIG")
            else:
                self._append_output(self.aig_output_text,
                                    f"\n❌ 生成失败 (rc={rc})", "red")
                self._set_status("AIG 生成失败")

        threading.Thread(target=task, daemon=True).start()

    def _aig_analyze(self):
        aig_path = self.aig_file.get()
        if not aig_path or not os.path.isfile(aig_path):
            messagebox.showerror("错误", "请先选择或生成 AIG 文件")
            return

        self._clear_output(self.aig_output_text)
        self._set_status("AIG 分析中...", "分析 AIG 文件")

        def task():
            rc, out, err = run_python_script(
                os.path.join('sim', 'formal_test', 'demo_aig_analysis.py'),
                f'"{aig_path}"'
            )
            combined = (out or "") + (err or "")
            self.aig_stats_var.set(
                f"文件: {os.path.basename(aig_path)}\n"
                f"大小: {os.path.getsize(aig_path):,} 字节\n"
                f"状态: {'✅ 分析成功' if rc == 0 else '❌ 分析失败'}"
            )
            # 输出到文本区域
            for line in combined.split('\n'):
                if line.strip():
                    color = None
                    if '错误' in line or 'Error' in line or 'error' in line:
                        color = "red"
                    elif '提示' in line or '脆弱性' in line:
                        color = "orange"
                    self._append_output(self.aig_output_text, line, color)

            self._set_status("AIG 分析完成" if rc == 0 else "AIG 分析失败",
                             "AIG 分析")

        threading.Thread(target=task, daemon=True).start()

    # ========================================================
    # Tab 5: 层次化加固 (Hierarchical Hardening)
    # ========================================================
    def _build_tab_hierarchical(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 层次化加固 (Hierarchical) ")

        top_row = ttk.Frame(tab)
        top_row.pack(fill=tk.X, padx=5, pady=(5, 0))

        self._make_label(top_row, "RTL 文件:", width=10).pack(side=tk.LEFT)
        self.hier_rtl_file = tk.StringVar()
        ent_rtl = ttk.Entry(top_row, textvariable=self.hier_rtl_file)
        ent_rtl.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_rtl = ttk.Button(top_row, text="浏览...", command=self._hier_browse_rtl, style='Browse.TButton')
        btn_rtl.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_rtl, "选择顶层 RTL 文件")
        btn_load = ttk.Button(top_row, text="加载设计", command=self._hier_load_design, style='Action.TButton')
        btn_load.pack(side=tk.LEFT)
        add_tooltip(btn_load, "加载 RTL 设计并提取层次结构")

        main_area = ttk.Frame(tab)
        main_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tree_frame = ttk.LabelFrame(main_area, text="模块层次结构", padding=5)
        tree_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        self.hier_tree = ttk.Treeview(tree_frame, columns=('strategy', 'regs'), show='tree headings')
        self.hier_tree.heading('#0', text='模块名称')
        self.hier_tree.heading('strategy', text='加固策略')
        self.hier_tree.heading('regs', text='寄存器数')
        self.hier_tree.column('#0', width=200)
        self.hier_tree.column('strategy', width=120)
        self.hier_tree.column('regs', width=80)

        scroll_tree = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.hier_tree.yview)
        self.hier_tree.configure(yscrollcommand=scroll_tree.set)
        scroll_tree.pack(side=tk.RIGHT, fill=tk.Y)
        self.hier_tree.pack(fill=tk.BOTH, expand=True)
        self.hier_tree.bind('<<TreeviewSelect>>', self._hier_on_select)

        config_frame = ttk.LabelFrame(main_area, text="策略配置", padding=8, width=280)
        config_frame.pack(side=tk.RIGHT, fill=tk.Y)
        config_frame.pack_propagate(False)

        self.hier_selected_module = tk.StringVar(value="未选择")
        lbl_module = ttk.Label(config_frame, text="选中模块:", font=("微软雅黑", 9))
        lbl_module.pack(anchor=tk.W)
        lbl_module_val = ttk.Label(config_frame, textvariable=self.hier_selected_module,
                                   font=("微软雅黑", 10, "bold"), foreground="#1976D2")
        lbl_module_val.pack(anchor=tk.W, pady=(0, 8))

        ttk.Label(config_frame, text="加固策略:", font=("微软雅黑", 9)).pack(anchor=tk.W)
        self.hier_strategy = ttk.Combobox(config_frame, state='readonly', width=22)
        self.hier_strategy['values'] = ('tmr', 'dice', 'ecc', 'parity', 'cnt_comp',
                                       'onehot_fsm', 'watchdog', 'parity_bus')
        self.hier_strategy.set('tmr')
        self.hier_strategy.pack(anchor=tk.W, pady=(0, 8))

        btn_apply = ttk.Button(config_frame, text="应用策略", command=self._hier_apply_strategy, style='Action.TButton')
        btn_apply.pack(fill=tk.X, pady=(0, 4))
        add_tooltip(btn_apply, "将策略应用到选中模块")

        btn_apply_all = ttk.Button(config_frame, text="全部应用默认", command=self._hier_apply_all_default, style='Action.TButton')
        btn_apply_all.pack(fill=tk.X, pady=(0, 8))
        add_tooltip(btn_apply_all, "将默认策略应用到所有模块")

        ttk.Separator(config_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        ttk.Label(config_frame, text="策略映射:", font=("微软雅黑", 9)).pack(anchor=tk.W, pady=(5, 2))
        self.hier_strategy_text = scrolledtext.ScrolledText(config_frame, height=8,
                                                            font=("Consolas", 9))
        self.hier_strategy_text.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        bottom_bar = ttk.Frame(tab)
        bottom_bar.pack(fill=tk.X, padx=5, pady=(0, 5))

        btn_run = ttk.Button(bottom_bar, text="运行层次化加固", command=self._hier_run_hardening, style='Run.TButton')
        btn_run.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_run, "根据模块级策略配置运行加固")

        btn_export = ttk.Button(bottom_bar, text="导出策略配置", command=self._hier_export_config, style='Export.TButton')
        btn_export.pack(side=tk.LEFT)
        add_tooltip(btn_export, "导出当前策略配置为 JSON 文件")

        self.hier_status_var = tk.StringVar(value="就绪")
        lbl_status = ttk.Label(bottom_bar, textvariable=self.hier_status_var,
                               font=("微软雅黑", 9), foreground="#388E3C")
        lbl_status.pack(side=tk.RIGHT)

        self._hier_design_info = {}
        self._hier_module_strategies = {}

    def _hier_browse_rtl(self):
        path = filedialog.askopenfilename(
            title="选择 RTL 文件",
            filetypes=[("Verilog 文件", "*.v"), ("SystemVerilog 文件", "*.sv"),
                       ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.hier_rtl_file.set(path)

    def _hier_load_design(self):
        rtl_path = self.hier_rtl_file.get()
        if not rtl_path or not os.path.isfile(rtl_path):
            messagebox.showerror("错误", "请选择有效的 RTL 文件")
            return

        self._set_status("加载设计中...", f"分析 {os.path.basename(rtl_path)}")

        def task():
            try:
                sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sim', 'formal_test'))
                from rag_integration import analyze_design_for_hardening

                analysis = analyze_design_for_hardening(rtl_path, recursive=True)

                self._hier_design_info = analysis
                self._hier_module_strategies = {}

                for item in self.hier_tree.get_children():
                    self.hier_tree.delete(item)

                top_name = analysis.get('module_name', 'top')
                top_regs = len(analysis.get('registers', []))
                top_id = self.hier_tree.insert('', tk.END, text=top_name,
                                                values=('tmr', top_regs))
                self._hier_module_strategies[top_name] = 'tmr'

                submodules = analysis.get('submodules', {})
                for sub_name, sub_info in submodules.items():
                    sub_regs = len(sub_info.get('registers', []))
                    self.hier_tree.insert(top_id, tk.END, text=sub_name,
                                            values=('tmr', sub_regs))
                    self._hier_module_strategies[sub_name] = 'tmr'

                self.hier_status_var.set(f"已加载: {top_name} ({len(submodules)} 个子模块)")
                self._update_strategy_text()

            except Exception as e:
                self.hier_status_var.set(f"加载失败: {str(e)}")
                messagebox.showerror("加载错误", f"分析 RTL 文件时出错:\n{str(e)}")

        threading.Thread(target=task, daemon=True).start()

    def _hier_on_select(self, event=None):
        selection = self.hier_tree.selection()
        if selection:
            item = selection[0]
            module_name = self.hier_tree.item(item, 'text')
            current_strategy = self._hier_module_strategies.get(module_name, 'tmr')
            self.hier_selected_module.set(module_name)
            self.hier_strategy.set(current_strategy)

    def _hier_apply_strategy(self):
        selection = self.hier_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个模块")
            return

        item = selection[0]
        module_name = self.hier_tree.item(item, 'text')
        strategy = self.hier_strategy.get()

        self._hier_module_strategies[module_name] = strategy
        self.hier_tree.set(item, 'strategy', strategy)

        self._update_strategy_text()
        self._set_status(f"已为 {module_name} 应用策略: {strategy}")

    def _hier_apply_all_default(self):
        default_strategy = self.hier_strategy.get()
        for item in self.hier_tree.get_children():
            self._hier_tree_recursive_apply(item, default_strategy)

        self._update_strategy_text()
        self._set_status(f"已为所有模块应用默认策略: {default_strategy}")

    def _hier_tree_recursive_apply(self, parent_item, strategy):
        module_name = self.hier_tree.item(parent_item, 'text')
        self._hier_module_strategies[module_name] = strategy
        self.hier_tree.set(parent_item, 'strategy', strategy)

        for child in self.hier_tree.get_children(parent_item):
            self._hier_tree_recursive_apply(child, strategy)

    def _update_strategy_text(self):
        self.hier_strategy_text.delete("1.0", tk.END)
        import json
        config = {
            'rtl_file': self.hier_rtl_file.get(),
            'module_strategies': self._hier_module_strategies,
        }
        self.hier_strategy_text.insert("1.0", json.dumps(config, indent=2, ensure_ascii=False))

    def _hier_run_hardening(self):
        rtl_path = self.hier_rtl_file.get()
        if not rtl_path or not os.path.isfile(rtl_path):
            messagebox.showerror("错误", "请先加载 RTL 设计")
            return

        if not self._hier_module_strategies:
            messagebox.showerror("错误", "请先配置模块策略")
            return

        self._set_status("运行层次化加固中...", "层次化加固")

        def task():
            try:
                sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sim', 'formal_test'))
                from rag_integration import analyze_design_for_hardening, \
                    allocate_strategy_per_module, apply_module_strategies

                analysis = analyze_design_for_hardening(rtl_path, recursive=True)
                analysis_with_strategy = allocate_strategy_per_module(
                    analysis,
                    module_strategies=self._hier_module_strategies,
                )

                with open(rtl_path, 'r', encoding='utf-8') as f:
                    rtl_content = f.read()

                hardened_content = apply_module_strategies(rtl_content, analysis_with_strategy)

                base_name = os.path.splitext(os.path.basename(rtl_path))[0]
                output_path = os.path.join(REPORTS_DIR, f"{base_name}_hierarchical_hardened.v")

                os.makedirs(REPORTS_DIR, exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(hardened_content)

                self.hier_status_var.set(f"加固完成! 输出: {os.path.basename(output_path)}")
                self._set_status("层次化加固完成", f"已生成: {output_path}")

                messagebox.showinfo("加固完成", f"层次化加固已完成!\n输出文件:\n{output_path}")

            except Exception as e:
                self.hier_status_var.set(f"加固失败: {str(e)}")
                messagebox.showerror("加固错误", f"运行层次化加固时出错:\n{str(e)}")

        threading.Thread(target=task, daemon=True).start()

    def _hier_export_config(self):
        if not self._hier_module_strategies:
            messagebox.showwarning("提示", "没有可导出的策略配置")
            return

        path = filedialog.asksaveasfilename(
            title="导出策略配置",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialdir=REPORTS_DIR,
        )
        if not path:
            return

        import json
        config = {
            'rtl_file': self.hier_rtl_file.get(),
            'module_strategies': self._hier_module_strategies,
            'export_time': time.strftime('%Y-%m-%d %H:%M:%S'),
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        self._set_status(f"配置已导出: {path}", "导出策略配置")
        messagebox.showinfo("导出成功", f"策略配置已保存至:\n{path}")

    # ========================================================
    # Tab 6: 策略推荐 (Strategy Recommendation)
    # ========================================================
    def _build_tab_strategy_recommend(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 策略推荐 (Recommendation) ")

        f_input = ttk.LabelFrame(tab, text="配置", padding=8)
        f_input.pack(fill=tk.X, padx=5, pady=(5, 0))

        row = ttk.Frame(f_input)
        row.pack(fill=tk.X, pady=2)

        self.rec_rtl_file = tk.StringVar()
        self._make_label(row, "RTL 文件:", width=10).pack(side=tk.LEFT)
        ent_rtl = ttk.Entry(row, textvariable=self.rec_rtl_file)
        ent_rtl.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_rtl = ttk.Button(row, text="浏览...", command=self._rec_browse_rtl, style='Browse.TButton')
        btn_rtl.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_rtl, "选择 RTL 文件进行策略推荐")

        self._make_label(row, "优化目标:", width=10).pack(side=tk.LEFT)
        self.rec_goal = ttk.Combobox(row, state='readonly', width=18)
        self.rec_goal['values'] = ('balanced', 'reliability', 'area', 'performance')
        self.rec_goal.set('balanced')
        self.rec_goal.pack(side=tk.LEFT, padx=5)
        add_tooltip(self.rec_goal, "选择策略优化目标")

        btn_recommend = ttk.Button(row, text="生成推荐", command=self._rec_generate, style='Recommend.TButton')
        btn_recommend.pack(side=tk.LEFT)
        add_tooltip(btn_recommend, "分析设计并生成策略推荐")

        f_result = ttk.LabelFrame(tab, text="推荐结果", padding=5)
        f_result.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ('module', 'type', 'strategy', 'score', 'alternatives')
        self.rec_tree = ttk.Treeview(f_result, columns=columns, show='headings', height=12)
        self.rec_tree.heading('module', text='模块名称')
        self.rec_tree.heading('type', text='模块类型')
        self.rec_tree.heading('strategy', text='推荐策略')
        self.rec_tree.heading('score', text='评分')
        self.rec_tree.heading('alternatives', text='备选策略')

        self.rec_tree.column('module', width=180)
        self.rec_tree.column('type', width=100)
        self.rec_tree.column('strategy', width=130)
        self.rec_tree.column('score', width=80, anchor=tk.CENTER)
        self.rec_tree.column('alternatives', width=300)

        scroll_tree = ttk.Scrollbar(f_result, orient=tk.VERTICAL, command=self.rec_tree.yview)
        self.rec_tree.configure(yscrollcommand=scroll_tree.set)
        self.rec_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_tree.pack(side=tk.RIGHT, fill=tk.Y)

        f_status = ttk.Frame(f_result)
        f_status.pack(fill=tk.X, pady=(5, 0))

        self.rec_status_var = tk.StringVar(value="就绪")
        lbl_status = ttk.Label(f_status, textvariable=self.rec_status_var,
                               font=("微软雅黑", 9), foreground="#6A1B9A")
        lbl_status.pack(side=tk.LEFT)

        self._rec_recommendations = {}

    def _rec_browse_rtl(self):
        path = filedialog.askopenfilename(
            title="选择 RTL 文件",
            filetypes=[("Verilog 文件", "*.v"), ("SystemVerilog 文件", "*.sv"),
                       ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.rec_rtl_file.set(path)

    def _rec_generate(self):
        rtl_path = self.rec_rtl_file.get()
        if not rtl_path or not os.path.isfile(rtl_path):
            messagebox.showerror("错误", "请选择有效的 RTL 文件")
            return

        self._set_status("生成策略推荐中...", "策略推荐")

        def task():
            try:
                sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sim', 'formal_test'))
                from rag_integration import analyze_design_for_hardening, recommend_strategies, explain_recommendation

                analysis = analyze_design_for_hardening(rtl_path, recursive=True)
                optimization_goal = self.rec_goal.get()
                result = recommend_strategies(analysis, optimization_goal)

                for item in self.rec_tree.get_children():
                    self.rec_tree.delete(item)

                self._rec_recommendations = {}
                for module_name, rec in result.get('recommendations', {}).items():
                    top_strategies = [s['strategy'] for s in rec.get('top_strategies', [])]
                    alternatives = ', '.join(top_strategies[1:]) if len(top_strategies) > 1 else '-'
                    self.rec_tree.insert('', tk.END, values=(
                        module_name,
                        rec.get('module_type', 'unknown'),
                        rec.get('recommended_strategy', 'unknown'),
                        f"{rec.get('top_strategies', [{}])[0].get('score', 0):.2f}",
                        alternatives,
                    ))
                    self._rec_recommendations[module_name] = rec

                self.rec_status_var.set(f"推荐完成: {len(self._rec_recommendations)} 个模块")
                self._set_status("策略推荐完成", f"基于 {optimization_goal} 目标")

            except Exception as e:
                self.rec_status_var.set(f"推荐失败: {str(e)}")
                messagebox.showerror("推荐错误", f"生成策略推荐时出错:\n{str(e)}")

        threading.Thread(target=task, daemon=True).start()

    # ========================================================
    # Tab 7: 加固效果可视化 (Visualization)
    # ========================================================
    def _build_tab_visualization(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 效果可视化 (Visualization) ")

        f_input = ttk.LabelFrame(tab, text="配置", padding=8)
        f_input.pack(fill=tk.X, padx=5, pady=(5, 0))

        row1 = ttk.Frame(f_input)
        row1.pack(fill=tk.X, pady=2)
        self._make_label(row1, "RTL 文件:", width=10).pack(side=tk.LEFT)
        self.vis_rtl_file = tk.StringVar()
        ent_rtl = ttk.Entry(row1, textvariable=self.vis_rtl_file)
        ent_rtl.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_rtl = ttk.Button(row1, text="浏览...", command=self._vis_browse_rtl, style='Browse.TButton')
        btn_rtl.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_rtl, "选择 RTL 文件")

        row2 = ttk.Frame(f_input)
        row2.pack(fill=tk.X, pady=2)
        self._make_label(row2, "策略配置:", width=10).pack(side=tk.LEFT)
        self.vis_strategy_file = tk.StringVar()
        ent_strat = ttk.Entry(row2, textvariable=self.vis_strategy_file)
        ent_strat.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_strat = ttk.Button(row2, text="浏览...", command=self._vis_browse_strategy, style='Browse.TButton')
        btn_strat.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_strat, "选择策略配置 JSON 文件")

        row3 = ttk.Frame(f_input)
        row3.pack(fill=tk.X, pady=(5, 0))

        btn_calc = ttk.Button(row3, text="计算指标", command=self._vis_calculate, style='Visualize.TButton')
        btn_calc.pack(side=tk.LEFT)
        add_tooltip(btn_calc, "计算加固效果指标")

        btn_html = ttk.Button(row3, text="生成 HTML 报告", command=self._vis_generate_html, style='Export.TButton')
        btn_html.pack(side=tk.LEFT, padx=5)
        add_tooltip(btn_html, "生成可视化 HTML 报告")

        f_stats = ttk.LabelFrame(tab, text="加固指标摘要", padding=8)
        f_stats.pack(fill=tk.X, padx=5, pady=5)

        self.vis_stats_vars = {
            'modules': tk.StringVar(value="0"),
            'registers': tk.StringVar(value="0"),
            'area': tk.StringVar(value="0%"),
            'latency': tk.StringVar(value="0 cycles"),
            'reliability': tk.StringVar(value="★☆☆☆☆"),
        }

        stats_grid = ttk.Frame(f_stats)
        stats_grid.pack(fill=tk.X)

        labels = [
            ('模块数', 'modules'),
            ('寄存器数', 'registers'),
            ('面积增加', 'area'),
            ('延迟开销', 'latency'),
            ('可靠性', 'reliability'),
        ]

        for i, (label, key) in enumerate(labels):
            f = ttk.Frame(stats_grid)
            f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 15))
            self._make_label(f, label, width=8).pack(anchor=tk.W)
            lbl_val = ttk.Label(f, textvariable=self.vis_stats_vars[key],
                               font=("微软雅黑", 14, "bold"), foreground="#006064")
            lbl_val.pack(anchor=tk.W)

        f_details = ttk.LabelFrame(tab, text="详细指标", padding=5)
        f_details.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        columns = ('module', 'strategy', 'area', 'reliability')
        self.vis_tree = ttk.Treeview(f_details, columns=columns, show='headings', height=10)
        self.vis_tree.heading('module', text='模块名称')
        self.vis_tree.heading('strategy', text='策略')
        self.vis_tree.heading('area', text='面积开销')
        self.vis_tree.heading('reliability', text='可靠性')

        self.vis_tree.column('module', width=200)
        self.vis_tree.column('strategy', width=120)
        self.vis_tree.column('area', width=120, anchor=tk.CENTER)
        self.vis_tree.column('reliability', width=120, anchor=tk.CENTER)

        scroll_tree = ttk.Scrollbar(f_details, orient=tk.VERTICAL, command=self.vis_tree.yview)
        self.vis_tree.configure(yscrollcommand=scroll_tree.set)
        self.vis_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_tree.pack(side=tk.RIGHT, fill=tk.Y)

        self._vis_metrics = None

    def _vis_browse_rtl(self):
        path = filedialog.askopenfilename(
            title="选择 RTL 文件",
            filetypes=[("Verilog 文件", "*.v"), ("SystemVerilog 文件", "*.sv"),
                       ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.vis_rtl_file.set(path)

    def _vis_browse_strategy(self):
        path = filedialog.askopenfilename(
            title="选择策略配置文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialdir=REPORTS_DIR if os.path.isdir(REPORTS_DIR) else SCRIPT_DIR,
        )
        if path:
            self.vis_strategy_file.set(path)

    def _vis_calculate(self):
        rtl_path = self.vis_rtl_file.get()
        if not rtl_path or not os.path.isfile(rtl_path):
            messagebox.showerror("错误", "请选择有效的 RTL 文件")
            return

        self._set_status("计算加固指标中...", "计算指标")

        def task():
            try:
                sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sim', 'formal_test'))
                from rag_integration import analyze_design_for_hardening, calculate_hardening_metrics

                analysis = analyze_design_for_hardening(rtl_path, recursive=True)

                strategy_file = self.vis_strategy_file.get()
                if strategy_file and os.path.isfile(strategy_file):
                    with open(strategy_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    module_strategy_map = config.get('module_strategies', {})
                else:
                    module_strategy_map = {}
                    top_module = analysis.get('module_name', 'top')
                    module_strategy_map[top_module] = 'tmr'
                    for sub_name in analysis.get('submodules', {}).keys():
                        module_strategy_map[sub_name] = 'tmr'

                metrics = calculate_hardening_metrics(analysis, module_strategy_map)
                self._vis_metrics = metrics

                summary = metrics.get('summary', {})
                self.vis_stats_vars['modules'].set(summary.get('total_modules', 0))
                self.vis_stats_vars['registers'].set(summary.get('total_registers', 0))
                self.vis_stats_vars['area'].set(f"{summary.get('area_increase_percent', 0):.1f}%")
                self.vis_stats_vars['latency'].set(f"{summary.get('max_latency_cycles', 0)} cycles")
                self.vis_stats_vars['reliability'].set(summary.get('avg_reliability_stars', '★☆☆☆☆'))

                for item in self.vis_tree.get_children():
                    self.vis_tree.delete(item)

                for module_name, metrics_item in metrics.get('by_module', {}).get('area', {}).items():
                    reliability = metrics.get('by_module', {}).get('reliability', {}).get(module_name, {})
                    self.vis_tree.insert('', tk.END, values=(
                        module_name,
                        metrics_item.get('strategy', 'unknown'),
                        f"{metrics_item.get('area_overhead', 0)}×",
                        reliability.get('reliability_stars', '★☆☆☆☆'),
                    ))

                self._set_status("指标计算完成", "计算加固效果")

            except Exception as e:
                messagebox.showerror("计算错误", f"计算加固指标时出错:\n{str(e)}")

        threading.Thread(target=task, daemon=True).start()

    def _vis_generate_html(self):
        if not self._vis_metrics:
            messagebox.showwarning("提示", "请先计算加固指标")
            return

        try:
            sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sim', 'formal_test'))
            from hardening_visualizer import generate_visualization_html

            os.makedirs(REPORTS_DIR, exist_ok=True)
            html_path = os.path.join(REPORTS_DIR, 'hardening_effect_report.html')
            generate_visualization_html(self._vis_metrics, html_path)

            self._set_status(f"HTML 报告已生成: {html_path}", "生成可视化报告")
            messagebox.showinfo("生成成功", f"HTML 报告已保存至:\n{html_path}\n\n是否在浏览器中打开？")
            os.startfile(html_path)

        except Exception as e:
            messagebox.showerror("生成错误", f"生成 HTML 报告时出错:\n{str(e)}")

    # ========================================================
    # Tab 8: 增量加固 (Incremental Hardening)
    # ========================================================
    def _build_tab_incremental(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 增量加固 (Incremental) ")

        f_top = ttk.Frame(tab)
        f_top.pack(fill=tk.X, pady=(5, 0), padx=5)

        self.inc_rtl_file = tk.StringVar()
        row1 = ttk.Frame(f_top)
        row1.pack(fill=tk.X, pady=2)
        self._make_label(row1, "RTL 文件:").pack(side=tk.LEFT)
        ent_rtl = ttk.Entry(row1, textvariable=self.inc_rtl_file, width=50)
        ent_rtl.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_rtl = ttk.Button(row1, text="浏览...", command=self._inc_browse_rtl)
        btn_rtl.pack(side=tk.LEFT)
        add_tooltip(btn_rtl, "选择 RTL 文件")

        row2 = ttk.Frame(f_top)
        row2.pack(fill=tk.X, pady=2)
        self._make_label(row2, "输出目录:").pack(side=tk.LEFT)
        self.inc_output_dir = tk.StringVar()
        ent_out = ttk.Entry(row2, textvariable=self.inc_output_dir, width=50)
        ent_out.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_out = ttk.Button(row2, text="浏览...", command=self._inc_browse_output)
        btn_out.pack(side=tk.LEFT)
        add_tooltip(btn_out, "选择增量数据输出目录")

        btn_run = ttk.Button(f_top, text="运行增量加固", command=self._inc_run)
        btn_run.pack(side=tk.RIGHT, padx=(5, 0))
        add_tooltip(btn_run, "运行增量加固流程")

        f_result = ttk.LabelFrame(tab, text="增量分析结果", padding=5)
        f_result.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.inc_result_text = scrolledtext.ScrolledText(f_result, height=15,
                                                        font=("Consolas", 9))
        self.inc_result_text.pack(fill=tk.BOTH, expand=True)

        self._inc_module_strategy_map = {}

    def _inc_browse_rtl(self):
        path = filedialog.askopenfilename(
            title="选择 RTL 文件",
            filetypes=[("Verilog 文件", "*.v"), ("SystemVerilog 文件", "*.sv"),
                       ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.inc_rtl_file.set(path)
            self.inc_output_dir.set(os.path.join(os.path.dirname(path), 'incremental_data'))

    def _inc_browse_output(self):
        path = filedialog.askdirectory(
            title="选择输出目录",
            initialdir=REPORTS_DIR if os.path.isdir(REPORTS_DIR) else SCRIPT_DIR,
        )
        if path:
            self.inc_output_dir.set(path)

    def _inc_run(self):
        rtl_path = self.inc_rtl_file.get()
        if not rtl_path or not os.path.isfile(rtl_path):
            messagebox.showerror("错误", "请选择有效的 RTL 文件")
            return

        output_dir = self.inc_output_dir.get()
        if not output_dir:
            messagebox.showerror("错误", "请指定输出目录")
            return

        self._set_status("运行增量加固中...", "增量加固")

        def task():
            try:
                sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sim', 'formal_test'))
                from rag_integration import analyze_design_for_hardening, run_incremental_hardening

                analysis = analyze_design_for_hardening(rtl_path, recursive=True)
                result = run_incremental_hardening(analysis, output_dir)

                self._inc_result_text.delete("1.0", tk.END)
                self._inc_result_text.insert("1.0", "=" * 60 + "\n")
                self._inc_result_text.insert(tk.END, "增量加固分析结果\n")
                self._inc_result_text.insert(tk.END, "=" * 60 + "\n\n")

                if result.get('design_changed'):
                    self._inc_result_text.insert(tk.END, "设计已变更，执行增量加固\n\n")
                    self._inc_result_text.insert(tk.END, f"复用模块数: {result.get('reused_modules', 0)}\n")
                    self._inc_result_text.insert(tk.END, f"新增模块数: {result.get('new_modules', 0)}\n")
                    self._inc_result_text.insert(tk.END, f"移除模块数: {result.get('removed_modules', 0)}\n")
                else:
                    self._inc_result_text.insert(tk.END, "设计未变更，使用缓存策略\n\n")

                self._inc_result_text.insert(tk.END, "\n模块策略映射:\n")
                for module_name, strategy in sorted(result.get('module_strategy_map', {}).items()):
                    self._inc_result_text.insert(tk.END, f"  {module_name}: {strategy}\n")

                self._inc_module_strategy_map = result.get('module_strategy_map', {})

                self._set_status("增量加固完成", f"处理 {len(self._inc_module_strategy_map)} 个模块")

            except Exception as e:
                self._inc_result_text.delete("1.0", tk.END)
                self._inc_result_text.insert("1.0", f"错误: {str(e)}")
                messagebox.showerror("增量加固错误", f"运行增量加固时出错:\n{str(e)}")

        threading.Thread(target=task, daemon=True).start()

    # ========================================================
    # Tab 9: Web GUI
    # ========================================================
    def _build_tab_web_gui(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" Web GUI ")

        f_top = ttk.Frame(tab)
        f_top.pack(fill=tk.X, pady=(5, 0), padx=5)

        self.web_rtl_file = tk.StringVar()
        row1 = ttk.Frame(f_top)
        row1.pack(fill=tk.X, pady=2)
        self._make_label(row1, "RTL 文件:").pack(side=tk.LEFT)
        ent_rtl = ttk.Entry(row1, textvariable=self.web_rtl_file, width=50)
        ent_rtl.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_rtl = ttk.Button(row1, text="浏览...", command=self._web_browse_rtl)
        btn_rtl.pack(side=tk.LEFT)
        add_tooltip(btn_rtl, "选择 RTL 文件")

        row2 = ttk.Frame(f_top)
        row2.pack(fill=tk.X, pady=2)
        self._make_label(row2, "端口:").pack(side=tk.LEFT)
        self.web_port = tk.IntVar(value=8080)
        ent_port = ttk.Entry(row2, textvariable=self.web_port, width=10)
        ent_port.pack(side=tk.LEFT, padx=5)

        btn_start = ttk.Button(f_top, text="启动 Web GUI", command=self._web_start)
        btn_start.pack(side=tk.RIGHT, padx=(5, 0))
        add_tooltip(btn_start, "启动 Web 图形界面")

        f_info = ttk.LabelFrame(tab, text="Web GUI 信息", padding=5)
        f_info.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.web_info_text = scrolledtext.ScrolledText(f_info, height=15,
                                                      font=("Consolas", 9))
        self.web_info_text.pack(fill=tk.BOTH, expand=True)

        self.web_info_text.insert("1.0", "Web GUI 允许您通过浏览器访问 RTL 加固工具集。\n\n")
        self.web_info_text.insert(tk.END, "功能特性:\n")
        self.web_info_text.insert(tk.END, "  • 模块层次结构可视化\n")
        self.web_info_text.insert(tk.END, "  • 模块级策略配置\n")
        self.web_info_text.insert(tk.END, "  • 实时策略 JSON 预览\n")
        self.web_info_text.insert(tk.END, "  • 一键运行加固\n\n")
        self.web_info_text.insert(tk.END, "使用步骤:\n")
        self.web_info_text.insert(tk.END, "  1. 选择 RTL 文件\n")
        self.web_info_text.insert(tk.END, "  2. 点击 \"启动 Web GUI\"\n")
        self.web_info_text.insert(tk.END, "  3. 在浏览器中访问显示的 URL\n")

        self._web_gui_instance = None

    def _web_browse_rtl(self):
        path = filedialog.askopenfilename(
            title="选择 RTL 文件",
            filetypes=[("Verilog 文件", "*.v"), ("SystemVerilog 文件", "*.sv"),
                       ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.web_rtl_file.set(path)

    def _web_start(self):
        rtl_path = self.web_rtl_file.get()
        if not rtl_path or not os.path.isfile(rtl_path):
            messagebox.showerror("错误", "请选择有效的 RTL 文件")
            return

        port = self.web_port.get()
        if port < 1 or port > 65535:
            messagebox.showerror("错误", "请输入有效的端口号 (1-65535)")
            return

        self._set_status("启动 Web GUI 中...", "启动 Web GUI")

        def task():
            try:
                sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sim', 'formal_test'))
                from rag_integration import analyze_design_for_hardening, open_web_gui

                analysis = analyze_design_for_hardening(rtl_path, recursive=True)

                module_strategy_map = {}
                top_module = analysis.get('module_name', 'top')
                module_strategy_map[top_module] = 'tmr'
                for sub_name in analysis.get('submodules', {}).keys():
                    module_strategy_map[sub_name] = 'tmr'

                self._web_gui_instance = open_web_gui(analysis, module_strategy_map, None, port)

                if self._web_gui_instance:
                    self.web_info_text.delete("1.0", tk.END)
                    self.web_info_text.insert("1.0", f"Web GUI 已启动!\n\n")
                    self.web_info_text.insert(tk.END, f"URL: http://localhost:{port}\n")
                    self.web_info_text.insert(tk.END, f"RTL 文件: {rtl_path}\n")
                    self.web_info_text.insert(tk.END, f"模块数: {len(module_strategy_map)}\n\n")
                    self.web_info_text.insert(tk.END, "Web GUI 运行在后台线程中。\n")
                    self.web_info_text.insert(tk.END, "关闭此窗口将停止 Web GUI。")
                    self._set_status(f"Web GUI 已启动: http://localhost:{port}", "Web GUI")
                else:
                    messagebox.showerror("启动失败", "Web GUI 模块不可用")

            except Exception as e:
                messagebox.showerror("启动错误", f"启动 Web GUI 时出错:\n{str(e)}")

        threading.Thread(target=task, daemon=True).start()

    # ========================================================
    # Tab 10: 报告 (Reports)
    # ========================================================
    def _build_tab_reports(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 报告 (Reports) ")

        # -- 工具栏 --
        f_toolbar = ttk.Frame(tab)
        f_toolbar.pack(fill=tk.X, pady=(5, 0), padx=5)
        btn_refresh = ttk.Button(f_toolbar, text="刷新",
                                 command=self._reports_refresh)
        btn_refresh.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_refresh, "刷新报告列表")

        btn_open_dir = ttk.Button(f_toolbar, text="在资源管理器中打开",
                                  command=self._reports_open_dir)
        btn_open_dir.pack(side=tk.LEFT)
        add_tooltip(btn_open_dir, "在 Windows 资源管理器中打开报告目录")

        # -- 中间区域: 左侧文件列表 + 右侧预览 --
        f_mid = ttk.Frame(tab)
        f_mid.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 左侧文件列表
        f_list = ttk.LabelFrame(f_mid, text="报告文件列表", padding=2)
        f_list.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))

        self.reports_listbox = tk.Listbox(f_list, width=35, height=20,
                                           font=("Consolas", 9),
                                           selectmode=tk.SINGLE)
        self.reports_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_list = ttk.Scrollbar(f_list, orient=tk.VERTICAL,
                                     command=self.reports_listbox.yview)
        self.reports_listbox.configure(yscrollcommand=scroll_list.set)
        scroll_list.pack(side=tk.RIGHT, fill=tk.Y)

        self.reports_listbox.bind('<<ListboxSelect>>', self._reports_on_select)

        # 右侧预览
        f_preview = ttk.LabelFrame(f_mid, text="文件预览", padding=2)
        f_preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.report_preview_text = scrolledtext.ScrolledText(
            f_preview, wrap=tk.WORD,
            font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white"
        )
        self.report_preview_text.pack(fill=tk.BOTH, expand=True)

        # 初始加载
        self._reports_refresh()

    def _reports_refresh(self):
        self.reports_listbox.delete(0, tk.END)
        self.report_preview_text.delete("1.0", tk.END)

        if not os.path.isdir(REPORTS_DIR):
            self.reports_listbox.insert(tk.END, "(报告目录不存在)")
            return

        files = sorted([
            f for f in os.listdir(REPORTS_DIR)
            if os.path.isfile(os.path.join(REPORTS_DIR, f))
        ])
        if not files:
            self.reports_listbox.insert(tk.END, "(暂无报告文件)")
            return

        self._report_files = {}
        for fname in files:
            full_path = os.path.join(REPORTS_DIR, fname)
            self.reports_listbox.insert(tk.END, fname)
            self._report_files[fname] = full_path

        self._set_status(f"找到 {len(files)} 个报告文件", "刷新报告列表")

    def _reports_on_select(self, _event=None):
        sel = self.reports_listbox.curselection()
        if not sel:
            return
        fname = self.reports_listbox.get(sel[0])
        full_path = self._report_files.get(fname)
        if not full_path or not os.path.isfile(full_path):
            return

        try:
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self.report_preview_text.delete("1.0", tk.END)
            self.report_preview_text.insert("1.0", content)
            self._set_status(f"预览: {fname}")
        except Exception as e:
            self.report_preview_text.delete("1.0", tk.END)
            self.report_preview_text.insert("1.0", f"读取失败: {e}")

    def _reports_open_dir(self):
        if os.path.isdir(REPORTS_DIR):
            os.startfile(REPORTS_DIR)
        else:
            messagebox.showerror("错误", f"报告目录不存在:\n{REPORTS_DIR}")

    # ========================================================
    # Tab 11: FPGA 比特流加固 (FPGA Bitstream Hardening)
    # ========================================================
    def _build_tab_fpga(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" FPGA 比特流加固 ")

        f_input = ttk.LabelFrame(tab, text="输入配置", padding=8)
        f_input.pack(fill=tk.X, padx=5, pady=(5, 0))

        row1 = ttk.Frame(f_input)
        row1.pack(fill=tk.X, pady=2)
        self._make_label(row1, "比特流文件:").pack(side=tk.LEFT)
        self.fpga_bitstream = tk.StringVar()
        ent_bit = ttk.Entry(row1, textvariable=self.fpga_bitstream, width=50)
        ent_bit.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_bit = ttk.Button(row1, text="浏览...", command=self._fpga_browse_bitstream)
        btn_bit.pack(side=tk.LEFT)
        add_tooltip(btn_bit, "选择 .bit 格式的 FPGA 比特流文件")

        row2 = ttk.Frame(f_input)
        row2.pack(fill=tk.X, pady=2)
        self._make_label(row2, "输出文件:").pack(side=tk.LEFT)
        self.fpga_output = tk.StringVar()
        ent_out = ttk.Entry(row2, textvariable=self.fpga_output, width=50)
        ent_out.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_out = ttk.Button(row2, text="浏览...", command=self._fpga_browse_output)
        btn_out.pack(side=tk.LEFT)
        add_tooltip(btn_out, "选择加固后比特流保存路径")

        f_options = ttk.LabelFrame(tab, text="加固选项", padding=8)
        f_options.pack(fill=tk.X, padx=5, pady=5)

        self.fpga_tmr = tk.BooleanVar(value=True)
        cb_tmr = ttk.Checkbutton(f_options, text="启用 TMR (三模冗余)", variable=self.fpga_tmr)
        cb_tmr.pack(anchor=tk.W)

        self.fpga_ecc = tk.BooleanVar(value=False)
        cb_ecc = ttk.Checkbutton(f_options, text="启用 ECC (纠错码)", variable=self.fpga_ecc)
        cb_ecc.pack(anchor=tk.W)

        self.fpga_scrub = tk.BooleanVar(value=True)
        cb_scrub = ttk.Checkbutton(f_options, text="启用比特流刷新 (Scrubbing)", variable=self.fpga_scrub)
        cb_scrub.pack(anchor=tk.W)

        self.fpga_pr = tk.BooleanVar(value=False)
        cb_pr = ttk.Checkbutton(f_options, text="启用 Partial Reconfiguration", variable=self.fpga_pr)
        cb_pr.pack(anchor=tk.W)

        f_action = ttk.Frame(tab)
        f_action.pack(fill=tk.X, padx=5, pady=(0, 5))
        btn_harden = ttk.Button(f_action, text="执行比特流加固", command=self._fpga_run_hardening, style='Run.TButton')
        btn_harden.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_harden, "对 FPGA 比特流进行加固处理")

        btn_report = ttk.Button(f_action, text="生成可靠性报告", command=self._fpga_generate_report, style='Export.TButton')
        btn_report.pack(side=tk.LEFT)
        add_tooltip(btn_report, "生成 FPGA 比特流可靠性分析报告")

        f_result = ttk.LabelFrame(tab, text="加固结果", padding=5)
        f_result.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        self.fpga_result_text = scrolledtext.ScrolledText(f_result, height=15,
                                                          font=("Consolas", 9))
        self.fpga_result_text.pack(fill=tk.BOTH, expand=True)

        self.fpga_result_text.insert("1.0", "FPGA 比特流加固工具\n\n")
        self.fpga_result_text.insert(tk.END, "支持以下加固策略:\n")
        self.fpga_result_text.insert(tk.END, "  • TMR: 三模冗余\n")
        self.fpga_result_text.insert(tk.END, "  • ECC: 纠错码保护\n")
        self.fpga_result_text.insert(tk.END, "  • Scrubbing: 比特流自动刷新\n")
        self.fpga_result_text.insert(tk.END, "  • PR: Partial Reconfiguration\n\n")
        self.fpga_result_text.insert(tk.END, "请选择比特流文件并配置加固选项后点击执行。")

    def _fpga_browse_bitstream(self):
        path = filedialog.askopenfilename(
            title="选择 FPGA 比特流文件",
            filetypes=[("比特流文件", "*.bit"), ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.fpga_bitstream.set(path)
            base, ext = os.path.splitext(path)
            self.fpga_output.set(base + "_hardened" + ext)

    def _fpga_browse_output(self):
        path = filedialog.asksaveasfilename(
            title="保存加固后比特流",
            defaultextension=".bit",
            filetypes=[("比特流文件", "*.bit"), ("所有文件", "*.*")],
        )
        if path:
            self.fpga_output.set(path)

    def _fpga_run_hardening(self):
        bitstream_path = self.fpga_bitstream.get()
        output_path = self.fpga_output.get()

        if not bitstream_path or not os.path.isfile(bitstream_path):
            messagebox.showerror("错误", "请选择有效的比特流文件")
            return
        if not output_path:
            messagebox.showerror("错误", "请指定输出文件路径")
            return

        self._set_status("FPGA 比特流加固中...", "FPGA 比特流加固")

        def task():
            try:
                sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sim', 'formal_test'))
                from fpga_bitstream_hardening import FPGABitstreamHardener

                hardener = FPGABitstreamHardener()

                if not hardener.load_bitstream(bitstream_path):
                    self.fpga_result_text.delete("1.0", tk.END)
                    self.fpga_result_text.insert("1.0", "错误: 加载比特流文件失败")
                    return

                if self.fpga_tmr.get():
                    hardener.configure_tmr(['TOP_MODULE'])

                if self.fpga_ecc.get():
                    hardener.configure_ecc_region('CONFIG_REGION', 0x0, 0xFFFF)

                hardener.enable_scrubbing(self.fpga_scrub.get(), 1000)
                hardener.enable_partial_reconfig(self.fpga_pr.get())

                result = hardener.generate_hardened_bitstream(output_path)

                self.fpga_result_text.delete("1.0", tk.END)
                self.fpga_result_text.insert("1.0", "=" * 60 + "\n")
                self.fpga_result_text.insert(tk.END, "FPGA 比特流加固结果\n")
                self.fpga_result_text.insert(tk.END, "=" * 60 + "\n\n")

                if result['success']:
                    self.fpga_result_text.insert(tk.END, "✅ 加固成功\n\n")
                    self.fpga_result_text.insert(tk.END, f"输入文件: {bitstream_path}\n")
                    self.fpga_result_text.insert(tk.END, f"输出文件: {output_path}\n")
                    self.fpga_result_text.insert(tk.END, f"应用策略: {', '.join(result['applied_strategies'])}\n")
                    self.fpga_result_text.insert(tk.END, f"可靠性提升: {result['reliability_improvement'] * 100:.1f}%\n")
                    self.fpga_result_text.insert(tk.END, f"面积开销: {result['overhead_percent']:.1f}%\n")
                else:
                    self.fpga_result_text.insert(tk.END, f"❌ 加固失败: {result.get('error', '未知错误')}\n")

                self._set_status("FPGA 比特流加固完成", "FPGA 比特流加固")

            except Exception as e:
                self.fpga_result_text.delete("1.0", tk.END)
                self.fpga_result_text.insert("1.0", f"错误: {str(e)}")
                messagebox.showerror("FPGA 加固错误", f"运行 FPGA 比特流加固时出错:\n{str(e)}")

        threading.Thread(target=task, daemon=True).start()

    def _fpga_generate_report(self):
        bitstream_path = self.fpga_bitstream.get()
        if not bitstream_path or not os.path.isfile(bitstream_path):
            messagebox.showerror("错误", "请选择有效的比特流文件")
            return

        self._set_status("生成 FPGA 可靠性报告...", "FPGA 可靠性报告")

        def task():
            try:
                sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sim', 'formal_test'))
                from fpga_bitstream_hardening import FPGABitstreamHardener

                hardener = FPGABitstreamHardener()
                hardener.load_bitstream(bitstream_path)

                if self.fpga_tmr.get():
                    hardener.configure_tmr(['TOP_MODULE'])
                if self.fpga_ecc.get():
                    hardener.configure_ecc_region('CONFIG_REGION', 0x0, 0xFFFF)
                hardener.enable_scrubbing(self.fpga_scrub.get(), 1000)

                report = hardener.generate_reliability_report()

                self.fpga_result_text.delete("1.0", tk.END)
                self.fpga_result_text.insert("1.0", json.dumps(report, indent=2, ensure_ascii=False))

                report_path = os.path.join(REPORTS_DIR, 'fpga_reliability_report.json')
                os.makedirs(REPORTS_DIR, exist_ok=True)
                with open(report_path, 'w', encoding='utf-8') as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)

                self._set_status(f"报告已生成: {report_path}", "FPGA 可靠性报告")

            except Exception as e:
                self.fpga_result_text.delete("1.0", tk.END)
                self.fpga_result_text.insert("1.0", f"错误: {str(e)}")
                messagebox.showerror("报告生成错误", f"生成报告时出错:\n{str(e)}")

        threading.Thread(target=task, daemon=True).start()

    # ========================================================
    # Tab 12: 可靠性报告 (Reliability Report)
    # ========================================================
    def _build_tab_reliability(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 可靠性报告 ")

        f_input = ttk.LabelFrame(tab, text="输入配置", padding=8)
        f_input.pack(fill=tk.X, padx=5, pady=(5, 0))

        row1 = ttk.Frame(f_input)
        row1.pack(fill=tk.X, pady=2)
        self._make_label(row1, "RTL 文件:").pack(side=tk.LEFT)
        self.rel_rtl_file = tk.StringVar()
        ent_rtl = ttk.Entry(row1, textvariable=self.rel_rtl_file, width=50)
        ent_rtl.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_rtl = ttk.Button(row1, text="浏览...", command=self._rel_browse_rtl)
        btn_rtl.pack(side=tk.LEFT)
        add_tooltip(btn_rtl, "选择 RTL 文件进行可靠性分析")

        f_action = ttk.Frame(tab)
        f_action.pack(fill=tk.X, padx=5, pady=5)
        btn_analyze = ttk.Button(f_action, text="生成可靠性报告", command=self._rel_generate_report, style='Export.TButton')
        btn_analyze.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_analyze, "分析设计并生成可靠性报告")

        btn_export = ttk.Button(f_action, text="导出报告", command=self._rel_export_report, style='Export.TButton')
        btn_export.pack(side=tk.LEFT)
        add_tooltip(btn_export, "导出报告为 JSON 文件")

        f_result = ttk.LabelFrame(tab, text="可靠性分析结果", padding=5)
        f_result.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        self.rel_result_text = scrolledtext.ScrolledText(f_result, height=20,
                                                        font=("Consolas", 9))
        self.rel_result_text.pack(fill=tk.BOTH, expand=True)

        self.rel_result_text.insert("1.0", "可靠性分析报告工具\n\n")
        self.rel_result_text.insert(tk.END, "支持计算以下指标:\n")
        self.rel_result_text.insert(tk.END, "  • AVF: 架构脆弱性因子\n")
        self.rel_result_text.insert(tk.END, "  • MTBF: 平均故障间隔时间\n")
        self.rel_result_text.insert(tk.END, "  • 故障率\n")
        self.rel_result_text.insert(tk.END, "  • 可靠性改进建议\n\n")
        self.rel_result_text.insert(tk.END, "请选择 RTL 文件后点击生成报告。")

        self._rel_report_data = None

    def _rel_browse_rtl(self):
        path = filedialog.askopenfilename(
            title="选择 RTL 文件",
            filetypes=[("Verilog 文件", "*.v"), ("SystemVerilog 文件", "*.sv"),
                       ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.rel_rtl_file.set(path)

    def _rel_generate_report(self):
        rtl_path = self.rel_rtl_file.get()
        if not rtl_path or not os.path.isfile(rtl_path):
            messagebox.showerror("错误", "请选择有效的 RTL 文件")
            return

        self._set_status("生成可靠性报告中...", "可靠性分析")

        def task():
            try:
                sys.path.insert(0, SCRIPT_DIR)
                from hardening_pipeline import HardeningPipeline

                pipeline = HardeningPipeline(optimization_goal='balanced')
                pipeline.load_design(rtl_path)
                pipeline.analyze()
                pipeline.route_strategies()

                report = pipeline.generate_reliability_report()

                self._rel_report_data = report

                self.rel_result_text.delete("1.0", tk.END)
                self.rel_result_text.insert("1.0", "=" * 60 + "\n")
                self.rel_result_text.insert(tk.END, "可靠性分析报告\n")
                self.rel_result_text.insert(tk.END, "=" * 60 + "\n\n")

                analysis = report.get('analysis', {})
                if 'overall_avf' in analysis:
                    self.rel_result_text.insert(tk.END, f"📊 总体 AVF: {analysis['overall_avf']:.4f}\n")
                if 'failure_rate' in analysis:
                    self.rel_result_text.insert(tk.END, f"📉 故障率: {analysis['failure_rate']:.2e} failures/hour\n")
                if 'mtbf' in analysis:
                    self.rel_result_text.insert(tk.END, f"⏱️ MTBF: {analysis['mtbf']:.2f} 小时\n")
                if 'reliability_improvement' in analysis:
                    self.rel_result_text.insert(tk.END, f"📈 可靠性提升: {analysis['reliability_improvement'] * 100:.1f}%\n")

                recommendations = report.get('recommendations', [])
                if recommendations:
                    self.rel_result_text.insert(tk.END, "\n💡 改进建议:\n")
                    for i, rec in enumerate(recommendations, 1):
                        self.rel_result_text.insert(tk.END, f"  {i}. {rec}\n")

                summary = report.get('summary', {})
                if summary:
                    self.rel_result_text.insert(tk.END, "\n📝 摘要:\n")
                    self.rel_result_text.insert(tk.END, json.dumps(summary, indent=2, ensure_ascii=False))

                self._set_status("可靠性报告生成完成", "可靠性分析")

            except Exception as e:
                self.rel_result_text.delete("1.0", tk.END)
                self.rel_result_text.insert("1.0", f"错误: {str(e)}")
                messagebox.showerror("可靠性分析错误", f"生成报告时出错:\n{str(e)}")

        threading.Thread(target=task, daemon=True).start()

    def _rel_export_report(self):
        if not self._rel_report_data:
            messagebox.showwarning("提示", "请先生成可靠性报告")
            return

        path = filedialog.asksaveasfilename(
            title="导出可靠性报告",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialdir=REPORTS_DIR,
        )
        if not path:
            return

        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._rel_report_data, f, indent=2, ensure_ascii=False)

            self._set_status(f"报告已导出: {path}", "导出可靠性报告")
            messagebox.showinfo("导出成功", f"报告已保存至:\n{path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ========================================================
    # Tab 13: 形式化验证 (Formal Verification)
    # ========================================================
    def _build_tab_formal(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" 形式化验证 ")

        f_input = ttk.LabelFrame(tab, text="输入配置", padding=8)
        f_input.pack(fill=tk.X, padx=5, pady=(5, 0))

        row1 = ttk.Frame(f_input)
        row1.pack(fill=tk.X, pady=2)
        self._make_label(row1, "RTL 文件:").pack(side=tk.LEFT)
        self.fml_rtl_file = tk.StringVar()
        ent_rtl = ttk.Entry(row1, textvariable=self.fml_rtl_file, width=50)
        ent_rtl.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_rtl = ttk.Button(row1, text="浏览...", command=self._fml_browse_rtl)
        btn_rtl.pack(side=tk.LEFT)
        add_tooltip(btn_rtl, "选择 RTL 文件进行形式化验证")

        row2 = ttk.Frame(f_input)
        row2.pack(fill=tk.X, pady=2)
        self._make_label(row2, "SVA 文件:").pack(side=tk.LEFT)
        self.fml_sva_file = tk.StringVar()
        ent_sva = ttk.Entry(row2, textvariable=self.fml_sva_file, width=50)
        ent_sva.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        btn_sva = ttk.Button(row2, text="浏览...", command=self._fml_browse_sva)
        btn_sva.pack(side=tk.LEFT)
        add_tooltip(btn_sva, "选择 SVA 属性文件（可选）")

        f_action = ttk.Frame(tab)
        f_action.pack(fill=tk.X, padx=5, pady=5)
        btn_verify = ttk.Button(f_action, text="执行形式化验证", command=self._fml_run_verify, style='Run.TButton')
        btn_verify.pack(side=tk.LEFT, padx=(0, 5))
        add_tooltip(btn_verify, "使用 SymbiYosys 执行形式化验证")

        btn_check = ttk.Button(f_action, text="检查 SymbiYosys", command=self._fml_check_sby)
        btn_check.pack(side=tk.LEFT)
        add_tooltip(btn_check, "检查 SymbiYosys 是否可用")

        f_result = ttk.LabelFrame(tab, text="验证结果", padding=5)
        f_result.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        self.fml_result_text = scrolledtext.ScrolledText(f_result, height=20,
                                                        font=("Consolas", 9))
        self.fml_result_text.pack(fill=tk.BOTH, expand=True)

        self.fml_result_text.insert("1.0", "形式化验证工具\n\n")
        self.fml_result_text.insert(tk.END, "集成 SymbiYosys 进行形式化验证:\n")
        self.fml_result_text.insert(tk.END, "  • 验证加固后设计的功能正确性\n")
        self.fml_result_text.insert(tk.END, "  • 支持 SVA 属性验证\n")
        self.fml_result_text.insert(tk.END, "  • 自动生成验证配置文件\n\n")
        self.fml_result_text.insert(tk.END, "注意: 需要安装 SymbiYosys 才能使用此功能。\n")
        self.fml_result_text.insert(tk.END, "请先点击 '检查 SymbiYosys' 确认环境。")

    def _fml_browse_rtl(self):
        path = filedialog.askopenfilename(
            title="选择 RTL 文件",
            filetypes=[("Verilog 文件", "*.v"), ("SystemVerilog 文件", "*.sv"),
                       ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.fml_rtl_file.set(path)

    def _fml_browse_sva(self):
        path = filedialog.askopenfilename(
            title="选择 SVA 文件",
            filetypes=[("SVA 文件", "*.sva"), ("所有文件", "*.*")],
            initialdir=TEST_MOCK_DIR if os.path.isdir(TEST_MOCK_DIR) else SCRIPT_DIR,
        )
        if path:
            self.fml_sva_file.set(path)

    def _fml_check_sby(self):
        self._set_status("检查 SymbiYosys...", "检查形式化验证环境")

        def task():
            try:
                sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sim', 'formal_test'))
                from formal_verification import FormalVerifier

                verifier = FormalVerifier()

                self.fml_result_text.delete("1.0", tk.END)
                if verifier.is_available():
                    self.fml_result_text.insert("1.0", "✅ SymbiYosys 可用\n\n")
                    self.fml_result_text.insert(tk.END, f"Yosys 路径: {verifier._yosys_path}\n")
                    self.fml_result_text.insert(tk.END, f"Sby 路径: {verifier._sby_path}\n\n")
                    self.fml_result_text.insert(tk.END, "可以执行形式化验证。")
                    self._set_status("SymbiYosys 可用", "形式化验证环境")
                else:
                    self.fml_result_text.insert("1.0", "❌ SymbiYosys 不可用\n\n")
                    self.fml_result_text.insert(tk.END, "请安装 SymbiYosys 以启用形式化验证功能。\n")
                    self.fml_result_text.insert(tk.END, "安装指南: https://symbiyosys.readthedocs.io/\n")
                    self._set_status("SymbiYosys 不可用", "形式化验证环境")

            except Exception as e:
                self.fml_result_text.delete("1.0", tk.END)
                self.fml_result_text.insert("1.0", f"错误: {str(e)}")

        threading.Thread(target=task, daemon=True).start()

    def _fml_run_verify(self):
        rtl_path = self.fml_rtl_file.get()
        if not rtl_path or not os.path.isfile(rtl_path):
            messagebox.showerror("错误", "请选择有效的 RTL 文件")
            return

        self._set_status("执行形式化验证中...", "形式化验证")

        def task():
            try:
                sys.path.insert(0, os.path.join(SCRIPT_DIR, 'sim', 'formal_test'))
                from formal_verification import FormalVerifier

                verifier = FormalVerifier()

                if not verifier.is_available():
                    self.fml_result_text.delete("1.0", tk.END)
                    self.fml_result_text.insert("1.0", "❌ SymbiYosys 不可用，无法执行验证")
                    return

                sva_path = self.fml_sva_file.get() if self.fml_sva_file.get() else None
                sva_files = [sva_path] if sva_path else None

                result = verifier.verify([rtl_path], sva_files=sva_files)

                self.fml_result_text.delete("1.0", tk.END)
                self.fml_result_text.insert("1.0", "=" * 60 + "\n")
                self.fml_result_text.insert(tk.END, "形式化验证结果\n")
                self.fml_result_text.insert(tk.END, "=" * 60 + "\n\n")

                if result.get('success'):
                    status = result.get('status', 'unknown')
                    self.fml_result_text.insert(tk.END, f"状态: {status}\n\n")

                    if 'properties' in result:
                        for prop in result['properties']:
                            p_status = prop.get('status', 'unknown')
                            p_name = prop.get('name', 'unknown')
                            color = "green" if p_status == 'PASS' else "red"
                            self.fml_result_text.insert(tk.END, f"  {p_name}: {p_status}\n", color)
                else:
                    self.fml_result_text.insert(tk.END, f"❌ 验证失败: {result.get('error', '未知错误')}\n")

                self._set_status("形式化验证完成", "形式化验证")

            except Exception as e:
                self.fml_result_text.delete("1.0", tk.END)
                self.fml_result_text.insert("1.0", f"错误: {str(e)}")
                messagebox.showerror("验证错误", f"执行形式化验证时出错:\n{str(e)}")

        threading.Thread(target=task, daemon=True).start()

    # ========================================================
    # 窗口关闭
    # ========================================================
    def _on_close(self):
        self.root.destroy()

    # ========================================================
    # 启动
    # ========================================================
    def run(self):
        self.root.mainloop()


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    app = HardeningGUI()
    app.run()
