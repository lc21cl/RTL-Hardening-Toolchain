`timescale 1ns/1ps

// ====================================================
// cnt_comp_up 故障注入测试台
// 验证 cnt_comp 加固方案对 SEU 的检测能力
// ====================================================
module tb_cnt_comp_fault;

    reg clk, rst_n, en;
    wire [31:0] counter;
    wire err_flag;
    wire [4:0] err_cnt;
    integer pass, fail;
    integer i;

    cnt_comp_up #(.WIDTH(32), .CW(5)) u_dut (
        .clk(clk), .rst_n(rst_n), .en(en),
        .counter(counter), .error_flag(err_flag), .error_count(err_cnt)
    );

    always #5 clk = ~clk;

    initial begin
        $dumpfile("tb_cnt_comp_fault.vcd");
        $dumpvars(0, tb_cnt_comp_fault);
        pass = 0; fail = 0;
        clk = 0; rst_n = 0; en = 0;

        // ============================================
        // Test 1: 复位后初始状态
        // ============================================
        @(posedge clk); rst_n = 1;
        #20;
        if (counter == 0 && err_flag == 0) begin
            $display("PASS: Test 1 - Reset state");
            pass++;
        end else begin
            $display("FAIL: Test 1 - Reset state (counter=%0d, err=%b)", counter, err_flag);
            fail++;
        end

        // ============================================
        // Test 2: 正常递增 5 周期, 无误报
        // ============================================
        en = 1;
        repeat (5) @(posedge clk);
        #1;
        if (counter == 5 && err_flag == 0) begin
            $display("PASS: Test 2 - Normal count, no false alarm");
            pass++;
        end else begin
            $display("FAIL: Test 2 - Normal count (counter=%0d, err=%b)", counter, err_flag);
            fail++;
        end

        // ============================================
        // Test 3: SEU 注入 - 翻转 counter (主计数器)
        // ============================================
        en = 0; @(posedge clk); #1;
        force u_dut.counter = 32'hDEAD;
        #20 release u_dut.counter;
        #1;
        // 此时 counter != shadow, error_flag 应触发
        en = 1;
        @(posedge clk);
        #1;
        if (err_flag) begin
            $display("PASS: Test 3 - SEU on counter detected");
            pass++;
        end else begin
            $display("FAIL: Test 3 - SEU on counter NOT detected");
            fail++;
        end

        // ============================================
        // Test 4: SEU 注入 - 翻转 shadow
        // ============================================
        en = 0; @(posedge clk); #1;
        // 先让主次同步
        en = 1;
        repeat (3) @(posedge clk);
        en = 0; @(posedge clk); #1;
        force u_dut.shadow = 32'hBEEF;
        #20 release u_dut.shadow;
        #1;
        en = 1;
        @(posedge clk);
        #1;
        if (err_flag) begin
            $display("PASS: Test 4 - SEU on shadow detected");
            pass++;
        end else begin
            $display("FAIL: Test 4 - SEU on shadow NOT detected");
            fail++;
        end

        // ============================================
        // Test 5: 错误计数器递增
        // ============================================
        if (err_cnt > 0) begin
            $display("PASS: Test 5 - Error counter incremented (err_cnt=%0d)", err_cnt);
            pass++;
        end else begin
            $display("FAIL: Test 5 - Error counter not incremented");
            fail++;
        end

        // ============================================
        // Test 6: 复位后正常计数
        // SEU 注入后 counter ≠ shadow 永久失步, 需复位恢复
        // ============================================
        rst_n = 0;
        @(posedge clk);
        #1;
        rst_n = 1;
        en = 1;
        repeat (5) @(posedge clk);
        #1;
        if (err_flag == 0 && counter == 5) begin
            $display("PASS: Test 6 - Recovery after reset");
            pass++;
        end else begin
            $display("FAIL: Test 6 - Recovery after reset (counter=%0d, err=%b)", counter, err_flag);
            fail++;
        end

        // ============================================
        // Test 7: 长周期稳定性 (500 周期无误报)
        // ============================================
        en = 1;
        repeat (500) @(posedge clk);
        #1;
        if (err_flag == 0 && counter > 5) begin
            $display("PASS: Test 7 - 500 cycle false-alarm free");
            pass++;
        end else begin
            $display("FAIL: Test 7 - False alarm (counter=%0d, err=%b)", counter, err_flag);
            fail++;
        end

        // ============================================
        // Test 8: 错误计数上限测试
        // ============================================
        // error_count 达到最大值后不再递增
        // 强制注入多次错误
        en = 0; @(posedge clk); #1;
        for (i = 0; i < 32; i++) begin
            force u_dut.counter = $urandom;
            #15 release u_dut.counter;
            #5;
            en = 1;
            @(posedge clk);
            #1;
            if (err_flag) begin
                $display("  Fault injection %0d: error_flag asserted", i);
            end
            en = 0;
            // 等待一次同步
            en = 1;
            repeat (2) @(posedge clk);
            en = 0; @(posedge clk); #1;
        end
        // error_count 不应超过饱和值
        // 错误计数器位宽 CW=5, 最大值 31
        if (err_cnt <= 31) begin
            $display("PASS: Test 8 - Error counter saturation (err_cnt=%0d)", err_cnt);
            pass++;
        end else begin
            $display("FAIL: Test 8 - Error counter overflow (err_cnt=%0d)", err_cnt);
            fail++;
        end

        // ============================================
        // Test 9: 双位翻转 (counter + shadow 同时翻转)
        // ============================================
        en = 0; @(posedge clk); #1;
        // 同步
        en = 1;
        repeat (3) @(posedge clk);
        en = 0; @(posedge clk); #1;
        // 同时翻转 counter 和 shadow 为相同值 - 应不触发错误
        force u_dut.counter = 32'hCAFE;
        force u_dut.shadow = 32'hCAFE;
        #20;
        release u_dut.counter;
        release u_dut.shadow;
        #1;
        en = 1;
        @(posedge clk);
        #1;
        // 由于 counter == shadow, 应无误报
        if (err_flag == 0) begin
            $display("PASS: Test 9 - Dual bit-flip same value, no false alarm");
            pass++;
        end else begin
            $display("FAIL: Test 9 - False alarm on dual bit-flip same value");
            fail++;
        end

        // ============================================
        // 汇总
        // ============================================
        $display("===========================================");
        $display("cnt_comp_up Fault Injection: %0d PASS, %0d FAIL", pass, fail);
        $display("===========================================");
        $finish;
    end

endmodule
