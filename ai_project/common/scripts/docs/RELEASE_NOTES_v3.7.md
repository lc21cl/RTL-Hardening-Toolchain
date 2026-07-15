# Release Notes v3.7 — 子模块级策略分配 & 层次化加固 GUI

**发布日期**: 2026-07-15  
**迭代**: v3.7  
**前版**: v3.5 (P4 缺陷修复 + P2 功能增强)

---

## 1. 新增核心功能

### 1.1 子模块级策略分配

为设计中的不同子模块独立指定加固策略，实现精细化的辐射加固设计。

**支持的子模块策略类型**:

| 策略名称 | 全称 | 说明 | 面积开销 | 适用模块类型 |
|:---------|:-----|:-----|:---------|:-------------|
| `tmr` | Triple Modular Redundancy | 三模冗余，3 副本 + 多数表决器 | 3.0× | 安全关键模块 |
| `dice` | Dual Interlocked Storage Cell | 双互锁存储单元，4 节点交叉耦合 | 2.5× | 高可靠寄存器模块 |
| `ecc` | Error Correcting Code | 汉明码 SECDED，单纠错双检错 | 1.4× (32-bit) | 数据通路模块 |
| `parity` | Parity Check | 奇偶校验，偶校验位插入与检查 | 0.03× (32-bit) | 控制模块 |
| `cnt_comp` | Counter Comparator | 计数器比较器，影子副本周期比对 | 0.1× (32-bit) | 计数器模块 |
| `onehot_fsm` | One-Hot FSM | 独热编码状态机，天然 SEU 容错 | 1.1× (2^N) | 状态机模块 |
| `watchdog` | Watchdog Timer | 看门狗定时器，超时检测复位 | 0.5× | 长时间运行模块 |
| `parity_bus` | Parity Bus | 总线奇偶校验 | 0.03× | 总线通信模块 |

**核心函数**:

```python
# rag_integration.py

def allocate_strategy_per_module(
    design_analysis: Dict[str, Any],
    module_strategies: Optional[Dict[str, str]] = None,
    default_strategy: str = 'tmr',
) -> Dict[str, Any]:
    """为每个模块分配加固策略，自动映射到信号级"""

def apply_module_strategies(
    rtl_content: str,
    design_analysis: Dict[str, Any],
) -> str:
    """应用模块级策略生成加固 RTL"""
```

**策略分配流程**:

```
设计分析 → 模块识别 → 策略配置 → 信号映射 → 策略应用 → 加固输出
     ↓          ↓          ↓          ↓          ↓          ↓
 递归提取   顶层+子模块  用户配置   自动转换   逐层应用   带策略头的RTL
```

### 1.2 层次化设计分析

自动解析 RTL 设计的完整层次结构：

- 递归深度限制（默认 3 层）
- 自动发现子模块文件
- 支持多搜索路径
- 返回扁平化寄存器列表（含模块前缀）

**输出示例**:

```python
{
    "module_name": "top_module",
    "submodules": {
        "control_unit": {"ports": 4, "registers": 2, "submodules": {}},
        "data_path": {"ports": 4, "registers": 2, "submodules": {}},
        "fsm_core": {"ports": 4, "registers": 1, "submodules": {}}
    },
    "all_registers": [
        {"name": "top_reg", "width": 32, "module": "top"},
        {"name": "control_unit.state_reg", "width": 4, "module": "control_unit"},
        {"name": "data_path.buffer_reg", "width": 32, "module": "data_path"},
        {"name": "fsm_core.fsm_state", "width": 3, "module": "fsm_core"}
    ],
    "total_registers": 6
}
```

### 1.3 GUI 子模块管理界面

新增 **"层次化加固 (Hierarchical)"** 标签页，提供可视化的模块级策略配置：

**功能特性**:

| 功能 | 说明 |
|:-----|:-----|
| 模块树状视图 | 显示设计层次结构（顶层 + 子模块），包含策略和寄存器数 |
| 策略下拉选择 | 为每个模块独立选择加固策略（8 种可选） |
| 全部应用默认 | 一键将当前策略应用到所有模块 |
| 实时配置显示 | JSON 格式显示当前策略配置 |
| 配置导出 | 导出策略配置为 JSON 文件，便于复用 |
| 加固执行 | 运行层次化加固，生成加固后 RTL |

**界面布局**:

```
┌─────────────────────────────────────────────────────────┐
│  层次化加固 (Hierarchical Hardening)                     │
├─────────────────────────────────────────────────────────┤
│  文件选择: [──────────────────] [浏览...] [加载设计]      │
├─────────────────────────────────────────────────────────┤
│  模块树状视图                          策略配置          │
│  ┌─────────────────────┐             ┌───────────────┐  │
│  │ top_module (tmr)    │             │ 模块: [──────] │  │
│  │ ├─ control_unit     │             │ 策略: [tmr▼]  │  │
│  │ │   (parity, 2 reg) │             │ [应用策略]     │  │
│  │ ├─ data_path        │             │ [全部应用默认] │  │
│  │ │   (ecc, 2 reg)    │             └───────────────┘  │
│  │ └─ fsm_core         │                                │
│  │     (onehot_fsm)    │                                │
│  └─────────────────────┘                                │
├─────────────────────────────────────────────────────────┤
│  策略配置预览:                                           │
│  {                                                       │
│    "top_module": "tmr",                                  │
│    "control_unit": "parity",                             │
│    "data_path": "ecc",                                   │
│    "fsm_core": "onehot_fsm"                              │
│  }                                                       │
├─────────────────────────────────────────────────────────┤
│  [运行层次化加固] [导出策略配置]                          │
└─────────────────────────────────────────────────────────┘
```

### 1.4 策略优先级和冲突解决机制

**策略优先级**:
1. 显式配置的模块策略（最高优先级）
2. 默认策略
3. 信号所属模块的策略

**冲突检测**:
- 当同一信号被多个策略映射时，按优先级选择
- 子模块间接口信号使用较高优先级的策略
- 日志输出详细的策略映射过程，便于排查冲突

### 1.5 子模块接口兼容性处理

自动检测和解决子模块间接口的策略不兼容问题：

**核心功能**:

| 功能 | 说明 |
|:-----|:-----|
| 兼容性矩阵 | 判断哪些策略组合是兼容的（如 TMR → ECC 不兼容） |
| 适配器生成 | 在不兼容模块之间自动添加适配器模块 |
| 策略升级 | 将低可靠性策略升级为高可靠性策略 |
| 策略降级 | 将高可靠性策略降级为低可靠性策略 |

**解决策略**:

| 模式 | 说明 | 适用场景 |
|:-----|:-----|:---------|
| `add_adapters` | 添加适配器模块 | 不同策略需要共存 |
| `upgrade` | 升级为高可靠性策略 | 安全性优先 |
| `downgrade` | 降级为低可靠性策略 | 面积优先 |

**核心函数**:

```python
from interface_compatibility import resolve_compatibility_conflicts

resolved = resolve_compatibility_conflicts(
    design_analysis,
    module_strategy_map,
    resolution_strategy='add_adapters',
)
```

### 1.6 自动策略推荐引擎

基于模块功能自动推荐最优加固策略：

**模块类型分类**:
- **FSM**: 状态机模块（检测 case 语句和状态转移）
- **Counter**: 计数器模块（检测自增/自减操作）
- **Data**: 数据通路模块（宽位宽数据寄存器）
- **Control**: 控制模块（配置和控制寄存器）

**优化目标**:

| 目标 | 说明 | 权重策略 |
|:-----|:-----|:---------|
| `balanced` | 平衡面积和可靠性（默认） | 面积 0.5 + 可靠性 0.5 |
| `reliability` | 优先考虑可靠性 | 可靠性权重 0.8 |
| `area` | 优先考虑面积开销 | 面积权重 0.8 |
| `performance` | 优先考虑性能 | 延迟权重 0.8 |

**核心函数**:

```python
from strategy_recommender import recommend_strategies, explain_recommendation

result = recommend_strategies(analysis, optimization_goal='balanced')
explanation = explain_recommendation(analysis, 'control_unit', 'parity')
```

### 1.7 加固效果可视化

计算和展示加固效果指标：

**指标类型**:

| 指标 | 说明 | 单位 |
|:-----|:-----|:-----|
| 面积开销 | 加固后面积相对于原设计的增加 | × 或 % |
| 路径延迟 | 加固引入的额外延迟 | cycles |
| 可靠性 | 加固后的可靠性评级 | ★☆☆☆☆ ~ ★★★★★ |

**功能特性**:
- 摘要面板（模块数、寄存器数、总面积增加、最大延迟、平均可靠性）
- 模块级详细指标（每个模块的面积开销和可靠性）
- HTML 可视化报告生成

**核心函数**:

```python
from hardening_visualizer import calculate_hardening_metrics, generate_visualization_html

metrics = calculate_hardening_metrics(analysis, module_strategy_map)
generate_visualization_html(metrics, 'hardening_report.html')
```

### 1.8 增量加固

只加固新增或修改的模块，提升效率：

**功能特性**:

| 功能 | 说明 |
|:-----|:-----|
| 设计变更检测 | 基于文件哈希检测设计是否变更 |
| 缓存策略复用 | 未改动模块直接使用上次的加固策略 |
| 增量分析 | 仅处理新增或修改的模块 |

**核心函数**:

```python
from incremental_hardening import run_incremental_hardening

result = run_incremental_hardening(analysis, './incremental_data')
```

### 1.9 Web GUI

基于浏览器的远程配置界面：

**功能特性**:

| 功能 | 说明 |
|:-----|:-----|
| 模块树视图 | 可视化层次化模块结构 |
| 策略配置 | 在浏览器中配置模块级策略 |
| 实时预览 | JSON 格式实时显示策略配置 |
| 一键加固 | 在浏览器中启动加固流程 |

**核心函数**:

```python
from web_gui import start_web_gui

web_gui = start_web_gui(analysis, module_strategy_map, None, port=8080)
```

---

## 2. 日志增强

在策略分配和应用逻辑中增加详细日志输出：

### 2.1 策略分配日志

```
[RAG] ===========================================
[RAG] Strategy Allocation Process Started
[RAG] ===========================================
[RAG] Top-level module identified: 'top_module'
[RAG] Default strategy: 'tmr'
[RAG] Explicit strategies provided for: ['control_unit', 'data_path']

--- Step 1: Module Strategy Assignment ---
[RAG]   Module 'top_module' → strategy 'tmr' (explicit)
[RAG]   Module 'control_unit' → strategy 'parity' (explicit, 2 regs)

--- Step 3: Register-to-Signal Strategy Mapping ---
[RAG]     Register 'control_unit.state_reg' → module='control_unit' → strategy='parity'

--- Step 5: Final Strategy Summary ---
[RAG]   Strategy distribution:
[RAG]     - tmr: 1 modules, 5 signals (50.0%)
[RAG]     - parity: 1 modules, 5 signals (50.0%)
```

### 2.2 策略应用日志

```
[RAG] ===========================================
[RAG] Strategy Application Process Started
[RAG] ===========================================
[RAG] ✓ Module strategy map loaded: 4 modules
[RAG] ✓ Signal strategy map loaded: 17 signals

--- Step 3: Processing Each Module ---
[RAG]   Module 'control_unit'
[RAG]     ├─ Strategy: parity
[RAG]     └─ Covered signals: ~4

--- Step 5: Final Output ---
[RAG]   Original RTL: 60 lines
[RAG]   Hardened RTL: 72 lines
```

---

## 3. 使用示例

### 3.1 Python API

```python
from rag_integration import (
    analyze_design_for_hardening,
    allocate_strategy_per_module,
    apply_module_strategies,
)

# 分析设计层次
analysis = analyze_design_for_hardening(
    'top.v',
    recursive=True,
    search_paths=['./submodules'],
)

# 配置模块级策略
result = allocate_strategy_per_module(
    analysis,
    module_strategies={
        'top_module': 'tmr',
        'control_unit': 'parity',
        'data_path': 'ecc',
        'fsm_core': 'onehot_fsm',
    },
    default_strategy='tmr',
)

# 应用策略生成加固代码
with open('top.v', 'r') as f:
    hardened = apply_module_strategies(f.read(), result)
```

### 3.2 GUI 操作流程

1. 启动 `python harden_gui.py`
2. 切换到 "层次化加固" 标签页
3. 点击 "浏览..." 选择顶层 RTL 文件
4. 点击 "加载设计" 解析层次结构
5. 在树状视图中选择模块，配置策略
6. 点击 "运行层次化加固" 生成结果

### 3.3 策略配置文件格式

```json
{
  "rtl_file": "/path/to/top.v",
  "module_strategies": {
    "top_module": "tmr",
    "control_unit": "parity",
    "data_path": "ecc",
    "fsm_core": "onehot_fsm"
  },
  "export_time": "2026-07-15 12:00:00"
}
```

---

## 4. 测试验证

### 4.1 GUI 功能测试

| 测试项 | 状态 | 说明 |
|:-------|:-----|:-----|
| 设计加载和模块层次提取 | ✅ PASS | 自动解析子模块结构 |
| 模块策略配置 | ✅ PASS | 8 种策略正确分配 |
| 层次化加固执行 | ✅ PASS | 多策略混合加固 |
| 策略配置导出 | ✅ PASS | JSON 格式配置文件 |
| 模块树结构验证 | ✅ PASS | 层次化数据结构 |

### 4.2 模块策略分配单元测试

| 测试项 | 状态 | 说明 |
|:-------|:-----|:-----|
| 基本模块策略分配 | ✅ PASS | 4 模块 4 策略 |
| 信号级策略映射 | ✅ PASS | 寄存器/端口正确映射 |
| 默认策略回退 | ✅ PASS | 未配置模块使用默认策略 |
| 嵌套模块支持 | ✅ PASS | 多层子模块递归 |
| 策略汇总统计 | ✅ PASS | 策略分布和信号计数 |
| 顶层模块别名 | ✅ PASS | 'top' 作为顶层别名 |
| 真实设计分析 | ✅ PASS | 完整设计分析流程 |

### 4.3 新功能验证

| 功能 | 测试文件 | 状态 |
|:-----|:---------|:-----|
| 接口兼容性 | `interface_compatibility.py` | ✅ 通过 |
| 自动策略推荐 | `strategy_recommender.py` | ✅ 通过 |
| 加固效果可视化 | `hardening_visualizer.py` | ✅ 通过 |
| 增量加固 | `incremental_hardening.py` | ✅ 通过 |
| Web GUI | `web_gui.py` | ✅ 通过 |

---

## 5. 文件变更清单

| 文件 | 操作 | 说明 |
|:-----|:-----|:-----|
| `sim/formal_test/rag_integration.py` | 修改 | 新增 `allocate_strategy_per_module()`、`apply_module_strategies()`、`recommend_strategies()`、`calculate_hardening_metrics()`、`run_incremental_hardening()`、`resolve_compatibility_conflicts()`、`open_web_gui()` |
| `harden_gui.py` | 修改 | 新增 5 个标签页：层次化加固、策略推荐、效果可视化、增量加固、Web GUI |
| `sim/formal_test/interface_compatibility.py` | 新建 | 子模块接口兼容性处理 |
| `sim/formal_test/strategy_recommender.py` | 新建 | 自动策略推荐引擎 |
| `sim/formal_test/hardening_visualizer.py` | 新建 | 加固效果可视化模块 |
| `sim/formal_test/incremental_hardening.py` | 新建 | 增量加固功能 |
| `sim/formal_test/web_gui.py` | 新建 | Web GUI 界面 |
| `sim/formal_test/test_module_strategy_allocation.py` | 新建 | 模块策略分配单元测试 |
| `sim/formal_test/test_gui_hierarchical.py` | 新建 | GUI 层次化功能测试 |
| `docs/SUBMODULE_STRATEGY_GUIDE.md` | 修改 | 集成新功能 API 参考 |
| `docs/USER_MANUAL.md` | 修改 | v3.7 更新，新增策略推荐、可视化、增量加固、Web GUI 使用说明 |
| `docs/HARDENING_OPTIMIZATION_ROADMAP.md` | 修改 | 更新 v3.6/v3.7 完成状态，标记所有计划功能为已完成 |
| `docs/RELEASE_NOTES_v3.7.md` | 修改 | 补充新功能发布说明 |

---

## 6. 已知问题

| 问题 | 说明 | 状态 |
|:-----|:-----|:-----|
| （无） | v3.7 已完成所有计划功能 | ✅ 全部完成 |

---

## 7. 下一阶段计划 (v3.8)

| 优先级 | 任务 | 说明 |
|:------:|:-----|:-----|
| 🟡 P1 | 形式化验证集成 | 将等价性检查集成到加固流程 |
| 🟡 P1 | 多用户协作 | Web GUI 支持多人协作和版本管理 |
| 🟢 P2 | 性能优化 | 大规模设计的加固速度优化 |
| 🟢 P2 | 更多加固策略 | 添加 CRC、时间冗余等新策略 |

---

*Generated from test results: 2026-07-15 20:56 UTC*