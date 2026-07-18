# RTL 级加固工具用户手册 (User Manual)

> **版本**: v4.0 | **更新日期**: 2026-07-18
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
| 加固效果可视化 | 面积增加、路径延迟、可靠性等指标可视化（柱状图/饼图） |
| 增量加固 | 复用未改动模块的加固结果，提升效率 |
| 子模块接口兼容性 | 检测并解决模块间策略冲突 |
| Web GUI | 基于浏览器的远程配置界面 |
| 故障注入验证 | 自动化故障注入 → AVF 分析 → 加固评分校准 |
| AIG 图分析 | 基于 yosys 综合的 AIG 图脆弱性预测 (Phase 3) |
| GUI & CLI | 图形界面和命令行两种使用方式 |
| **FPGA 比特流加固** | 支持 TMR/ECC/Scrubbing/部分重配置的比特流级加固 |
| **RTL 文件/文件夹/数据集加固** | 三种加固模式：单文件、文件夹批量、数据集处理 |
| **GNN 脆弱性预测** | 基于 GraphSAGE 的寄存器脆弱性评分，F1=0.97+ |
| **模型融合** | GAT/GCN/GraphSAGE 集成学习，加权投票提升预测精度 |
| **迁移学习** | 预训练模型微调，降低训练数据需求 |
| **形式化验证** | 集成 SymbiYosys 进行设计正确性验证 |
| **可靠性报告** | 自动生成 AVF、MTBF、故障率等可靠性指标报告 |

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
| matplotlib | ≥ 3.4 | 可视化图表生成 |
| scikit-learn | ≥ 1.0 | 模型评估与指标计算 |
| symbiyosys | **可选** | 形式化验证 |
| gradio | **可选** | Web GUI 界面 |

### 2.2 安装步骤

```bash
# 1. 克隆项目
git clone <repository_url>
cd ai_project/common/scripts

# 2. 安装 Python 依赖
pip install pyverilog networkx numpy matplotlib scikit-learn
pip install torch torch-geometric    # 可选，用于 GraphSAGE
pip install gradio                   # 可选，用于 Web GUI

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

### GUI 模式（流程导向版）

```bash
# 启动图形界面
python harden_gui.py
```

**启动后显示流程选择首页**，包含以下功能区域：

#### 3.1 首页流程选择

首页展示 4 种加固流程，用户根据需求选择：

| 流程 | 图标 | 说明 | 适用场景 |
|:-----|:-----|:-----|:---------|
| RTL 单文件加固 | 📄 | 对单个 Verilog 文件进行加固 | 单个设计文件 |
| RTL 文件夹批量加固 | 📁 | 批量处理文件夹中的所有 RTL 文件 | 多个文件的项目 |
| RTL 数据集加固 | 📊 | 处理数据集目录下的多个设计项目 | 大规模数据集 |
| FPGA 比特流加固 | 🔧 | 对比特流文件进行加固（TMR/ECC/Scrubbing） | FPGA 设计 |

**快捷操作区域**：
- **加载示例设计**: 快速加载 `mixed_design.v` 示例文件，进入单文件加固流程
- **运行测试套件**: 运行工具验证测试

#### 3.2 流程步骤引导

选择流程后，进入步骤引导界面：

```
┌─────────────────────────────────────────────────────────────┐
│ ← 返回首页    📄 RTL 单文件加固                              │
├─────────────────────────────────────────────────────────────┤
│ ✅ 选择文件    🔴 配置策略    ○ 执行加固    ○ 验证结果    ○ 导出报告 │
│ 已完成         当前步骤       待完成       待完成       待完成      │
├─────────────────────────────────────────────────────────────┤
│                         内容区域                            │
│                    (根据当前步骤动态显示)                     │
├─────────────────────────────────────────────────────────────┤
│ [上一步]                            [下一步/完成]          │
├─────────────────────────────────────────────────────────────┤
│ 输出日志                                                    │
│ [INFO] 日志内容...                                          │
└─────────────────────────────────────────────────────────────┘
```

**步骤指示器说明**：
- ✅ 绿色背景：已完成步骤
- 🔴 橙色背景：当前步骤
- ○ 灰色背景：待完成步骤

#### 3.3 各流程步骤详解

**RTL 单文件加固流程**（5 步）：
1. **选择文件** → 选择待加固的 RTL 文件，显示设计信息（模块名、寄存器数等）
2. **配置策略** → 选择加固策略（TMR/DICE/ECC/Parity/cnt_comp/FSM_TMR）和优化目标
3. **执行加固** → 运行加固管线，生成加固后的 RTL 文件
4. **验证结果** → 查看加固效果（寄存器数、面积开销、可靠性等）
5. **导出报告** → 生成可靠性分析报告

**RTL 文件夹批量加固流程**（5 步）：
1. **选择文件夹** → 选择包含 RTL 文件的文件夹
2. **配置策略** → 选择加固策略
3. **执行批量加固** → 批量处理所有 RTL 文件
4. **查看汇总** → 显示批量处理结果汇总和详细列表
5. **导出报告** → 生成批量加固汇总报告

**RTL 数据集加固流程**（5 步）：
1. **选择数据集** → 选择数据集根目录
2. **配置策略** → 选择加固策略
3. **执行数据集加固** → 处理所有设计项目
4. **数据分析** → 分析各设计加固效果
5. **导出报告** → 生成数据集分析报告

**FPGA 比特流加固流程**（5 步）：
1. **选择比特流** → 选择 FPGA 比特流文件
2. **配置加固方式** → 选择 TMR/ECC/Scrubbing/部分重配置，选择 FPGA 型号
3. **执行比特流加固** → 对比特流进行加固处理
4. **验证比特流** → 验证加固后的比特流完整性
5. **导出结果** → 导出加固后的比特流

#### 3.4 按钮颜色说明

| 按钮颜色 | 用途 | 示例 |
|:---------|:-----|:-----|
| 🔵 **蓝色** | 流程选择 | 首页流程按钮 |
| 🟢 **绿色** | 执行操作 | "开始执行加固"、"生成报告" |
| 🟠 **橙色** | 导航操作 | "上一步"、"下一步" |

#### 3.5 帮助对话框

点击状态栏的 **帮助** 按钮，打开帮助对话框：

- **快速入门**: 使用流程和推荐工作流说明
- **输出目录**: 输出文件的分类存储说明

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

# FPGA 比特流加固
python sim/formal_test/fpga_bitstream_hardening.py --bitstream design.bit --output hardened.bit

# GNN 脆弱性预测
python sim/formal_test/gnn_inference.py --input design.v

# 生成可靠性报告
python sim/formal_test/reliability_report.py --input design.v --output report.json

# 运行示例代码
python sim/formal_test/examples.py
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
| 工具栏 | 顶部 | 13个功能按钮，快速切换标签页 |
| 左侧面板 | 左侧 | 项目资源树、加固策略选择 |
| 标签页区域 | 中部 | 13个功能标签页 |
| 右侧面板 | 右侧 | 设计信息、快捷操作 |
| 状态栏 | 底部 | 当前状态、上次操作记录、版本信息 |

### 5.3 完整使用流程（从启动到完成）

以下是使用 RTL 加固工具的完整工作流程，以示例设计 `mixed_design.v` 为例：

#### 步骤 1: 启动 GUI

```bash
cd ai_project/common/scripts
python harden_gui.py
```

启动后会看到主界面，包含：
- 顶部工具栏（13个功能按钮）
- 左侧项目资源树和策略选择
- 中间标签页区域（默认显示"加固管线"）
- 右侧设计信息和快捷操作
- 底部状态栏和输出区域

#### 步骤 2: 加载示例设计

**方法 A: 使用"加载示例"按钮（推荐）**

1. 在右侧面板"快捷操作"区域点击 **加载示例** 按钮
2. 弹出提示框，显示设计信息：
   - 模块名: mixed_design
   - 寄存器数: 12
   - 端口数: 8
   - 子模块数: 3
3. 各标签页的文件路径自动填充

**方法 B: 手动选择文件**

1. 在"加固管线"标签页点击 **浏览...** 按钮
2. 导航到 `test_mock_data/mixed_design.v`
3. 点击确定

#### 步骤 3: 策略推荐（可选但推荐）

1. 切换到 **策略推荐** 标签页
2. 文件路径已自动填充（来自步骤2）
3. 选择优化目标（balanced/reliability/area/performance）
4. 点击 **生成推荐** 按钮
5. 等待分析完成，查看推荐结果表格：
   - 每个模块的推荐策略
   - 策略评分
   - 备选策略列表

**示例输出**:
```
模块名称     模块类型     推荐策略     评分     备选策略
mixed_design counter     cnt_comp     95.00    tmr, ecc
```

#### 步骤 4: 层次化加固配置

1. 切换到 **层次化加固** 标签页
2. 文件路径已自动填充
3. 点击 **加载设计** 按钮
4. 左侧树状视图显示模块层次结构
5. 在树状视图中选择模块
6. 在右侧策略下拉菜单中选择加固策略（8种可选）
7. 点击 **应用策略** 保存配置
8. 重复为其他模块配置策略
9. 点击 **运行层次化加固** 生成加固结果

**策略配置示例**:
```
top_module     → tmr
control_unit   → parity
data_path      → ecc
fsm_core       → onehot_fsm
```

#### 步骤 5: 效果可视化

1. 切换到 **效果可视化** 标签页
2. 点击 **计算指标** 按钮
3. 查看加固指标摘要：
   - 模块数、寄存器数
   - 面积增加百分比
   - 延迟开销
   - 可靠性评级
4. 查看可视化图表：
   - 面积开销柱状图
   - 可靠性对比柱状图
   - 策略分布饼图
5. 点击 **生成 HTML 报告** 导出完整报告

#### 步骤 6: 信号扫描（可选）

1. 切换到 **信号扫描** 标签页
2. 点击 **选择目录...** 选择 RTL 文件所在目录
3. 设置扇入/扇出阈值（默认3）
4. 点击 **开始扫描** 按钮
5. 查看扫描结果表格：
   - 信号名、位宽、活跃度
   - 推荐策略、优先级
6. 点击 **导出报告** 导出 Markdown 报告

#### 步骤 7: AIG 分析（可选，需要 yosys）

1. 切换到 **AIG 分析** 标签页
2. 点击 **生成模拟 AIG** 按钮（或选择已有 AIG 文件）
3. 点击 **解析并分析** 按钮
4. 查看分析结果：
   - AIG 文件统计信息
   - 高扇出节点列表
   - 脆弱性分析结果

#### 步骤 8: 测试运行（验证工具正确性）

1. 切换到 **测试运行** 标签页
2. 选择测试套件（可多选）
3. 点击 **运行选定套件** 或 **运行全部** 按钮
4. 查看测试结果：
   - 每个套件的 PASS/FAIL 状态
   - 测试摘要（通过数/失败数）
   - 测试日志输出

#### 步骤 9: 增量加固（设计修改后使用）

1. 修改 RTL 设计文件
2. 切换到 **增量加固** 标签页
3. 点击 **浏览...** 选择修改后的文件
4. 点击 **运行增量加固** 按钮
5. 工具自动检测变更：
   - 复用未改动模块的加固策略
   - 仅处理新增或修改的模块

#### 步骤 10: 可靠性报告

1. 切换到 **可靠性报告** 标签页
2. 点击 **浏览...** 选择 RTL 文件
3. 点击 **生成可靠性报告** 按钮
4. 查看报告：
   - AVF（架构脆弱性因子）
   - MTBF（平均无故障时间）
   - 故障率计算
   - 改进建议

#### 步骤 11: 导出报告

1. 在任意标签页中完成操作后
2. 切换到 **报告** 标签页
3. 点击 **刷新列表** 更新报告列表
4. 选择报告并点击 **打开报告** 在浏览器中查看

### 5.4 推荐工作流程总结

```
┌─────────────────────────────────────────────────────────────────────┐
│                         完整工作流程                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  启动GUI  ──▶  加载示例  ──▶  策略推荐  ──▶  层次化加固           │
│                                      │            │                │
│                                      ▼            ▼                │
│                                   查看推荐      配置策略            │
│                                      │            │                │
│                                      └─────┬─────┘                │
│                                            ▼                      │
│                                     运行层次化加固                  │
│                                            │                      │
│                                            ▼                      │
│                                     效果可视化                      │
│                                            │                      │
│                                            ▼                      │
│                              ┌───── 生成 HTML 报告 ─────┐          │
│                              │                          │          │
│                              ▼                          ▼          │
│                         信号扫描                    可靠性报告        │
│                              │                          │          │
│                              └───── 导出报告 ─────┘                │
│                                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.5 工具验证情况

通过运行示例代码验证了以下功能的可行性：

| 功能 | 状态 | 说明 |
|:-----|:-----|:-----|
| 基础加固流程 | ✅ 通过 | 成功生成加固后的 RTL 文件 |
| 单个文件加固 | ✅ 通过 | 支持多种优化目标 |
| 文件夹批量加固 | ✅ 通过 | 28/28 文件成功加固 |
| 数据集加固 | ✅ 通过 | 生成汇总报告 |
| 增量加固 | ✅ 通过 | 变更检测正常 |
| 可靠性分析报告 | ✅ 通过 | AVF/MTBF 计算正常 |
| 策略自动选择 | ✅ 通过 | 多策略评分排序正常 |
| 形式化验证 | ✅ 通过 | 验证流程正常 |
| FPGA 比特流加固 | ✅ 通过 | 模块可用 |
| 故障注入测试 | ✅ 通过 | SEU 注入正常 |

### 5.6 标签页详细说明

#### 5.6.1 加固管线 (Pipeline)

**功能**: 基础的 RTL 加固功能，支持单文件、文件夹、数据集三种模式的批量加固。

**输入**:
- RTL 文件（.v/.sv）、文件夹或数据集目录
- 加固策略选择（TMR/DICE/ECC/Parity/cnt_comp/FSM_TMR）

**输出**:
- 加固后的 RTL 文件（_hardened.v）
- 加固效果汇总（模块数、寄存器数、面积开销、可靠性）
- iverilog 编译检查结果

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **浏览...** | 选择输入文件/文件夹/数据集目录 |
| **选择路径...** | 指定输出路径 |
| **执行加固** | 按所选策略执行加固管线 |

**操作流程**:
1. 选择加固模式（单文件/文件夹/数据集）
2. 点击"浏览..."选择输入
3. 勾选加固策略
4. 点击"执行加固"
5. 查看输出区域的加固结果

---

#### 5.6.2 测试运行 (Test Runner)

**功能**: 执行回归测试套件，验证工具各组件的正确性。

**输入**: 测试套件选择（cnt_comp/parity/dice/ecc/mixed_ecc/voter_debug/python_unit）

**输出**:
- 每个测试套件的 PASS/FAIL 结果
- 测试摘要（通过数/失败数）
- 测试日志输出

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **运行选定套件** | 运行勾选的测试套件 |
| **运行全部** | 运行所有测试套件 |

**测试套件说明**:
| 套件 | 测试内容 |
|:-----|:---------|
| cnt_comp | 计数器比较器基本功能测试（6项） |
| parity | 奇偶校验功能测试（268项） |
| dice | DICE 寄存器功能测试（6项） |
| ecc | ECC SECDED 纠错码测试（265项） |
| mixed_ecc | 混合 ECC 设计加固测试（39项） |
| voter_debug | 表决器调试日志测试 |
| python_unit | Python 单元测试（24项） |

---

#### 5.6.3 信号扫描 (Signal Scan)

**功能**: 扫描 RTL 设计中的高扇出信号，识别脆弱信号并推荐加固策略。

**输入**:
- RTL 目录路径
- 活跃度阈值（扇入+扇出的阈值）

**输出**:
- 高扇出信号列表（表格形式）
- 每个信号的位宽、活跃度、推荐策略、优先级
- Markdown 格式的扫描报告

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **选择目录...** | 选择包含 RTL 文件的目录 |
| **开始扫描** | 扫描目录中所有未加固的高扇出信号 |
| **导出报告** | 将扫描结果导出为 Markdown 报告文件 |

**扫描内容**:
- 识别设计中扇入/扇出超过阈值的信号
- 分析信号类型（控制/数据/状态）
- 计算信号活跃度（扇入 + 扇出）
- 根据信号特性推荐加固策略

---

#### 5.6.4 AIG 分析 (AIG Analysis)

**功能**: 对 AIG（And-Inverter Graph）文件进行分析，提取电路结构信息和脆弱性分析。

**输入**: .aig 格式的 AIG 文件（可自动生成模拟文件）

**输出**:
- AIG 文件统计信息（节点数、AND门数、输入/输出数）
- 高扇出节点列表
- 脆弱性分析结果
- 电路结构摘要

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **浏览...** | 选择已有的 AIG 文件 |
| **生成模拟 AIG** | 自动生成模拟 AIG 文件用于演示 |
| **解析并分析** | 解析 AIG 文件并显示统计和脆弱性信息 |

**解析内容**:
- AIG 文件头信息解析
- AND 门节点提取
- 输入/输出节点识别
- 扇入/扇出分析
- 脆弱性评分计算

---

#### 5.6.5 层次化加固 (Hierarchical Hardening)

**功能**: 以模块树状视图展示设计层次，为每个模块独立配置加固策略。

**与「加固管线」的区别**:
| 特性 | 加固管线 | 层次化加固 |
|:-----|:---------|:-----------|
| 策略配置 | 全局统一策略 | 模块级独立策略 |
| 界面 | 简单表单 | 树状视图 + 配置面板 |
| 适用场景 | 快速加固、批量处理 | 精细策略配置 |
| 配置复杂度 | 低 | 高 |

**输入**:
- 顶层 RTL 文件
- 每个模块的加固策略选择

**输出**:
- 加固后的 RTL 文件（_hierarchical_hardened.v）
- 策略配置 JSON 文件
- 模块级策略映射

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **浏览...** | 选择顶层 RTL 文件 |
| **加载设计** | 解析模块层次结构并显示树状视图 |
| **应用策略** | 将所选策略应用到当前选中模块 |
| **全部应用默认** | 将当前策略应用到所有模块 |
| **运行层次化加固** | 根据模块级策略配置运行加固 |
| **导出策略配置** | 导出当前策略配置为 JSON 文件 |

---

#### 5.6.6 策略推荐 (Strategy Recommendation)

**功能**: 基于设计分析结果，自动推荐最优加固策略。

**输入**:
- RTL 文件
- 优化目标（balanced/reliability/area/performance）

**输出**:
- 每个模块的推荐策略
- 策略评分
- 备选策略列表

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **浏览...** | 选择 RTL 文件 |
| **生成推荐** | 分析设计并生成策略推荐 |

**优化目标说明**:
| 目标 | 说明 |
|:-----|:-----|
| balanced | 平衡面积和可靠性（默认） |
| reliability | 优先保证可靠性 |
| area | 优先最小化面积开销 |
| performance | 优先最小化延迟开销 |

---

#### 5.6.7 效果可视化 (Visualization)

**功能**: 计算并可视化加固效果指标，包括面积开销、可靠性、策略分布等。

**输入**:
- RTL 文件
- 策略配置（可选）

**输出**:
- 加固指标摘要（模块数、寄存器数、面积开销、延迟开销、可靠性）
- 面积开销柱状图
- 可靠性对比柱状图
- 策略分布饼图
- HTML 格式的可视化报告

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **浏览...** | 选择 RTL 文件 |
| **计算指标** | 计算加固效果指标并更新图表 |
| **生成 HTML 报告** | 生成可视化 HTML 报告 |

**图表说明**:
| 图表类型 | 数据展示 | 用途 |
|:---------|:---------|:-----|
| 面积开销柱状图 | 各模块面积开销百分比 | 快速识别面积开销较大的模块 |
| 可靠性对比柱状图 | 各模块可靠性评级（百分比） | 评估加固后的可靠性水平 |
| 策略分布饼图 | 各策略使用比例 | 了解策略分配情况 |

---

#### 5.6.8 增量加固 (Incremental Hardening)

**功能**: 检测设计变更，复用未改动模块的加固结果，提升迭代效率。

**输入**: 修改后的 RTL 文件

**输出**:
- 变更检测报告
- 增量加固后的 RTL 文件
- 复用的策略配置

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **浏览...** | 选择修改后的 RTL 文件 |
| **运行增量加固** | 检测变更并执行增量加固 |

**功能特性**:
- 检测设计文件是否发生变化
- 复用未改动模块的加固策略
- 仅处理新增或修改的模块
- 加速设计迭代周期

---

#### 5.6.9 FPGA 加固 (FPGA Hardening)

**功能**: 对 FPGA 比特流进行加固处理，支持 TMR/ECC/Scrubbing/部分重配置。

**输入**:
- FPGA 比特流文件（.bit/.bin）
- 加固策略选择

**输出**:
- 加固后的比特流文件
- 加固配置报告

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **浏览...** | 选择比特流文件 |
| **运行 FPGA 加固** | 执行比特流级加固 |

---

#### 5.6.10 可靠性报告 (Reliability Report)

**功能**: 自动生成可靠性分析报告，包括 AVF、MTBF、故障率等指标。

**输入**: RTL 文件或加固后的设计

**输出**:
- AVF（架构脆弱性因子）计算结果
- MTBF（平均无故障时间）估算
- 故障率计算
- 加固前后可靠性对比

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **浏览...** | 选择 RTL 文件 |
| **生成可靠性报告** | 计算并生成可靠性报告 |

---

#### 5.6.11 形式化验证 (Formal Verification)

**功能**: 集成 SymbiYosys 进行设计正确性验证。

**输入**: RTL 文件

**输出**:
- 等价性检查结果
- 属性验证结果
- SVA 断言生成

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **浏览...** | 选择 RTL 文件 |
| **运行形式化验证** | 执行形式化验证 |

---

#### 5.6.12 Web GUI

**功能**: 启动基于浏览器的远程 GUI 界面，支持远程访问和操作。

**输入**: 无

**输出**:
- Web GUI 服务启动地址（通常为 http://localhost:7860）
- 浏览器界面访问

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **启动 Web GUI** | 启动 Gradio Web 服务 |

---

#### 5.6.13 报告 (Reports)

**功能**: 查看和管理所有生成的加固报告。

**输入**: 无（自动读取 reports 目录）

**输出**:
- 报告列表
- 报告内容预览

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **刷新列表** | 刷新报告列表 |
| **打开报告** | 在默认浏览器中打开报告 |

---

### 5.6.14 三种加固模式（v3.7 新增）

GUI 支持三种加固模式，适用于不同规模的设计场景：

| 模式 | 说明 | 适用场景 |
|:-----|:-----|:---------|
| **RTL 文件加固** | 对单个 RTL 文件进行加固 | 小型设计、快速验证 |
| **RTL 文件夹加固** | 对文件夹中所有 RTL 文件批量加固 | 中型设计、多个模块 |
| **RTL 数据集加固** | 对数据集目录进行批量加固处理 | 大规模设计、多项目 |

**操作步骤**:
1. 在"加固管线"标签页中
2. 选择加固模式（单文件/文件夹/数据集）
3. 点击"浏览..."选择文件、文件夹或数据集目录
4. 配置加固策略后点击"执行加固"

### 5.6.15 加载示例（v3.7 新增）

**功能**: 快速加载示例设计文件，方便用户体验工具功能。

**位置**: 首页"快捷操作"区域

**作用**:
- 自动加载示例文件 `mixed_design.v`
- 进入 RTL 单文件加固流程
- 显示设计信息（模块名、寄存器数、端口数、子模块数）
- 弹出使用提示，指导用户下一步操作

**核心按钮**:
| 按钮 | 作用 |
|:-----|:-----|
| **加载示例** | 加载预配置的示例设计文件 |

### 5.6.16 输出目录结构（v3.7 新增）

**功能**: 不同流程的输出文件分类存储，方便查阅和管理。

**目录结构**:
```
output/
├── rtl_single/          # RTL 单文件加固输出
│   ├── <timestamp>/
│   │   ├── design_hardened.v    # 加固后的 RTL 文件
│   │   ├── report.html          # 可靠性报告
│   │   └── analysis.json        # 分析数据
│   └── ...
├── rtl_folder/          # RTL 文件夹批量加固输出
│   ├── <timestamp>/
│   │   ├── file1_hardened.v
│   │   ├── file2_hardened.v
│   │   ├── summary_report.html  # 汇总报告
│   │   └── analysis.json
│   └── ...
├── rtl_dataset/         # RTL 数据集加固输出
│   ├── <timestamp>/
│   │   ├── project1/
│   │   │   └── hardened.v
│   │   ├── project2/
│   │   │   └── hardened.v
│   │   ├── dataset_report.html  # 数据集报告
│   │   └── analysis.json
│   └── ...
├── fpga_bitstream/      # FPGA 比特流加固输出
│   ├── <timestamp>/
│   │   ├── design_hardened.bit  # 加固后的比特流
│   │   ├── config_report.html   # 配置报告
│   │   └── analysis.json
│   └── ...
├── reports/             # 所有报告汇总
│   └── ...
└── logs/                # 日志文件
    └── ...
```

**分类说明**:
| 目录 | 用途 | 内容 |
|:-----|:-----|:-----|
| `rtl_single` | 单文件加固结果 | 加固后的 RTL 文件、可靠性报告 |
| `rtl_folder` | 文件夹批量加固结果 | 所有加固文件、汇总报告 |
| `rtl_dataset` | 数据集加固结果 | 各项目加固文件、数据集分析报告 |
| `fpga_bitstream` | 比特流加固结果 | 加固后的比特流文件、配置报告 |
| `reports` | 报告汇总 | 所有生成的 HTML 报告 |
| `logs` | 日志文件 | 工具运行日志 |

**时间戳命名**:
- 每个输出目录下按时间戳创建子目录（格式：`YYYYMMDD_HHMMSS`）
- 便于区分多次运行的结果

---

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
| **面积开销柱状图** | 直观展示各模块的面积开销对比 |
| **可靠性对比柱状图** | 展示各模块的可靠性评级 |
| **策略分布饼图** | 展示不同加固策略的使用比例 |
| HTML 报告 | 生成可视化 HTML 报告 |

**图表说明**:

| 图表类型 | 数据展示 | 用途 |
|:---------|:---------|:-----|
| **面积开销柱状图** | 各模块面积开销百分比 | 快速识别面积开销较大的模块 |
| **可靠性对比柱状图** | 各模块可靠性评级（1-5星） | 评估加固后的可靠性水平 |
| **策略分布饼图** | 各策略使用比例 | 了解策略分配情况 |

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
| **Python 单元测试** | `sim/formal_test/test_*.py` | **24** | ✅ PASS |
| **GNN 模型测试** | `test_qat_int8.py`, `test_int8_quantization.py` | **5** | ✅ PASS |
| **FPGA 部署测试** | `test_fpga_deploy.py` | **3** | ✅ PASS |
| **总计** | — | **683+** | ✅ **全部通过** |

### 测试类型说明

- **功能测试**: 验证复位、基本读写、正常计数等功能
- **故障注入测试**: 注入 SEU 验证检错/纠错能力
- **压力/稳定性测试**: 长时间运行（100/500/1000 周期）无虚警
- **穷举模式测试**: Parity 和 ECC 的 8-bit 全 256 模式验证
- **边界测试**: 计数器饱和、Mod 回绕、同值双翻转等边界条件
- **GNN 模型测试**: 验证 GraphSAGE 脆弱性预测精度（F1=0.97+）
- **FPGA 部署测试**: 验证量化模型在 FPGA 上的推理正确性

### 回归效率

全部 683+ 个测试可在 **约 30 秒** 内完成，适合 CI/CD 流水线集成。

### GNN 模型评估结果

| 模型 | 参数数量 | Test F1 | 训练时长 |
|:-----|:---------|:--------|:---------|
| SAGE2-Lite-64 | 6,385 | 0.9707 | ~6 分钟 |
| SAGE2-Lite-32 | 2,177 | 0.9614 | ~2.5 分钟 |
| SAGE3-Lite-32 | 4,257 | 0.9574 | ~4.5 分钟 |

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
│       ├── gnn_vulnerability.py     # GNN 脆弱性预测
│       ├── graphsage_model.py       # GraphSAGE 模型定义
│       ├── gnn_inference.py         # GNN 推理接口
│       ├── model_fusion.py          # GAT/GCN/GraphSAGE 模型融合
│       ├── transfer_learning.py     # 迁移学习模块
│       ├── fpga_bitstream_hardening.py    # FPGA 比特流加固
│       ├── formal_verification.py   # 形式化验证
│       ├── reliability_report.py    # 可靠性报告生成
│       ├── incremental_hardening.py # 增量加固模块
│       ├── examples.py              # 使用示例代码
│       ├── harden_gui.py            # GUI 主界面
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
