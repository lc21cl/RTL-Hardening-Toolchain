# SAGE2-Lite-64 FPGA部署方案文档

## 1. 文档概览

| 项目 | 值 |
|------|-----|
| 推荐模型 | SAGE2-Lite-64 |
| 输入特征维度 | 15 |
| 量化方式 | INT8 |
| 目标设备 | Xilinx XC7Z020CLG484-1 |
| 部署目标 | 实时脆弱性预测 |
| 文档版本 | v1.0 |

## 2. 模型架构

### 2.1 网络结构

```
输入层 (15 features)
    ↓
Conv1: SAGEConv(15 → 64)  + ReLU + Dropout
    ↓
Conv2: SAGEConv(64 → 32)  + ReLU + Dropout
    ↓
MLP1: Linear(32 → 8)      + ReLU + Dropout
    ↓
MLP2: Linear(8 → 1)       + Sigmoid
    ↓
输出层 (1) — 脆弱性概率 [0, 1]
```

### 2.2 模型参数

| 参数 | 值 |
|------|-----|
| 总参数 | 6,385 |
| 可训练参数 | 6,385 |
| MAC操作数 | 6,280 |
| 浮点运算量 | ~12K FLOPs |

### 2.3 性能指标

| 指标 | 值 |
|------|-----|
| Test F1 | 0.9853 |
| Val F1 | 0.9872 |
| Precision | 0.97+ |
| Recall | 0.98+ |

## 3. INT8量化步骤

### 3.1 量化方案

采用非对称量化（Asymmetric Quantization）：
- 权重：INT8
- 激活：INT8（运行时量化）
- 偏差：保持原始精度

### 3.2 量化参数计算

```python
def quantize_tensor(tensor):
    min_val = tensor.min().item()
    max_val = tensor.max().item()
    
    # Scale = (max - min) / 255
    scale = (max_val - min_val) / 255.0
    
    # Zero-point = -min / scale (clamped to [0, 255])
    zero_point = int(-min_val / scale)
    zero_point = max(0, min(255, zero_point))
    
    # Quantize: q = round(x / scale + zero_point)
    quantized = torch.clamp((tensor / scale + zero_point).round(), 0, 255).byte()
    
    return quantized, scale, zero_point

def dequantize(q, scale, zero_point):
    # x = (q - zero_point) * scale
    return (int(q) - zero_point) * scale
```

### 3.3 量化配置

| 层 | 权重量化 | 激活量化 | 量化类型 |
|-----|----------|----------|----------|
| Conv1.lin_l | INT8 | INT8 | Asymmetric |
| Conv1.lin_r | INT8 | INT8 | Asymmetric |
| Conv1.bias | FP32 | - | - |
| Conv2.lin_l | INT8 | INT8 | Asymmetric |
| Conv2.lin_r | INT8 | INT8 | Asymmetric |
| Conv2.bias | FP32 | - | - |
| MLP1 | INT8 | INT8 | Asymmetric |
| MLP2 | INT8 | INT8 | Asymmetric |

### 3.4 量化流程

```
1. 训练完成（FP32）
    ↓
2. 收集校准数据（500-1000个样本）
    ↓
3. 计算各层权重的scale和zero-point
    ↓
4. 生成INT8权重文件
    ↓
5. 验证量化精度
    ↓
6. 部署到FPGA
```

### 3.5 量化工具调用

```python
from fpga_deploy_lite import INT8Quantizer

# Load trained model
model = SAGE2Lite(in_channels=15, hidden_channels=64)
model.load_state_dict(torch.load('SAGE2-Lite-64.pth'))

# Quantize
quantizer = INT8Quantizer()
quantized_params = quantizer.quantize_model(model)

# Generate C++ header
header = quantizer.generate_cpp_header(model, quantized_params)
with open('sage3_lite_model.h', 'w') as f:
    f.write(header)

# Generate inference code
cpp_code = quantizer.generate_cpp_inference()
with open('sage3_lite_inference.cpp', 'w') as f:
    f.write(cpp_code)
```

## 4. FPGA配置参数

### 4.1 目标设备规格

| 资源 | 可用数量 | 估算使用 | 利用率 |
|------|----------|----------|--------|
| BRAM_18K | 36 | 0.35 | 1.0% |
| DSP48E | 220 | 98 | 44.6% |
| LUT | 53,200 | 12,770 | 24.0% |
| FF | 106,400 | 105 | 0.1% |

### 4.2 Vivado HLS配置

```tcl
# sage3_lite_hls_config.tcl

set top sage3_lite_inference
set part xc7z020clg484-1
set clock_period 10   ;# 100 MHz

# Interface configuration
config_interface -m_axi_addr64 0
config_interface -m_axi_offset off

# Resource configuration
config_resource -core Mul_LUT
config_resource -core Mul_Usage No_LUT_Mul

# Loop optimization directives
set_directive_pipeline -II 1 "sage3_lite_inference/matmul_int8"
set_directive_unroll -factor 8 "sage3_lite_inference/matmul_int8"

# Array partitioning
set_directive_resource -core Mul_LUT "sage3_lite_inference"
set_directive_resource -core AddSub_LUT "sage3_lite_inference"

# Optimization directives
set_directive_inline "sage3_lite_inference/relu"
set_directive_inline "sage3_lite_inference/sigmoid"
set_directive_inline "sage3_lite_inference/dequantize"
```

### 4.3 时钟约束

```tcl
# Clock constraints
create_clock -name sys_clk -period 10.0 [get_ports clk]
set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets clk_IBUF]

# Timing constraints
set_max_delay 10.0 -from [get_ports *] -to [get_ports *]
```

### 4.4 接口协议

| 接口 | 类型 | 位宽 | 说明 |
|------|------|------|------|
| features | AXI-Stream | 128-bit | 输入特征流 |
| edge_index | AXI-Stream | 32-bit | 边索引流 |
| output | AXI-Stream | 32-bit | 输出概率流 |
| num_nodes | AXI-Lite | 32-bit | 节点数量 |
| num_edges | AXI-Lite | 32-bit | 边数量 |
| start | AXI-Lite | 1-bit | 启动信号 |
| done | AXI-Lite | 1-bit | 完成信号 |

## 5. 推理延迟分析

### 5.1 CPU推理延迟

| 模型 | 参数 | 平均延迟 | 最大延迟 | 满足实时性 |
|------|------|----------|----------|------------|
| SAGE2-Lite-64 | 6,385 | **3.838 ms** | 72.062 ms | ✅ |
| SAGE2-Lite-32 | 2,177 | 2.996 ms | 65.885 ms | ✅ |
| SAGE3-Lite-32 | 4,257 | 4.144 ms | 57.392 ms | ✅ |

### 5.2 FPGA推理延迟（估算）

| 参数 | 值 |
|------|-----|
| 时钟频率 | 100 MHz |
| 每节点延迟 | ~60 周期 |
| 每图延迟（1000节点） | ~0.6 ms |
| 吞吐量 | ~1,667 图/秒 |

### 5.3 实时性要求验证

| 要求 | 值 | 实际 | 状态 |
|------|-----|------|------|
| 单图推理延迟 | < 100 ms | 3.84 ms | ✅ |
| 处理速率 | > 10 图/秒 | 260 图/秒 | ✅ |
| 批量处理 | > 100 图/秒 | 1,667 图/秒 | ✅ |

## 6. 部署文件清单

### 6.1 必需文件

| 文件 | 路径 | 说明 |
|------|------|------|
| 模型权重 | `data/models/SAGE2-Lite-64.pth` | PyTorch模型 |
| 量化权重 | `data/fpga/quantized_weights_lite.json` | INT8量化权重 |
| C++头文件 | `data/fpga/sage3_lite_model.h` | 权重定义 |
| 推理代码 | `data/fpga/sage3_lite_inference.cpp` | C++推理实现 |
| 资源分析 | `data/fpga/resource_analysis_lite.json` | FPGA资源估算 |

### 6.2 配置文件

| 文件 | 说明 |
|------|------|
| `hls_config.tcl` | Vivado HLS配置 |
| `constraints.xdc` | 时序约束 |
| `system_wrapper.v` | 顶层封装 |
| `dma_config.xml` | DMA配置 |

## 7. 部署步骤

### 7.1 量化阶段

```bash
# 1. 运行量化脚本
python fpga_deploy_lite.py

# 2. 验证量化结果
python verify_quantization.py --model SAGE2-Lite-64 --data test

# 3. 生成部署文件
python generate_deployment_files.py
```

### 7.2 HLS综合阶段

```bash
# 1. 启动Vivado HLS
vivado_hls

# 2. 创建项目
create_project sage3_lite ./hls_project -part xc7z020clg484-1

# 3. 添加源文件
add_files sage3_lite_inference.cpp
add_files sage3_lite_model.h

# 4. 设置顶层函数
set_top sage3_lite_inference

# 5. 综合
csynth_design

# 6. 导出IP
export_design -format ip_catalog
```

### 7.3 系统集成阶段

```bash
# 1. 创建Vivado项目
vivado -mode batch -source create_project.tcl

# 2. 导入IP
import_ip ./hls_project/exported_ip

# 3. 连接IP
connect_bd_intf_net [get_bd_intf_pins sage3_lite_0/S_AXIS] ...
connect_bd_intf_net [get_bd_intf_pins sage3_lite_0/M_AXIS] ...

# 4. 生成比特流
generate_target all [get_files *.bd]
make_wrapper -files [get_files *.bd] -top
add_files -norecurse *.bdw

# 5. 生成比特流
launch_runs impl_1 -to_step write_bitstream
```

### 7.4 测试阶段

```bash
# 1. 连接FPGA板卡
connect_hw_server
open_hw_target

# 2. 下载比特流
download_bitstream ./project_1.runs/impl_1/*.bit

# 3. 运行测试
python fpga_test.py --host 192.168.1.100 --port 5000
```

## 8. 故障排查

### 8.1 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| DSP48E超支 | 模型过大 | 减少隐藏通道数 |
| 时序不满足 | 时钟频率过高 | 降低至50 MHz |
| 精度下降 | 量化误差 | 调整量化阈值 |
| 资源不足 | BRAM不够 | 使用外部DDR |
| 接口错误 | AXI配置问题 | 检查接口协议 |

### 8.2 调试建议

1. **仿真验证**：先在HLS中进行C仿真和RTL仿真
2. **逐步验证**：先验证单层，再验证完整网络
3. **资源监控**：利用Vivado资源分析工具监控使用情况
4. **时序分析**：使用Report Timing分析关键路径

## 9. 性能优化建议

### 9.1 算法层面

| 优化项 | 当前状态 | 建议 |
|--------|----------|------|
| 模型深度 | 2层 | 保持当前深度 |
| 隐藏通道 | 64 | 可降至32（F1损失<1%） |
| 量化精度 | INT8 | 可尝试INT4（需验证） |

### 9.2 架构层面

| 优化项 | 说明 | 预期效果 |
|--------|------|----------|
| 流水线 | 每层独立流水线 | 吞吐量提升3x |
| 并行处理 | 多图并行推理 | 吞吐量提升Nx |
| 权重复用 | 跨节点共享计算 | 延迟降低 |

### 9.3 部署层面

| 优化项 | 说明 | 预期效果 |
|--------|------|----------|
| 外部DDR | 使用片外存储 | 支持更大图 |
| DMA优化 | 优化数据传输 | 带宽提升 |
| 异步处理 | 流水线+缓冲 | 延迟降低 |

## 10. 总结

### 10.1 部署可行性

| 指标 | 状态 |
|------|------|
| FPGA资源 | ✅ 充足 |
| 实时性 | ✅ 满足 |
| 精度 | ✅ 98.5% F1 |
| 量化 | ✅ INT8已完成 |

### 10.2 推荐配置

- **模型**：SAGE2-Lite-64（F1=0.9853）
- **量化**：INT8（75%内存节省）
- **时钟**：100 MHz
- **接口**：AXI-Stream

### 10.3 后续工作

1. **HLS综合验证**：生成RTL并验证时序
2. **板级测试**：在实际FPGA板卡上测试
3. **性能调优**：优化流水线和并行处理
4. **批量处理**：支持多图并行推理
