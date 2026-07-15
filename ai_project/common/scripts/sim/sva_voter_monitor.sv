// ================================================================
// sva_voter_monitor.sv — 6 通道 SVA 断言模块 (含多比特翻转防御)
//
// 功能: 使用 SystemVerilog Assertion (SVA) 实时监控 3 个核心
//       的接口输出一致性, 在 SEU 注入时立即触发断言失败
//
// 每个表决器通道使用独立的 assert property:
//   - 单比特信号 (ch-0,1,2,4): 直接相等比较
//   - 多比特信号 (ch-3,5):    逐比特相等比较, 含差异位信息 + Hamming 距离
//   - 多比特 SEU 告警:        当 Hamming 距离 > 1 时额外触发 MULTI-BIT
//
// 仿真:
//   vsim -G/ENABLE_SVA=1 work.tb_sva_voter
//
// 形式化验证:
//   sby -f sva_voter.sby    # 使用 SymbiYosys 穷举证明
// ================================================================

`timescale 1ns / 1ps

module sva_voter_monitor (
    input logic clk,
    input logic rst_n,

    // ch-0: mmio_in.ready (3 个核心, 1-bit)
    input logic ready_1, ready_2, ready_3,

    // ch-1: mmio_out.boot_valid (3 个核心, 1-bit)
    input logic boot_valid_1, boot_valid_2, boot_valid_3,

    // ch-2: mmio_out.exit_valid (3 个核心, 1-bit)
    input logic exit_valid_1, exit_valid_2, exit_valid_3,

    // ch-3: mmio_out.exit_code (3 个核心, 8-bit)
    input logic [7:0] exit_code_1, exit_code_2, exit_code_3,

    // ch-4: mmio_out.print_valid (3 个核心, 1-bit)
    input logic print_valid_1, print_valid_2, print_valid_3,

    // ch-5: mmio_out.print_data (3 个核心, 32-bit)
    input logic [31:0] print_data_1, print_data_2, print_data_3
);

    // ================================================================
    // SVA 断言使能: 通过参数控制
    // ================================================================
    parameter ENABLE_SVA = 1;

    // 辅助函数: 计算 Hamming 距离 ($countones 的纯 Verilog 实现)
    function automatic integer hamming_distance(input [31:0] x);
        integer cnt, i;
        begin
            cnt = 0;
            for (i = 0; i < 32; i = i + 1) begin
                if (x[i]) cnt = cnt + 1;
            end
            hamming_distance = cnt;
        end
    endfunction

    generate
        if (ENABLE_SVA) begin : sva_assertions

            // ============================================================
            // ch-0: mmio_in.ready — 3 个核心的 ready 必须一致
            //        应用场景: 输入接口反馈信号, 影响 next-cycle 数据流
            // ============================================================
            assert property (@(posedge clk)
                disable iff (!rst_n)
                (ready_1 == ready_2) && (ready_2 == ready_3)
            ) else begin
                $error("[SVA-VOTER][ch-0] mmio_in.ready 断言失败 @t=%0t: "
                       "core1=%b core2=%b core3=%b",
                       $time, ready_1, ready_2, ready_3);
            end

            // ============================================================
            // ch-1: mmio_out.boot_valid — 3 个核心的输出 BOOT 信号一致
            //        应用场景: 上电启动序列 (boot)
            // ============================================================
            assert property (@(posedge clk)
                disable iff (!rst_n)
                (boot_valid_1 == boot_valid_2) && (boot_valid_2 == boot_valid_3)
            ) else begin
                $error("[SVA-VOTER][ch-1] mmio_out.boot_valid 断言失败 @t=%0t: "
                       "core1=%b core2=%b core3=%b",
                       $time, boot_valid_1, boot_valid_2, boot_valid_3);
            end

            // ============================================================
            // ch-2: mmio_out.exit_valid — 3 个核心的程序退出信号一致
            //        应用场景: 程序终止/exit 事件
            // ============================================================
            assert property (@(posedge clk)
                disable iff (!rst_n)
                (exit_valid_1 == exit_valid_2) && (exit_valid_2 == exit_valid_3)
            ) else begin
                $error("[SVA-VOTER][ch-2] mmio_out.exit_valid 断言失败 @t=%0t: "
                       "core1=%b core2=%b core3=%b",
                       $time, exit_valid_1, exit_valid_2, exit_valid_3);
            end

            // ============================================================
            // ch-3: mmio_out.exit_code — 3 个核心的退出码逐比特一致
            //        应用场景: 程序返回值, 8-bit 错误码
            //        多比特防御: Hamming 距离 > 1 触发 MULTI-BIT 告警
            // ============================================================
            assert property (@(posedge clk)
                disable iff (!rst_n)
                (exit_code_1 == exit_code_2) && (exit_code_2 == exit_code_3)
            ) else begin
                $error("[SVA-VOTER][ch-3] mmio_out.exit_code 断言失败 @t=%0t: "
                       "core1=%h core2=%h core3=%h 差异位=%b",
                       $time, exit_code_1, exit_code_2, exit_code_3,
                       exit_code_1 ^ exit_code_2);
                // 多比特翻转防御: 检查 Hamming 距离
                if (hamming_distance(exit_code_1 ^ exit_code_2) > 1) begin
                    $error("[SVA-VOTER][ch-3][MULTI-BIT] 多比特 SEU 检测: Hamming=%0d > 1",
                           hamming_distance(exit_code_1 ^ exit_code_2));
                end
            end

            // ============================================================
            // ch-4: mmio_out.print_valid — 3 个核心的打印使能信号一致
            //        应用场景: 串口/UART 打印使能
            // ============================================================
            assert property (@(posedge clk)
                disable iff (!rst_n)
                (print_valid_1 == print_valid_2) && (print_valid_2 == print_valid_3)
            ) else begin
                $error("[SVA-VOTER][ch-4] mmio_out.print_valid 断言失败 @t=%0t: "
                       "core1=%b core2=%b core3=%b",
                       $time, print_valid_1, print_valid_2, print_valid_3);
            end

            // ============================================================
            // ch-5: mmio_out.print_data — 3 个核心的打印数据逐比特一致
            //        应用场景: 串口/UART 打印数据, 32-bit
            //        多比特防御: Hamming 距离 > 1 触发 MULTI-BIT 告警
            // ============================================================
            assert property (@(posedge clk)
                disable iff (!rst_n)
                (print_data_1 == print_data_2) && (print_data_2 == print_data_3)
            ) else begin
                $error("[SVA-VOTER][ch-5] mmio_out.print_data 断言失败 @t=%0t: "
                       "core1=%h core2=%h core3=%h 差异位=%b",
                       $time, print_data_1, print_data_2, print_data_3,
                       print_data_1 ^ print_data_2);
                // 多比特翻转防御: 检查 Hamming 距离
                if (hamming_distance(print_data_1 ^ print_data_2) > 1) begin
                    $error("[SVA-VOTER][ch-5][MULTI-BIT] 多比特 SEU 检测: Hamming=%0d > 1",
                           hamming_distance(print_data_1 ^ print_data_2));
                end
            end

            // ============================================================
            // [SUMMARY] 全局统计: 当任一通道断言失败时记录
            // 使用 cover property 统计每个通道的失败次数
            // ============================================================
            cover property (@(posedge clk)
                (ready_1 !== ready_2 || ready_2 !== ready_3)
            );

            cover property (@(posedge clk)
                (boot_valid_1 !== boot_valid_2 || boot_valid_2 !== boot_valid_3)
            );

            cover property (@(posedge clk)
                (print_data_1 !== print_data_2 || print_data_2 !== print_data_3)
            );

        end
    endgenerate

endmodule : sva_voter_monitor
