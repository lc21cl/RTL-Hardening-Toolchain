// ------------------------------------------------------------
// adder_sub.v — 正确的子模块（用于端口错误测试的引用）
// ------------------------------------------------------------
module adder_sub (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  a,
    input  wire [7:0]  b,
    output reg  [7:0]  sum,
    output wire        carry
);

    assign carry = &a | &b;  // 简单的 carry 生成

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            sum <= 8'h00;
        else
            sum <= a + b;
    end

endmodule
