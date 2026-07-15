# tmr_voter_6ch — Vivado IP 集成指南

## 1. 概述

本指南说明如何将 `tmr_voter_6ch` IP 核集成到 Xilinx Vivado 设计流程中，包括 IP Integrator 集成、手动 HDL 实例化、时序约束集成和设计注意事项。

## 2. 目录结构

```
tmr_voter_6ch/
├── src/
│   └── tmr_voter_6ch_xilinx.v       # 核心 RTL (LUT3 原语 + tmr_voter_6ch_xilinx 模块)
├── ip/
│   ├── component.xml                 # IP-XACT 元数据
│   └── tmr_voter_6ch.xci            # Vivado IP 配置文件
├── constraints/
│   └── tmr_voter_6ch_timing.xdc     # IP 级时序约束
├── sim/
│   └── tb_tmr_voter_6ch_ip.sv       # IP 测试台
├── docs/
│   ├── DATASHEET.md                  # IP 数据手册
│   └── INTEGRATION_GUIDE.md          # 本文件
└── scripts/
    ├── package_ip.tcl                # IP 打包脚本
    └── synth_ip.tcl                  # 独立综合脚本
```

## 3. Vivado IP Integrator 集成

### 3.1 将 IP 添加到 IP 仓库

1. 打开 Vivado 并创建或打开一个工程。
2. 在 Tcl 控制台中运行:
   ```tcl
   set_property ip_repo_paths [list <path_to>/tmr_voter_6ch] [current_project]
   update_ip_catalog
   ```
   或者通过 GUI: **Tools > Settings > IP > Repository > Add**，选择 `tmr_voter_6ch/` 目录。
3. IP 核将出现在 IP Catalog 中，位于 **user.org > tmr > tmr_voter_6ch**。

### 3.2 在 Block Design 中实例化

1. 打开或创建一个 Block Design。
2. 右键点击画布，选择 **Add IP**，搜索 `tmr_voter_6ch`。
3. 双击添加 IP 核。
4. 连接端口:
   - `clk` → 系统时钟 (如 10 MHz)
   - `rst_n` → 系统复位 (低有效)
   - `core1_ready/2/3` → 三个 CPU 核心的 mmio_in.ready
   - `voted_ready` → 下游模块的 mmio_in.ready
   - 其他通道类似连接。

### 3.3 IP 打包 (从源码重建)

如果需要对 IP 进行修改，运行打包脚本:

```tcl
cd <tmr_voter_6ch>/scripts
vivado -source package_ip.tcl -mode batch
```

这将从 RTL 源码重新生成 `ip/` 目录下的 IP-XACT 和 XCI 文件。

## 4. 手动 HDL 实例化

### 4.1 Verilog 实例化示例

```verilog
// 实例化 tmr_voter_6ch_xilinx
tmr_voter_6ch_xilinx u_tmr_voter (
    .clk                (sys_clk),
    .rst_n              (sys_rst_n),

    // ch-0: mmio_in.ready
    .core1_ready        (cpu0_mmio_in_ready),
    .core2_ready        (cpu1_mmio_in_ready),
    .core3_ready        (cpu2_mmio_in_ready),
    .voted_ready        (voted_mmio_in_ready),

    // ch-1: boot_valid
    .core1_boot_valid   (cpu0_boot_valid),
    .core2_boot_valid   (cpu1_boot_valid),
    .core3_boot_valid   (cpu2_boot_valid),
    .voted_boot_valid   (voted_boot_valid),

    // ch-2: exit_valid
    .core1_exit_valid   (cpu0_exit_valid),
    .core2_exit_valid   (cpu1_exit_valid),
    .core3_exit_valid   (cpu2_exit_valid),
    .voted_exit_valid   (voted_exit_valid),

    // ch-3: exit_code (8-bit)
    .core1_exit_code    (cpu0_exit_code),
    .core2_exit_code    (cpu1_exit_code),
    .core3_exit_code    (cpu2_exit_code),
    .voted_exit_code    (voted_exit_code),

    // ch-4: print_valid
    .core1_print_valid  (cpu0_print_valid),
    .core2_print_valid  (cpu1_print_valid),
    .core3_print_valid  (cpu2_print_valid),
    .voted_print_valid  (voted_print_valid),

    // ch-5: print_data (32-bit)
    .core1_print_data   (cpu0_print_data),
    .core2_print_data   (cpu1_print_data),
    .core3_print_data   (cpu2_print_data),
    .voted_print_data   (voted_print_data)
);
```

### 4.2 SystemVerilog 实例化

与上述 Verilog 实例化语法兼容。在 SystemVerilog 环境中也可以使用 `.name` 和 `.*` 连接方式。

## 5. 参数说明

| 参数   | 类型       | 默认值 | 描述                        |
|:------|:----------|:------:|:---------------------------|
| INIT  | 8-bit hex | 8'hE8  | LUT3 初始化值 (Majority-3)  |

**注意:** 在标准使用中无需修改 INIT 参数。如果修改，表决函数将改变。

## 6. 时序约束集成

### 6.1 自动集成 (IP Integrator)

当通过 IP Integrator 使用 IP 时，`constraints/tmr_voter_6ch_timing.xdc` 中的约束会自动被 Vivado 识别和应用。

### 6.2 手动集成

如果在 RTL 中直接实例化，需要在工程的 XDC 文件中添加以下内容:

```tcl
# 添加 IP 约束文件
read_xdc <path_to>/tmr_voter_6ch/constraints/tmr_voter_6ch_timing.xdc
```

或者直接将约束内容复制到主约束文件中。

### 6.3 约束文件内容摘要

- **时钟:** 10 MHz (周期 100 ns)
- **输入延迟:** 最大 2.0 ns，最小 0.5 ns
- **输出延迟:** 最大 3.0 ns，最小 0.5 ns
- **组合路径最大延迟:** 2.0 ns (输入到输出)
- **时钟不确定性:** setup 0.5 ns, hold 0.3 ns

## 7. 仿真

### 7.1 使用 iverilog

```bash
cd <tmr_voter_6ch>/sim
iverilog -g2012 -o tb_ip tb_tmr_voter_6ch_ip.sv ../src/tmr_voter_6ch_xilinx.v
vvp tb_ip
```

### 7.2 使用 Vivado Simulator

```tcl
cd <tmr_voter_6ch>/sim
xvlog -sv tb_tmr_voter_6ch_ip.sv ../src/tmr_voter_6ch_xilinx.v
xelab tb_tmr_voter_6ch_ip -s tb_ip
xsim tb_ip
```

### 7.3 仿真结果解读

测试台执行 10,000 次随机测试，输出如下:

```
TMR 6-Channel Voter IP Testbench
  Module: tmr_voter_6ch_xilinx
  Tests:  10000 random vectors
============================================================
PASS: ch-0 (mmio_in.ready) | c1=0 c2=1 c3=1 | voted=1 expected=1
...
============================================================
SIMULATION SUMMARY
============================================================
  Total tests: 460000
  Passed:      460000
  Failed:      0
  Test vectors: 10000 (target: >= 1000)
------------------------------------------------------------
  RESULT: ALL TESTS PASSED
============================================================
```

每次随机测试产生 46 个逐位检查 (4 × 1-bit + 8 × 1-bit + 32 × 1-bit = 46)。

## 8. 设计考虑

### 8.1 时钟域

该 IP 是纯组合逻辑，不包含任何寄存器或时钟域交叉。`clk` 和 `rst_n` 端口仅作为系统连接接口提供，模块内部未使用。

### 8.2 复位策略

由于 IP 不包含寄存器，复位信号不影响内部逻辑。但建议将 `rst_n` 连接到系统复位，以便保持一致的设计层次结构。

### 8.3 扇出考虑

- 每个 core* 输入端口驱动一个或多个 LUT3 输入
- 对于 1-bit 通道: 扇出为 1
- 对于 8-bit exit_code: 每个 core*_exit_code 位扇出到 1 个 LUT3
- 对于 32-bit print_data: 每个 core*_print_data 位扇出到 1 个 LUT3
- 所有扇出均在器件的能力范围内

### 8.4 资源占用

总计 44 个 LUT3，零 FF。适合在资源受限的器件中使用。

### 8.5 性能

- 2 级组合逻辑深度
- 每级 LUT3 延迟 ~0.5 ns
- 输入到输出最大延迟 ~2 ns (含布线)
- 可轻松满足 10 MHz 设计，也可用于更高频率

## 9. 综合脚本

单独综合 IP 核:

```tcl
cd <tmr_voter_6ch>/scripts
vivado -source synth_ip.tcl -mode batch
```

## 10. 常见问题

### Q: 为什么 clk 和 rst_n 不连接内部逻辑?
A: 模块是纯组合逻辑，不需要时钟或复位。这些端口是为了在 Vivado IP Integrator 中正确连接总线接口而保留的。

### Q: 如何验证 IP 功能?
A: 使用提供的仿真测试台 (见第 7 节) 进行 10,000 次随机向量测试。

### Q: 能否用于非 Xilinx 器件?
A: 本 IP 专门使用 Xilinx LUT3 原语。对于非 Xilinx 器件，请使用等效的布尔表达式实现 (`tmr_voter_6ch` RTL 版本)。

### Q: 如何修改表决函数?
A: 修改 `LUT3 #(.INIT(8'hE8))` 中的 INIT 参数。例如，使用 INIT=8'h80 实现 AND-3 函数。

---

## 附录 C: Pipeline 寄存器版本集成

本 IP 核 v1.1 版本在输出端添加了可选的 pipeline 寄存器 (PIPELINE_ENABLE=1), 提供以下改进:
- 时序裕量从 49 ns 提升至 97 ns (时钟周期 100 ns @ 10 MHz)
- 消除所有组合逻辑毛刺 (寄存器采样)
- 增加 1 个时钟周期延迟 (纯组合变为寄存输出)

### C.1 参数配置

| 参数名 | 默认值 | 说明 |
|:-------|:------:|:------|
| PIPELINE_ENABLE | 1 | 0=直通模式, 1=寄存器模式 |

实例化示例:
```verilog
tmr_voter_6ch_pipeline #(
    .PIPELINE_ENABLE(1)
) u_voter (
    .clk(clk), .rst_n(rst_n),
    .core1_ready(...), ...
);
```

### C.2 时序约束更新

使用 `ch5_print_data_timing_pipeline.xdc` 替换原 XDC:
```
旧: set_max_delay -from core1_print_data -to mmio_out_print_data 30.0
新: 寄存器输出, 自动约束为 clk 周期 - FF setup
预期 slack: ~97 ns
```

---

## 第七章: UVM 寄存器模型与毛刺注入验证

### 7.1 寄存器模型更新

Pipeline 版本新增以下寄存器映射:
```
偏移 0x40: PIPELINE_CTRL — [0] PIPELINE_ENABLE (RW)
偏移 0x44: PIPELINE_LATENCY — [7:0] 延迟周期数 (RO, 固定=1)
```

在 `tmr_voter_ral_model.sv` 中添加:
```systemverilog
class reg_pipeline_ctrl extends uvm_reg;
    rand uvm_reg_field pipeline_enable;
    `uvm_object_utils(reg_pipeline_ctrl)
    
    function new(string name = "reg_pipeline_ctrl");
        super.new(name, 32, UVM_NO_COVERAGE);
    endfunction
    
    virtual function void build();
        pipeline_enable = uvm_reg_field::type_id::create("pipeline_enable");
        pipeline_enable.configure(this, 1, 0, "RW", 1, 1, 1, 1, 0);
    endfunction
endclass
```

### 7.2 毛刺注入验证场景

毛刺注入测试序列 `glitch_injection_sequence` 验证 pipeline 寄存器的毛刺抑制能力:

```systemverilog
class glitch_injection_sequence extends uvm_sequence #(tmr_voter_seq_item);
    `uvm_object_utils(glitch_injection_sequence)
    
    virtual task body();
        tmr_voter_seq_item req;
        
        `uvm_info("GLITCH_SEQ", "开始毛刺注入测试", UVM_LOW)
        
        // 场景 1: 单比特毛刺 (ch-0 ready)
        // 在同一个时钟周期内, 让 core1_ready 跳变 2 次
        // 无 pipeline: 输出出现毛刺
        // 有 pipeline: 输出稳定
        req = tmr_voter_seq_item::type_id::create("req");
        req.ch_idx = 0; req.width = 1;
        req.core1_val = 0; req.core2_val = 1; req.core3_val = 1;
        start_item(req); finish_item(req);
        
        // 场景 2: 多比特毛刺 (ch-5 print_data)
        // 一个周期内, 32-bit 信号中某些 bit 抢先跳变
        // 检查 pipeline 输出是否只有干净波形
        for (int i = 0; i < 100; i++) begin
            req = tmr_voter_seq_item::type_id::create("req");
            req.ch_idx = 5; req.width = 32;
            req.core1_val = $urandom;
            req.core2_val = $urandom;
            req.core3_val = $urandom;
            req.pipeline_delay = 1;  // 期望 1 周期延迟
            start_item(req); finish_item(req);
        end
        
        // 场景 3: 时钟边沿附近的输入变化 (建立/保持时间违规模拟)
        // 在时钟上升沿前 1ps 改变输入
        // 验证 pipeline 寄存器正确采样
        
        `uvm_info("GLITCH_SEQ", "毛刺注入完成", UVM_LOW)
    endtask
endclass
```

### 7.3 记分板更新 (pipeline 延迟补偿)

```systemverilog
class tmr_voter_scoreboard_pipeline extends tmr_voter_scoreboard;
    `uvm_object_utils(tmr_voter_scoreboard_pipeline)
    
    // 增加延迟队列补偿 pipeline 的 1 周期延迟
    int expected_q[$];
    
    virtual function void check_voter(tmr_voter_seq_item item);
        if (item.pipeline_delay > 0) begin
            // 存入延迟队列
            expected_q.push_back(item.expected_voted);
        end else begin
            // 从队列中取出并比较
            int expected = expected_q.pop_front();
            if (item.voted_output !== expected) begin
                `uvm_error("SCOREBOARD", 
                    $sformatf("Pipeline mismatch: got=%h expected=%h", 
                              item.voted_output, expected))
            end
        end
    endfunction
endclass
```

### 7.4 回归测试更新

在 `run_uvm_regression.tcl` 的 `TEST_LIST` 中添加:
```tcl
{glitch_injection_test   "Glitch Injection Test (Pipeline Verification)"}
```

新增回归测试命令:
```bash
# 运行毛刺注入回归
make -f Makefile.questa single_test TEST_NAME=glitch_injection_test
```

### 7.5 覆盖率收集

添加以下覆盖点:
```systemverilog
covergroup glitch_coverage @(posedge clk);
    // 毛刺检测: 组合输出 vs 寄存器输出比较
    glitch_detected: coverpoint (combo_out !== reg_out);
    
    // 单比特通道毛刺
    ch0_glitch: coverpoint (voted_ready_combo !== voted_ready_reg);
    ch1_glitch: coverpoint (voted_boot_valid_combo !== voted_boot_valid_reg);
    ch2_glitch: coverpoint (voted_exit_valid_combo !== voted_exit_valid_reg);
    ch4_glitch: coverpoint (voted_print_valid_combo !== voted_print_valid_reg);
    
    // 多比特通道毛刺
    ch3_glitch_bits: coverpoint ($countones(voted_exit_code_combo ^ voted_exit_code_reg));
    ch5_glitch_bits: coverpoint ($countones(voted_print_data_combo ^ voted_print_data_reg));
    
    // 交叉覆盖
    cross_glitch: cross ch0_glitch, ch1_glitch, ch2_glitch, ch4_glitch;
endgroup
```
