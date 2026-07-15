
// ============================================================
// 测试用计数器模块 (包含 3 种计数器模式)
// 用途: 演示 cnt_comp AST 变换
// ============================================================

module test_counter_module (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        en,
    input  wire [31:0] max_val,
    output reg  [31:0] up_counter,
    output reg  [31:0] down_counter,
    output reg  [7:0]  mod_counter
);

    // ---- 递增计数器 (up_counter) ----
    // 模式: reg <= reg + 1
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) up_counter <= 32'd0;
        else if (en) up_counter <= up_counter + 1'b1;
    end

    // ---- 递减计数器 (down_counter) ----
    // 模式: reg <= reg - 1
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) down_counter <= 32'hFFFFFFFF;
        else if (en) down_counter <= down_counter - 1'b1;
    end

    // ---- 模计数器 (mod_counter, 0->255->0) ----
    // 模式: if (reg == MAX) reg <= 0 else reg <= reg + 1
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) mod_counter <= 8'd0;
        else if (en) begin
            if (mod_counter == 8'd255)
                mod_counter <= 8'd0;
            else
                mod_counter <= mod_counter + 1'b1;
        end
    end

    // ---- 非计数器寄存器 (不应被匹配) ----
    reg [7:0] config_reg;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) config_reg <= 8'd0;
        else if (en) config_reg <= max_val[7:0];
    end

endmodule
