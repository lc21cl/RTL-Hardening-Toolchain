// ------------------------------------------------------------
// test_complex_repair.v — 复杂 Verilog 测试用例
// 包含以下设计错误用于验证 SyntaxFixer 规则:
//   [1] inout 端口 (test inout_without_direction)
//   [2] 缺失 endgenerate (test missing_endgenerate)
//   [3] 缺失分号 (test missing_semicolon)
//   [4] 参数无默认值 (test missing_parameter_default)
//   [5] generate 块未闭合
//   [6] 敏感列表缺少 or
// ------------------------------------------------------------

module test_complex_repair #(
    parameter DATA_WIDTH = 0,          // [4] 参数无默认值
    parameter ADDR_WIDTH = 8
) (
    inout wire [7:0] data_bus,    // [1] inout 端口
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] addr,
    output reg  [7:0] result
);

    // 内部信号
    wire [7:0] internal_data;
    reg  [7:0] shift_reg;

    // Generate 块 — 有 begin 无 endgenerate
    generate
        if (DATA_WIDTH > 8) begin : gen_wide
            assign internal_data = data_bus;
        end else begin : gen_narrow
            assign internal_data = data_bus;
        end
    // [2] 缺失 endgenerate

    // 第二个 generate 块
    generate
        for (genvar i = 0; i < 4; i++) begin : gen_shift
            always @(posedge clk) begin
                if (i == 0)
                    shift_reg[i*2+:2] <= data_bus[i*2+:2];
                else
                    shift_reg[i*2+:2] <= shift_reg[(i-1)*2+:2];
            end
        end
    endgenerate  // 这个有 endgenerate

    // 敏感列表缺少 or
    always @(posedge clk or negedge rst_n) begin  // [6] 缺少 or
        if (!rst_n)
            result <= 8'b0;
        else
            result <= internal_data;
    end

    // 缺失分号
    wire [7:0] debug_bus; // [3] 缺失分号;
    assign debug_bus = addr; // [3] 缺失分号


    // Case 语句无 default
    always @(*) begin
        case (addr[1:0])
            2'b00: result = internal_data;
            2'b01: result = shift_reg;
            2'b10: result = 8'hFF;
            // [no default]
        default : ;
    endcase
    end

endgenerate
endmodule
// 注意: 没有缺失 endmodule
