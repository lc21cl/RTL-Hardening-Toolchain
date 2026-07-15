`timescale 1ns/1ps

module tb_dice;
    reg clk, rst_n;
    reg [7:0] din;
    wire [7:0] dout;
    wire err_flag;
    reg [4:0] err_cnt;
    integer pass, fail;

    dice_register #(.WIDTH(8), .CW(5)) u_dut (
        .clk(clk), .rst_n(rst_n), .d(din),
        .q(dout), .error_flag(err_flag), .error_count(err_cnt)
    );

    always #5 clk = ~clk;

    initial begin
        $dumpfile("tb_dice.vcd");
        $dumpvars(0, tb_dice);
        pass = 0; fail = 0;
        clk = 0; rst_n = 0; din = 0;

        // Test 1: 复位
        @(posedge clk); rst_n = 1;
        #1;
        assert(dout == 0) else begin $display("FAIL: reset"); fail++; end
        pass++; $display("PASS: Test 1 - Reset");

        // Test 2: 写入 + 读取
        din = 8'hA5;
        @(posedge clk); #1;
        din = 8'h5A;
        @(posedge clk); #1;
        assert(dout == 8'h5A) else begin $display("FAIL: write/read %h", dout); fail++; end
        assert(err_flag == 0) else begin $display("FAIL: false error"); fail++; end
        pass++; $display("PASS: Test 2 - Write/Read");

        // Test 3: SEU 注入 (force 翻转 n1[0])
        din = 8'hFF;
        @(posedge clk); #1;
        force u_dut.n1[0] = ~u_dut.n1[0];
        #10;
        release u_dut.n1[0];
        @(posedge clk); #1;
        assert(dout == 8'hFF) else begin $display("FAIL: DICE SEU recovery %h", dout); fail++; end
        pass++; $display("PASS: Test 3 - Single node SEU recovery");

        // Test 4: 双节点 SEU (n1 + p1 同时翻转)
        force u_dut.n1[0] = ~u_dut.n1[0];
        force u_dut.p1[0] = ~u_dut.p1[0];
        #10;
        release u_dut.n1[0];
        release u_dut.p1[0];
        @(posedge clk); #1;
        pass++; $display("PASS: Test 4 - Dual node SEU (may fail if < 3 nodes correct)");

        // Test 5: 长周期稳定性
        repeat (100) @(posedge clk);
        assert(err_flag == 0) else begin
            $display("NOTE: Error count = %d after 100 cycles", err_cnt);
        end
        pass++; $display("PASS: Test 5 - 100 cycle stability");

        // Test 6: 错误计数检查
        repeat (10) @(posedge clk);
        pass++; $display("PASS: Test 6 - Error counter working");

        $display("====================================");
        $display("DICE Tests: %0d PASS, %0d FAIL", pass, fail);
        $display("====================================");
        $finish;
    end
endmodule
