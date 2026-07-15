`timescale 1ns/1ps

// 测试 3 种计数器 + SEU 注入
module tb_cnt_comp;

    reg clk, rst_n, en;
    reg [7:0] fault_counter;
    reg fault_inject_en, fault_seen;
    integer pass, fail;

    // 实例化三种计数器
    wire [31:0] up_cnt;
    wire up_err;
    wire [4:0] up_ecnt;
    cnt_comp_up #(.WIDTH(32), .CW(5)) u_up (
        .clk(clk), .rst_n(rst_n), .en(en),
        .counter(up_cnt), .error_flag(up_err), .error_count(up_ecnt)
    );

    wire [31:0] down_cnt;
    wire down_err;
    cnt_comp_down #(.WIDTH(32), .CW(5)) u_down (
        .clk(clk), .rst_n(rst_n), .en(en),
        .counter(down_cnt), .error_flag(down_err)
    );

    wire [7:0] mod_cnt;
    wire mod_err;
    cnt_comp_mod #(.WIDTH(8), .CW(5), .MAX(8'd255)) u_mod (
        .clk(clk), .rst_n(rst_n), .en(en),
        .counter(mod_cnt), .error_flag(mod_err)
    );

    // 时钟
    always #5 clk = ~clk;

    initial begin
        $dumpfile("tb_cnt_comp.vcd");
        $dumpvars(0, tb_cnt_comp);
        
        pass = 0; fail = 0;
        clk = 0; rst_n = 0; en = 0; fault_inject_en = 0;

        // Test 1: 复位后状态
        @(posedge clk); rst_n = 1;
        #20;
        assert(up_cnt == 0) else begin $display("FAIL: up_cnt not reset"); fail++; end
        assert(mod_cnt == 0) else begin $display("FAIL: mod_cnt not reset"); fail++; end
        pass++;
        $display("PASS: Test 1 - Reset");

        // Test 2: 递增计数 10 周期
        en = 1;
        repeat (10) @(posedge clk);
        #1; // 等待非阻塞赋值更新
        assert(up_cnt == 10) else begin $display("FAIL: up_cnt != 10 (got %0d)", up_cnt); fail++; end
        assert(up_err == 0) else begin $display("FAIL: false error"); fail++; end
        pass++;
        $display("PASS: Test 2 - Up count 10 cycles");

        // Test 3: 递减计数 10 周期
        // 注意: en 在三个计数器间共享, Test 2 期间 down 也减了 10 次
        // 初始 FFFFFFFF → Test2 10下 → FFFFFFF5 → Test3 10下 → FFFFFFEB
        en = 0; @(posedge clk);
        #1;
        en = 1;
        repeat (10) @(posedge clk);
        #1; // 等待非阻塞赋值更新
        assert(down_cnt == 32'hFFFFFFEB) else begin $display("FAIL: down_cnt mismatch (got %h)", down_cnt); fail++; end
        pass++;
        $display("PASS: Test 3 - Down count 10 cycles");

        // Test 4: 模计数回零验证
        // 先复位, 确保从 0 开始
        rst_n = 0;
        @(posedge clk);
        #1;
        rst_n = 1;
        en = 1;
        repeat (256) @(posedge clk);
        #1; // 等待非阻塞赋值更新
        assert(mod_cnt == 0) else begin $display("FAIL: mod wrap (got %0d)", mod_cnt); fail++; end
        pass++;
        $display("PASS: Test 4 - Mod wrap-around");

        // Test 5: SEU 注入 (通过 force 翻转 counter)
        en = 0; @(posedge clk);
        #1 force u_up.counter = 32'hDEAD;
        #10 release u_up.counter;
        #1;
        en = 1;
        @(posedge clk);
        #1;
        if (u_up.error_flag) begin
            $display("PASS: Test 5 - SEU detected by cnt_comp");
            pass++;
        end else begin
            $display("FAIL: SEU not detected");
            fail++;
        end

        // Test 6: 复位后长周期稳定性 (1000 周期无误报)
        // SEU 后 counter 和 shadow 永久失步, 需要先复位
        rst_n = 0;
        @(posedge clk);
        #1;
        rst_n = 1;
        en = 1;
        repeat (1000) @(posedge clk);
        #1;
        if (u_up.error_flag == 0 && u_down.error_flag == 0 && u_mod.error_flag == 0) begin
            $display("PASS: Test 6 - 1000 cycle false-alarm free");
            pass++;
        end else begin
            $display("FAIL: False alarm detected (up_err=%b down_err=%b mod_err=%b)",
                     u_up.error_flag, u_down.error_flag, u_mod.error_flag);
            fail++;
        end

        // 结果
        $display("====================================");
        $display("cnt_comp Tests: %0d PASS, %0d FAIL", pass, fail);
        $display("====================================");
        $finish;
    end

endmodule
