// ====================================================
// ECC (SECDED) 加固模板 — 简化 Hamming 码
// 使用位置 XOR 法: syndrome = XOR(所有数据位位置)
// 面积开销: ~1.4x (32-bit)
// 
// 包含:
//   1. ecc_encoder   — ECC 编码器
//   2. ecc_decoder   — 解码器 (SEC + DED)
//   3. ecc_register  — 带 ECC 的寄存器
//   4. ecc_bus       — 总线 ECC 保护
// ====================================================

`ifndef ECC_TEMPLATE_V
`define ECC_TEMPLATE_V

// clog2 函数
function integer clog2;
    input integer n;
    begin
        n = n - 1;
        for (clog2 = 0; n > 0; clog2 = clog2 + 1)
            n = n >> 1;
    end
endfunction

// ====================================================
// 1. ECC 编码器
// 使用位置 XOR 法: 对每个为 1 的数据位, XOR 其位置
// 输出: {global_parity, hamming_parity[P-2:0], data}
// ====================================================
module ecc_encoder #(
    parameter WIDTH = 8
) (
    input  wire [WIDTH-1:0] data,
    output wire [WIDTH + clog2(WIDTH):0] codeword  // WIDTH + P + GP bits = CW
);

    localparam P = clog2(WIDTH);    // Hamming 校验位数量 (不含全局)
    localparam GP = 1;              // 全局校验位 (DED 用)
    localparam CW = WIDTH + P + GP; // 总码字宽度

    // 计算 Hamming syndrome (位置 XOR)
    function [P-1:0] hamming_syndrome;
        input [WIDTH-1:0] d;
        integer i;
        reg [P-1:0] s;
        begin
            s = 0;
            for (i = 0; i < WIDTH; i = i + 1) begin
                if (d[i])
                    s = s ^ (i + 1);  // 1-indexed 位置
            end
            hamming_syndrome = s;
        end
    endfunction

    // 计算全局偶校验
    function global_parity;
        input [WIDTH-1:0] d;
        input [P-1:0] hp;
        begin
            global_parity = ^d ^ ^hp;
        end
    endfunction

    wire [P-1:0] hp;
    assign hp = hamming_syndrome(data);

    // codeword = {global_parity, hamming_parity[P-1:0], data[WIDTH-1:0]}
    assign codeword = {global_parity(data, hp), hp, data};

endmodule


// ====================================================
// 2. ECC 解码器 (SEC + DED)
// ====================================================
module ecc_decoder #(
    parameter WIDTH = 8
) (
    input  wire [WIDTH + clog2(WIDTH):0] codeword,
    output wire [WIDTH-1:0] data_corrected,
    output wire             single_error,   // 单比特错误已纠正
    output wire             double_error    // 双比特错误
);

    localparam P = clog2(WIDTH);
    localparam GP = 1;
    localparam CW = WIDTH + P + GP;

    // 解析码字
    wire stored_gp;                        // 存储的全局校验位
    wire [P-1:0] stored_hp;                // 存储的 Hamming 校验位
    wire [WIDTH-1:0] stored_data;          // 存储的数据
    assign {stored_gp, stored_hp, stored_data} = codeword;

    // 重新计算 Hamming syndrome
    reg [P-1:0] calc_hp;
    integer i;
    always @(*) begin
        calc_hp = 0;
        for (i = 0; i < WIDTH; i = i + 1) begin
            if (stored_data[i])
                calc_hp = calc_hp ^ (i + 1);
        end
    end

    // 计算校验子
    wire [P-1:0] syndrome;
    assign syndrome = stored_hp ^ calc_hp;

    // 重新计算全局偶校验
    wire calc_gp;
    assign calc_gp = ^stored_data ^ ^stored_hp;

    // 错误检测与纠正 (SECDED)
    //   syndrome == 0,  gp == calc_gp  → 无错误
    //   syndrome == 0,  gp != calc_gp  → GP校验位错误(或3+错误)
    //   syndrome != 0,  gp != calc_gp  → 单比特错误(奇数个翻转), 可纠正
    //   syndrome != 0,  gp == calc_gp  → 双比特错误(偶数个翻转), 不可纠正
    reg single_err, double_err;
    reg [WIDTH-1:0] corrected;
    always @(*) begin
        single_err = 0;
        double_err = 0;
        corrected = stored_data;

        if (syndrome == 0) begin
            // 无错误, 或全局校验位错误
            if (stored_gp != calc_gp)
                double_err = 1;  // GP校验位翻转(或3+错误)
        end else begin
            if (stored_gp != calc_gp) begin
                // 单比特错误 (奇数个翻转): 可以纠正
                single_err = 1;
                if (syndrome >= 1 && syndrome <= WIDTH)
                    corrected[syndrome - 1] = ~stored_data[syndrome - 1];
                // 如果 syndrome > WIDTH, 错误在校验位, 数据无需纠正
            end else begin
                // 双比特错误 (偶数个翻转): 不可纠正, 仅检错
                double_err = 1;
            end
        end
    end

    assign data_corrected = corrected;
    assign single_error = single_err;
    assign double_error = double_err;

endmodule


// ====================================================
// 3. 带 ECC 保护的寄存器
// ====================================================
module ecc_register #(
    parameter WIDTH = 8
) (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               en,
    input  wire [WIDTH-1:0]   d,
    output wire [WIDTH-1:0]   q,
    output wire               error_flag,   // 1=检测到不可纠正错误
    output wire               corrected     // 1=单比特错误已纠正
);

    localparam P = clog2(WIDTH);
    localparam GP = 1;
    localparam CW = WIDTH + P + GP;

    reg [CW-1:0] code_reg;

    wire [CW-1:0] encoded;
    ecc_encoder #(.WIDTH(WIDTH)) u_enc (
        .data(d),
        .codeword(encoded)
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            code_reg <= '0;
        else if (en)
            code_reg <= encoded;
    end

    ecc_decoder #(.WIDTH(WIDTH)) u_dec (
        .codeword(code_reg),
        .data_corrected(q),
        .single_error(corrected),
        .double_error(error_flag)
    );

endmodule


// ====================================================
// 4. 总线 ECC 保护
// ====================================================
module ecc_bus #(
    parameter WIDTH = 32
) (
    input  wire               clk,
    input  wire               rst_n,
    input  wire [WIDTH-1:0]   data_in,
    output wire [WIDTH-1:0]   data_out,
    output wire               error_flag,
    output wire               corrected
);

    localparam P = clog2(WIDTH);
    localparam GP = 1;
    localparam CW = WIDTH + P + GP;

    reg [CW-1:0] pipe_reg;

    wire [CW-1:0] encoded;
    ecc_encoder #(.WIDTH(WIDTH)) u_enc (
        .data(data_in),
        .codeword(encoded)
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            pipe_reg <= '0;
        else
            pipe_reg <= encoded;
    end

    ecc_decoder #(.WIDTH(WIDTH)) u_dec (
        .codeword(pipe_reg),
        .data_corrected(data_out),
        .single_error(corrected),
        .double_error(error_flag)
    );

endmodule

`endif
