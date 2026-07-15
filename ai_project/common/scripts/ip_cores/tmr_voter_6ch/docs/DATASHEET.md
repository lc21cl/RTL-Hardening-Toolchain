# tmr_voter_6ch — 6 通道 TMR 多数表决器 IP 数据手册

## 1. 概述

**tmr_voter_6ch** 是一个基于 Xilinx LUT3 原语的 6 通道三模冗余 (TMR) 多数表决器 IP 核。它对三个冗余处理器核心的输出信号执行逐位 Majority-3 投票，确保单个核心故障不会传播到下游逻辑。

- **IP 名称:** tmr_voter_6ch
- **版本:** 1.0
- **供应商:** user.org
- **库:** tmr
- **实现:** 纯组合逻辑 (无寄存器)
- **LUT3 INIT 值:** 8'hE8 (Majority-3 函数)

## 2. 功能描述

### 2.1 Majority-3 表决原理

对于三个冗余输入 (A, B, C)，多数表决输出为:

```
Y = (A & B) | (B & C) | (A & C)
```

使用 Xilinx LUT3 原语实现，INIT 参数设置为 8'hE8 (二进制 11101000)。

### 2.2 LUT3 真值表 (INIT=8'hE8)

| I2 | I1 | I0 | O   |
|:--:|:--:|:--:|:---:|
| 0  | 0  | 0  | 0   |
| 0  | 0  | 1  | 0   |
| 0  | 1  | 0  | 0   |
| 0  | 1  | 1  | 1   |
| 1  | 0  | 0  | 0   |
| 1  | 0  | 1  | 1   |
| 1  | 1  | 0  | 1   |
| 1  | 1  | 1  | 1   |

### 2.3 通道映射

| 通道 | 信号名称       | 方向 | 位宽 | 描述                    |
|:----:|:--------------|:----:|:----:|:-----------------------|
| ch-0 | core[1:3]_ready / voted_ready | 输入/输出 | 1-bit | mmio_in.ready 表决      |
| ch-1 | core[1:3]_boot_valid / voted_boot_valid | 输入/输出 | 1-bit | boot_valid 表决         |
| ch-2 | core[1:3]_exit_valid / voted_exit_valid | 输入/输出 | 1-bit | exit_valid 表决         |
| ch-3 | core[1:3]_exit_code / voted_exit_code | 输入/输出 | 8-bit | exit_code[7:0] 逐位表决 |
| ch-4 | core[1:3]_print_valid / voted_print_valid | 输入/输出 | 1-bit | print_valid 表决        |
| ch-5 | core[1:3]_print_data / voted_print_data | 输入/输出 | 32-bit | print_data[31:0] 逐位表决 |

## 3. 接口定义

### 3.1 端口列表

| 端口名             | 方向 | 位宽 | 描述                               |
|:------------------|:----:|:----:|:----------------------------------|
| clk               | 输入 | 1    | 系统时钟 (10 MHz)                  |
| rst_n             | 输入 | 1    | 异步复位，低电平有效                |
| core1_ready       | 输入 | 1    | 核心 1 mmio_in.ready               |
| core2_ready       | 输入 | 1    | 核心 2 mmio_in.ready               |
| core3_ready       | 输入 | 1    | 核心 3 mmio_in.ready               |
| voted_ready       | 输出 | 1    | 表决后 mmio_in.ready               |
| core1_boot_valid  | 输入 | 1    | 核心 1 boot_valid                  |
| core2_boot_valid  | 输入 | 1    | 核心 2 boot_valid                  |
| core3_boot_valid  | 输入 | 1    | 核心 3 boot_valid                  |
| voted_boot_valid  | 输出 | 1    | 表决后 boot_valid                  |
| core1_exit_valid  | 输入 | 1    | 核心 1 exit_valid                  |
| core2_exit_valid  | 输入 | 1    | 核心 2 exit_valid                  |
| core3_exit_valid  | 输入 | 1    | 核心 3 exit_valid                  |
| voted_exit_valid  | 输出 | 1    | 表决后 exit_valid                  |
| core1_exit_code   | 输入 | 8    | 核心 1 exit_code[7:0]             |
| core2_exit_code   | 输入 | 8    | 核心 2 exit_code[7:0]             |
| core3_exit_code   | 输入 | 8    | 核心 3 exit_code[7:0]             |
| voted_exit_code   | 输出 | 8    | 表决后 exit_code[7:0] (逐位投票)   |
| core1_print_valid | 输入 | 1    | 核心 1 print_valid                 |
| core2_print_valid | 输入 | 1    | 核心 2 print_valid                 |
| core3_print_valid | 输入 | 1    | 核心 3 print_valid                 |
| voted_print_valid | 输出 | 1    | 表决后 print_valid                 |
| core1_print_data  | 输入 | 32   | 核心 1 print_data[31:0]           |
| core2_print_data  | 输入 | 32   | 核心 2 print_data[31:0]           |
| core3_print_data  | 输入 | 32   | 核心 3 print_data[31:0]           |
| voted_print_data  | 输出 | 32   | 表决后 print_data[31:0] (逐位投票) |

**端口总计:** 24 个 (18 输入 + 6 输出)

### 3.2 时序参数

| 参数                  | 最小值 | 典型值 | 最大值 | 单位 |
|:---------------------|:------:|:------:|:------:|:----:|
| 时钟频率             | —      | 10     | 100+   | MHz  |
| 时钟周期             | 10     | 100    | —      | ns   |
| 输入到输出组合延迟   | —      | 1.0    | 2.0    | ns   |
| 每级 LUT3 延迟       | —      | 0.5    | —      | ns   |
| 建立时间 (输入)      | 2.0    | —      | —      | ns   |
| 保持时间 (输入)      | 0.5    | —      | —      | ns   |
| 输出有效延迟         | —      | —      | 3.0    | ns   |

## 4. 资源利用率

| 资源       | 使用量 |
|:----------|:------:|
| LUT3      | 44     |
| FF        | 0      |
| 逻辑深度  | 2 级   |

**资源分解:**

| 通道   | LUT3 数量 |
|:------|:---------:|
| ch-0 (ready) | 1 |
| ch-1 (boot_valid) | 1 |
| ch-2 (exit_valid) | 1 |
| ch-3 (exit_code, 8-bit) | 8 |
| ch-4 (print_valid) | 1 |
| ch-5 (print_data, 32-bit) | 32 |
| **总计** | **44** |

## 5. 支持器件

| 系列            | 支持情况 |
|:---------------|:--------:|
| Xilinx 7-series (Artix-7, Kintex-7, Virtex-7) | 完全支持 |
| Xilinx UltraScale (Kintex-U, Virtex-U) | 完全支持 |
| Xilinx UltraScale+ (Kintex-U+, Virtex-U+, Zynq-U+) | 完全支持 |
| Xilinx Spartan-7 | 完全支持 |

## 6. 设计约束

- **逻辑深度:** 2 级组合逻辑 (输入缓冲 → LUT3)
- **时钟域:** 无时钟域交叉 (纯组合)
- **复位:** clk 和 rst_n 端口供系统连接，模块内部未使用
- **扇出:** 每个输入端口驱动其所在的 LUT3 链，扇出 ≤ 32

## 7. 版本历史

| 版本 | 日期       | 描述                  |
|:---:|:----------|:---------------------|
| 1.0 | 2026-07-12 | 初始版本              |
