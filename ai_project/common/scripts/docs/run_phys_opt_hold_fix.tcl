# run_phys_opt_hold_fix.tcl — 物理优化保持时间修复脚本
#
# 用法:
#   vivado -mode batch -source run_phys_opt_hold_fix.tcl
#   vivado -mode tcl -source run_phys_opt_hold_fix.tcl
#
# 功能:
#   1. 读入综合后 checkpoint (DCP)
#   2. 布局 (place_design)
#   3. 物理优化保持时间 (phys_opt_design -hold_fix)
#   4. 布线 (route_design)
#   5. 生成保持时间优化前后对比报告
#
# 环境要求: Vivado 2023+
# 目标器件: xc7a100tcsg324-1 (Artix-7)

set PART              "xc7a100tcsg324-1"
set SCRIPT_DIR        [file dirname [info script]]
set WORK_DIR          "$SCRIPT_DIR/vivado_hold_opt"
set DCP_IN            "$WORK_DIR/reports/post_synth.dcp"
set REPORT_DIR        "$WORK_DIR/reports"

# 检查综合后 DCP 是否存在
if {![file exists $DCP_IN]} {
    puts "错误: 未找到综合后 DCP 文件 $DCP_IN"
    puts "请先运行 run_vivado_hold_fix.tcl 完成综合阶段"
    exit 1
}

file mkdir $REPORT_DIR

# 打开综合后 checkpoint
open_checkpoint $DCP_IN

# ======== 阶段 1: 布局 ========
puts "\n[阶段 1/4] 布局 (place_design)..."
place_design
write_checkpoint -force $REPORT_DIR/post_place.dcp

# 优化前保持时间基线
puts "  生成优化前保持时间报告..."
report_timing -delay_type min -max_paths 100 -file $REPORT_DIR/hold_before_opt.rpt
report_hold_analysis -file $REPORT_DIR/hold_before_opt_detail.rpt

# 提取优化前最差 slack
set before_worst_slack [get_property SLACK [lindex [get_timing_paths -delay_type min -max_paths 1] 0]]
puts "  优化前最差保持时间 slack: $before_worst_slack ns"

# ======== 阶段 2: 物理优化保持时间 ========
puts "\n[阶段 2/4] 物理优化保持时间 (phys_opt_design -hold_fix)..."
phys_opt_design -hold_fix
write_checkpoint -force $REPORT_DIR/post_phys_opt.dcp

# 优化后保持时间报告
puts "  生成优化后保持时间报告..."
report_timing -delay_type min -max_paths 100 -file $REPORT_DIR/hold_after_phys_opt.rpt
report_hold_analysis -file $REPORT_DIR/hold_after_phys_opt_detail.rpt

set after_worst_slack [get_property SLACK [lindex [get_timing_paths -delay_type min -max_paths 1] 0]]
puts "  优化后最差保持时间 slack: $after_worst_slack ns"

# ======== 阶段 3: 布线 ========
puts "\n[阶段 3/4] 布线 (route_design)..."
route_design
write_checkpoint -force $REPORT_DIR/post_route.dcp

# 布线后最终报告
report_timing -delay_type min -max_paths 100 -file $REPORT_DIR/hold_route_final.rpt
report_timing_summary -file $REPORT_DIR/timing_summary.rpt
report_utilization -file $REPORT_DIR/utilization.rpt

set route_worst_slack [get_property SLACK [lindex [get_timing_paths -delay_type min -max_paths 1] 0]]
puts "  布线后最差保持时间 slack: $route_worst_slack ns"

# ======== 阶段 4: 对比报告 ========
puts "\n================================================"
puts "  保持时间优化前后对比报告"
puts "================================================"
puts "  指标               | 优化前     | phys_opt后  | 布线后"
puts "  ------------------|-----------|------------|--------"
puts "  最差 slack (ns)   | [format %8.4f $before_worst_slack] | [format %10.4f $after_worst_slack] | [format %7.4f $route_worst_slack]"

set improvement [expr {$after_worst_slack - $before_worst_slack}]
puts "  优化改善 (ns)      | +[format %.4f $improvement]"
puts "================================================"
puts "  输出文件:"
puts "    hold_before_opt.rpt    — 优化前保持时间"
puts "    hold_after_phys_opt.rpt — 优化后保持时间"
puts "    hold_route_final.rpt   — 布线后最终保持时间"
puts "================================================"

close_project
