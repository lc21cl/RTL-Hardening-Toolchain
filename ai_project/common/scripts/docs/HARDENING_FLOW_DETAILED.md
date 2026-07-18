# RTL加固工具完整流程详解

## 文档版本: v2.0
## 日期: 2026-07-16
## 更新说明: 流程从5步扩展到8步，集成信号扫描、GNN预测、形式化验证等功能

---

## 一、整体流程概览

工具的加固流程分为8个核心步骤，每个步骤都有明确的输入、输出和操作逻辑：

```
┌─────────────────────────────────────────────────────────────────────┐
│                      加固流程九步法                                   │
├─────────────────────────────────────────────────────────────────────┤
│  Step 1: load_design()      → 加载RTL文件                           │
│         ↓                                                           │
│  Step 2: analyze()          → 语法解析 + 资产分类                     │
│         ↓                                                           │
│  Step 3: scan_high_fanout_signals() → 高扇出信号扫描                 │
│         ↓                                                           │
│  Step 4: run_aig_analysis() → AIG电路结构分析 (优先yosys真实综合)     │
│         ↓                                                           │
│  Step 5: predict_vulnerability() → GNN脆弱性预测                     │
│         ↓                                                           │
│  Step 6: route_strategies() → 策略选择与分配 (含冲突检测)              │
│         ↓                                                           │
│  Step 7: transform()        → AST变换 + 策略分组                      │
│         ↓                                                           │
│  Step 8: output()           → 应用模板变换 + 生成加固代码             │
│         ↓                                                           │
│  Step 9: verify()           → 形式化验证 + 编译检查 + 故障注入        │
└─────────────────────────────────────────────────────────────────────┘
```

**自动化程度说明：**
- ✅ 步骤3、4、8：**自动执行**，无需用户干预
- ✅ 步骤1、2、5、6、7：**核心流程自动执行**，用户只需配置参数
- ⚠️ 步骤5的策略配置：用户可选择"自动层次化加固"或手动选择策略

---

## 二、Step 1: load_design() — 加载RTL设计文件

### 2.1 操作流程

```python
def load_design(self, file_path: str) -> bool:
    # 1. 验证文件路径
    if not os.path.exists(file_path):
        return False
    
    # 2. 尝试用pyverilog解析AST
    try:
        import pyverilog
        self.ast, _ = pyverilog.parse.parse([file_path])
    except ImportError:
        # pyverilog不可用时，使用文件级分析
        self.ast = None
    
    # 3. 保存文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        self.design_content = f.read()
    
    self.design_file = file_path
    return True
```

### 2.2 原理机制

**AST（抽象语法树）解析：**
- 使用`pyverilog`库将RTL代码解析为结构化的AST表示
- AST是代码的结构化表示，便于后续的自动化变换
- 如果`pyverilog`不可用，降级为文件级文本分析

**输入/输出：**
| 输入 | 输出 |
|------|------|
| RTL文件路径（.v/.sv） | `self.design_file` = 文件路径 |
| | `self.ast` = AST对象或None |
| | `self.design_content` = 文件内容 |

---

## 三、Step 2: analyze() — 语法解析 + 资产类型分类

### 3.1 操作流程

```python
def analyze(self) -> Dict:
    # 1. 读取文件内容
    content = self.design_content
    
    # 2. 使用正则表达式提取所有寄存器声明
    reg_pattern = re.finditer(
        r'(?:input|output|inout)?\s*reg\s*(?:\[(\d+):(\d+)\])?\s*(\w+)\s*(?:,|;|\)|$)',
        content, re.IGNORECASE
    )
    
    # 3. 对每个寄存器进行类型分类
    for m in reg_pattern:
        name = m.group(3)
        msb = int(m.group(1)) if m.group(1) else 0
        lsb = int(m.group(2)) if m.group(2) else 0
        width = msb - lsb + 1 if m.group(1) else 1
        
        signal_type = self._classify_signal(name, content)
        self.module_info[name] = {'name': name, 'width': width, 'type': signal_type}
    
    # 4. 额外检测wire声明
    wire_pattern = re.finditer(...)
    
    # 5. 统计各类信号数量
    self.reg_count = len(self.module_info)
    self.critical_count = sum(1 for info in self.module_info.values() 
                              if info['type'] in ['fsm', 'counter', 'control'])
    
    return self.module_info
```

### 3.2 资产类型分类机制

`_classify_signal()`方法根据信号特征进行分类：

| 信号类型 | 识别特征 | 关键词/模式 |
|----------|----------|-------------|
| **FSM** | 状态寄存器 | `state`关键字 + `case`语句 |
| **Counter** | 计数器 | `count <= count + 1` 或 `cnt/timer/ticks` |
| **Control** | 控制寄存器 | `cfg/config/mode/ctrl/control/status/enable` |
| **Memory** | 存储器 | `reg name[depth]` 数组声明 |
| **Data Path** | 数据路径 | 默认类型（非上述类型） |

### 3.3 原理机制

**正则表达式模式匹配：**
- 使用复杂正则表达式提取寄存器声明，包括位宽信息
- 通过字符串匹配和上下文分析判断信号类型
- 这种方法不需要完整的AST解析，兼容性更好

**输入/输出：**
| 输入 | 输出 |
|------|------|
| `self.design_content` | `self.module_info` = 信号信息字典 |
| | `self.reg_count` = 寄存器总数 |
| | `self.critical_count` = 关键信号数 |

### 3.4 示例输出

```
[ANALYZE] 发现 8 个信号:
  - fsm:           2 个
  - counter:       1 个
  - data_path:     4 个
  - control:       1 个
```

---

## 四、Step 3: scan_high_fanout_signals() — 高扇出信号扫描 ⭐ 自动执行

### 4.1 操作流程

```python
def scan_high_fanout_signals(self, fanout_threshold: int = 10) -> Dict:
    try:
        from scan_high_fanout_signals import SignalScanner
        scanner = SignalScanner()
        results = scanner.scan(self.design_file, fanout_threshold)
    except ImportError:
        # 备用方案：简化扫描
        results = self._simple_signal_scan(fanout_threshold)
    
    self.signal_scan_results = results
    return results

def _simple_signal_scan(self, fanout_threshold: int) -> Dict:
    content = self.design_content
    signal_uses = {}
    
    for sig_name in self.module_info.keys():
        pattern = rf'\b{sig_name}\b'
        count = len(re.findall(pattern, content))
        signal_uses[sig_name] = count
    
    high_fanout = {sig: count for sig, count in signal_uses.items() 
                    if count >= fanout_threshold}
    
    return {
        'high_fanout_signals': high_fanout,
        'signal_fanout': signal_uses,
        'top_signals': sorted(signal_uses.items(), key=lambda x: x[1], reverse=True)[:10],
        'total_signals': len(signal_uses),
    }
```

### 4.2 作用和意义

**作用：**
- 识别高扇出信号（扇出>10），这些信号对故障更敏感
- 高扇出信号的单点故障会影响更多下游逻辑
- 为GNN脆弱性预测提供特征输入

**自动执行时机：**
- 在`analyze()`步骤完成后自动执行
- 结果存储在`self.signal_scan_results`中

**输入/输出：**
| 输入 | 输出 |
|------|------|
| `self.design_file` | `self.signal_scan_results` = 扫描结果字典 |
| 扇出阈值（默认10） | 高扇出信号列表、所有信号扇出值、Top 10信号 |

### 4.3 示例输出

```
[SCAN] 高扇出信号扫描完成: 2 个
  - data_out: 扇出 = 15
  - ctrl_signal: 扇出 = 12
```

---

## 五、Step 4: predict_vulnerability() — GNN脆弱性预测 ⭐ 自动执行

### 5.1 操作流程

```python
def predict_vulnerability(self) -> Dict:
    try:
        from sim.formal_test.gnn_vulnerability import VulnerabilityPredictor
        predictor = VulnerabilityPredictor()
        scores = predictor.predict(self.design_file)
    except ImportError:
        # 备用方案：启发式评分
        scores = self._heuristic_vulnerability()
    
    self.vulnerability_scores = scores
    return scores

def _heuristic_vulnerability(self) -> Dict:
    scores = {}
    type_weights = {
        'fsm': 0.9,
        'counter': 0.8,
        'control': 0.7,
        'data_path': 0.5,
        'memory': 0.6,
        'bus': 0.65,
    }
    
    for sig_name, info in self.module_info.items():
        base_score = type_weights.get(info['type'], 0.5)
        
        if self.signal_scan_results:
            fanout = self.signal_scan_results.get('signal_fanout', {}).get(sig_name, 1)
            fanout_factor = min(fanout / 10, 1.0)
            score = base_score * (0.5 + 0.5 * fanout_factor)
        else:
            score = base_score
        
        scores[sig_name] = score
    
    return scores
```

### 5.2 原理机制

**GNN预测（主方案）：**
- 使用GraphSAGE图神经网络模型
- 将RTL代码转换为电路图表示（节点=寄存器/门，边=连接关系）
- 预测每个寄存器的脆弱性评分（0-1，越高越脆弱）

**启发式评分（备用方案）：**
- 根据信号类型分配基础权重
- 结合扇出值调整评分
- 高扇出+关键类型信号得分更高

**自动执行时机：**
- 在`scan_high_fanout_signals()`步骤完成后自动执行
- 结果存储在`self.vulnerability_scores`中

**输入/输出：**
| 输入 | 输出 |
|------|------|
| `self.design_file` | `self.vulnerability_scores` = 脆弱性评分字典 |
| `self.signal_scan_results` | 每个信号的脆弱性分数（0-1） |

### 5.3 示例输出

```
[GNN] 脆弱性预测完成: 8 个寄存器
  - state_reg: 0.9523
  - ctrl_enable: 0.8765
  - counter_reg: 0.7890
```

---

## 六、Step 5: route_strategies() — 策略选择与分配

### 6.1 策略适用矩阵

工具使用策略权重矩阵决定每个信号类型适用的加固策略：

```python
STRATEGY_MATRIX = {
    'fsm':      {'tmr_state': 0.95, 'one_hot': 0.85, 'parity': 0.50, 'dice': 0.30},
    'counter':  {'cnt_comp': 0.95, 'parity': 0.70, 'tmr': 0.20, 'dice': 0.10},
    'data_path':{'tmr': 0.80, 'ecc': 0.60, 'dice': 0.40, 'parity': 0.30},
    'control':  {'parity': 0.85, 'tmr': 0.70, 'watchdog': 0.60, 'dice': 0.30},
    'memory':   {'ecc': 0.95, 'scrubbing': 0.70, 'parity': 0.30, 'tmr': 0.10},
    'bus':      {'parity': 0.90, 'ecc': 0.80, 'crc': 0.50, 'tmr': 0.10},
}
```

### 6.2 操作流程

```python
def route_strategies(self, goal=None, user_strategies=None):
    # 1. 设置优化目标
    if goal:
        self.optimization_goal = goal
    
    # 2. 遍历所有信号，为每个信号分配策略
    for sig_name, info in self.module_info.items():
        sig_type = info['type']
        
        # 从策略矩阵获取该类型适用的策略
        strategies = self.STRATEGY_MATRIX.get(sig_type, {'parity': 0.5})
        
        # 如果用户指定了策略列表，过滤策略池
        if user_strategies:
            strategies = {k: v for k, v in strategies.items() 
                          if k in user_strategies}
        
        # 根据优化目标选择最佳策略
        if self.optimization_goal == 'reliability':
            best_strategy = max(strategies, key=strategies.get)
        elif self.optimization_goal == 'area':
            best_strategy = min(strategies, key=lambda x: self._get_strategy_area_overhead(x))
        else:
            best_strategy = max(strategies, key=strategies.get)
        
        self.strategy_map[sig_name] = best_strategy
```

### 6.3 优化目标机制

| 优化目标 | 策略选择规则 | 适用场景 |
|----------|--------------|----------|
| **reliability** | 选择权重最高的策略 | 高可靠性需求，如航天、核工业 |
| **area** | 选择面积开销最小的策略 | 面积敏感场景，如ASIC |
| **balanced** | 默认选择权重最高的策略 | 平衡可靠性和面积开销 |

### 6.4 原理机制

**策略路由算法：**
1. 根据信号类型从策略矩阵中获取适用策略列表
2. 如果用户指定了策略池，过滤出用户允许的策略
3. 根据优化目标（面积/可靠性/平衡）选择最佳策略
4. 构建策略映射表 `strategy_map`

**输入/输出：**
| 输入 | 输出 |
|------|------|
| `self.module_info` | `self.strategy_map` = 信号→策略映射 |
| 优化目标 | `self.strategy_groups` = 策略→信号分组（在transform中创建） |
| 用户策略列表（可选） | |

### 6.5 示例输出

```
[ROUTE] 策略分配:
  - state_reg          (fsm       ) → TMR_state: 状态寄存器三重化 (2.5×)
  - next_state         (fsm       ) → TMR_state: 状态寄存器三重化 (2.5×)
  - counter_reg        (counter   ) → cnt_comp: 计数器比较器 (0.3×)
  - data_a             (data_path ) → Full TMR: 3 副本 + 多数表决器 (3.0×)
  - data_b             (data_path ) → Full TMR: 3 副本 + 多数表决器 (3.0×)
  - ctrl_enable        (control   ) → 奇偶校验: 奇偶位生成+检查 (0.03×)
```

---

## 七、Step 6: transform() — AST变换 + 策略分组

### 7.1 操作流程

```python
def transform(self) -> bool:
    # 1. 按策略分组信号
    strategy_groups = {}
    for sig, strategy in self.strategy_map.items():
        if strategy not in strategy_groups:
            strategy_groups[strategy] = []
        strategy_groups[strategy].append(sig)
    
    # 2. 保存策略分组
    self.strategy_groups = strategy_groups
    
    # 3. 生成替换指南
    self._generate_replacement_guide(strategy_groups)
    
    return True
```

### 7.2 替换指南生成

```python
def _generate_replacement_guide(self, strategy_groups):
    for strategy, signals in strategy_groups.items():
        for sig in signals:
            info = self.module_info[sig]
            self.replacement_guide.append({
                'signal': sig,
                'strategy': strategy,
                'width': info['width'],
                'vulnerability': self.vulnerability_scores.get(sig, 0.5),
                'action': f"添加 {strategy} 加固模块"
            })
```

### 7.3 原理机制

**策略分组：**
- 将所有信号按策略类型分组，便于批量处理
- 相同策略的信号可以共享模板代码
- 替换指南记录每个信号的变换操作，便于追溯

**输入/输出：**
| 输入 | 输出 |
|------|------|
| `self.strategy_map` | `self.strategy_groups` = 策略→信号列表 |
| | `self.replacement_guide` = 替换操作列表 |

---

## 八、Step 7: output() — 应用模板变换 + 生成加固代码

### 8.1 操作流程

```python
def output(self, output_file: str) -> bool:
    # 1. 读取原始代码
    content = self.design_content
    
    # 2. 应用加固变换
    hardened_content = self._apply_hardening_transform(content)
    
    # 3. 写入加固后代码
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(hardened_content)
    
    # 4. 生成元数据和报告
    self._write_metadata(output_file)
    self.generate_reliability_report(output_file)
    
    return True
```

### 8.2 模板变换机制

`_apply_hardening_transform()`根据策略类型调用对应的变换方法：

#### 8.2.1 TMR变换（Triple Modular Redundancy）

```python
def _apply_tmr_transform(self, content, signal, width):
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
    # 修改寄存器声明和赋值...
    return content
```

**原理：** TMR通过三重化和多数表决器实现故障屏蔽。

#### 8.2.2 奇偶校验变换

```python
def _apply_parity_transform(self, content, signal, width):
    parity_module = f"""
    module parity_{signal}(
        input [{width-1}:0] data,
        output parity_bit,
        output error_flag
    );
        assign parity_bit = ^data;
        assign error_flag = (parity_bit != ^data);
    endmodule
    """
    content += "\n\n" + parity_module
    # 修改寄存器声明...
    return content
```

**原理：** 通过添加奇偶位检测数据位的单比特错误。

#### 8.2.3 计数器比较器变换

```python
def _apply_cnt_comp_transform(self, content, signal, width):
    cnt_comp_module = f"""
    module cnt_comp_{signal}(
        input clk, input rst,
        input [{width-1}:0] d,
        output reg [{width-1}:0] q,
        output error_flag
    );
        reg [{width-1}:0] prev_q;
        assign error_flag = (q != prev_q + 1) && !rst;
        always @(posedge clk) begin
            prev_q <= q;
            q <= d;
        end
    endmodule
    """
    content += "\n\n" + cnt_comp_module
    return content
```

**原理：** 计数器的值应该是连续递增的，通过检测非法跳变来发现故障。

#### 8.2.4 TMR状态寄存器变换

```python
def _apply_tmr_state_transform(self, content, signal, width):
    # 与普通TMR类似，但额外检测FSM状态一致性
    ...
    assign fsm_error = (q1 != q2) || (q2 != q3);
```

**原理：** 状态寄存器的一致性至关重要，通过检测三个副本的状态是否一致来发现故障。

#### 8.2.5 ECC变换

```python
def _apply_ecc_transform(self, content, signal, width):
    ecc_bits = (width + 1).bit_length()
    ecc_module = f"""
    module ecc_{signal}(
        input [{width-1}:0] data_in,
        output [{width+ecc_bits-1}:0] data_out,
        ...
    );
        syndrome = encoded ^ (encoded >> 1) ^ ...;
        data_out = encoded | syndrome;
        ...
    endmodule
    """
    content += "\n\n" + ecc_module
    return content
```

**原理：** 使用SECDED（单比特纠错，双比特检测）编码。

### 8.3 模板生成原理

| 策略 | 模板结构 | 故障容错能力 | 面积开销 |
|------|----------|--------------|----------|
| **TMR** | 3个寄存器 + 多数表决器 | 容忍任意1个副本故障 | 3.0× |
| **TMR_state** | 3个状态寄存器 + 状态一致性检测 | 容忍任意1个副本故障 | 2.5× |
| **cnt_comp** | 计数器 + 比较器 | 检测非法跳变 | 1.1× |
| **parity** | 奇偶位生成器 + 错误检测 | 检测单比特错误 | 0.03× |
| **ECC** | SECDED编码器/解码器 | 纠正单比特，检测双比特 | 1.4× |
| **DICE** | 4节点交叉耦合结构 | 容忍单节点故障 | 2.5× |

### 8.4 输入/输出

| 输入 | 输出 |
|------|------|
| `self.design_content` | 加固后的RTL文件 |
| `self.strategy_groups` | 元数据JSON文件 |
| | 可靠性报告 |

---

## 九、Step 8: verify() — 形式化验证 + 编译检查 ⭐ 自动执行

### 9.1 操作流程

```python
def formal_verify(self, files):
    try:
        from sim.formal_test.formal_verification import FormalVerifier
        verifier = FormalVerifier()
        result = verifier.verify(files)
        self.verification_results = result
        return result
    except ImportError:
        return {"success": False, "error": "形式化验证模块不可用"}

def run_iverilog_check(self, file_path):
    try:
        import subprocess
        result = subprocess.run(
            ['iverilog', '-o', '/dev/null', file_path],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except:
        return False
```

### 9.2 自动执行时机

- 在`output()`步骤完成后自动执行
- 先执行形式化验证（如果可用）
- 再执行编译检查（如果iverilog可用）

### 9.3 输入/输出

| 输入 | 输出 |
|------|------|
| 加固后RTL文件路径 | `self.verification_results` = 验证结果 |
| | 编译检查结果（True/False） |

---

## 十、完整流程时序图

```
时间轴 →
        用户选择RTL文件
              ↓
        ┌─────────────────┐
Step 1  │  load_design()  │ ← 读取文件，尝试AST解析
        └────────┬────────┘
                 ↓
        ┌─────────────────┐
Step 2  │   analyze()     │ ← 正则提取寄存器，分类信号类型
        │  ┌────────────┐ │
        │  │ 提取reg声明│ │
        │  │ 提取wire声明│ │
        │  │ 分类信号类型│ │
        │  └────────────┘ │
        └────────┬────────┘
                 ↓
        ┌─────────────────┐
Step 3  │scan_high_fanout │ ← ⭐ 自动扫描高扇出信号
        │_signals()       │ │
        │  ┌────────────┐ │
        │  │ 统计扇出数 │ │
        │  │ 识别高扇出 │ │
        │  └────────────┘ │
        └────────┬────────┘
                 ↓
        ┌─────────────────┐
Step 4  │predict_vulnerab │ ← ⭐ 自动GNN脆弱性预测
        │  ility()        │ │
        │  ┌────────────┐ │
        │  │ GNN推理    │ │
        │  │ 启发式评分 │ │
        │  └────────────┘ │
        └────────┬────────┘
                 ↓
        ┌─────────────────┐
Step 5  │route_strategies()│ ← 根据信号类型分配策略
        │  ┌────────────┐ │
        │  │ 查询策略矩阵│ │
        │  │ 应用优化目标│ │
        │  │ 用户策略过滤│ │
        │  └────────────┘ │
        └────────┬────────┘
                 ↓
        ┌─────────────────┐
Step 6  │  transform()    │ ← 按策略分组，生成替换指南
        └────────┬────────┘
                 ↓
        ┌─────────────────┐
Step 7  │   output()      │ ← 应用模板变换，生成加固代码
        │  ┌────────────┐ │
        │  │ TMR变换    │ │
        │  │ parity变换 │ │
        │  │ cnt_comp   │ │
        │  │ ecc变换    │ │
        │  └────────────┘ │
        └────────┬────────┘
                 ↓
        ┌─────────────────┐
Step 8  │   verify()      │ ← ⭐ 自动形式化验证 + 编译检查
        └────────┬────────┘
                 ↓
        输出加固后RTL文件 + 元数据 + 可靠性报告 + 验证结果
```

---

## 十一、策略选择决策树

```
                    开始
                      │
                      ▼
              信号类型是什么？
         ┌───────┬───────┬───────┬───────┐
         ▼       ▼       ▼       ▼       ▼
        FSM   Counter  Data   Control  Memory
         │       │     Path    │        │
         ▼       ▼       ▼       ▼       ▼
    ┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐
    │tmr_state││cnt_comp││   tmr  ││ parity ││  ecc   │
    │ one_hot ││ parity ││  ecc   ││   tmr  ││scrubbing│
    │ parity  ││   tmr  ││  dice  ││watchdog││ parity │
    │  dice   ││  dice  ││ parity ││  dice  ││   tmr  │
    └────────┘└────────┘└────────┘└────────┘└────────┘
         │       │       │       │       │
         ▼       ▼       ▼       ▼       ▼
    根据优化目标选择最佳策略
    reliability → 选择权重最高
    area        → 选择面积最小
    balanced    → 选择权重最高
```

---

## 十二、输入输出示例

### 12.1 输入：原始RTL代码

```verilog
module counter(
    input clk,
    input rst,
    output reg [7:0] count
);
    always @(posedge clk or posedge rst) begin
        if (rst) count <= 0;
        else count <= count + 1;
    end
endmodule
```

### 12.2 分析结果

```python
module_info = {
    'count': {'name': 'count', 'width': 8, 'type': 'counter'}
}
```

### 12.3 信号扫描结果

```python
signal_scan_results = {
    'high_fanout_signals': {},
    'signal_fanout': {'count': 5},
    'top_signals': [('count', 5)],
    'total_signals': 1,
}
```

### 12.4 脆弱性预测

```python
vulnerability_scores = {'count': 0.85}
```

### 12.5 策略分配

```python
strategy_map = {'count': 'cnt_comp'}
```

### 12.6 输出：加固后代码

```verilog
module counter(
    input clk,
    input rst,
    output reg [7:0] count
);
    reg [7:0] count_cnt_d;
    reg [7:0] count_cnt_q;
    wire count_cnt_error;
    cnt_comp_count u_count_cnt(
        .clk(clk), .rst(rst), 
        .d(count_cnt_d), .q(count_cnt_q), 
        .error_flag(count_cnt_error)
    );
    
    always @(posedge clk or posedge rst) begin
        if (rst) count_cnt_d <= 0;
        else count_cnt_d <= count_cnt_q + 1;
    end
    
    always @(*) begin
        count = count_cnt_q;
    end
endmodule

module cnt_comp_count(
    input clk, input rst,
    input [7:0] d,
    output reg [7:0] q,
    output error_flag
);
    reg [7:0] prev_q;
    assign error_flag = (q != prev_q + 1) && !rst;
    
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            q <= 0;
            prev_q <= 0;
        end else begin
            prev_q <= q;
            q <= d;
        end
    end
endmodule
```

---

## 十三、总结

### 流程核心特点

1. **层次化加固**：根据信号类型分配不同级别的加固策略
2. **策略灵活性**：支持用户自定义策略池和优化目标
3. **自动化流程**：信号扫描、脆弱性预测、验证分析自动执行
4. **模板化生成**：基于预定义模板生成加固代码，保证正确性
5. **可追溯性**：生成替换指南，记录每个信号的变换操作

### 技术原理汇总

| 步骤 | 技术原理 | 关键操作 | 自动化 |
|------|----------|----------|--------|
| load_design | AST解析 | pyverilog解析RTL代码 | ✅ |
| analyze | 正则匹配 | 提取寄存器，分类信号类型 | ✅ |
| scan_high_fanout_signals | 字符串统计 | 识别高扇出信号 | ✅ |
| predict_vulnerability | GNN/启发式 | 预测寄存器脆弱性 | ✅ |
| route_strategies | 策略矩阵 + 优化算法 | 根据类型和目标分配策略 | ✅ |
| transform | 策略分组 | 按策略类型组织信号 | ✅ |
| output | 模板替换 | 正则匹配+模板插入生成加固代码 | ✅ |
| verify | 形式化验证/编译检查 | 验证加固后代码正确性 | ✅ |

---

**文档版本：** v2.0
**最后更新：** 2026-07-16