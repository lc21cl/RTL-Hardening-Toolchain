//------------------------------------------------------------------------------
// tmr_voter_env.sv — TMR Voter UVM Environment
// 实例化 agent (driver + monitor + sequencer), scoreboard
// 连接 monitor 到 scoreboard 的 analysis port
//------------------------------------------------------------------------------

// TMR Voter Agent — 包含 driver, monitor, sequencer
class tmr_voter_agent extends uvm_agent;
    `uvm_component_utils(tmr_voter_agent)

    tmr_voter_driver     driver;
    tmr_voter_monitor    monitor;
    uvm_sequencer #(tmr_voter_seq_item) sequencer;

    // 虚拟接口
    virtual tmr_voter_if vif;

    // 构造函数
    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction : new

    // build_phase
    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);

        // 获取接口
        if (!uvm_config_db #(virtual tmr_voter_if)::get(this, "", "vif", vif))
            `uvm_fatal("AGENT", "无法获取 tmr_voter_if 虚拟接口")

        // 创建子组件
        driver    = tmr_voter_driver::type_id::create("driver", this);
        monitor   = tmr_voter_monitor::type_id::create("monitor", this);
        sequencer = uvm_sequencer #(tmr_voter_seq_item)::type_id::create("sequencer", this);

        // 配置子组件
        uvm_config_db #(virtual tmr_voter_if)::set(this, "driver",   "vif", vif);
        uvm_config_db #(virtual tmr_voter_if)::set(this, "monitor",  "vif", vif);
    endfunction : build_phase

    // connect_phase
    virtual function void connect_phase(uvm_phase phase);
        super.connect_phase(phase);
        // 连接 driver 到 sequencer
        driver.seq_item_port.connect(sequencer.seq_item_export);
    endfunction : connect_phase

endclass : tmr_voter_agent


//------------------------------------------------------------------------------
// tmr_voter_env — 顶层环境
//------------------------------------------------------------------------------
class tmr_voter_env extends uvm_env;
    `uvm_component_utils(tmr_voter_env)

    tmr_voter_agent      agent;
    tmr_voter_scoreboard scoreboard;

    // 寄存器模型
    tmr_voter_reg_block reg_model;

    // 虚拟接口
    virtual tmr_voter_if vif;

    // 构造函数
    function new(string name, uvm_component parent);
        super.new(name, parent);
    endfunction : new

    // build_phase
    virtual function void build_phase(uvm_phase phase);
        super.build_phase(phase);

        // 获取接口
        if (!uvm_config_db #(virtual tmr_voter_if)::get(this, "", "vif", vif))
            `uvm_fatal("ENV", "无法获取 tmr_voter_if 虚拟接口")

        // 创建 agent
        agent = tmr_voter_agent::type_id::create("agent", this);

        // 创建 scoreboard
        scoreboard = tmr_voter_scoreboard::type_id::create("scoreboard", this);

        // 创建寄存器模型
        reg_model = tmr_voter_reg_block::type_id::create("reg_model");
        reg_model.build();
        reg_model.lock_model();
        // 默认启用 pipeline
        reg_model.pipeline_ctrl.pipeline_enable.set(1);

        // 包含 RAL 覆盖率收集 (启用 pipeline 寄存器覆盖)
        uvm_reg::include_coverage("*", UVM_NO_COVERAGE);
    endfunction : build_phase

    // connect_phase: 连接 monitor 到 scoreboard
    virtual function void connect_phase(uvm_phase phase);
        super.connect_phase(phase);
        // monitor 的 analysis port -> scoreboard 的 analysis imp
        agent.monitor.mon_ap.connect(scoreboard.sb_imp);
    endfunction : connect_phase

    // end_of_elaboration_phase
    virtual function void end_of_elaboration_phase(uvm_phase phase);
        super.end_of_elaboration_phase(phase);
        `uvm_info("ENV", "TMR Voter 环境构建完成", UVM_LOW)
    endfunction : end_of_elaboration_phase

endclass : tmr_voter_env
