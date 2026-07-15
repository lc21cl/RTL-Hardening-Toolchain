//------------------------------------------------------------------------------
// tb_tmr_voter_uvm.sv — TMR Voter UVM 顶层测试台
// 实例化 DUT (cpu_core_tmr_uvm), 实例化接口, 运行 UVM 测试
//------------------------------------------------------------------------------

// 测试包裹器: 封装 DUT 并暴露内部核心信号
module tmr_voter_wrapper (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        start,

    // rom_init 扇入
    input  logic        rom_init_write_enable,
    input  logic [31:0] rom_init_write_addr,
    input  logic [31:0] rom_init_write_data,

    // mmio_in 扇入
    input  logic        mmio_in_valid,
    input  logic [7:0]  mmio_in_data,
    output logic        mmio_in_ready,

    // mmio_out 输出表决
    output logic        mmio_out_boot_valid,
    output logic        mmio_out_exit_valid,
    output logic [7:0]  mmio_out_exit_code,
    output logic        mmio_out_print_valid,
    output logic [31:0] mmio_out_print_data,

    // ====== 内部核心信号暴露 (用于故障注入和监视) ======
    // ch-0: ready
    output logic        core1_ready,
    output logic        core2_ready,
    output logic        core3_ready,
    // ch-1: boot_valid
    output logic        core1_boot_valid,
    output logic        core2_boot_valid,
    output logic        core3_boot_valid,
    // ch-2: exit_valid
    output logic        core1_exit_valid,
    output logic        core2_exit_valid,
    output logic        core3_exit_valid,
    // ch-3: exit_code
    output logic [7:0]  core1_exit_code,
    output logic [7:0]  core2_exit_code,
    output logic [7:0]  core3_exit_code,
    // ch-4: print_valid
    output logic        core1_print_valid,
    output logic        core2_print_valid,
    output logic        core3_print_valid,
    // ch-5: print_data
    output logic [31:0] core1_print_data,
    output logic [31:0] core2_print_data,
    output logic [31:0] core3_print_data,

    // 错误计数器
    output logic [15:0] error_count_ch0,
    output logic [15:0] error_count_ch1,
    output logic [15:0] error_count_ch2,
    output logic [15:0] error_count_ch3,
    output logic [15:0] error_count_ch4,
    output logic [15:0] error_count_ch5,
    output logic [31:0] total_cycles
);
    // DUT 内部信号 (被 cpu_core_tmr_uvm 驱动)
    logic               dut_mmio_in_ready;
    logic               dut_mmio_out_boot_valid;
    logic               dut_mmio_out_exit_valid;
    logic [7:0]         dut_mmio_out_exit_code;
    logic               dut_mmio_out_print_valid;
    logic [31:0]        dut_mmio_out_print_data;

    // 实例化 DUT
    cpu_core_tmr_uvm dut (
        .clk                  (clk),
        .start                (start),
        .rom_init_write_enable(rom_init_write_enable),
        .rom_init_write_addr  (rom_init_write_addr),
        .rom_init_write_data  (rom_init_write_data),
        .mmio_in_valid        (mmio_in_valid),
        .mmio_in_data         (mmio_in_data),
        .mmio_in_ready        (dut_mmio_in_ready),
        .mmio_out_boot_valid  (dut_mmio_out_boot_valid),
        .mmio_out_exit_valid  (dut_mmio_out_exit_valid),
        .mmio_out_exit_code   (dut_mmio_out_exit_code),
        .mmio_out_print_valid (dut_mmio_out_print_valid),
        .mmio_out_print_data  (dut_mmio_out_print_data)
    );

    // 将 DUT 输出连接到外部端口
    assign mmio_in_ready       = dut_mmio_in_ready;
    assign mmio_out_boot_valid = dut_mmio_out_boot_valid;
    assign mmio_out_exit_valid = dut_mmio_out_exit_valid;
    assign mmio_out_exit_code  = dut_mmio_out_exit_code;
    assign mmio_out_print_valid = dut_mmio_out_print_valid;
    assign mmio_out_print_data = dut_mmio_out_print_data;

    // 内部核心信号通过层次引用暴露
    // 注意: 这些信号在 cpu_core_tmr_uvm 内部是 wire/reg,
    //       通过 hierarchical reference 连接
    assign core1_ready        = dut.core1_ready;
    assign core2_ready        = dut.core2_ready;
    assign core3_ready        = dut.core3_ready;

    assign core1_boot_valid   = dut.core1_boot_valid;
    assign core2_boot_valid   = dut.core2_boot_valid;
    assign core3_boot_valid   = dut.core3_boot_valid;

    assign core1_exit_valid   = dut.core1_exit_valid;
    assign core2_exit_valid   = dut.core2_exit_valid;
    assign core3_exit_valid   = dut.core3_exit_valid;

    assign core1_exit_code    = dut.core1_exit_code;
    assign core2_exit_code    = dut.core2_exit_code;
    assign core3_exit_code    = dut.core3_exit_code;

    assign core1_print_valid  = dut.core1_print_valid;
    assign core2_print_valid  = dut.core2_print_valid;
    assign core3_print_valid  = dut.core3_print_valid;

    assign core1_print_data   = dut.core1_print_data;
    assign core2_print_data   = dut.core2_print_data;
    assign core3_print_data   = dut.core3_print_data;

    // 错误计数器
    assign error_count_ch0    = dut.error_count_ch0;
    assign error_count_ch1    = dut.error_count_ch1;
    assign error_count_ch2    = dut.error_count_ch2;
    assign error_count_ch3    = dut.error_count_ch3;
    assign error_count_ch4    = dut.error_count_ch4;
    assign error_count_ch5    = dut.error_count_ch5;
    assign total_cycles       = dut.total_cycles;

endmodule : tmr_voter_wrapper


// ========================================================================
// 顶层测试台
// ========================================================================
module tb_tmr_voter_uvm;

    import uvm_pkg::*;
    `include "uvm_macros.svh"

    // 导入 TMR Voter UVM 包
    import tmr_voter_pkg::*;

    // ========================================================================
    // 信号声明
    // ========================================================================
    logic        clk;
    logic        rst_n;
    logic        start;
    logic        rom_init_write_enable;
    logic [31:0] rom_init_write_addr;
    logic [31:0] rom_init_write_data;
    logic        mmio_in_valid;
    logic [7:0]  mmio_in_data;

    // 输出信号
    logic        mmio_in_ready;
    logic        mmio_out_boot_valid;
    logic        mmio_out_exit_valid;
    logic [7:0]  mmio_out_exit_code;
    logic        mmio_out_print_valid;
    logic [31:0] mmio_out_print_data;

    // 内部核心信号 (来自 wrapper)
    logic        core1_ready, core2_ready, core3_ready;
    logic        core1_boot_valid, core2_boot_valid, core3_boot_valid;
    logic        core1_exit_valid, core2_exit_valid, core3_exit_valid;
    logic [7:0]  core1_exit_code, core2_exit_code, core3_exit_code;
    logic        core1_print_valid, core2_print_valid, core3_print_valid;
    logic [31:0] core1_print_data, core2_print_data, core3_print_data;

    // 错误计数器
    logic [15:0] error_count_ch0, error_count_ch1, error_count_ch2;
    logic [15:0] error_count_ch3, error_count_ch4, error_count_ch5;
    logic [31:0] total_cycles;

    // ========================================================================
    // 接口实例化
    // ========================================================================
    tmr_voter_if vif (
        .clk   (clk),
        .rst_n (rst_n)
    );

    // ========================================================================
    // DUT 包裹器实例化
    // ========================================================================
    tmr_voter_wrapper dut_wrapper (
        .clk                  (clk),
        .rst_n                (rst_n),
        .start                (start),
        .rom_init_write_enable(rom_init_write_enable),
        .rom_init_write_addr  (rom_init_write_addr),
        .rom_init_write_data  (rom_init_write_data),
        .mmio_in_valid        (mmio_in_valid),
        .mmio_in_data         (mmio_in_data),
        .mmio_in_ready        (mmio_in_ready),
        .mmio_out_boot_valid  (mmio_out_boot_valid),
        .mmio_out_exit_valid  (mmio_out_exit_valid),
        .mmio_out_exit_code   (mmio_out_exit_code),
        .mmio_out_print_valid (mmio_out_print_valid),
        .mmio_out_print_data  (mmio_out_print_data),

        .core1_ready        (core1_ready),
        .core2_ready        (core2_ready),
        .core3_ready        (core3_ready),
        .core1_boot_valid   (core1_boot_valid),
        .core2_boot_valid   (core2_boot_valid),
        .core3_boot_valid   (core3_boot_valid),
        .core1_exit_valid   (core1_exit_valid),
        .core2_exit_valid   (core2_exit_valid),
        .core3_exit_valid   (core3_exit_valid),
        .core1_exit_code    (core1_exit_code),
        .core2_exit_code    (core2_exit_code),
        .core3_exit_code    (core3_exit_code),
        .core1_print_valid  (core1_print_valid),
        .core2_print_valid  (core2_print_valid),
        .core3_print_valid  (core3_print_valid),
        .core1_print_data   (core1_print_data),
        .core2_print_data   (core2_print_data),
        .core3_print_data   (core3_print_data),

        .error_count_ch0    (error_count_ch0),
        .error_count_ch1    (error_count_ch1),
        .error_count_ch2    (error_count_ch2),
        .error_count_ch3    (error_count_ch3),
        .error_count_ch4    (error_count_ch4),
        .error_count_ch5    (error_count_ch5),
        .total_cycles       (total_cycles)
    );

    // ========================================================================
    // 接口信号连接
    // ========================================================================
    // DUT 端口连接
    assign vif.start                 = start;
    assign vif.rom_init_write_enable = rom_init_write_enable;
    assign vif.rom_init_write_addr   = rom_init_write_addr;
    assign vif.rom_init_write_data   = rom_init_write_data;
    assign vif.mmio_in_valid         = mmio_in_valid;
    assign vif.mmio_in_data          = mmio_in_data;
    assign vif.mmio_in_ready         = mmio_in_ready;
    assign vif.mmio_out_boot_valid   = mmio_out_boot_valid;
    assign vif.mmio_out_exit_valid   = mmio_out_exit_valid;
    assign vif.mmio_out_exit_code    = mmio_out_exit_code;
    assign vif.mmio_out_print_valid  = mmio_out_print_valid;
    assign vif.mmio_out_print_data   = mmio_out_print_data;

    // 核心内部信号和错误计数器由 UVM driver 直接驱动,
    // 此处不再连续赋值以避免多驱动冲突

    // ========================================================================
    // 时钟生成
    // ========================================================================
    initial begin
        clk = 0;
        forever #5 clk = ~clk;  // 100MHz
    end

    // ========================================================================
    // 复位和初始化
    // ========================================================================
    initial begin
        rst_n = 0;
        start = 0;
        rom_init_write_enable = 0;
        rom_init_write_addr   = 32'h0;
        rom_init_write_data   = 32'h0;
        mmio_in_valid = 0;
        mmio_in_data  = 8'h00;

        // 驱动内部核心信号初始值 (通过接口驱动, 但 DUT 内部 core 会驱动这些信号)
        // UVM driver 会通过 vif.driver_mp 驱动 core* 信号

        // 复位保持 100ns
        #100;
        rst_n = 1;
        start = 1;
        #20;
        start = 0;

        // 传递虚拟接口给 UVM
        uvm_config_db #(virtual tmr_voter_if)::set(null, "uvm_test_top.env", "vif", vif);
        uvm_config_db #(virtual tmr_voter_if)::set(null, "uvm_test_top.env.agent", "vif", vif);
        uvm_config_db #(virtual tmr_voter_if)::set(null, "uvm_test_top.env.agent.driver", "vif", vif);
        uvm_config_db #(virtual tmr_voter_if)::set(null, "uvm_test_top.env.agent.monitor", "vif", vif);

        // 启动 UVM 测试
        run_test();
    end

    // ========================================================================
    // VCD 波形转储 (调试用)
    // ========================================================================
    initial begin
        $dumpfile("tmr_voter_uvm.vcd");
        $dumpvars(0, tb_tmr_voter_uvm);
    end

endmodule : tb_tmr_voter_uvm
