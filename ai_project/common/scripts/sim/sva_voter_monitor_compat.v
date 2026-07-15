// ================================================================
// sva_voter_monitor_compat.v -- 6 通道断言 (iverilog 兼容版)
//
// 兼容性: Icarus Verilog 12.0+ / ModelSim / VCS
// 功能: 与 sva_voter_monitor.sv 完全等价的断言逻辑,
//       但使用 always @(posedge clk) + if + $display 替代
//       assert property 语法, 以兼容老版本仿真器
//
// 断言策略:
//   正常模式: $display 永不输出
//   SEU 注入: 对应通道的 $display 立即输出 [SVA-ERROR], 包含差异信息
// ================================================================

`timescale 1ns / 1ps

module sva_voter_monitor_compat (
    input clk,
    input rst_n,

    // ch-0: mmio_in.ready (1-bit)
    input ready_1, ready_2, ready_3,

    // ch-1: mmio_out.boot_valid (1-bit)
    input boot_valid_1, boot_valid_2, boot_valid_3,

    // ch-2: mmio_out.exit_valid (1-bit)
    input exit_valid_1, exit_valid_2, exit_valid_3,

    // ch-3: mmio_out.exit_code (8-bit)
    input [7:0] exit_code_1, exit_code_2, exit_code_3,

    // ch-4: mmio_out.print_valid (1-bit)
    input print_valid_1, print_valid_2, print_valid_3,

    // ch-5: mmio_out.print_data (32-bit)
    input [31:0] print_data_1, print_data_2, print_data_3
);

    parameter ENABLE_SVA = 1;

    // 辅助函数: 计算 Hamming 距离 ($countones 的纯 Verilog 实现)
    function automatic integer hamming_distance;
        input [31:0] x;
        integer cnt, i;
        begin
            cnt = 0;
            for (i = 0; i < 32; i = i + 1) begin
                if (x[i]) cnt = cnt + 1;
            end
            hamming_distance = cnt;
        end
    endfunction

    // 6 通道错误计数器 (用于阈值告警)
    reg [15:0] error_count_ch0;
    reg [15:0] error_count_ch1;
    reg [15:0] error_count_ch2;
    reg [15:0] error_count_ch3;
    reg [15:0] error_count_ch4;
    reg [15:0] error_count_ch5;
    reg [31:0] total_clock_cycles;

    generate
        if (ENABLE_SVA) begin : sva_assertions

            // 所有断言每时钟周期检查
            always @(posedge clk) begin
                if (!rst_n) begin
                    error_count_ch0 <= 0;
                    error_count_ch1 <= 0;
                    error_count_ch2 <= 0;
                    error_count_ch3 <= 0;
                    error_count_ch4 <= 0;
                    error_count_ch5 <= 0;
                    total_clock_cycles <= 0;
                end else begin
                    total_clock_cycles <= total_clock_cycles + 1;

                    // ---- ch-0: mmio_in.ready ----
                    if (!(ready_1 === ready_2 && ready_2 === ready_3)) begin
                        error_count_ch0 <= error_count_ch0 + 1;
                        $display("[SVA-ERROR][ch-0] mmio_in.ready fail @t=%0t: core1=%b core2=%b core3=%b", $time, ready_1, ready_2, ready_3);
                    end

                    // ---- ch-1: mmio_out.boot_valid ----
                    if (!(boot_valid_1 === boot_valid_2 && boot_valid_2 === boot_valid_3)) begin
                        error_count_ch1 <= error_count_ch1 + 1;
                        $display("[SVA-ERROR][ch-1] mmio_out.boot_valid fail @t=%0t: core1=%b core2=%b core3=%b", $time, boot_valid_1, boot_valid_2, boot_valid_3);
                    end

                    // ---- ch-2: mmio_out.exit_valid ----
                    if (!(exit_valid_1 === exit_valid_2 && exit_valid_2 === exit_valid_3)) begin
                        error_count_ch2 <= error_count_ch2 + 1;
                        $display("[SVA-ERROR][ch-2] mmio_out.exit_valid fail @t=%0t: core1=%b core2=%b core3=%b", $time, exit_valid_1, exit_valid_2, exit_valid_3);
                    end

                    // ---- ch-3: mmio_out.exit_code (含差异位掩码 + 多比特翻转检测) ----
                    if (!(exit_code_1 === exit_code_2 && exit_code_2 === exit_code_3)) begin
                        error_count_ch3 <= error_count_ch3 + 1;
                        $display("[SVA-ERROR][ch-3] mmio_out.exit_code fail @t=%0t: core1=%h core2=%h core3=%h diff_mask=%b", $time, exit_code_1, exit_code_2, exit_code_3, exit_code_1 ^ exit_code_2);
                        if (hamming_distance(exit_code_1 ^ exit_code_2) > 1) begin
                            $display("[SVA-ERROR][ch-3][MULTI-BIT] 多比特 SEU 检测: Hamming=%0d > 1, mask=%b",
                                     hamming_distance(exit_code_1 ^ exit_code_2), exit_code_1 ^ exit_code_2);
                        end
                    end

                    // ---- ch-4: mmio_out.print_valid ----
                    if (!(print_valid_1 === print_valid_2 && print_valid_2 === print_valid_3)) begin
                        error_count_ch4 <= error_count_ch4 + 1;
                        $display("[SVA-ERROR][ch-4] mmio_out.print_valid fail @t=%0t: core1=%b core2=%b core3=%b", $time, print_valid_1, print_valid_2, print_valid_3);
                    end

                    // ---- ch-5: mmio_out.print_data (含差异位掩码 + 多比特翻转检测) ----
                    if (!(print_data_1 === print_data_2 && print_data_2 === print_data_3)) begin
                        error_count_ch5 <= error_count_ch5 + 1;
                        $display("[SVA-ERROR][ch-5] mmio_out.print_data fail @t=%0t: core1=%h core2=%h core3=%h diff_mask=%b", $time, print_data_1, print_data_2, print_data_3, print_data_1 ^ print_data_2);
                        if (hamming_distance(print_data_1 ^ print_data_2) > 1) begin
                            $display("[SVA-ERROR][ch-5][MULTI-BIT] 多比特 SEU 检测: Hamming=%0d > 1",
                                     hamming_distance(print_data_1 ^ print_data_2));
                        end
                    end

                    // ---- 阈值告警: 每 256 周期检查错误率 ----
                    if (total_clock_cycles > 100 && total_clock_cycles[7:0] == 0) begin
                        if (error_count_ch0 > (total_clock_cycles >> 7))
                            $display("[SVA-ERROR][ALERT] ch-0 错误率超过 1%%! count=%0d/%0d", error_count_ch0, total_clock_cycles);
                        if (error_count_ch1 > (total_clock_cycles >> 7))
                            $display("[SVA-ERROR][ALERT] ch-1 错误率超过 1%%! count=%0d/%0d", error_count_ch1, total_clock_cycles);
                        if (error_count_ch2 > (total_clock_cycles >> 7))
                            $display("[SVA-ERROR][ALERT] ch-2 错误率超过 1%%! count=%0d/%0d", error_count_ch2, total_clock_cycles);
                        if (error_count_ch3 > (total_clock_cycles >> 7))
                            $display("[SVA-ERROR][ALERT] ch-3 错误率超过 1%%! count=%0d/%0d", error_count_ch3, total_clock_cycles);
                        if (error_count_ch4 > (total_clock_cycles >> 7))
                            $display("[SVA-ERROR][ALERT] ch-4 错误率超过 1%%! count=%0d/%0d", error_count_ch4, total_clock_cycles);
                        if (error_count_ch5 > (total_clock_cycles >> 7))
                            $display("[SVA-ERROR][ALERT] ch-5 错误率超过 1%%! count=%0d/%0d", error_count_ch5, total_clock_cycles);
                    end

                end
            end

        end
    endgenerate

endmodule
