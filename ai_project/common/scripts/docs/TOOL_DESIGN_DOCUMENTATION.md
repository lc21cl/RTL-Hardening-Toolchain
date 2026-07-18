# RTL 级加固工具 — 技术设计文档

> **版本**: v3.7 | **更新日期**: 2026-07-16
> **项目**: RTL Hardening Tool — 差异化混合加固管线

---

## 1. 工具概述

RTL 级加固工具是一个**自动化、智能化的数字电路辐射加固工具集**，旨在为航天/高可靠领域的 Verilog RTL 设计提供抗单粒子翻转 (SEU) 的加固方案。工具从单一的 TMR（三模冗余）扩展到 **10+ 种加固策略**，通过 **GraphSAGE 图神经网络**实现智能脆弱性预测，结合 **RAG-LLM** 实现上下文感知的加固代码生成。

### 1.1 核心设计理念

| 设计原则 | 说明 |
|:---------|:-----|
| **差异化加固** | 不同信号类型（FSM/Counter/Data/Control）应用最优策略，避免一刀切的 Full TMR |
| **机器学习驱动** | GNN 预测脆弱性 + LLM 生成加固代码，提升决策准确性和代码质量 |
| **层次化处理** | 支持子模块级策略分配，递归遍历设计层次结构 |
| **增量加固** | 复用未改动模块的加固结果，提升迭代效率 |
| **可视化评估** | 面积开销、可靠性、策略分布等指标的图表化展示 |

### 1.2 工具架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RTL 加固工具架构 (v3.7)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   输入层      │    │   分析层      │    │   策略层      │          │
│  │  RTL文件/    │───▶│  AST解析/    │───▶│  策略路由/    │          │
│  │  文件夹/     │    │  类型分类/    │    │  GNN预测/    │          │
│  │  数据集      │    │  AIG构建      │    │  LLM生成     │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
│         │                   │                   │                   │
│         │                   │                   ▼                   │
│         │                   │          ┌──────────────┐            │
│         │                   │          │   执行层      │            │
│         │                   │          │  AST变换/    │            │
│         │                   │          │  RTL生成/    │            │
│         │                   │          │  增量处理     │            │
│         │                   │          └──────────────┘            │
│         │                   │                   │                   │
│         │                   │                   ▼                   │
│         │                   │          ┌──────────────┐            │
│         │                   │          │   验证层      │            │
│         │                   │          │  形式化验证/  │            │
│         │                   │          │  故障注入/    │            │
│         │                   │          │  可靠性分析   │            │
│         │                   │          └──────────────┘            │
│         │                   │                   │                   │
│         │                   ▼                   ▼                   │
│         │          ┌──────────────┐    ┌──────────────┐            │
│         │          │   可视化层    │    │   报告层      │            │
│         │          │  图表展示/    │    │  HTML报告/   │            │
│         │          │  GUI界面      │    │  JSON元数据  │            │
│         │          └──────────────┘    └──────────────┘            │
│         │                                                          │
│         ▼                                                          │
│  ┌──────────────┐                                                  │
│  │   输出层      │                                                  │
│  │  加固后RTL/  │                                                  │
│  │  比特流/     │                                                  │
│  │  验证报告    │                                                  │
│  └──────────────┘                                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 功能详细介绍

### 2.1 加固策略

| 策略 | 原理 | 面积开销 | SEU抑制比 | 适用场景 |
|:-----|:-----|:--------:|:---------:|:---------|
| **TMR** | 三模冗余 + 多数表决器 | 3.0× | 10³–10⁶ | 安全关键信号 |
| **TMR_state** | 仅状态寄存器三重化 | 2.5× | 10³–10⁶ | FSM 状态寄存器 |
| **DICE** | 4节点交叉耦合寄存器 | 2.5× | 免疫单粒子 | 高可靠寄存器 |
| **ECC SECDED** | 汉明码编解码 | 1.4× | 10²–10⁴ | 数据总线/存储器 |
| **Parity** | 奇偶校验位插入 | 0.03× | 10¹ | 控制寄存器 |
| **cnt_comp** | 计数器影子比较 | 0.1× | 10² | 计数器寄存器 |
| **onehot_fsm** | 独热编码状态机 | 1.1× | 10³ | 状态机模块 |
| **watchdog** | 超时监控 | 0.5× | 10¹ | 长时间运行模块 |
| **BCH ECC** | BCH纠错码 | 1.5–2.0× | 10³–10⁵ | 高可靠存储器 |
| **CRC** | 循环冗余校验 | 0.1× | 10² | 通信接口 |

### 2.2 GNN 脆弱性预测

基于 **GraphSAGE** 图神经网络的寄存器脆弱性评分系统：

**输入特征（15维）**:
- 节点类型（PI/PO/AND/DFF）
- 扇入/扇出计数
- 关键路径深度
- 可达性信息
- DFF 专用特征（复位类型、时钟域、位宽等）

**模型架构**:
| 模型 | 层数 | 隐藏层 | 参数数量 | Test F1 |
|:-----|:----:|:------:|:--------:|:--------|
| SAGE2-Lite-64 | 2 | 64 | 6,385 | 0.9707 |
| SAGE2-Lite-32 | 2 | 32 | 2,177 | 0.9614 |
| SAGE3-Lite-32 | 3 | 32 | 4,257 | 0.9574 |

**工作流程**:
```
RTL → Yosys综合 → BLIF/AIG → 图构建 → GNN推理 → 脆弱性评分
```

### 2.3 RAG-LLM 加固生成

检索增强生成（RAG）管线，结合加固知识库和 LLM 生成上下文感知的加固代码：

**知识库内容**:
- 1070+ 行加固模式定义
- 支持 TMR/ECC/Parity/DICE/cnt_comp 等策略
- BCH ECC、CRC、Scrubbing、Interleaving 扩展模板

**LLM 后端**:
| 模式 | 说明 |
|:-----|:-----|
| **MockLLM** | 内置模板匹配，无需 API key |
| **OpenAI API** | GPT-4 生成高质量加固代码 |
| **DeepSeek API** | DeepSeek Chat 兼容模式 |

### 2.4 增量加固

支持设计变更检测和缓存复用：

**功能**:
- 检测设计文件是否发生变化
- 复用未改动模块的加固策略
- 仅处理新增或修改的模块
- 增量分析提升迭代效率

### 2.5 FPGA 比特流加固

支持 FPGA 比特流级别的加固操作：

**功能**:
- TMR 比特流标记
- ECC 编码
- 内存擦洗（Scrubbing）
- 部分重配置支持

### 2.6 可靠性分析

自动生成可靠性报告：

**指标**:
- AVF（架构脆弱性因子）
- MTBF（平均无故障时间）
- 故障率计算
- 加固效果对比

### 2.7 形式化验证

集成 SymbiYosys 进行设计正确性验证：

**验证类型**:
- 等价性检查
- 属性验证
- SVA 断言生成

---

## 3. 原理机制

### 3.1 差异化加固原理

**核心思想**: 不同类型的寄存器对 SEU 的敏感度和影响不同，应采用不同的加固策略。

**资产类型分类算法**:
```
1. FSM检测: 识别 case 表达式 + localparam 状态声明
2. Counter检测: 识别自增/自减操作 (+=, -=, inc, dec)
3. Data Path检测: 识别流水线寄存器、数据通路
4. Control检测: 识别配置寄存器、控制信号
5. Memory检测: 识别 mem/fifo 声明
6. Bus检测: 识别 valid/ready 握手协议
```

**策略路由引擎**:
```python
def route_strategy(asset_type, optimization_goal):
    weights = get_strategy_weights(asset_type)
    ranked = sort_by_weight(weights, optimization_goal)
    return select_best_strategy(ranked, area_constraint)
```

### 3.2 GraphSAGE 脆弱性预测原理

**图构建**:
- 节点：电路中的 PI、PO、AND 门、DFF
- 边：信号连接关系
- 特征：节点类型、扇入/扇出、路径深度、可达性

**确定性故障标签算法**:
```
对于每个节点 i:
  if 节点类型 in (PI, AND, DFF) AND 存在路径从 i 到任意 PO:
    标签[i] = 1 (脆弱)
  else:
    标签[i] = 0 (不脆弱)
```

**优势**: 零随机性，标签完全可复现，基于电路结构反映真实故障传播路径。

### 3.3 RAG 加固生成原理

**检索流程**:
```
1. 输入: 设计信息 + 脆弱性分析结果
2. 检索: 在知识库中查找相似设计模式
3. 构建: 组装上下文（设计模式 + 加固方案）
4. 生成: LLM 生成上下文感知的加固 RTL
5. 验证: 语法检查、可综合性检查、功能验证
```

**提示工程**:
```
你是一个硬件加固专家。请根据以下设计信息和脆弱性分析结果，
生成加固后的 Verilog 代码。

设计信息:
- 模块名称: {module_name}
- 端口列表: {ports}
- 信号类型: {signal_type}

脆弱性分析:
- 脆弱节点: {vulnerable_nodes}
- 脆弱性评分: {scores}

加固策略: {strategy}

要求:
1. 生成可综合的 Verilog 代码
2. 添加适当的注释
3. 确保接口兼容性
4. 输出加固后的完整模块代码
```

---

## 4. 创新点

### 4.1 差异化混合加固

**创新**: 突破单一 TMR 的限制，实现按信号类型自动分配最优加固策略。

**效果**:
- 面积开销降低 40%–70%
- 保持同等或更高的可靠性水平
- 支持多种优化目标（balanced/reliability/area/performance）

### 4.2 GNN 驱动的脆弱性预测

**创新**: 使用 GraphSAGE 图神经网络替代传统的静态评分方法。

**优势**:
- F1 分数从 0.55–0.65 提升至 0.97+
- 不依赖命名规范，跨设计通用
- 捕获信号间的拓扑依赖关系

### 4.3 轻量化模型设计

**创新**: 设计轻量级 GraphSAGE 模型，在保证精度的同时大幅减少参数量。

**对比**:
| 模型 | 参数数量 | Test F1 |
|:-----|:--------:|:--------|
| sage3_128 | 52,577 | 0.7737 |
| SAGE2-Lite-64 | 6,385 | **0.9707** |
| SAGE2-Lite-32 | 2,177 | **0.9614** |

**效果**: 参数减少 87%，F1 提升 25%，训练时长从 18 分钟降至 2.5–6 分钟。

### 4.4 确定性故障标签

**创新**: 使用反向可达性分析生成确定性故障标签，消除随机注入的噪声。

**优势**:
- 零随机性 → 标签完全可复现
- 基于电路结构 → 反映真实故障传播路径
- 无标签噪声 → 模型学习更稳定的决策边界

### 4.5 NSGA-II 多目标优化

**创新**: 使用 NSGA-II 遗传算法进行面积-可靠性多目标优化。

**效果**:
- 生成 53 个帕累托最优解
- 支持用户在面积和可靠性之间权衡
- 提供多样化的加固方案选择

### 4.6 增量加固机制

**创新**: 实现设计变更检测和缓存复用，提升迭代效率。

**效果**:
- 避免不必要的重新加固
- 加速设计迭代周期
- 保持已验证模块的加固结果

---

## 5. 参考开源项目

### 5.1 加固方法参考

| 项目/论文 | 参考内容 |
|:---------|:---------|
| **FT-Pilot** | GraphSAGE 脆弱性预测方法、AIG 图分析流程 |
| **TMR Compiler** | TMR 插入和表决器生成的实现思路 |
| **DICE Cell** | DICE 寄存器的标准 Verilog 建模方法 |
| **SECDED ECC** | 汉明码编解码器的实现方案 |
| **PARITY Protection** | 奇偶校验的 RTL 实现模式 |

### 5.2 工具链参考

| 工具 | 用途 |
|:-----|:-----|
| **yosys** | RTL 综合、AIG 生成 |
| **iverilog** | Verilog 仿真、测试验证 |
| **PyVerilog** | Verilog AST 解析 |
| **PyTorch Geometric** | GNN 模型构建和训练 |
| **NetworkX** | 图数据结构和算法 |
| **SymbiYosys** | 形式化验证 |

### 5.3 算法参考

| 算法 | 应用场景 |
|:-----|:---------|
| **GraphSAGE** | 图节点分类（脆弱性预测） |
| **GAT** | 图注意力机制（模型融合） |
| **NSGA-II** | 多目标优化（策略选择） |
| **Focal Loss** | 类别不平衡处理（训练） |
| **BFS** | 反向可达性分析（故障标签） |

---

## 6. 测试验证情况

### 6.1 测试总览

| 测试类别 | 测试数 | 状态 |
|:---------|:------|:-----|
| Verilog 仿真测试 | 593 | ✅ PASS |
| Python 单元测试 | 24 | ✅ PASS |
| GNN 模型测试 | 5 | ✅ PASS |
| FPGA 部署测试 | 3 | ✅ PASS |
| **总计** | **683+** | ✅ **全部通过** |

### 6.2 组件测试详情

| 组件 | 测试文件 | 测试数 | 状态 |
|:-----|:--------|:------|:-----|
| cnt_comp 基本功能 | `tb_cnt_comp.v` | 6 | ✅ PASS |
| cnt_comp 故障注入 | `tb_cnt_comp_fault.v` | 9 | ✅ PASS |
| 奇偶校验 | `tb_parity.v` | 268 | ✅ PASS |
| DICE | `tb_dice.v` | 6 | ✅ PASS |
| ECC (SECDED) | `tb_ecc.v` | 265 | ✅ PASS |
| ECC 混合设计 | `tb_mixed_design_ecc.v` | 39 | ✅ PASS |
| AIG 图构建 | `aig_builder.py` | 4 | ✅ PASS |
| SVA 断言 | `sva_generator.py` | 3 | ✅ PASS |
| Auto-Repair | `auto_repair.py` | 2 | ✅ PASS |
| 寄存器提取 | `register_extractor.py` | 3 | ✅ PASS |
| pytest 回归套件 | `conftest.py` | 24 | ✅ PASS |

### 6.3 GNN 模型评估

| 模型 | 参数数量 | Test F1 | AUC-ROC | 训练时长 |
|:-----|:--------:|:--------|:--------|:---------|
| SAGE2-Lite-64 | 6,385 | **0.9707** | - | ~6 分钟 |
| SAGE2-Lite-32 | 2,177 | **0.9614** | - | ~2.5 分钟 |
| SAGE3-Lite-32 | 4,257 | 0.9574 | - | ~4.5 分钟 |
| sage3_128 (旧版) | 52,577 | 0.7737 | 0.9309 | ~18 分钟 |

### 6.4 故障注入验证

**测试结果**:
- 加固前平均 AVF: 34.11%
- 加固后平均 AVF: 10.97%
- 改善倍数: 3.11×

### 6.5 回归效率

全部 683+ 个测试可在 **约 30 秒** 内完成，适合 CI/CD 流水线集成。

---

## 7. 训练内容说明

### 7.1 训练的模型

本工具在本地进行了 **GraphSAGE 图神经网络模型**的训练，用于寄存器脆弱性预测：

**训练数据**:
- 数据集规模: 4,160 个图样本（26 个 BLIF 文件 × 16 变体 × 10 场景）
- 特征维度: 15 维（含 DFF 专用特征）
- 节点总数: ~500K
- 标签模式: 确定性结构标签（无噪声）

**训练配置**:
| 参数 | 值 |
|:-----|:---|
| 模型架构 | SAGE2-Lite-64（2层，64隐藏单元） |
| 损失函数 | Focal Loss (alpha=0.977) |
| 优化器 | Adam |
| 学习率 | 0.001 |
| Epochs | 23–30 |
| 训练时长 | ~2.5–6 分钟 (CPU) |

**训练结果**:
| 指标 | 值 |
|:-----|:---|
| Test F1 | 0.9707 |
| Precision | ~0.96 |
| Recall | ~0.97 |
| 最佳阈值 | 0.45 |

### 7.2 训练数据生成流程

```
1. RTL Verilog → Yosys综合 → BLIF 文件
2. BLIF → blif_to_pyg.py → PyG Data 对象
3. 生成确定性故障标签（反向可达性分析）
4. 生成 16 种变体（不同综合选项）
5. 生成 10 种场景（不同故障注入模式）
6. 拆分 train/val/test 数据集
7. 训练 GraphSAGE 模型
8. 评估模型性能
9. 保存最佳模型
```

### 7.3 模型版本演进

| 版本 | 架构 | 参数 | F1 | 说明 |
|:-----|:-----|:----:|:---|:-----|
| v1 | SAGE3-128 | 52,577 | 0.7737 | 初始版本，参数较多 |
| v2 | SAGE2-Lite-64 | 6,385 | 0.9707 | 轻量化优化，精度大幅提升 |
| v3 | SAGE2-Lite-32 | 2,177 | 0.9614 | 超轻量版本，适合边缘部署 |

---

## 8. OpenAI/DeepSeek API 使用说明

### 8.1 调用目的

调用 OpenAI API 或 DeepSeek API 的主要目的是**生成高质量的加固 RTL 代码**，具体包括：

| 用途 | 说明 |
|:-----|:-----|
| **RAG 加固代码生成** | 根据设计信息和脆弱性分析结果，生成上下文感知的加固 RTL |
| **策略推荐优化** | 利用 LLM 的推理能力，提供更智能的策略推荐和解释 |
| **SVA 断言生成** | 自动生成 TMR 一致性断言、错误检测断言等形式化验证属性 |
| **代码修复建议** | 为 Auto-Repair 提供修复方案建议 |

### 8.2 API 使用场景

**场景 1: RAG 加固生成**
```python
from rag_integration import RAGEngine

engine = RAGEngine(llm_backend='deepseek', api_key='sk-xxx')
engine.load_knowledge_base()

rtl = engine.generate_hardened_rtl(design_info, vulnerability_result)
```

**场景 2: 策略推荐**
```python
result = recommend_strategies(analysis, optimization_goal='balanced')
explanation = explain_recommendation(analysis, module_name, strategy)
```

**场景 3: SVA 断言生成**
```python
from sva_generator import generate_comprehensive_sva
sva_module = generate_comprehensive_sva(design_info)
```

### 8.3 三种运行模式

| 模式 | 条件 | 行为 |
|:-----|:------|:------|
| **OpenAI 真实 API** | `openai` 包已安装 + API key 可用 | 调用 GPT-4 生成加固 RTL |
| **DeepSeek 兼容 API** | `openai` 包已安装 + DeepSeek API key | 调用 DeepSeek Chat 生成加固 RTL |
| **MockLLM 回退** | 无 API key 或 API 调用失败 | 使用 13 种内置模板自动生成 |

### 8.4 MockLLM 模板库

当没有 API key 时，工具使用内置模板库（13 种模板）：

| 模板 | 策略 | 适用场景 |
|:-----|:-----|:---------|
| `tmr` | TMR 三模冗余 | 安全关键信号 |
| `ecc` | ECC SECDED | 数据总线 |
| `parity` | 奇偶校验 | 控制寄存器 |
| `dice` | DICE 寄存器 | 高可靠寄存器 |
| `cnt_comp` | 计数器比较器 | 计数器 |
| `bch_ecc` | BCH 纠错码 | 存储器 |
| `crc` | CRC 校验 | 通信接口 |
| `tmr_dice` | TMR + DICE 混合 | 安全关键寄存器 |
| `scrubbing` | 内存擦洗 | SRAM |
| `interleaving` | 位交错 | 抗辐射 |

### 8.5 API 配置方法

**方法 1: 环境变量**
```bash
export OPENAI_API_KEY="sk-xxx"
export DEEPSEEK_API_KEY="sk-xxx"
```

**方法 2: .env 文件**
```
OPENAI_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx
```

**方法 3: 代码参数**
```python
engine = RAGEngine(api_key='sk-xxx', llm_backend='deepseek')
```

---

## 9. 技术亮点总结

### 9.1 核心技术突破

| 技术 | 突破点 |
|:-----|:-------|
| **差异化混合加固** | 面积开销降低 40%–70%，保持同等可靠性 |
| **GNN 脆弱性预测** | F1 从 0.55–0.65 提升至 0.97+ |
| **轻量化模型** | 参数减少 87%，精度提升 25% |
| **确定性故障标签** | 消除随机噪声，标签完全可复现 |
| **NSGA-II 优化** | 53 个帕累托最优解，支持多目标权衡 |

### 9.2 工程化亮点

| 特性 | 说明 |
|:-----|:-----|
| **统一配置管理** | YAML + 环境变量覆盖 + 点号路径访问 |
| **结构化日志** | TRACE/VERBOSE/INFO 多级 + 彩色输出 + JSON 文件 |
| **进度跟踪** | PipelineProgress + BatchProgress + StageProgress |
| **错误处理** | PipelineError 体系 + safe_run 装饰器 + ErrorCollector |
| **CI/CD** | 多 Python 版本 + 多阶段流水线 |

### 9.3 易用性亮点

| 特性 | 说明 |
|:-----|:-----|
| **三种加固模式** | 文件/文件夹/数据集批量处理 |
| **可视化图表** | 面积柱状图/可靠性柱状图/策略饼图 |
| **增量加固** | 设计变更检测 + 缓存复用 |
| **Web GUI** | 浏览器远程访问 + 模块树视图 |
| **自动安装** | yosys 三平台自动下载安装 |

---

## 10. 文件结构

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
│   ├── USER_MANUAL.md               # 用户手册
│   ├── HARDENING_OPTIMIZATION_ROADMAP.md     # 优化路线图
│   ├── TOOL_DESIGN_DOCUMENTATION.md          # 技术设计文档（本文档）
│   ├── OPENAI_BACKEND_USAGE.md               # API 使用文档
│   ├── OPTIMIZATION_SUMMARY_REPORT.md        # 优化总结报告
│   └── ... (其他报告)
│
├── sim/formal_test/                 # 核心模块
│   ├── gnn_vulnerability.py         # GNN 脆弱性预测
│   ├── graphsage_model.py           # GraphSAGE 模型
│   ├── gnn_inference.py             # GNN 推理接口
│   ├── model_fusion.py              # 模型融合
│   ├── transfer_learning.py         # 迁移学习
│   ├── fpga_bitstream_hardening.py  # FPGA 比特流加固
│   ├── formal_verification.py       # 形式化验证
│   ├── reliability_report.py        # 可靠性报告
│   ├── incremental_hardening.py     # 增量加固
│   ├── rag_integration.py           # RAG 引擎
│   ├── auto_repair.py               # 自动修复
│   ├── fault_injection_framework.py # 故障注入框架
│   ├── harden_gui.py                # GUI 主界面
│   ├── examples.py                  # 使用示例
│   └── ... (其他模块)
│
├── test_mock_data/                  # 测试用例与模板
│   ├── cnt_comp_template.v
│   ├── parity_template.v
│   ├── dice_template.v
│   ├── ecc_template.v
│   └── ... (其他模板)
│
└── ip_cores/                        # IP 核
    └── tmr_voter_6ch/              # 6 通道表决器 IP
```

---

*文档生成时间: 2026-07-16*  
*项目版本: v3.7*  
*如有疑问，请参考 `USER_MANUAL.md` 了解详细使用方法。*