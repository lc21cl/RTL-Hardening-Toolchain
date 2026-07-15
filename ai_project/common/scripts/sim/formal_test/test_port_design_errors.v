// ------------------------------------------------------------
// test_port_design_errors.v — 设计级端口错误测试用例
//
// 本文件包含 3 种设计级错误（非语法错误）:
//   ERROR #1 — 端口方向错误: 将 output 端口 (carry) 连接到
//               input 信号 (rst_n)，导致方向冲突
//   ERROR #2 — 端口类型错误: 用 reg 信号连接 output wire 端口
//               (carry)，但未在 continuous assignment 中驱动
//   ERROR #3 — 端口数量错误: 实例化时端口连接数与声明不匹配
//               (遗漏了 carry 端口)
//
// 这些错误能通过 yosys 综合检查检测到，但不会被语法检查捕获，
// 属于设计级问题。
// ------------------------------------------------------------

module test_port_errors (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  data_a,
    input  wire [7:0]  data_b,
    output wire [7:0]  result,
    output wire        flag
);

    // ================================================================
    // ERROR #1 — 端口方向错误
    // 将 sub_module 的 output 'carry' 连接到 input 'rst_n'，
    // rst_n 在 top 中是 input，但在实例中同时作为 input 和 output
    // 的驱动器，产生方向冲突。
    // ================================================================
    adder_sub u_adder_dir_error (
        .clk   (clk),
        .rst_n (carry_sig),     // ← 方向错误: carry_sig 应连接到 .carry
        .a     (data_a),
        .b     (data_b),
        .sum   (result),
        .carry (carry_sig)      // ← 方向错误: carry_sig 同时连接 input 和 output
    );

    // ================================================================
    // ERROR #2 — 端口类型错误
    // carry_sig 声明为 reg，但连接到 output wire 端口。
    // 综合工具会警告 wire/reg 类型不匹配。
    // ================================================================
    reg carry_sig;              // ← 类型错误: 应为 wire（output 端口类型是 wire）

    // ================================================================
    // ERROR #3 — 端口数量错误
    // 另一个实例遗漏了 carry 端口连接 (只有 5 个连接而非 6 个)
    // ================================================================
    adder_sub u_adder_count_error (
        .clk   (clk),
        .rst_n (rst_n),
        .a     (data_a),
        .b     (data_b)
        // .sum 和 .carry 未连接 — 端口数量不匹配
    );

    wire [7:0] internal_result;
    assign result = internal_result;

    assign flag = carry_sig;

endmodule
