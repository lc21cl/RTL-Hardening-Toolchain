// ============================================================
// tmr_voter_6ch_xilinx.v — 6 通道 TMR 表决器 (Xilinx LUT3 原语版本)
//
// 使用 LUT3 #(.INIT(8'hE8)) 实现 Majority-3 函数。
// LUT3 真值表 (INIT=8'hE8 = 8'b11101000):
//   I2 I1 I0 | O
//   0  0  0  | 0
//   0  0  1  | 0
//   0  1  0  | 0
//   0  1  1  | 1
//   1  0  0  | 0
//   1  0  1  | 1
//   1  1  0  | 1
//   1  1  1  | 1
//
// 适用于 Xilinx 7-series / UltraScale / UltraScale+ FPGA。
// 纯组合逻辑，无时钟域交叉。
// ============================================================

`timescale 1ns / 1ps


// ======== LUT3 仿真模型 ========
// 为 iverilog 仿真提供行为模型，同时保持与 Xilinx Vivado 工具链兼容。
module LUT3 #(
    parameter [7:0] INIT = 8'h00
) (
    input  wire I0,
    input  wire I1,
    input  wire I2,
    output wire O
);
    wire [2:0] lut_sel;
    assign lut_sel = {I2, I1, I0};
    assign O = INIT[lut_sel];
endmodule


// ======== 6 通道 TMR 表决器 (Xilinx LUT3 版本) ========
module tmr_voter_6ch_xilinx (
    input  wire       clk,
    input  wire       rst_n,

    // ch-0: mmio_in.ready
    input  wire       core1_ready,
    input  wire       core2_ready,
    input  wire       core3_ready,
    output wire       voted_ready,

    // ch-1: boot_valid
    input  wire       core1_boot_valid,
    input  wire       core2_boot_valid,
    input  wire       core3_boot_valid,
    output wire       voted_boot_valid,

    // ch-2: exit_valid
    input  wire       core1_exit_valid,
    input  wire       core2_exit_valid,
    input  wire       core3_exit_valid,
    output wire       voted_exit_valid,

    // ch-3: exit_code (8-bit)
    input  wire [7:0] core1_exit_code,
    input  wire [7:0] core2_exit_code,
    input  wire [7:0] core3_exit_code,
    output wire [7:0] voted_exit_code,

    // ch-4: print_valid
    input  wire       core1_print_valid,
    input  wire       core2_print_valid,
    input  wire       core3_print_valid,
    output wire       voted_print_valid,

    // ch-5: print_data (32-bit)
    input  wire [31:0] core1_print_data,
    input  wire [31:0] core2_print_data,
    input  wire [31:0] core3_print_data,
    output wire [31:0] voted_print_data
);

    // ======== 1-bit 通道: 直接例化 LUT3 ========

    // ch-0: ready
    LUT3 #(.INIT(8'hE8)) u_lut_ch0_ready (
        .O (voted_ready),
        .I0(core1_ready),
        .I1(core2_ready),
        .I2(core3_ready)
    );

    // ch-1: boot_valid
    LUT3 #(.INIT(8'hE8)) u_lut_ch1_boot_valid (
        .O (voted_boot_valid),
        .I0(core1_boot_valid),
        .I1(core2_boot_valid),
        .I2(core3_boot_valid)
    );

    // ch-2: exit_valid
    LUT3 #(.INIT(8'hE8)) u_lut_ch2_exit_valid (
        .O (voted_exit_valid),
        .I0(core1_exit_valid),
        .I1(core2_exit_valid),
        .I2(core3_exit_valid)
    );

    // ch-4: print_valid
    LUT3 #(.INIT(8'hE8)) u_lut_ch4_print_valid (
        .O (voted_print_valid),
        .I0(core1_print_valid),
        .I1(core2_print_valid),
        .I2(core3_print_valid)
    );

    // ======== 多-bit 通道: generate for 循环批量生成 ========

    // ch-3: exit_code (8-bit)
    genvar i;
    generate
        for (i = 0; i < 8; i = i + 1) begin : gen_exit_code
            LUT3 #(.INIT(8'hE8)) u_lut (
                .O (voted_exit_code[i]),
                .I0(core1_exit_code[i]),
                .I1(core2_exit_code[i]),
                .I2(core3_exit_code[i])
            );
        end
    endgenerate

    // ch-5: print_data (32-bit)
    generate
        for (i = 0; i < 32; i = i + 1) begin : gen_print_data
            LUT3 #(.INIT(8'hE8)) u_lut (
                .O (voted_print_data[i]),
                .I0(core1_print_data[i]),
                .I1(core2_print_data[i]),
                .I2(core3_print_data[i])
            );
        end
    endgenerate

endmodule
