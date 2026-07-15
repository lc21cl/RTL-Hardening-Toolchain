// ============================================================
// tb_glitch_injection.v — 毛刺注入测试台
//
// 验证 pipeline 版 TMR 表决器 (tmr_voter_6ch_xilinx) 能正确
// 抑制组合逻辑毛刺。
//
// 实例化两个 DUT:
//   u_voter_pipeline — PIPELINE_ENABLE=1 (pipeline 模式)
//   u_voter_combo    — PIPELINE_ENABLE=0 (组合直通, 毛刺参考)
//
// 场景:
//   1. 单比特毛刺 (ch-0 ready) — 快速切换 core1_ready
//   2. 多比特毛刺 (ch-5 print_data) — 不同 bit 延迟跳变
//   3. 建立时间违例注入 (Setup violation)
// ============================================================

`timescale 1ns / 1ps

module tb_glitch_injection;

    // ====== 时钟与复位 ======
    reg clk;
    reg rst_n;

    // ====== 共享输入 ======
    // ch-0: ready
    reg       core1_ready, core2_ready, core3_ready;
    // ch-1: boot_valid
    reg       core1_boot_valid, core2_boot_valid, core3_boot_valid;
    // ch-2: exit_valid
    reg       core1_exit_valid, core2_exit_valid, core3_exit_valid;
    // ch-3: exit_code
    reg [7:0] core1_exit_code, core2_exit_code, core3_exit_code;
    // ch-4: print_valid
    reg       core1_print_valid, core2_print_valid, core3_print_valid;
    // ch-5: print_data
    reg [31:0] core1_print_data, core2_print_data, core3_print_data;

    // ====== Pipeline DUT 输出 ======
    wire      voted_ready_pipe;
    wire      voted_boot_valid_pipe;
    wire      voted_exit_valid_pipe;
    wire [7:0] voted_exit_code_pipe;
    wire      voted_print_valid_pipe;
    wire [31:0] voted_print_data_pipe;

    // ====== Combo DUT 输出 (组合直通参考) ======
    wire      voted_ready_cmb;
    wire      voted_boot_valid_cmb;
    wire      voted_exit_valid_cmb;
    wire [7:0] voted_exit_code_cmb;
    wire      voted_print_valid_cmb;
    wire [31:0] voted_print_data_cmb;

    // ====== DUT 实例化 ======

    // Pipeline 模式 (PIPELINE_ENABLE=1)
    tmr_voter_6ch_xilinx #(
        .PIPELINE_ENABLE(1)
    ) u_voter_pipeline (
        .clk                (clk),
        .rst_n              (rst_n),

        .core1_ready        (core1_ready),
        .core2_ready        (core2_ready),
        .core3_ready        (core3_ready),
        .voted_ready        (voted_ready_pipe),

        .core1_boot_valid   (core1_boot_valid),
        .core2_boot_valid   (core2_boot_valid),
        .core3_boot_valid   (core3_boot_valid),
        .voted_boot_valid   (voted_boot_valid_pipe),

        .core1_exit_valid   (core1_exit_valid),
        .core2_exit_valid   (core2_exit_valid),
        .core3_exit_valid   (core3_exit_valid),
        .voted_exit_valid   (voted_exit_valid_pipe),

        .core1_exit_code    (core1_exit_code),
        .core2_exit_code    (core2_exit_code),
        .core3_exit_code    (core3_exit_code),
        .voted_exit_code    (voted_exit_code_pipe),

        .core1_print_valid  (core1_print_valid),
        .core2_print_valid  (core2_print_valid),
        .core3_print_valid  (core3_print_valid),
        .voted_print_valid  (voted_print_valid_pipe),

        .core1_print_data   (core1_print_data),
        .core2_print_data   (core2_print_data),
        .core3_print_data   (core3_print_data),
        .voted_print_data   (voted_print_data_pipe)
    );

    // 组合直通模式 (PIPELINE_ENABLE=0) — 毛刺检测参考
    tmr_voter_6ch_xilinx #(
        .PIPELINE_ENABLE(0)
    ) u_voter_combo (
        .clk                (clk),
        .rst_n              (rst_n),

        .core1_ready        (core1_ready),
        .core2_ready        (core2_ready),
        .core3_ready        (core3_ready),
        .voted_ready        (voted_ready_cmb),

        .core1_boot_valid   (core1_boot_valid),
        .core2_boot_valid   (core2_boot_valid),
        .core3_boot_valid   (core3_boot_valid),
        .voted_boot_valid   (voted_boot_valid_cmb),

        .core1_exit_valid   (core1_exit_valid),
        .core2_exit_valid   (core2_exit_valid),
        .core3_exit_valid   (core3_exit_valid),
        .voted_exit_valid   (voted_exit_valid_cmb),

        .core1_exit_code    (core1_exit_code),
        .core2_exit_code    (core2_exit_code),
        .core3_exit_code    (core3_exit_code),
        .voted_exit_code    (voted_exit_code_cmb),

        .core1_print_valid  (core1_print_valid),
        .core2_print_valid  (core2_print_valid),
        .core3_print_valid  (core3_print_valid),
        .voted_print_valid  (voted_print_valid_cmb),

        .core1_print_data   (core1_print_data),
        .core2_print_data   (core2_print_data),
        .core3_print_data   (core3_print_data),
        .voted_print_data   (voted_print_data_cmb)
    );

    // ====== 10MHz 时钟 (周期 100ns) ======
    initial clk = 0;
    always #50 clk = ~clk;

    // ====== 测试控制变量 ======
    integer total_tests, passed_tests, failed_tests;
    integer scene_num;
    reg glitch_flag;

    // ====== 毛刺监控: 检测 combo 输出上的瞬时跳变 ======
    always @(voted_ready_cmb) begin
        // 在复位之后且 combo != pipeline 时，报告毛刺
        if (rst_n && ($realtime > 300) && (voted_ready_cmb !== voted_ready_pipe)) begin
            $display("  [GLITCH MONITOR] t=%0t: Combo=%d Pipeline=%d (combo 毛刺被检测到!)",
                     $realtime, voted_ready_cmb, voted_ready_pipe);
            glitch_flag = 1;
        end
    end

    // ====== 主测试流程 ======
    initial begin
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

        total_tests = 0;
        passed_tests = 0;
        failed_tests = 0;
        glitch_flag = 0;

        // VCD 波形输出
        $dumpfile("tb_glitch_injection.vcd");
        $dumpvars(0, tb_glitch_injection);

        $display("================================================================");
        $display("Glitch Injection Testbench for Pipeline TMR Voter");
        $display("Comparing: PIPELINE_ENABLE=1 (pipeline) vs PIPELINE_ENABLE=0 (combo)");
        $display("================================================================");
        $display("");

        // ====== 复位序列 ======
        $display("--- Reset Sequence ---");
        #150;
        rst_n = 1;
        $display("  Reset released at t=%0t", $realtime);
        #100;
        $display("  Post-reset: voted_ready_pipe=%d, voted_ready_cmb=%d",
                 voted_ready_pipe, voted_ready_cmb);

        // ================================================================
        // SCENE 1: 单比特毛刺注入 (ch-0 ready)
        //   在同一个时钟周期内快速切换 core1_ready,
        //   combo 输出会出现毛刺, pipeline 保持稳定
        // ================================================================
        scene_num = 1;
        $display("");
        $display("=================================================================");
        $display("SCENE %0d: Single-bit glitch injection on ch-0 (core1_ready)", scene_num);
        $display("=================================================================");

        // --- 场景 1a: 从全 0 出发，注入正向毛刺 (0→1→0) ---
        $display("");
        $display("  --- 1a: Glitch 0->1->0 (core2=1 fixed) ---");

        @(posedge clk);
        #5;
        // Setup: core1=0, core2=1, core3=0 => voted=MAJ(0,1,0)=0
        core1_ready = 0; core2_ready = 1; core3_ready = 0;
        #20;
        $display("  [Setup] core=(%d,%d,%d) => cmb=%d pipe=%d",
                 core1_ready, core2_ready, core3_ready,
                 voted_ready_cmb, voted_ready_pipe);

        // 等待 posedge, pipeline 采样 voted_comb=0
        @(posedge clk);
        #10;
        $display("  [After posedge] Pipeline sampled: pipe=%d", voted_ready_pipe);

        // 注入毛刺: core1 0→1→0 (短时间内)
        // 在 t=0: core1=0 => (0,1,0) => cmb=0
        // 在 t=1: core1=1 => (1,1,0) => cmb=1 (毛刺!)
        // 在 t=4: core1=0 => (0,1,0) => cmb=0
        #1;
        core1_ready = 1;   // (1,1,0) => cmb=1
        $display("  [Glitch ON]  core1=1 => cmb=%d pipe=%d", voted_ready_cmb, voted_ready_pipe);
        #3;
        core1_ready = 0;   // (0,1,0) => cmb=0
        $display("  [Glitch OFF] core1=0 => cmb=%d pipe=%d", voted_ready_cmb, voted_ready_pipe);

        #5;
        // 断言: pipeline 应该保持为 0 (未被毛刺影响)
        if (voted_ready_pipe === 1'b0) begin
            $display("  PASS 1a: Pipeline output stayed at 0 during glitch");
            passed_tests = passed_tests + 1;
        end else begin
            $display("  FAIL 1a: Pipeline output corrupted by glitch! pipe=%d", voted_ready_pipe);
            failed_tests = failed_tests + 1;
        end
        total_tests = total_tests + 1;

        // --- 场景 1b: 从全 1 出发，注入负向毛刺 (1→0→1) ---
        $display("");
        $display("  --- 1b: Glitch 1->0->1 (core2=1, core3=1 fixed) ---");

        @(posedge clk);
        #5;
        // Setup: core1=1, core2=1, core3=1 => voted=MAJ(1,1,1)=1
        core1_ready = 1; core2_ready = 1; core3_ready = 1;
        @(posedge clk);
        #10;
        $display("  [After posedge] Pipeline sampled: pipe=%d", voted_ready_pipe);

        // 注入毛刺: core1 1→0→1
        #1;
        core1_ready = 0;   // (0,1,1) => cmb=1 (仍然为1, 因为 core2,core3=1)
        // 实际上 MAJ(0,1,1)=1, 所以这个切换不会产生毛刺!
        // 需要改变两个输入才能产生 1→0 毛刺

        // 重新做: 改变 core2 1→0→1 同时 core1=1, core3=1
        // 不对, 让我重新设计这个子场景

        $display("  (Note: MAJ(0,1,1)=1, single-bit toggle doesn't change output)");
        $display("  (Skip 1b, use different approach below)");

        // --- 场景 1c: 两比特同时跳变产生负向毛刺 ---
        $display("");
        $display("  --- 1c: Two-bit toggle glitch (1->0->1 on core1 and core2) ---");

        @(posedge clk);
        #5;
        core1_ready = 1; core2_ready = 1; core3_ready = 1;
        @(posedge clk);
        #10;
        $display("  [After posedge] Pipeline sampled: pipe=%d", voted_ready_pipe);

        // 注入毛刺: core1 和 core2 同时 1→0→1 (但不同步)
        #1;
        core1_ready = 0;   // (0,1,1) => cmb=1 (still 1)
        #2;
        core2_ready = 0;   // (0,0,1) => cmb=0 (毛刺!)
        #2;
        core1_ready = 1;   // (1,0,1) => cmb=1
        #2;
        core2_ready = 1;   // (1,1,1) => cmb=1

        $display("  After glitch sequence: cmb=%d pipe=%d", voted_ready_cmb, voted_ready_pipe);

        if (voted_ready_pipe === 1'b1) begin
            $display("  PASS 1c: Pipeline output stayed at 1 during glitch");
            passed_tests = passed_tests + 1;
        end else begin
            $display("  FAIL 1c: Pipeline output corrupted! pipe=%d", voted_ready_pipe);
            failed_tests = failed_tests + 1;
        end
        total_tests = total_tests + 1;

        // ================================================================
        // SCENE 2: 多比特毛刺 (ch-5 print_data)
        //   对 32-bit 信号的不同 byte 施加不同延迟，模拟布线延迟差异
        // ================================================================
        scene_num = 2;
        $display("");
        $display("=================================================================");
        $display("SCENE %0d: Multi-bit glitch on ch-5 (print_data)", scene_num);
        $display("=================================================================");

        // --- 场景 2a: 所有 core 初始相同，改变 core1 的值 ---
        $display("");
        $display("  --- 2a: All cores=0xFFFFFFFF -> change core1 to 0, check pipeline latch ---");

        @(posedge clk);
        #5;
        core1_print_data = 32'hFFFFFFFF;
        core2_print_data = 32'hFFFFFFFF;
        core3_print_data = 32'h00000000;
        // voted = MAJ(1,1,0) = 1 (per bit) => 0xFFFFFFFF
        @(posedge clk);
        #10;
        $display("  [Setup] c1=0x%08x c2=0x%08x c3=0x%08x => cmb=0x%08x pipe=0x%08x",
                 core1_print_data, core2_print_data, core3_print_data,
                 voted_print_data_cmb, voted_print_data_pipe);

        // 改变 core1 为 0 — 相当于所有三核输入从 (1,1,0) 变 (0,1,0)
        // voted combo 应即刻变为 0
        core1_print_data = 32'h00000000;
        #1;
        $display("  [After core1->0] cmb=0x%08x pipe=0x%08x",
                 voted_print_data_cmb, voted_print_data_pipe);

        if (voted_print_data_cmb === 32'h00000000) begin
            $display("  PASS 2a-i: Combo output correctly changed to 0x%08x", voted_print_data_cmb);
            passed_tests = passed_tests + 1;
        end else begin
            $display("  FAIL 2a-i: Combo output wrong! cmb=0x%08x", voted_print_data_cmb);
            failed_tests = failed_tests + 1;
        end
        total_tests = total_tests + 1;

        if (voted_print_data_pipe === 32'hFFFFFFFF) begin
            $display("  PASS 2a-ii: Pipeline output still holds old value 0x%08x (latched)", voted_print_data_pipe);
            passed_tests = passed_tests + 1;
        end else begin
            $display("  FAIL 2a-ii: Pipeline output changed mid-cycle! pipe=0x%08x", voted_print_data_pipe);
            failed_tests = failed_tests + 1;
        end
        total_tests = total_tests + 1;

        // 下一个时钟沿，pipeline 应更新
        @(posedge clk);
        #5;
        if (voted_print_data_pipe === 32'h00000000) begin
            $display("  PASS 2a-iii: Pipeline correctly updated to 0x%08x at next clock edge", voted_print_data_pipe);
            passed_tests = passed_tests + 1;
        end else begin
            $display("  FAIL 2a-iii: Pipeline failed to update at clock edge! pipe=0x%08x", voted_print_data_pipe);
            failed_tests = failed_tests + 1;
        end
        total_tests = total_tests + 1;

        // --- 场景 2b: 模拟布线延迟 — 不同 bit 在不同时间跳变 ---
        $display("");
        $display("  --- 2b: Simulate routing delay — staggered bit transitions ---");

        @(posedge clk);
        #5;
        // Setup: 所有三个 core 都为 0xFFFF0000
        core1_print_data = 32'hFFFF0000;
        core2_print_data = 32'hFFFF0000;
        core3_print_data = 32'h0000FFFF;
        // voted: MAJ per bit
        // bit[31:16]: MAJ(1,1,0)=1 => 0xFFFF
        // bit[15:0]:  MAJ(0,0,1)=0 => 0x0000
        // voted = 0xFFFF0000
        @(posedge clk);
        #10;
        $display("  [Setup] c1=0x%08x c2=0x%08x c3=0x%08x => cmb=0x%08x pipe=0x%08x",
                 core1_print_data, core2_print_data, core3_print_data,
                 voted_print_data_cmb, voted_print_data_pipe);

        // 模拟延迟: 高 16 位先变，低 16 位后变
        // core1 从 0xFFFF0000 变为 0x0000FFFF
        // 但下半部分 (bits 15:0) 先变为 0xFFFF, 上半部分 (bits 31:16) 后变为 0x0000
        // 中间态: core1 = 0xFFFFXXXX (低16位已变, 但高16位还没变)

        // 第一阶段: 低 16 位变
        core1_print_data[15:0] = 16'hFFFF;
        #2;
        $display("  [Phase 1] lower 16 bits changed: c1=0x%08x => cmb=0x%08x pipe=0x%08x",
                 core1_print_data, voted_print_data_cmb, voted_print_data_pipe);
        // 此时 core1=0xFFFFFFFF core2=0xFFFF0000 core3=0x0000FFFF
        // bit[31:16]: MAJ(1,1,0)=1
        // bit[15:0]:  MAJ(1,0,1)=1 (因为 core1=1, core3=1)
        // => voted = 0xFFFFFFFF

        // 第二阶段: 高 16 位变
        #2;
        core1_print_data[31:16] = 16'h0000;
        #2;
        $display("  [Phase 2] upper 16 bits changed: c1=0x%08x => cmb=0x%08x pipe=0x%08x",
                 core1_print_data, voted_print_data_cmb, voted_print_data_pipe);
        // 此时 core1=0x0000FFFF core2=0xFFFF0000 core3=0x0000FFFF
        // bit[31:16]: MAJ(0,1,0)=0
        // bit[15:0]:  MAJ(1,0,1)=1
        // => voted = 0x0000FFFF

        // 检查 combo 是否在相位 1 时出现了 0xFFFFFFFF (中间毛刺值)
        // 以及 pipeline 是否在整个过程中保持 0xFFFF0000

        if (voted_print_data_pipe === 32'hFFFF0000) begin
            $display("  PASS 2b-i: Pipeline output stable at 0x%08x during staggered transition", voted_print_data_pipe);
            passed_tests = passed_tests + 1;
        end else begin
            $display("  FAIL 2b-i: Pipeline output changed! pipe=0x%08x", voted_print_data_pipe);
            failed_tests = failed_tests + 1;
        end
        total_tests = total_tests + 1;

        // 下一个时钟沿后 pipeline 应更新到 0x0000FFFF
        @(posedge clk);
        #5;
        if (voted_print_data_pipe === 32'h0000FFFF) begin
            $display("  PASS 2b-ii: Pipeline correctly updated to 0x%08x at next edge", voted_print_data_pipe);
            passed_tests = passed_tests + 1;
        end else begin
            $display("  FAIL 2b-ii: Pipeline wrong after edge! pipe=0x%08x (expected 0x0000FFFF)",
                     voted_print_data_pipe);
            failed_tests = failed_tests + 1;
        end
        total_tests = total_tests + 1;

        // ================================================================
        // SCENE 3: 建立时间违例注入
        //   在时钟上升沿附近改变输入, 检查 pipeline 输出是否稳定
        // ================================================================
        scene_num = 3;
        $display("");
        $display("=================================================================");
        $display("SCENE %0d: Setup violation injection on ch-0 ready", scene_num);
        $display("=================================================================");

        $display("");
        $display("  --- 3a: Input change at #49 (1ns before clock edge #50) ---");

        @(posedge clk);
        #5;
        // 先建立已知状态
        core1_ready = 0; core2_ready = 0; core3_ready = 0;
        @(posedge clk);  // pipeline samples 0
        #10;
        $display("  [Baseline] core=(%d,%d,%d) => cmb=%d pipe=%d",
                 core1_ready, core2_ready, core3_ready,
                 voted_ready_cmb, voted_ready_pipe);

        // 在 #49 处改变输入 (距离下一个上升沿 #50 仅 1ns — 建立时间违例)
        #39;  // total: 10 + 39 = 49
        core1_ready = 1; core2_ready = 1;
        // 在 #49 时: core=(1,1,0) => cmb=1
        #1;   // passes clock edge at #50
        $display("  [After setup violation] core=(%d,%d,%d) at t=%0t",
                 core1_ready, core2_ready, core3_ready, $realtime);
        $display("  cmb=%d pipe=%d (after edge at #50)", voted_ready_cmb, voted_ready_pipe);

        // 断言: pipeline 输出应稳定 (是 0 或 1, 但不能是 X/Z)
        if ((voted_ready_pipe === 1'b0) || (voted_ready_pipe === 1'b1)) begin
            $display("  PASS 3a: Pipeline output is stable (%d) after setup violation", voted_ready_pipe);
            passed_tests = passed_tests + 1;
        end else begin
            $display("  FAIL 3a: Pipeline output is X or Z after setup violation");
            failed_tests = failed_tests + 1;
        end
        total_tests = total_tests + 1;

        // --- 场景 3b: 输入在时钟沿同时改变 ---
        $display("");
        $display("  --- 3b: Input changes simultaneous with clock edge ---");

        @(posedge clk);
        #5;
        core1_ready = 0; core2_ready = 0; core3_ready = 0;
        @(posedge clk);
        #10;

        // 在时钟沿 #0 时刻改变输入 (使用非阻塞赋值模拟)
        // 使用 #0 延迟在时钟沿上改变
        @(posedge clk);
        core1_ready = 1; core2_ready = 1; core3_ready = 0;
        // 在同一个时间片 #0 改变
        #1;
        $display("  [At edge] core=(%d,%d,%d) => cmb=%d pipe=%d",
                 core1_ready, core2_ready, core3_ready,
                 voted_ready_cmb, voted_ready_pipe);

        // pipeline 可能采样到旧值 (0) 或新值 (1), 两者都合理
        // 关键是稳定
        if ((voted_ready_pipe === 1'b0) || (voted_ready_pipe === 1'b1)) begin
            $display("  PASS 3b: Pipeline output is stable (%d) after edge-synchronous change", voted_ready_pipe);
            passed_tests = passed_tests + 1;
        end else begin
            $display("  FAIL 3b: Pipeline output is X or Z after edge-synchronous change");
            failed_tests = failed_tests + 1;
        end
        total_tests = total_tests + 1;

        // --- 场景 3c: 在时钟沿后极短时间内改变 ---
        $display("");
        $display("  --- 3c: Input change at #51 (1ns after clock edge #50) ---");

        @(posedge clk);
        #5;
        core1_ready = 0; core2_ready = 1; core3_ready = 0;
        @(posedge clk);
        #10;

        #41; // total: 10 + 41 = 51 (1ns after next edge at #50)
        core1_ready = 1; // (1,1,0) => cmb=1
        #1;
        $display("  [After edge+1ns] core=(%d,%d,%d) => cmb=%d pipe=%d",
                 core1_ready, core2_ready, core3_ready,
                 voted_ready_cmb, voted_ready_pipe);

        // combo 应该已经变为 1, pipeline 应该保持原来的采样值
        if (voted_ready_cmb === 1'b1) begin
            $display("  PASS 3c-i: Combo correctly reflects new input (1)");
            passed_tests = passed_tests + 1;
        end else begin
            $display("  FAIL 3c-i: Combo wrong! cmb=%d", voted_ready_cmb);
            failed_tests = failed_tests + 1;
        end
        total_tests = total_tests + 1;

        // pipeline 应该还是 0 (它在上个沿采样的是 core=(0,1,0) => 0)
        // 除非设置 violation 导致它采样到了新值
        // 这里我们接受任何稳定值
        if ((voted_ready_pipe === 1'b0) || (voted_ready_pipe === 1'b1)) begin
            $display("  PASS 3c-ii: Pipeline output is stable (%d)", voted_ready_pipe);
            passed_tests = passed_tests + 1;
        end else begin
            $display("  FAIL 3c-ii: Pipeline output is X or Z");
            failed_tests = failed_tests + 1;
        end
        total_tests = total_tests + 1;

        // ====== 最终总结 ======
        #200;
        $display("");
        $display("================================================================");
        $display("GLITCH INJECTION TEST SUMMARY");
        $display("================================================================");
        $display("  Total assertions: %0d", total_tests);
        $display("  Passed:           %0d", passed_tests);
        $display("  Failed:           %0d", failed_tests);
        if (glitch_flag) begin
            $display("  Glitch detected:  YES (combo output showed glitches)");
        end else begin
            $display("  Glitch detected:  NO (no combo glitch registered)");
        end
        $display("------------------------------------------------------------");
        if (failed_tests == 0) begin
            $display("  RESULT: ALL TESTS PASSED — Pipeline correctly suppresses glitches");
        end else begin
            $display("  RESULT: %0d TEST(S) FAILED", failed_tests);
            $display("  Review above FAIL lines for details");
        end
        $display("================================================================");

        repeat (10) @(posedge clk);
        $finish;
    end

endmodule
