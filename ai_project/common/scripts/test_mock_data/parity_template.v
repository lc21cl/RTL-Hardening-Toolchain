// ====================================================
// 奇偶校验加固模板
// 面积开销: ~0.03x (32-bit) 到 ~0.1x (8-bit)
// 适用场景: 控制寄存器、总线通信、非关键数据
// 
// 包含:
//   1. parity_gen  — 奇偶位生成器 (纯组合)
//   2. parity_check — 奇偶校验器 (含错误标志)
//   3. parity_register — 带奇偶校验的寄存器
//   4. parity_bus — 总线奇偶校验
//   5. parity_byte  — 字节奇偶校验 (parity_byte 模式)
// ====================================================

`ifndef PARITY_TEMPLATE_V
`define PARITY_TEMPLATE_V

// ====================================================
// 1. 奇偶位生成器 (纯组合)
// ====================================================
module parity_gen #(
    parameter WIDTH = 8,
    parameter EVEN  = 1        // 1=偶校验, 0=奇校验
) (
    input  wire [WIDTH-1:0] data,
    output wire              parity
);
    // 偶校验: parity = XOR of all data bits
    // 奇校验: parity = NOT(XOR of all data bits)
    wire xor_tree;

    generate
        if (WIDTH == 1) begin
            assign xor_tree = data[0];
        end else begin
            genvar i;
            wire [WIDTH-1:0] x;
            assign x[0] = data[0];
            for (i = 1; i < WIDTH; i = i + 1) begin : gen_xor
                assign x[i] = x[i-1] ^ data[i];
            end
            assign xor_tree = x[WIDTH-1];
        end
    endgenerate

    assign parity = EVEN ? xor_tree : ~xor_tree;

endmodule


// ====================================================
// 2. 奇偶校验器
// ====================================================
module parity_check #(
    parameter WIDTH = 8,
    parameter EVEN  = 1
) (
    input  wire [WIDTH-1:0] data,
    input  wire              parity_in,
    output wire              error_flag   // 1=奇偶错误
);
    wire expected_parity;
    parity_gen #(.WIDTH(WIDTH), .EVEN(EVEN)) u_gen (
        .data(data), .parity(expected_parity)
    );
    assign error_flag = (parity_in != expected_parity);
endmodule


// ====================================================
// 3. 带奇偶校验的寄存器 (推荐用法)
// 每写入一次, 自动生成并存储奇偶位
// 每读取时, 自动校验
// ====================================================
module parity_register #(
    parameter WIDTH   = 8,
    parameter EVEN    = 1,
    parameter CW      = 5     // 错误计数器位宽
) (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               en,
    input  wire [WIDTH-1:0]   d,
    output wire [WIDTH-1:0]   q,
    output wire               error_flag,
    output reg  [CW-1:0]      error_count
);
    // 存储数据和奇偶位
    reg [WIDTH-1:0] data_reg;
    reg parity_reg;

    // 写: 存储数据 + 生成奇偶位 (直接计算, 避免中间 wire delta 竞争)
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_reg   <= '0;
            parity_reg <= '0;
        end else if (en) begin
            data_reg   <= d;
            parity_reg <= ^d;  // 直接 XOR 计算偶校验, 避免通过 wire 引入 delta 延迟
        end
    end

    // 输出
    assign q = data_reg;

    // 校验: 读取时检查存储的奇偶位是否与存储的数据匹配
    // 使用 data_reg 直接计算, 确保与写入时的计算一致
    wire stored_parity_expected;
    assign stored_parity_expected = ^data_reg;  // 直接 XOR 计算
    assign error_flag = (parity_reg != stored_parity_expected);

    // 错误计数
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) error_count <= '0;
        else if (error_flag && (&error_count != 1'b1))
            error_count <= error_count + 1'b1;
    end

endmodule


// ====================================================
// 4. 总线奇偶校验 (带 1 周期 pipeline 检查)
// 适用: 跨时钟域/长距离总线
// ====================================================
module parity_bus #(
    parameter WIDTH = 32,
    parameter EVEN  = 1
) (
    input  wire               clk,
    input  wire               rst_n,
    input  wire [WIDTH-1:0]   data_in,
    input  wire               data_parity_in,   // 发送端奇偶位
    output wire [WIDTH-1:0]   data_out,
    output wire               error_flag
);
    reg [WIDTH-1:0] data_pipe;
    reg parity_pipe;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_pipe   <= '0;
            parity_pipe <= '0;
        end else begin
            data_pipe   <= data_in;
            parity_pipe <= data_parity_in;
        end
    end

    parity_check #(.WIDTH(WIDTH), .EVEN(EVEN)) u_check (
        .data(data_pipe), .parity_in(parity_pipe), .error_flag(error_flag)
    );

    assign data_out = data_pipe;
endmodule


// ====================================================
// 5. 字节奇偶校验 (parity_byte 模式)
// 每字节一个奇偶位, 适合 32-bit 数据
// 面积: 4 奇偶位 + 4 生成器 = ~0.06x
// ====================================================
module parity_byte #(
    parameter BYTES = 4,
    parameter EVEN  = 1
) (
    input  wire [BYTES*8-1:0] data,
    output wire [BYTES-1:0]    parity_bits,
    output wire                error_flag
);
    genvar i;
    wire [BYTES-1:0] errors;

    generate
        for (i = 0; i < BYTES; i = i + 1) begin : gen_byte
            parity_gen #(.WIDTH(8), .EVEN(EVEN)) u_gen (
                .data(data[i*8 +: 8]), .parity(parity_bits[i])
            );
        end
    endgenerate

    assign error_flag = |errors;
endmodule

`endif
