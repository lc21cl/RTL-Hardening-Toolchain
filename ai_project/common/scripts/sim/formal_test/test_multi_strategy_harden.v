// ============================================================================
// test_multi_strategy_harden.v
// 复杂 RTL 测试用例 — 含 ECC、DICE、TMR 三种加固策略
//
// 用途：验证完整的加固流水线端到端联动效果
//   - MockLLM 模板选择：三种策略自动匹配
//   - AST 修复器：纠正端口声明/方向/分号等语法错误
//   - SyntaxFixer：修复 begin/end 不匹配/敏感列表等剩余问题
//   - Yosys 验证：语法检查 + 综合检查 → 确保生成代码可综合
//
// 结构：
//   top_multi_strategy      — 混合三种加固策略的顶层模块
//     ├─ ecc_bus_interface  — 采用 ECC 加固的总线接口数据
//     ├─ dice_regfile       — 采用 DICE 加固的寄存器文件
//     └─ tmr_control_fsm    — 采用 TMR 加固的控制状态机
// ============================================================================

// ======================================================================
// 顶层模块：混合三种加固策略
// 故意包含端口方向缺失和分号缺失，测试 AST 修复器
// ======================================================================
module top_multi_strategy (
    clk,
    rst_n,
    bus_addr,
    bus_wr_data,
    bus_wr_en,
    bus_rd_data,
    bus_error,
    reg_wr_addr,
    reg_wr_data,
    reg_wr_en,
    reg_rd_addr,
    reg_rd_data,
    fsm_start,
    fsm_done,
    fsm_error
);
    // 时钟和复位
    input  wire        clk;
    input  wire        rst_n;

    // 总线接口（ECC 加固目标）
    input  wire [7:0]  bus_addr;
    input  wire [15:0] bus_wr_data;
    input  wire        bus_wr_en;
    output wire [15:0] bus_rd_data;
    output wire        bus_error;

    // 寄存器文件接口（DICE 加固目标）
    input  wire [3:0]  reg_wr_addr;
    input  wire [7:0]  reg_wr_data;
    input  wire        reg_wr_en;
    input  wire [3:0]  reg_rd_addr;
    output wire [7:0]  reg_rd_data;

    // 控制状态机接口（TMR 加固目标）
    input  wire        fsm_start;
    output wire        fsm_done;
    output wire        fsm_error;

    // ── 内部信号 ──
    wire [15:0] ecc_data_out;
    wire        ecc_uncorrectable;
    wire [7:0]  dice_data_out;
    wire        dice_consistency_error;
    wire        tmr_state_voted;
    wire        tmr_error_flag;
    wire        fsm_fault;

    // ── ECC 加固实例：总线保护 ──
    ecc_bus_interface #(
        .DATA_WIDTH(16)
    ) u_ecc_bus (
        .clk        (clk),
        .rst_n      (rst_n),
        .addr       (bus_addr),
        .data_wr    (bus_wr_data),
        .wr_en      (bus_wr_en),
        .data_rd    (ecc_data_out),
        .error_flag (ecc_uncorrectable)
    );
    assign bus_rd_data = ecc_data_out;
    assign bus_error   = ecc_uncorrectable;

    // ── DICE 加固实例：寄存器文件 ──
    dice_regfile #(
        .DATA_WIDTH(8),
        .ADDR_WIDTH(4)
    ) u_dice_reg (
        .clk        (clk),
        .rst_n      (rst_n),
        .wr_addr    (reg_wr_addr),
        .wr_data    (reg_wr_data),
        .wr_en      (reg_wr_en),
        .rd_addr    (reg_rd_addr),
        .rd_data    (dice_data_out),
        .err_flag   (dice_consistency_error)
    );
    assign reg_rd_data = dice_data_out;

    // ── TMR 加固实例：控制状态机 ──
    tmr_control_fsm u_tmr_fsm (
        .clk      (clk),
        .rst_n    (rst_n),
        .start    (fsm_start),
        .state_vot(tmr_state_voted),
        .done     (fsm_done),
        .fault    (fsm_fault),
        .err_flag (tmr_error_flag)
    );
    assign fsm_error = fsm_fault | tmr_error_flag;

endmodule


// ======================================================================
// DICE 加固模块：寄存器文件
// 4 节点交叉耦合 + 4-of-4 多数表决
// ======================================================================
module dice_regfile #(
    parameter DATA_WIDTH = 8,
    parameter ADDR_WIDTH = 4
) (
    input  wire                    clk,
    input  wire                    rst_n,
    input  wire [ADDR_WIDTH-1:0]  wr_addr,
    input  wire [DATA_WIDTH-1:0]  wr_data,
    input  wire                    wr_en,
    input  wire [ADDR_WIDTH-1:0]  rd_addr,
    output reg  [DATA_WIDTH-1:0]  rd_data,
    output wire                    err_flag
);
    // DICE 存储：4 个节点
    reg [DATA_WIDTH-1:0] n0 [0:15];
    reg [DATA_WIDTH-1:0] n1 [0:15];
    reg [DATA_WIDTH-1:0] n2 [0:15];
    reg [DATA_WIDTH-1:0] n3 [0:15];

    integer i;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < 16; i = i + 1) begin
                n0[i] <= {DATA_WIDTH{1'b0}};
                n1[i] <= {DATA_WIDTH{1'b0}};
                n2[i] <= {DATA_WIDTH{1'b0}};
                n3[i] <= {DATA_WIDTH{1'b0}};
            end
        end else if (wr_en) begin
            n0[wr_addr] <= wr_data;
            n1[wr_addr] <= n0[wr_addr];
            n2[wr_addr] <= n1[wr_addr];
            n3[wr_addr] <= n2[wr_addr];
        end
    end

    // 4-of-4 多数表决读取
    always @(*) begin
        rd_data = n0[rd_addr];
    end

    // 一致性检查：四个节点应一致
    assign err_flag = (n0[rd_addr] != n1[rd_addr]) |
                      (n0[rd_addr] != n2[rd_addr]) |
                      (n0[rd_addr] != n3[rd_addr]);

endmodule


// ======================================================================
// ECC 加固模块：总线接口
// SECDED 编解码，单比特纠正双比特检测
// ======================================================================
module ecc_bus_interface #(
    parameter DATA_WIDTH = 16
) (
    input  wire                    clk,
    input  wire                    rst_n,
    input  wire [7:0]             addr,
    input  wire [DATA_WIDTH-1:0]  data_wr,
    input  wire                    wr_en,
    output reg  [DATA_WIDTH-1:0]  data_rd,
    output wire                    error_flag
);

    // 内存阵列 + ECC 校验位
    localparam DEPTH = 256;
    localparam CHECK_BITS = 6;  // SECDED for 16-bit data
    localparam CODE_WIDTH = DATA_WIDTH + CHECK_BITS;
    reg [CODE_WIDTH-1:0] mem [0:DEPTH-1];

    // ECC 编码：写路径
    wire [CHECK_BITS-1:0] check_wr;
    assign check_wr[0] = ^data_wr[0:DATA_WIDTH/4-1];
    assign check_wr[1] = ^data_wr[DATA_WIDTH/4:DATA_WIDTH/2-1];
    assign check_wr[2] = ^data_wr[DATA_WIDTH/2:3*DATA_WIDTH/4-1];
    assign check_wr[3] = ^data_wr[3*DATA_WIDTH/4:DATA_WIDTH-1];
    assign check_wr[4] = ^data_wr;
    assign check_wr[5] = ^(data_wr >> 1);

    // 读数据：含 ECC 解码
    wire [CODE_WIDTH-1:0] rdata;
    wire [CHECK_BITS-1:0] check_rd;
    assign rdata = mem[addr];

    assign check_rd[0] = ^rdata[DATA_WIDTH-1:DATA_WIDTH/4];
    assign check_rd[1] = ^rdata[DATA_WIDTH/2:DATA_WIDTH];
    assign check_rd[2] = ^rdata[DATA_WIDTH/4:DATA_WIDTH/2];
    assign check_rd[3] = ^rdata[DATA_WIDTH-1:DATA_WIDTH/2];
    assign check_rd[4] = ^rdata[DATA_WIDTH-1:0];
    assign check_rd[5] = ^(rdata[DATA_WIDTH-1:0] >> 1);

    // 校正向量
    wire [CHECK_BITS-1:0] syndrome;
    assign syndrome = check_rd ^ rdata[CODE_WIDTH-1:DATA_WIDTH];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_rd <= {DATA_WIDTH{1'b0}};
        end else if (wr_en) begin
            mem[addr] <= {data_wr, check_wr};
        end else begin
            // 单比特纠正
            if (syndrome != 0 && (^syndrome == 1))
                data_rd <= rdata[DATA_WIDTH-1:0] ^ (1 << syndrome[4:0]);
            else
                data_rd <= rdata[DATA_WIDTH-1:0];
        end
    end

    // 不可纠正错误标志
    assign error_flag = (syndrome != 0) && (^syndrome != 1);

endmodule


// ======================================================================
// TMR 加固模块：控制状态机
// 三模冗余 + 多数表决 + 错误标志
// ======================================================================
module tmr_control_fsm (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,
    output reg         state_vot,
    output reg         done,
    output reg         fault,
    output wire        err_flag
);

    // 状态编码
    localparam IDLE = 2'b00;
    localparam RUN  = 2'b01;
    localparam DONE = 2'b10;
    localparam ERR  = 2'b11;

    // TMR：三个冗余副本
    reg [1:0] state0, state1, state2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state0 <= IDLE;
            state1 <= IDLE;
            state2 <= IDLE;
        end else begin
            case (state0)
                IDLE: if (start) state0 <= RUN;
                RUN:  state0 <= DONE;
                DONE: state0 <= IDLE;
                default: state0 <= IDLE;
            endcase
            // 副本1、副本2 完全相同
            case (state1)
                IDLE: if (start) state1 <= RUN;
                RUN:  state1 <= DONE;
                DONE: state1 <= IDLE;
                default: state1 <= IDLE;
            endcase
            case (state2)
                IDLE: if (start) state2 <= RUN;
                RUN:  state2 <= DONE;
                DONE: state2 <= IDLE;
                default: state2 <= IDLE;
            endcase
        end
    end

    // 多数表决
    always @(*) begin
        state_vot = (state0 == RUN && state1 == RUN) ||
                    (state0 == RUN && state2 == RUN) ||
                    (state1 == RUN && state2 == RUN);
        done = (state0 == DONE && state1 == DONE) ||
               (state0 == DONE && state2 == DONE) ||
               (state1 == DONE && state2 == DONE);
        fault = (state0 == ERR || state1 == ERR || state2 == ERR);
    end

    // 错误标志：任意两份不匹配
    assign err_flag = (state0 != state1) | (state0 != state2) | (state1 != state2);

endmodule
