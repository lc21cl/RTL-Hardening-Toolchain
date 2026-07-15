// ============================================================
// cpu_core_tmr_xilinx.v — Xilinx FPGA 3-LUT 原语例化版本的
// TMR 表决器 (替换 cpu_core_tmr_synth.v 中的布尔表达式)
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


// ======== 6 通道 TMR 表决器 (Xilinx LUT3 + Pipeline 版本) ========
// PIPELINE_ENABLE=1: 插入 44 级寄存器，时序裕量 ~97ns
// PIPELINE_ENABLE=0: 纯组合逻辑，与 LUT3 版一致
module tmr_voter_6ch_xilinx #(
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


// ======== Xilinx LUT3 表决器测试台 ========
// 与 tb_tmr_voter_6ch 结构一致，实例化 tmr_voter_6ch_xilinx。
// 使用 `ifndef YOSYS 保护，避免 yosys 解析不可综合的测试台代码。
`ifndef YOSYS
module tb_tmr_voter_xilinx;

    // ====== 时钟与复位 ======
    reg clk;
    reg rst_n;

    // ====== DUT 连线 ======

    // ch-0: ready (1-bit)
    reg       core1_ready, core2_ready, core3_ready;
    wire      voted_ready;

    // ch-1: boot_valid (1-bit)
    reg       core1_boot_valid, core2_boot_valid, core3_boot_valid;
    wire      voted_boot_valid;

    // ch-2: exit_valid (1-bit)
    reg       core1_exit_valid, core2_exit_valid, core3_exit_valid;
    wire      voted_exit_valid;

    // ch-3: exit_code (8-bit)
    reg [7:0] core1_exit_code, core2_exit_code, core3_exit_code;
    wire [7:0] voted_exit_code;

    // ch-4: print_valid (1-bit)
    reg       core1_print_valid, core2_print_valid, core3_print_valid;
    wire      voted_print_valid;

    // ch-5: print_data (32-bit)
    reg [31:0] core1_print_data, core2_print_data, core3_print_data;
    wire [31:0] voted_print_data;

    // ====== DUT 实例化 ======
    tmr_voter_6ch_xilinx u_voter (
        .clk                (clk),
        .rst_n              (rst_n),

        .core1_ready        (core1_ready),
        .core2_ready        (core2_ready),
        .core3_ready        (core3_ready),
        .voted_ready        (voted_ready),

        .core1_boot_valid   (core1_boot_valid),
        .core2_boot_valid   (core2_boot_valid),
        .core3_boot_valid   (core3_boot_valid),
        .voted_boot_valid   (voted_boot_valid),

        .core1_exit_valid   (core1_exit_valid),
        .core2_exit_valid   (core2_exit_valid),
        .core3_exit_valid   (core3_exit_valid),
        .voted_exit_valid   (voted_exit_valid),

        .core1_exit_code    (core1_exit_code),
        .core2_exit_code    (core2_exit_code),
        .core3_exit_code    (core3_exit_code),
        .voted_exit_code    (voted_exit_code),

        .core1_print_valid  (core1_print_valid),
        .core2_print_valid  (core2_print_valid),
        .core3_print_valid  (core3_print_valid),
        .voted_print_valid  (voted_print_valid),

        .core1_print_data   (core1_print_data),
        .core2_print_data   (core2_print_data),
        .core3_print_data   (core3_print_data),
        .voted_print_data   (voted_print_data)
    );

    // ====== 10MHz 时钟 ======
    initial clk = 0;
    always #50 clk = ~clk;  // 周期 100ns

    // ====== 测试主流程 ======
    integer fd;
    integer ch_idx, width;
    integer c1_val, c2_val, c3_val, exp_val;
    integer total, passed, failed;
    integer scan_ret;
    integer is_ok;
    reg [80:0] ch_str;

    initial begin
        // 初始化
        clk = 0;
        rst_n = 0;
        {core1_ready, core2_ready, core3_ready} = 3'b0;
        {core1_boot_valid, core2_boot_valid, core3_boot_valid} = 3'b0;
        {core1_exit_valid, core2_exit_valid, core3_exit_valid} = 3'b0;
        core1_exit_code = 8'h00; core2_exit_code = 8'h00; core3_exit_code = 8'h00;
        {core1_print_valid, core2_print_valid, core3_print_valid} = 3'b0;
        core1_print_data = 32'h00000000;
        core2_print_data = 32'h00000000;
        core3_print_data = 32'h00000000;

        total = 0;
        passed = 0;
        failed = 0;

        // VCD 波形输出
        $dumpfile("tmr_voter_xilinx_waveform.vcd");
        $dumpvars(0, tb_tmr_voter_xilinx);

        $display("============================================================");
        $display("TMR 6-Channel Voter Xilinx LUT3 Simulation Testbench");
        $display("============================================================");

        // 复位
        #150;
        rst_n = 1;
        #100;

        // 打开测试向量文件
        fd = $fopen("tmr_voter_test_vectors.hex", "r");
        if (fd == 0) begin
            $display("ERROR: Cannot open test vector file 'tmr_voter_test_vectors.hex'");
            $display("Please run gen_tb_vectors.py first to generate test vectors.");
            $finish;
        end

        $display("Reading test vectors from tmr_voter_test_vectors.hex ...\n");

        // 逐行处理测试向量
        while (!$feof(fd)) begin
            scan_ret = $fscanf(fd, "%d %d %x %x %x %x",
                               ch_idx, width, c1_val, c2_val, c3_val, exp_val);

            if (scan_ret >= 6) begin
                // 有效向量行 — 执行测试
                @(posedge clk);
                #2;

                // 设置输入
                case (ch_idx)
                    0: begin
                        core1_ready = c1_val[0];
                        core2_ready = c2_val[0];
                        core3_ready = c3_val[0];
                    end
                    1: begin
                        core1_boot_valid = c1_val[0];
                        core2_boot_valid = c2_val[0];
                        core3_boot_valid = c3_val[0];
                    end
                    2: begin
                        core1_exit_valid = c1_val[0];
                        core2_exit_valid = c2_val[0];
                        core3_exit_valid = c3_val[0];
                    end
                    3: begin
                        core1_exit_code = c1_val[7:0];
                        core2_exit_code = c2_val[7:0];
                        core3_exit_code = c3_val[7:0];
                    end
                    4: begin
                        core1_print_valid = c1_val[0];
                        core2_print_valid = c2_val[0];
                        core3_print_valid = c3_val[0];
                    end
                    5: begin
                        core1_print_data = c1_val;
                        core2_print_data = c2_val;
                        core3_print_data = c3_val;
                    end
                endcase

                #1;  // 等待组合逻辑稳定

                // 获取通道字符串
                if (ch_idx == 0) ch_str = "ch-0 (mmio_in.ready)";
                else if (ch_idx == 1) ch_str = "ch-1 (mmio_out.boot_valid)";
                else if (ch_idx == 2) ch_str = "ch-2 (mmio_out.exit_valid)";
                else if (ch_idx == 3) ch_str = "ch-3 (mmio_out.exit_code)";
                else if (ch_idx == 4) ch_str = "ch-4 (mmio_out.print_valid)";
                else ch_str = "ch-5 (mmio_out.print_data)";

                is_ok = 0;

                // 检查输出
                case (ch_idx)
                    0: begin
                        is_ok = (voted_ready === exp_val[0]);
                        if (is_ok) begin
                            $display("PASS: %0s | c1=%d c2=%d c3=%d | voted=%d expected=%d",
                                     ch_str, core1_ready, core2_ready, core3_ready,
                                     voted_ready, exp_val[0]);
                        end else begin
                            $display("FAIL: %0s | c1=%d c2=%d c3=%d | voted=%d expected=%d",
                                     ch_str, core1_ready, core2_ready, core3_ready,
                                     voted_ready, exp_val[0]);
                        end
                    end
                    1: begin
                        is_ok = (voted_boot_valid === exp_val[0]);
                        if (is_ok) begin
                            $display("PASS: %0s | c1=%d c2=%d c3=%d | voted=%d expected=%d",
                                     ch_str, core1_boot_valid, core2_boot_valid,
                                     core3_boot_valid, voted_boot_valid, exp_val[0]);
                        end else begin
                            $display("FAIL: %0s | c1=%d c2=%d c3=%d | voted=%d expected=%d",
                                     ch_str, core1_boot_valid, core2_boot_valid,
                                     core3_boot_valid, voted_boot_valid, exp_val[0]);
                        end
                    end
                    2: begin
                        is_ok = (voted_exit_valid === exp_val[0]);
                        if (is_ok) begin
                            $display("PASS: %0s | c1=%d c2=%d c3=%d | voted=%d expected=%d",
                                     ch_str, core1_exit_valid, core2_exit_valid,
                                     core3_exit_valid, voted_exit_valid, exp_val[0]);
                        end else begin
                            $display("FAIL: %0s | c1=%d c2=%d c3=%d | voted=%d expected=%d",
                                     ch_str, core1_exit_valid, core2_exit_valid,
                                     core3_exit_valid, voted_exit_valid, exp_val[0]);
                        end
                    end
                    3: begin
                        is_ok = (voted_exit_code === exp_val[7:0]);
                        if (is_ok) begin
                            $display("PASS: %0s | c1=%02x c2=%02x c3=%02x | voted=%02x expected=%02x",
                                     ch_str, core1_exit_code, core2_exit_code,
                                     core3_exit_code, voted_exit_code, exp_val[7:0]);
                        end else begin
                            $display("FAIL: %0s | c1=%02x c2=%02x c3=%02x | voted=%02x expected=%02x",
                                     ch_str, core1_exit_code, core2_exit_code,
                                     core3_exit_code, voted_exit_code, exp_val[7:0]);
                        end
                    end
                    4: begin
                        is_ok = (voted_print_valid === exp_val[0]);
                        if (is_ok) begin
                            $display("PASS: %0s | c1=%d c2=%d c3=%d | voted=%d expected=%d",
                                     ch_str, core1_print_valid, core2_print_valid,
                                     core3_print_valid, voted_print_valid, exp_val[0]);
                        end else begin
                            $display("FAIL: %0s | c1=%d c2=%d c3=%d | voted=%d expected=%d",
                                     ch_str, core1_print_valid, core2_print_valid,
                                     core3_print_valid, voted_print_valid, exp_val[0]);
                        end
                    end
                    5: begin
                        is_ok = (voted_print_data === exp_val);
                        if (is_ok) begin
                            $display("PASS: %0s | c1=%08x c2=%08x c3=%08x | voted=%08x expected=%08x",
                                     ch_str, core1_print_data, core2_print_data,
                                     core3_print_data, voted_print_data, exp_val);
                        end else begin
                            $display("FAIL: %0s | c1=%08x c2=%08x c3=%08x | voted=%08x expected=%08x",
                                     ch_str, core1_print_data, core2_print_data,
                                     core3_print_data, voted_print_data, exp_val);
                        end
                    end
                endcase

                if (is_ok) passed = passed + 1;
                else failed = failed + 1;
                total = total + 1;

                // 清除所有输入 (为下一个测试周期做准备)
                @(negedge clk);
                #1;
                core1_ready = 0; core2_ready = 0; core3_ready = 0;
                core1_boot_valid = 0; core2_boot_valid = 0; core3_boot_valid = 0;
                core1_exit_valid = 0; core2_exit_valid = 0; core3_exit_valid = 0;
                core1_exit_code = 8'h00; core2_exit_code = 8'h00; core3_exit_code = 8'h00;
                core1_print_valid = 0; core2_print_valid = 0; core3_print_valid = 0;
                core1_print_data = 32'h00000000;
                core2_print_data = 32'h00000000;
                core3_print_data = 32'h00000000;
            end else begin
                // 忽略空白或格式错误的行
                if (!$feof(fd))
                    $display("WARNING: Skipping malformed line at test %0d", total+1);
            end
        end

        $fclose(fd);

        // ====== 最终总结 ======
        $display("");
        $display("============================================================");
        $display("SIMULATION SUMMARY");
        $display("============================================================");
        $display("  Total tests: %0d", total);
        $display("  Passed:      %0d", passed);
        $display("  Failed:      %0d", failed);
        $display("  Clock cycles: %0d (target: >= 1000)", total);
        $display("------------------------------------------------------------");

        if (failed == 0) begin
            $display("  RESULT: ALL TESTS PASSED");
        end else begin
            $display("  RESULT: %0d TEST(S) FAILED", failed);
        end
        $display("============================================================");

        // 额外运行几个周期以扩展波形
        repeat (10) @(posedge clk);

        $finish;
    end

endmodule
`endif
