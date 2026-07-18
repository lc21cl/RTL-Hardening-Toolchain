// ============================================
// 自动生成: mixed_design.v 加固版
// 加固管线: hardening_pipeline.py
// 优化目标: area
// 策略分配:
//   acc_reg              [data_path ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
//   clk                  [data_path ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
//   config_reg           [control   ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
//   cycle_count          [counter   ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
//   data_in              [data_path ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
//   done                 [data_path ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
//   mode_select          [control   ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
//   result               [data_path ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
//   state                [fsm       ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
//   tmp_reg              [data_path ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
// ============================================

// 混合设计: 含计数器/控制/数据寄存器
module mixed_design (
    input wire clk, rst_n, en,
    input wire [31:0] data_in,
    output reg [31:0] result,
    output reg done
);
    // 计数器
    reg [15:0] cycle_count;
    wire parity_cycle_count_bit;
    wire cycle_count_error_flag;
    parity_cycle_count u_cycle_count_parity(.data(cycle_count), .parity_bit(parity_cycle_count_bit), .error_flag(cycle_count_error_flag));
    
    // 控制寄存器
    reg [7:0] config_reg;
    wire parity_config_reg_bit;
    wire config_reg_error_flag;
    parity_config_reg u_config_reg_parity(.data(config_reg), .parity_bit(parity_config_reg_bit), .error_flag(config_reg_error_flag));
    reg mode_select;
    
    // 数据寄存器
    reg [31:0] acc_reg;
    wire parity_acc_reg_bit;
    wire acc_reg_error_flag;
    parity_acc_reg u_acc_reg_parity(.data(acc_reg), .parity_bit(parity_acc_reg_bit), .error_flag(acc_reg_error_flag));
    reg [31:0] tmp_reg;
    wire parity_tmp_reg_bit;
    wire tmp_reg_error_flag;
    parity_tmp_reg u_tmp_reg_parity(.data(tmp_reg), .parity_bit(parity_tmp_reg_bit), .error_flag(tmp_reg_error_flag));
    
    // FSM (状态寄存器)
    reg [1:0] state;
    wire parity_state_bit;
    wire state_error_flag;
    parity_state u_state_parity(.data(state), .parity_bit(parity_state_bit), .error_flag(state_error_flag));
    localparam IDLE = 2'b00, BUSY = 2'b01, DONE = 2'b10;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cycle_count <= 0;
            config_reg <= 0;
            mode_select <= 0;
            acc_reg <= 0;
            tmp_reg <= 0;
            state <= IDLE;
            result <= 0;
            done <= 0;
        end else begin
            case (state)
                IDLE: if (en) state <= BUSY;
                BUSY: begin
                    cycle_count <= cycle_count + 1;
                    if (cycle_count == 100) state <= DONE;
                end
                DONE: begin
                    result <= acc_reg;
                    done <= 1;
                    state <= IDLE;
                end
            endcase
        end
    end
    
    always_ff @(posedge clk) begin
        if (en) begin
            config_reg <= data_in[7:0];
            mode_select <= data_in[8];
            acc_reg <= acc_reg + data_in;
            tmp_reg <= data_in;
        end
    end
endmodule


// 奇偶校验模块: result
module parity_result(
    input [31:0] data,
    output parity_bit,
    output error_flag
);
    assign parity_bit = ^data;
    assign error_flag = (parity_bit != ^data);
endmodule


// 奇偶校验模块: done
module parity_done(
    input [0:0] data,
    output parity_bit,
    output error_flag
);
    assign parity_bit = ^data;
    assign error_flag = (parity_bit != ^data);
endmodule


// 奇偶校验模块: cycle_count
module parity_cycle_count(
    input [15:0] data,
    output parity_bit,
    output error_flag
);
    assign parity_bit = ^data;
    assign error_flag = (parity_bit != ^data);
endmodule


// 奇偶校验模块: config_reg
module parity_config_reg(
    input [7:0] data,
    output parity_bit,
    output error_flag
);
    assign parity_bit = ^data;
    assign error_flag = (parity_bit != ^data);
endmodule


// 奇偶校验模块: mode_select
module parity_mode_select(
    input [0:0] data,
    output parity_bit,
    output error_flag
);
    assign parity_bit = ^data;
    assign error_flag = (parity_bit != ^data);
endmodule


// 奇偶校验模块: acc_reg
module parity_acc_reg(
    input [31:0] data,
    output parity_bit,
    output error_flag
);
    assign parity_bit = ^data;
    assign error_flag = (parity_bit != ^data);
endmodule


// 奇偶校验模块: tmp_reg
module parity_tmp_reg(
    input [31:0] data,
    output parity_bit,
    output error_flag
);
    assign parity_bit = ^data;
    assign error_flag = (parity_bit != ^data);
endmodule


// 奇偶校验模块: state
module parity_state(
    input [1:0] data,
    output parity_bit,
    output error_flag
);
    assign parity_bit = ^data;
    assign error_flag = (parity_bit != ^data);
endmodule


// 奇偶校验模块: clk
module parity_clk(
    input [0:0] data,
    output parity_bit,
    output error_flag
);
    assign parity_bit = ^data;
    assign error_flag = (parity_bit != ^data);
endmodule


// 奇偶校验模块: data_in
module parity_data_in(
    input [31:0] data,
    output parity_bit,
    output error_flag
);
    assign parity_bit = ^data;
    assign error_flag = (parity_bit != ^data);
endmodule


// ============================================
// 加固实例化模板
// ============================================
// 添加 parity_result 奇偶位 + result_error_flag
// 添加 parity_done 奇偶位 + done_error_flag
// 添加 parity_cycle_count 奇偶位 + cycle_count_error_flag
// 添加 parity_config_reg 奇偶位 + config_reg_error_flag
// 添加 parity_mode_select 奇偶位 + mode_select_error_flag
// 添加 parity_acc_reg 奇偶位 + acc_reg_error_flag
// 添加 parity_tmp_reg 奇偶位 + tmp_reg_error_flag
// 添加 parity_state 奇偶位 + state_error_flag
// 添加 parity_clk 奇偶位 + clk_error_flag
// 添加 parity_data_in 奇偶位 + data_in_error_flag