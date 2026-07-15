# run_vivado_hold_fix.tcl — Vivado 保持时间修复综合脚本
# 用法: vivado -mode batch -source run_vivado_hold_fix.tcl
#
# 前提: Vivado 2023+ 已安装并配置环境变量

set TOP_MODULE        "tmr_voter_6ch_pipeline"
set PART              "xc7a100tcsg324-1"
set SRC_DIR           [file normalize [file dirname [info script]]/../test_mock_data]
set CONSTRAINT_DIR    [file dirname [info script]]
set OUTPUT_DIR        "[file dirname [info script]]/vivado_hold_opt"
set REPORT_DIR        "$OUTPUT_DIR/reports"

file mkdir $OUTPUT_DIR $REPORT_DIR

create_project -force hold_fix_opt $OUTPUT_DIR -part $PART

# 添加源文件
read_verilog $SRC_DIR/cpu_core_tmr_xilinx_pipeline.v

# 添加约束
read_xdc $CONSTRAINT_DIR/hold_time_fix.xdc
read_xdc $CONSTRAINT_DIR/ch5_print_data_timing_pipeline.xdc

# ==== 阶段 1: 基础综合 ====
synth_design -top $TOP_MODULE -part $PART -flatten_hierarchy rebuilt
write_checkpoint -force $REPORT_DIR/post_synth.dcp

# 综合后保持时间报告
report_timing -delay_type min -max_paths 50 -file $REPORT_DIR/post_synth_hold.rpt
report_hold_analysis -file $REPORT_DIR/post_synth_hold_analysis.rpt

puts "\n阶段 1 完成: 基础综合后保持时间报告已生成\n"

# ==== 阶段 2: 布局 + 物理优化 (hold_fix) ====
opt_design
place_design
write_checkpoint -force $REPORT_DIR/post_place.dcp

# 布局后保持时间报告 (优化前基线)
report_timing -delay_type min -max_paths 50 -file $REPORT_DIR/post_place_hold_before_opt.rpt
report_hold_analysis -file $REPORT_DIR/post_place_hold_before_opt_detail.rpt

puts "\n阶段 2 完成: 布局后保持时间基线已生成\n"

# ==== 阶段 3: phys_opt_design -hold_fix ====
phys_opt_design -hold_fix
write_checkpoint -force $REPORT_DIR/post_phys_opt.dcp

# phys_opt 后保持时间报告
report_timing -delay_type min -max_paths 50 -file $REPORT_DIR/post_phys_opt_hold.rpt
report_hold_analysis -file $REPORT_DIR/post_phys_opt_hold_detail.rpt

puts "\n阶段 3 完成: phys_opt_design -hold_fix 已执行\n"

# ==== 阶段 4: 布线 ====
route_design
write_checkpoint -force $REPORT_DIR/post_route.dcp

# 最终保持时间报告
report_timing -delay_type min -max_paths 100 -file $REPORT_DIR/post_route_hold_final.rpt
report_hold_analysis -file $REPORT_DIR/post_route_hold_final_detail.rpt

# 建立时间总结
report_timing_summary -file $REPORT_DIR/post_route_timing_summary.rpt
report_utilization -file $REPORT_DIR/post_route_util.rpt
report_qor -file $REPORT_DIR/post_route_qor.rpt

# ==== 优化前后对比总结 ====
puts "\n================================================"
puts "  保持时间优化前后对比"
puts "================================================"
puts "  阶段 2 (优化前) : post_place_hold_before_opt.rpt"
puts "  阶段 3 (优化后) : post_phys_opt_hold.rpt"
puts "  阶段 4 (布线后) : post_route_hold_final.rpt"
puts "================================================"
puts "  预期改善:"
puts "    set_min_delay 0.150 → 0.200 (+0.05ns margin)"
puts "    phys_opt_design -hold_fix → 自动插入 hold buffer"
puts "    最终保持时间裕量: ~0.25-0.30 ns"
puts "================================================"

close_project
