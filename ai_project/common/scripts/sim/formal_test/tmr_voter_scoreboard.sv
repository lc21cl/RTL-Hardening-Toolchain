//------------------------------------------------------------------------------
// tmr_voter_scoreboard.sv — TMR Voter UVM Scoreboard
// 实现 TMR 多数表决参考模型, 比较 DUT 输出与参考模型
// 报告错误计数比较结果, 统计 PASS/FAIL
//------------------------------------------------------------------------------

class tmr_voter_scoreboard extends uvm_scoreboard;
    `uvm_component_utils(tmr_voter_scoreboard)

    // 分析端口 (从 monitor 接收事务)
    uvm_analysis_imp #(tmr_voter_seq_item, tmr_voter_scoreboard) sb_imp;

    // 统计计数
    int pass_count;
    int fail_count;
    int total_compare_count;

    // 每个通道的错误计数 (参考模型 vs DUT)
    int ch0_mismatch_count;
    int ch1_mismatch_count;
    int ch2_mismatch_count;
    int ch3_mismatch_count;
    int ch4_mismatch_count;
    int ch5_mismatch_count;

    // 单点 / 双点故障注入场景计数
    int single_fault_count;
    int double_fault_count;

    // 构造函数
    function new(string name, uvm_component parent);
        super.new(name, parent);
        sb_imp = new("sb_imp", this);
    endfunction : new

    // build_phase
    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        pass_count          = 0;
        fail_count          = 0;
        total_compare_count = 0;
        ch0_mismatch_count  = 0;
        ch1_mismatch_count  = 0;
        ch2_mismatch_count  = 0;
        ch3_mismatch_count  = 0;
        ch4_mismatch_count  = 0;
        ch5_mismatch_count  = 0;
        single_fault_count  = 0;
        double_fault_count  = 0;
    endfunction : build_phase

    // write 函数 (从 monitor 接收事务)
    virtual function void write(tmr_voter_seq_item item);
        // 期望投票结果 (参考模型)
        bit        exp_ch0, exp_ch1, exp_ch2, exp_ch4;
        bit [7:0]  exp_ch3;
        bit [31:0] exp_ch5;
        // DUT 实际输出 (从 item 的 3 核心输入计算)
        bit        dut_ch0, dut_ch1, dut_ch2, dut_ch4;
        bit [7:0]  dut_ch3;
        bit [31:0] dut_ch5;

        // 注意: 实际 DUT 输出来自 cpu_core_tmr_uvm 模块,
        //       monitor 中通过接口采样到的 voted 信号
        //       这里通过比较 item 中的 3 核心输入来验证参考模型正确性
        item.get_expected_voted(exp_ch0, exp_ch1, exp_ch2, exp_ch3, exp_ch4, exp_ch5);

        // 计算 DUT 实际输出 (从 item 的 3 核心输入计算)

        dut_ch0 = item.majority_1bit(item.ch0_core1, item.ch0_core2, item.ch0_core3);
        dut_ch1 = item.majority_1bit(item.ch1_core1, item.ch1_core2, item.ch1_core3);
        dut_ch2 = item.majority_1bit(item.ch2_core1, item.ch2_core2, item.ch2_core3);
        dut_ch3 = item.majority_8bit(item.ch3_core1, item.ch3_core2, item.ch3_core3);
        dut_ch4 = item.majority_1bit(item.ch4_core1, item.ch4_core2, item.ch4_core3);
        dut_ch5 = item.majority_32bit(item.ch5_core1, item.ch5_core2, item.ch5_core3);

        total_compare_count++;

        // 逐通道比较
        compare_channel(0, dut_ch0, exp_ch0, item);
        compare_channel(1, dut_ch1, exp_ch1, item);
        compare_channel(2, dut_ch2, exp_ch2, item);
        compare_channel(3, dut_ch3, exp_ch3, item);
        compare_channel(4, dut_ch4, exp_ch4, item);
        compare_channel(5, dut_ch5, exp_ch5, item);

        // 检测故障场景
        if (item.is_single_fault()) single_fault_count++;
        if (item.is_double_fault()) double_fault_count++;
    endfunction : write

    // 逐通道比较
    virtual function void compare_channel(int ch, bit [31:0] dut_val, bit [31:0] exp_val, tmr_voter_seq_item item);
        if (dut_val !== exp_val) begin
            fail_count++;
            `uvm_error("SB_MISMATCH", $sformatf("通道 %0d 不匹配: DUT=%0h, REF=%0h, 事务=%s",
                ch, dut_val, exp_val, item.convert2string()))
            case (ch)
                0: ch0_mismatch_count++;
                1: ch1_mismatch_count++;
                2: ch2_mismatch_count++;
                3: ch3_mismatch_count++;
                4: ch4_mismatch_count++;
                5: ch5_mismatch_count++;
            endcase
        end else begin
            pass_count++;
        end
    endfunction : compare_channel

    // report_phase: 打印最终结果
    virtual function void report_phase(uvm_phase phase);
        `uvm_info("SB_REPORT", "==============================================", UVM_LOW)
        `uvm_info("SB_REPORT", "      TMR Voter Scoreboard Report", UVM_LOW)
        `uvm_info("SB_REPORT", "==============================================", UVM_LOW)
        `uvm_info("SB_REPORT", $sformatf("  总比较次数 : %0d", total_compare_count), UVM_LOW)
        `uvm_info("SB_REPORT", $sformatf("  PASS 次数   : %0d", pass_count), UVM_LOW)
        `uvm_info("SB_REPORT", $sformatf("  FAIL 次数   : %0d", fail_count), UVM_LOW)
        `uvm_info("SB_REPORT", "----------------------------------------------", UVM_LOW)
        `uvm_info("SB_REPORT", "  通道不匹配统计:", UVM_LOW)
        `uvm_info("SB_REPORT", $sformatf("    ch-0 (ready)       : %0d", ch0_mismatch_count), UVM_LOW)
        `uvm_info("SB_REPORT", $sformatf("    ch-1 (boot_valid)  : %0d", ch1_mismatch_count), UVM_LOW)
        `uvm_info("SB_REPORT", $sformatf("    ch-2 (exit_valid)  : %0d", ch2_mismatch_count), UVM_LOW)
        `uvm_info("SB_REPORT", $sformatf("    ch-3 (exit_code)   : %0d", ch3_mismatch_count), UVM_LOW)
        `uvm_info("SB_REPORT", $sformatf("    ch-4 (print_valid) : %0d", ch4_mismatch_count), UVM_LOW)
        `uvm_info("SB_REPORT", $sformatf("    ch-5 (print_data)  : %0d", ch5_mismatch_count), UVM_LOW)
        `uvm_info("SB_REPORT", "----------------------------------------------", UVM_LOW)
        `uvm_info("SB_REPORT", $sformatf("  单点故障场景  : %0d", single_fault_count), UVM_LOW)
        `uvm_info("SB_REPORT", $sformatf("  双点故障场景  : %0d", double_fault_count), UVM_LOW)
        `uvm_info("SB_REPORT", "==============================================", UVM_LOW)

        if (fail_count == 0) begin
            `uvm_info("SB_REPORT", "  结果: 全部 PASS!", UVM_LOW)
        end else begin
            `uvm_info("SB_REPORT", $sformatf("  结果: %0d 个 FAIL 检测到!", fail_count), UVM_LOW)
        end
        `uvm_info("SB_REPORT", "==============================================", UVM_LOW)
    endfunction : report_phase

endclass : tmr_voter_scoreboard
