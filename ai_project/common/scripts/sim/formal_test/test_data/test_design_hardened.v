// ============================================
// 自动生成: test_design.v 加固版
// 加固管线: hardening_pipeline.py
// 优化目标: reliability
// 策略分配:
//   count                [counter   ] → cnt_comp: 计数器比较器 (0.3×)
// ============================================


module test_design(
    input clk,
    input rst_n,
    input [7:0] data_in,
    output [7:0] data_out,
    output reg [3:0] count
);

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        count <= 4'b0;
    end else begin
        count <= count + 1'b1;
    end
end

assign data_out = data_in;

endmodule


// ============================================
// 加固实例化模板
// ============================================
// 替换 reg [3:0] count → 实例化 cnt_comp_up