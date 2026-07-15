# RTL 级加固工具用户手册 (User Manual)

> **版本**: v3.7 | **更新日期**: 2026-07-15
> **项目**: RTL Hardening Tool — 差异化混合加固管线

---

## 1. 概述

RTL 级加固工具是一个自动化的 **Verilog RTL 设计加固 (Hardening)** 工具集，能够对数字电路设计自动施加多种抗单粒子翻转 (SEU) 的加固方法。工具从单一的 **TMR（三模冗余）** 扩展到 **7 种加固策略**，支持按信号类型自动分配最优加固方案，并通过 **AIG 图分析** 和 **GraphSAGE 脆弱性预测** 实现智能化加固决策。

### 核心能力

| 能力 | 说明 |
|:-----|:------|
| 多种加固策略 | TMR、TMR_state、DICE、ECC、Parity、cnt_comp、onehot_fsm、watchdog |
| 差异混合加固 | 按信号类型（FSM/Counter/Data Path/Control）分配不同策略 |
| 子模块级策略分配 | 为不同子模块独立指定加固策略 |
| 层次化设计分析 | 递归解析子模块结构，提取完整寄存器层次 |
| 自动策略推荐 | 根据模块类型智能推荐最优加固策略 |
| 加固效果可视化 | 面积增加、路径延迟、可靠性等指标可视化 |
| 增量加固 | 复用未改动模块的加固结果，提升效率 |
| 子模块接口兼容性 | 检测并解决模块间策略冲突 |
| Web GUI | 基于浏览器的远程配置界面 |
| 故障注入验证 | 自动化故障注入 → AVF 分析 → 加固评分校准 |
| AIG 图分析 | 基于 yosys 综合的 AIG 图脆弱性预测 (Phase 3) |
| GUI & CLI | 图形界面和命令行两种使用方式 |

---

## 2. 安装与环境要求

### 2.1 系统要求

| 依赖 | 版本要求 | 用途 |
|:-----|:---------|:-----|
| Python | ≥ 3.8 | 主运行环境 |
| pyverilog | ≥ 1.4.0 | Verilog AST 解析 |
| iverilog | ≥ 10.0 | Verilog 仿真测试 |
| NetworkX | ≥ 2.5 | AIG 图数据结构 |
| PyTorch Geometric | **可选** (≥ 2.0) | GraphSAGE 训练与推理 |
| yosys | **可选** (≥ 0.9) | RTL → AIG 综合 |

### 2.2 安装步骤

```bash
# 1. 克隆项目
git clone <repository_url>
cd ai_project/common/scripts

# 2. 安装 Python 依赖
pip install pyverilog networkx numpy matplotlib
pip install torch torch-geometric    # 可选，用于 GraphSAGE

# 3. 安装 iverilog
# Windows (choco):
choco install iverilog
# Linux:
sudo apt install iverilog
# macOS:
brew install iverilog

# 4. 安装 yosys (可选，用于 AIG 图构建)
# Windows: 从 https://yosyshq.net/yosys/ 下载安装包
# Linux: 从源码编译或使用包管理器
# macOS: brew install yosys
```

### 2.3 验证安装

```bash
python -c "import pyverilog; print(f'pyverilog {pyverilog.__version__}')"
iverilog -V
yosys --version    # 可选
```

---

## 3. 快速开始 (Quick Start)

### GUI 模式

```bash
# 启动图形界面
python harden_gui.py
```

启动后会显示主窗口，包含以下功能区域：
- **顶部菜单栏**: 文件操作、帮助信息
- **标签页区域**: 10 个功能标签页，包含核心功能和新增功能
- **底部状态栏**: 当前状态和上次操作记录

**按钮颜色说明**（帮助用户快速识别按钮功能）：

| 按钮颜色 | 样式名称 | 用途 | 示例 |
|:---------|:---------|:-----|:-----|
| 🔵 **蓝色** | `Browse.TButton` | 文件浏览、选择 | "浏览..." |
| 🟢 **绿色** | `Action.TButton` | 操作执行、应用 | "加载设计"、"应用策略" |
| 🔴 **红色** | `Run.TButton` | 运行加固、执行 | "运行层次化加固" |
| 🟠 **橙色** | `Export.TButton` | 导出、保存 | "导出策略配置"、"生成 HTML 报告" |
| 🟣 **紫色** | `Recommend.TButton` | 推荐、分析 | "生成推荐" |
| 🔷 **青色** | `Visualize.TButton` | 可视化、计算 | "计算指标" |

### 命令行模式

```bash
# 基本用法: 加固单个设计文件
python hardening_pipeline.py --input design.v --output hardened.v --strategies ecc,parity

# 混合加固（4 种策略自动分配）
python hardening_pipeline.py --input mixed_design.v --output hardened.v --strategies auto

# 故障注入验证
python sim/formal_test/fault_injection_framework.py --design design.v --num_injections 100

# AIG 图分析 (需要 yosys)
python sim/formal_test/demo_aig_analysis.py

# 运行全部回归测试
python run_regression.py
```

### 端到端示例

```bash
# Step 1: 准备设计文件
# Step 2: 运行加固管线 (自动识别信号类型并分配策略)
python hardening_pipeline.py --input test_mock_data/mixed_design.v --output hardened.v

# Step 3: 使用 iverilog 验证加固后设计
iverilog -g2012 -o tb_sim.vvp hardened.v tb_test.v
vvp tb_sim.vvp

# Step 4: 故障注入验证
python sim/formal_test/fault_injection_framework.py
```

### 层次化设计支持

工具支持层次化设计的寄存器提取和分析：

```bash
# 递归分析层次化设计（包含子模块）
python -c "
from rag_integration import analyze_design_for_hardening

result = analyze_design_for_hardening(
    'top_design.v',
    search_paths=['./submodules'],  # 子模块搜索路径
    recursive=True,                  # 启用递归分析
)

print(f'顶层模块: {result[\"module_name\"]}')
print(f'子模块: {list(result.get(\"submodules\", {}).keys())}')
print(f'总寄存器数: {len(result.get(\"all_registers\", []))}')
"
```

**功能特点：**
- 自动发现和分析子模块 RTL 文件
- 支持搜索多个目录
- 递归深度限制（默认 3 层）
- 返回扁平化的寄存器列表（顶层 + 子模块）
- 子模块寄存器命名格式：`submodule_name.register_name`

**测试验证：**
```bash
# 运行层次化寄存器提取测试
python sim/formal_test/test_hierarchical_registers.py
```

---

## 4. 加固方法说明

### 4.1 方法总览

| 方法 | 面积开销 (1-bit) | 面积开销 (32-bit) | SEU 抑制比 | RTL 实现难度 | 适用场景 |
|:-----|:---------------:|:----------------:|:----------:|:------------:|:---------|
| **TMR (三模冗余)** | 3.0× | 3.0× | 10³–10⁶ | 中 | 安全关键信号 |
| **TMR_state (状态机三模)** | 2.5× | — | 10³–10⁶ | 中 | FSM 状态寄存器 |
| **cnt_comp (计数器比较器)** | **0.3×** | **0.1×** | 10² | 低 | 计数器寄存器 |
| **DICE (双互锁存储单元)** | 2.5× | 2.5× | 免疫单粒子 | 中 | 高可靠寄存器 |
| **ECC SECDED (单纠错双检错)** | — | **1.4×** | 10²–10⁴ | 高 | 数据总线/存储器 |
| **Parity (奇偶校验)** | **0.1×** | **0.03×** | 10¹ (检错) | **低** | 控制寄存器 |
| **Watchdog (看门狗)** | 0.5× | — | 10¹ (超时) | 低 | 任务监控 |
| **onehot_fsm (独热状态机)** | 1.1× (2^N) | — | 10³ | 中 | 状态机模块 |
| **parity_bus (总线奇偶校验)** | — | **0.03×** | 10¹ (检错) | 低 | 总线通信模块 |

### 4.2 各方法详解

#### TMR (Triple Modular Redundancy)

将目标信号复制为 3 份，通过多数表决器输出最终结果。任意一个副本出错，表决器仍输出正确结果。

- **模板文件**: 内置 AST 变换引擎
- **原理**: `q = (a&b) | (b&c) | (a&c)`
- **面积开销**: 3.0×
- **SEU 抑制比**: 10³–10⁶

#### TMR_state (状态机三模)

仅对状态寄存器进行三重化，状态转移的组合逻辑不复制。适用于 FSM 状态寄存器。

- **实现**: 在 FSM 分析的基础上，仅替换状态寄存器
- **面积开销**: 2.5×（相比 Full TMR 的 3.0× 节省约 17%）
- **文件**: `fsm_tmr_transformer.py`

#### cnt_comp (计数器比较器)

对计数器寄存器添加影子副本，在特定检查点比对两值是否一致。适用于计数器类信号。

- **模板**: `test_mock_data/cnt_comp_template.v`
- **面积开销**: 0.3× (1-bit), 0.1× (32-bit)
- **SEU 抑制比**: 10²
- **测试结果**: 6/6 基本功能 + 9/9 故障注入

#### DICE (Dual Interlocked Storage Cell)

4 节点交叉耦合寄存器，将标准 DFF 替换为 DICE 单元，免疫单粒子翻转。

- **模板**: `test_mock_data/dice_template.v`
- **面积开销**: 2.5×
- **SEU 抑制比**: 免疫单粒子翻转
- **限制**: 双节点同时翻转场景需晶体管级仿真验证
- **测试结果**: 6/6 PASS

#### ECC SECDED (汉明码单纠错双检错)

为数据总线增加汉明码编解码器，支持单比特纠错和双比特检错。

- **模板**: `test_mock_data/ecc_template.v`
- **实现**: 自定义汉明码 (38, 32) SECDED
- **面积开销**: 1.4× (32-bit)，校验位开销随位宽增加而摊薄
- **测试结果**: 265/265 PASS（含 256 模式穷举）
- **修复**: 早期双比特检测逻辑缺陷已修复

#### Parity (奇偶校验)

为寄存器组添加偶校验位，在读操作时校验。适用于控制寄存器类信号。

- **模板**: `test_mock_data/parity_template.v`
- **面积开销**: 0.03× (32-bit)
- **SEU 抑制比**: 10¹（仅检错）
- **限制**: 无法检测偶数比特翻转（设计预期）
- **测试结果**: 268/268 PASS（含 256 模式穷举）
- **修复**: Delta 周期竞争缺陷已修复

### 4.3 策略选择原则

1. **面积优先**: 选择开销最小的策略（cnt_comp 0.1×、parity 0.03×）
2. **可靠性优先**: 选择 SEU 抑制比最高的策略（TMR 10³–10⁶、DICE 免疫）
3. **混合策略**: 同一模块不同信号可应用不同策略（AST 策略路由引擎统一编排）

### 4.4 子模块级策略分配

v3.7 新增功能 — 允许为设计中的不同子模块独立指定加固策略，实现精细化的辐射加固设计。

**策略分配流程**:

```
设计分析 → 模块识别 → 策略配置 → 信号映射 → 策略应用 → 加固输出
     ↓          ↓          ↓          ↓          ↓          ↓
 递归提取   顶层+子模块  用户配置   自动转换   逐层应用   带策略头的RTL
```

**支持的策略类型**:

| 策略名称 | 适用模块类型 |
|:---------|:-------------|
| `tmr` | 安全关键模块 |
| `dice` | 高可靠寄存器模块 |
| `ecc` | 数据通路模块 |
| `parity` | 控制模块 |
| `cnt_comp` | 计数器模块 |
| `onehot_fsm` | 状态机模块 |
| `watchdog` | 长时间运行模块 |
| `parity_bus` | 总线通信模块 |

**策略优先级**:
1. 显式配置的模块策略（最高优先级）
2. 默认策略
3. 信号所属模块的策略

**代码示例**:

```python
from rag_integration import (
    analyze_design_for_hardening,
    allocate_strategy_per_module,
    apply_module_strategies,
)

analysis = analyze_design_for_hardening(
    'top.v',
    recursive=True,
    search_paths=['./submodules'],
)

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

with open('top.v', 'r') as f:
    hardened = apply_module_strategies(f.read(), result)
```

---

## 5. GUI 使用指南

### 5.1 启动方式

```bash
cd ai_project/common/scripts
python harden_gui.py
```

主窗口默认尺寸为 1200×800 像素，支持调整大小（最小 1000×650）。

### 5.2 界面布局

主界面分为三个区域：

| 区域 | 位置 | 功能 |
|:-----|:-----|:------|
| 菜单栏 | 顶部 | 文件操作、帮助信息 |
| 标签页区域 | 中部 | 10 个功能标签页 |
| 状态栏 | 底部 | 当前状态、上次操作记录、版本信息 |

### 5.3 标签页说明

| 标签页 | 功能 | 核心按钮 |
|:-------|:------|:---------|
| 加固管线 | 基础加固功能 | 选择策略、运行加固 |
| 测试运行 | 回归测试执行 | 运行测试、查看结果 |
| 信号扫描 | 高扇出信号检测 | 扫描信号、分析脆弱性 |
| AIG 分析 | AIG 图分析（需要 yosys） | 生成/分析 AIG |
| **层次化加固** | 模块树状视图和策略配置 | 🔵浏览、🟢加载设计、🟢应用策略、🔴运行加固、🟠导出 |
| **策略推荐** | 自动推荐最优策略 | 🔵浏览、🟣生成推荐 |
| **效果可视化** | 加固指标计算与展示 | 🔵浏览、🔷计算指标、🟠生成 HTML 报告 |
| **增量加固** | 增量分析与复用 | 🔵浏览、🔴运行增量加固 |
| **Web GUI** | 浏览器远程访问 | 🔵浏览、🔴启动 Web GUI |
| 报告 | 查看加固报告 | 打开报告 |

### 5.4 按钮颜色速查

GUI 中使用不同颜色的按钮来区分功能类型：

| 颜色 | 含义 | 示例 |
|:-----|:-----|:-----|
| 🔵 **蓝色** | 文件选择 | "浏览..." |
| 🟢 **绿色** | 操作执行 | "加载设计"、"应用策略" |
| 🔴 **红色** | 运行加固 | "运行层次化加固" |
| 🟠 **橙色** | 导出保存 | "导出策略配置"、"生成 HTML 报告" |
| 🟣 **紫色** | 智能推荐 | "生成推荐" |
| 🔷 **青色** | 可视化计算 | "计算指标" |

### 5.5 标准操作流程

#### 推荐工作流程

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  1. 策略推荐      │ ──▶ │  2. 层次化加固    │ ──▶ │  3. 效果可视化    │
│  (生成初始策略)    │     │  (微调策略配置)   │     │  (评估加固效果)   │
└──────────────────┘     └──────────────────┘     └──────────────────┘
         │                      │                      │
         ▼                      ▼                      ▼
      🟣生成推荐              🔴运行加固              🔷计算指标
         │                      │                      │
         └──────────────────────┴──────────────────────┘
                                 │
                                 ▼
                       ┌──────────────────┐
                       │  4. 导出/查看报告│
                       └──────────────────┘
                                 │
                                 ▼
                          🟠导出配置/报告
```

#### 详细步骤

1. **策略推荐**（可选但推荐）
   - 切换到 "策略推荐" 标签页
   - 🔵点击 "浏览..." 选择 RTL 文件
   - 选择优化目标（balanced/reliability/area/performance）
   - 🟣点击 "生成推荐" 获取建议的策略配置

2. **层次化加固**
   - 切换到 "层次化加固" 标签页
   - 🔵点击 "浏览..." 选择顶层 RTL 文件
   - 🟢点击 "加载设计" 解析模块层次结构
   - 在左侧树状视图中选择模块
   - 在右侧策略下拉菜单中选择加固策略
   - 🟢点击 "应用策略" 保存配置
   - 重复为其他模块配置策略
   - 🔴点击 "运行层次化加固" 生成加固结果

3. **效果可视化**
   - 切换到 "效果可视化" 标签页
   - 🔵点击 "浏览..." 选择 RTL 文件
   - 🔷点击 "计算指标" 查看加固效果预估
   - 🟠点击 "生成 HTML 报告" 导出可视化报告

4. **增量加固**（后续修改设计时使用）
   - 切换到 "增量加固" 标签页
   - 🔵点击 "浏览..." 选择修改后的 RTL 文件
   - 🔴点击 "运行增量加固"
   - 工具会自动检测变更，复用未修改模块的加固策略

### 层次化加固界面（v3.7 新增）

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

**功能特性**:

| 功能 | 说明 |
|:-----|:-----|
| 模块树状视图 | 显示设计层次结构（顶层 + 子模块），包含策略和寄存器数 |
| 策略下拉选择 | 为每个模块独立选择加固策略（8 种可选） |
| 全部应用默认 | 一键将当前策略应用到所有模块 |
| 实时配置显示 | JSON 格式显示当前策略配置 |
| 配置导出 | 导出策略配置为 JSON 文件，便于复用 |
| 加固执行 | 运行层次化加固，生成加固后 RTL |

**操作步骤**:

1. 切换到 "层次化加固" 标签页
2. 点击 "浏览..." 选择顶层 RTL 文件
3. 点击 "加载设计" 解析层次结构
4. 在树状视图中选择模块
5. 在右侧策略下拉菜单中选择加固策略
6. 点击 "应用策略" 保存配置
7. 重复步骤 4-6 为其他模块配置策略
8. 点击 "运行层次化加固" 生成结果
9. （可选）点击 "导出策略配置" 保存配置文件

### 策略推荐界面（v3.7 新增）

**功能特性**:

| 功能 | 说明 |
|:-----|:-----|
| 模块类型分类 | 自动识别 FSM/Counter/Data/Control 模块类型 |
| 多目标优化 | 支持 balanced/reliability/area/performance 四种目标 |
| 策略评分 | 为每个模块的候选策略计算评分 |
| 备选策略 | 显示次优策略供参考 |

**操作步骤**:

1. 切换到 "策略推荐" 标签页
2. 点击 "浏览..." 选择 RTL 文件
3. 在 "优化目标" 下拉菜单中选择优化方向：
   - `balanced`: 平衡面积和可靠性（默认）
   - `reliability`: 优先考虑可靠性
   - `area`: 优先考虑面积开销
   - `performance`: 优先考虑性能
4. 点击 "生成推荐" 按钮
5. 查看推荐结果表格，包含模块名称、类型、推荐策略、评分和备选策略

**代码示例**:

```python
from rag_integration import (
    analyze_design_for_hardening,
    recommend_strategies,
    explain_recommendation,
)

analysis = analyze_design_for_hardening('top.v', recursive=True)
result = recommend_strategies(analysis, optimization_goal='balanced')

for module_name, rec in result['recommendations'].items():
    print(f"{module_name}: {rec['recommended_strategy']}")
    print(f"  类型: {rec['module_type']}")
    print(f"  评分: {rec['top_strategies'][0]['score']:.2f}")
    
explanation = explain_recommendation(analysis, 'control_unit', 'parity')
print(f"推荐理由: {explanation}")
```

### 加固效果可视化界面（v3.7 新增）

**功能特性**:

| 功能 | 说明 |
|:-----|:-----|
| 指标计算 | 计算面积开销、延迟开销、可靠性等指标 |
| 摘要面板 | 显示模块数、寄存器数、面积增加百分比、延迟、可靠性评级 |
| 详细表格 | 按模块展示各策略的开销和可靠性 |
| HTML 报告 | 生成可视化 HTML 报告 |

**操作步骤**:

1. 切换到 "效果可视化" 标签页
2. 点击 "浏览..." 选择 RTL 文件
3. （可选）点击 "浏览..." 选择策略配置 JSON 文件
4. 点击 "计算指标" 按钮
5. 查看加固指标摘要和详细表格
6. （可选）点击 "生成 HTML 报告" 生成可视化报告

**代码示例**:

```python
from rag_integration import (
    analyze_design_for_hardening,
    calculate_hardening_metrics,
)
from hardening_visualizer import generate_visualization_html

analysis = analyze_design_for_hardening('top.v', recursive=True)
module_strategy_map = {
    'top_module': 'tmr',
    'control_unit': 'parity',
    'data_path': 'ecc',
}

metrics = calculate_hardening_metrics(analysis, module_strategy_map)
print(f"面积增加: {metrics['summary']['area_increase_percent']:.1f}%")
print(f"最大延迟: {metrics['summary']['max_latency_cycles']} cycles")
print(f"可靠性: {metrics['summary']['avg_reliability_stars']}")

generate_visualization_html(metrics, 'hardening_report.html')
```

### 增量加固界面（v3.7 新增）

**功能特性**:

| 功能 | 说明 |
|:-----|:-----|
| 设计变更检测 | 检测设计文件是否发生变化 |
| 缓存复用 | 复用未改动模块的加固策略 |
| 增量分析 | 仅处理新增或修改的模块 |

**操作步骤**:

1. 切换到 "增量加固" 标签页
2. 点击 "浏览..." 选择 RTL 文件
3. 指定输出目录（自动填充到 `incremental_data`）
4. 点击 "运行增量加固" 按钮
5. 查看分析结果，包括：
   - 设计是否变更
   - 复用/新增/移除的模块数
   - 最终模块策略映射

**代码示例**:

```python
from rag_integration import (
    analyze_design_for_hardening,
    run_incremental_hardening,
)

analysis = analyze_design_for_hardening('top.v', recursive=True)
result = run_incremental_hardening(analysis, './incremental_data')

if result['design_changed']:
    print(f"复用模块: {result['reused_modules']}")
    print(f"新增模块: {result['new_modules']}")
    print(f"移除模块: {result['removed_modules']}")
else:
    print("设计未变更，使用缓存策略")

print("\n模块策略:")
for module, strategy in result['module_strategy_map'].items():
    print(f"  {module}: {strategy}")
```

### Web GUI 界面（v3.7 新增）

**功能特性**:

| 功能 | 说明 |
|:-----|:-----|
| 浏览器访问 | 通过 Web 浏览器远程访问工具 |
| 模块树视图 | 可视化层次化模块结构 |
| 策略配置 | 在浏览器中配置模块级策略 |
| 实时预览 | JSON 格式实时显示策略配置 |

**操作步骤**:

1. 切换到 "Web GUI" 标签页
2. 点击 "浏览..." 选择 RTL 文件
3. 设置端口号（默认 8080）
4. 点击 "启动 Web GUI" 按钮
5. 在浏览器中访问 `http://localhost:8080`
6. 在 Web 界面中进行模块策略配置和加固操作

---

## 6. 命令行使用

### 6.1 加固管线 (`hardening_pipeline.py`)

**基本用法**:

```bash
# 自动识别信号类型并分配最优策略
python hardening_pipeline.py --input design.v --output hardened.v --strategies auto

# 指定具体加固策略
python hardening_pipeline.py --input design.v --output hardened.v --strategies tmr,parity

# 混合加固（多个信号使用不同策略）
python hardening_pipeline.py --input mixed_design.v --output hardened.v --strategies tmr,parity,cnt_comp,ecc

# 查看详细日志
python hardening_pipeline.py --input design.v --output hardened.v --strategies auto --verbose
```

**支持的参数**:

| 参数 | 说明 | 必填 |
|:-----|:-----|:-----|
| `--input` | 输入 RTL 文件路径 | ✅ 是 |
| `--output` | 输出加固后文件路径 | ✅ 是 |
| `--strategies` | 加固策略列表，用逗号分隔 | ✅ 是 |
| `--verbose` | 显示详细日志 | ❌ 否 |
| `--report` | 生成 HTML 报告 | ❌ 否 |

**输出文件**:
- `hardened.v` — 加固后的 Verilog 代码
- `hardened_meta.json` — 加固元数据（策略分配、面积估计等）
- `hardened_report.html` — 加固报告（如果使用 `--report` 参数）

### 6.2 层次化加固（Python API）

```python
from rag_integration import (
    analyze_design_for_hardening,
    allocate_strategy_per_module,
    apply_module_strategies,
)

# 分析层次化设计
analysis = analyze_design_for_hardening(
    'top.v',
    recursive=True,
    search_paths=['./submodules'],
)

# 分配模块级策略
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

# 应用策略并生成加固代码
with open('top.v', 'r', encoding='utf-8') as f:
    hardened_content = apply_module_strategies(f.read(), result)

# 保存结果
with open('hardened_top.v', 'w', encoding='utf-8') as f:
    f.write(hardened_content)
```

### 6.3 策略推荐（Python API）

```python
from rag_integration import analyze_design_for_hardening, recommend_strategies

# 分析设计
analysis = analyze_design_for_hardening('top.v', recursive=True)

# 生成策略推荐
result = recommend_strategies(analysis, optimization_goal='balanced')

# 查看推荐结果
for module_name, rec in result['recommendations'].items():
    print(f"模块: {module_name}")
    print(f"  类型: {rec['module_type']}")
    print(f"  推荐策略: {rec['recommended_strategy']}")
    print(f"  评分: {rec['top_strategies'][0]['score']:.2f}")
```

### 6.4 加固效果计算（Python API）

```python
from rag_integration import analyze_design_for_hardening, calculate_hardening_metrics

analysis = analyze_design_for_hardening('top.v', recursive=True)
module_strategy_map = {
    'top_module': 'tmr',
    'control_unit': 'parity',
    'data_path': 'ecc',
}

metrics = calculate_hardening_metrics(analysis, module_strategy_map)
summary = metrics['summary']

print(f"模块数: {summary['total_modules']}")
print(f"寄存器数: {summary['total_registers']}")
print(f"面积增加: {summary['area_increase_percent']:.1f}%")
print(f"最大延迟: {summary['max_latency_cycles']} cycles")
print(f"可靠性: {summary['avg_reliability_stars']}")
```

### 6.5 增量加固（Python API）

```python
from rag_integration import analyze_design_for_hardening, run_incremental_hardening

analysis = analyze_design_for_hardening('top.v', recursive=True)
result = run_incremental_hardening(analysis, './incremental_data')

if result['design_changed']:
    print(f"复用模块: {result.get('reused_modules', [])}")
    print(f"新增模块: {result.get('new_modules', [])}")
    print(f"移除模块: {result.get('removed_modules', [])}")
else:
    print("设计未变更，使用缓存策略")

print("\n模块策略映射:")
for module, strategy in result['module_strategy_map'].items():
    print(f"  {module}: {strategy}")
```

### 6.6 故障注入框架 (`fault_injection_framework.py`)

```bash
# 基本故障注入
python sim/formal_test/fault_injection_framework.py

# 指定注入次数
python sim/formal_test/fault_injection_framework.py --num_injections 200

# 分析指定设计
python sim/formal_test/fault_injection_framework.py --design design.v

# 输出 AVF 报告
python sim/formal_test/fault_injection_framework.py --output avf_report.json
```

### 6.7 AIG 分析 (`demo_aig_analysis.py`)

```bash
# 分析默认 AIG 文件
python sim/formal_test/demo_aig_analysis.py

# 分析指定 AIG 文件
python sim/formal_test/demo_aig_analysis.py path/to/design.aig
```

### 6.8 单个加固方法示例

```bash
# cnt_comp 加固示例
python demo_cnt_comp_transform.py

# FSM 识别 + TMR_state 加固
python fsm_tmr_transformer.py --input design.v --output hardened.v

# Parity 转换
python parity_transformer.py --input design.v --output hardened.v

# ECC 转换 (32-bit SECDED)
python ecc_transformer.py --input design.v --output hardened.v

# DICE 寄存器替换 (通过管线)
python hardening_pipeline.py --input design.v --output hardened.v --strategies dice
```

### 6.9 查看所有选项

```bash
python hardening_pipeline.py --help
```

---

## 7. 测试与验证

### 回归测试

所有加固组件均配有完整的回归测试套件，基于 iverilog + vvp 仿真器。

```bash
# 运行所有回归测试
python run_regression.py

# 运行特定组件测试
iverilog -g2012 -o tb_cnt_comp.vvp test_mock_data/tb_cnt_comp.v
vvp tb_cnt_comp.vvp
```

### 回归测试总表

| 组件 | 测试文件 | 测试数 | 状态 |
|:-----|:--------|:------|:-----|
| cnt_comp 基本功能 | `test_mock_data/tb_cnt_comp.v` | 6 | ✅ PASS |
| cnt_comp 故障注入 | `test_mock_data/tb_cnt_comp_fault.v` | 9 | ✅ PASS |
| 奇偶校验 | `test_mock_data/tb_parity.v` | 268 | ✅ PASS |
| DICE | `test_mock_data/tb_dice.v` | 6 | ✅ PASS |
| ECC (SECDED) | `test_mock_data/tb_ecc.v` | 265 | ✅ PASS |
| ECC 混合设计加固 | `test_mock_data/tb_mixed_design_ecc.v` | 39 | ✅ PASS |
| **总计** | — | **593** | ✅ **全部通过** |

### 测试类型说明

- **功能测试**: 验证复位、基本读写、正常计数等功能
- **故障注入测试**: 注入 SEU 验证检错/纠错能力
- **压力/稳定性测试**: 长时间运行（100/500/1000 周期）无虚警
- **穷举模式测试**: Parity 和 ECC 的 8-bit 全 256 模式验证
- **边界测试**: 计数器饱和、Mod 回绕、同值双翻转等边界条件

### 回归效率

全部 593 个测试可在 **约 30 秒** 内完成，适合 CI/CD 流水线集成。

---

## 8. 故障注入验证

### 框架简介

`fault_injection_framework.py` 提供自动化故障注入 → AVF 分析 → 加固评分的完整验证流程。

### 工作流程

```
[1/4] 发现寄存器
  → 从 RTL 设计中提取所有寄存器信号
[2/4] 模拟故障注入
  → 随机翻转寄存器比特，模拟 SEU
[3/4] AVF 分析
  → 计算每个寄存器的架构脆弱性因子 (AVF)
  → AVF = 故障导致输出错误的次数 / 总注入次数
[4/4] 加固效果对比
  → 加固前 AVF 与加固后 AVF 对比
  → 与关键词评分方法对比校准
```

### 输出示例

```
AVF 排名 (Top 5):
  data_reg            : AVF = 46.67%
  addr_reg            : AVF = 35.71%
  flag_reg            : AVF = 34.62%
  state               : AVF = 28.57%
  counter             : AVF = 25.00%

加固效果对比:
  加固前平均 AVF: 34.11%
  加固后平均 AVF: 10.97%
  改善倍数:       3.11×
```

---

## 9. AIG 图分析

### 概述

Phase 3 功能 — 将 RTL 设计综合为 **And-Inverter Graph (AIG)**，利用 **GraphSAGE** 图神经网络进行脆弱性预测。

### 管线组件

| 组件 | 文件 | 功能 |
|:-----|:-----|:------|
| AIG 构建器 | `sim/formal_test/aig_builder.py` (计划中) | yosys 综合封装 |
| AIG 解析器 | `sim/formal_test/aig_parser.py` | AIGER 二进制格式解析 ✅ |
| AIG → PyG 转换 | `sim/formal_test/aig_to_pyg.py` (计划中) | NetworkX → PyG Data |
| AIG 可视化 | `sim/formal_test/aig_visualizer.py` (计划中) | matplotlib/GraphViz 可视化 |
| 脆弱性预测 | `sim/formal_test/gnn_*.py` (计划中) | GraphSAGE 训练与推理 |
| 演示脚本 | `sim/formal_test/demo_aig_analysis.py` | AIG 解析与分析演示 ✅ |
| 模拟 AIG 生成 | `sim/formal_test/gen_mock_aig.py` | 生成测试用 AIG 文件 ✅ |
| yosys Tcl 脚本 | `sim/formal_test/synth_to_aig.tcl` | RTL → AIG 综合流程 ✅ |

### 使用示例

```bash
# Step 1: 生成模拟 AIG 文件 (用于测试)
python sim/formal_test/gen_mock_aig.py

# Step 2: 分析 AIG 图
python sim/formal_test/demo_aig_analysis.py

# Step 3: 使用 yosys 将 RTL 综合为 AIG (需要 yosys)
yosys -c sim/formal_test/synth_to_aig.tcl
```

---

## 10. 常见问题 (FAQ)

### Q1: 如何选择合适的加固策略？

**A**: 使用 `hardening_pipeline.py --strategies auto` 自动分配。工具会识别信号类型（FSM/Counter/Data Path/Control）并为每种类型选择最优策略。也可参考 [第 4 节的策略适用表](#4-加固方法说明)。

### Q2: 安装 pyverilog 失败怎么办？

**A**: 确保 Python ≥ 3.8。使用 `pip install --upgrade pip` 更新 pip，再尝试 `pip install pyverilog`。

### Q3: iverilog 编译报 `procedural continuous assignments` 警告？

**A**: 这是 iverilog 对 `force`/`release` 语句的正常警告，不影响功能。使用 `-g2012` 标志可减少警告。如需完全静默，建议使用商用仿真器（QuestaSim/VCS）。

### Q4: 加固后面积开销比预期大？

**A**: 检查是否所有信号都使用了 Full TMR。可使用混合加固（`--strategies auto`）将轻量策略（cnt_comp、parity）分配给适合的信号，典型节省可达 51.9%。

### Q5: Parity 无法检测双比特错误？

**A**: 这是设计预期。奇偶校验码本质上无法检测偶数比特翻转（2、4、6、8 位）。需要双比特检错时，请改用 ECC SECDED。

### Q6: AIG 分析需要 yosys 吗？

**A**: 基础 AIG 解析（`aig_parser.py`）不需要 yosys，可直接解析现有 `.aig` 文件。如需将 RTL 综合为 AIG，则需要 yosys。

### Q7: ECC 支持哪些数据宽度？

**A**: 当前验证在 32-bit 宽度下完成（码字宽度 38-bit）。对于其他宽度，汉明码的校验矩阵需要重新生成。模板设计支持参数化 `WIDTH`。

### Q8: 如何贡献新的加固模板？

**A**: 在 `test_mock_data/` 下创建模板文件，在 `hardening_pipeline.py` 的 `_apply_*_transformation` 方法中添加变换逻辑，并在 `test_mock_data/` 下添加对应的测试平台。

---

## 11. 文件结构

```
ai_project/common/scripts/
│
├── hardening_pipeline.py            # 统一加固管线（入口）
├── fsm_tmr_transformer.py           # FSM 识别 + TMR_state 变换
├── cnt_comp_transformer.py          # cnt_comp 变换
├── parity_transformer.py            # 奇偶校验变换
├── ecc_transformer.py               # ECC 变换
├── scan_high_fanout_signals.py      # 高扇出信号扫描
├── run_regression.py                # 回归测试运行器
│
├── docs/                            # 文档
│   ├── USER_MANUAL.md               # 本手册
│   ├── HARDENING_OPTIMIZATION_ROADMAP.md     # 优化路线图
│   ├── OPTIMIZATION_COMPLETION_REPORT.md     # 优化完成报告
│   ├── OPTIMIZATION_PHASE2_RESULTS.md        # Phase 2 结果
│   ├── REGRESSION_TEST_SUMMARY_REPORT.md     # 回归测试报告
│   ├── PHASE3_AIG_GRAPHSAGE_TECHNICAL_PLAN.md # Phase 3 技术方案
│   └── ... (其他报告)
│
├── test_mock_data/                  # 测试用例与模板
│   ├── cnt_comp_template.v          # cnt_comp Verilog 模板
│   ├── parity_template.v            # 奇偶校验 Verilog 模板
│   ├── dice_template.v              # DICE Verilog 模板
│   ├── ecc_template.v               # ECC Verilog 模板
│   ├── mixed_design.v               # 混合设计测试用例
│   ├── mixed_design_ecc.v           # ECC 混合设计测试用例
│   ├── tb_cnt_comp.v                # cnt_comp 测试平台
│   ├── tb_cnt_comp_fault.v          # cnt_comp 故障注入测试平台
│   ├── tb_parity.v                  # 奇偶校验测试平台
│   ├── tb_dice.v                    # DICE 测试平台
│   ├── tb_ecc.v                     # ECC 测试平台
│   ├── tb_mixed_design_ecc.v        # ECC 混合设计测试平台
│   └── synth_output.aig             # 模拟 AIG 文件
│
├── sim/                             # 仿真支持
│   ├── run_simulation.py            # 仿真运行器
│   ├── run_regression.ps1           # PowerShell 回归脚本
│   ├── run_verilator_ecc.py         # Verilator ECC 仿真
│   ├── sva_voter_monitor.sv         # SVA 断言监视器
│   │
│   └── formal_test/                 # 形式化验证与 Lint
│       ├── aig_parser.py            # AIG 解析器 ✅
│       ├── demo_aig_analysis.py     # AIG 分析演示 ✅
│       ├── gen_mock_aig.py          # 模拟 AIG 生成 ✅
│       ├── synth_to_aig.tcl         # yosys 综合 Tcl 脚本 ✅
│       ├── fault_injection_framework.py    # 故障注入框架
│       ├── rag_integration.py       # RAG 引擎 + 子模块策略分配
│       ├── test_module_strategy_allocation.py  # 模块策略分配测试
│       ├── test_gui_hierarchical.py # GUI 层次化功能测试
│       └── ... (其他 UVM/形式化验证文件)
│
├── ip_cores/                        # IP 核
│   └── tmr_voter_6ch/              # 6 通道表决器 IP
│
└── reports/                         # 报告
    ├── TMR_HARDENING_ACCEPTANCE_REPORT.md
    └── SVA_REGRESSION_REPORT.md
```

---

*文档生成时间: 2026-07-15*  
*项目版本: v3.7*  
*如有疑问，请参考 `HARDENING_OPTIMIZATION_ROADMAP.md` 了解完整的优化路线图。*  
*子模块级策略功能详细指南: `SUBMODULE_STRATEGY_GUIDE.md`*
