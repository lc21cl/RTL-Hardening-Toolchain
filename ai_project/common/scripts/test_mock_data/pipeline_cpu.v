// Multi-stage pipeline processor with external I/O
// Each stage is a wide datapath with register pipeline
// Designed to produce a large BLIF (>1000 cells)

module pipeline_cpu (
    input wire clk,
    input wire rst_n,
    input wire [31:0] instr_in,    // Instruction input
    input wire [31:0] data_in,     // Data input
    output reg [31:0] addr_out,    // Address output
    output reg [31:0] data_out,    // Data output
    output reg [31:0] debug_out,   // Debug output
    output reg valid_out           // Output valid
);

    parameter W = 32;

    // ── Stage 1: IF (Instruction Fetch) ──
    reg [W-1:0] if_pc;
    reg [W-1:0] if_instr;
    reg if_valid;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            if_pc <= 0;
            if_instr <= 0;
            if_valid <= 0;
        end else begin
            if_pc <= if_pc + 4;
            if_instr <= instr_in;
            if_valid <= 1'b1;
        end
    end

    // ── Stage 2: ID (Instruction Decode) ──
    reg [W-1:0] id_pc;
    reg [W-1:0] id_instr;
    reg [4:0] id_rs1, id_rs2, id_rd;
    reg [6:0] id_opcode;
    reg [2:0] id_funct3;
    reg [6:0] id_funct7;
    reg id_valid;
    
    wire [W-1:0] imm_i = {{21{id_instr[31]}}, id_instr[30:20]};
    wire [W-1:0] imm_s = {{21{id_instr[31]}}, id_instr[30:25], id_instr[11:7]};
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            id_pc <= 0; id_instr <= 0; id_valid <= 0;
            id_rs1 <= 0; id_rs2 <= 0; id_rd <= 0;
            id_opcode <= 0; id_funct3 <= 0; id_funct7 <= 0;
        end else if (if_valid) begin
            id_pc <= if_pc;
            id_instr <= if_instr;
            id_rs1 <= if_instr[19:15];
            id_rs2 <= if_instr[24:20];
            id_rd <= if_instr[11:7];
            id_opcode <= if_instr[6:0];
            id_funct3 <= if_instr[14:12];
            id_funct7 <= if_instr[31:25];
            id_valid <= 1'b1;
        end else begin
            id_valid <= 1'b0;
        end
    end

    // ── Register File (32 x 32-bit) ──
    reg [W-1:0] regfile [0:31];
    integer ri;
    always @(posedge clk) begin
        if (wb_valid && wb_rd != 0)
            regfile[wb_rd] <= wb_result;
    end
    
    // Read ports
    wire [W-1:0] rs1_val = (id_rs1 == 0) ? 0 : regfile[id_rs1];
    wire [W-1:0] rs2_val = (id_rs2 == 0) ? 0 : regfile[id_rs2];

    // ── Stage 3: EX (Execute) ──
    reg [W-1:0] ex_pc;
    reg [4:0] ex_rd;
    reg ex_valid;
    reg [W-1:0] ex_result;
    reg ex_branch_taken;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ex_pc <= 0; ex_rd <= 0; ex_valid <= 0;
            ex_result <= 0; ex_branch_taken <= 0;
        end else if (id_valid) begin
            ex_pc <= id_pc;
            ex_rd <= id_rd;
            ex_valid <= 1'b1;
            
            // ALU operations
            case (id_funct3)
                3'b000: ex_result = rs1_val + rs2_val;        // ADD/SUB
                3'b001: ex_result = rs1_val << rs2_val[4:0];  // SLL
                3'b010: ex_result = (rs1_val < rs2_val) ? 1 : 0;  // SLT
                3'b011: ex_result = ($unsigned(rs1_val) < $unsigned(rs2_val)) ? 1 : 0;  // SLTU
                3'b100: ex_result = rs1_val ^ rs2_val;        // XOR
                3'b101: ex_result = rs1_val >> rs2_val[4:0];  // SRL/SRA
                3'b110: ex_result = rs1_val | rs2_val;        // OR
                3'b111: ex_result = rs1_val & rs2_val;        // AND
                default: ex_result = rs1_val + rs2_val;
            endcase
            
            // Branch condition
            case (id_funct3)
                3'b000: ex_branch_taken = (rs1_val == rs2_val);     // BEQ
                3'b001: ex_branch_taken = (rs1_val != rs2_val);     // BNE
                3'b100: ex_branch_taken = (rs1_val < rs2_val);      // BLT
                3'b101: ex_branch_taken = (rs1_val >= rs2_val);     // BGE
                default: ex_branch_taken = 0;
            endcase
        end else begin
            ex_valid <= 1'b0;
        end
    end

    // ── Stage 4: MEM (Memory Access) ──
    reg [W-1:0] mem_pc;
    reg [4:0] mem_rd;
    reg mem_valid;
    reg [W-1:0] mem_result;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mem_pc <= 0; mem_rd <= 0; mem_valid <= 0; mem_result <= 0;
        end else if (ex_valid) begin
            mem_pc <= ex_pc;
            mem_rd <= ex_rd;
            mem_valid <= 1'b1;
            // Forward result: ALU result + data_in combination
            mem_result <= ex_result ^ data_in;  // XOR with external data
        end else begin
            mem_valid <= 1'b0;
        end
    end

    // ── Stage 5: WB (Write Back) ──
    reg wb_valid;
    reg [4:0] wb_rd;
    reg [W-1:0] wb_result;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wb_valid <= 0; wb_rd <= 0; wb_result <= 0;
        end else if (mem_valid && mem_rd != 0) begin
            wb_valid <= 1'b1;
            wb_rd <= mem_rd;
            wb_result <= mem_result;
        end else begin
            wb_valid <= 1'b0;
        end
    end

    // ── Outputs ──
    reg [2:0] cycle;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            addr_out <= 0; data_out <= 0; debug_out <= 0; valid_out <= 0;
            cycle <= 0;
        end else begin
            addr_out <= mem_pc;
            data_out <= mem_result;
            debug_out <= regfile[1] ^ regfile[2] ^ regfile[3] ^ regfile[4];
            valid_out <= mem_valid;
            cycle <= cycle + 1;
        end
    end

endmodule
