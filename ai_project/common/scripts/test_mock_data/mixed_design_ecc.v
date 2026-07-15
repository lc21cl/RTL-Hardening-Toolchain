// ====================================================
// mixed_design_ecc.v — ECC (SECDED) 加固示例
// 基于 mixed_design.v，使用 ecc_template.v 中的
// ecc_register 模块对 acc_reg 和 tmp_reg 进行加固。
//
// 变换说明:
//   1. `include "ecc_template.v"   — 引入 ECC 模板
//   2. SEC_DED 参数                — 1=ECC加固, 0=原始版本
//   3. generate 块                 — 条件编译 ECC/非ECC
//   4. ecc_register 实例化         — 替换 reg [31:0] acc_reg/tmp_reg
//   5. error_flag / corrected      — 错误监测信号上引出
//   6. ecc_error_count             — 8-bit 错误计数器(饱和计数)
//   7. 原始 FSM/cycle_count 保持不变
// ====================================================

`timescale 1ns/1ps

`include "ecc_template.v"

// ====================================================
// 模块: mixed_design_ecc
// 描述: 含 SECDED ECC 加固的混合设计 (计数器/控制/数据寄存器)
// 端口与原版 mixed_design 完全一致
// ====================================================
module mixed_design_ecc #(
    parameter SEC_DED = 1  // 0=原始版本(无ECC), 1=ECC加固版本
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       en,
    input  wire [31:0] data_in,
    output reg  [31:0] result,
    output reg         done
);

    // --------------------------------------------------
    // 保持原样的信号 (FSM 状态机 + 计数器)
    // --------------------------------------------------
    reg [15:0] cycle_count;          // 计数器
    reg [7:0]  config_reg;           // 控制寄存器 (低8位)
    reg        mode_select;           // 控制寄存器 (bit8)
    reg [1:0]  state;                // FSM 状态寄存器 (未加固)
    localparam IDLE = 2'b00,
               BUSY = 2'b01,
               DONE = 2'b10;

    // --------------------------------------------------
    // ECC 错误监测 (在 SEC_DED=1 时由 generate 驱动)
    // --------------------------------------------------
    reg [7:0] ecc_error_count;       // ECC 错误计数器, 饱和至 255
    wire      ecc_any_error;         // 任意 ECC 实例报告不可纠正错误

    // --------------------------------------------------
    // 统一读取接口: 在两种模式下均可通过 acc_reg_q/tmp_reg_q 读取
    // - SEC_DED=1: 直接连接 ecc_register 的 q 输出
    // - SEC_DED=0: 通过 assign 镜像原始 reg 的值
    // --------------------------------------------------
    wire [31:0] acc_reg_q;
    wire [31:0] tmp_reg_q;

    // --------------------------------------------------
    // 条件生成: ECC 加固 / 原始逻辑
    // --------------------------------------------------
    generate
        if (SEC_DED) begin : gen_ecc_on
            // ==========================================
            // ECC 加固分支
            //
            // 变换1: acc_reg (累加器模式)
            //   原始: acc_reg <= acc_reg + data_in
            //   加固: acc_reg_next = acc_reg_q + data_in  (组合逻辑)
            //         ecc_register 在 en=1 时采样 acc_reg_next
            //         q 输出替代 acc_reg 的读取
            //
            // 变换2: tmp_reg (简单存储)
            //   原始: tmp_reg <= data_in
            //   加固: d = data_in, q 替代 tmp_reg 的读取
            // ==========================================

            // --- acc_reg: 累加器 ECC 加固 ---
            wire [31:0] acc_reg_next;
            wire        acc_err;
            wire        acc_corrected;

            // 累加器组合逻辑: 使用 ECC 保护的 q 输出代替原始 acc_reg 读取
            assign acc_reg_next = acc_reg_q + data_in;

            // ecc_register 实例化 — 替换 reg [31:0] acc_reg
            //   .d = acc_reg_next   → 累加结果写入 ECC 寄存器
            //   .q = acc_reg_q      → ECC 纠正后的数据输出
            //   .en = en            → 原始代码中 acc_reg 仅在 en=1 时更新
            //   .error_flag = acc_err     → 不可纠正错误 (DED)
            //   .corrected = acc_corrected → 单比特错误已纠正 (SEC)
            ecc_register #(
                .WIDTH(32)
            ) u_ecc_acc (
                .clk        (clk),
                .rst_n      (rst_n),
                .en         (en),
                .d          (acc_reg_next),
                .q          (acc_reg_q),
                .error_flag (acc_err),
                .corrected  (acc_corrected)
            );

            // --- tmp_reg: 简单存储 ECC 加固 ---
            wire tmp_err;
            wire tmp_corrected;

            // ecc_register 实例化 — 替换 reg [31:0] tmp_reg
            //   .d = data_in      → 直接存储输入数据
            //   .q = tmp_reg_q    → ECC 纠正后的数据输出
            //   .en = en          → 原始代码中 tmp_reg 仅在 en=1 时更新
            //   .error_flag = tmp_err     → 不可纠正错误
            //   .corrected = tmp_corrected → 单比特错误已纠正
            ecc_register #(
                .WIDTH(32)
            ) u_ecc_tmp (
                .clk        (clk),
                .rst_n      (rst_n),
                .en         (en),
                .d          (data_in),
                .q          (tmp_reg_q),
                .error_flag (tmp_err),
                .corrected  (tmp_corrected)
            );

            // 汇总错误标志: 两个 ECC 实例任一报告不可纠正错误
            assign ecc_any_error = acc_err | tmp_err;

        end else begin : gen_ecc_off
            // ==========================================
            // 原始 (非ECC) 分支
            //
            // 保持与原版 mixed_design.v 完全一致的行为
            // ==========================================

            // 原始寄存器声明
            reg [31:0] acc_reg;
            reg [31:0] tmp_reg;

            // 将 reg 值镜像到 wire 接口, 供公共逻辑读取
            assign acc_reg_q = acc_reg;
            assign tmp_reg_q = tmp_reg;

            // 非ECC模式下无错误事件
            assign ecc_any_error = 1'b0;

            // acc_reg / tmp_reg 的复位与赋值逻辑
            // (原本分散在两个 always_ff 中, 此处合并以保持 generate 封装性)
            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    acc_reg <= 32'd0;
                    tmp_reg <= 32'd0;
                end else if (en) begin
                    acc_reg <= acc_reg + data_in;   // 累加器
                    tmp_reg <= data_in;              // 简单存储
                end
            end

        end
    endgenerate


    // --------------------------------------------------
    // 公共时序逻辑 (FSM + 计数器 + 控制寄存器)
    //
    // 注意:
    //   - acc_reg / tmp_reg 的赋值由 generate 分支处理, 此处不涉及
    //   - 读取 acc_reg/tmp_reg 均通过 acc_reg_q/tmp_reg_q wire
    // --------------------------------------------------

    // 主状态机 + 计数器 (含复位)
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cycle_count <= 16'd0;
            config_reg  <= 8'd0;
            mode_select <= 1'b0;
            state       <= IDLE;
            result      <= 32'd0;
            done        <= 1'b0;
        end else begin
            case (state)
                IDLE: begin
                    if (en)
                        state <= BUSY;
                end

                BUSY: begin
                    cycle_count <= cycle_count + 16'd1;
                    if (cycle_count == 16'd100)
                        state <= DONE;
                end

                DONE: begin
                    // 使用 acc_reg_q 而非 acc_reg:
                    //   SEC_DED=1 时是 ECC 纠正后的数据
                    //   SEC_DED=0 时是原始 reg 的镜像
                    result <= acc_reg_q;
                    done   <= 1'b1;
                    state  <= IDLE;
                end
            endcase
        end
    end

    // 控制寄存器更新 (无复位, 仅 en 使能)
    always_ff @(posedge clk) begin
        if (en) begin
            config_reg  <= data_in[7:0];
            mode_select <= data_in[8];
        end
    end


    // --------------------------------------------------
    // ECC 错误计数器
    //
    // 在 SEC_DED=1 时:
    //   - 任何 ecc_register 实例检测到不可纠正错误 (error_flag=1)
    //     则计数器递增
    //   - 计数器饱和至 255 后停止计数
    //
    // 在 SEC_DED=0 时:
    //   - ecc_any_error 恒为 0, 计数器永不递增
    // --------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ecc_error_count <= 8'd0;
        end else if (ecc_any_error && (&ecc_error_count != 1'b1)) begin
            // 存在未纠正错误且计数器未饱和 → 递增
            ecc_error_count <= ecc_error_count + 8'd1;
        end
    end

endmodule
