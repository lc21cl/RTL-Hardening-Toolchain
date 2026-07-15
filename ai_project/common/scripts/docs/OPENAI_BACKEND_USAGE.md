# OpenAIBackend API 使用文档

## 1. 概述

`OpenAIBackend` 是 RTL 自动加固系统的 LLM 连接层，支持三种运行模式：

| 模式 | 条件 | 行为 |
|:-----|:------|:------|
| **OpenAI 真实 API** | `openai` 包已安装 + API key 可用 | 调用 GPT-4 生成加固 RTL |
| **DeepSeek 兼容 API** | `openai` 包已安装 + DeepSeek API key | 调用 DeepSeek Chat 生成加固 RTL |
| **MockLLM 回退** | 无 API key 或 API 调用失败 | 使用 8 种内置模板自动生成 |

**文件位置**: `common/scripts/sim/formal_test/rag_integration.py`

---

## 2. 快速开始

### 2.1 使用 MockLLM 回退（无需 API key）

```python
from rag_integration import RAGEngine

engine = RAGEngine(llm_backend='mock')  # 默认, 无需 API key
engine.load_knowledge_base()

design_info = {
    'module_name': 'tmr_voter',
    'signals': ['data_in', 'data_out', 'clk', 'rst_n'],
    'signal_width': 32,
    'vulnerabilities': 'SEU in datapath',
}
vulnerability_result = {
    'all_vulnerable_nodes': [{'name': 'reg_0', 'type': 'DFF', 'vulnerability': 0.85}],
}

rtl = engine.generate_hardened_rtl(design_info, vulnerability_result)
```

### 2.2 使用 DeepSeek API

```python
from rag_integration import RAGEngine

engine = RAGEngine(
    llm_backend='deepseek',
    api_key='sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',  # DeepSeek API key
)
engine.load_knowledge_base()

rtl = engine.generate_hardened_rtl(design_info, vulnerability_result)
```

### 2.3 使用 OpenAI API

```python
from rag_integration import RAGEngine

engine = RAGEngine(
    llm_backend='openai',
    api_key='sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',  # OpenAI API key
)
engine.load_knowledge_base()

rtl = engine.generate_hardened_rtl(design_info, vulnerability_result)
```

---

## 3. API Key 解析

`_resolve_api_key()` 使用三源优先级自动检测 API key：

1. **显式传入**: `RAGEngine(api_key='sk-xxx')` 或 `OpenAIBackend(api_key='sk-xxx')`
2. **环境变量**: `$OPENAI_API_KEY`（对 DeepSeek 用 `$DEEPSEEK_API_KEY`）
3. **.env 文件**: 在当前目录或脚本目录搜索 `.env` 文件

```python
# .env 文件示例
OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

API key 在日志中自动脱敏：`sk-xxxx...xxxx`

---

## 4. 支持的加固策略

OpenAIBackend + MockLLM 回退支持 **8 种加固策略**：

| 策略 | 关键词检测 | 输出特征 |
|:-----|:-----------|:---------|
| `tmr` | `TMR`, `Triple.Modular` | 三模冗余 + 多数表决器 |
| `ecc` | `ECC`, `Error.Correction`, `Hamming`, `SECDED` | Hamming SECDED 编解码器 |
| `dice` | `DICE` | 双互锁存储单元 (4 节点) |
| `parity` | `parity` | 奇偶校验生成/检查 |
| `tmr_ecc` | `TMR` + `ECC` 同时出现 | TMR + ECC 混合加固 |
| `cnt_comp` | `cnt_comp`, `counter comparator` | 计数器比较器 + 范围检查 |
| `watchdog` | `watchdog`, `wdt` | 看门狗定时器 + 超时复位 |
| `one_hot_fsm` | `one_hot.*FSM`, `onehot` | 独热状态机 + 状态错误检测 |

### 4.1 MockLLM 模板直接调用

```python
from rag_integration import MockLLM

# 所有静态方法
tmr_rtl     = MockLLM._tmr_rtl('my_module', 32)
ecc_rtl     = MockLLM._ecc_rtl('my_module', 32)
dice_rtl    = MockLLM._dice_rtl('my_module', 8)
parity_rtl  = MockLLM._parity_rtl('my_module', 16)
tmr_ecc_rtl = MockLLM._tmr_ecc_rtl('my_module', 32)
cnt_comp    = MockLLM._cnt_comp_rtl('my_module', 32)    # 含 error_flag
watchdog    = MockLLM._watchdog_rtl('my_module', 32)     # 含 timeout_flag + watchdog_reset
one_hot_fsm = MockLLM._one_hot_fsm_rtl('my_module', 32) # 含 fsm_error
```

### 4.2 通过 OpenAIBackend 调用

```python
from rag_integration import OpenAIBackend

backend = OpenAIBackend()  # 自动使用 MockLLM 回退

# 策略通过 prompt 关键词自动检测
rtl = backend.generate("Apply cnt_comp hardening to module my_counter")
rtl = backend.generate("Apply watchdog timer with heartbeat to module system_monitor")
rtl = backend.generate("Apply one_hot FSM hardening to module controller")
```

---

## 5. DeepSeekBackend

`DeepSeekBackend` 使用 OpenAI 兼容的 DeepSeek API 端点：

```python
from rag_integration import DeepSeekBackend

backend = DeepSeekBackend(
    api_key='sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    model='deepseek-chat',  # 默认
)

rtl = backend.generate(
    "Generate TMR-hardened 32-bit register with voter",
    max_tokens=4096,
    temperature=0.1,
)
```

### 5.1 与 GraphPipeline 集成

```python
from graph_pipeline import GraphPipeline

pipeline = GraphPipeline(verbose=True)
result = pipeline.harden(
    rtl_path="design.v",
    llm_backend="deepseek",       # 使用 DeepSeek API
    api_key="sk-xxxxxxxxxxxx",    # API key
    hardening_strategy="tmr",     # 加固策略
    max_repair_iterations=5,
    analyze_errors_first=True,
)
print(f"Hardened RTL: {len(result['hardened_rtl'].splitlines())} lines")
print(f"Passed: {result['passed']}")
```

---

## 6. GNN 脆弱性推理 API

`GNNInference` 基于 GraphSAGE 图神经网络，对综合后的 BLIF/AIG 图进行节点级脆弱性预测，识别易受 SEU（单粒子翻转）影响的寄存器。

### 6.1 初始化

```python
from gnn_inference import GNNInference

infer = GNNInference(
    model_path: Optional[str] = None,  # 模型 checkpoint 路径 (默认 auto-detect)
    device: str = 'auto',              # 'cpu' | 'cuda' | 'mps' | 'auto'
    threshold: float = 0.05,           # 脆弱性判定阈值
    verbose: bool = False,             # 详细日志
)
```

### 6.2 推理方法

```python
# 方法 1: 从 PyG Data 对象推理 (推荐)
scores = infer.infer(data)          # data: torch_geometric.data.Data
# 返回: torch.Tensor, shape=[num_nodes], 值域 [0, 1]

# 方法 2: 从 BLIF 文件推理
result = infer.infer_from_blif("path/to/design.blif")
# 返回: dict { 'vulnerable_list': [...], 'top_10_vulnerable': [...], ... }

# 方法 3: 与 GraphPipeline 集成 (从 RTL 到脆弱性输出一步到位)
from graph_pipeline import GraphPipeline
gp = GraphPipeline(verbose=True)
results = gp.from_rtl("design.v")
scores = infer.infer(results["blif"])
n_vuln = int((scores >= infer.threshold).sum().item())
print(f"{n_vuln}/{results['blif'].num_nodes} nodes vulnerable")
```

### 6.3 注意事项

| 要点 | 说明 |
|:-----|:------|
| **API 名称** | 方法名为 `infer()`，**不是** `predict()` |
| **返回值** | `infer()` 返回 `torch.Tensor`，非 `predict()` 的 `dict` |
| **模型不存在** | 抛出 `RuntimeError("Model not loaded")`，需捕获处理 |
| **输入格式** | 接收 PyG `Data` 对象，通过 `GraphPipeline.from_rtl()` 获取 |
| **阈值** | 默认 0.05，可通过 `infer.threshold` 调整 |

### 6.4 集成到加固管线

```python
from graph_pipeline import GraphPipeline
from gnn_inference import GNNInference
import torch

pipeline = GraphPipeline(verbose=True)
infer = GNNInference()

# 1. RTL → BLIF → PyG Data
results = pipeline.from_rtl("design.v")

# 2. GNN 脆弱性预测
try:
    scores = infer.infer(results["blif"])
    vulnerable_nodes = (scores >= infer.threshold).nonzero().squeeze().tolist()
    if isinstance(vulnerable_nodes, int):
        vulnerable_nodes = [vulnerable_nodes]
    print(f"Vulnerable nodes: {len(vulnerable_nodes)}/{results['blif'].num_nodes}")
    
    # 3. 将脆弱性预测结果传递给 RAGEngine 进行加固
    vuln_result = {
        "all_vulnerable_nodes": [
            {"name": f"node_{i}", "type": "DFF", "vulnerability": float(scores[i])}
            for i in vulnerable_nodes
        ],
        "num_nodes": results["blif"].num_nodes,
    }
    
    from rag_integration import RAGEngine
    engine = RAGEngine()
    engine.load_knowledge_base()
    design_info = {"module_name": "design", "signals": [], "signal_width": 32}
    rtl = engine.generate_hardened_rtl(design_info, vuln_result)
    
except RuntimeError as e:
    if "Model not loaded" in str(e):
        print("GNN model not available, using rule-based analysis")
        # 优雅降级到规则分析
    else:
        raise
```

---

## 7. RAGEngine 完整 API

### 7.1 初始化

```python
RAGEngine(
    llm_backend: str = 'mock',     # 'mock' | 'openai' | 'deepseek'
    api_key: Optional[str] = None,  # API key (自动解析)
    model: str = 'gpt-4',           # 模型名
    kb_path: Optional[str] = None,  # 知识库路径 (默认 auto-detect)
)
```

### 7.2 方法

| 方法 | 说明 |
|:-----|:------|
| `load_knowledge_base() -> bool` | 加载加固模式知识库 |
| `generate_hardened_rtl(design_info, vulnerability_result) -> str` | 生成加固 RTL 代码 |
| `set_llm_backend(backend_name[, api_key])` | 动态切换 LLM 后端 |
| `get_metrics() -> dict` | 获取性能指标 (缓存命中率/延迟等) |

### 7.3 design_info 格式

```python
design_info = {
    'module_name': str,           # 模块名
    'signals': List[str],         # 信号名列表
    'signal_width': int,          # 信号位宽
    'vulnerabilities': str,       # 脆弱性描述
    'module_ports': Dict,         # 端口信息 (可选)
}
```

### 7.4 vulnerability_result 格式

```python
vulnerability_result = {
    'all_vulnerable_nodes': [
        {'name': str, 'type': str, 'vulnerability': float},
        # ...
    ],
    'num_nodes': int,             # 总节点数
}
```

---

## 8. 知识库 (KnowledgeBase)

RAGEngine 使用 `HardeningKnowledgeBase` 管理加固设计模式：

```python
from hardening_knowledge_base import KnowledgeBase, HardeningPattern, PatternRetriever

kb = KnowledgeBase()
kb.load()  # 从默认路径加载

# 检索相关模式
results = kb.query("TMR hardened voter with pipeline", top_k=3)
for pattern, score in results:
    print(f"  [{score:.2f}] {pattern.name}")
    print(pattern.rtl_template[:200])
```

知识库包含 16+ 种加固设计模式，自动从 `hardening_knowledge_base.py` 加载。

---

## 9. 日志与安全

### 9.1 API key 脱敏

所有日志输出中 API key 自动脱敏：

```python
from rag_integration import _mask_api_key

assert _mask_api_key("sk-1234567890abcdef") == "sk-xxxx...cdef"
assert _mask_api_key(None) == "None"
assert _mask_api_key("") == "(empty)"
```

### 9.2 日志级别

| 组件 | 日志内容 |
|:-----|:---------|
| `[RAG]` | 知识库检索结果、上下文拼接 |
| `[MOCKLLM]` | MockLLM 模板选择与生成状态 |
| `[OPENAI]` | API 调用状态、模型、token 数 |
| `[DEEPSEEK]` | DeepSeek API 调用状态 |

---

## 10. 性能指标

RAGEngine 自动收集性能指标：

```python
engine = RAGEngine(llm_backend='mock')
engine.load_knowledge_base()
rtl = engine.generate_hardened_rtl(design_info, vuln_result)

metrics = engine.get_metrics()
# {
#     'knowledge_base': {'patterns': 16, 'status': 'loaded'},
#     'rag': {
#         'total_time': 2.5,
#         'retrieval_time': 0.3,
#         'generation_time': 2.2,
#         'context_size': 4,
#         'tokens': 1200,
#     },
#     'cache': {
#         'size': 8,
#         'hits': 3,
#         'misses': 5,
#     },
# }
```

---

## 11. 真实 API 测试

```python
# 测试脚本: common/scripts/sim/formal_test/test_regression_suite.py
# 或直接运行完整回归测试:
python test_regression_suite.py

# 预期输出:
#   [✅] Strategy: TMR            (0.80s)
#   [✅] Strategy: ECC            (0.81s)
#   [✅] Strategy: DICE           (0.81s)
#   [✅] Strategy: PARITY         (0.81s)
#   [✅] Strategy: TMR_ECC        (0.81s)
#   [✅] Strategy: CNT_COMP       (0.55s)
#   [✅] Strategy: WATCHDOG       (0.74s)
#   [✅] Strategy: ONE_HOT_FSM    (0.76s)
#   ...
#   Total: 12/12 tests passed
```

---

## 12. 依赖

| 依赖 | 必需 | 用途 |
|:-----|:----:|:------|
| Python 3.10+ | ✅ | 运行环境 |
| PyTorch | ✅ | 知识库向量检索 + GNN 推理 |
| PyYAML | ✅ | 配置文件加载 |
| `openai` Python 包 | ❌ (推荐) | 真实 API 调用 |
| torch-geometric | ❌ | 图神经网络推理 |
| yosys | ❌ | RTL 综合验证 |

---

## 13. 常见问题

### Q: API key 配置在哪里？
**A**: 三处任选其一：
1. 代码中传入 `RAGEngine(api_key='sk-xxx')`
2. 环境变量 `$OPENAI_API_KEY` 或 `$DEEPSEEK_API_KEY`
3. `.env` 文件（当前目录或脚本目录）

### Q: 没有 API key 能用吗？
**A**: 能。无 key 时自动回退到 MockLLM 模板，内置 8 种加固策略。

### Q: DeepSeek 和 OpenAI 的区别？
**A**: 接口完全兼容。DeepSeek 使用 `base_url="https://api.deepseek.com"` 端点。

### Q: GNNInference 的 `infer()` 和 `predict()` 有什么区别？
**A**: 正确方法名为 `infer()`。`predict()` 是旧版名称，已在 v3.3 中移除。`infer()` 接收 PyG `Data` 对象，返回 `torch.Tensor`。

### Q: 如何添加新的加固策略模板？
**A**: 在 `MockLLM` 类中添加 `@staticmethod _xxx_rtl()` 方法，在 `_strategy_templates` 和 `_STRATEGY_MOCK` 中注册，在 `_detect_strategy` 中添加关键词检测。
