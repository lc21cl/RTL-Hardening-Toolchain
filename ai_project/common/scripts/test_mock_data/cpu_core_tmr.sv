module cpu_core_tmr_core (
    input   logic                   start,
    input   logic                   clk,

    mem_init_if.sink                rom_init,
    mmio_out_if.source             mmio_out,
    mmio_in_if.sink                mmio_in
);

    reg alu_valid_tmr_1;
    reg alu_valid_tmr_2;
    reg alu_valid_tmr_3;
    reg[31:0] aluresult_e_tmr_1;
    reg[31:0] aluresult_e_tmr_2;
    reg[31:0] aluresult_e_tmr_3;
    reg[31:0] csr_wdata_e_tmr_1;
    reg[31:0] csr_wdata_e_tmr_2;
    reg[31:0] csr_wdata_e_tmr_3;
    reg[31:0] csr_wdata_m1_tmr_1;
    reg[31:0] csr_wdata_m1_tmr_2;
    reg[31:0] csr_wdata_m1_tmr_3;
    reg div_valid_tmr_1;
    reg div_valid_tmr_2;
    reg div_valid_tmr_3;
    reg[31:0] divresult_e_tmr_1;
    reg[31:0] divresult_e_tmr_2;
    reg[31:0] divresult_e_tmr_3;
    reg[31:0] immext_d_tmr_1;
    reg[31:0] immext_d_tmr_2;
    reg[31:0] immext_d_tmr_3;
    reg instret_w_tmr_1;
    reg instret_w_tmr_2;
    reg instret_w_tmr_3;
    reg[31:0] memresult_m2_tmr_1;
    reg[31:0] memresult_m2_tmr_2;
    reg[31:0] memresult_m2_tmr_3;
    reg[31:0] mepc_tmr_1;
    reg[31:0] mepc_tmr_2;
    reg[31:0] mepc_tmr_3;
    reg mispredict_tmr_1;
    reg mispredict_tmr_2;
    reg mispredict_tmr_3;
    reg mul_valid_tmr_1;
    reg mul_valid_tmr_2;
    reg mul_valid_tmr_3;
    reg[31:0] mulresult_e_tmr_1;
    reg[31:0] mulresult_e_tmr_2;
    reg[31:0] mulresult_e_tmr_3;
    reg[31:0] pc_d_tmr_1;
    reg[31:0] pc_d_tmr_2;
    reg[31:0] pc_d_tmr_3;
    reg[31:0] pc_e_tmr_1;
    reg[31:0] pc_e_tmr_2;
    reg[31:0] pc_e_tmr_3;
    reg[31:0] pc_e_reg_tmr_1;
    reg[31:0] pc_e_reg_tmr_2;
    reg[31:0] pc_e_reg_tmr_3;
    reg[31:0] pc_f_tmr_1;
    reg[31:0] pc_f_tmr_2;
    reg[31:0] pc_f_tmr_3;
    reg[31:0] pc_jump_tmr_1;
    reg[31:0] pc_jump_tmr_2;
    reg[31:0] pc_jump_tmr_3;
    reg[31:0] pc_pred_tmr_1;
    reg[31:0] pc_pred_tmr_2;
    reg[31:0] pc_pred_tmr_3;
    reg[31:0] pc_pred_d_tmr_1;
    reg[31:0] pc_pred_d_tmr_2;
    reg[31:0] pc_pred_d_tmr_3;
    reg[31:0] pcplus4_d_tmr_1;
    reg[31:0] pcplus4_d_tmr_2;
    reg[31:0] pcplus4_d_tmr_3;
    reg[31:0] pcplus4_e_tmr_1;
    reg[31:0] pcplus4_e_tmr_2;
    reg[31:0] pcplus4_e_tmr_3;
    reg[31:0] pcplus4_e_reg_tmr_1;
    reg[31:0] pcplus4_e_reg_tmr_2;
    reg[31:0] pcplus4_e_reg_tmr_3;
    reg[31:0] pcplus4_f_tmr_1;
    reg[31:0] pcplus4_f_tmr_2;
    reg[31:0] pcplus4_f_tmr_3;
    reg pred_taken_tmr_1;
    reg pred_taken_tmr_2;
    reg pred_taken_tmr_3;
    reg pred_taken_d_tmr_1;
    reg pred_taken_d_tmr_2;
    reg pred_taken_d_tmr_3;
    reg[31:0] ram_addr_tmr_1;
    reg[31:0] ram_addr_tmr_2;
    reg[31:0] ram_addr_tmr_3;
    reg[31:0] ram_read_data_tmr_1;
    reg[31:0] ram_read_data_tmr_2;
    reg[31:0] ram_read_data_tmr_3;
    reg[31:0] ram_write_data_tmr_1;
    reg[31:0] ram_write_data_tmr_2;
    reg[31:0] ram_write_data_tmr_3;
    reg[4:0] rd_d_tmr_1;
    reg[4:0] rd_d_tmr_2;
    reg[4:0] rd_d_tmr_3;
    reg[4:0] rd_e_tmr_1;
    reg[4:0] rd_e_tmr_2;
    reg[4:0] rd_e_tmr_3;
    reg[4:0] rd_m1_tmr_1;
    reg[4:0] rd_m1_tmr_2;
    reg[4:0] rd_m1_tmr_3;
    reg[4:0] rd_m2_tmr_1;
    reg[4:0] rd_m2_tmr_2;
    reg[4:0] rd_m2_tmr_3;
    reg[4:0] rd_w_tmr_1;
    reg[4:0] rd_w_tmr_2;
    reg[4:0] rd_w_tmr_3;
    reg[31:0] rdata1_d_tmr_1;
    reg[31:0] rdata1_d_tmr_2;
    reg[31:0] rdata1_d_tmr_3;
    reg[31:0] rdata2_d_tmr_1;
    reg[31:0] rdata2_d_tmr_2;
    reg[31:0] rdata2_d_tmr_3;
    reg regwrite_w_tmr_1;
    reg regwrite_w_tmr_2;
    reg regwrite_w_tmr_3;
    reg[31:0] result_m1_tmr_1;
    reg[31:0] result_m1_tmr_2;
    reg[31:0] result_m1_tmr_3;
    reg[31:0] result_m2_tmr_1;
    reg[31:0] result_m2_tmr_2;
    reg[31:0] result_m2_tmr_3;
    reg[31:0] result_w_tmr_1;
    reg[31:0] result_w_tmr_2;
    reg[31:0] result_w_tmr_3;
    reg rom_fetch_access_fault_tmr_1;
    reg rom_fetch_access_fault_tmr_2;
    reg rom_fetch_access_fault_tmr_3;
    reg[31:0] rom_fetch_addr_tmr_1;
    reg[31:0] rom_fetch_addr_tmr_2;
    reg[31:0] rom_fetch_addr_tmr_3;
    reg[31:0] rom_load_addr_tmr_1;
    reg[31:0] rom_load_addr_tmr_2;
    reg[31:0] rom_load_addr_tmr_3;
    reg[31:0] rom_load_data_tmr_1;
    reg[31:0] rom_load_data_tmr_2;
    reg[31:0] rom_load_data_tmr_3;
    reg rom_load_enable_tmr_1;
    reg rom_load_enable_tmr_2;
    reg rom_load_enable_tmr_3;
    reg[4:0] rs1_d_tmr_1;
    reg[4:0] rs1_d_tmr_2;
    reg[4:0] rs1_d_tmr_3;
    reg[4:0] rs2_d_tmr_1;
    reg[4:0] rs2_d_tmr_2;
    reg[4:0] rs2_d_tmr_3;
    reg[31:0] storedata_e_tmr_1;
    reg[31:0] storedata_e_tmr_2;
    reg[31:0] storedata_e_tmr_3;


    // ========================================================================
    // All signal declarations moved to module beginning
    // ========================================================================

    // -------- Backward signals --------
    logic [31:0]                    result_m1;
    logic [31:0]                    result_m2;
    logic                           regwrite_w;
    logic [4:0]                     rd_w;
    logic [31:0]                    result_w;
    logic                           instret_w;

    // -------- Hazard & Control signals --------
    haz_if                          hazard_bus();
    trap_if                         trap_bus();
    csr_if                          csr_bus();

    // Branch Predictor signals
    logic [31:0]                    pc_f;
    logic [31:0]                    pc_e, pc_e_reg;
    logic [31:0]                    pcplus4_e, pcplus4_e_reg;
    logic [31:0]                    pc_pred;
    logic [31:0]                    pc_jump;
    cflow_mode_t                    cflow_mode_reg;
    cflow_hint_t                    cflow_hint_reg;
    logic                           pred_taken;
    logic                           cflow_taken;
    logic                           mispredict;

    // Memory signals
    inst_t                          rom_fetch_inst;
    logic [31:0]                    rom_fetch_addr;
    logic                           rom_fetch_access_fault;
    logic                           rom_load_enable;
    logic [31:0]                    rom_load_addr;
    logic [31:0]                    rom_load_data;
    memaccess_t                     ram_access;
    logic [31:0]                    ram_addr;
    logic [3:0]                     ram_wstrb;
    logic [31:0]                    ram_write_data;
    logic [31:0]                    ram_read_data;

    // IF stage signals
    logic [31:0]                    pcplus4_f;
    trap_req_t                      trap_req_f;

    // ID stage signals
    control_bus_t                   control_bus_d;
    cflow_hint_t                    cflow_hint_d;
    logic [31:0]                    pc_d;
    logic [31:0]                    pcplus4_d;
    logic [31:0]                    pc_pred_d;
    logic                           pred_taken_d;
    logic [4:0]                     rs1_d, rs2_d, rd_d;
    logic [31:0]                    rdata1_d, rdata2_d;
    logic [31:0]                    immext_d;
    trap_req_t                      trap_req_d;

    // EX stage signals
    control_bus_t                   control_bus_e;
    logic                           ex_fire;
    logic [4:0]                     rs1_e, rs2_e, rd_e;
    logic                           alu_valid, mul_valid, div_valid;
    logic [31:0]                    aluresult_e, mulresult_e, divresult_e;
    logic [31:0]                    storedata_e;
    logic [31:0]                    csr_wdata_e;
    trap_req_t                      trap_req_e;

    // MEM1 stage signals
    control_bus_t                   control_bus_m1;
    logic [4:0]                     rs2_m1;
    logic [4:0]                     rd_m1;
    logic [31:0]                    csr_wdata_m1;
    loadsrc_t                       load_source_m1;
    logic [1:0]                     byte_offset_m1;
    trap_req_t                      trap_req_m1;

    // MEM2 stage signals
    control_bus_t                   control_bus_m2;
    logic [4:0]                     rd_m2;
    logic [31:0]                    memresult_m2;

    // CSR and Trap
    logic [31:0]                    mtvec, mepc;

    // ========================================================================
    // Unit instantiations
    // ========================================================================

    // -------- Hazard Unit --------
    hazard hazard (
        .start                      (start),
        .clk                        (clk),
        .hazard_bus                 (hazard_bus)
    );

    // -------- Trap Unit --------
    trap trap (
        .trap_bus                   (trap_bus),
        .mtvec_i                    (mtvec),
        .mepc_i                     (mepc)
    );

    // -------- CSR Unit --------
    csr csr (
        .start                      (start),
        .clk                        (clk),
        .instret                    (instret_w),
        .trap                       (trap_bus.req),
        .csr_bus                    (csr_bus),
        .mtvec_o                    (mtvec),
        .mepc_o                     (mepc)
    );

    // -------- Branch Predictor --------
    predictor predictor (
        .start                      (start),
        .clk                        (clk),

        .pc_f                       (pc_f),
        .pred_taken                 (pred_taken),
        .pred_target                (pc_pred),

        .pc_e                       (pc_e_reg),
        .cflow_mode                 (cflow_mode_reg),
        .cflow_hint                 (cflow_hint_reg),
        .cflow_taken                (cflow_taken),
        .cflow_target               (pc_jump)
    );

    // -------- Memory Blocks --------
    rom rom (
        .start                      (start),
        .clk                        (clk),

        .fetch_addr                 (rom_fetch_addr),
        .fetch_access_fault         (rom_fetch_access_fault),
        .fetch_inst                 (rom_fetch_inst),

        .load_enable                (rom_load_enable),
        .load_addr                  (rom_load_addr),
        .load_data                  (rom_load_data),

        .init                       (rom_init)
    );

    ram ram (
        .clk                        (clk),
        .access                     (ram_access),
        .addr                       (ram_addr),
        .wstrb                      (ram_wstrb),
        .write_data                 (ram_write_data),
        .read_data                  (ram_read_data)
    );

    // -------- Pipeline Stages --------
    fetch fetch (
        .start                      (start),
        .clk                        (clk),

        .pc_pred                    (pc_pred),
        .pc_jump                    (pc_jump),
        .pc_return                  (pcplus4_e_reg),
        .mispredict                 (mispredict),
        .cflow_taken                (cflow_taken),
        .pred_taken                 (pred_taken),

        .pc_f                       (pc_f),
        .pcplus4_f                  (pcplus4_f),
        .fetch_addr                 (rom_fetch_addr),

        .fetch_access_fault         (rom_fetch_access_fault),

        .trap_res                   (trap_bus.res),
        .trap_req_f                 (trap_req_f),
        .hazard_res                 (hazard_bus.res)
    );

    decode decode (
        .start                      (start),
        .clk                        (clk),

        .pc_f                       (pc_f),
        .pcplus4_f                  (pcplus4_f),
        .pc_pred_f                  (pc_pred),
        .pred_taken_f               (pred_taken),
        .fetch_inst                 (rom_fetch_inst),

        .regwrite_w                 (regwrite_w),
        .rd_w                       (rd_w),
        .result_w                   (result_w),

        .control_bus_d              (control_bus_d),
        .cflow_hint_d               (cflow_hint_d),
        .pc_d                       (pc_d),
        .pcplus4_d                  (pcplus4_d),
        .pc_pred_d                  (pc_pred_d),
        .pred_taken_d               (pred_taken_d),
        .rs1_d                      (rs1_d),
        .rs2_d                      (rs2_d),
        .rd_d                       (rd_d),
        .rdata1_d                   (rdata1_d),
        .rdata2_d                   (rdata2_d),
        .immext_d                   (immext_d),

        .trap_req_f                 (trap_req_f),
        .trap_req_d                 (trap_req_d),
        .hazard_res                 (hazard_bus.res)
    );

    execute execute (
        .start                      (start),
        .clk                        (clk),

        .control_bus_d              (control_bus_d),
        .cflow_hint_d               (cflow_hint_d),
        .pc_d                       (pc_d),
        .pcplus4_d                  (pcplus4_d),
        .pc_pred_d                  (pc_pred_d),
        .pred_taken_d               (pred_taken_d),
        .rs1_d                      (rs1_d),
        .rs2_d                      (rs2_d),
        .rd_d                       (rd_d),
        .rdata1_d                   (rdata1_d),
        .rdata2_d                   (rdata2_d),
        .immext_d                   (immext_d),

        .result_m1                  (result_m1),
        .result_m2                  (result_m2),
        .result_w                   (result_w),

        .control_bus_e              (control_bus_e),
        .pc_e                       (pc_e),
        .pcplus4_e                  (pcplus4_e),
        .rs1_e                      (rs1_e),
        .rs2_e                      (rs2_e),
        .rd_e                       (rd_e),

        .alu_valid                  (alu_valid),
        .mul_valid                  (mul_valid),
        .div_valid                  (div_valid),
        .aluresult_e                (aluresult_e),
        .mulresult_e                (mulresult_e),
        .divresult_e                (divresult_e),

        .storedata_e                (storedata_e),
        .csr_wdata_e                (csr_wdata_e),

        .pc_jump                    (pc_jump),
        .cflow_mode_reg             (cflow_mode_reg),
        .cflow_hint_reg             (cflow_hint_reg),
        .cflow_taken                (cflow_taken),
        .mispredict                 (mispredict),
        .ex_fire                    (ex_fire),

        .trap_req_d                 (trap_req_d),
        .trap_req_e                 (trap_req_e),
        .hazard_res                 (hazard_bus.res)
    );

    mem1 mem1 (
        .start                      (start),
        .clk                        (clk),

        .control_bus_e              (control_bus_e),
        .pc_e                       (pc_e),
        .pcplus4_e                  (pcplus4_e),
        .rs2_e                      (rs2_e),
        .rd_e                       (rd_e),

        .alu_valid                  (alu_valid),
        .mul_valid                  (mul_valid),
        .div_valid                  (div_valid),
        .aluresult_e                (aluresult_e),
        .mulresult_e                (mulresult_e),
        .divresult_e                (divresult_e),

        .storedata_e                (storedata_e),
        .csr_wdata_e                (csr_wdata_e),

        .result_w                   (result_w),

        .control_bus_m1             (control_bus_m1),
        .rd_m1                      (rd_m1),
        .rs2_m1                     (rs2_m1),
        .csr_wdata_m1               (csr_wdata_m1),
        .load_source_m1             (load_source_m1),
        .byte_offset_m1             (byte_offset_m1),
        .result_m1                  (result_m1),

        .rom_load_enable            (rom_load_enable),
        .rom_load_addr              (rom_load_addr),

        .ram_access                 (ram_access),
        .ram_addr                   (ram_addr),
        .ram_wstrb                  (ram_wstrb),
        .ram_write_data             (ram_write_data),

        .trap_req_e                 (trap_req_e),
        .trap_req_m1                (trap_req_m1),
        .csr_result                 (csr_bus.rdata),
        .hazard_res                 (hazard_bus.res),

        .mmio_out                   (mmio_out),
        .mmio_in                    (mmio_in)
    );

    mem2 mem2 (
        .start                      (start),
        .clk                        (clk),

        .control_bus_m1             (control_bus_m1),
        .rd_m1                      (rd_m1),
        .load_source_m1             (load_source_m1),
        .byte_offset_m1             (byte_offset_m1),
        .result_m1                  (result_m1),
        .ram_read_data              (ram_read_data),
        .rom_load_data              (rom_load_data),
        .mmio_in_valid              (mmio_in.valid),
        .mmio_in_data               (mmio_in.data),

        .control_bus_m2             (control_bus_m2),
        .rd_m2                      (rd_m2),
        .memresult_m2               (memresult_m2),
        .result_m2                  (result_m2),

        .hazard_res                 (hazard_bus.res)
    );

    writeback writeback (
        .start                      (start),
        .clk                        (clk),

        .control_bus_m2             (control_bus_m2),
        .rd_m2                      (rd_m2),
        .memresult_m2               (memresult_m2),
        .result_m2                  (result_m2),

        .regwrite_w                 (regwrite_w),
        .rd_w                       (rd_w),
        .result_w                   (result_w),
        .instret_w                  (instret_w)
    );

    // ========================================================================
    // Combinational logic connections
    // ========================================================================

    // PC and control flow registers
    always_ff @(posedge clk) begin
        if (!start) begin
            pc_e_reg                <= 32'b0;
            pcplus4_e_reg           <= 32'b0;
        end
        else begin
            pc_e_reg                <= pc_e;
            pcplus4_e_reg           <= pcplus4_e;
        end
    end

    // Hazard unit connections
    always_comb begin
        hazard_bus.req.flushflag    = trap_bus.res.flushflag || control_bus_m1.fencei;
        hazard_bus.req.mispredict   = mispredict;
        hazard_bus.req.ex_fire      = ex_fire;
        hazard_bus.req.aluop_e      = control_bus_e.aluop;
        hazard_bus.req.use_rs1_d    = control_bus_d.use_rs1;
        hazard_bus.req.use_rs2_d    = control_bus_d.use_rs2;
        hazard_bus.req.rs1_d        = rs1_d;
        hazard_bus.req.rs1_e        = rs1_e;
        hazard_bus.req.rs2_d        = rs2_d;
        hazard_bus.req.rs2_e        = rs2_e;
        hazard_bus.req.rs2_m1       = rs2_m1;
        hazard_bus.req.rd_e         = rd_e;
        hazard_bus.req.rd_m1        = rd_m1;
        hazard_bus.req.rd_m2        = rd_m2;
        hazard_bus.req.rd_w         = rd_w;
        hazard_bus.req.regwrite_m1  = control_bus_m1.regwrite;
        hazard_bus.req.regwrite_m2  = control_bus_m2.regwrite;
        hazard_bus.req.regwrite_w   = regwrite_w;
        hazard_bus.req.memaccess_e  = control_bus_e.memaccess;
        hazard_bus.req.memaccess_m1 = control_bus_m1.memaccess;
        hazard_bus.req.memaccess_m2 = control_bus_m2.memaccess;
    end

    // Trap unit connections
    always_comb begin
        trap_bus.req               = trap_req_m1;
    end

    // CSR unit connections
    always_comb begin
        csr_bus.req                = control_bus_e.csr_req;
        csr_bus.wdata              = csr_wdata_e;
    end


    // ====== TMR 表决器（仅输出端口）======
endmodule

// ============================================================
// D-004 修复: Interface-aware TMR Voter & 3-Core Wrapper
// ============================================================
// 策略:
//   - mem_init_if.sink (纯输入)        → 直接扇出到 3 个核心
//   - mmio_in_if.sink  (混合输入/输出)  → valid/data 扇出, ready 多数表决
//   - mmio_out_if.source (纯输出)      → 3 份输出分别抽样, 多数表决
//
// mem_init_if signals:  write_enable(1), write_addr(32), write_data(32)
// mmio_in_if  signals:  valid(1), data(8), ready(1)
// mmio_out_if signals:  boot_valid(1), exit_valid(1), exit_code(8), print_valid(1), print_data(32)
// ============================================================

module cpu_core_tmr (
    input   logic                   start,
    input   logic                   clk,

    mem_init_if.sink                rom_init,
    mmio_out_if.source             mmio_out,
    mmio_in_if.sink                mmio_in
);

    // ---- 3 套内部 interface 连线 ----
    mem_init_if   rom_init_1(), rom_init_2(), rom_init_3();
    mmio_out_if   mmio_out_1(), mmio_out_2(), mmio_out_3();
    mmio_in_if    mmio_in_1(),  mmio_in_2(),  mmio_in_3();

    // --- [1] mem_init_if.sink → 纯输入扇出 (3个核心共享输入源) ---
    assign rom_init_1.write_enable = rom_init.write_enable;
    assign rom_init_1.write_addr   = rom_init.write_addr;
    assign rom_init_1.write_data   = rom_init.write_data;

    assign rom_init_2.write_enable = rom_init.write_enable;
    assign rom_init_2.write_addr   = rom_init.write_addr;
    assign rom_init_2.write_data   = rom_init.write_data;

    assign rom_init_3.write_enable = rom_init.write_enable;
    assign rom_init_3.write_addr   = rom_init.write_addr;
    assign rom_init_3.write_data   = rom_init.write_data;

    // --- [2] mmio_in_if.sink → valid/data 扇入, ready 多数表决 ---
    assign mmio_in_1.valid = mmio_in.valid;
    assign mmio_in_1.data  = mmio_in.data;
    assign mmio_in_2.valid = mmio_in.valid;
    assign mmio_in_2.data  = mmio_in.data;
    assign mmio_in_3.valid = mmio_in.valid;
    assign mmio_in_3.data  = mmio_in.data;

    // TMR 多数表决器: mmio_in.ready (3选2)
    assign mmio_in.ready = (mmio_in_1.ready & mmio_in_2.ready) |
                           (mmio_in_1.ready & mmio_in_3.ready) |
                           (mmio_in_2.ready & mmio_in_3.ready);

    // --- [3] 3 个核心实例化 ---
    cpu_core_tmr_core core_inst_1 (
        .start       (start),
        .clk         (clk),
        .rom_init    (rom_init_1),
        .mmio_out    (mmio_out_1),
        .mmio_in     (mmio_in_1)
    );

    cpu_core_tmr_core core_inst_2 (
        .start       (start),
        .clk         (clk),
        .rom_init    (rom_init_2),
        .mmio_out    (mmio_out_2),
        .mmio_in     (mmio_in_2)
    );

    cpu_core_tmr_core core_inst_3 (
        .start       (start),
        .clk         (clk),
        .rom_init    (rom_init_3),
        .mmio_out    (mmio_out_3),
        .mmio_in     (mmio_in_3)
    );

    // --- [4] mmio_out_if.source 多数表决器 (5 个信号) ---
    // boot_valid
    assign mmio_out.boot_valid = (mmio_out_1.boot_valid & mmio_out_2.boot_valid) |
                                 (mmio_out_1.boot_valid & mmio_out_3.boot_valid) |
                                 (mmio_out_2.boot_valid & mmio_out_3.boot_valid);

    // exit_valid
    assign mmio_out.exit_valid = (mmio_out_1.exit_valid & mmio_out_2.exit_valid) |
                                  (mmio_out_1.exit_valid & mmio_out_3.exit_valid) |
                                  (mmio_out_2.exit_valid & mmio_out_3.exit_valid);

    // exit_code[7:0]
    assign mmio_out.exit_code = (mmio_out_1.exit_code & mmio_out_2.exit_code) |
                                 (mmio_out_1.exit_code & mmio_out_3.exit_code) |
                                 (mmio_out_2.exit_code & mmio_out_3.exit_code);

    // print_valid
    assign mmio_out.print_valid = (mmio_out_1.print_valid & mmio_out_2.print_valid) |
                                   (mmio_out_1.print_valid & mmio_out_3.print_valid) |
                                   (mmio_out_2.print_valid & mmio_out_3.print_valid);

    // print_data[31:0]
    assign mmio_out.print_data = (mmio_out_1.print_data & mmio_out_2.print_data) |
                                  (mmio_out_1.print_data & mmio_out_3.print_data) |
                                  (mmio_out_2.print_data & mmio_out_3.print_data);

    // --- [5] 表决器调试日志（全部 6 通道） ---
    //
    // 使用方法:
    //   在 testbench 中设置 ENABLE_VOTER_DEBUG=1 以启用运行时断言
    //   所有表决器不一致事件会通过 $warning 记录时间戳和具体值
    //
    // 仿真命令:
    //   vsim -G/ENABLE_VOTER_DEBUG=1 work.cpu_core_tmr

    parameter ENABLE_VOTER_DEBUG = 0;

    // 生成唯一的断言 ID 用于日志追踪
    // 每个表决器分配一个固定的通道号 (0-5)
    // 通道映射:
    //   ch-0: mmio_in.ready       (输入接口反馈)
    //   ch-1: mmio_out.boot_valid (输出接口)
    //   ch-2: mmio_out.exit_valid (输出接口)
    //   ch-3: mmio_out.exit_code  (输出接口, 8-bit)
    //   ch-4: mmio_out.print_valid(输出接口)
    //   ch-5: mmio_out.print_data (输出接口, 32-bit)

    // ================================================================
    // 多比特翻转防御: 错误计数器 (6 通道)
    //   - error_count_ch[N]: 每个通道的不一致事件计数
    //   - multi_bit_alert:   多比特 SEU (Hamming > 1) 告警
    //   - threshold_alert:   错误率超过阈值告警
    // 复位: 所有计数器在 start=0 时归零
    // ================================================================
    reg [15:0] error_count_ch0;
    reg [15:0] error_count_ch1;
    reg [15:0] error_count_ch2;
    reg [15:0] error_count_ch3;
    reg [15:0] error_count_ch4;
    reg [15:0] error_count_ch5;
    reg [31:0] total_clock_cycles;

    // 辅助函数: 计算 Hamming 距离 ($countones 的纯 Verilog 实现)
    function automatic integer hamming_distance(input [31:0] x);
        integer cnt, i;
        begin
            cnt = 0;
            for (i = 0; i < 32; i = i + 1) begin
                if (x[i]) cnt = cnt + 1;
            end
            hamming_distance = cnt;
        end
    endfunction

    generate
        if (ENABLE_VOTER_DEBUG) begin : voter_debug

            // === 运行时表决器状态采集 (每个时钟沿采样) ===
            always_ff @(posedge clk) begin
                if (!start) begin
                    error_count_ch0 <= 0;
                    error_count_ch1 <= 0;
                    error_count_ch2 <= 0;
                    error_count_ch3 <= 0;
                    error_count_ch4 <= 0;
                    error_count_ch5 <= 0;
                    total_clock_cycles <= 0;
                end else begin
                    total_clock_cycles <= total_clock_cycles + 1;

                    // [ch-0] mmio_in.ready — 3个核心的 ready 是否一致
                    if (mmio_in_1.ready !== mmio_in_2.ready ||
                        mmio_in_2.ready !== mmio_in_3.ready) begin
                        error_count_ch0 <= error_count_ch0 + 1;
                        $warning("[TMR-VOTER][ch-0] mmio_in.ready 不一致 @t=%0t: "
                                 "core1=%b core2=%b core3=%b | voted=%b",
                                 $time, mmio_in_1.ready, mmio_in_2.ready, mmio_in_3.ready, mmio_in.ready);
                    end

                    // [ch-1] mmio_out.boot_valid
                    if (mmio_out_1.boot_valid !== mmio_out_2.boot_valid ||
                        mmio_out_2.boot_valid !== mmio_out_3.boot_valid) begin
                        error_count_ch1 <= error_count_ch1 + 1;
                        $warning("[TMR-VOTER][ch-1] mmio_out.boot_valid 不一致 @t=%0t: "
                                 "core1=%b core2=%b core3=%b | voted=%b",
                                 $time, mmio_out_1.boot_valid, mmio_out_2.boot_valid,
                                 mmio_out_3.boot_valid, mmio_out.boot_valid);
                    end

                    // [ch-2] mmio_out.exit_valid
                    if (mmio_out_1.exit_valid !== mmio_out_2.exit_valid ||
                        mmio_out_2.exit_valid !== mmio_out_3.exit_valid) begin
                        error_count_ch2 <= error_count_ch2 + 1;
                        $warning("[TMR-VOTER][ch-2] mmio_out.exit_valid 不一致 @t=%0t: "
                                 "core1=%b core2=%b core3=%b | voted=%b",
                                 $time, mmio_out_1.exit_valid, mmio_out_2.exit_valid,
                                 mmio_out_3.exit_valid, mmio_out.exit_valid);
                    end

                    // [ch-3] mmio_out.exit_code[7:0] — 按位比较 + 多比特告警
                    if (mmio_out_1.exit_code !== mmio_out_2.exit_code ||
                        mmio_out_2.exit_code !== mmio_out_3.exit_code) begin
                        error_count_ch3 <= error_count_ch3 + 1;
                        if (hamming_distance(mmio_out_1.exit_code ^ mmio_out_2.exit_code) > 1) begin
                            $warning("[TMR-VOTER][ch-3][MULTI-BIT] mmio_out.exit_code 多比特翻转 @t=%0t: "
                                     "core1=%h core2=%h core3=%h Hamming=%0d",
                                     $time, mmio_out_1.exit_code, mmio_out_2.exit_code,
                                     mmio_out_3.exit_code,
                                     hamming_distance(mmio_out_1.exit_code ^ mmio_out_2.exit_code));
                        end
                        $warning("[TMR-VOTER][ch-3] mmio_out.exit_code 不一致 @t=%0t: "
                                 "core1=%h core2=%h core3=%h | voted=%h, 差异位=core1^core2=%b",
                                 $time, mmio_out_1.exit_code, mmio_out_2.exit_code,
                                 mmio_out_3.exit_code, mmio_out.exit_code,
                                 mmio_out_1.exit_code ^ mmio_out_2.exit_code);
                    end

                    // [ch-4] mmio_out.print_valid
                    if (mmio_out_1.print_valid !== mmio_out_2.print_valid ||
                        mmio_out_2.print_valid !== mmio_out_3.print_valid) begin
                        error_count_ch4 <= error_count_ch4 + 1;
                        $warning("[TMR-VOTER][ch-4] mmio_out.print_valid 不一致 @t=%0t: "
                                 "core1=%b core2=%b core3=%b | voted=%b",
                                 $time, mmio_out_1.print_valid, mmio_out_2.print_valid,
                                 mmio_out_3.print_valid, mmio_out.print_valid);
                    end

                    // [ch-5] mmio_out.print_data[31:0] — 按位比较 + 多比特告警
                    if (mmio_out_1.print_data !== mmio_out_2.print_data ||
                        mmio_out_2.print_data !== mmio_out_3.print_data) begin
                        error_count_ch5 <= error_count_ch5 + 1;
                        if (hamming_distance(mmio_out_1.print_data ^ mmio_out_2.print_data) > 1) begin
                            $warning("[TMR-VOTER][ch-5][MULTI-BIT] mmio_out.print_data 多比特翻转 @t=%0t: "
                                     "core1=%h core2=%h core3=%h Hamming=%0d",
                                     $time, mmio_out_1.print_data, mmio_out_2.print_data,
                                     mmio_out_3.print_data,
                                     hamming_distance(mmio_out_1.print_data ^ mmio_out_2.print_data));
                        end
                        $warning("[TMR-VOTER][ch-5] mmio_out.print_data 不一致 @t=%0t: "
                                 "core1=%h core2=%h core3=%h | voted=%h, 差异位=core1^core2=%b",
                                 $time, mmio_out_1.print_data, mmio_out_2.print_data,
                                 mmio_out_3.print_data, mmio_out.print_data,
                                 mmio_out_1.print_data ^ mmio_out_2.print_data);
                    end

                    // 错误率阈值告警: 当某个通道错误率超过 1% 时输出高优先级警告
                    if (total_clock_cycles > 100 && total_clock_cycles[7:0] == 0) begin
                        if (error_count_ch0 > (total_clock_cycles >> 7))
                            $display("[TMR-VOTER][ALERT] ch-0 错误率超过 1%%! count=%0d/%0d", error_count_ch0, total_clock_cycles);
                        if (error_count_ch1 > (total_clock_cycles >> 7))
                            $display("[TMR-VOTER][ALERT] ch-1 错误率超过 1%%! count=%0d/%0d", error_count_ch1, total_clock_cycles);
                        if (error_count_ch2 > (total_clock_cycles >> 7))
                            $display("[TMR-VOTER][ALERT] ch-2 错误率超过 1%%! count=%0d/%0d", error_count_ch2, total_clock_cycles);
                        if (error_count_ch3 > (total_clock_cycles >> 7))
                            $display("[TMR-VOTER][ALERT] ch-3 错误率超过 1%%! count=%0d/%0d", error_count_ch3, total_clock_cycles);
                        if (error_count_ch4 > (total_clock_cycles >> 7))
                            $display("[TMR-VOTER][ALERT] ch-4 错误率超过 1%%! count=%0d/%0d", error_count_ch4, total_clock_cycles);
                        if (error_count_ch5 > (total_clock_cycles >> 7))
                            $display("[TMR-VOTER][ALERT] ch-5 错误率超过 1%%! count=%0d/%0d", error_count_ch5, total_clock_cycles);
                    end

                    // 聚合统计: 若本周期有任一不一致, 记录汇总
                    if (mmio_in_1.ready          !== mmio_in_2.ready          ||
                        mmio_out_1.boot_valid    !== mmio_out_2.boot_valid    ||
                        mmio_out_1.exit_valid    !== mmio_out_2.exit_valid    ||
                        mmio_out_1.exit_code     !== mmio_out_2.exit_code     ||
                        mmio_out_1.print_valid   !== mmio_out_2.print_valid   ||
                        mmio_out_1.print_data    !== mmio_out_2.print_data) begin
                        $display("[TMR-VOTER][SUMMARY] @t=%0t: 存在表决器不一致, 请查看上方详细警告", $time);
                    end
                end
            end

            // === 形式化断言 (formal verification, 6 通道完整 SVA) ===
            //
            // 通道映射:
            //   ch-0: mmio_in.ready       (1-bit, 输入接口反馈)
            //   ch-1: mmio_out.boot_valid  (1-bit, 启动信号)
            //   ch-2: mmio_out.exit_valid  (1-bit, 退出信号)
            //   ch-3: mmio_out.exit_code   (8-bit, 退出码)
            //   ch-4: mmio_out.print_valid (1-bit, 打印使能)
            //   ch-5: mmio_out.print_data  (32-bit, 打印数据)
            //
            // 启用: 取消注释后使用 SymbiYosys / JasperGold 穷举证明
            //
            // 仿真: 默认启用, 当 ENABLE_VOTER_DEBUG=1 时激活
            // $error 输出: [SVA-VOTER][ch-N] {signal} 断言失败 @t: ...
            //
            // ch-0: mmio_in.ready
            assert property (@(posedge clk)
                (mmio_in_1.ready === mmio_in_2.ready) &&
                (mmio_in_2.ready === mmio_in_3.ready)
            ) else
                $error("[SVA-VOTER][ch-0] mmio_in.ready 断言失败 @t=%0t: "
                       "core1=%b core2=%b core3=%b", $time,
                       mmio_in_1.ready, mmio_in_2.ready, mmio_in_3.ready);

            // ch-1: mmio_out.boot_valid
            assert property (@(posedge clk)
                (mmio_out_1.boot_valid === mmio_out_2.boot_valid) &&
                (mmio_out_2.boot_valid === mmio_out_3.boot_valid)
            ) else
                $error("[SVA-VOTER][ch-1] mmio_out.boot_valid 断言失败 @t=%0t: "
                       "core1=%b core2=%b core3=%b", $time,
                       mmio_out_1.boot_valid, mmio_out_2.boot_valid, mmio_out_3.boot_valid);

            // ch-2: mmio_out.exit_valid
            assert property (@(posedge clk)
                (mmio_out_1.exit_valid === mmio_out_2.exit_valid) &&
                (mmio_out_2.exit_valid === mmio_out_3.exit_valid)
            ) else
                $error("[SVA-VOTER][ch-2] mmio_out.exit_valid 断言失败 @t=%0t: "
                       "core1=%b core2=%b core3=%b", $time,
                       mmio_out_1.exit_valid, mmio_out_2.exit_valid, mmio_out_3.exit_valid);

            // ch-3: mmio_out.exit_code (8-bit, 含差异位掩码 + Hamming 距离)
            assert property (@(posedge clk)
                (mmio_out_1.exit_code === mmio_out_2.exit_code) &&
                (mmio_out_2.exit_code === mmio_out_3.exit_code)
            ) else begin
                $error("[SVA-VOTER][ch-3] mmio_out.exit_code 断言失败 @t=%0t: "
                       "core1=%h core2=%h core3=%h 差异位=%b", $time,
                       mmio_out_1.exit_code, mmio_out_2.exit_code, mmio_out_3.exit_code,
                       mmio_out_1.exit_code ^ mmio_out_2.exit_code);
                // 多比特翻转防御: 检查 Hamming 距离 (翻转比特数)
                if (hamming_distance(mmio_out_1.exit_code ^ mmio_out_2.exit_code) > 1) begin
                    $error("[SVA-VOTER][ch-3][MULTI-BIT] 多比特 SEU 检测: Hamming=%0d > 1",
                           hamming_distance(mmio_out_1.exit_code ^ mmio_out_2.exit_code));
                end
            end

            // ch-4: mmio_out.print_valid
            assert property (@(posedge clk)
                (mmio_out_1.print_valid === mmio_out_2.print_valid) &&
                (mmio_out_2.print_valid === mmio_out_3.print_valid)
            ) else
                $error("[SVA-VOTER][ch-4] mmio_out.print_valid 断言失败 @t=%0t: "
                       "core1=%b core2=%b core3=%b", $time,
                       mmio_out_1.print_valid, mmio_out_2.print_valid, mmio_out_3.print_valid);

            // ch-5: mmio_out.print_data (32-bit, 含差异位掩码 + Hamming 距离)
            assert property (@(posedge clk)
                (mmio_out_1.print_data === mmio_out_2.print_data) &&
                (mmio_out_2.print_data === mmio_out_3.print_data)
            ) else begin
                $error("[SVA-VOTER][ch-5] mmio_out.print_data 断言失败 @t=%0t: "
                       "core1=%h core2=%h core3=%h 差异位=%b", $time,
                       mmio_out_1.print_data, mmio_out_2.print_data, mmio_out_3.print_data,
                       mmio_out_1.print_data ^ mmio_out_2.print_data);
                // 多比特翻转防御: 检查 Hamming 距离 (翻转比特数)
                if (hamming_distance(mmio_out_1.print_data ^ mmio_out_2.print_data) > 1) begin
                    $error("[SVA-VOTER][ch-5][MULTI-BIT] 多比特 SEU 检测: Hamming=%0d > 1",
                           hamming_distance(mmio_out_1.print_data ^ mmio_out_2.print_data));
                end
            end

        end
    endgenerate

endmodule : cpu_core_tmr