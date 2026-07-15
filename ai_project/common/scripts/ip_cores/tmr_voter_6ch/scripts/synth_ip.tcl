# ============================================================
# synth_ip.tcl — IP 独立综合脚本
#
# 对 tmr_voter_6ch_xilinx 进行独立综合并报告资源与时序。
#
# 用法:
#   cd scripts/
#   vivado -source synth_ip.tcl -mode batch
# ============================================================

# 读取 RTL 源码
read_verilog ../src/tmr_voter_6ch_xilinx.v

# 指定顶层模块和目标器件
synth_design -top tmr_voter_6ch_xilinx -part xc7a100tcsg324-1

# 报告资源利用率
report_utilization

# 报告时序
report_timing

puts "============================================================"
puts "综合完成!"
puts "  顶层模块: tmr_voter_6ch_xilinx"
puts "  目标器件: xc7a100tcsg324-1 (Artix-7)"
puts "============================================================"
