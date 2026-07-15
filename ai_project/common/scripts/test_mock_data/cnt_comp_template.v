// ====================================================
// cnt_comp 加固: 递增计数器
// 原始代码:
//   always_ff @(posedge clk) counter <= counter + 1;
//
// cnt_comp 加固后:
// ====================================================
module cnt_comp_up #(
    parameter WIDTH = 32,
    parameter CW    = 5   // 错误计数器位宽
) (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               en,
    output reg  [WIDTH-1:0]   counter,
    output wire               error_flag,
    output reg  [CW-1:0]      error_count
);
    // ---- 影子寄存器 (shadow counter) ----
    reg [WIDTH-1:0] shadow;

    // ---- 主计数器 ----
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) counter <= '0;
        else if (en) counter <= counter + 1'b1;
    end

    // ---- 影子寄存器 (独立于主计数器) ----
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) shadow <= '0;
        else if (en) shadow <= shadow + 1'b1;
    end

    // ---- 比较器检测 ----
    // 检测方法: 在 en 有效时, 两个独立寄存器递增不一致 = 错误
    // 注意: 使能后至少 2 周期才做比较 (给影子追上主计数器的时间)
    reg en_dly;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) en_dly <= '0;
        else en_dly <= en;
    end

    assign error_flag = (en && en_dly) ? (counter != shadow) : 1'b0;

    // ---- 错误计数器 ----
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) error_count <= '0;
        else if (error_flag && (&error_count != 1'b1)) error_count <= error_count + 1'b1;
    end

endmodule


// ====================================================
// cnt_comp 加固: 递减计数器
// 原始代码:
//   always_ff @(posedge clk) counter <= counter - 1;
// ====================================================
module cnt_comp_down #(
    parameter WIDTH = 32,
    parameter CW    = 5,
    parameter INIT  = {WIDTH{1'b1}}  // 起始值 (默认全1 = 最大值)
) (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               en,
    output reg  [WIDTH-1:0]   counter,
    output wire               error_flag,
    output reg  [CW-1:0]      error_count
);
    reg [WIDTH-1:0] shadow;
    reg en_dly;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin counter <= INIT; shadow <= INIT; end
        else if (en) begin
            counter <= counter - 1'b1;
            shadow  <= shadow - 1'b1;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) en_dly <= '0;
        else en_dly <= en;
    end

    assign error_flag = (en && en_dly) ? (counter != shadow) : 1'b0;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) error_count <= '0;
        else if (error_flag && (&error_count != 1'b1)) error_count <= error_count + 1'b1;
    end

endmodule


// ====================================================
// cnt_comp 加固: 模计数器 (0 → MAX → 0)
// 原始代码:
//   always_ff @(posedge clk)
//     if (counter == MAX) counter <= 0;
//     else counter <= counter + 1;
// ====================================================
module cnt_comp_mod #(
    parameter WIDTH = 8,
    parameter CW    = 5,
    parameter MAX   = 8'd255
) (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               en,
    output reg  [WIDTH-1:0]   counter,
    output wire               error_flag,
    output reg  [CW-1:0]      error_count
);
    reg [WIDTH-1:0] shadow;
    reg en_dly;

    // 主计数器
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) counter <= '0;
        else if (en) begin
            if (counter == MAX) counter <= '0;
            else counter <= counter + 1'b1;
        end
    end

    // 影子
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) shadow <= '0;
        else if (en) begin
            if (shadow == MAX) shadow <= '0;
            else shadow <= shadow + 1'b1;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) en_dly <= '0;
        else en_dly <= en;
    end

    assign error_flag = (en && en_dly) ? (counter != shadow) : 1'b0;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) error_count <= '0;
        else if (error_flag && (&error_count != 1'b1)) error_count <= error_count + 1'b1;
    end

endmodule
