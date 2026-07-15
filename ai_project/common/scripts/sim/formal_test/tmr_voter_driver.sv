//------------------------------------------------------------------------------
// tmr_voter_driver.sv — TMR Voter UVM Driver
// 从 sequencer 获取序列项, 驱动 DUT 接口, 支持故障注入
//------------------------------------------------------------------------------

// 核心事务数据结构
class tmr_voter_seq_item extends uvm_sequence_item;
    `uvm_object_utils(tmr_voter_seq_item)

    // 3 核心 6 通道输入
    rand bit       ch0_core1;  // core1_ready
    rand bit       ch0_core2;  // core2_ready
    rand bit       ch0_core3;  // core3_ready

    rand bit       ch1_core1;  // core1_boot_valid
    rand bit       ch1_core2;  // core2_boot_valid
    rand bit       ch1_core3;  // core3_boot_valid

    rand bit       ch2_core1;  // core1_exit_valid
    rand bit       ch2_core2;  // core2_exit_valid
    rand bit       ch2_core3;  // core3_exit_valid

    rand bit [7:0] ch3_core1;  // core1_exit_code
    rand bit [7:0] ch3_core2;  // core2_exit_code
    rand bit [7:0] ch3_core3;  // core3_exit_code

    rand bit       ch4_core1;  // core1_print_valid
    rand bit       ch4_core2;  // core2_print_valid
    rand bit       ch4_core3;  // core3_print_valid

    rand bit [31:0] ch5_core1; // core1_print_data
    rand bit [31:0] ch5_core2; // core2_print_data
    rand bit [31:0] ch5_core3; // core3_print_data

    // 故障注入控制
    rand bit       fault_inject_en;
    rand bit [2:0] fault_target_ch;
    rand bit [2:0] fault_target_core;
    rand bit       fault_inject_override;

    // 约束: 故障注入通道范围 0-5
    constraint c_fault_ch {
        fault_target_ch inside {0, 1, 2, 3, 4, 5};
    }

    // 约束: 故障注入核心范围 1-3
    constraint c_fault_core {
        fault_target_core inside {1, 2, 3};
    }

    // 单点故障约束 (只有 1 个核心与其他核心不同)
    constraint c_single_fault_ch0 {
        (ch0_core1 == ch0_core2) || (ch0_core1 == ch0_core3) || (ch0_core2 == ch0_core3);
    }

    function new(string name = "tmr_voter_seq_item");
        super.new(name);
    endfunction : new

    // 计算参考投票结果: voted = (c1&c2)|(c1&c3)|(c2&c3)
    function bit majority_1bit(bit c1, bit c2, bit c3);
        return (c1 & c2) | (c1 & c3) | (c2 & c3);
    endfunction : majority_1bit

    function bit [7:0] majority_8bit(bit [7:0] c1, bit [7:0] c2, bit [7:0] c3);
        return (c1 & c2) | (c1 & c3) | (c2 & c3);
    endfunction : majority_8bit

    function bit [31:0] majority_32bit(bit [31:0] c1, bit [31:0] c2, bit [31:0] c3);
        return (c1 & c2) | (c1 & c3) | (c2 & c3);
    endfunction : majority_32bit

    // 获取预期的投票结果
    function void get_expected_voted(
        output bit       exp_ch0,
        output bit       exp_ch1,
        output bit       exp_ch2,
        output bit [7:0] exp_ch3,
        output bit       exp_ch4,
        output bit [31:0] exp_ch5
    );
        exp_ch0 = majority_1bit(ch0_core1, ch0_core2, ch0_core3);
        exp_ch1 = majority_1bit(ch1_core1, ch1_core2, ch1_core3);
        exp_ch2 = majority_1bit(ch2_core1, ch2_core2, ch2_core3);
        exp_ch3 = majority_8bit(ch3_core1, ch3_core2, ch3_core3);
        exp_ch4 = majority_1bit(ch4_core1, ch4_core2, ch4_core3);
        exp_ch5 = majority_32bit(ch5_core1, ch5_core2, ch5_core3);
    endfunction : get_expected_voted

    // 检测是否为单点故障场景
    function bit is_single_fault();
        // ch0 单点故障检测
        if ((ch0_core1 != ch0_core2) && (ch0_core2 == ch0_core3)) return 1;
        if ((ch0_core2 != ch0_core1) && (ch0_core1 == ch0_core3)) return 1;
        if ((ch0_core3 != ch0_core1) && (ch0_core1 == ch0_core2)) return 1;
        return 0;
    endfunction : is_single_fault

    // 检测是否为双点故障场景
    function bit is_double_fault();
        // 所有三个输入互不相同
        if ((ch0_core1 != ch0_core2) && (ch0_core1 != ch0_core3) && (ch0_core2 != ch0_core3))
            return 1;
        return 0;
    endfunction : is_double_fault

    // 字符串表示
    function string convert2string();
        return $sformatf(
            "ch0:[%0d %0d %0d] ch1:[%0d %0d %0d] ch2:[%0d %0d %0d] ch3:[%0h %0h %0h] ch4:[%0d %0d %0d] ch5:[%0h %0h %0h] fault_inject:%0d",
            ch0_core1, ch0_core2, ch0_core3,
            ch1_core1, ch1_core2, ch1_core3,
            ch2_core1, ch2_core2, ch2_core3,
            ch3_core1, ch3_core2, ch3_core3,
            ch4_core1, ch4_core2, ch4_core3,
            ch5_core1, ch5_core2, ch5_core3,
            fault_inject_en
        );
    endfunction : convert2string

endclass : tmr_voter_seq_item


//------------------------------------------------------------------------------
// tmr_voter_driver — 驱动类
//------------------------------------------------------------------------------
class tmr_voter_driver extends uvm_driver #(tmr_voter_seq_item);
    `uvm_component_utils(tmr_voter_driver)

    // 虚拟接口
    virtual tmr_voter_if vif;

    // 构造函数
    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction : new

    // build_phase: 获取接口
    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);
        if (!uvm_config_db #(virtual tmr_voter_if)::get(this, "", "vif", vif))
            `uvm_fatal("DRV", "无法获取 tmr_voter_if 虚拟接口")
    endfunction : build_phase

    // run_phase: 驱动逻辑
    virtual task run_phase(uvm_phase phase);
        `uvm_info("DRV", "驱动开始运行", UVM_LOW)
        forever begin
            // 从 sequencer 获取序列项
            seq_item_port.get_next_item(req);

            // 驱动接口信号 (通过 clocking block)
            drive_item(req);

            // 通知 sequencer 完成
            seq_item_port.item_done();
        end
    endtask : run_phase

    // 驱动单个事务
    // 注意: 使用 modport 输出而非 clocking block (cb),
    //       因为核心信号在 cb 中声明为 input (仅供 monitor 采样)
    virtual task drive_item(tmr_voter_seq_item item);
        @(vif.cb);
        // 驱动 3 核心 6 通道输入
        vif.core1_ready       = item.ch0_core1;
        vif.core2_ready       = item.ch0_core2;
        vif.core3_ready       = item.ch0_core3;

        vif.core1_boot_valid  = item.ch1_core1;
        vif.core2_boot_valid  = item.ch1_core2;
        vif.core3_boot_valid  = item.ch1_core3;

        vif.core1_exit_valid  = item.ch2_core1;
        vif.core2_exit_valid  = item.ch2_core2;
        vif.core3_exit_valid  = item.ch2_core3;

        vif.core1_exit_code   = item.ch3_core1;
        vif.core2_exit_code   = item.ch3_core2;
        vif.core3_exit_code   = item.ch3_core3;

        vif.core1_print_valid = item.ch4_core1;
        vif.core2_print_valid = item.ch4_core2;
        vif.core3_print_valid = item.ch4_core3;

        vif.core1_print_data  = item.ch5_core1;
        vif.core2_print_data  = item.ch5_core2;
        vif.core3_print_data  = item.ch5_core3;

        // 驱动故障注入控制 (这些是 cb output, 可从 cb 驱动)
        vif.cb.fault_inject_en        <= item.fault_inject_en;
        vif.cb.fault_target_ch        <= item.fault_target_ch;
        vif.cb.fault_target_core      <= item.fault_target_core;
        vif.cb.fault_inject_override  <= item.fault_inject_override;

        `uvm_info("DRV", $sformatf("驱动事务: %s", item.convert2string()), UVM_HIGH)
    endtask : drive_item

endclass : tmr_voter_driver
