// ============================================================
// cpu_core_tmr_xilinx_pipeline.v — Pipeline 寄存器版本
//
// tmr_voter_6ch_pipeline: 在 LUT3 组合逻辑输出端插入
//   pipeline 寄存器，受 PIPELINE_ENABLE 参数控制。
//
// 特性:
//   - PIPELINE_ENABLE=1: 插入 44 级寄存器，时序裕量 ~97ns
//   - PIPELINE_ENABLE=0: 纯组合逻辑，与 baseline 版一致
// ============================================================

`timescale 1ns / 1ps


// ======== LUT3 仿真模型 ========
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


// ======== 6 通道 TMR 表决器 (Pipeline 版本) ========
module tmr_voter_6ch_pipeline #(
    parameter PIPELINE_ENABLE = 1
) (
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

    // ======== 组合逻辑中间信号 ========
    wire voted_ready_cmb;
    wire voted_boot_valid_cmb;
    wire voted_exit_valid_cmb;
    wire [7:0] voted_exit_code_cmb;
    wire voted_print_valid_cmb;
    wire [31:0] voted_print_data_cmb;

    // ======== 1-bit 通道: 直接例化 LUT3 ========

    // ch-0: ready
    LUT3 #(.INIT(8'hE8)) u_lut_ch0_ready (
        .O (voted_ready_cmb),
        .I0(core1_ready),
        .I1(core2_ready),
        .I2(core3_ready)
    );

    // ch-1: boot_valid
    LUT3 #(.INIT(8'hE8)) u_lut_ch1_boot_valid (
        .O (voted_boot_valid_cmb),
        .I0(core1_boot_valid),
        .I1(core2_boot_valid),
        .I2(core3_boot_valid)
    );

    // ch-2: exit_valid
    LUT3 #(.INIT(8'hE8)) u_lut_ch2_exit_valid (
        .O (voted_exit_valid_cmb),
        .I0(core1_exit_valid),
        .I1(core2_exit_valid),
        .I2(core3_exit_valid)
    );

    // ch-4: print_valid
    LUT3 #(.INIT(8'hE8)) u_lut_ch4_print_valid (
        .O (voted_print_valid_cmb),
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
                .O (voted_exit_code_cmb[i]),
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
                .O (voted_print_data_cmb[i]),
                .I0(core1_print_data[i]),
                .I1(core2_print_data[i]),
                .I2(core3_print_data[i])
            );
        end
    endgenerate

    // ======== Pipeline 寄存器 (受 PIPELINE_ENABLE 控制) ========
    generate
        if (PIPELINE_ENABLE) begin : gen_pipe_on
            // ch-0: ready
            reg voted_ready_r;
            // ch-1: boot_valid
            reg voted_boot_valid_r;
            // ch-2: exit_valid
            reg voted_exit_valid_r;
            // ch-3: exit_code (8-bit)
            reg [7:0] voted_exit_code_r;
            // ch-4: print_valid
            reg voted_print_valid_r;
            // ch-5: print_data (32-bit)
            reg [31:0] voted_print_data_r;

            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    voted_ready_r      <= 1'b0;
                    voted_boot_valid_r <= 1'b0;
                    voted_exit_valid_r <= 1'b0;
                    voted_exit_code_r  <= 8'h00;
                    voted_print_valid_r <= 1'b0;
                    voted_print_data_r <= 32'h00000000;
                end else begin
                    voted_ready_r      <= voted_ready_cmb;
                    voted_boot_valid_r <= voted_boot_valid_cmb;
                    voted_exit_valid_r <= voted_exit_valid_cmb;
                    voted_exit_code_r  <= voted_exit_code_cmb;
                    voted_print_valid_r <= voted_print_valid_cmb;
                    voted_print_data_r <= voted_print_data_cmb;
                end
            end

            assign voted_ready       = voted_ready_r;
            assign voted_boot_valid  = voted_boot_valid_r;
            assign voted_exit_valid  = voted_exit_valid_r;
            assign voted_exit_code   = voted_exit_code_r;
            assign voted_print_valid = voted_print_valid_r;
            assign voted_print_data  = voted_print_data_r;

        end else begin : gen_pipe_off
            // PIPELINE_ENABLE=0: 直通，纯组合逻辑
            assign voted_ready       = voted_ready_cmb;
            assign voted_boot_valid  = voted_boot_valid_cmb;
            assign voted_exit_valid  = voted_exit_valid_cmb;
            assign voted_exit_code   = voted_exit_code_cmb;
            assign voted_print_valid = voted_print_valid_cmb;
            assign voted_print_data  = voted_print_data_cmb;
        end
    endgenerate

endmodule
