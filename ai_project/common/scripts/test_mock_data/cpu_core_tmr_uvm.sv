//------------------------------------------------------------------------------
// cpu_core_tmr_uvm.sv
// UVM-compatible SystemVerilog wrapper — auto-converted from cpu_core_tmr.vhd
//
// 层次化 TMR 加固顶层
//
// 结构:
//   Layer 1: cpu_core_tmr_uvm (SV 顶层)
//   Layer 2: cpu_core_tmr_core × 3 (TMR 三模冗余)
//   Layer 3: 12 个子模块 (hazard, trap, csr, predictor, rom, ram,
//                        fetch, decode, execute, mem1, mem2, writeback)
//
// TMR 表决通道 (6 通道):
//   通道 0 — mmio_in_ready       (3选2)
//   通道 1 — mmio_out_boot_valid (3选2)
//   通道 2 — mmio_out_exit_valid (3选2)
//   通道 3 — mmio_out_exit_code  (8-bit 按位3选2)
//   通道 4 — mmio_out_print_valid(3选2)
//   通道 5 — mmio_out_print_data (32-bit 按位3选2)
//
// UVM Register Model 映射说明:
//   ch0: TMR_VOTER_CH0_CTRL   — mmio_in_ready 表决结果
//   ch1: TMR_VOTER_CH1_CTRL   — mmio_out_boot_valid 表决结果
//   ch2: TMR_VOTER_CH2_CTRL   — mmio_out_exit_valid 表决结果
//   ch3: TMR_VOTER_CH3_DATA   — mmio_out_exit_code[*] 按位表决
//   ch4: TMR_VOTER_CH4_CTRL   — mmio_out_print_valid 表决结果
//   ch5: TMR_VOTER_CH5_DATA   — mmio_out_print_data[*] 按位表决
//   ERR_CNT_CH0–CH5           — 6 通道错误计数器 (16-bit)
//   TMR_TOTAL_CYCLES          — 总运行周期计数器 (32-bit)
//
// 使用方法:
//   import cpu_core_tmr_uvm_pkg::*;
//   或在编译时 `include "cpu_core_tmr_uvm.sv"
//
//------------------------------------------------------------------------------

`ifndef CPU_CORE_TMR_UVM_SV
`define CPU_CORE_TMR_UVM_SV

// UVM 库引入
import uvm_pkg::*;
`include "uvm_macros.svh"

//------------------------------------------------------------------------------
// cpu_core_tmr_uvm — TMR 加固顶层模块
//------------------------------------------------------------------------------
module cpu_core_tmr_uvm (
    input  logic        clk,
    input  logic        start,

    // mem_init_if (纯输入, 扇出到 3 核心)
    input  logic        rom_init_write_enable,
    input  logic [31:0] rom_init_write_addr,
    input  logic [31:0] rom_init_write_data,

    // mmio_out_if (输出表决, 5 通道)
    output logic        mmio_out_boot_valid,
    output logic        mmio_out_exit_valid,
    output logic [7:0]  mmio_out_exit_code,
    output logic        mmio_out_print_valid,
    output logic [31:0] mmio_out_print_data,

    // mmio_in_if (混合: valid/data 扇入, ready 表决)
    input  logic        mmio_in_valid,
    input  logic [7:0]  mmio_in_data,
    output logic        mmio_in_ready
);

    // ========================================================================
    // 内部信号声明
    // ========================================================================

    // 核心内部接口连线 (3 套)
    logic core1_ready, core2_ready, core3_ready;

    logic core1_boot_valid;
    logic core2_boot_valid;
    logic core3_boot_valid;

    logic core1_exit_valid;
    logic core2_exit_valid;
    logic core3_exit_valid;

    logic [7:0] core1_exit_code;
    logic [7:0] core2_exit_code;
    logic [7:0] core3_exit_code;

    logic core1_print_valid;
    logic core2_print_valid;
    logic core3_print_valid;

    logic [31:0] core1_print_data;
    logic [31:0] core2_print_data;
    logic [31:0] core3_print_data;

    // 内部连线 (3 核心驱动) — 预留，当前未用
    logic [2:0] core_ready;

    // rom_init 扇出信号 (3 路)
    logic       rom_init_core1_write_enable;
    logic [31:0] rom_init_core1_write_addr;
    logic [31:0] rom_init_core1_write_data;
    logic       rom_init_core2_write_enable;
    logic [31:0] rom_init_core2_write_addr;
    logic [31:0] rom_init_core2_write_data;
    logic       rom_init_core3_write_enable;
    logic [31:0] rom_init_core3_write_addr;
    logic [31:0] rom_init_core3_write_data;

    // mmio_in 扇出信号 (3 路)
    logic       mmio_in_core1_valid;
    logic [7:0] mmio_in_core1_data;
    logic       mmio_in_core2_valid;
    logic [7:0] mmio_in_core2_data;
    logic       mmio_in_core3_valid;
    logic [7:0] mmio_in_core3_data;

    // -----------------------------------------------------------------------
    // 错误计数器 (UVM Register Model: ERR_CNT_CH0–CH5, TMR_TOTAL_CYCLES)
    // 预留用于 TMR 错误追踪，当前为占位实现
    // -----------------------------------------------------------------------
    logic [15:0] error_count_ch0;
    logic [15:0] error_count_ch1;
    logic [15:0] error_count_ch2;
    logic [15:0] error_count_ch3;
    logic [15:0] error_count_ch4;
    logic [15:0] error_count_ch5;
    logic [31:0] total_cycles;

    // ========================================================================
    // [1] mem_init_if.sink → 纯输入扇出 (3 路)
    // ========================================================================
    always_comb begin
        rom_init_core1_write_enable = rom_init_write_enable;
        rom_init_core1_write_addr   = rom_init_write_addr;
        rom_init_core1_write_data   = rom_init_write_data;

        rom_init_core2_write_enable = rom_init_write_enable;
        rom_init_core2_write_addr   = rom_init_write_addr;
        rom_init_core2_write_data   = rom_init_write_data;

        rom_init_core3_write_enable = rom_init_write_enable;
        rom_init_core3_write_addr   = rom_init_write_addr;
        rom_init_core3_write_data   = rom_init_write_data;
    end

    // ========================================================================
    // [2] mmio_in_if.sink → valid/data 扇入 (3 路)
    // ========================================================================
    always_comb begin
        mmio_in_core1_valid = mmio_in_valid;
        mmio_in_core1_data  = mmio_in_data;
        mmio_in_core2_valid = mmio_in_valid;
        mmio_in_core2_data  = mmio_in_data;
        mmio_in_core3_valid = mmio_in_valid;
        mmio_in_core3_data  = mmio_in_data;
    end

    // ========================================================================
    // [3] 3 核心实例化 — 直接模块实例化 (无需 component 声明)
    // ========================================================================
    cpu_core_tmr_core core_inst_1 (
        .clk                  (clk),
        .start                (start),
        .rom_init_write_enable(rom_init_core1_write_enable),
        .rom_init_write_addr  (rom_init_core1_write_addr),
        .rom_init_write_data  (rom_init_core1_write_data),
        .mmio_in_valid        (mmio_in_core1_valid),
        .mmio_in_data         (mmio_in_core1_data),
        .mmio_in_ready        (core1_ready),
        .mmio_out_boot_valid  (core1_boot_valid),
        .mmio_out_exit_valid  (core1_exit_valid),
        .mmio_out_exit_code   (core1_exit_code),
        .mmio_out_print_valid (core1_print_valid),
        .mmio_out_print_data  (core1_print_data)
    );

    cpu_core_tmr_core core_inst_2 (
        .clk                  (clk),
        .start                (start),
        .rom_init_write_enable(rom_init_core2_write_enable),
        .rom_init_write_addr  (rom_init_core2_write_addr),
        .rom_init_write_data  (rom_init_core2_write_data),
        .mmio_in_valid        (mmio_in_core2_valid),
        .mmio_in_data         (mmio_in_core2_data),
        .mmio_in_ready        (core2_ready),
        .mmio_out_boot_valid  (core2_boot_valid),
        .mmio_out_exit_valid  (core2_exit_valid),
        .mmio_out_exit_code   (core2_exit_code),
        .mmio_out_print_valid (core2_print_valid),
        .mmio_out_print_data  (core2_print_data)
    );

    cpu_core_tmr_core core_inst_3 (
        .clk                  (clk),
        .start                (start),
        .rom_init_write_enable(rom_init_core3_write_enable),
        .rom_init_write_addr  (rom_init_core3_write_addr),
        .rom_init_write_data  (rom_init_core3_write_data),
        .mmio_in_valid        (mmio_in_core3_valid),
        .mmio_in_data         (mmio_in_core3_data),
        .mmio_in_ready        (core3_ready),
        .mmio_out_boot_valid  (core3_boot_valid),
        .mmio_out_exit_valid  (core3_exit_valid),
        .mmio_out_exit_code   (core3_exit_code),
        .mmio_out_print_valid (core3_print_valid),
        .mmio_out_print_data  (core3_print_data)
    );

    // ========================================================================
    // [4] TMR 多数表决器 (6 通道) — 使用 always_comb 组合逻辑
    // ========================================================================

    // ch-0: mmio_in.ready (3选2)
    // UVM RegMap: TMR_VOTER_CH0_CTRL [0] — 硬连线表决结果
    always_comb begin
        mmio_in_ready = (core1_ready & core2_ready) |
                        (core1_ready & core3_ready) |
                        (core2_ready & core3_ready);
    end

    // ch-1: mmio_out.boot_valid (3选2)
    // UVM RegMap: TMR_VOTER_CH1_CTRL [0] — 硬连线表决结果
    always_comb begin
        mmio_out_boot_valid = (core1_boot_valid & core2_boot_valid) |
                              (core1_boot_valid & core3_boot_valid) |
                              (core2_boot_valid & core3_boot_valid);
    end

    // ch-2: mmio_out.exit_valid (3选2)
    // UVM RegMap: TMR_VOTER_CH2_CTRL [0] — 硬连线表决结果
    always_comb begin
        mmio_out_exit_valid = (core1_exit_valid & core2_exit_valid) |
                              (core1_exit_valid & core3_exit_valid) |
                              (core2_exit_valid & core3_exit_valid);
    end

    // ch-3: mmio_out.exit_code (8-bit 按位3选2)
    // UVM RegMap: TMR_VOTER_CH3_DATA[7:0] — 按位多数表决
    always_comb begin
        mmio_out_exit_code = (core1_exit_code & core2_exit_code) |
                             (core1_exit_code & core3_exit_code) |
                             (core2_exit_code & core3_exit_code);
    end

    // ch-4: mmio_out.print_valid (3选2)
    // UVM RegMap: TMR_VOTER_CH4_CTRL [0] — 硬连线表决结果
    always_comb begin
        mmio_out_print_valid = (core1_print_valid & core2_print_valid) |
                               (core1_print_valid & core3_print_valid) |
                               (core2_print_valid & core3_print_valid);
    end

    // ch-5: mmio_out.print_data (32-bit 按位3选2)
    // UVM RegMap: TMR_VOTER_CH5_DATA[31:0] — 按位多数表决
    always_comb begin
        mmio_out_print_data = (core1_print_data & core2_print_data) |
                              (core1_print_data & core3_print_data) |
                              (core2_print_data & core3_print_data);
    end

    // ========================================================================
    // 初始值设定 (仿真用)
    // ========================================================================
    initial begin
        error_count_ch0 = 16'h0;
        error_count_ch1 = 16'h0;
        error_count_ch2 = 16'h0;
        error_count_ch3 = 16'h0;
        error_count_ch4 = 16'h0;
        error_count_ch5 = 16'h0;
        total_cycles    = 32'h0;
    end

endmodule : cpu_core_tmr_uvm

`endif // CPU_CORE_TMR_UVM_SV
