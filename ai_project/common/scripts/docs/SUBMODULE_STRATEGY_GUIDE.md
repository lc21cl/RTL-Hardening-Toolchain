# 子模块级策略分配功能使用指南

## 概述

子模块级策略分配功能允许用户为设计中的不同子模块指定不同的加固策略。通过层次化分析和策略映射机制，系统可以自动将模块级策略转换为信号级策略，实现精细化的辐射加固设计。

## 核心功能

### 1. 层次化 RTL 分析

系统能够自动解析 RTL 设计的层次结构，提取：
- 顶层模块信息
- 子模块实例化关系
- 各模块的寄存器和端口信号
- 跨层级的寄存器映射

### 2. 模块级策略配置

支持为每个模块独立指定加固策略，策略包括：
- `tmr`: 三模冗余 (Triple Modular Redundancy)
- `dice`: 双互锁存储单元 (Dual Interlocked Storage Cell)
- `ecc`: 纠错码 (Error Correction Codes)
- `parity`: 奇偶校验 (Parity Check)
- `cnt_comp`: 计数器比较器 (Counter Comparator)
- `onehot_fsm`: 独热编码状态机 (One-Hot FSM)
- `watchdog`: 看门狗定时器 (Watchdog Timer)
- `parity_bus`: 总线奇偶校验

### 3. 自动信号级映射

系统自动将模块级策略映射到该模块的所有寄存器和端口信号，生成完整的信号策略映射表。

### 4. 接口兼容性处理

自动检测和解决子模块间接口的策略不兼容问题：
- 策略兼容性矩阵（判断哪些策略组合是兼容的）
- 适配器模块自动生成（在不兼容模块之间添加适配器）
- 策略升级/降级机制（将低可靠性策略升级为高可靠性策略）

### 5. 自动策略推荐

基于模块功能自动推荐最优加固策略：
- 模块类型分类（FSM/Counter/Data/Control）
- 多目标优化（balanced/reliability/area/performance）
- 策略评分和备选推荐

### 6. 加固效果可视化

计算和展示加固效果指标：
- 面积开销估算
- 路径延迟分析
- 可靠性评级
- HTML 可视化报告生成

### 7. 增量加固

只加固新增或修改的模块，提升效率：
- 设计变更检测（基于文件哈希）
- 缓存策略复用（未改动模块直接使用上次结果）
- 增量分析执行

## 使用方法

### 方法一：GUI 界面操作

#### 步骤 1：打开层次化加固界面

启动 `harden_gui.py`，切换到 **"层次化加固 (Hierarchical)"** 标签页。

#### 步骤 2：加载 RTL 设计

1. 点击 **"浏览..."** 按钮选择顶层 RTL 文件
2. 点击 **"加载设计"** 按钮
3. 系统自动解析设计层次，在树状视图中显示模块结构

#### 步骤 3：配置模块策略

1. 在树状视图中选中目标模块
2. 在右侧下拉菜单中选择加固策略
3. 点击 **"应用策略"** 按钮保存配置
4. 重复上述步骤为其他模块配置策略

#### 步骤 4：批量配置（可选）

1. 在策略下拉菜单中选择默认策略
2. 点击 **"全部应用默认"** 按钮
3. 系统自动将当前策略应用到所有模块

#### 步骤 5：运行加固

1. 点击 **"运行层次化加固"** 按钮
2. 系统生成加固后的 RTL 文件，保存在 `reports` 目录

#### 步骤 6：导出配置（可选）

1. 点击 **"导出策略配置"** 按钮
2. 将当前策略配置保存为 JSON 文件，便于复用

### 方法二：Python API 调用

#### 基础示例

```python
from rag_integration import (
    analyze_design_for_hardening,
    allocate_strategy_per_module,
    apply_module_strategies,
)

# 步骤 1：分析设计层次
analysis = analyze_design_for_hardening(
    'top.v',
    recursive=True,
    search_paths=['./submodules'],
)

# 步骤 2：配置模块级策略
module_strategies = {
    'top_module': 'tmr',
    'control_unit': 'parity',
    'data_path': 'ecc',
    'fsm_core': 'onehot_fsm',
}

result = allocate_strategy_per_module(
    analysis,
    module_strategies=module_strategies,
    default_strategy='tmr',
)

# 步骤 3：应用策略生成加固代码
with open('top.v', 'r') as f:
    rtl_content = f.read()

hardened_content = apply_module_strategies(rtl_content, result)

# 步骤 4：保存结果
with open('top_hardened.v', 'w') as f:
    f.write(hardened_content)
```

#### 策略配置格式

```python
module_strategies = {
    # 顶层模块策略
    'top_module': 'tmr',
    
    # 子模块策略
    'control_unit': 'parity',
    'data_path': 'ecc',
    'fsm_core': 'onehot_fsm',
    
    # 嵌套子模块（如果有）
    'data_path.alu_unit': 'dice',
}
```

#### 使用默认策略

```python
# 仅配置部分模块，其余使用默认策略
module_strategies = {
    'critical_module': 'tmr',  # 关键模块使用 TMR
}

result = allocate_strategy_per_module(
    analysis,
    module_strategies=module_strategies,
    default_strategy='parity',  # 默认使用奇偶校验
)
```

## 配置示例

### 示例 1：混合策略配置

针对一个包含控制、数据和状态机模块的设计：

```python
module_strategies = {
    'top_module': 'tmr',            # 顶层使用 TMR
    'control_unit': 'parity',       # 控制单元使用奇偶校验
    'data_path': 'ecc',             # 数据通路使用 ECC
    'fsm_core': 'onehot_fsm',       # 状态机使用独热编码
}
```

### 示例 2：高性能设计配置

针对对面积敏感的设计，采用轻量级策略：

```python
module_strategies = {
    'top_module': 'parity',         # 顶层使用奇偶校验
    'control_unit': 'parity',       # 控制单元使用奇偶校验
    'data_path': 'ecc',             # 数据通路仍使用 ECC
    'fsm_core': 'onehot_fsm',       # 状态机使用独热编码
}
```

### 示例 3：高可靠性设计配置

针对航天级应用，采用最强保护：

```python
module_strategies = {
    'top_module': 'tmr',            # 顶层使用 TMR
    'control_unit': 'tmr',          # 控制单元使用 TMR
    'data_path': 'tmr_ecc',         # 数据通路使用 TMR+ECC
    'fsm_core': 'onehot_fsm',       # 状态机使用独热编码
}
```

## 策略选择指南

### 根据模块类型选择策略

| 模块类型 | 推荐策略 | 原因 |
|---------|---------|------|
| 控制单元 | parity | 低面积开销，检测单比特错误 |
| 数据通路 | ecc | 单比特纠错，适合宽数据路径 |
| 状态机 | onehot_fsm | 天然 SEU 容错，状态编码冗余 |
| 计数器 | cnt_comp | 监控计数器值，检测越界 |
| 关键寄存器 | dice | 4 节点交叉耦合，抗 SEU |
| 时序关键路径 | tmr | 三模冗余，多数表决 |
| 长时间运行模块 | watchdog | 超时检测，自动复位 |

### 面积开销参考

| 策略 | 面积开销 | 延迟开销 |
|-----|---------|---------|
| parity | ~1.1x | 0 cyc |
| onehot_fsm | ~2-4x | 0 cyc |
| dice | ~1.8x | 0 cyc |
| cnt_comp | ~1.3x | 0 cyc |
| ecc | ~1.5-2x | 1 cyc |
| tmr | ~3.2x | 1 cyc |
| tmr_ecc | ~4-5x | 2 cyc |

## 注意事项

### 1. 模块名称匹配

- 策略配置中的模块名必须与 RTL 中的模块定义完全一致（大小写敏感）
- 可以使用 `'top'` 作为顶层模块的别名
- 对于嵌套模块，使用 `parent.child` 格式

### 2. 搜索路径配置

当子模块定义在不同目录时，需要指定搜索路径：

```python
analysis = analyze_design_for_hardening(
    'top.v',
    recursive=True,
    search_paths=[
        './src',
        './submodules',
        './ip_cores',
    ],
)
```

### 3. 递归深度限制

默认递归深度为 3 层，防止循环实例化导致的无限递归：

```python
# 在 _parse_single_rtl_file 中定义
MAX_RECURSION_DEPTH = 3
```

### 4. 缓存机制

系统使用全局缓存加速重复分析：

- `_MODULE_RESULT_CACHE`: 模块分析结果缓存
- `_SUBMODULE_FILE_CACHE`: 子模块文件路径缓存
- 每次调用 `analyze_design_for_hardening` 会自动清空缓存

### 5. 信号命名约定

层次化寄存器名称格式：`<module_name>.<register_name>`

例如：
- `control_unit.state_reg`
- `data_path.buffer_reg`

### 6. 策略冲突处理

当同一信号被多个策略映射时，系统遵循以下优先级：
1. 显式配置的模块策略
2. 默认策略
3. 信号所属模块的策略

### 7. 不支持的策略

如果指定了系统不支持的策略名称，会记录警告日志并跳过该模块的加固：

```python
# 会产生警告
module_strategies = {
    'unknown_module': 'invalid_strategy',  # 未知策略
}
```

## 日志输出说明

系统在策略分配和应用过程中会输出详细日志，便于排查问题：

### 策略分配日志

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
[RAG]   Register 'control_unit.state_reg' → module='control_unit' → strategy='parity'

--- Step 5: Final Strategy Summary ---
[RAG]   Strategy distribution:
[RAG]     - tmr: 1 modules, 5 signals (50.0%)
[RAG]     - parity: 1 modules, 5 signals (50.0%)
```

### 策略应用日志

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

## 常见问题

### Q1：子模块文件找不到

**现象**：日志显示 `file not found on search paths`

**解决方案**：
1. 确认子模块文件与顶层文件在同一目录
2. 通过 `search_paths` 参数指定额外搜索目录
3. 确认文件名包含模块名（如 `control_unit.v`）

### Q2：策略未正确应用

**现象**：信号策略映射为空或不正确

**解决方案**：
1. 确认模块名拼写正确（大小写敏感）
2. 检查设计是否成功解析（`parse_success=True`）
3. 查看日志中的策略分配过程

### Q3：递归分析深度不够

**现象**：深层嵌套模块未被分析

**解决方案**：
1. 修改 `MAX_RECURSION_DEPTH` 常量（默认 3）
2. 检查是否存在循环实例化

### Q4：缓存导致的问题

**现象**：修改 RTL 后分析结果未更新

**解决方案**：
1. 重启 Python 进程（缓存是全局的）
2. 手动调用 `_MODULE_RESULT_CACHE.clear()`

## 输出文件

### 加固后 RTL 文件

保存在 `reports` 目录，命名格式：`<top_module>_hierarchical_hardened.v`

文件头部包含策略摘要：

```verilog
// ------------------------------------------------------------
// Hardened Design with Module-Level Strategies
// Generated by RAG Engine
// 
// Strategy Distribution: ecc(1), onehot_fsm(1), parity(1), tmr(1)
// Total Modules: 4
// Total Signals: 17
// ------------------------------------------------------------
```

### 策略配置导出文件

JSON 格式，包含：
- `rtl_file`: 原始 RTL 文件路径
- `module_strategies`: 模块策略映射
- `export_time`: 导出时间

## 新功能 API 参考

### 接口兼容性处理

```python
from rag_integration import (
    analyze_design_for_hardening,
    allocate_strategy_per_module,
    resolve_compatibility_conflicts,
)

analysis = analyze_design_for_hardening('top.v', recursive=True)
module_strategies = {
    'top_module': 'tmr',
    'control_unit': 'parity',
    'data_path': 'ecc',
}

result = allocate_strategy_per_module(analysis, module_strategies)

resolved = resolve_compatibility_conflicts(
    analysis,
    result['module_strategy_map'],
    resolution_strategy='add_adapters',  # add_adapters / upgrade / downgrade
)

print(f"检测到冲突: {len(resolved.get('conflicts', []))}")
print(f"生成适配器: {len(resolved.get('adapters', []))}")
```

### 自动策略推荐

```python
from rag_integration import (
    analyze_design_for_hardening,
    recommend_strategies,
    explain_recommendation,
)

analysis = analyze_design_for_hardening('top.v', recursive=True)

# 基于平衡目标推荐
result = recommend_strategies(analysis, optimization_goal='balanced')

for module_name, rec in result['recommendations'].items():
    print(f"{module_name}:")
    print(f"  类型: {rec['module_type']}")
    print(f"  推荐策略: {rec['recommended_strategy']}")
    print(f"  评分: {rec['top_strategies'][0]['score']:.2f}")
    
explanation = explain_recommendation(analysis, 'control_unit', 'parity')
print(f"\n推荐理由: {explanation}")
```

### 加固效果可视化

```python
from rag_integration import (
    analyze_design_for_hardening,
    allocate_strategy_per_module,
    calculate_hardening_metrics,
)
from hardening_visualizer import generate_visualization_html

analysis = analyze_design_for_hardening('top.v', recursive=True)
module_strategies = {
    'top_module': 'tmr',
    'control_unit': 'parity',
    'data_path': 'ecc',
    'fsm_core': 'onehot_fsm',
}

result = allocate_strategy_per_module(analysis, module_strategies)

metrics = calculate_hardening_metrics(analysis, result['module_strategy_map'])

print("加固指标摘要:")
print(f"  模块数: {metrics['summary']['total_modules']}")
print(f"  寄存器数: {metrics['summary']['total_registers']}")
print(f"  面积增加: {metrics['summary']['area_increase_percent']:.1f}%")
print(f"  最大延迟: {metrics['summary']['max_latency_cycles']} cycles")
print(f"  平均可靠性: {metrics['summary']['avg_reliability_stars']}")

generate_visualization_html(metrics, 'hardening_report.html')
```

### 增量加固

```python
from rag_integration import (
    analyze_design_for_hardening,
    run_incremental_hardening,
)

analysis = analyze_design_for_hardening('top.v', recursive=True)

result = run_incremental_hardening(analysis, './incremental_data')

if result['design_changed']:
    print("设计已变更:")
    print(f"  复用模块: {result['reused_modules']}")
    print(f"  新增模块: {result['new_modules']}")
    print(f"  移除模块: {result['removed_modules']}")
else:
    print("设计未变更，使用缓存策略")

print("\n最终策略映射:")
for module, strategy in result['module_strategy_map'].items():
    print(f"  {module}: {strategy}")
```

### Web GUI

```python
from rag_integration import (
    analyze_design_for_hardening,
    open_web_gui,
)

analysis = analyze_design_for_hardening('top.v', recursive=True)

module_strategy_map = {
    'top_module': 'tmr',
    'control_unit': 'parity',
    'data_path': 'ecc',
}

web_gui = open_web_gui(analysis, module_strategy_map, None, port=8080)
if web_gui:
    print("Web GUI 已启动，访问 http://localhost:8080")
```

## 版本历史

| 版本 | 日期 | 变更 |
|-----|------|-----|
| 1.0 | 2026-07-15 | 初始版本，支持基础模块级策略分配 |
| 1.1 | 2026-07-15 | 增加详细日志输出，优化策略映射逻辑 |

## 技术支持

如遇问题，请检查以下日志文件：
- `sim/formal_test/logs/pipeline.log`: 主日志文件
- GUI 界面输出区域：实时执行日志

---

*文档版本: 1.1*
*最后更新: 2026-07-15*