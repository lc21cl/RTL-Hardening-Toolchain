//------------------------------------------------------------------------------
// tmr_voter_ral_model.sv — UVM 寄存器模型 (RAL)
//
// 寄存器映射:
//   偏移 0x00: TMR_CTRL      (32-bit, 读写, 使能控制)
//   偏移 0x04: TMR_STATUS    (32-bit, 读写, 状态标志)
//   偏移 0x10: ERR_CNT_CH0   (16-bit, 只读)
//   偏移 0x12: ERR_CNT_CH1   (16-bit, 只读)
//   偏移 0x14: ERR_CNT_CH2   (16-bit, 只读)
//   偏移 0x16: ERR_CNT_CH3   (16-bit, 只读)
//   偏移 0x18: ERR_CNT_CH4   (16-bit, 只读)
//   偏移 0x1A: ERR_CNT_CH5   (16-bit, 只读)
//   偏移 0x20: TMR_CYCLES    (32-bit, 只读)
//   偏移 0x30: FAULT_INJECT  (32-bit, 读写, 故障注入)
//   偏移 0x40: PIPELINE_CTRL (32-bit, 读写, Pipeline 控制)
//------------------------------------------------------------------------------

import uvm_pkg::*;
`include "uvm_macros.svh"

//------------------------------------------------------------------------------
// 各个寄存器类
//------------------------------------------------------------------------------

// TMR_CTRL — 使能控制寄存器
class tmr_ctrl_reg extends uvm_reg;
    `uvm_object_utils(tmr_ctrl_reg)

    rand uvm_reg_field tmr_en;       // [0]    TMR 全局使能
    rand uvm_reg_field ch0_en;       // [1]    通道 0 使能
    rand uvm_reg_field ch1_en;       // [2]    通道 1 使能
    rand uvm_reg_field ch2_en;       // [3]    通道 2 使能
    rand uvm_reg_field ch3_en;       // [4]    通道 3 使能
    rand uvm_reg_field ch4_en;       // [5]    通道 4 使能
    rand uvm_reg_field ch5_en;       // [6]    通道 5 使能
    rand uvm_reg_field fault_inject_mode; // [15:8] 故障注入模式
    rand uvm_reg_field reserved;     // [31:16] 保留

    function new(string name = "tmr_ctrl_reg");
        super.new(name, 32, UVM_NO_COVERAGE);
    endfunction : new

    virtual function void build();
        tmr_en           = uvm_reg_field::type_id::create("tmr_en");
        ch0_en           = uvm_reg_field::type_id::create("ch0_en");
        ch1_en           = uvm_reg_field::type_id::create("ch1_en");
        ch2_en           = uvm_reg_field::type_id::create("ch2_en");
        ch3_en           = uvm_reg_field::type_id::create("ch3_en");
        ch4_en           = uvm_reg_field::type_id::create("ch4_en");
        ch5_en           = uvm_reg_field::type_id::create("ch5_en");
        fault_inject_mode = uvm_reg_field::type_id::create("fault_inject_mode");
        reserved         = uvm_reg_field::type_id::create("reserved");

        tmr_en.configure(this,  1,  0, "RW", 0, 1'h1, 1, 0, 0);
        ch0_en.configure(this,  1,  1, "RW", 0, 1'h1, 1, 0, 0);
        ch1_en.configure(this,  1,  2, "RW", 0, 1'h1, 1, 0, 0);
        ch2_en.configure(this,  1,  3, "RW", 0, 1'h1, 1, 0, 0);
        ch3_en.configure(this,  1,  4, "RW", 0, 1'h1, 1, 0, 0);
        ch4_en.configure(this,  1,  5, "RW", 0, 1'h1, 1, 0, 0);
        ch5_en.configure(this,  1,  6, "RW", 0, 1'h1, 1, 0, 0);
        fault_inject_mode.configure(this, 8,  8, "RW", 0, 8'h00, 1, 0, 0);
        reserved.configure(this, 16, 16, "RW", 0, 16'h0000, 0, 0, 0);
    endfunction : build
endclass : tmr_ctrl_reg


// TMR_STATUS — 状态标志寄存器
class tmr_status_reg extends uvm_reg;
    `uvm_object_utils(tmr_status_reg)

    rand uvm_reg_field voter_ready;    // [0]    表决器就绪
    rand uvm_reg_field fault_detected; // [1]    检测到故障
    rand uvm_reg_field single_fault;   // [2]    单点故障标志
    rand uvm_reg_field double_fault;   // [3]    双点故障标志
    rand uvm_reg_field chan0_mismatch;  // [8]    通道 0 不一致
    rand uvm_reg_field chan1_mismatch;  // [9]    通道 1 不一致
    rand uvm_reg_field chan2_mismatch;  // [10]   通道 2 不一致
    rand uvm_reg_field chan3_mismatch;  // [11]   通道 3 不一致
    rand uvm_reg_field chan4_mismatch;  // [12]   通道 4 不一致
    rand uvm_reg_field chan5_mismatch;  // [13]   通道 5 不一致
    rand uvm_reg_field reserved;

    function new(string name = "tmr_status_reg");
        super.new(name, 32, UVM_NO_COVERAGE);
    endfunction : new

    virtual function void build();
        voter_ready    = uvm_reg_field::type_id::create("voter_ready");
        fault_detected = uvm_reg_field::type_id::create("fault_detected");
        single_fault   = uvm_reg_field::type_id::create("single_fault");
        double_fault   = uvm_reg_field::type_id::create("double_fault");
        chan0_mismatch = uvm_reg_field::type_id::create("chan0_mismatch");
        chan1_mismatch = uvm_reg_field::type_id::create("chan1_mismatch");
        chan2_mismatch = uvm_reg_field::type_id::create("chan2_mismatch");
        chan3_mismatch = uvm_reg_field::type_id::create("chan3_mismatch");
        chan4_mismatch = uvm_reg_field::type_id::create("chan4_mismatch");
        chan5_mismatch = uvm_reg_field::type_id::create("chan5_mismatch");
        reserved       = uvm_reg_field::type_id::create("reserved");

        voter_ready.configure(this,    1,  0, "RO", 0, 1'h0, 1, 0, 0);
        fault_detected.configure(this, 1,  1, "RO", 0, 1'h0, 1, 0, 0);
        single_fault.configure(this,   1,  2, "RO", 0, 1'h0, 1, 0, 0);
        double_fault.configure(this,   1,  3, "RO", 0, 1'h0, 1, 0, 0);
        chan0_mismatch.configure(this, 1,  8, "RO", 0, 1'h0, 1, 0, 0);
        chan1_mismatch.configure(this, 1,  9, "RO", 0, 1'h0, 1, 0, 0);
        chan2_mismatch.configure(this, 1, 10, "RO", 0, 1'h0, 1, 0, 0);
        chan3_mismatch.configure(this, 1, 11, "RO", 0, 1'h0, 1, 0, 0);
        chan4_mismatch.configure(this, 1, 12, "RO", 0, 1'h0, 1, 0, 0);
        chan5_mismatch.configure(this, 1, 13, "RO", 0, 1'h0, 1, 0, 0);
        reserved.configure(this, 18, 14, "RO", 0, 18'h0, 0, 0, 0);
    endfunction : build
endclass : tmr_status_reg


// ERR_CNT_CH0 ~ ERR_CNT_CH5 — 错误计数器 (16-bit, 只读)
class err_cnt_reg extends uvm_reg;
    `uvm_object_utils(err_cnt_reg)

    rand uvm_reg_field count_value;

    function new(string name = "err_cnt_reg");
        super.new(name, 16, UVM_NO_COVERAGE);
    endfunction : new

    virtual function void build();
        count_value = uvm_reg_field::type_id::create("count_value");
        count_value.configure(this, 16, 0, "RO", 0, 16'h0000, 1, 0, 0);
    endfunction : build
endclass : err_cnt_reg


// TMR_CYCLES — 总周期计数器 (32-bit, 只读)
class tmr_cycles_reg extends uvm_reg;
    `uvm_object_utils(tmr_cycles_reg)

    rand uvm_reg_field cycle_count;

    function new(string name = "tmr_cycles_reg");
        super.new(name, 32, UVM_NO_COVERAGE);
    endfunction : new

    virtual function void build();
        cycle_count = uvm_reg_field::type_id::create("cycle_count");
        cycle_count.configure(this, 32, 0, "RO", 0, 32'h00000000, 1, 0, 0);
    endfunction : build
endclass : tmr_cycles_reg


// FAULT_INJECT — 故障注入寄存器
class fault_inject_reg extends uvm_reg;
    `uvm_object_utils(fault_inject_reg)

    rand uvm_reg_field inject_en;       // [0]    注入使能
    rand uvm_reg_field target_ch;       // [2:1]  目标通道 0-5
    rand uvm_reg_field target_core;     // [4:3]  目标核心 1-3
    rand uvm_reg_field override_val;    // [5]    覆写值
    rand uvm_reg_field inject_once;      // [6]    单次注入模式
    rand uvm_reg_field reserved;

    function new(string name = "fault_inject_reg");
        super.new(name, 32, UVM_NO_COVERAGE);
    endfunction : new

    virtual function void build();
        inject_en     = uvm_reg_field::type_id::create("inject_en");
        target_ch     = uvm_reg_field::type_id::create("target_ch");
        target_core   = uvm_reg_field::type_id::create("target_core");
        override_val  = uvm_reg_field::type_id::create("override_val");
        inject_once   = uvm_reg_field::type_id::create("inject_once");
        reserved      = uvm_reg_field::type_id::create("reserved");

        inject_en.configure(this,    1,  0, "RW", 0, 1'h0, 1, 0, 0);
        target_ch.configure(this,    2,  1, "RW", 0, 2'h0, 1, 0, 0);
        target_core.configure(this,  2,  3, "RW", 0, 2'h0, 1, 0, 0);
        override_val.configure(this, 1,  5, "RW", 0, 1'h0, 1, 0, 0);
        inject_once.configure(this,  1,  6, "RW", 0, 1'h0, 1, 0, 0);
        reserved.configure(this,    25,  7, "RW", 0, 25'h0, 0, 0, 0);
    endfunction : build
endclass : fault_inject_reg


//------------------------------------------------------------------------------
// PIPELINE_CTRL — Pipeline 控制寄存器 (v1.1 新增)
// 偏移 0x40: PIPELINE_CTRL (32-bit, RW)
//   [0]    PIPELINE_ENABLE — Pipeline 使能 (0=直通, 1=寄存器)
//   [31:1] reserved
//------------------------------------------------------------------------------
class pipeline_ctrl_reg extends uvm_reg;
    `uvm_object_utils(pipeline_ctrl_reg)

    rand uvm_reg_field pipeline_enable;
    rand uvm_reg_field reserved;

    function new(string name = "pipeline_ctrl_reg");
        super.new(name, 32, UVM_NO_COVERAGE);
    endfunction : new

    virtual function void build();
        pipeline_enable = uvm_reg_field::type_id::create("pipeline_enable");
        reserved        = uvm_reg_field::type_id::create("reserved");

        pipeline_enable.configure(this, 1,  0, "RW", 0, 1'h1, 1, 0, 0);
        reserved.configure(this,      31,  1, "RO", 0, 31'h0, 0, 0, 0);
    endfunction : build
endclass : pipeline_ctrl_reg


//------------------------------------------------------------------------------
// tmr_voter_reg_block — 寄存器块 (基地址 0x0000)
//------------------------------------------------------------------------------
class tmr_voter_reg_block extends uvm_reg_block;
    `uvm_object_utils(tmr_voter_reg_block)

    rand tmr_ctrl_reg      tmr_ctrl;
    rand tmr_status_reg    tmr_status;
    rand err_cnt_reg       err_cnt_ch0;
    rand err_cnt_reg       err_cnt_ch1;
    rand err_cnt_reg       err_cnt_ch2;
    rand err_cnt_reg       err_cnt_ch3;
    rand err_cnt_reg       err_cnt_ch4;
    rand err_cnt_reg       err_cnt_ch5;
    rand tmr_cycles_reg    tmr_cycles;
    rand fault_inject_reg  fault_inject;
    rand pipeline_ctrl_reg pipeline_ctrl;

    function new(string name = "tmr_voter_reg_block");
        super.new(name, UVM_NO_COVERAGE);
    endfunction : new

    virtual function void build();
        // 创建寄存器实例
        tmr_ctrl     = tmr_ctrl_reg::type_id::create("tmr_ctrl");
        tmr_status   = tmr_status_reg::type_id::create("tmr_status");
        err_cnt_ch0  = err_cnt_reg::type_id::create("err_cnt_ch0");
        err_cnt_ch1  = err_cnt_reg::type_id::create("err_cnt_ch1");
        err_cnt_ch2  = err_cnt_reg::type_id::create("err_cnt_ch2");
        err_cnt_ch3  = err_cnt_reg::type_id::create("err_cnt_ch3");
        err_cnt_ch4  = err_cnt_reg::type_id::create("err_cnt_ch4");
        err_cnt_ch5  = err_cnt_reg::type_id::create("err_cnt_ch5");
        tmr_cycles   = tmr_cycles_reg::type_id::create("tmr_cycles");
        fault_inject = fault_inject_reg::type_id::create("fault_inject");
        pipeline_ctrl = pipeline_ctrl_reg::type_id::create("pipeline_ctrl");

        // 构建寄存器字段
        tmr_ctrl.build();
        tmr_status.build();
        err_cnt_ch0.build();
        err_cnt_ch1.build();
        err_cnt_ch2.build();
        err_cnt_ch3.build();
        err_cnt_ch4.build();
        err_cnt_ch5.build();
        tmr_cycles.build();
        fault_inject.build();
        pipeline_ctrl.build();

        // 映射到地址空间
        default_map = create_map("default_map", 32'h0000, 4, UVM_LITTLE_ENDIAN);

        default_map.add_reg(tmr_ctrl,     32'h0000, "RW");
        default_map.add_reg(tmr_status,   32'h0004, "RO");
        default_map.add_reg(err_cnt_ch0,  32'h0010, "RO");
        default_map.add_reg(err_cnt_ch1,  32'h0012, "RO");
        default_map.add_reg(err_cnt_ch2,  32'h0014, "RO");
        default_map.add_reg(err_cnt_ch3,  32'h0016, "RO");
        default_map.add_reg(err_cnt_ch4,  32'h0018, "RO");
        default_map.add_reg(err_cnt_ch5,  32'h001A, "RO");
        default_map.add_reg(tmr_cycles,   32'h0020, "RO");
        default_map.add_reg(fault_inject, 32'h0030, "RW");
        default_map.add_reg(pipeline_ctrl, 32'h0040, "RW");

        // 锁存模型
        lock_model();
    endfunction : build
endclass : tmr_voter_reg_block
