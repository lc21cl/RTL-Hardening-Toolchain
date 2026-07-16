#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""web_gui.py — 基于 FastAPI 的 Web 可视化界面

提供 RTL 加固工具链的 Web 可视化界面，所有 HTML/CSS/JS 均内嵌于本模块，
不依赖外部静态文件或 CDN。

功能页面:
  - 仪表盘 (/): 工具链状态、可用加固策略数量、模型信息
  - RTL 加固 (/harden): 输入 RTL 代码，选择策略，查看加固结果（带语法高亮）
  - 脆弱性分析 (/vulnerability): 输入 RTL 代码，以表格展示脆弱节点列表
  - 策略对比 (/compare): 勾选策略，查看面积开销/可靠性/延迟/功耗对比表与推荐策略

页面通过 fetch 调用已有的 REST API 端点:
  /api/health, /api/strategies, /api/harden, /api/vulnerability, /api/compare

用法:
    python web_gui.py              # 直接启动，默认端口 8080
    uvicorn web_gui:app --port 8080  # 通过 uvicorn 启动
"""

import os
import sys
import threading
from typing import Any, Callable, Dict, Optional

# 确保能导入同目录下的其他模块
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# ---------------------------------------------------------------------------
# FastAPI 可用性检查
# ---------------------------------------------------------------------------
try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None  # type: ignore
    HTMLResponse = None  # type: ignore
    uvicorn = None  # type: ignore

_WEB_GUI_PORT = 8080

# ---------------------------------------------------------------------------
# 创建 FastAPI 应用
# 优先复用 api_server 中已注册 /api/* 路由的 app 实例，使页面与 API 同源。
# 若 api_server 导入失败则创建独立 app，页面仍可渲染但 API 调用会返回 404。
# ---------------------------------------------------------------------------
if FASTAPI_AVAILABLE:
    try:
        from api_server import app  # noqa: E402
        _API_AVAILABLE = True
    except Exception:
        app = FastAPI(title="RTL 加固工具链 Web GUI", version="1.0.0")
        _API_AVAILABLE = False
else:
    app = None  # type: ignore
    _API_AVAILABLE = False

# ---------------------------------------------------------------------------
# 导航配置
# ---------------------------------------------------------------------------
_NAV_ITEMS = [
    ("/", "仪表盘", "dashboard"),
    ("/harden", "RTL 加固", "harden"),
    ("/vulnerability", "脆弱性分析", "vulnerability"),
    ("/compare", "策略对比", "compare"),
]

# ---------------------------------------------------------------------------
# 内联样式表（深色主题，flexbox/grid 布局）
# ---------------------------------------------------------------------------
_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
:root {
    --bg: #0d1117;
    --surface: #161b22;
    --surface-hover: #1c2128;
    --border: #30363d;
    --text: #e6edf3;
    --text-dim: #8b949e;
    --accent: #58a6ff;
    --green: #3fb950;
    --red: #f85149;
    --yellow: #d29922;
    --orange: #db6d28;
    --purple: #d2a8ff;
    --radius: 8px;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
}
/* 顶部导航栏 */
.navbar {
    display: flex;
    align-items: center;
    gap: 24px;
    padding: 0 24px;
    height: 56px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 100;
}
.nav-brand { font-size: 16px; font-weight: 700; white-space: nowrap; }
.nav-links { display: flex; gap: 4px; flex: 1; }
.nav-item {
    padding: 8px 16px;
    color: var(--text-dim);
    text-decoration: none;
    border-radius: 6px;
    font-size: 14px;
    transition: all 0.15s;
}
.nav-item:hover { background: var(--surface-hover); color: var(--text); }
.nav-item.active { background: rgba(88,166,255,0.15); color: var(--accent); }
.api-badge { font-size: 12px; padding: 4px 12px; border-radius: 12px; font-weight: 600; white-space: nowrap; }
.api-badge.ok { background: rgba(63,185,80,0.15); color: var(--green); }
.api-badge.err { background: rgba(248,81,73,0.15); color: var(--red); }
/* 主容器 */
.container { max-width: 1280px; margin: 0 auto; padding: 24px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 24px; font-weight: 700; }
.page-header .subtitle { color: var(--text-dim); font-size: 14px; margin-top: 4px; }
/* 卡片 */
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 20px;
}
.card h2 {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
}
/* 统计网格 */
.stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}
.stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
}
.stat-card .label { color: var(--text-dim); font-size: 13px; margin-bottom: 8px; }
.stat-card .value { font-size: 28px; font-weight: 700; }
.stat-card .value.green { color: var(--green); }
.stat-card .value.red { color: var(--red); }
.stat-card .value.accent { color: var(--accent); }
.stat-card .detail { color: var(--text-dim); font-size: 12px; margin-top: 8px; word-break: break-all; }
/* 两栏布局 */
.layout-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 900px) { .layout-grid { grid-template-columns: 1fr; } }
/* 代码编辑器（textarea + 行号） */
.editor-wrap {
    display: flex;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
    margin-bottom: 16px;
}
.line-numbers {
    padding: 12px 8px;
    text-align: right;
    color: var(--text-dim);
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.5;
    user-select: none;
    background: var(--surface);
    border-right: 1px solid var(--border);
    min-width: 44px;
    overflow: hidden;
    white-space: pre;
}
.code-input {
    flex: 1;
    background: var(--bg);
    color: var(--text);
    border: none;
    outline: none;
    padding: 12px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.5;
    resize: vertical;
    min-height: 220px;
    white-space: pre;
    overflow: auto;
    tab-size: 4;
}
/* 表单 */
.form-row { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.form-row label { font-size: 14px; color: var(--text-dim); white-space: nowrap; }
select, input[type="text"] {
    background: var(--bg);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 14px;
    outline: none;
    flex: 1;
}
select:focus, input:focus { border-color: var(--accent); }
/* 按钮 */
.btn {
    padding: 10px 24px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    transition: opacity 0.15s;
    text-decoration: none;
    display: inline-block;
}
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
/* 表格 */
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }
th { color: var(--text-dim); font-weight: 600; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }
tr:hover td { background: var(--surface-hover); }
/* 代码结果（语法高亮） */
.code-result {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 16px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.5;
    overflow: auto;
    max-height: 500px;
    white-space: pre;
    min-height: 220px;
}
.code-result .kw { color: #ff7b72; }
.code-result .cm { color: #8b949e; font-style: italic; }
.code-result .st { color: #a5d6ff; }
.code-result .nm { color: #79c0ff; }
.code-result .op { color: var(--purple); }
/* 提示框 */
.alert { padding: 12px 16px; border-radius: 6px; font-size: 14px; margin-top: 16px; }
.alert-info { background: rgba(88,166,255,0.1); color: var(--accent); border: 1px solid rgba(88,166,255,0.3); }
.alert-success { background: rgba(63,185,80,0.1); color: var(--green); border: 1px solid rgba(63,185,80,0.3); }
.alert-error { background: rgba(248,81,73,0.1); color: var(--red); border: 1px solid rgba(248,81,73,0.3); }
/* 加载动画 */
.loading {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    vertical-align: middle;
    margin-right: 6px;
}
@keyframes spin { to { transform: rotate(360deg); } }
/* 策略多选网格 */
.checkbox-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 8px;
    margin-bottom: 16px;
}
.checkbox-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
}
.checkbox-item:hover { border-color: var(--accent); }
.checkbox-item input { accent-color: var(--accent); }
/* 脆弱性分数条 */
.score-bar {
    display: inline-block;
    width: 60px;
    height: 6px;
    background: var(--border);
    border-radius: 3px;
    overflow: hidden;
    vertical-align: middle;
    margin-right: 8px;
}
.score-bar-fill { height: 100%; border-radius: 3px; }
/* 快速链接按钮组 */
.btn-group { display: flex; gap: 12px; flex-wrap: wrap; }
"""

# ---------------------------------------------------------------------------
# 公共 JavaScript（工具函数、行号同步、语法高亮）
# ---------------------------------------------------------------------------
_COMMON_JS = """\
// 封装 fetch，统一处理错误
function apiFetch(url, options) {
    return fetch(url, options).then(function(resp) {
        if (!resp.ok) {
            return resp.text().then(function(text) {
                var msg = 'HTTP ' + resp.status;
                try {
                    var err = JSON.parse(text);
                    if (err.detail) msg = err.detail;
                } catch (e) {}
                throw new Error(msg);
            });
        }
        return resp.json();
    });
}

// 显示提示框
function showAlert(id, type, message) {
    var el = document.getElementById(id);
    if (el) { el.className = 'alert alert-' + type; el.textContent = message; }
}
function showLoading(id, message) {
    var el = document.getElementById(id);
    if (el) { el.className = 'alert alert-info'; el.innerHTML = '<span class="loading"></span>' + message; }
}

// 初始化带行号的代码编辑器
function initEditor(textareaId, lineNumbersId) {
    var ta = document.getElementById(textareaId);
    var ln = document.getElementById(lineNumbersId);
    if (!ta || !ln) return;
    function updateLines() {
        var count = ta.value.split('\\n').length;
        var html = '';
        for (var i = 1; i <= count; i++) { html += i + '\\n'; }
        ln.textContent = html;
    }
    ta.addEventListener('input', updateLines);
    ta.addEventListener('scroll', function() { ln.scrollTop = ta.scrollTop; });
    updateLines();
}

// HTML 转义
function escapeHtml(text) {
    return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// RTL/Verilog 语法高亮（简单分词器）
function highlightRTL(code) {
    var tokens = [
        ['cm', /\\/\\/[^\\n]*|\\/\\*[\\s\\S]*?\\*\\//],
        ['st', /"(?:[^"\\\\]|\\\\.)*"/],
        ['kw', /\\b(?:module|endmodule|input|output|inout|wire|reg|logic|always|assign|begin|end|if|else|case|endcase|casex|casez|default|parameter|localparam|generate|endgenerate|genvar|integer|function|endfunction|task|endtask|posedge|negedge|initial|forever|while|for|repeat|wait|disable|fork|join|always_ff|always_comb|always_latch|timescale|define|include|ifdef|ifndef|endif|else|pragma)\\b/],
        ['nm', /\\b(?:\\d+'[bBoOdDhH][0-9a-fA-FxXzZ_]+|\\d+)\\b/]
    ];
    var combined = '';
    for (var i = 0; i < tokens.length; i++) { combined += '(' + tokens[i][1].source + ')|'; }
    combined = combined.slice(0, -1);
    var fullRe = new RegExp(combined, 'g');
    var result = '';
    var lastIndex = 0;
    var m;
    while ((m = fullRe.exec(code)) !== null) {
        if (m.index > lastIndex) { result += escapeHtml(code.substring(lastIndex, m.index)); }
        for (var i = 0; i < tokens.length; i++) {
            if (m[i + 1] !== undefined) {
                result += '<span class="' + tokens[i][0] + '">' + escapeHtml(m[0]) + '</span>';
                break;
            }
        }
        lastIndex = fullRe.lastIndex;
    }
    if (lastIndex < code.length) { result += escapeHtml(code.substring(lastIndex)); }
    return result;
}

// 加载策略列表
function loadStrategies(callback) {
    apiFetch('/api/strategies').then(function(data) {
        callback(data.strategies || []);
    }).catch(function() { callback([]); });
}

// 渲染可靠性星级
function renderStars(count) {
    var html = '';
    for (var i = 0; i < 5; i++) { html += i < count ? '\\u2605' : '\\u2606'; }
    return html;
}
"""

# ---------------------------------------------------------------------------
# HTML 页面模板（使用占位符替换，避免 f-string 花括号转义问题）
# ---------------------------------------------------------------------------
_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RTL 加固工具链</title>
    <style>
__CSS__
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="nav-brand">&#128295; RTL 加固工具链</div>
        <div class="nav-links">
__NAV__
        </div>
        <div class="__API_CLS__">__API_TXT__</div>
    </nav>
    <main class="container">
__CONTENT__
    </main>
    <script>
__COMMON_JS__
    </script>
__PAGE_JS_TAG__
</body>
</html>"""


def _render_page(active: str, html_content: str, page_js: str = "") -> str:
    """渲染带导航栏和公共样式的完整 HTML 页面。"""
    nav_html = ""
    for href, label, key in _NAV_ITEMS:
        cls = "nav-item active" if key == active else "nav-item"
        nav_html += '            <a href="{}" class="{}">{}</a>\n'.format(href, cls, label)

    api_text = "API 已连接" if _API_AVAILABLE else "API 未连接"
    api_cls = "api-badge ok" if _API_AVAILABLE else "api-badge err"

    page_js_tag = ""
    if page_js:
        page_js_tag = "    <script>\n{}\n    </script>".format(page_js)

    html = _PAGE_TEMPLATE
    html = html.replace("__CSS__", _CSS)
    html = html.replace("__NAV__", nav_html)
    html = html.replace("__API_CLS__", api_cls)
    html = html.replace("__API_TXT__", api_text)
    html = html.replace("__CONTENT__", html_content)
    html = html.replace("__COMMON_JS__", _COMMON_JS)
    html = html.replace("__PAGE_JS_TAG__", page_js_tag)
    return html


# ---------------------------------------------------------------------------
# 默认 RTL 示例代码
# ---------------------------------------------------------------------------
_SAMPLE_RTL = """\
module counter(
    input clk,
    input rst_n,
    input en,
    output reg [7:0] count
);
always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        count <= 8'b0;
    else if (en)
        count <= count + 1'b1;
end
endmodule"""


# ---------------------------------------------------------------------------
# 仪表盘页面
# ---------------------------------------------------------------------------
def _dashboard_content() -> tuple:
    html = """\
<div class="page-header">
    <h1>仪表盘</h1>
    <p class="subtitle">RTL 加固工具链状态总览</p>
</div>
<div class="stat-grid">
    <div class="stat-card">
        <div class="label">工具链状态</div>
        <div class="value" id="health-status">检测中...</div>
        <div class="detail" id="health-detail"></div>
    </div>
    <div class="stat-card">
        <div class="label">可用加固策略</div>
        <div class="value accent" id="strategy-count">-</div>
        <div class="detail" id="strategy-list-detail"></div>
    </div>
    <div class="stat-card">
        <div class="label">后端版本</div>
        <div class="value" id="version">-</div>
        <div class="detail" id="timestamp"></div>
    </div>
    <div class="stat-card">
        <div class="label">模型信息</div>
        <div class="value">GraphSAGE</div>
        <div class="detail">脆弱性预测 + MockLLM 加固生成</div>
    </div>
</div>
<div class="card">
    <h2>快速链接</h2>
    <p style="color: var(--text-dim); margin-bottom: 12px;">选择下方功能开始使用：</p>
    <div class="btn-group">
        <a href="/harden" class="btn btn-primary">RTL 加固</a>
        <a href="/vulnerability" class="btn btn-primary">脆弱性分析</a>
        <a href="/compare" class="btn btn-primary">策略对比</a>
    </div>
</div>"""

    js = """\
(function() {
    document.getElementById('health-status').textContent = '检测中...';

    apiFetch('/api/health').then(function(data) {
        document.getElementById('health-status').innerHTML = '<span style="color:var(--green)">\\u25cf 运行中</span>';
        document.getElementById('version').textContent = data.version || '-';
        document.getElementById('timestamp').textContent = '更新时间: ' + (data.timestamp || '-');
    }).catch(function(err) {
        document.getElementById('health-status').innerHTML = '<span style="color:var(--red)">\\u25cf 不可用</span>';
        document.getElementById('health-detail').textContent = err.message;
    });

    loadStrategies(function(strategies) {
        document.getElementById('strategy-count').textContent = strategies.length;
        if (strategies.length > 0) {
            var names = strategies.map(function(s) { return s.name; }).join(', ');
            document.getElementById('strategy-list-detail').textContent = names;
        } else {
            document.getElementById('strategy-list-detail').textContent = '无法获取策略列表';
        }
    });
})();"""
    return html, js


# ---------------------------------------------------------------------------
# RTL 加固页面
# ---------------------------------------------------------------------------
def _harden_content() -> tuple:
    html = """\
<div class="page-header">
    <h1>RTL 加固</h1>
    <p class="subtitle">输入 RTL 代码，选择加固策略，生成加固后的设计</p>
</div>
<div class="layout-grid">
    <div class="card">
        <h2>输入</h2>
        <div class="editor-wrap">
            <div class="line-numbers" id="harden-lines">1</div>
            <textarea id="harden-input" class="code-input" wrap="off" spellcheck="false" placeholder="在此输入 Verilog RTL 代码...">__SAMPLE__</textarea>
        </div>
        <div class="form-row">
            <label>加固策略</label>
            <select id="harden-strategy"><option value="">加载中...</option></select>
        </div>
        <button class="btn btn-primary" id="harden-btn" onclick="runHarden()">执行加固</button>
        <div id="harden-alert"></div>
    </div>
    <div class="card">
        <h2>加固结果</h2>
        <pre class="code-result" id="harden-result">加固结果将显示在此处...</pre>
        <div id="harden-meta" style="margin-top: 12px; font-size: 13px; color: var(--text-dim);"></div>
    </div>
</div>"""

    js = """\
initEditor('harden-input', 'harden-lines');

loadStrategies(function(strategies) {
    var sel = document.getElementById('harden-strategy');
    sel.innerHTML = '';
    if (strategies.length === 0) {
        sel.innerHTML = '<option value="">无可用策略</option>';
        return;
    }
    strategies.forEach(function(s) {
        var opt = document.createElement('option');
        opt.value = s.name;
        opt.textContent = s.name + ' \\u2014 ' + s.description;
        sel.appendChild(opt);
    });
});

function runHarden() {
    var code = document.getElementById('harden-input').value;
    var strategy = document.getElementById('harden-strategy').value;
    if (!code.trim()) { showAlert('harden-alert', 'error', '请输入 RTL 代码'); return; }
    if (!strategy) { showAlert('harden-alert', 'error', '请选择加固策略'); return; }

    var btn = document.getElementById('harden-btn');
    btn.disabled = true;
    showLoading('harden-alert', '正在执行加固...');

    apiFetch('/api/harden', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rtl_code: code, strategy: strategy })
    }).then(function(data) {
        if (data.success) {
            document.getElementById('harden-result').innerHTML = highlightRTL(data.hardened_rtl);
            var meta = '策略: ' + data.strategy;
            if (data.metadata && data.metadata.model) meta += ' | 模型: ' + data.metadata.model;
            document.getElementById('harden-meta').textContent = meta;
            showAlert('harden-alert', 'success', '加固完成！');
        } else {
            showAlert('harden-alert', 'error', '加固失败');
        }
    }).catch(function(err) {
        showAlert('harden-alert', 'error', '错误: ' + err.message);
    }).finally(function() {
        btn.disabled = false;
    });
}"""
    html = html.replace("__SAMPLE__", _SAMPLE_RTL)
    return html, js


# ---------------------------------------------------------------------------
# 脆弱性分析页面
# ---------------------------------------------------------------------------
def _vuln_content() -> tuple:
    html = """\
<div class="page-header">
    <h1>脆弱性分析</h1>
    <p class="subtitle">分析 RTL 代码中的脆弱节点，识别需要加固的关键信号</p>
</div>
<div class="card">
    <h2>输入 RTL 代码</h2>
    <div class="editor-wrap">
        <div class="line-numbers" id="vuln-lines">1</div>
        <textarea id="vuln-input" class="code-input" wrap="off" spellcheck="false" placeholder="在此输入 Verilog RTL 代码...">__SAMPLE__</textarea>
    </div>
    <button class="btn btn-primary" id="vuln-btn" onclick="runVulnAnalysis()">开始分析</button>
    <div id="vuln-alert"></div>
</div>
<div class="card" id="vuln-result-card" style="display:none;">
    <h2>脆弱节点列表</h2>
    <table>
        <thead>
            <tr>
                <th>节点名称</th>
                <th>类型</th>
                <th>脆弱性分数</th>
                <th>推荐策略</th>
            </tr>
        </thead>
        <tbody id="vuln-tbody"></tbody>
    </table>
    <div id="vuln-summary" style="margin-top: 16px; font-size: 14px; color: var(--text-dim);"></div>
</div>"""

    js = """\
initEditor('vuln-input', 'vuln-lines');

function runVulnAnalysis() {
    var code = document.getElementById('vuln-input').value;
    if (!code.trim()) { showAlert('vuln-alert', 'error', '请输入 RTL 代码'); return; }

    var btn = document.getElementById('vuln-btn');
    btn.disabled = true;
    showLoading('vuln-alert', '正在分析脆弱性...');

    apiFetch('/api/vulnerability', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rtl_code: code })
    }).then(function(data) {
        if (data.success) {
            renderVulnResults(data.results, data.summary);
            showAlert('vuln-alert', 'success', '分析完成');
        } else {
            showAlert('vuln-alert', 'error', '分析失败');
        }
    }).catch(function(err) {
        showAlert('vuln-alert', 'error', '错误: ' + err.message);
    }).finally(function() {
        btn.disabled = false;
    });
}

function renderVulnResults(results, summary) {
    var tbody = document.getElementById('vuln-tbody');
    tbody.innerHTML = '';
    var keys = Object.keys(results);
    if (keys.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-dim)">未检测到脆弱节点</td></tr>';
    } else {
        keys.forEach(function(name) {
            var info = results[name] || {};
            var score = info.vulnerability_score || 0;
            var type = info.type || info.node_type || '-';
            var rec = info.recommended_strategy || info.strategy || '-';
            var color = score > 0.7 ? 'var(--red)' : (score > 0.4 ? 'var(--yellow)' : 'var(--green)');
            var pct = Math.round(score * 100);
            var tr = document.createElement('tr');
            tr.innerHTML = '<td>' + escapeHtml(name) + '</td>'
                + '<td>' + escapeHtml(type) + '</td>'
                + '<td style="color:' + color + '"><span class="score-bar"><span class="score-bar-fill" style="width:' + pct + '%;background:' + color + '"></span></span>' + score.toFixed(3) + '</td>'
                + '<td>' + escapeHtml(rec) + '</td>';
            tbody.appendChild(tr);
        });
    }

    if (summary) {
        document.getElementById('vuln-summary').textContent =
            '共分析 ' + (summary.total_analyzed || 0) + ' 个节点，高脆弱性 ' + (summary.high_vulnerability_count || 0) + ' 个';
    }
    document.getElementById('vuln-result-card').style.display = 'block';
}"""
    html = html.replace("__SAMPLE__", _SAMPLE_RTL)
    return html, js


# ---------------------------------------------------------------------------
# 策略对比页面
# ---------------------------------------------------------------------------
def _compare_content() -> tuple:
    html = """\
<div class="page-header">
    <h1>策略对比</h1>
    <p class="subtitle">对比多种加固策略的面积开销、可靠性、延迟和功耗</p>
</div>
<div class="card">
    <h2>输入与选择</h2>
    <div class="editor-wrap">
        <div class="line-numbers" id="cmp-lines">1</div>
        <textarea id="cmp-input" class="code-input" wrap="off" spellcheck="false" placeholder="在此输入 Verilog RTL 代码...">__SAMPLE__</textarea>
    </div>
    <p style="color: var(--text-dim); margin-bottom: 8px;">勾选要对比的加固策略：</p>
    <div class="checkbox-grid" id="cmp-strategies"><span style="color:var(--text-dim)">加载策略列表...</span></div>
    <button class="btn btn-primary" id="cmp-btn" onclick="runCompare()">开始对比</button>
    <div id="cmp-alert"></div>
</div>
<div class="card" id="cmp-result-card" style="display:none;">
    <h2>对比结果</h2>
    <table>
        <thead>
            <tr>
                <th>策略</th>
                <th>面积开销</th>
                <th>可靠性</th>
                <th>延迟</th>
                <th>功耗开销</th>
            </tr>
        </thead>
        <tbody id="cmp-tbody"></tbody>
    </table>
    <div id="cmp-recommendation"></div>
</div>"""

    js = """\
initEditor('cmp-input', 'cmp-lines');

loadStrategies(function(strategies) {
    var container = document.getElementById('cmp-strategies');
    if (strategies.length === 0) {
        container.innerHTML = '<span style="color:var(--red)">无法获取策略列表，请检查 API 服务</span>';
        return;
    }
    container.innerHTML = '';
    strategies.forEach(function(s) {
        var label = document.createElement('label');
        label.className = 'checkbox-item';
        label.innerHTML = '<input type="checkbox" value="' + escapeHtml(s.name) + '"> '
            + escapeHtml(s.name) + ' <span style="color:var(--text-dim);font-size:12px">(' + escapeHtml(s.description) + ')</span>';
        container.appendChild(label);
    });
});

function runCompare() {
    var code = document.getElementById('cmp-input').value;
    var checkboxes = document.querySelectorAll('#cmp-strategies input:checked');
    var strategies = Array.prototype.map.call(checkboxes, function(cb) { return cb.value; });

    if (!code.trim()) { showAlert('cmp-alert', 'error', '请输入 RTL 代码'); return; }
    if (strategies.length < 2) { showAlert('cmp-alert', 'error', '请至少选择 2 种策略进行对比'); return; }

    var btn = document.getElementById('cmp-btn');
    btn.disabled = true;
    showLoading('cmp-alert', '正在对比策略...');

    apiFetch('/api/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rtl_code: code, strategies: strategies })
    }).then(function(data) {
        if (data.success) {
            renderCompareResults(data.comparison, data.recommendation);
            showAlert('cmp-alert', 'success', '对比完成');
        } else {
            showAlert('cmp-alert', 'error', '对比失败');
        }
    }).catch(function(err) {
        showAlert('cmp-alert', 'error', '错误: ' + err.message);
    }).finally(function() {
        btn.disabled = false;
    });
}

function renderCompareResults(comparison, recommendation) {
    var tbody = document.getElementById('cmp-tbody');
    tbody.innerHTML = '';
    comparison.forEach(function(item) {
        var tr = document.createElement('tr');
        tr.innerHTML = '<td><strong>' + escapeHtml(item.strategy) + '</strong></td>'
            + '<td>' + item.area_overhead + 'x</td>'
            + '<td>' + renderStars(item.reliability) + '</td>'
            + '<td>' + item.latency + '</td>'
            + '<td>' + item.power_overhead + 'x</td>';
        tbody.appendChild(tr);
    });

    var recEl = document.getElementById('cmp-recommendation');
    if (recommendation) {
        recEl.className = 'alert alert-success';
        recEl.innerHTML = '\\u2192 推荐策略: <strong>' + escapeHtml(recommendation) + '</strong>';
    } else {
        recEl.className = '';
        recEl.innerHTML = '';
    }
    document.getElementById('cmp-result-card').style.display = 'block';
}"""
    html = html.replace("__SAMPLE__", _SAMPLE_RTL)
    return html, js


# ---------------------------------------------------------------------------
# 路由注册
# ---------------------------------------------------------------------------
if FASTAPI_AVAILABLE and app is not None:

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def _dashboard_page():
        html, js = _dashboard_content()
        return _render_page("dashboard", html, js)

    @app.get("/harden", response_class=HTMLResponse, include_in_schema=False)
    async def _harden_page():
        html, js = _harden_content()
        return _render_page("harden", html, js)

    @app.get("/vulnerability", response_class=HTMLResponse, include_in_schema=False)
    async def _vulnerability_page():
        html, js = _vuln_content()
        return _render_page("vulnerability", html, js)

    @app.get("/compare", response_class=HTMLResponse, include_in_schema=False)
    async def _compare_page():
        html, js = _compare_content()
        return _render_page("compare", html, js)


# ---------------------------------------------------------------------------
# 向后兼容：WebGUI 类与 start_web_gui 函数
# rag_integration.py 等模块通过此接口启动 Web GUI。
# 新版基于 FastAPI/uvicorn，通过 REST API 获取数据，
# set_data() 保留签名兼容但不再使用传入数据。
# ---------------------------------------------------------------------------
class WebGUI:
    """基于 FastAPI/uvicorn 的 Web GUI 服务封装。"""

    def __init__(self, port: int = _WEB_GUI_PORT):
        self.port = port
        self._server = None
        self._thread = None

    def set_data(
        self,
        design_analysis: Optional[Dict[str, Any]] = None,
        module_strategy_map: Optional[Dict[str, str]] = None,
        hardening_callback: Optional[Callable] = None,
    ) -> None:
        """保留接口兼容。新版应用通过 REST API 获取所有数据。"""
        pass

    def start(self) -> None:
        """在后台线程中启动 uvicorn 服务。"""
        if not FASTAPI_AVAILABLE or app is None:
            print("[WebGUI] FastAPI 未安装，无法启动。请执行: pip install fastapi uvicorn")
            return
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=self.port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        url = "http://localhost:{}".format(self.port)
        print("[WebGUI] 服务已启动: {}".format(url))
        if not _API_AVAILABLE:
            print("[WebGUI] 警告: API 服务不可用，页面功能将受限。请确保 api_server.py 可正常导入。")
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    def stop(self) -> None:
        """停止 uvicorn 服务。"""
        if self._server:
            self._server.should_exit = True
            print("[WebGUI] 服务已停止")


def start_web_gui(
    design_analysis: Optional[Dict[str, Any]] = None,
    module_strategy_map: Optional[Dict[str, str]] = None,
    hardening_callback: Optional[Callable] = None,
    port: int = _WEB_GUI_PORT,
) -> WebGUI:
    """启动 Web GUI 服务（向后兼容接口）。

    Args:
        design_analysis: 设计分析输出（新版不再使用，保留兼容）
        module_strategy_map: 模块策略映射（新版不再使用，保留兼容）
        hardening_callback: 加固回调（新版不再使用，保留兼容）
        port: 服务端口

    Returns:
        WebGUI 实例
    """
    gui = WebGUI(port)
    gui.set_data(design_analysis, module_strategy_map, hardening_callback)
    gui.start()
    return gui


# ---------------------------------------------------------------------------
# 主入口：python web_gui.py 直接启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not FASTAPI_AVAILABLE:
        print("=" * 60)
        print("  FastAPI 未安装，无法启动 Web GUI。")
        print("  请安装依赖:")
        print("      pip install fastapi uvicorn")
        print("=" * 60)
        sys.exit(1)

    _port = int(os.environ.get("WEB_GUI_PORT", _WEB_GUI_PORT))
    print("RTL 加固工具链 Web GUI")
    print("  地址: http://localhost:{}".format(_port))
    if _API_AVAILABLE:
        print("  API: 已连接 (复用 api_server 路由)")
    else:
        print("  API: 未连接 (api_server 导入失败，API 调用将不可用)")
        print("       请确保 api_server.py 及其依赖可正常导入。")
    print("  按 Ctrl+C 停止服务")
    print()

    uvicorn.run(app, host="0.0.0.0", port=_port)
