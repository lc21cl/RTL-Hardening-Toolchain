import os
import json
import webbrowser
import threading
from typing import Dict, Any, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from logger import logger

_WEB_GUI_PORT = 8080


class WebGUIHandler(BaseHTTPRequestHandler):
    design_analysis = None
    module_strategy_map = {}
    hardening_callback = None

    def _send_json(self, data: Dict[str, Any], status: int = 200) -> None:
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _send_html(self, html: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/':
            self._send_html(self._generate_main_page())
        elif path == '/api/design':
            if self.design_analysis:
                self._send_json({
                    'success': True,
                    'design': self.design_analysis,
                    'strategies': self.module_strategy_map,
                })
            else:
                self._send_json({'success': False, 'error': 'No design loaded'}, 404)
        elif path == '/api/strategies/list':
            strategies = ['tmr', 'dice', 'ecc', 'parity', 'cnt_comp', 'onehot_fsm', 'watchdog', 'parity_bus']
            self._send_json({'success': True, 'strategies': strategies})
        elif path == '/api/optimization_goals':
            goals = ['balanced', 'reliability', 'area', 'performance']
            self._send_json({'success': True, 'goals': goals})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(body) if body else {}

        if path == '/api/set_strategy':
            module_name = data.get('module_name')
            strategy = data.get('strategy')
            if module_name and strategy:
                self.module_strategy_map[module_name] = strategy
                self._send_json({'success': True, 'module_name': module_name, 'strategy': strategy})
            else:
                self._send_json({'success': False, 'error': 'Missing module_name or strategy'}, 400)

        elif path == '/api/set_all_strategies':
            strategies = data.get('strategies', {})
            self.module_strategy_map.update(strategies)
            self._send_json({'success': True, 'count': len(strategies)})

        elif path == '/api/run_hardening':
            if self.hardening_callback:
                try:
                    result = self.hardening_callback(self.module_strategy_map)
                    self._send_json({'success': True, 'result': result})
                except Exception as e:
                    self._send_json({'success': False, 'error': str(e)}, 500)
            else:
                self._send_json({'success': False, 'error': 'No hardening callback set'}, 400)

        else:
            self.send_response(404)
            self.end_headers()

    def _generate_main_page(self) -> str:
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RTL Hardening Web GUI</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; color: #333; }
        .header { background: linear-gradient(135deg, #2196F3, #1565C0); color: white; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .header h1 { font-size: 24px; font-weight: 600; }
        .container { max-width: 1400px; margin: 20px auto; padding: 0 20px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .card-title { font-size: 18px; font-weight: 600; color: #1976D2; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #e3f2fd; }
        .tree-container { max-height: 400px; overflow-y: auto; }
        .tree-item { padding: 8px 12px; cursor: pointer; border-radius: 4px; transition: background 0.2s; display: flex; justify-content: space-between; align-items: center; }
        .tree-item:hover { background: #f1f8e9; }
        .tree-item.selected { background: #e3f2fd; }
        .tree-item .indent-1 { padding-left: 20px; }
        .tree-item .indent-2 { padding-left: 40px; }
        .strategy-select { padding: 6px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; background: white; }
        .btn { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: 500; transition: opacity 0.2s; }
        .btn-primary { background: #2196F3; color: white; }
        .btn-primary:hover { opacity: 0.9; }
        .btn-success { background: #4CAF50; color: white; }
        .btn-success:hover { opacity: 0.9; }
        .btn-warning { background: #FF9800; color: white; }
        .btn-group { display: flex; gap: 10px; margin-top: 10px; }
        .status-box { padding: 10px; border-radius: 4px; font-size: 13px; margin-top: 10px; }
        .status-success { background: #e8f5e9; color: #2e7d32; }
        .status-error { background: #ffebee; color: #c62828; }
        .status-info { background: #e3f2fd; color: #1565c0; }
        .json-view { background: #f8f9fa; border: 1px solid #ddd; border-radius: 4px; padding: 15px; max-height: 300px; overflow-y: auto; font-family: monospace; font-size: 12px; white-space: pre-wrap; }
        .summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-top: 15px; }
        .summary-item { background: #f5f5f5; border-radius: 8px; padding: 15px; text-align: center; }
        .summary-value { font-size: 24px; font-weight: bold; color: #1976D2; }
        .summary-label { font-size: 12px; color: #666; margin-top: 5px; }
        .loading { animation: pulse 1s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔧 RTL Hardening Web GUI</h1>
        <p style="opacity: 0.9; font-size: 14px; margin-top: 5px;">Submodule-Level Strategy Configuration</p>
    </div>
    
    <div class="container">
        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-value" id="total-modules">0</div>
                <div class="summary-label">Total Modules</div>
            </div>
            <div class="summary-item">
                <div class="summary-value" id="total-registers">0</div>
                <div class="summary-label">Total Registers</div>
            </div>
            <div class="summary-item">
                <div class="summary-value" id="configured-strategies">0</div>
                <div class="summary-label">Configured Strategies</div>
            </div>
            <div class="summary-item">
                <div class="summary-value" id="status-text">Ready</div>
                <div class="summary-label">Status</div>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <div class="card-title">📁 Module Tree</div>
                <div class="tree-container" id="module-tree"></div>
                <div class="btn-group">
                    <button class="btn btn-warning" onclick="applyDefaultStrategy()">Apply Default</button>
                    <button class="btn btn-primary" onclick="recommendStrategies()">Recommend</button>
                </div>
            </div>
            
            <div class="card">
                <div class="card-title">⚙️ Strategy Configuration</div>
                <div id="config-panel">
                    <p style="color: #999;">Select a module to configure its strategy</p>
                </div>
            </div>
            
            <div class="card">
                <div class="card-title">📊 Strategy JSON</div>
                <div class="json-view" id="strategy-json">{}</div>
            </div>
            
            <div class="card">
                <div class="card-title">🚀 Actions</div>
                <button class="btn btn-success" onclick="runHardening()" style="width: 100%; padding: 15px; font-size: 16px;">
                    Run Hardening
                </button>
                <div class="status-box status-info" id="hardening-status">
                    Click "Run Hardening" to process the design
                </div>
            </div>
        </div>
    </div>

    <script>
        let design = null;
        let strategies = {};
        let selectedModule = null;

        async function loadDesign() {
            try {
                const response = await fetch('/api/design');
                const data = await response.json();
                if (data.success) {
                    design = data.design;
                    strategies = data.strategies || {};
                    renderModuleTree();
                    updateSummary();
                    updateStrategyJson();
                }
            } catch (e) {
                console.error('Failed to load design:', e);
            }
        }

        function renderModuleTree() {
            const container = document.getElementById('module-tree');
            container.innerHTML = '';

            if (!design) return;

            const topModule = design.module_name || 'top';
            const submodules = design.submodules || {};

            const topItem = createTreeItem(topModule, design.registers || [], 0);
            container.appendChild(topItem);

            for (const [name, info] of Object.entries(submodules)) {
                const item = createTreeItem(name, info.registers || [], 1);
                container.appendChild(item);
            }
        }

        function createTreeItem(moduleName, registers, indent) {
            const div = document.createElement('div');
            div.className = `tree-item indent-${indent}`;
            div.dataset.module = moduleName;
            
            const strategy = strategies[moduleName] || 'none';
            
            div.innerHTML = `
                <span><strong>${moduleName}</strong> (${registers.length} registers)</span>
                <select class="strategy-select" onchange="updateStrategy('${moduleName}', this.value)">
                    <option value="none" ${strategy === 'none' ? 'selected' : ''}>None</option>
                    <option value="tmr" ${strategy === 'tmr' ? 'selected' : ''}>TMR</option>
                    <option value="dice" ${strategy === 'dice' ? 'selected' : ''}>DICE</option>
                    <option value="ecc" ${strategy === 'ecc' ? 'selected' : ''}>ECC</option>
                    <option value="parity" ${strategy === 'parity' ? 'selected' : ''}>Parity</option>
                    <option value="cnt_comp" ${strategy === 'cnt_comp' ? 'selected' : ''}>CNT_COMP</option>
                    <option value="onehot_fsm" ${strategy === 'onehot_fsm' ? 'selected' : ''}>One-Hot FSM</option>
                    <option value="watchdog" ${strategy === 'watchdog' ? 'selected' : ''}>Watchdog</option>
                    <option value="parity_bus" ${strategy === 'parity_bus' ? 'selected' : ''}>Parity Bus</option>
                </select>
            `;
            
            div.addEventListener('click', () => selectModule(moduleName));
            
            return div;
        }

        function selectModule(moduleName) {
            document.querySelectorAll('.tree-item').forEach(el => el.classList.remove('selected'));
            document.querySelector(`[data-module="${moduleName}"]`).classList.add('selected');
            selectedModule = moduleName;
            showConfigPanel(moduleName);
        }

        function showConfigPanel(moduleName) {
            const panel = document.getElementById('config-panel');
            const moduleInfo = design.submodules[moduleName] || design;
            const strategy = strategies[moduleName] || 'none';
            
            panel.innerHTML = `
                <h3>${moduleName}</h3>
                <p><strong>Registers:</strong> ${moduleInfo.registers ? moduleInfo.registers.length : 0}</p>
                <p><strong>Signals:</strong> ${moduleInfo.signals ? moduleInfo.signals.length : 0}</p>
                <p><strong>Current Strategy:</strong> ${strategy}</p>
                <div style="margin-top: 10px;">
                    <label>Select Strategy:</label><br>
                    <select class="strategy-select" style="width: 100%; padding: 8px;" onchange="updateStrategy('${moduleName}', this.value)">
                        <option value="none" ${strategy === 'none' ? 'selected' : ''}>None</option>
                        <option value="tmr" ${strategy === 'tmr' ? 'selected' : ''}>TMR - Triple Modular Redundancy</option>
                        <option value="dice" ${strategy === 'dice' ? 'selected' : ''}>DICE - Dual Interlocked Storage Cell</option>
                        <option value="ecc" ${strategy === 'ecc' ? 'selected' : ''}>ECC - Error Correcting Code</option>
                        <option value="parity" ${strategy === 'parity' ? 'selected' : ''}>Parity - Parity Check</option>
                        <option value="cnt_comp" ${strategy === 'cnt_comp' ? 'selected' : ''}>CNT_COMP - Counter Comparator</option>
                        <option value="onehot_fsm" ${strategy === 'onehot_fsm' ? 'selected' : ''}>One-Hot FSM</option>
                        <option value="watchdog" ${strategy === 'watchdog' ? 'selected' : ''}>Watchdog - Watchdog Timer</option>
                        <option value="parity_bus" ${strategy === 'parity_bus' ? 'selected' : ''}>Parity Bus</option>
                    </select>
                </div>
            `;
        }

        async function updateStrategy(moduleName, strategy) {
            strategies[moduleName] = strategy === 'none' ? 'tmr' : strategy;
            
            const response = await fetch('/api/set_strategy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ module_name: moduleName, strategy: strategies[moduleName] })
            });
            
            updateSummary();
            updateStrategyJson();
        }

        async function applyDefaultStrategy() {
            const newStrategies = {};
            const modules = [design.module_name || 'top', ...Object.keys(design.submodules || {})];
            
            modules.forEach(m => {
                newStrategies[m] = 'tmr';
            });
            
            strategies = newStrategies;
            
            await fetch('/api/set_all_strategies', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ strategies })
            });
            
            renderModuleTree();
            updateSummary();
            updateStrategyJson();
        }

        function recommendStrategies() {
            alert('Recommendation feature available in desktop GUI');
        }

        function updateSummary() {
            const modules = design ? [design.module_name || 'top', ...Object.keys(design.submodules || {})] : [];
            const registers = design ? (design.all_registers || []).length : 0;
            const configured = Object.keys(strategies).filter(k => strategies[k] !== 'none').length;
            
            document.getElementById('total-modules').textContent = modules.length;
            document.getElementById('total-registers').textContent = registers;
            document.getElementById('configured-strategies').textContent = configured;
            document.getElementById('status-text').textContent = configured > 0 ? 'Configured' : 'Ready';
        }

        function updateStrategyJson() {
            document.getElementById('strategy-json').textContent = JSON.stringify(strategies, null, 2);
        }

        async function runHardening() {
            const status = document.getElementById('hardening-status');
            status.className = 'status-box status-info loading';
            status.textContent = 'Running hardening...';
            
            try {
                const response = await fetch('/api/run_hardening', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                
                const data = await response.json();
                
                if (data.success) {
                    status.className = 'status-box status-success';
                    status.textContent = 'Hardening completed successfully!';
                } else {
                    status.className = 'status-box status-error';
                    status.textContent = 'Error: ' + data.error;
                }
            } catch (e) {
                status.className = 'status-box status-error';
                status.textContent = 'Error: ' + e.message;
            }
        }

        loadDesign();
    </script>
</body>
</html>"""
        return html

    def log_message(self, format, *args):
        pass


class WebGUI:
    def __init__(self, port: int = _WEB_GUI_PORT):
        self.port = port
        self.server = None
        self.server_thread = None

    def set_data(
        self,
        design_analysis: Dict[str, Any],
        module_strategy_map: Dict[str, str],
        hardening_callback,
    ) -> None:
        WebGUIHandler.design_analysis = design_analysis
        WebGUIHandler.module_strategy_map = module_strategy_map
        WebGUIHandler.hardening_callback = hardening_callback

    def start(self) -> None:
        logger.section("Starting Web GUI")
        logger.print(f"  [RAG]   Starting Web GUI on http://localhost:{self.port}")
        
        self.server = HTTPServer(('localhost', self.port), WebGUIHandler)
        
        def run_server():
            self.server.serve_forever()
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        
        url = f"http://localhost:{self.port}"
        logger.print(f"  [RAG]   Web GUI started at: {url}")
        
        try:
            webbrowser.open(url)
        except Exception:
            logger.print(f"  [RAG]   Please open {url} in your browser")

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            logger.print("  [RAG]   Web GUI stopped")


def start_web_gui(
    design_analysis: Dict[str, Any],
    module_strategy_map: Dict[str, str],
    hardening_callback,
    port: int = _WEB_GUI_PORT,
) -> WebGUI:
    """Start the Web GUI server.

    Args:
        design_analysis: Design analysis output
        module_strategy_map: Module strategy mapping
        hardening_callback: Callback function for running hardening
        port: Server port

    Returns:
        WebGUI instance
    """
    web_gui = WebGUI(port)
    web_gui.set_data(design_analysis, module_strategy_map, hardening_callback)
    web_gui.start()
    return web_gui