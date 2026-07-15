// ============================================
// 自动生成: mixed_design.v 加固版
// 加固管线: hardening_pipeline.py
// 优化目标: area
// 策略分配:
//   acc_reg              [data_path ] → Full TMR: 3 副本 + 多数表决器 (3.0×)
//   config_reg           [control   ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
//   cycle_count          [counter   ] → cnt_comp: 计数器比较器 (0.3×)
//   mode_select          [control   ] → 奇偶校验: 奇偶位生成+检查 (0.03×)
//   state                [fsm       ] → TMR_state: 状态寄存器三重化 (2.5×)
//   tmp_reg              [data_path ] → Full TMR: 3 副本 + 多数表决器 (3.0×)
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
    
    // 控制寄存器
    reg [7:0] config_reg;
    reg mode_select;
    
    // 数据寄存器
    reg [31:0] acc_reg;
    reg [31:0] tmp_reg;
    
    // FSM (状态寄存器)
    reg [1:0] state;
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


// ============================================
// 加固实例化模板
// ============================================
// 替换 reg [15:0] cycle_count → 实例化 cnt_comp_up
// 添加 parity_config_reg 奇偶位 + config_reg_error_flag
// 添加 parity_mode_select 奇偶位 + mode_select_error_flag
// 替换 reg [1:0] state → 3 副本 + 多数表决器 + fsm_error