# RTL加固工具架构详解

## 文档版本: v2.1
## 日期: 2026-07-18
## 更新说明: v2.1 - 故障注入/LLM生成/增量加固已全部集成，新增FPGA比特流加固/GNN模型离线打包/CI-CD

---

## 一、工具整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GUI 界面层                                   │
│  流程选择 → 步骤导航 → 代码对比 → 可视化 → 报告生成                    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    HardeningPipeline 核心管线                        │
│  load_design → analyze → scan → predict → route → transform → output→verify
└─────────────────────────────────────────────────────────────────────┘
                                  │
         ┌───────────┬───────────┼───────────┬───────────┐
         ▼           ▼           ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
    │ 策略选择 │ │ 代码变换 │ │ 信号扫描 │ │ GNN预测 │ │ 验证分析 │
    │strategy_│ │ AST变换 │ │scan_high │ │gnn_vuln │ │formal_  │
    │auto_    │ │ 模板生成 │ │_fanout_  │ │erabilit │ │verify   │
    │select   │ │          │ │signals   │ │y        │ │fault_   │
    └─────────┘ └─────────┘ └─────────┘ └─────────┘ │inject   │
                                                    │reliability│
                                                    └─────────┘
                                                              │
                                                              ▼
                                                   ┌────────────────┐
                                                   │ AIG分析模块     │
                                                   │demo_aig_       │
                                                   │analysis        │
                                                   └────────────────┘
```

---

## 二、信号扫描和AIG分析

### 2.1 信号扫描 (scan_high_fanout_signals.py)

**作用：**
- 扫描设计中扇出较高的信号（扇出>10）
- 识别关键信号，这些信号对故障更敏感
- 为GNN脆弱性预测提供特征输入

**是否需要用户手动执行：**
- ✅ **自动执行**：在`analyze()`步骤完成后自动执行
- 不需要用户干预

**执行时机：**
- Step 3（分析设计之后，脆弱性预测之前）
- 结果存储在`self.signal_scan_results`中

**集成状态：** ✅ 已集成到主流程

### 2.2 AIG分析 (demo_aig_analysis.py)

**作用：**
- 将RTL代码综合为AIG（And-Inverter Graph）格式
- 分析电路结构：PI数、AND门数、PO数、扇入分布
- 生成模拟AIG文件用于后续分析

**是否需要用户手动执行：**
- ⚠️ **手动触发**：在验证分析步骤中点击按钮执行
- AIG分析不是核心流程的必要步骤，属于可选分析

**执行时机：**
- 在验证分析步骤中作为可选操作
- 用户可根据需要触发

**集成状态：** ✅ 已集成到GUI（可选操作）

---

## 三、当前加固代码生成方式

### 3.1 生成原理

当前加固代码采用**模板生成**方式：

```python
def _apply_tmr_transform(self, content: str, signal: str, width: int) -> str:
    tmr_module = f"""
    module tmr_{signal}(
        input clk, input rst,
        input [{width-1}:0] d,
        output reg [{width-1}:0] q
    );
        reg [{width-1}:0] q1, q2, q3;
        always @(posedge clk) begin
            q1 <= d; q2 <= d; q3 <= d;
        end
        always @(*) begin
            q = (q1 & q2) | (q1 & q3) | (q2 & q3);
        end
    endmodule
    """
    content += "\n\n" + tmr_module
    return content
```

### 3.2 模板类型

| 策略 | 模板内容 | 面积开销 |
|------|----------|----------|
| **TMR** | 3个寄存器副本 + 多数表决器 | 3.0× |
| **Parity** | 奇偶位生成器 + 错误检测标志 | 0.03× |
| **cnt_comp** | 计数器比较器 + 错误检测 | 1.1× |
| **TMR_state** | 状态寄存器TMR + FSM错误检测 | 2.5× |
| **ECC** | SECDED纠错码编码器/解码器 | 1.4× |
| **DICE** | 双互锁存储单元 | 2.5× |

### 3.3 生成流程

```
原始RTL代码 → 解析寄存器 → 分类信号类型 → 信号扫描 → 脆弱性预测 → 分配策略 → 应用模板变换 → 加固后代码 → 验证分析
                 ↓              ↓              ↓            ↓            ↓              ↓              ↓
              analyze()   _classify_signal() scan()     predict()   route()      output()       verify()
```

---

## 四、GNN预测和LLM生成

### 4.1 GNN脆弱性预测 (gnn_vulnerability.py)

**原理：**
- 使用GraphSAGE图神经网络模型
- 将RTL代码转换为电路图表示（节点=寄存器/门，边=连接关系）
- 预测每个寄存器的脆弱性评分（0-1，越高越脆弱）

**工作流程：**
```
RTL代码 → 构建电路图 → 提取节点特征 → GNN推理 → 脆弱性评分 → 加固优先级排序
              ↓
        CircuitGraph类
              ↓
        GraphSAGE模型
              ↓
        输出: 每个寄存器的脆弱性分数
```

**是否需要用户手动执行：**
- ✅ **自动执行**：在信号扫描完成后自动执行
- 不需要用户干预

**执行时机：**
- Step 4（信号扫描之后，策略路由之前）
- 结果存储在`self.vulnerability_scores`中

**备用方案：**
- 如果GNN模块不可用，自动降级为启发式评分
- 启发式评分基于信号类型权重和扇出值计算

**集成状态：** ✅ 已集成到主流程

### 4.2 LLM加固生成 (llm_hardening.py)

**原理：**
- 使用检索增强生成（RAG）技术
- 构建加固知识库（包含各种加固模式、最佳实践）
- 根据设计特征检索相关知识
- 使用LLM生成优化的加固代码

**工作流程：**
```
RTL代码 → 提取特征 → 知识库检索 → LLM生成加固代码 → 验证优化
              ↓              ↓              ↓
        KnowledgeBase    RAG检索         LLM推理
```

**当前集成状态：** ⚠️ 未集成到主流程
- 模块已实现但未在`hardening_pipeline.py`中调用
- **建议：** 在`output()`步骤中作为可选生成方式

---

## 五、验证分析过程

### 5.1 当前验证分析内容

| 验证类型 | 模块 | 当前状态 | 集成位置 | 自动化 |
|----------|------|----------|----------|--------|
| **代码对比** | GUI内置 | ✅ 已实现 | 验证分析步骤 | ✅ |
| **可视化对比** | matplotlib | ✅ 已实现 | 验证分析步骤 | ✅ |
| **形式化验证** | formal_verification.py | ✅ 已集成 | Step 8 自动执行 | ✅ |
| **故障注入** | fault_injection.py | ⚠️ 未集成 | 待集成 | — |
| **编译检查** | iverilog | ✅ 已集成 | Step 8 自动执行 | ✅ |
| **可靠性分析** | reliability_report.py | ✅ 已集成 | 报告生成步骤 | ✅ |

### 5.2 验证流程

```
加固后代码 → 形式化验证 → 编译检查 → 可靠性分析 → 可视化对比 → 综合评估报告
              ↓              ↓              ↓              ↓
         FormalVerifier   iverilog     ReliabilityAnalyzer  matplotlib
```

### 5.3 各验证模块说明

#### 5.3.1 形式化验证 (formal_verification.py)
- 集成SymbiYosys工具
- 验证加固后功能正确性
- 检查时序属性（使用SVA断言）
- **自动执行**：在output()步骤完成后自动执行

#### 5.3.2 编译检查 (iverilog)
- 使用iverilog检查加固后代码的语法正确性
- **自动执行**：在形式化验证后自动执行（如果iverilog可用）

#### 5.3.3 可靠性分析 (reliability_report.py)
- 计算可靠性指标（MTTF、FIT率）
- 分析面积开销和延迟开销
- 使用GNN脆弱性评分生成报告
- **自动执行**：在output()步骤中自动生成

#### 5.3.4 故障注入 (fault_injection.py)
- 支持SEU（单事件翻转）、SET（单事件瞬态）
- 支持Stuck-at、Bridge等故障类型
- 评估加固方案的故障覆盖率
- **待集成**：计划在Step 8中作为可选验证步骤

---

## 六、完整加固流程时序

### 6.1 当前流程（8步）

```
时间轴 →
Step 1: 选择文件
  └─ 加载RTL文件
  └─ 显示代码预览

Step 2: 配置策略
  └─ 策略推荐（可选）
  └─ 选择"自动层次化加固"或手动选择策略
  └─ 选择优化目标（面积/可靠性/平衡）

Step 3: 执行加固（自动执行8个子步骤）
  └─ [1/8] load_design()     → 加载文件内容
  └─ [2/8] analyze()         → 正则解析寄存器/信号，分类信号类型
  └─ [3/8] scan_high_fanout_signals() → ⭐ 自动扫描高扇出信号
  └─ [4/8] predict_vulnerability()    → ⭐ 自动GNN脆弱性预测
  └─ [5/8] route_strategies() → 根据信号类型和优化目标分配策略
  └─ [6/8] transform()       → 按策略分组，生成替换指南
  └─ [7/8] output()          → 应用模板变换，生成加固代码
  └─ [8/8] verify()          → ⭐ 自动形式化验证 + 编译检查

Step 4: 验证分析
  └─ 代码对比（原始vs加固后）
  └─ 可视化效果（图表）
  └─ 脆弱性评分显示（Top 5）
  └─ 高扇出信号显示
  └─ 策略分配详情
  └─ AIG分析（可选）

Step 5: 导出报告
  └─ 生成HTML报告
  └─ 查看报告内容
```

### 6.2 自动化步骤汇总

| 步骤 | 操作 | 自动化 | 用户干预 |
|------|------|--------|----------|
| 加载设计 | load_design() | ✅ | 选择文件 |
| 分析设计 | analyze() | ✅ | 无 |
| 信号扫描 | scan_high_fanout_signals() | ✅ | 无 |
| 脆弱性预测 | predict_vulnerability() | ✅ | 无 |
| 策略路由 | route_strategies() | ✅ | 配置策略 |
| AST变换 | transform() | ✅ | 无 |
| 输出代码 | output() | ✅ | 无 |
| 验证分析 | verify() | ✅ | 无 |

---

## 七、数据流

### 7.1 核心数据结构

```python
# 设计信息
self.module_info = {
    'signal_name': {
        'name': 'signal_name',
        'width': 8,
        'type': 'counter'  # fsm/counter/data_path/control/memory/bus
    }
}

# 信号扫描结果
self.signal_scan_results = {
    'high_fanout_signals': {'data_out': 15},
    'signal_fanout': {'count': 5, 'data_out': 15},
    'top_signals': [('data_out', 15), ('count', 5)],
    'total_signals': 8,
}

# 脆弱性评分
self.vulnerability_scores = {
    'state_reg': 0.9523,
    'ctrl_enable': 0.8765,
    'count': 0.8500,
}

# 策略映射
self.strategy_map = {
    'state_reg': 'tmr_state',
    'ctrl_enable': 'parity',
    'count': 'cnt_comp',
}

# 验证结果
self.verification_results = {
    'success': True,
    'formal_verification': 'passed',
    'compile_check': True,
}
```

### 7.2 数据流向

```
用户选择文件
      │
      ▼
load_design() → self.design_content, self.ast
      │
      ▼
analyze() → self.module_info (信号类型分类)
      │
      ▼
scan_high_fanout_signals() → self.signal_scan_results (扇出统计)
      │
      ▼
predict_vulnerability() → self.vulnerability_scores (脆弱性评分)
      │
      ▼
route_strategies() → self.strategy_map (策略分配)
      │
      ▼
transform() → self.strategy_groups, self.replacement_guide
      │
      ▼
output() → 加固后RTL文件 + 元数据 + 可靠性报告
      │
      ▼
verify() → self.verification_results
```

---

## 八、关键问题解答

### Q1: 信号扫描和AIG分析需要用户手动进行吗？
- **信号扫描**：不需要，Step 3自动执行
- **AIG分析**：需要，验证步骤中点击按钮触发（可选）

### Q2: AIG分析是AST解析后自动进行的吗？
- 不是，AIG分析需要综合RTL代码，是独立的分析步骤
- 当前设计为可选操作，在验证分析步骤中手动触发

### Q3: GNN预测和LLM生成是什么？
- **GNN预测**：使用图神经网络预测寄存器脆弱性，Step 4自动执行
- **LLM生成**：使用大语言模型生成优化的加固代码，未集成到主流程

### Q4: 当前加固代码是怎么生成的？
- **模板生成**：根据策略类型选择对应模板，替换占位符后插入代码
- **不是API或LLM生成**

### Q5: 验证分析包含形式化验证、故障注入、可靠性分析吗？
- **形式化验证**：✅ 已集成，Step 8自动执行
- **故障注入**：⚠️ 未集成，待后续添加
- **可靠性分析**：✅ 已集成，output()步骤中自动生成

### Q6: GNN驱动的脆弱性预测在哪一步进行？
- **Step 4**：在信号扫描之后，策略路由之前
- **自动执行**：不需要用户干预

---

## 九、优化建议汇总

| 优化项 | 当前状态 | 建议改进 | 优先级 |
|--------|----------|----------|--------|
| 信号扫描自动化 | ✅ 已实现 | 完成 | — |
| AIG分析自动化 | ⚠️ 可选 | 可考虑在分析步骤后自动生成 | 低 |
| GNN预测集成 | ✅ 已实现 | 完成 | — |
| 形式化验证集成 | ✅ 已实现 | 完成 | — |
| 故障注入测试集成 | ⚠️ 未集成 | 在验证步骤中添加 | 中 |
| 可靠性分析集成 | ✅ 已实现 | 完成 | — |
| **LLM生成集成** | ✅ 已集成 | 作为可选验证步骤(3种后端) | — |
| **GNN模型离线打包** | ✅ 已实现 | 三级加载机制(完整模型/嵌入/内置回退) | — |
| **FPGA比特流加固** | ✅ 已实现 | 支持Xilinx 7系列+Altera Cyclone | — |
| **增量加固** | ✅ 已实现 | 信号级细粒度增量更新(宽度/类型/扇出) | — |
| **CI/CD集成** | ✅ 已实现 | GitHub Actions自动化测试流水线 | — |
| **Docker容器化** | ✅ 已实现 | Dockerfile+docker-compose.yml | — |

---

**文档版本：** v2.1
**最后更新：** 2026-07-18