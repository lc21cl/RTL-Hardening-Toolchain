//------------------------------------------------------------------------------
// tmr_voter_test.sv — TMR Voter UVM Test
// 包含所有测试序列和 test 类
//------------------------------------------------------------------------------

// ========================================================================
// 基序列 — 所有序列的基类
// ========================================================================
class tmr_voter_base_sequence extends uvm_sequence #(tmr_voter_seq_item);
    `uvm_object_utils(tmr_voter_base_sequence)

    function new(string name = "tmr_voter_base_sequence");
        super.new(name);
    endfunction : new

    // 创建并发送一个序列项
    virtual task send_item(
        bit       ch0_c1, bit       ch0_c2, bit       ch0_c3,
        bit       ch1_c1, bit       ch1_c2, bit       ch1_c3,
        bit       ch2_c1, bit       ch2_c2, bit       ch2_c3,
        bit [7:0] ch3_c1, bit [7:0] ch3_c2, bit [7:0] ch3_c3,
        bit       ch4_c1, bit       ch4_c2, bit       ch4_c3,
        bit [31:0] ch5_c1, bit [31:0] ch5_c2, bit [31:0] ch5_c3
    );
        tmr_voter_seq_item item = tmr_voter_seq_item::type_id::create("item");
        start_item(item);
        item.ch0_core1 = ch0_c1; item.ch0_core2 = ch0_c2; item.ch0_core3 = ch0_c3;
        item.ch1_core1 = ch1_c1; item.ch1_core2 = ch1_c2; item.ch1_core3 = ch1_c3;
        item.ch2_core1 = ch2_c1; item.ch2_core2 = ch2_c2; item.ch2_core3 = ch2_c3;
        item.ch3_core1 = ch3_c1; item.ch3_core2 = ch3_c2; item.ch3_core3 = ch3_c3;
        item.ch4_core1 = ch4_c1; item.ch4_core2 = ch4_c2; item.ch4_core3 = ch4_c3;
        item.ch5_core1 = ch5_c1; item.ch5_core2 = ch5_c2; item.ch5_core3 = ch5_c3;
        item.fault_inject_en = 0;
        finish_item(item);
    endtask : send_item

endclass : tmr_voter_base_sequence


// ========================================================================
// reset_sequence — 复位测试
// ========================================================================
class reset_sequence extends tmr_voter_base_sequence;
    `uvm_object_utils(reset_sequence)

    function new(string name = "reset_sequence");
        super.new(name);
    endfunction : new

    virtual task body();
        `uvm_info("SEQ", "开始复位测试序列...", UVM_LOW)

        // 所有核心输出为 0, 模拟复位后状态
        for (int i = 0; i < 10; i++) begin
            send_item(0,0,0,  0,0,0,  0,0,0,  8'h00,8'h00,8'h00,  0,0,0,  32'h00000000,32'h00000000,32'h00000000);
            #10;
        end

        `uvm_info("SEQ", "复位测试序列完成", UVM_LOW)
    endtask : body
endclass : reset_sequence


// ========================================================================
// single_fault_sequence — 单点故障注入测试
// ========================================================================
class single_fault_sequence extends tmr_voter_base_sequence;
    `uvm_object_utils(single_fault_sequence)

    function new(string name = "single_fault_sequence");
        super.new(name);
    endfunction : new

    virtual task body();
        `uvm_info("SEQ", "开始单点故障注入测试序列...", UVM_LOW)

        // === core1 故障测试 ===
        `uvm_info("SEQ", "--- core1 故障注入 (ch0~ch5) ---", UVM_LOW)
        // ch0: core1=0, core2=1, core3=1 → 预期 voted=1
        send_item(0,1,1,  1,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'hA5A5A5A5,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;
        // ch0: core1=1, core2=0, core3=0 → 预期 voted=0
        send_item(1,0,0,  1,0,0,  1,0,0,  8'h55,8'hAA,8'hAA,  1,0,0,  32'hA5A5A5A5,32'h00000000,32'h00000000);
        #10;
        // ch1: core1=0, core2=1, core3=1 → 预期 voted=1
        send_item(1,1,1,  0,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'hA5A5A5A5,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;

        // === core2 故障测试 ===
        `uvm_info("SEQ", "--- core2 故障注入 (ch0~ch5) ---", UVM_LOW)
        send_item(1,0,1,  1,0,1,  1,0,1,  8'hAA,8'h55,8'hAA,  1,0,1,  32'hA5A5A5A5,32'h5A5A5A5A,32'hA5A5A5A5);
        #10;
        send_item(0,1,0,  0,1,0,  0,1,0,  8'hAA,8'h55,8'hAA,  0,1,0,  32'h00000000,32'h5A5A5A5A,32'h00000000);
        #10;

        // === core3 故障测试 ===
        `uvm_info("SEQ", "--- core3 故障注入 (ch0~ch5) ---", UVM_LOW)
        send_item(1,1,0,  1,1,0,  1,1,0,  8'hAA,8'hAA,8'h55,  1,1,0,  32'hA5A5A5A5,32'hA5A5A5A5,32'h5A5A5A5A);
        #10;
        send_item(0,0,1,  0,0,1,  0,0,1,  8'hAA,8'hAA,8'h55,  0,0,1,  32'h00000000,32'h00000000,32'h5A5A5A5A);
        #10;

        `uvm_info("SEQ", "单点故障注入测试序列完成", UVM_LOW)
    endtask : body
endclass : single_fault_sequence


// ========================================================================
// double_fault_sequence — 双点故障注入测试
// ========================================================================
class double_fault_sequence extends tmr_voter_base_sequence;
    `uvm_object_utils(double_fault_sequence)

    function new(string name = "double_fault_sequence");
        super.new(name);
    endfunction : new

    virtual task body();
        `uvm_info("SEQ", "开始双点故障注入测试序列...", UVM_LOW)

        // 2 个核心故障, 1 个核心正常
        // 双点故障: 所有 3 个输入互不相同 → 按位与/或逻辑决定

        // === 场景 1: core1=1, core2=0, core3=0 → voted=0 ===
        `uvm_info("SEQ", "--- 双点故障场景 1: (1,0,0) ---", UVM_LOW)
        send_item(1,0,0,  1,0,0,  1,0,0,  8'hFF,8'h00,8'h00,  1,0,0,  32'hFFFFFFFF,32'h00000000,32'h00000000);
        #10;

        // === 场景 2: core1=0, core2=1, core3=0 → voted=0 ===
        `uvm_info("SEQ", "--- 双点故障场景 2: (0,1,0) ---", UVM_LOW)
        send_item(0,1,0,  0,1,0,  0,1,0,  8'h00,8'hFF,8'h00,  0,1,0,  32'h00000000,32'hFFFFFFFF,32'h00000000);
        #10;

        // === 场景 3: core1=0, core2=0, core3=1 → voted=0 ===
        `uvm_info("SEQ", "--- 双点故障场景 3: (0,0,1) ---", UVM_LOW)
        send_item(0,0,1,  0,0,1,  0,0,1,  8'h00,8'h00,8'hFF,  0,0,1,  32'h00000000,32'h00000000,32'hFFFFFFFF);
        #10;

        // === 场景 4: 所有 3 个 core 都不同 (1-bit) ===
        `uvm_info("SEQ", "--- 双点故障场景 4: (1,0,1) — 2个一致, 实际上不是双点 ---", UVM_LOW)
        send_item(1,0,1,  1,0,1,  1,0,1,  8'hAA,8'h55,8'h33,  1,0,1,  32'hA5A5A5A5,32'h5A5A5A5A,32'hFFFFFFFF);
        #10;

        // === 场景 5: 所有 3 个 core 完全相同但为 0 ===
        `uvm_info("SEQ", "--- 双点故障场景 5: all-zero ---", UVM_LOW)
        send_item(0,0,0,  0,0,0,  0,0,0,  8'h00,8'h00,8'h00,  0,0,0,  32'h00000000,32'h00000000,32'h00000000);
        #10;

        `uvm_info("SEQ", "双点故障注入测试序列完成", UVM_LOW)
    endtask : body
endclass : double_fault_sequence


// ========================================================================
// random_stimulus_sequence — 1000 组随机激励
// ========================================================================
class random_stimulus_sequence extends tmr_voter_base_sequence;
    `uvm_object_utils(random_stimulus_sequence)

    function new(string name = "random_stimulus_sequence");
        super.new(name);
    endfunction : new

    virtual task body();
        `uvm_info("SEQ", "开始随机激励测试序列 (1000 组)...", UVM_LOW)

        repeat (1000) begin
            tmr_voter_seq_item item = tmr_voter_seq_item::type_id::create("item");
            start_item(item);
            // 完全随机化
            if (!item.randomize())
                `uvm_error("SEQ", "随机化失败")
            item.fault_inject_en = 0;
            finish_item(item);
            #5;
        end

        `uvm_info("SEQ", "随机激励测试序列完成", UVM_LOW)
    endtask : body
endclass : random_stimulus_sequence


// ========================================================================
// boundary_sequence — 边界条件测试
// ========================================================================
class boundary_sequence extends tmr_voter_base_sequence;
    `uvm_object_utils(boundary_sequence)

    function new(string name = "boundary_sequence");
        super.new(name);
    endfunction : new

    virtual task body();
        `uvm_info("SEQ", "开始边界条件测试序列...", UVM_LOW)

        // === 1. 全 0 ===
        `uvm_info("SEQ", "--- 边界: 全 0 ---", UVM_LOW)
        send_item(0,0,0,  0,0,0,  0,0,0,  8'h00,8'h00,8'h00,  0,0,0,  32'h00000000,32'h00000000,32'h00000000);
        #10;

        // === 2. 全 1 ===
        `uvm_info("SEQ", "--- 边界: 全 1 ---", UVM_LOW)
        send_item(1,1,1,  1,1,1,  1,1,1,  8'hFF,8'hFF,8'hFF,  1,1,1,  32'hFFFFFFFF,32'hFFFFFFFF,32'hFFFFFFFF);
        #10;

        // === 3. 全相同 (中间值) ===
        `uvm_info("SEQ", "--- 边界: 全相同 (0xAA) ---", UVM_LOW)
        send_item(1,1,1,  1,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'hA5A5A5A5,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;

        // === 4. 全不同 (每个通道 3 个互不相同的值) ===
        `uvm_info("SEQ", "--- 边界: 全不同 ---", UVM_LOW)
        // ch0: (1,0,1) → (1&0)|(1&1)|(0&1) = 0|1|0 = 1
        // ch3: (0xAA,0x55,0x33) 按位 majority
        // ch5: (0xA5A5A5A5,0x5A5A5A5A,0xFFFFFFFF) 按位 majority
        send_item(1,0,1,  1,0,1,  1,0,1,  8'hAA,8'h55,8'h33,  1,0,1,  32'hA5A5A5A5,32'h5A5A5A5A,32'hFFFFFFFF);
        #10;

        // === 5. 单 bit 翻转 (每个通道依次翻转 1 bit) ===
        `uvm_info("SEQ", "--- 边界: 逐通道单 bit 翻转 ---", UVM_LOW)
        // ch0: core1 翻转
        send_item(0,1,1,  1,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'hA5A5A5A5,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;
        // ch1: core2 翻转
        send_item(1,1,1,  1,0,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'hA5A5A5A5,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;
        // ch2: core3 翻转
        send_item(1,1,1,  1,1,1,  1,1,0,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'hA5A5A5A5,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;

        // === 6. 最大值/最小值边界 ===
        `uvm_info("SEQ", "--- 边界: exit_code 最大值/最小值 ---", UVM_LOW)
        send_item(1,1,1,  1,1,1,  1,1,1,  8'h00,8'h00,8'h00,  1,1,1,  32'hA5A5A5A5,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;
        send_item(1,1,1,  1,1,1,  1,1,1,  8'hFF,8'hFF,8'hFF,  1,1,1,  32'hA5A5A5A5,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;

        // === 7. print_data 边界值 ===
        `uvm_info("SEQ", "--- 边界: print_data 边界值 ---", UVM_LOW)
        send_item(1,1,1,  1,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'h00000000,32'h00000000,32'h00000000);
        #10;
        send_item(1,1,1,  1,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'hFFFFFFFF,32'hFFFFFFFF,32'hFFFFFFFF);
        #10;
        send_item(1,1,1,  1,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'h80000000,32'h80000000,32'h80000000);
        #10;
        send_item(1,1,1,  1,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'h7FFFFFFF,32'h7FFFFFFF,32'h7FFFFFFF);
        #10;

        `uvm_info("SEQ", "边界条件测试序列完成", UVM_LOW)
    endtask : body
endclass : boundary_sequence


// ========================================================================
// glitch_injection_sequence — 毛刺注入测试序列 (Pipeline 验证)
// 验证 pipeline 寄存器的毛刺抑制能力
// ========================================================================
class glitch_injection_sequence extends tmr_voter_base_sequence;
    `uvm_object_utils(glitch_injection_sequence)

    // 期望的 voted 值 (用于 pipeline 延迟补偿)
    int expected_voted[$];

    function new(string name = "glitch_injection_sequence");
        super.new(name);
    endfunction : new

    virtual task body();
        `uvm_info("GLITCH_SEQ", "=== 开始毛刺注入测试序列 ===", UVM_LOW)

        // --- 场景 1: 单比特毛刺注入 ---
        `uvm_info("GLITCH_SEQ", "场景 1: 单比特毛刺 (ch-0 ready)", UVM_LOW)
        // 注入 core1_ready=0, 但 core2/3=1 → majority 期望 = 1
        // 正常情况: voted=1
        send_item(1,1,1,  1,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'hA5A5A5A5,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;
        // 注入 core1_ready=0 (单点故障) → 期望 voted 仍为 1 (因为 core2/3=1)
        send_item(0,1,1,  1,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'hA5A5A5A5,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;

        // --- 场景 2: 多比特毛刺注入 ---
        `uvm_info("GLITCH_SEQ", "场景 2: 多比特毛刺 (ch-5 print_data)", UVM_LOW)
        // 32-bit 信号的逐位毛刺: 32 个 bit 同时变化但多数一致
        send_item(1,1,1,  1,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'hA5A5A5A5,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;
        // 注入 core1_print_data 低位跳跃, 但 majority 不变
        send_item(1,1,1,  1,1,1,  1,1,1,  8'hAA,8'hAA,8'hAA,  1,1,1,  32'hA5A5A5A4,32'hA5A5A5A5,32'hA5A5A5A5);
        #10;

        // --- 场景 3: 3核心同值验证 (无故障) ---
        `uvm_info("GLITCH_SEQ", "场景 3: 无故障 — 3 核心完全一致", UVM_LOW)
        for (int i = 0; i < 10; i++) begin
            bit [31:0] rand_val = $urandom;
            send_item(1,1,1,  1,1,1,  1,1,1,  8'hA5,8'hA5,8'hA5,  1,1,1,  rand_val, rand_val, rand_val);
            #10;
        end

        // --- 场景 4: 边界条件 ---
        `uvm_info("GLITCH_SEQ", "场景 4: 全 0 与全 1 快速切换", UVM_LOW)
        for (int i = 0; i < 4; i++) begin
            send_item(1,1,1,  1,1,1,  1,1,1,  8'hFF,8'hFF,8'hFF,  1,1,1,  32'hFFFFFFFF,32'hFFFFFFFF,32'hFFFFFFFF);
            #5;
            send_item(0,0,0,  0,0,0,  0,0,0,  8'h00,8'h00,8'h00,  0,0,0,  32'h00000000,32'h00000000,32'h00000000);
            #5;
        end

        `uvm_info("GLITCH_SEQ", "=== 毛刺注入测试序列完成 ===", UVM_LOW)
    endtask : body
endclass : glitch_injection_sequence


// ========================================================================
// all_sequences — 完整回归序列 (运行所有测试)
// ========================================================================
class all_sequences extends tmr_voter_base_sequence;
    `uvm_object_utils(all_sequences)

    function new(string name = "all_sequences");
        super.new(name);
    endfunction : new

    virtual task body();
        reset_sequence          reset_seq;
        single_fault_sequence   single_seq;
        double_fault_sequence   double_seq;
        random_stimulus_sequence random_seq;
        boundary_sequence       bound_seq;
        glitch_injection_sequence glitch_seq;

        `uvm_info("SEQ", "===== 开始完整回归测试 =====", UVM_LOW)

        // 创建并运行子序列
        reset_seq  = reset_sequence::type_id::create("reset_seq");
        single_seq = single_fault_sequence::type_id::create("single_seq");
        double_seq = double_fault_sequence::type_id::create("double_seq");
        random_seq = random_stimulus_sequence::type_id::create("random_seq");
        bound_seq  = boundary_sequence::type_id::create("bound_seq");
        glitch_seq = glitch_injection_sequence::type_id::create("glitch_seq");

        `uvm_info("SEQ", "运行 reset_sequence...", UVM_LOW)
        reset_seq.start(m_sequencer);

        `uvm_info("SEQ", "运行 single_fault_sequence...", UVM_LOW)
        single_seq.start(m_sequencer);

        `uvm_info("SEQ", "运行 double_fault_sequence...", UVM_LOW)
        double_seq.start(m_sequencer);

        `uvm_info("SEQ", "运行 random_stimulus_sequence...", UVM_LOW)
        random_seq.start(m_sequencer);

        `uvm_info("SEQ", "运行 boundary_sequence...", UVM_LOW)
        bound_seq.start(m_sequencer);

        `uvm_info("SEQ", "运行 glitch_injection_sequence...", UVM_LOW)
        glitch_seq.start(m_sequencer);

        `uvm_info("SEQ", "===== 完整回归测试完成 =====", UVM_LOW)
    endtask : body
endclass : all_sequences


// ========================================================================
// tmr_voter_base_test — 测试基类
// ========================================================================
class tmr_voter_base_test extends uvm_test;
    `uvm_component_utils(tmr_voter_base_test)

    tmr_voter_env      env;
    tmr_voter_reg_block reg_model;

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction : new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);

        // 创建环境
        env = tmr_voter_env::type_id::create("env", this);

        // 设置默认超时
        uvm_root::get().set_timeout(10ms, 0);
    endfunction : build_phase

    virtual function void end_of_elaboration_phase(uvm_phase phase);
        super.end_of_elaboration_phase(phase);
        // 打印 UVM 拓扑
        uvm_top.print_topology();
    endfunction : end_of_elaboration_phase

    virtual function void report_phase(uvm_phase phase);
        super.report_phase(phase);
        `uvm_info("TEST", "测试完成", UVM_LOW)
    endfunction : report_phase

endclass : tmr_voter_base_test


// ========================================================================
// reset_test — 复位测试
// ========================================================================
class reset_test extends tmr_voter_base_test;
    `uvm_component_utils(reset_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction : new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        uvm_config_wrapper::set(this, "env.agent.sequencer.run_phase",
                                "default_sequence", reset_sequence::get_type());
    endfunction : build_phase
endclass : reset_test


// ========================================================================
// single_fault_test — 单点故障测试
// ========================================================================
class single_fault_test extends tmr_voter_base_test;
    `uvm_component_utils(single_fault_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction : new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        uvm_config_wrapper::set(this, "env.agent.sequencer.run_phase",
                                "default_sequence", single_fault_sequence::get_type());
    endfunction : build_phase
endclass : single_fault_test


// ========================================================================
// double_fault_test — 双点故障测试
// ========================================================================
class double_fault_test extends tmr_voter_base_test;
    `uvm_component_utils(double_fault_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction : new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        uvm_config_wrapper::set(this, "env.agent.sequencer.run_phase",
                                "default_sequence", double_fault_sequence::get_type());
    endfunction : build_phase
endclass : double_fault_test


// ========================================================================
// random_stimulus_test — 随机激励测试
// ========================================================================
class random_stimulus_test extends tmr_voter_base_test;
    `uvm_component_utils(random_stimulus_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction : new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        uvm_config_wrapper::set(this, "env.agent.sequencer.run_phase",
                                "default_sequence", random_stimulus_sequence::get_type());
    endfunction : build_phase
endclass : random_stimulus_test


// ========================================================================
// boundary_test — 边界条件测试
// ========================================================================
class boundary_test extends tmr_voter_base_test;
    `uvm_component_utils(boundary_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction : new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        uvm_config_wrapper::set(this, "env.agent.sequencer.run_phase",
                                "default_sequence", boundary_sequence::get_type());
    endfunction : build_phase
endclass : boundary_test


// ========================================================================
// regress_test — 完整回归测试 (运行所有序列)
// ========================================================================
class regress_test extends tmr_voter_base_test;
    `uvm_component_utils(regress_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction : new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        uvm_config_wrapper::set(this, "env.agent.sequencer.run_phase",
                                "default_sequence", all_sequences::get_type());
    endfunction : build_phase
endclass : regress_test


// ========================================================================
// glitch_injection_test — 毛刺注入测试 (Pipeline 验证)
// ========================================================================
class glitch_injection_test extends tmr_voter_base_test;
    `uvm_component_utils(glitch_injection_test)

    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction : new

    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        uvm_config_wrapper::set(this, "env.agent.sequencer.run_phase",
                                "default_sequence", glitch_injection_sequence::get_type());
    endfunction : build_phase
endclass : glitch_injection_test
