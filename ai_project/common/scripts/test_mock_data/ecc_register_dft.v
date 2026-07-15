// ====================================================
// ecc_register_dft.v — 带 DFT 故障注入端口的 ECC 寄存器
//
// 基于 ecc_template.v 的 ecc_register 模块，添加：
//   1. fault_inject_en   — 故障注入使能
//   2. fault_bit_mask    — 数据位翻转掩码 (XOR 到 data 域)
//   3. fault_parity_mask — 校验位翻转掩码 (XOR 到 parity 域)
//
// 设计目的: Verilator 不支持 force/release，
// 通过 DFT 端口可在 C++ testbench 中直接注错。
//
// 监控输出:
//   single_err_detected  — 单比特错误检测 (SEC)
//   double_err_detected  — 双比特错误检测 (DED)
//   corrected_data       — 纠正后的数据 (同 q)
// ====================================================

`ifndef ECC_REGISTER_DFT_V
`define ECC_REGISTER_DFT_V

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
// 1. ECC 编码器 (SECDED Hamming Code)
// ====================================================
module ecc_encoder_dft #(
    parameter WIDTH = 32
) (
    input  wire [WIDTH-1:0] data,
    output wire [WIDTH + clog2(WIDTH):0] codeword
);

    localparam P = clog2(WIDTH);
    localparam GP = 1;
    localparam CW = WIDTH + P + GP;

    // Hamming syndrome: position XOR (1-indexed)
    function [P-1:0] hamming_syndrome;
        input [WIDTH-1:0] d;
        integer i;
        reg [P-1:0] s;
        begin
            s = 0;
            for (i = 0; i < WIDTH; i = i + 1) begin
                if (d[i])
                    // verilator lint_off WIDTHEXPAND
                    // verilator lint_off WIDTHTRUNC
                    s = s ^ (i + 1);
                    // verilator lint_on WIDTHTRUNC
                    // verilator lint_on WIDTHEXPAND
            end
            hamming_syndrome = s;
        end
    endfunction

    // Global even parity
    function global_parity;
        input [WIDTH-1:0] d;
        input [P-1:0] hp;
        begin
            global_parity = ^d ^ ^hp;
        end
    endfunction

    wire [P-1:0] hp;
    assign hp = hamming_syndrome(data);
    assign codeword = {global_parity(data, hp), hp, data};

endmodule


// ====================================================
// 2. ECC 解码器 (SEC + DED)
// ====================================================
module ecc_decoder_dft #(
    parameter WIDTH = 32
) (
    input  wire [WIDTH + clog2(WIDTH):0] codeword,
    output wire [WIDTH-1:0] data_corrected,
    output wire             single_error,
    output wire             double_error
);

    localparam P = clog2(WIDTH);
    localparam GP = 1;
    localparam CW = WIDTH + P + GP;

    wire stored_gp;
    wire [P-1:0] stored_hp;
    wire [WIDTH-1:0] stored_data;
    assign {stored_gp, stored_hp, stored_data} = codeword;

    // Recompute Hamming syndrome
    reg [P-1:0] calc_hp;
    integer i;
    always @(*) begin
        calc_hp = 0;
        for (i = 0; i < WIDTH; i = i + 1) begin
            if (stored_data[i])
                // verilator lint_off WIDTHEXPAND
                // verilator lint_off WIDTHTRUNC
                calc_hp = calc_hp ^ (i + 1);
                // verilator lint_on WIDTHTRUNC
                // verilator lint_on WIDTHEXPAND
        end
    end

    wire [P-1:0] syndrome;
    assign syndrome = stored_hp ^ calc_hp;

    wire calc_gp;
    assign calc_gp = ^stored_data ^ ^stored_hp;

    reg single_err, double_err;
    reg [WIDTH-1:0] corrected;
    always @(*) begin
        single_err = 0;
        double_err = 0;
        corrected = stored_data;

        if (syndrome == 0) begin
            if (stored_gp != calc_gp)
                double_err = 1;  // GP parity bit flipped (or 3+ errors)
        end else begin
            if (stored_gp != calc_gp) begin
                // Single-bit error: correctable
                single_err = 1;
                // verilator lint_off WIDTHEXPAND
                if (syndrome >= 1 && syndrome <= WIDTH[P-1:0])
                // verilator lint_on WIDTHEXPAND
                    corrected[syndrome - 1] = ~stored_data[syndrome - 1];
            end else begin
                // Double-bit error: detectable only
                double_err = 1;
            end
        end
    end

    assign data_corrected = corrected;
    assign single_error = single_err;
    assign double_error = double_err;

endmodule


// ====================================================
// 3. 带 DFT 故障注入的 ECC 寄存器
// ====================================================
module ecc_register_dft #(
    parameter WIDTH = 32
) (
    // 标准接口
    input  wire               clk,
    input  wire               rst_n,
    input  wire               en,
    input  wire [WIDTH-1:0]   d,
    output wire [WIDTH-1:0]   q,
    output wire               error_flag,    // 不可纠正错误 (DED)
    output wire               corrected,     // 单比特错误已纠正 (SEC)

    // DFT 故障注入端口 (替代 force/release)
    input  wire               fault_inject_en,     // 故障注入使能
    input  wire [WIDTH-1:0]   fault_bit_mask,      // 数据位翻转掩码
    input  wire [clog2(WIDTH)-1:0] fault_parity_mask, // 校验位翻转掩码

    // 监控输出
    output reg                single_err_detected,  // 单比特错误检测标志
    output reg                double_err_detected,  // 双比特错误检测标志
    output wire [WIDTH-1:0]   corrected_data        // 纠正后数据
);

    localparam P = clog2(WIDTH);
    localparam GP = 1;
    localparam CW = WIDTH + P + GP;

    reg [CW-1:0] code_reg;

    // 编码: 将输入数据编码为码字
    wire [CW-1:0] encoded;
    ecc_encoder_dft #(.WIDTH(WIDTH)) u_enc (
        .data(d),
        .codeword(encoded)
    );

    // 时序逻辑: 复位 / 正常写入 / 故障注入
    // 码字布局: {global_parity(1), hamming_parity(P), data(WIDTH)}
    // fault_inject_en 时: 对编码后的码字 XOR 故障掩码, 模拟 SEU
    //   掩码结构: {1'b0(不翻转GP), fault_parity_mask(P), fault_bit_mask(W)}
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            code_reg <= '0;
        end else if (fault_inject_en) begin
            // DFT 故障注入: encoded XOR 故障掩码
            // 全局校验位不翻转 (保留 DED 能力)
            code_reg <= encoded ^ {{1{1'b0}}, fault_parity_mask, fault_bit_mask};
        end else if (en) begin
            code_reg <= encoded;
        end
    end

    // 解码: 从码字中恢复数据 + 错误检测
    wire dec_single_err, dec_double_err;
    ecc_decoder_dft #(.WIDTH(WIDTH)) u_dec (
        .codeword(code_reg),
        .data_corrected(q),
        .single_error(dec_single_err),
        .double_error(dec_double_err)
    );

    assign corrected_data = q;
    assign error_flag = dec_double_err;
    assign corrected = dec_single_err;

    // 监控输出
    always @(*) begin
        single_err_detected = dec_single_err;
        double_err_detected = dec_double_err;
    end

endmodule

`endif
