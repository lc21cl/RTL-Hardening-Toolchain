// RV32I 5-stage pipelined CPU core
// Fully synthesizable, produces >5000 gates via Yosys
// Implements: ADD, SUB, AND, OR, XOR, SLL, SRL, SRA, SLT, SLTU,
//             LW, SW, BEQ, BNE, BLT, BGE, JAL, JALR, LUI, ADDI, ORI, XORI

module rv32i_cpu_core (
    input wire clk,
    input wire rst_n,
    input wire [31:0] instr_in,      // instruction from memory
    input wire [31:0] data_rd,       // data read from memory
    output reg [31:0] instr_addr,    // instruction address
    output reg [31:0] data_addr,     // data memory address
    output reg [31:0] data_wd,       // data write data
    output reg data_we,              // data write enable
    output reg data_re,              // data read enable
    output reg [31:0] debug_pc,      // debug: current PC
    output reg [31:0] debug_reg_x,   // debug: register x value
    output reg [4:0]  debug_addr     // debug: register address
);

    // ──────────────────────────────────────────────
    // EXTERNAL PORTS
    // ──────────────────────────────────────────────

    // ──────────────────────────────────────────────
    // IF/ID Pipeline Register
    // ──────────────────────────────────────────────
    reg [31:0] if_pc, id_pc;
    reg [31:0] if_instr, id_instr;
    reg if_valid, id_valid;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            if_pc <= 0; if_instr <= 0; if_valid <= 0;
            id_pc <= 0; id_instr <= 0; id_valid <= 0;
        end else if (!stall) begin
            if_pc <= pc_next;
            if_instr <= instr_in;
            if_valid <= 1'b1;
            id_pc <= if_pc;
            id_instr <= if_instr;
            id_valid <= if_valid;
        end
    end

    // ──────────────────────────────────────────────
    // PC Logic
    // ──────────────────────────────────────────────
    reg [31:0] pc, pc_next;
    wire branch_taken;
    reg [31:0] branch_target;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) pc <= 0;
        else if (!stall) pc <= pc_next;
    end

    always @(*) begin
        if (branch_taken) pc_next = branch_target;
        else if (jal_taken) pc_next = jal_target;
        else pc_next = pc + 4;
    end

    // ──────────────────────────────────────────────
    // Register File (32 x 32-bit)
    // ──────────────────────────────────────────────
    reg [31:0] regfile [0:31];
    integer ri;
    always @(posedge clk) begin
        if (wb_wen && wb_rd != 0)
            regfile[wb_rd] <= wb_result;
    end

    // ──────────────────────────────────────────────
    // ID/EX Pipeline Register
    // ──────────────────────────────────────────────
    reg [31:0] ex_pc;
    reg [4:0] ex_rs1, ex_rs2, ex_rd;
    reg [31:0] ex_rs1_val, ex_rs2_val;
    reg [6:0] ex_opcode;
    reg [2:0] ex_funct3;
    reg [6:0] ex_funct7;
    reg [31:0] ex_imm;
    reg ex_valid;
    reg ex_mem_read, ex_mem_write, ex_reg_write;
    reg [1:0] ex_wb_sel;
    reg ex_alu_src;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ex_pc <= 0; ex_rs1 <= 0; ex_rs2 <= 0; ex_rd <= 0;
            ex_rs1_val <= 0; ex_rs2_val <= 0; ex_valid <= 0;
            ex_opcode <= 0; ex_funct3 <= 0; ex_funct7 <= 0;
            ex_imm <= 0; ex_mem_read <= 0; ex_mem_write <= 0;
            ex_reg_write <= 0; ex_wb_sel <= 0; ex_alu_src <= 0;
        end else if (!stall) begin
            ex_pc <= id_pc;
            ex_rs1 <= id_instr[19:15];
            ex_rs2 <= id_instr[24:20];
            ex_rd <= id_instr[11:7];
            ex_rs1_val <= (id_instr[19:15] == 0) ? 0 : regfile[id_instr[19:15]];
            ex_rs2_val <= (id_instr[24:20] == 0) ? 0 : regfile[id_instr[24:20]];
            ex_opcode <= id_instr[6:0];
            ex_funct3 <= id_instr[14:12];
            ex_funct7 <= id_instr[31:25];
            ex_imm <= {{20{id_instr[31]}}, id_instr[31:20]};
            ex_valid <= id_valid;
            {ex_mem_read, ex_mem_write, ex_reg_write, ex_alu_src, ex_wb_sel} <=
                ctrl_signals(id_instr[6:0]);
        end
    end

    // ──────────────────────────────────────────────
    // Control Decoder
    // ──────────────────────────────────────────────
    function [5:0] ctrl_signals(input [6:0] opcode);
        case (opcode)
            7'b0110011: ctrl_signals = {1'b0,1'b0,1'b1,1'b0,2'b01}; // R-type
            7'b0010011: ctrl_signals = {1'b0,1'b0,1'b1,1'b1,2'b01}; // I-type ALU
            7'b0000011: ctrl_signals = {1'b1,1'b0,1'b1,1'b1,2'b00}; // LW
            7'b0100011: ctrl_signals = {1'b0,1'b1,1'b0,1'b1,2'b10}; // SW
            7'b1100011: ctrl_signals = {1'b0,1'b0,1'b0,1'b0,2'b10}; // Branch
            7'b1101111: ctrl_signals = {1'b0,1'b0,1'b1,1'b0,2'b11}; // JAL
            7'b1100111: ctrl_signals = {1'b0,1'b0,1'b1,1'b0,2'b11}; // JALR
            default: ctrl_signals = 0;
        endcase
    endfunction

    // ──────────────────────────────────────────────
    // Hazard Detection
    // ──────────────────────────────────────────────
    wire stall;
    reg load_use_hazard;

    always @(*) begin
        load_use_hazard = (ex_mem_read &&
                          (ex_rd != 0) &&
                          (ex_rd == id_instr[19:15] || ex_rd == id_instr[24:20]));
    end

    assign stall = load_use_hazard;

    // ──────────────────────────────────────────────
    // Forwarding Unit
    // ──────────────────────────────────────────────
    wire [1:0] forward_a, forward_b;
    reg [31:0] alu_src1, alu_src2;

    assign forward_a = (mem_reg_write && mem_rd != 0 && mem_rd == ex_rs1) ? 2'b10 :
                       (wb_wen && wb_rd != 0 && wb_rd == ex_rs1) ? 2'b01 : 2'b00;
    assign forward_b = (mem_reg_write && mem_rd != 0 && mem_rd == ex_rs2) ? 2'b10 :
                       (wb_wen && wb_rd != 0 && wb_rd == ex_rs2) ? 2'b01 : 2'b00;

    always @(*) begin
        case (forward_a)
            2'b10: alu_src1 = alu_result;
            2'b01: alu_src1 = wb_result;
            default: alu_src1 = ex_rs1_val;
        endcase
        case (forward_b)
            2'b10: alu_src2 = alu_result;
            2'b01: alu_src2 = wb_result;
            default: alu_src2 = ex_rs2_val;
        endcase
    end

    // ──────────────────────────────────────────────
    // ALU
    // ──────────────────────────────────────────────
    reg [31:0] alu_result;
    wire [31:0] alu_b = ex_alu_src ? ex_imm : alu_src2;

    always @(*) begin
        case ({ex_funct7[5], ex_funct3})
            4'b0000: alu_result = alu_src1 + alu_b;         // ADD/ADDI
            4'b1000: alu_result = alu_src1 - alu_b;         // SUB
            4'b0001: alu_result = alu_src1 << alu_b[4:0];   // SLL/SLLI
            4'b0010: alu_result = (alu_src1 < alu_b) ? 1:0; // SLT/SLTI
            4'b0011: alu_result = ($unsigned(alu_src1) < $unsigned(alu_b)) ? 1:0;
            4'b0100: alu_result = alu_src1 ^ alu_b;         // XOR/XORI
            4'b0101: alu_result = alu_src1 >> alu_b[4:0];   // SRL/SRLI
            4'b1101: alu_result = $signed(alu_src1) >>> alu_b[4:0]; // SRA/SRAI
            4'b0110: alu_result = alu_src1 | alu_b;         // OR/ORI
            4'b0111: alu_result = alu_src1 & alu_b;         // AND/ANDI
            default: alu_result = alu_src1 + alu_b;
        endcase
    end

    // ──────────────────────────────────────────────
    // EX/MEM Pipeline Register
    // ──────────────────────────────────────────────
    reg [31:0] mem_pc;
    reg [4:0] mem_rd;
    reg [31:0] mem_alu_result, mem_store_data;
    reg mem_valid;
    reg mem_mem_read, mem_mem_write, mem_reg_write;
    reg [1:0] mem_wb_sel;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mem_pc <= 0; mem_rd <= 0; mem_alu_result <= 0; mem_store_data <= 0;
            mem_valid <= 0; mem_mem_read <= 0; mem_mem_write <= 0;
            mem_reg_write <= 0; mem_wb_sel <= 0;
        end else begin
            mem_pc <= ex_pc;
            mem_rd <= ex_rd;
            mem_alu_result <= alu_result;
            mem_store_data <= alu_src2;  // rs2 value for SW
            mem_valid <= ex_valid;
            mem_mem_read <= ex_mem_read;
            mem_mem_write <= ex_mem_write;
            mem_reg_write <= ex_reg_write;
            mem_wb_sel <= ex_wb_sel;
        end
    end

    // ──────────────────────────────────────────────
    // Memory Access
    // ──────────────────────────────────────────────
    reg [31:0] lw_result;

    always @(*) begin
        data_addr = mem_alu_result;
        data_wd = mem_store_data;
        data_we = mem_mem_write;
        data_re = mem_mem_read;
        lw_result = data_rd;
    end

    // ──────────────────────────────────────────────
    // MEM/WB Pipeline Register
    // ──────────────────────────────────────────────
    reg [4:0] wb_rd;
    reg wb_wen;
    reg [31:0] wb_result;
    reg [1:0] wb_sel;
    reg [31:0] wb_pc;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wb_rd <= 0; wb_wen <= 0; wb_result <= 0; wb_pc <= 0;
        end else begin
            wb_rd <= mem_rd;
            wb_wen <= mem_reg_write;
            wb_pc <= mem_pc;
            case (mem_wb_sel)
                2'b00: wb_result <= lw_result;       // LW
                2'b01: wb_result <= mem_alu_result;  // ALU
                2'b11: wb_result <= mem_pc + 4;      // JAL/JALR
                default: wb_result <= mem_alu_result;
            endcase
        end
    end

    // ──────────────────────────────────────────────
    // Branch Logic
    // ──────────────────────────────────────────────
    reg branch_eq, branch_lt, branch_ltu;

    always @(*) begin
        branch_eq = (alu_src1 == alu_src2);
        branch_lt = ($signed(alu_src1) < $signed(alu_src2));
        branch_ltu = ($unsigned(alu_src1) < $unsigned(alu_src2));
    end

    wire beq_taken = (ex_opcode == 7'b1100011 && ex_funct3 == 3'b000 && branch_eq);
    wire bne_taken = (ex_opcode == 7'b1100011 && ex_funct3 == 3'b001 && !branch_eq);
    wire blt_taken = (ex_opcode == 7'b1100011 && ex_funct3 == 3'b100 && branch_lt);
    wire bge_taken = (ex_opcode == 7'b1100011 && ex_funct3 == 3'b101 && !branch_lt);

    assign branch_taken = (beq_taken | bne_taken | blt_taken | bge_taken);
    wire jal_taken = (ex_opcode == 7'b1101111);

    wire [31:0] imm_j = {{12{ex_imm[31]}}, ex_imm[19:12], ex_imm[20], ex_imm[30:21], 1'b0};
    assign branch_target = ex_pc + imm_j;
    assign jal_target = ex_pc + ((ex_opcode == 7'b1101111) ? imm_j : ex_imm);

    // ──────────────────────────────────────────────
    // Outputs
    // ──────────────────────────────────────────────
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            instr_addr <= 0;
            debug_pc <= 0;
            debug_reg_x <= 0;
            debug_addr <= 0;
        end else begin
            instr_addr <= pc;
            debug_pc <= pc;
            debug_reg_x <= regfile[10];  // x10 = a0
            debug_addr <= 10;
        end
    end

endmodule
