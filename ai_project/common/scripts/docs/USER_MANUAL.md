# RTL 级加固工具用户手册 (User Manual)

> **版本**: v2.0 | **更新日期**: 2026-07-12
> **项目**: RTL Hardening Tool — 差异化混合加固管线

---

## 1. 概述

RTL 级加固工具是一个自动化的 **Verilog RTL 设计加固 (Hardening)** 工具集，能够对数字电路设计自动施加多种抗单粒子翻转 (SEU) 的加固方法。工具从单一的 **TMR（三模冗余）** 扩展到 **7 种加固策略**，支持按信号类型自动分配最优加固方案，并通过 **AIG 图分析** 和 **GraphSAGE 脆弱性预测** 实现智能化加固决策。

### 核心能力

| 能力 | 说明 |
|:-----|:------|
| 多种加固策略 | TMR、TMR_state、DICE、ECC、Parity、cnt_comp |
| 差异混合加固 | 按信号类型（FSM/Counter/Data Path/Control）分配不同策略 |
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
# 启动图形界面 (开发中)
python harden_gui.py
```

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

---

## 5. GUI 使用指南

> **注意**: GUI 界面目前处于开发阶段，功能通过命令行完成。

### 主窗口

启动后显示主界面，包含以下功能区域：

| 区域 | 功能 |
|:-----|:------|
| 文件菜单 | 打开/保存 Verilog 设计文件 |
| 信号列表 | 显示解析后的所有信号及其类型 |
| 策略面板 | 为每个信号选择加固策略 |
| 输出窗口 | 显示加固过程和结果 |
| 状态栏 | 显示当前操作状态 |

### 标签页说明

| 标签页 | 功能 |
|:-------|:------|
| 设计加载 | 导入 Verilog 设计，AST 解析 |
| 信号分析 | 查看信号类型、扇出、脆弱性评分 |
| 策略配置 | 手动或自动分配加固策略 |
| 加固执行 | 运行加固变换，查看加固后代码 |
| 验证测试 | 编译、仿真、故障注入 |

### 操作流程

1. **加载设计**: 打开 Verilog 文件或粘贴代码
2. **分析信号**: 自动识别信号类型（FSM/Counter/Data Path/Control）
3. **配置策略**: 手动选择或使用 `auto` 模式自动分配
4. **执行加固**: 查看加固后的 Verilog 代码
5. **验证结果**: 运行 iverilog 编译和仿真测试

---

## 6. 命令行使用

### 加固管线 (`hardening_pipeline.py`)

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

**输出文件**:
- `hardened.v` — 加固后的 Verilog 代码
- `hardened_meta.json` — 加固元数据（策略分配、面积估计等）

### 故障注入框架 (`fault_injection_framework.py`)

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

### AIG 分析 (`demo_aig_analysis.py`)

```bash
# 分析默认 AIG 文件
python sim/formal_test/demo_aig_analysis.py

# 分析指定 AIG 文件
python sim/formal_test/demo_aig_analysis.py path/to/design.aig
```

### 单个加固方法示例

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

### 查看所有选项

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

*文档生成时间: 2026-07-12*  
*项目版本: v2.0*  
*如有疑问，请参考 `HARDENING_OPTIMIZATION_ROADMAP.md` 了解完整的优化路线图。*
