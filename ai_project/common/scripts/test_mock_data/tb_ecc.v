`timescale 1ns/1ps
// ECC (SECDED) 测试台 — 覆盖编码/解码/单纠错/双检错/100周期稳定
module tb_ecc;
    reg clk, rst_n, en;
    reg [7:0] din;
    wire [7:0] q;
    wire err_flag, corrected;
    integer pass, fail, i;

    localparam W = 8;
    localparam P = 3;  // clog2(8) = 3 Hamming bits
    localparam CW = W + P + 1;  // +1 global parity = 12

    ecc_register #(.WIDTH(W)) u_dut (
        .clk(clk), .rst_n(rst_n), .en(en),
        .d(din), .q(q), .error_flag(err_flag), .corrected(corrected)
    );

    always #5 clk = ~clk;

    task write_val(input [7:0] val);
        begin
            // 用 NBA 写入, 与 DUT always_ff 同步
            @(negedge clk);
            din <= val; en <= 1;
            @(negedge clk);
            en <= 0;
            @(posedge clk);  // 等待 ECC 解码稳定
            #1;
        end
    endtask

    initial begin
        $dumpfile("tb_ecc.vcd");
        $dumpvars(0, tb_ecc);
        pass = 0; fail = 0;
        clk = 0; rst_n = 0; en = 0; din = 0;

        // Test 1: 复位
        @(posedge clk); rst_n = 1; #1;
        if (q === 8'h00) begin
            pass++; $display("PASS: Test 1 - Reset (q=%h)", q);
        end else begin
            fail++; $display("FAIL: Test 1 - Reset (q=%h)", q);
        end

        // Test 2: 写入 + 读取
        write_val(8'hA5);
        if (q === 8'hA5) begin
            pass++; $display("PASS: Test 2 - Write/Read 0xA5 (q=%h)", q);
        end else begin
            fail++; $display("FAIL: Test 2 - Write/Read 0xA5 (q=%h)", q);
        end

        write_val(8'h5A);
        if (q === 8'h5A) begin
            pass++; $display("PASS: Test 2 - Write/Read 0x5A (q=%h)", q);
        end else begin
            fail++; $display("FAIL: Test 2 - Write/Read 0x5A (q=%h)", q);
        end

        // Test 3: 单比特 SEU — ECC 应自动纠正
        write_val(8'hFF);
        @(posedge clk); #1;
        // force 翻转 bit-2: 应触发 corrected, q 仍为 0xFF
        force u_dut.code_reg[2] = ~u_dut.code_reg[2];
        #15; @(posedge clk); #1;
        if (corrected && q === 8'hFF) begin
            pass++; $display("PASS: Test 3 - Single-bit SEU corrected (q=%h, corrected=%b)", q, corrected);
        end else begin
            fail++; $display("FAIL: Test 3 - Single-bit SEU (q=%h, corrected=%b)", q, corrected);
        end
        release u_dut.code_reg[2];

        // Test 4: 写入恢复
        write_val(8'h00);
        if (q === 8'h00) begin
            pass++; $display("PASS: Test 4 - Recovery (q=%h)", q);
        end else begin
            fail++; $display("FAIL: Test 4 - Recovery (q=%h)", q);
        end

        // Test 5: 双比特 SEU — 应触发 error_flag (DED)
        write_val(8'h55);
        @(posedge clk); #1;
        force u_dut.code_reg[0] = ~u_dut.code_reg[0];
        force u_dut.code_reg[3] = ~u_dut.code_reg[3];
        #15; @(posedge clk); #1;
        if (err_flag) begin
            pass++; $display("PASS: Test 5 - Double-bit SEU detected (err=%b)", err_flag);
        end else begin
            fail++; $display("FAIL: Test 5 - Double-bit SEU NOT detected (err=%b)", err_flag);
        end
        release u_dut.code_reg[0];
        release u_dut.code_reg[3];

        // Test 6: 写入恢复
        write_val(8'hAA);
        if (q === 8'hAA) begin
            pass++; $display("PASS: Test 6 - Recovery (q=%h)", q);
        end else begin
            fail++; $display("FAIL: Test 6 - Recovery (q=%h)", q);
        end

        // Test 7: 100 周期无误报 & 无错误纠正
        write_val(8'hA5);
        repeat (100) @(posedge clk); #1;
        if (!err_flag && !corrected) begin
            pass++; $display("PASS: Test 7 - 100 cycles no errors (err=%b, corrected=%b)", err_flag, corrected);
        end else begin
            fail++; $display("FAIL: Test 7 - False error (err=%b, corrected=%b)", err_flag, corrected);
        end

        // Test 8: 全 256 模式遍历验证编码/解码正确
        for (i = 0; i < 256; i = i + 1) begin
            write_val(i);
            if (q !== i[7:0]) begin
                fail++; $display("FAIL: Test 8 - Pattern %0d (q=%h)", i, q);
            end else if (err_flag || corrected) begin
                fail++; $display("FAIL: Test 8 - False flag at pattern %0d", i);
            end else begin
                pass++;
            end
        end

        // Test 9: 校验位 SEU (syndrome 指出错误在校验位)
        write_val(8'hFF);
        @(posedge clk); #1;
        // force 翻转一个校验位 (高位 MSB of code_reg)
        force u_dut.code_reg[CW-1] = ~u_dut.code_reg[CW-1];
        #15; @(posedge clk); #1;
        // 校验位错误: q 应保持正确, corrected 取决于实现
        if (q === 8'hFF) begin
            pass++; $display("PASS: Test 9 - Parity-bit SEU, data intact (q=%h)", q);
        end else begin
            fail++; $display("FAIL: Test 9 - Parity-bit SEU corrupted data (q=%h)", q);
        end
        release u_dut.code_reg[CW-1];

        // ============================================
        // 最终结果
        // ============================================
        $display("==========================================");
        $display("ECC Tests: %0d PASS, %0d FAIL", pass, fail);
        $display("==========================================");
        if (fail == 0) $display("ALL TESTS PASSED");
        $finish;
    end
endmodule
