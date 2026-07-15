# ============================================================
# tmr_voter_6ch_timing.xdc — 6 通道 TMR 表决器时序约束
#
# 适用器件: Xilinx 7-series / UltraScale / UltraScale+
# 设计特性: 纯组合逻辑 (2 级 LUT3 深度)
# 时钟频率: 10 MHz (周期 100 ns)
# ============================================================

# ====== 时钟定义 ======
create_clock -period 100.000 -name clk [get_ports clk]

# ====== 时钟抖动 ======
set_clock_uncertainty -setup 0.500 [get_clocks clk]
set_clock_uncertainty -hold  0.300 [get_clocks clk]

# ====== 输入延迟约束 ======
# 假设外部寄存器输出延迟 ~2 ns (参考 10 MHz 系统)
set_input_delay -clock clk -max 2.000 [get_ports core1_ready]
set_input_delay -clock clk -max 2.000 [get_ports core2_ready]
set_input_delay -clock clk -max 2.000 [get_ports core3_ready]
set_input_delay -clock clk -max 2.000 [get_ports core1_boot_valid]
set_input_delay -clock clk -max 2.000 [get_ports core2_boot_valid]
set_input_delay -clock clk -max 2.000 [get_ports core3_boot_valid]
set_input_delay -clock clk -max 2.000 [get_ports core1_exit_valid]
set_input_delay -clock clk -max 2.000 [get_ports core2_exit_valid]
set_input_delay -clock clk -max 2.000 [get_ports core3_exit_valid]
set_input_delay -clock clk -max 2.000 [get_ports core1_exit_code]
set_input_delay -clock clk -max 2.000 [get_ports core2_exit_code]
set_input_delay -clock clk -max 2.000 [get_ports core3_exit_code]
set_input_delay -clock clk -max 2.000 [get_ports core1_print_valid]
set_input_delay -clock clk -max 2.000 [get_ports core2_print_valid]
set_input_delay -clock clk -max 2.000 [get_ports core3_print_valid]
set_input_delay -clock clk -max 2.000 [get_ports core1_print_data]
set_input_delay -clock clk -max 2.000 [get_ports core2_print_data]
set_input_delay -clock clk -max 2.000 [get_ports core3_print_data]

# 输入最小延迟 (保持时间)
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core1_ready]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core2_ready]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core3_ready]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core1_boot_valid]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core2_boot_valid]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core3_boot_valid]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core1_exit_valid]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core2_exit_valid]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core3_exit_valid]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core1_exit_code]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core2_exit_code]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core3_exit_code]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core1_print_valid]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core2_print_valid]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core3_print_valid]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core1_print_data]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core2_print_data]
set_input_delay -clock clk -min -add_delay 0.500 [get_ports core3_print_data]

# ====== 输出延迟约束 ======
# 组合输出直接连接到目标寄存器输入
set_output_delay -clock clk -max 3.000 [get_ports voted_ready]
set_output_delay -clock clk -max 3.000 [get_ports voted_boot_valid]
set_output_delay -clock clk -max 3.000 [get_ports voted_exit_valid]
set_output_delay -clock clk -max 3.000 [get_ports voted_exit_code]
set_output_delay -clock clk -max 3.000 [get_ports voted_print_valid]
set_output_delay -clock clk -max 3.000 [get_ports voted_print_data]

set_output_delay -clock clk -min -add_delay 0.500 [get_ports voted_ready]
set_output_delay -clock clk -min -add_delay 0.500 [get_ports voted_boot_valid]
set_output_delay -clock clk -min -add_delay 0.500 [get_ports voted_exit_valid]
set_output_delay -clock clk -min -add_delay 0.500 [get_ports voted_exit_code]
set_output_delay -clock clk -min -add_delay 0.500 [get_ports voted_print_valid]
set_output_delay -clock clk -min -add_delay 0.500 [get_ports voted_print_data]

# ====== 组合逻辑路径约束 ======
# 由于表决器是纯组合逻辑，需要约束 max delay 确保内部路径时序
set_max_delay -from [get_ports core1_ready]      -to [get_ports voted_ready]      2.000
set_max_delay -from [get_ports core2_ready]      -to [get_ports voted_ready]      2.000
set_max_delay -from [get_ports core3_ready]      -to [get_ports voted_ready]      2.000
set_max_delay -from [get_ports core1_boot_valid] -to [get_ports voted_boot_valid] 2.000
set_max_delay -from [get_ports core2_boot_valid] -to [get_ports voted_boot_valid] 2.000
set_max_delay -from [get_ports core3_boot_valid] -to [get_ports voted_boot_valid] 2.000
set_max_delay -from [get_ports core1_exit_valid] -to [get_ports voted_exit_valid] 2.000
set_max_delay -from [get_ports core2_exit_valid] -to [get_ports voted_exit_valid] 2.000
set_max_delay -from [get_ports core3_exit_valid] -to [get_ports voted_exit_valid] 2.000
set_max_delay -from [get_ports core1_print_valid] -to [get_ports voted_print_valid] 2.000
set_max_delay -from [get_ports core2_print_valid] -to [get_ports voted_print_valid] 2.000
set_max_delay -from [get_ports core3_print_valid] -to [get_ports voted_print_valid] 2.000
set_max_delay -from [get_ports core1_exit_code]  -to [get_ports voted_exit_code]  2.000
set_max_delay -from [get_ports core2_exit_code]  -to [get_ports voted_exit_code]  2.000
set_max_delay -from [get_ports core3_exit_code]  -to [get_ports voted_exit_code]  2.000
set_max_delay -from [get_ports core1_print_data] -to [get_ports voted_print_data] 2.000
set_max_delay -from [get_ports core2_print_data] -to [get_ports voted_print_data] 2.000
set_max_delay -from [get_ports core3_print_data] -to [get_ports voted_print_data] 2.000

# ====== 误路径 ======
# 没有时钟域交叉，无需 false_path

# ====== 布局布线选项 ======
# 建议: 如果时序紧张，可启用重定时
# set_property OPTIMIZE_BINDING true [current_design]
