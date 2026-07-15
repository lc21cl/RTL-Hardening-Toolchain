// ============================================================
// test_buggy_design.v — 含语法错误+端口不匹配的测试用例
// 用于验证 Auto-Repair 闭环修复效果
// 故意构造的错误:
//   1. 第34行缺少分号
//   2. 端口列表没有 direction 声明（旧风格）
//   3. output 端口缺少 wire/reg 类型
//   4. assign 语句缺少分号
//   5. 端口数量不匹配（声明 4 个，使用 6 个信号）
// ============================================================

module test_buggy_design (
    input clk,
    input rst_n,
    input [7:0] data_in,
    output [7:0] data_out,
    output valid,
    input enable
);
    wire [7:0] internal_bus
    assign internal_bus = data_in + 8'h01

    reg [7:0] result_reg;
    reg valid_reg;

    // 组合逻辑
    always @(*) begin
        if (enable) begin
            result_reg = internal_bus;
            valid_reg = 1'b1;
        end else begin
            result_reg = 8'b0;
            valid_reg = 1'b0;
        end
    end

    // 时序逻辑
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out <= 8'b0;
            valid    <= 1'b0;
        end else begin
            data_out <= result_reg;
            valid    <= valid_reg;
        end
    end

endmodule
