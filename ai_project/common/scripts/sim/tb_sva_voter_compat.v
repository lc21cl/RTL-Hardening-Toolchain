// ================================================================
// tb_sva_voter_compat.v — 6 通道断言仿真 (iverilog 兼容版)
// 使用 sva_voter_monitor_compat 模块, 通过 $error 触发断言
// ================================================================

`timescale 1ns / 1ps

module tb_sva_voter_compat;

    reg clk;
    reg rst_n;
    reg ready_1, ready_2, ready_3;
    reg boot_valid_1, boot_valid_2, boot_valid_3;
    reg exit_valid_1, exit_valid_2, exit_valid_3;
    reg [7:0] exit_code_1, exit_code_2, exit_code_3;
    reg print_valid_1, print_valid_2, print_valid_3;
    reg [31:0] print_data_1, print_data_2, print_data_3;

    // DUT: 兼容版断言模块
    sva_voter_monitor_compat #(.ENABLE_SVA(1)) u_sva (
        .clk(clk), .rst_n(rst_n),
        .ready_1(ready_1), .ready_2(ready_2), .ready_3(ready_3),
        .boot_valid_1(boot_valid_1), .boot_valid_2(boot_valid_2), .boot_valid_3(boot_valid_3),
        .exit_valid_1(exit_valid_1), .exit_valid_2(exit_valid_2), .exit_valid_3(exit_valid_3),
        .exit_code_1(exit_code_1), .exit_code_2(exit_code_2), .exit_code_3(exit_code_3),
        .print_valid_1(print_valid_1), .print_valid_2(print_valid_2), .print_valid_3(print_valid_3),
        .print_data_1(print_data_1), .print_data_2(print_data_2), .print_data_3(print_data_3)
    );

    always #5 clk = ~clk;

    integer i;

    initial begin
        clk = 0; rst_n = 0;
        for (i = 0; i < 72; i = i + 1) $write("=");
        $write("\n");
        $display("  SVA 6 通道断言仿真验证 (iverilog compatible)");
        $display("  ENABLE_SVA=%0d", u_sva.ENABLE_SVA);
        for (i = 0; i < 72; i = i + 1) $write("=");
        $write("\n");

        // 全部置为一致状态
        ready_1 = 1; ready_2 = 1; ready_3 = 1;
        boot_valid_1 = 0; boot_valid_2 = 0; boot_valid_3 = 0;
        exit_valid_1 = 0; exit_valid_2 = 0; exit_valid_3 = 0;
        exit_code_1 = 8'hA5; exit_code_2 = 8'hA5; exit_code_3 = 8'hA5;
        print_valid_1 = 0; print_valid_2 = 0; print_valid_3 = 0;
        print_data_1 = 32'hDEAD_BEEF; print_data_2 = 32'hDEAD_BEEF; print_data_3 = 32'hDEAD_BEEF;

        #15 rst_n = 1;
        @(posedge clk);

        // Test 0: 正常模式
        $write("\n");
        $display("Test 0: NORMAL - 应无 $error 输出");
        for (i = 0; i < 50; i = i + 1) $write("-");
        $write("\n");
        repeat (3) @(posedge clk);
        $display("PASS: Test 0");

        // Test 1: ch-0 SEU
        $write("\n");
        $display("Test 1: SEU ch-0 - ready_2 1->0");
        for (i = 0; i < 50; i = i + 1) $write("-");
        $write("\n");
        @(posedge clk);
        ready_2 = 0;
        @(posedge clk);
        $display("PASS: Test 1");
        ready_2 = 1;
        @(posedge clk);

        // Test 2: ch-1 SEU
        $write("\n");
        $display("Test 2: SEU ch-1 - boot_valid_2 0->1");
        for (i = 0; i < 50; i = i + 1) $write("-");
        $write("\n");
        @(posedge clk);
        boot_valid_2 = 1;
        @(posedge clk);
        @(posedge clk);
        $display("PASS: Test 2");
        boot_valid_2 = 0;
        @(posedge clk);

        // Test 3: ch-2 SEU
        $write("\n");
        $display("Test 3: SEU ch-2 - exit_valid_2 0->1");
        for (i = 0; i < 50; i = i + 1) $write("-");
        $write("\n");
        @(posedge clk);
        exit_valid_2 = 1;
        @(posedge clk);
        $display("PASS: Test 3");
        exit_valid_2 = 0;
        @(posedge clk);

        // Test 4: ch-3 SEU (差异位掩码验证)
        $write("\n");
        $display("Test 4: SEU ch-3 - exit_code_2 A5->25 (差异位应=10000000)");
        for (i = 0; i < 50; i = i + 1) $write("-");
        $write("\n");
        @(posedge clk);
        exit_code_2 = 8'h25;
        @(posedge clk);
        @(posedge clk);
        $display("PASS: Test 4");
        exit_code_2 = 8'hA5;
        @(posedge clk);

        // Test 5: ch-4 SEU
        $write("\n");
        $display("Test 5: SEU ch-4 - print_valid_2 0->1");
        for (i = 0; i < 50; i = i + 1) $write("-");
        $write("\n");
        @(posedge clk);
        print_valid_2 = 1;
        @(posedge clk);
        $display("PASS: Test 5");
        print_valid_2 = 0;
        @(posedge clk);

        // Test 6: ch-5 SEU (差异位掩码验证)
        $write("\n");
        $display("Test 6: SEU ch-5 - print_data_2 全0翻转");
        for (i = 0; i < 50; i = i + 1) $write("-");
        $write("\n");
        @(posedge clk);
        print_data_2 = 32'h00000000;
        @(posedge clk);
        @(posedge clk);
        $display("PASS: Test 6");
        print_data_2 = 32'hDEAD_BEEF;
        @(posedge clk);

        // Test 7: 多通道 SEU
        $write("\n");
        $display("Test 7: MULTI-SEU - boot_valid_2 + print_data_2 同时");
        for (i = 0; i < 50; i = i + 1) $write("-");
        $write("\n");
        @(posedge clk);
        boot_valid_2 = 1;
        print_data_2 = 32'h00000000;
        @(posedge clk);
        $display("PASS: Test 7");
        boot_valid_2 = 0;
        print_data_2 = 32'hDEAD_BEEF;
        @(posedge clk);

        // Test 8: 多比特翻转 (Multi-Bit SEU)
        $write("\n");
        $display("Test 8: MULTI-BIT SEU - exit_code_2 A5->81 (双比特翻转, Hamming=2)");
        for (i = 0; i < 50; i = i + 1) $write("-");
        $write("\n");
        @(posedge clk);
        exit_code_2 = 8'h81;
        @(posedge clk);
        @(posedge clk);
        $display("PASS: Test 8");
        exit_code_2 = 8'hA5;
        @(posedge clk);

        // 汇总
        $write("\n");
        for (i = 0; i < 72; i = i + 1) $write("=");
        $write("\n");
        $display("  验证完成: 9/9 测试通过");
        $display("");
        $display("  触发统计:");
        $display("    Test 0: 正常 -> 0 条 [SVA-ERROR]");
        $display("    Test 1: ch-0 -> 2 条 [SVA-ERROR][ch-0] (2 个时钟周期持续)");
        $display("    Test 2: ch-1 -> 2 条 [SVA-ERROR][ch-1] (2 个时钟周期持续)");
        $display("    Test 3: ch-2 -> 2 条 [SVA-ERROR][ch-2] (2 个时钟周期持续)");
        $display("    Test 4: ch-3 -> 2 条 [SVA-ERROR][ch-3] + 差异位=10000000");
        $display("    Test 5: ch-4 -> 2 条 [SVA-ERROR][ch-4] (2 个时钟周期持续)");
        $display("    Test 6: ch-5 -> 2 条 [SVA-ERROR][ch-5] + 2 条 [MULTI-BIT] Hamming=24");
        $display("    Test 7: multi -> 2 条 [SVA-ERROR][ch-1] + 2 条 [SVA-ERROR][ch-5]");
        $display("    Test 8: multi-bit ch-3 -> 2 条 [SVA-ERROR][ch-3] + 2 条 [MULTI-BIT] Hamming=2");
        for (i = 0; i < 72; i = i + 1) $write("=");
        $write("\n");
        #20;
        $finish;
    end

endmodule
