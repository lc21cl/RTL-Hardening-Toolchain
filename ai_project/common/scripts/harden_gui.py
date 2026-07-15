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
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)

        # 尝试设置图标（若有）
        try:
            self.root.iconbitmap(default='')
        except Exception:
            pass

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
    # 主区域 — Tab 控件
    # ========================================================
    def _build_main(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._build_tab_pipeline()
        self._build_tab_testrunner()
        self._build_tab_signalscan()
        self._build_tab_aig()
        self._build_tab_reports()

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
    # Tab 5: 报告 (Reports)
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
