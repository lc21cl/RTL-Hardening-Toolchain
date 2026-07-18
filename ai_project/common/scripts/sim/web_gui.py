#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_gui.py — 基于 Flask 的远程 Web GUI 加固工具

提供浏览器远程访问 RTL 加固工具链的能力，支持文件上传、策略选择、
异步执行、实时日志查看和加固结果对比。

用法:
    python web_gui.py          # 直接启动，默认 0.0.0.0:5000
"""

import os
import sys
import json
import uuid
import time
import threading
import queue
import zipfile
import shutil
import re
from io import StringIO
from datetime import datetime

# ---------------------------------------------------------------------------
# Flask 可用性检查
# ---------------------------------------------------------------------------
try:
    from flask import Flask, render_template_string, request, jsonify, send_file
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, '..'))

_UPLOAD_DIR = os.path.join(_SCRIPT_DIR, 'web_uploads')
_OUTPUT_DIR = os.path.join(_SCRIPT_DIR, 'web_outputs')
_HISTORY_FILE = os.path.join(_SCRIPT_DIR, 'web_history.json')
_CONFIG_FILE = os.path.join(_SCRIPT_DIR, 'web_config.json')

os.makedirs(_UPLOAD_DIR, exist_ok=True)
os.makedirs(_OUTPUT_DIR, exist_ok=True)

# 默认配置
DEFAULT_CONFIG = {
    'api_key': '',
    'api_endpoint': '',
    'max_upload_size_mb': 100,
    'default_strategy': 'auto',
}

# ---------------------------------------------------------------------------
# 任务管理
# ---------------------------------------------------------------------------
tasks = {}
task_logs = {}
task_cancel = {}


# ---------------------------------------------------------------------------
# 任务日志
# ---------------------------------------------------------------------------
class TaskLogger:
    """重定向 stdout 到任务队列"""
    def __init__(self, task_id):
        self.task_id = task_id
        self.queue = task_logs.get(task_id)
        self.old_stdout = None
        self.old_stderr = None

    def write(self, text):
        if text.strip():
            timestamp = datetime.now().strftime('%H:%M:%S')
            msg = f"{timestamp} [INFO] {text.rstrip()}"
            if self.queue:
                self.queue.put(msg)

    def flush(self):
        pass

    def __enter__(self):
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        sys.stdout = self
        sys.stderr = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr
        if exc_type:
            msg = f"[ERROR] {exc_val}"
            if self.queue:
                self.queue.put(msg)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def load_config():
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_history():
    if os.path.exists(_HISTORY_FILE):
        try:
            with open(_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []


def save_history(history):
    with open(_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def add_history(entry):
    history = load_history()
    history.insert(0, entry)
    if len(history) > 100:
        history = history[:100]
    save_history(history)


def get_task(task_id):
    return tasks.get(task_id)


def update_task(task_id, **kwargs):
    if task_id in tasks:
        tasks[task_id].update(kwargs)


def make_task_id():
    return uuid.uuid4().hex[:12]


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'v', 'sv', 'vhdl', 'vhd', 'zip'}


def extract_zip(zip_path, extract_to):
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_to)
    rtl_files = []
    for root, dirs, files in os.walk(extract_to):
        for f in files:
            if f.endswith(('.v', '.sv')):
                rtl_files.append(os.path.join(root, f))
    return rtl_files


def get_file_content(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except:
            return f"[无法读取文件: {file_path}]"


# ---------------------------------------------------------------------------
# 后台任务执行
# ---------------------------------------------------------------------------
def run_harden_task(task_id, design_file, strategies, optimization_goal):
    """后台执行加固任务的线程函数"""
    task_logs[task_id] = queue.Queue()
    task_cancel[task_id] = threading.Event()

    logger = TaskLogger(task_id)
    with logger:
        try:
            update_task(task_id, status='running', progress='初始化加固管线...')

            from hardening_pipeline import HardeningPipeline

            pipeline = HardeningPipeline(optimization_goal=optimization_goal)

            # 加载设计
            update_task(task_id, progress='加载设计文件...')
            task_logs[task_id].put("[INFO] 加载设计文件...")
            success = pipeline.load_design(design_file)
            if not success:
                raise RuntimeError(f"加载设计文件失败: {design_file}")
            task_logs[task_id].put(f"[OK] 设计文件加载成功")

            # 分析
            update_task(task_id, progress='正在分析设计结构...')
            module_info = pipeline.analyze()
            task_logs[task_id].put(f"[OK] 分析完成: 发现 {len(module_info)} 个信号")

            if task_cancel[task_id].is_set():
                update_task(task_id, status='cancelled', progress='任务已取消')
                return

            # 策略选择
            update_task(task_id, progress='正在分配加固策略...')
            if strategies and 'auto' not in strategies:
                user_strategies = [s.strip() for s in strategies if s.strip()]
                pipeline.route_strategies(goal=optimization_goal, user_strategies=user_strategies)
            else:
                pipeline.route_strategies(goal=optimization_goal)
            task_logs[task_id].put("[OK] 策略分配完成")

            strategy_map = dict(pipeline.strategy_map)
            strategy_groups = {}
            for sig, strategy in strategy_map.items():
                strategy_groups.setdefault(strategy, []).append(sig)

            if task_cancel[task_id].is_set():
                update_task(task_id, status='cancelled')
                return

            # 变换
            update_task(task_id, progress='正在执行加固变换...')
            pipeline.transform()
            task_logs[task_id].put("[OK] 加固变换完成")

            if task_cancel[task_id].is_set():
                update_task(task_id, status='cancelled')
                return

            # 输出
            update_task(task_id, progress='正在生成加固代码...')
            base_name = os.path.basename(design_file)
            stem, ext = os.path.splitext(base_name)
            output_file = os.path.join(_OUTPUT_DIR, f"{task_id}_{stem}_hardened{ext}")
            pipeline.output(output_file)
            task_logs[task_id].put(f"[OK] 加固代码已生成")

            original_code = get_file_content(design_file)
            hardened_code = get_file_content(output_file)

            # AIG 分析
            update_task(task_id, progress='正在执行AIG分析...')
            try:
                aig_results = pipeline.run_aig_analysis()
            except Exception as e:
                aig_results = {'success': False, 'error': str(e)}

            if task_cancel[task_id].is_set():
                update_task(task_id, status='cancelled')
                return

            # 故障注入
            update_task(task_id, progress='正在执行故障注入测试...')
            try:
                fault_results = pipeline.run_fault_injection(num_injections=200)
            except Exception as e:
                fault_results = {'success': False, 'error': str(e)}

            if task_cancel[task_id].is_set():
                update_task(task_id, status='cancelled')
                return

            # GNN 脆弱性预测
            update_task(task_id, progress='正在执行脆弱性预测...')
            try:
                vulnerability_scores = pipeline.predict_vulnerability()
                pipeline.vulnerability_scores = vulnerability_scores
            except Exception as e:
                vulnerability_scores = {}

            # LLM 增强
            update_task(task_id, progress='正在执行LLM增强...')
            config = load_config()
            llm_backend = 'openai' if config.get('api_key') and config.get('api_endpoint') else 'mock'
            try:
                llm_results = pipeline.llm_generate(backend=llm_backend)
            except Exception as e:
                llm_results = {'success': False, 'error': str(e)}

            pipeline.print_summary()

            summary_lines = [
                f"设计文件: {os.path.basename(design_file)}",
                f"信号总数: {len(module_info)}",
                f"使用策略: {', '.join(strategy_groups.keys())}",
            ]
            for strategy, sigs in strategy_groups.items():
                summary_lines.append(f"  {strategy}: {len(sigs)} 个信号")

            update_task(
                task_id,
                status='completed',
                progress='加固完成',
                original_code=original_code,
                hardened_code=hardened_code,
                output_file=output_file,
                module_info={k: dict(v) for k, v in module_info.items()},
                strategy_map=strategy_map,
                strategy_groups=strategy_groups,
                aig_results=aig_results,
                fault_results=fault_results,
                vulnerability_scores=vulnerability_scores,
                llm_results=llm_results,
                summary='\n'.join(summary_lines),
                completed_at=datetime.now().isoformat(),
            )
            task_logs[task_id].put("\n[OK] 加固任务全部完成!")

            add_history({
                'task_id': task_id,
                'design_file': os.path.basename(design_file),
                'strategies': list(strategy_groups.keys()),
                'num_signals': len(module_info),
                'status': 'completed',
                'created_at': tasks.get(task_id, {}).get('created_at', ''),
                'completed_at': datetime.now().isoformat(),
                'optimization_goal': optimization_goal,
            })

        except Exception as e:
            task_logs[task_id].put(f"[ERROR] 加固任务失败: {e}")
            update_task(task_id, status='failed', progress=f'失败: {e}', error=str(e))
            add_history({
                'task_id': task_id,
                'design_file': os.path.basename(design_file) if design_file else 'unknown',
                'strategies': strategies or [],
                'status': 'failed',
                'created_at': tasks.get(task_id, {}).get('created_at', ''),
                'completed_at': datetime.now().isoformat(),
                'error': str(e),
            })


# ===================================================================
# Flask 应用
# ===================================================================
app = Flask(__name__)
app.secret_key = 'web-gui-secret-key-change-in-production'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# ===================================================================
# HTML 模板
# ===================================================================
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RTL 加固工具 - Web GUI</title>
<style>
:root{--primary:#2563eb;--primary-dark:#1d4ed8;--primary-light:#dbeafe;--success:#16a34a;--warning:#d97706;--danger:#dc2626;--gray-50:#f9fafb;--gray-100:#f3f4f6;--gray-200:#e5e7eb;--gray-300:#d1d5db;--gray-400:#9ca3af;--gray-500:#6b7280;--gray-600:#4b5563;--gray-700:#374151;--gray-800:#1f2937;--gray-900:#111827;--radius:8px;--shadow:0 1px 3px rgba(0,0,0,0.1),0 1px 2px rgba(0,0,0,0.06);--shadow-lg:0 10px 15px -3px rgba(0,0,0,0.1),0 4px 6px -2px rgba(0,0,0,0.05)}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans SC',sans-serif;background:var(--gray-50);color:var(--gray-800);line-height:1.6}
.navbar{background:linear-gradient(135deg,var(--primary),#1e40af);color:white;padding:0 24px;height:60px;display:flex;align-items:center;justify-content:space-between;box-shadow:var(--shadow);position:sticky;top:0;z-index:100}
.navbar-brand{font-size:18px;font-weight:700;display:flex;align-items:center;gap:10px;color:white;text-decoration:none}
.navbar-menu{display:flex;gap:4px;list-style:none}
.navbar-menu a{color:rgba(255,255,255,0.85);text-decoration:none;padding:8px 14px;border-radius:6px;font-size:14px;transition:all .2s}
.navbar-menu a:hover,.navbar-menu a.active{background:rgba(255,255,255,0.15);color:white}
.navbar-toggle{display:none;background:none;border:none;color:white;font-size:24px;cursor:pointer}
@media(max-width:768px){.navbar-toggle{display:block}.navbar-menu{display:none;position:absolute;top:60px;left:0;right:0;background:var(--primary-dark);flex-direction:column;padding:8px}.navbar-menu.open{display:flex}.container{padding:16px}}
.container{max-width:1200px;margin:0 auto;padding:24px}
.card{background:white;border-radius:var(--radius);box-shadow:var(--shadow);padding:24px;margin-bottom:20px;border:1px solid var(--gray-200)}
.card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--gray-100)}
.card-title{font-size:18px;font-weight:600;color:var(--gray-900)}
.card-subtitle{font-size:14px;color:var(--gray-500)}
.steps{display:flex;gap:8px;margin-bottom:24px;overflow-x:auto;padding:4px 0}
.step{display:flex;align-items:center;gap:8px;padding:10px 18px;background:var(--gray-100);border-radius:20px;font-size:14px;color:var(--gray-500);white-space:nowrap;border:2px solid transparent;transition:all .3s}
.step.active{background:var(--primary-light);color:var(--primary);border-color:var(--primary);font-weight:600}
.step.completed{background:#dcfce7;color:var(--success);border-color:var(--success)}
.step-number{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;background:currentColor;color:white}
.btn{display:inline-flex;align-items:center;gap:6px;padding:10px 20px;border-radius:6px;font-size:14px;font-weight:500;border:none;cursor:pointer;transition:all .2s;text-decoration:none}
.btn-primary{background:var(--primary);color:white}.btn-primary:hover{background:var(--primary-dark);transform:translateY(-1px);box-shadow:0 4px 12px rgba(37,99,235,0.3)}
.btn-success{background:var(--success);color:white}.btn-success:hover{background:#15803d}
.btn-danger{background:var(--danger);color:white}.btn-danger:hover{background:#b91c1c}
.btn-outline{background:transparent;color:var(--gray-600);border:1px solid var(--gray-300)}.btn-outline:hover{background:var(--gray-100)}
.btn-sm{padding:6px 12px;font-size:12px}.btn:disabled{opacity:0.5;cursor:not-allowed;transform:none!important}
.form-group{margin-bottom:16px}
.form-label{display:block;font-size:14px;font-weight:500;color:var(--gray-700);margin-bottom:6px}
.form-control{width:100%;padding:10px 12px;border:1px solid var(--gray-300);border-radius:6px;font-size:14px;transition:border-color .2s;background:white}
.form-control:focus{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px rgba(37,99,235,0.15)}
textarea.form-control{font-family:'JetBrains Mono','Fira Code','Consolas',monospace;font-size:13px;min-height:120px;resize:vertical}
.code-viewer{border:1px solid var(--gray-200);border-radius:var(--radius);overflow:hidden;margin-top:8px}
.code-viewer-header{display:flex;justify-content:space-between;align-items:center;padding:8px 16px;background:var(--gray-100);border-bottom:1px solid var(--gray-200);font-size:13px;color:var(--gray-600)}
.code-viewer-body{padding:16px;background:#1e1e2e;color:#cdd6f4;font-family:'JetBrains Mono','Fira Code','Consolas',monospace;font-size:13px;line-height:1.6;overflow-x:auto;max-height:500px;overflow-y:auto;white-space:pre-wrap;word-break:break-all}
.code-viewer-body .kw{color:#89b4fa}.code-viewer-body .num{color:#a6e3a1}.code-viewer-body .cmt{color:#6c7086;font-style:italic}.code-viewer-body .str{color:#fab387}
.comparison{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
@media(max-width:768px){.comparison{grid-template-columns:1fr}}
.log-output{background:#1e1e2e;color:#a6e3a1;font-family:'JetBrains Mono','Fira Code','Consolas',monospace;font-size:12px;line-height:1.5;padding:16px;border-radius:var(--radius);max-height:400px;overflow-y:auto;white-space:pre-wrap}
.log-output .log-error{color:#f38ba8}.log-output .log-warn{color:#fab387}.log-output .log-info{color:#89b4fa}.log-output .log-ok{color:#a6e3a1}
.progress-bar{width:100%;height:8px;background:var(--gray-200);border-radius:4px;overflow:hidden;margin:12px 0}
.progress-bar-fill{height:100%;background:linear-gradient(90deg,var(--primary),#3b82f6);border-radius:4px;transition:width .5s ease;width:0%}
.progress-text{font-size:14px;color:var(--gray-600);text-align:center;margin-bottom:8px}
.strategy-tag{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:12px;font-size:12px;font-weight:500;background:var(--primary-light);color:var(--primary)}
.strategy-tag.tmr{background:#fee2e2;color:#b91c1c}.strategy-tag.parity{background:#dbeafe;color:#1d4ed8}.strategy-tag.cnt_comp{background:#dcfce7;color:#15803d}.strategy-tag.dice{background:#f3e8ff;color:#7c3aed}.strategy-tag.ecc{background:#fef3c7;color:#92400e}.strategy-tag.auto{background:var(--gray-100);color:var(--gray-600)}
.alert{padding:12px 16px;border-radius:var(--radius);font-size:14px;margin-bottom:16px}
.alert-info{background:var(--primary-light);color:var(--primary-dark)}.alert-success{background:#dcfce7;color:#15803d}.alert-warning{background:#fef3c7;color:#92400e}.alert-danger{background:#fee2e2;color:#b91c1c}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px}.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}.grid-4{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:16px}
@media(max-width:768px){.grid-2,.grid-3,.grid-4{grid-template-columns:1fr}}
.stat-card{text-align:center;padding:20px}.stat-value{font-size:32px;font-weight:700;color:var(--primary)}.stat-label{font-size:13px;color:var(--gray-500);margin-top:4px}
.drop-zone{border:2px dashed var(--gray-300);border-radius:var(--radius);padding:40px;text-align:center;cursor:pointer;transition:all .3s;background:var(--gray-50)}
.drop-zone:hover,.drop-zone.dragover{border-color:var(--primary);background:var(--primary-light)}
.drop-zone-icon{font-size:48px;color:var(--gray-400);margin-bottom:8px}.drop-zone-text{font-size:16px;color:var(--gray-600)}.drop-zone-hint{font-size:13px;color:var(--gray-400);margin-top:4px}
.file-list{list-style:none;margin-top:12px}
.file-item{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:var(--gray-50);border-radius:6px;margin-bottom:6px;border:1px solid var(--gray-200)}
.file-item .file-info{display:flex;align-items:center;gap:10px}.file-item .file-icon{font-size:20px}.file-item .file-name{font-weight:500}.file-item .file-size{font-size:12px;color:var(--gray-400)}
.checkbox-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}
.checkbox-item{display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--gray-50);border-radius:6px;border:1px solid var(--gray-200);cursor:pointer;transition:all .2s}
.checkbox-item:hover{border-color:var(--primary)}.checkbox-item input[type=checkbox]{width:16px;height:16px;accent-color:var(--primary)}
.history-table{width:100%;border-collapse:collapse}
.history-table th{text-align:left;padding:10px 12px;font-size:12px;text-transform:uppercase;color:var(--gray-500);border-bottom:2px solid var(--gray-200)}
.history-table td{padding:10px 12px;font-size:14px;border-bottom:1px solid var(--gray-100)}
.history-table tr:hover td{background:var(--gray-50)}
.status-badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:500}
.status-badge.completed{background:#dcfce7;color:#15803d}.status-badge.running{background:#dbeafe;color:#1d4ed8;animation:pulse 1.5s infinite}.status-badge.failed{background:#fee2e2;color:#b91c1c}.status-badge.pending{background:var(--gray-100);color:var(--gray-600)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}
.metrics-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.metric-item{background:var(--gray-50);padding:16px;border-radius:var(--radius);border:1px solid var(--gray-200)}
.metric-label{font-size:12px;color:var(--gray-500);text-transform:uppercase;letter-spacing:.5px}
.metric-value{font-size:24px;font-weight:700;margin-top:4px}.metric-value.good{color:var(--success)}.metric-value.warn{color:var(--warning)}.metric-value.bad{color:var(--danger)}
.tabs{display:flex;gap:2px;border-bottom:2px solid var(--gray-200);margin-bottom:16px;flex-wrap:wrap}
.tab{padding:10px 18px;font-size:14px;cursor:pointer;border:none;background:transparent;color:var(--gray-500);border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .2s}
.tab:hover{color:var(--gray-700)}.tab.active{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}
.tab-content{display:none}.tab-content.active{display:block}
.toast{position:fixed;top:80px;right:24px;padding:12px 20px;border-radius:var(--radius);color:white;font-size:14px;box-shadow:var(--shadow-lg);z-index:1000;animation:slideIn .3s ease;max-width:400px}
.toast-success{background:var(--success)}.toast-error{background:var(--danger)}.toast-info{background:var(--primary)}
@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
.spinner{display:inline-block;width:16px;height:16px;border:2px solid rgba(255,255,255,0.3);border-top-color:white;border-radius:50%;animation:spin .6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.footer{text-align:center;padding:24px;color:var(--gray-400);font-size:13px}
.empty-state{text-align:center;padding:40px;color:var(--gray-400)}.empty-state-icon{font-size:64px;margin-bottom:16px}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--gray-300);border-radius:3px}
</style>
</head>
<body>
<nav class="navbar">
  <a href="/" class="navbar-brand"><span class="navbar-brand">&#9881; RTL 加固工具</span></a>
  <button class="navbar-toggle" onclick="document.getElementById('navMenu').classList.toggle('open')">&#9776;</button>
  <div class="navbar-menu" id="navMenu">
    <a href="/">仪表盘</a>
    <a href="/upload">上传文件</a>
    <a href="/history">历史记录</a>
    <a href="/config">配置</a>
  </div>
</nav>
<div class="container" id="pageContent">
<script>
const _path=window.location.pathname;
document.querySelectorAll('#navMenu a').forEach(function(a){a.classList.toggle('active',a.getAttribute('href')===_path)});
function showToast(m,t){t=t||'info';var e=document.createElement('div');e.className='toast toast-'+t;e.textContent=m;document.body.appendChild(e);setTimeout(function(){e.remove()},3000)}
function navigateTo(u){window.location.href=u}
function switchTab(btn,id){btn.parentNode.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active')});btn.classList.add('active');var parent=btn.closest('.card')||document;parent.querySelectorAll('.tab-content').forEach(function(tc){tc.classList.remove('active')});var target=document.getElementById(id);if(target)target.classList.add('active')}
{% if page=='dashboard' %}
document.getElementById('pageContent').innerHTML='\
<div class="card"><div class="card-header"><div><div class="card-title">RTL 加固工具 - 仪表盘</div><div class="card-subtitle">基于 HardeningPipeline 的远程 RTL 加固服务</div></div></div>\
<div class="grid-4">\
<div class="stat-card card"><div class="stat-value">{{stats.total_tasks}}</div><div class="stat-label">总任务数</div></div>\
<div class="stat-card card"><div class="stat-value" style="color:var(--success)">{{stats.completed_tasks}}</div><div class="stat-label">已完成</div></div>\
<div class="stat-card card"><div class="stat-value" style="color:var(--primary)">{{stats.running_tasks}}</div><div class="stat-label">运行中</div></div>\
<div class="stat-card card"><div class="stat-value">{{stats.strategies_count}}</div><div class="stat-label">可用策略</div></div>\
</div>\
<div style="margin-top:16px;display:flex;gap:12px;flex-wrap:wrap"><a href="/upload" class="btn btn-primary">&#128194; 上传设计文件</a><a href="/history" class="btn btn-outline">&#128214; 查看历史记录</a></div></div>\
<div class="card"><div class="card-header"><div class="card-title">加固步骤指南</div></div>\
<div class="steps"><div class="step completed"><span class="step-number">1</span> 上传设计文件</div><div class="step"><span class="step-number">2</span> 选择加固策略</div><div class="step"><span class="step-number">3</span> 执行加固</div><div class="step"><span class="step-number">4</span> 查看结果</div></div>\
<p style="color:var(--gray-500);font-size:14px">支持 Verilog (.v) / SystemVerilog (.sv) ZIP 压缩包上传。内置 6 种加固策略：TMR、奇偶校验、计数器比较器、DICE、ECC、自动选择。</p></div>\
<div class="card"><div class="card-header"><div class="card-title">可用加固策略</div></div><div class="grid-2">\
<div class="metric-item"><div class="metric-label">TMR</div><div style="font-size:13px;margin-top:4px;color:var(--gray-500)">3 副本 + 多数表决器 (3.0x)</div></div>\
<div class="metric-item"><div class="metric-label">奇偶校验</div><div style="font-size:13px;margin-top:4px;color:var(--gray-500)">奇偶位生成+检查 (0.03x)</div></div>\
<div class="metric-item"><div class="metric-label">cnt_comp</div><div style="font-size:13px;margin-top:4px;color:var(--gray-500)">计数器比较器 (0.3x)</div></div>\
<div class="metric-item"><div class="metric-label">DICE</div><div style="font-size:13px;margin-top:4px;color:var(--gray-500)">4 节点交叉耦合 (2.5x)</div></div>\
<div class="metric-item"><div class="metric-label">ECC</div><div style="font-size:13px;margin-top:4px;color:var(--gray-500)">SECDED 纠错码 (1.4x)</div></div>\
<div class="metric-item"><div class="metric-label">自动选择</div><div style="font-size:13px;margin-top:4px;color:var(--gray-500)">根据信号类型自动优选</div></div></div></div>';
{% elif page=='upload' %}
document.getElementById('pageContent').innerHTML='\
<div class="card"><div class="card-header"><div class="card-title">上传设计文件</div><div class="card-subtitle">步骤 1/4</div></div>\
<form id="uploadForm" enctype="multipart/form-data"><div class="drop-zone" id="dropZone"><div class="drop-zone-icon">&#128196;</div><div class="drop-zone-text">点击选择或拖拽文件到此处</div><div class="drop-zone-hint">支持 .v/.sv/.zip (最大100MB)</div></div>\
<input type="file" id="fileInput" name="file" style="display:none" accept=".v,.sv,.zip">\
<div id="fileInfo" style="display:none;margin-top:12px"><div class="file-item"><div class="file-info"><span class="file-icon">&#128196;</span><div><div class="file-name" id="fileName"></div><div class="file-size" id="fileSize"></div></div></div><button type="button" class="btn btn-sm btn-danger" onclick="clearFile()">移除</button></div></div>\
<div style="margin-top:16px;display:flex;gap:12px"><button type="submit" class="btn btn-primary" id="uploadBtn" disabled>&#128228; 上传文件</button><a href="/" class="btn btn-outline">返回</a></div></form></div>\
<div class="card"><div class="card-header"><div class="card-title">已上传文件</div></div>\
<div id="uploadedFiles">{% if files %}<ul class="file-list">{% for f in files %}\
<li class="file-item"><div class="file-info"><span class="file-icon">&#128196;</span><div><div class="file-name">{{f.name}}</div><div class="file-size">{{f.size}} | {{f.time}}</div></div></div>\
<div style="display:flex;gap:8px"><button class="btn btn-sm btn-primary" onclick="selectFile(\'{{f.path}}\',\'{{f.name}}\')">选择</button><a href="/upload?delete={{f.path|urlencode}}" class="btn btn-sm btn-danger">删除</a></div></li>\
{% endfor %}</ul>{% else %}<div class="empty-state"><div class="empty-state-icon">&#128203;</div><p>暂无上传文件</p></div>{% endif %}</div></div>\
<div class="card" id="hardenConfig" style="display:none"><div class="card-header"><div class="card-title">加固配置</div><div class="card-subtitle">步骤 2/4</div></div>\
<form id="hardenForm" action="/harden" method="POST"><input type="hidden" name="design_file" id="selectedFile">\
<div class="form-group"><label class="form-label">加固策略（可多选，auto为自动选择）</label><div class="checkbox-grid">\
<label class="checkbox-item"><input type="checkbox" name="strategies" value="tmr"><span>TMR</span></label>\
<label class="checkbox-item"><input type="checkbox" name="strategies" value="parity"><span>奇偶校验</span></label>\
<label class="checkbox-item"><input type="checkbox" name="strategies" value="cnt_comp"><span>计数器比较器</span></label>\
<label class="checkbox-item"><input type="checkbox" name="strategies" value="dice"><span>DICE</span></label>\
<label class="checkbox-item"><input type="checkbox" name="strategies" value="ecc"><span>ECC</span></label>\
<label class="checkbox-item"><input type="checkbox" name="strategies" value="auto" checked><span>自动选择</span></label></div></div>\
<div class="form-group"><label class="form-label">优化目标</label><select name="optimization_goal" class="form-control"><option value="area">面积优先</option><option value="reliability" selected>可靠性优先</option><option value="balanced">平衡</option></select></div>\
<div style="display:flex;gap:12px"><button type="submit" class="btn btn-success">&#9654; 开始加固</button><button type="button" class="btn btn-outline" onclick="hideConfig()">取消</button></div></form></div>';
var dz=document.getElementById('dropZone'),fi=document.getElementById('fileInput');
dz.addEventListener('click',function(){fi.click()});
dz.addEventListener('dragover',function(e){e.preventDefault();dz.classList.add('dragover')});
dz.addEventListener('dragleave',function(){dz.classList.remove('dragover')});
dz.addEventListener('drop',function(e){e.preventDefault();dz.classList.remove('dragover');if(e.dataTransfer.files.length){fi.files=e.dataTransfer.files;onFileSelect(e.dataTransfer.files[0])}});
fi.addEventListener('change',function(){if(fi.files.length)onFileSelect(fi.files[0])});
function onFileSelect(f){var ext=f.name.split('.').pop().toLowerCase();if(!['v','sv','zip'].includes(ext)){showToast('不支持的文件类型: .'+ext,'error');return}
document.getElementById('fileName').textContent=f.name;document.getElementById('fileSize').textContent=(f.size/1024/1024).toFixed(2)+' MB';document.getElementById('fileInfo').style.display='block';document.getElementById('uploadBtn').disabled=false}
function clearFile(){fi.value='';document.getElementById('fileInfo').style.display='none';document.getElementById('uploadBtn').disabled=true}
document.getElementById('uploadForm').addEventListener('submit',async function(e){e.preventDefault();var file=fi.files[0];if(!file)return;var btn=document.getElementById('uploadBtn');btn.disabled=true;btn.innerHTML='<span class="spinner"></span> 上传中...';var fd=new FormData();fd.append('file',file);try{var r=await fetch('/upload',{method:'POST',body:fd});var d=await r.json();if(d.success){showToast('上传成功: '+d.filename,'success');clearFile();setTimeout(function(){navigateTo('/upload')},1000)}else{showToast('上传失败: '+(d.error||'未知错误'),'error');btn.disabled=false;btn.innerHTML='&#128228; 上传文件'}}catch(err){showToast('上传失败: '+err.message,'error');btn.disabled=false;btn.innerHTML='&#128228; 上传文件'}});
function selectFile(p,n){document.getElementById('selectedFile').value=p;document.getElementById('hardenConfig').style.display='block';document.getElementById('hardenConfig').scrollIntoView({behavior:'smooth'});document.querySelectorAll('#hardenForm input[name="strategies"]').forEach(function(cb){cb.checked=cb.value==='auto'})}
function hideConfig(){document.getElementById('hardenConfig').style.display='none'}
document.getElementById('hardenForm').addEventListener('submit',async function(e){e.preventDefault();var fd=new FormData(this);var btn=this.querySelector('button[type="submit"]');btn.disabled=true;btn.innerHTML='<span class="spinner"></span> 启动中...';try{var r=await fetch('/harden',{method:'POST',body:new URLSearchParams(fd)});var d=await r.json();if(d.success){showToast('加固任务已启动','success');navigateTo('/status/'+d.task_id)}else{showToast('启动失败: '+(d.error||'未知错误'),'error');btn.disabled=false;btn.innerHTML='&#9654; 开始加固'}}catch(err){showToast('启动失败: '+err.message,'error');btn.disabled=false;btn.innerHTML='&#9654; 开始加固'}});
{% elif page=='status' %}
var _tid='{{task_id}}';
function updateStatus(){fetch('/api/status/'+_tid).then(function(r){return r.json()}).then(function(d){var s=d.status,prog=d.progress||'',sum=d.summary||'';var cls='pending',ico='&#9203;';if(s==='running'){cls='running';ico='&#9889;'}else if(s==='completed'){cls='completed';ico='&#9989;'}else if(s==='failed'){cls='failed';ico='&#10060;'}
document.getElementById('taskStatus').innerHTML='<span class="status-badge '+cls+'">'+ico+' '+s+'</span>';document.getElementById('taskProgress').textContent=prog
if(s==='completed'){document.getElementById('taskActions').style.display='block';clearInterval(_st);if(sum)document.getElementById('taskSummary').textContent=sum}
else if(s==='failed'){document.getElementById('taskError').style.display='block';document.getElementById('taskError').innerHTML='<div class="alert alert-danger">&#10060; '+(d.error||'任务失败')+'</div>';clearInterval(_st)}}).catch(function(){})}
function fetchLog(){fetch('/api/log/'+_tid).then(function(r){return r.json()}).then(function(d){var logDiv=document.getElementById('taskLog');if(d.logs&&d.logs.length){logDiv.innerHTML=d.logs.map(function(l){l=l.replace(/</g,'&lt;').replace(/>/g,'&gt;');if(l.includes('[ERROR]'))return '<div class="log-error">'+l+'</div>';if(l.includes('[WARN]'))return '<div class="log-warn">'+l+'</div>';if(l.includes('[OK]'))return '<div class="log-ok">'+l+'</div>';if(l.includes('[INFO]'))return '<div class="log-info">'+l+'</div>';return '<div>'+l+'</div>'}).join('');logDiv.scrollTop=logDiv.scrollHeight}}).catch(function(){})}
var _st=setInterval(function(){updateStatus();fetchLog()},1000);updateStatus();fetchLog();
document.getElementById('pageContent').innerHTML='\
<div class="card"><div class="card-header"><div class="card-title">加固任务状态</div><div id="taskStatus" class="status-badge pending">&#9203; pending</div></div>\
<div class="progress-bar"><div class="progress-bar-fill" id="progressFill" style="width:0%"></div></div><div class="progress-text" id="taskProgress">正在初始化...</div></div>\
<div class="card"><div class="card-header"><div class="card-title">执行日志</div></div><div class="log-output" id="taskLog" style="max-height:500px"><div>等待日志输出...</div></div></div>\
<div id="taskActions" style="display:none"><div style="display:flex;gap:12px;margin-bottom:16px"><a href="/result/'+_tid+'" class="btn btn-primary">&#128269; 查看结果</a><button class="btn btn-outline" onclick="navigateTo(\'/upload\')">&#128194; 新任务</button></div>\
<div class="card"><div class="card-header"><div class="card-title">任务摘要</div></div><pre id="taskSummary" style="font-size:13px;color:var(--gray-600);white-space:pre-wrap"></pre></div></div>\
<div id="taskError" style="display:none"></div>';
{% elif page=='result' %}
var _rid='{{task_id}}';
function loadResult(){fetch('/api/result/'+_rid).then(function(r){return r.json()}).then(function(d){if(!d){document.getElementById('pageContent').innerHTML='<div class="alert alert-danger">任务不存在</div>';return}
var s=d.status;if(s!=='completed'){document.getElementById('pageContent').innerHTML='<div class="alert alert-warning">任务尚未完成，当前状态: '+s+'</div><a href="/status/'+_rid+'" class="btn btn-primary">查看进度</a>';return}
var oc=d.original_code||'// 无原始代码',hc=d.hardened_code||'// 无加固代码',sm=d.strategy_map||{},sg=d.strategy_groups||{},aig=d.aig_results||{},ft=d.fault_results||{},vuln=d.vulnerability_scores||{},llm=d.llm_results||{},sum=d.summary||'';
var stTags='',sDesc={tmr:'TMR',parity:'奇偶校验',cnt_comp:'计数器比较器',dice:'DICE',ecc:'ECC'};
for(var sk in sg){if(sg.hasOwnProperty(sk))stTags+='<span class="strategy-tag '+sk+'">'+(sDesc[sk]||sk)+': '+sg[sk].length+'个</span> '}
var fImpr=ft.improvement?(ft.improvement*100).toFixed(1):'N/A',fAvf=ft.average_avf?(ft.average_avf*100).toFixed(1):'N/A';
function hl(c){c=c.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');var kws=['module','endmodule','input','output','inout','wire','reg','assign','always','posedge','negedge','or','begin','end','if','else','case','endcase','default','for','while','parameter','localparam','function','endfunction','generate','endgenerate','genvar','integer','real','initial','final','repeat','wait','forever','signed','unsigned'];kws.forEach(function(kw){var re=new RegExp('\\b'+kw+'\\b','gi');c=c.replace(re,'<span class="kw">'+kw+'</span>')});c=c.replace(/(\b\d+'(?:[bdh])[0-9a-fA-F_]+\b|\b\d+\b)/g,'<span class="num">$1</span>');c=c.replace(/(\/\/[^\n]*)/g,'<span class="cmt">$1</span>');c=c.replace(/("[^"]*")/g,'<span class="str">$1</span>');return c}
document.getElementById('pageContent').innerHTML='\
<div class="card"><div class="card-header"><div class="card-title">加固结果 #'+_rid+'</div><span class="status-badge completed">&#9989; 已完成</span></div>\
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px"><a href="/download/'+_rid+'" class="btn btn-success btn-sm">&#128229; 下载加固代码</a><button class="btn btn-outline btn-sm" onclick="navigateTo(\'/upload\')">&#128194; 新任务</button></div>\
<div style="margin-bottom:8px;font-size:13px;color:var(--gray-500)">应用策略:</div><div style="display:flex;gap:6px;flex-wrap:wrap">'+stTags+'</div></div>\
<div class="card"><div class="tabs"><button class="tab active" onclick="switchTab(this,\'tabCode\')">代码对比</button><button class="tab" onclick="switchTab(this,\'tabMetrics\')">分析指标</button><button class="tab" onclick="switchTab(this,\'tabAIG\')">AIG分析</button><button class="tab" onclick="switchTab(this,\'tabFault\')">故障注入</button><button class="tab" onclick="switchTab(this,\'tabLLM\')">LLM增强</button><button class="tab" onclick="switchTab(this,\'tabSignals\')">信号映射</button></div>\
<div id="tabCode" class="tab-content active"><div class="card-header"><div class="card-title">代码对比</div></div><div class="comparison"><div><div class="code-viewer-header">原始代码</div><div class="code-viewer-body">'+hl(oc)+'</div></div><div><div class="code-viewer-header">加固后代码</div><div class="code-viewer-body">'+hl(hc)+'</div></div></div></div>\
<div id="tabMetrics" class="tab-content"><div class="card-header"><div class="card-title">加固指标</div></div><pre style="font-size:13px;color:var(--gray-600);white-space:pre-wrap;background:var(--gray-50);padding:16px;border-radius:6px">'+(sum||'无摘要')+'</pre>\
<div class="metrics-grid" style="margin-top:16px"><div class="metric-item"><div class="metric-label">信号总数</div><div class="metric-value">'+Object.keys(sm).length+'</div></div>\
<div class="metric-item"><div class="metric-label">使用策略数</div><div class="metric-value">'+Object.keys(sg).length+'</div></div>\
<div class="metric-item"><div class="metric-label">故障注入改善</div><div class="metric-value good">'+fImpr+'%</div></div>\
<div class="metric-item"><div class="metric-label">原始AVF</div><div class="metric-value warn">'+fAvf+'%</div></div></div></div>\
<div id="tabAIG" class="tab-content"><div class="card-header"><div class="card-title">AIG 分析结果</div></div>\
<div class="metrics-grid"><div class="metric-item"><div class="metric-label">AND门数</div><div class="metric-value">'+(aig.and_count||'N/A')+'</div></div>\
<div class="metric-item"><div class="metric-label">输入数(PI)</div><div class="metric-value">'+(aig.pi_count||'N/A')+'</div></div>\
<div class="metric-item"><div class="metric-label">输出数(PO)</div><div class="metric-value">'+(aig.po_count||'N/A')+'</div></div>\
<div class="metric-item"><div class="metric-label">锁存器数</div><div class="metric-value">'+(aig.latches||'N/A')+'</div></div></div></div>\
<div id="tabFault" class="tab-content"><div class="card-header"><div class="card-title">故障注入结果</div></div>\
<div class="metrics-grid"><div class="metric-item"><div class="metric-label">注入次数</div><div class="metric-value">'+(ft.num_injections||'N/A')+'</div></div>\
<div class="metric-item"><div class="metric-label">平均AVF</div><div class="metric-value warn">'+fAvf+'%</div></div>\
<div class="metric-item"><div class="metric-label">加固后AVF</div><div class="metric-value good">'+(ft.hardened_avf?(ft.hardened_avf*100).toFixed(1):'N/A')+'%</div></div>\
<div class="metric-item"><div class="metric-label">改善幅度</div><div class="metric-value good">'+fImpr+'%</div></div></div></div>\
<div id="tabLLM" class="tab-content"><div class="card-header"><div class="card-title">LLM 增强结果</div></div>\
<div class="metrics-grid"><div class="metric-item"><div class="metric-label">后端</div><div class="metric-value">'+(llm.backend||'mock')+'</div></div>\
<div class="metric-item"><div class="metric-label">成功</div><div class="metric-value">'+(llm.success?'&#9989;':'&#10060;')+'</div></div></div>\
<pre style="font-size:13px;color:var(--gray-600);white-space:pre-wrap;background:var(--gray-50);padding:16px;border-radius:6px;margin-top:12px">'+(llm.explanation||'无LLM增强说明')+'</pre></div>\
<div id="tabSignals" class="tab-content"><div class="card-header"><div class="card-title">信号策略映射</div></div>\
<table class="history-table"><thead><tr><th>信号名</th><th>类型</th><th>策略</th><th>位宽</th></tr></thead><tbody>'+function(){var h='';for(var sk2 in sm){if(sm.hasOwnProperty(sk2)){var info=d.module_info&&d.module_info[sk2]||{};h+='<tr><td>'+sk2+'</td><td>'+(info.type||'')+'</td><td><span class="strategy-tag '+sm[sk2]+'">'+(sDesc[sm[sk2]]||sm[sk2])+'</span></td><td>'+(info.width||1)+'</td></tr>'}}return h}()+'</tbody></table></div></div>';}).catch(function(err){document.getElementById('pageContent').innerHTML='<div class="alert alert-danger">加载结果失败: '+err.message+'</div>'})}
loadResult();
{% elif page=='history' %}
document.getElementById('pageContent').innerHTML='<div class="card"><div class="card-header"><div class="card-title">历史加固记录</div></div>\
{% if history %}<table class="history-table"><thead><tr><th>任务ID</th><th>设计文件</th><th>策略</th><th>信号数</th><th>状态</th><th>时间</th><th>操作</th></tr></thead><tbody>\
{% for h in history %}<tr><td style="font-family:monospace;font-size:12px">{{h.task_id}}</td><td>{{h.design_file}}</td><td>{% if h.strategies %}{{h.strategies|join:", "}}{% endif %}</td><td>{{h.num_signals or "-"}}</td>\
<td><span class="status-badge {{h.status}}">{{h.status}}</span></td><td style="font-size:12px;color:var(--gray-500)">{{h.created_at[:16] if h.created_at else "-"}}</td>\
<td>{% if h.status=="completed" %}<a href="/result/{{h.task_id}}" class="btn btn-sm btn-primary">查看</a>{% elif h.status=="running" or h.status=="pending" %}<a href="/status/{{h.task_id}}" class="btn btn-sm btn-outline">进度</a>{% endif %}</td></tr>\
{% endfor %}</tbody></table>\
{% else %}<div class="empty-state"><div class="empty-state-icon">&#128214;</div><p>暂无历史记录</p></div>{% endif %}</div>';
{% elif page=='config' %}
document.getElementById('pageContent').innerHTML='<div class="card"><div class="card-header"><div class="card-title">API Key 配置</div></div>\
<form id="configForm"><div class="form-group"><label class="form-label">API Key</label><input type="password" name="api_key" class="form-control" value="{{config.api_key}}" placeholder="输入 LLM API Key"></div>\
<div class="form-group"><label class="form-label">API Endpoint</label><input type="text" name="api_endpoint" class="form-control" value="{{config.api_endpoint}}" placeholder="例如: https://api.openai.com/v1"></div>\
<div class="form-group"><label class="form-label">最大上传大小 (MB)</label><input type="number" name="max_upload_size_mb" class="form-control" value="{{config.max_upload_size_mb}}"></div>\
<div style="display:flex;gap:12px"><button type="submit" class="btn btn-primary">保存配置</button><a href="/" class="btn btn-outline">返回</a></div></form></div>\
<div class="card"><div class="card-header"><div class="card-title">关于</div></div><p style="color:var(--gray-500);font-size:14px">RTL 加固工具 Web GUI v1.0<br>基于 Flask 框架开发，通过 HardeningPipeline 实现 RTL 加固功能。</p></div>';
document.getElementById('configForm').addEventListener('submit',async function(e){e.preventDefault();var fd=new FormData(this);var btn=this.querySelector('button[type="submit"]');btn.disabled=true;btn.innerHTML='<span class="spinner"></span> 保存中...';try{var r=await fetch('/config',{method:'POST',body:new URLSearchParams(fd)});var d=await r.json();if(d.success){showToast('配置已保存','success')}else{showToast('保存失败: '+(d.error||'未知错误'),'error')}}catch(err){showToast('保存失败: '+err.message,'error')};btn.disabled=false;btn.innerHTML='保存配置'});
{% endif %}
</script>
</div>
<div class="footer">RTL 加固工具 Web GUI &copy; 2026</div>
</body>
</html>"""


# ===================================================================
# Flask 路由
# ===================================================================

def get_dashboard_stats():
    """获取仪表盘统计数据"""
    history = load_history()
    total = len(history) + len([t for t in tasks.values() if t.get('status') in ('running', 'pending')])
    completed = sum(1 for h in history if h.get('status') == 'completed')
    running = sum(1 for t in tasks.values() if t.get('status') == 'running')
    running += sum(1 for h in history if h.get('status') == 'running')
    return {
        'total_tasks': total or 0,
        'completed_tasks': completed or 0,
        'running_tasks': running or 0,
        'strategies_count': 6,
    }


def get_uploaded_files():
    """获取已上传文件列表"""
    files = []
    if not os.path.exists(_UPLOAD_DIR):
        return files
    for f in sorted(os.listdir(_UPLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(_UPLOAD_DIR, x)), reverse=True):
        fpath = os.path.join(_UPLOAD_DIR, f)
        if os.path.isfile(fpath):
            size = os.path.getsize(fpath)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            files.append({
                'name': f,
                'path': fpath,
                'size': f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB",
                'time': mtime.strftime('%Y-%m-%d %H:%M'),
            })
    return files


@app.route('/')
def index():
    """Dashboard 首页"""
    stats = get_dashboard_stats()
    return render_template_string(INDEX_HTML, page='dashboard', stats=stats)


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """文件上传页面"""
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有选择文件'})

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '文件名为空'})

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': f'不支持的文件类型: {file.filename}'})

        # 保存文件
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        filepath = os.path.join(_UPLOAD_DIR, filename)
        file.save(filepath)

        # 如果是ZIP则解压
        if filename.endswith('.zip'):
            extract_dir = filepath.replace('.zip', '')
            os.makedirs(extract_dir, exist_ok=True)
            rtl_files = extract_zip(filepath, extract_dir)
            if rtl_files:
                return jsonify({
                    'success': True,
                    'filename': filename,
                    'extracted': [os.path.basename(f) for f in rtl_files],
                    'files': rtl_files,
                })
            return jsonify({'success': False, 'error': 'ZIP文件中未找到 .v/.sv 文件'})

        return jsonify({'success': True, 'filename': filename})

    # GET 请求
    files = get_uploaded_files()
    # 处理删除
    delete_path = request.args.get('delete')
    if delete_path and os.path.exists(delete_path):
        if os.path.isdir(delete_path):
            shutil.rmtree(delete_path)
        else:
            os.remove(delete_path)
        # 同时删除对应的 zip 文件
        zip_path = delete_path.replace('_extracted', '.zip') if '_extracted' in delete_path else None
        if zip_path and os.path.exists(zip_path):
            os.remove(zip_path)
        return render_template_string(INDEX_HTML, page='upload', files=get_uploaded_files())

    return render_template_string(INDEX_HTML, page='upload', files=files)


@app.route('/harden', methods=['POST'])
def harden():
    """发起加固任务（异步执行）"""
    design_file = request.form.get('design_file', '')
    strategies = request.form.getlist('strategies')
    optimization_goal = request.form.get('optimization_goal', 'reliability')

    if not design_file or not os.path.exists(design_file):
        return jsonify({'success': False, 'error': '设计文件不存在'})

    # 创建任务
    task_id = make_task_id()
    tasks[task_id] = {
        'task_id': task_id,
        'design_file': design_file,
        'strategies': strategies,
        'optimization_goal': optimization_goal,
        'status': 'pending',
        'progress': '排队等待中...',
        'created_at': datetime.now().isoformat(),
    }

    # 启动后台线程
    thread = threading.Thread(
        target=run_harden_task,
        args=(task_id, design_file, strategies, optimization_goal),
        daemon=True,
    )
    thread.start()

    return jsonify({'success': True, 'task_id': task_id})


@app.route('/status/<task_id>')
def status_page(task_id):
    """查看加固任务状态页面"""
    task = get_task(task_id)
    if not task:
        # 检查历史记录
        history = load_history()
        for h in history:
            if h.get('task_id') == task_id:
                return render_template_string(INDEX_HTML, page='result', task_id=task_id)
        return render_template_string(INDEX_HTML, page='status', task_id=task_id)
    return render_template_string(INDEX_HTML, page='status', task_id=task_id)


@app.route('/result/<task_id>')
def result_page(task_id):
    """查看加固结果页面"""
    return render_template_string(INDEX_HTML, page='result', task_id=task_id)


@app.route('/history')
def history_page():
    """查看历史加固记录"""
    history = load_history()
    return render_template_string(INDEX_HTML, page='history', history=history)


@app.route('/config', methods=['GET', 'POST'])
def config_page():
    """API Key 配置页面"""
    if request.method == 'POST':
        cfg = load_config()
        cfg['api_key'] = request.form.get('api_key', cfg['api_key'])
        cfg['api_endpoint'] = request.form.get('api_endpoint', cfg['api_endpoint'])
        try:
            cfg['max_upload_size_mb'] = int(request.form.get('max_upload_size_mb', cfg['max_upload_size_mb']))
        except:
            pass
        save_config(cfg)
        return jsonify({'success': True})

    cfg = load_config()
    return render_template_string(INDEX_HTML, page='config', config=cfg)


@app.route('/download/<task_id>')
def download_result(task_id):
    """下载加固结果文件"""
    task = get_task(task_id)
    if not task or task.get('status') != 'completed':
        return jsonify({'error': '任务未完成或不存在'}), 404

    output_file = task.get('output_file')
    if not output_file or not os.path.exists(output_file):
        return jsonify({'error': '输出文件不存在'}), 404

    return send_file(output_file, as_attachment=True)


# ===================================================================
# API 路由（供前端 AJAX 调用）
# ===================================================================

@app.route('/api/status/<task_id>')
def api_status(task_id):
    """获取任务状态（JSON）"""
    task = get_task(task_id)
    if not task:
        return jsonify({'status': 'not_found', 'error': '任务不存在'})
    return jsonify({
        'status': task.get('status', 'unknown'),
        'progress': task.get('progress', ''),
        'summary': task.get('summary', ''),
        'error': task.get('error', ''),
    })


@app.route('/api/log/<task_id>')
def api_log(task_id):
    """获取任务日志（JSON），轮询调用"""
    logs = []
    q = task_logs.get(task_id)
    if q:
        while not q.empty():
            try:
                logs.append(q.get_nowait())
            except queue.Empty:
                break
    return jsonify({'logs': logs})


@app.route('/api/result/<task_id>')
def api_result(task_id):
    """获取任务结果（JSON）"""
    task = get_task(task_id)
    if not task:
        # 检查历史
        history = load_history()
        for h in history:
            if h.get('task_id') == task_id and h.get('status') == 'completed':
                # 从历史记录中无法获取完整数据，返回基本信息
                return jsonify({
                    'status': 'completed',
                    'design_file': h.get('design_file', ''),
                    'strategy_map': {},
                    'strategy_groups': {},
                    'summary': f"设计文件: {h.get('design_file', '')}\n策略: {', '.join(h.get('strategies', []))}\n信号数: {h.get('num_signals', 0)}",
                })
        return jsonify(None)
    return jsonify({
        'status': task.get('status', 'unknown'),
        'original_code': task.get('original_code', ''),
        'hardened_code': task.get('hardened_code', ''),
        'strategy_map': task.get('strategy_map', {}),
        'strategy_groups': task.get('strategy_groups', {}),
        'module_info': task.get('module_info', {}),
        'aig_results': task.get('aig_results', {}),
        'fault_results': task.get('fault_results', {}),
        'vulnerability_scores': task.get('vulnerability_scores', {}),
        'llm_results': task.get('llm_results', {}),
        'summary': task.get('summary', ''),
    })


# ===================================================================
# 入口
# ===================================================================

if __name__ == '__main__':
    if not FLASK_AVAILABLE:
        print("=" * 60)
        print("  [ERROR] Flask 未安装!")
        print("  请执行: pip install flask")
        print("=" * 60)
        sys.exit(1)

    print("=" * 60)
    print("  RTL 加固工具 - Web GUI")
    print("=" * 60)
    print(f"  * 访问地址: http://0.0.0.0:5000")
    print(f"  * 局域网访问: http://<本机IP>:5000")
    print(f"  * 上传目录: {_UPLOAD_DIR}")
    print(f"  * 输出目录: {_OUTPUT_DIR}")
    print(f"  * 历史记录: {_HISTORY_FILE}")
    print("=" * 60)
    print("  按 Ctrl+C 停止服务")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
