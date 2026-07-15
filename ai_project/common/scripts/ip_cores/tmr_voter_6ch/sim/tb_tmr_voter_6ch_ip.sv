// ============================================================
// tb_tmr_voter_6ch_ip.sv — 6 通道 TMR 表决器 IP 测试台
//
// 功能:
//   - 实例化 tmr_voter_6ch_xilinx
//   - 生成随机测试向量进行功能验证
//   - 自动比较 Majority-3 期望值
//   - 支持 10000 次随机测试
//   - 输出 PASS/FAIL 汇总报告
//
// 运行:
//   - iverilog:  iverilog -g2012 -o tb_ip tb_tmr_voter_6ch_ip.sv ../src/tmr_voter_6ch_xilinx.v
//                vvp tb_ip
//   - Vivado:    xvlog -sv tb_tmr_voter_6ch_ip.sv ../src/tmr_voter_6ch_xilinx.v
//                xelab tb_tmr_voter_6ch_ip -s tb_ip
//                xsim tb_ip
// ============================================================

`timescale 1ns / 1ps

module tb_tmr_voter_6ch_ip;

    // ====== 参数 ======
    parameter int NUM_TESTS = 10000;

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

    // ====== 统计 ======
    integer total, passed, failed;

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

    // ====== 时钟生成 (10 MHz) ======
    initial clk = 0;
    always #50 clk = ~clk;

    // ====== Majority-3 参考函数 ======
    function automatic bit majority_3(input bit a, b, c);
        return (a & b) | (b & c) | (a & c);
    endfunction

    // ====== 测试任务 ======
    task automatic test_1bit_channel(
        input string       ch_name,
        input integer      ch_idx,
        input bit          c1,
        input bit          c2,
        input bit          c3,
        input bit          dut_out
    );
        bit expected;
        expected = majority_3(c1, c2, c3);
        if (dut_out === expected) begin
            $display("PASS: %s | c1=%d c2=%d c3=%d | voted=%d expected=%d",
                     ch_name, c1, c2, c3, dut_out, expected);
            passed = passed + 1;
        end else begin
            $display("FAIL: %s | c1=%d c2=%d c3=%d | voted=%d expected=%d",
                     ch_name, c1, c2, c3, dut_out, expected);
            failed = failed + 1;
        end
        total = total + 1;
    endtask

    task automatic test_vector_channel(
        input string       ch_name,
        input integer      ch_idx,
        input bit    [7:0] c1_byte,
        input bit    [7:0] c2_byte,
        input bit    [7:0] c3_byte,
        input bit    [7:0] dut_byte,
        input integer      width
    );
        bit expected_bit;
        bit dut_bit;
        integer b;
        for (b = 0; b < width; b = b + 1) begin
            expected_bit = majority_3(c1_byte[b], c2_byte[b], c3_byte[b]);
            dut_bit = dut_byte[b];
            if (dut_bit === expected_bit) begin
                passed = passed + 1;
            end else begin
                $display("FAIL: %s[%0d] | c1=%d c2=%d c3=%d | voted=%d expected=%d",
                         ch_name, b, c1_byte[b], c2_byte[b], c3_byte[b], dut_bit, expected_bit);
                failed = failed + 1;
            end
            total = total + 1;
        end
    endtask

    // ====== 主测试流程 ======
    initial begin
        integer i;
        bit [31:0] r1, r2, r3;

        // 初始化
        clk = 0;
        rst_n = 0;
        core1_ready = 0; core2_ready = 0; core3_ready = 0;
        core1_boot_valid = 0; core2_boot_valid = 0; core3_boot_valid = 0;
        core1_exit_valid = 0; core2_exit_valid = 0; core3_exit_valid = 0;
        core1_exit_code = 8'h00; core2_exit_code = 8'h00; core3_exit_code = 8'h00;
        core1_print_valid = 0; core2_print_valid = 0; core3_print_valid = 0;
        core1_print_data = 32'h00000000;
        core2_print_data = 32'h00000000;
        core3_print_data = 32'h00000000;

        total = 0;
        passed = 0;
        failed = 0;

        $display("============================================================");
        $display("TMR 6-Channel Voter IP Testbench");
        $display("  Module: tmr_voter_6ch_xilinx");
        $display("  Tests:  %0d random vectors", NUM_TESTS);
        $display("============================================================");

        // VCD 波形输出
        $dumpfile("tb_tmr_voter_6ch_ip_waveform.vcd");
        $dumpvars(0, tb_tmr_voter_6ch_ip);

        // 复位
        #150;
        rst_n = 1;
        #100;

        // ====== 随机测试循环 ======
        for (i = 0; i < NUM_TESTS; i = i + 1) begin
            @(posedge clk);
            #2;

            // 生成随机测试向量
            r1 = $random;
            r2 = $random;
            r3 = $random;

            // 设置所有通道输入
            core1_ready       = r1[0];
            core2_ready       = r2[0];
            core3_ready       = r3[0];

            core1_boot_valid  = r1[1];
            core2_boot_valid  = r2[1];
            core3_boot_valid  = r3[1];

            core1_exit_valid  = r1[2];
            core2_exit_valid  = r2[2];
            core3_exit_valid  = r3[2];

            core1_exit_code   = r1[15:8];
            core2_exit_code   = r2[15:8];
            core3_exit_code   = r3[15:8];

            core1_print_valid = r1[3];
            core2_print_valid = r2[3];
            core3_print_valid = r3[3];

            core1_print_data  = r1;
            core2_print_data  = r2;
            core3_print_data  = r3;

            #1;  // 等待组合逻辑稳定

            // ---- 检查 ch-0: ready ----
            test_1bit_channel("ch-0 (mmio_in.ready)", 0,
                core1_ready, core2_ready, core3_ready, voted_ready);

            // ---- 检查 ch-1: boot_valid ----
            test_1bit_channel("ch-1 (boot_valid)", 1,
                core1_boot_valid, core2_boot_valid, core3_boot_valid, voted_boot_valid);

            // ---- 检查 ch-2: exit_valid ----
            test_1bit_channel("ch-2 (exit_valid)", 2,
                core1_exit_valid, core2_exit_valid, core3_exit_valid, voted_exit_valid);

            // ---- 检查 ch-3: exit_code (逐位比较) ----
            test_vector_channel("ch-3 (exit_code)", 3,
                core1_exit_code, core2_exit_code, core3_exit_code,
                voted_exit_code, 8);

            // ---- 检查 ch-4: print_valid ----
            test_1bit_channel("ch-4 (print_valid)", 4,
                core1_print_valid, core2_print_valid, core3_print_valid, voted_print_valid);

            // ---- 检查 ch-5: print_data (逐位比较) ----
            test_vector_channel("ch-5 (print_data)", 5,
                core1_print_data[7:0], core2_print_data[7:0], core3_print_data[7:0],
                voted_print_data[7:0], 32);

            // 清除输入 (为下一周期做准备)
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
        end

        // ====== 最终总结 ======
        $display("");
        $display("============================================================");
        $display("SIMULATION SUMMARY");
        $display("============================================================");
        $display("  Total tests: %0d", total);
        $display("  Passed:      %0d", passed);
        $display("  Failed:      %0d", failed);
        $display("  Test vectors: %0d (target: >= 1000)", NUM_TESTS);
        $display("------------------------------------------------------------");

        if (failed == 0) begin
            $display("  RESULT: ALL TESTS PASSED");
        end else begin
            $display("  RESULT: %0d TEST(S) FAILED", failed);
        end
        $display("============================================================");

        repeat (10) @(posedge clk);
        $finish;
    end

endmodule
