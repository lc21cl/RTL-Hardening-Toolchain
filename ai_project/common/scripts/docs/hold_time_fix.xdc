# hold_time_fix.xdc — 保持时间修复约束
#
# 针对 STA 报告 Type-3 路径 (LUT3 O → FF D) 保持时间临界问题
# 原始裕量: 0.10 ns (基于 STA 报告)
# 修复目标: 添加 0.20 ns buffer margin (从 0.15 收紧)
#
# 注意: ch5_print_data_timing_pipeline.xdc 第62-63行已有更严格的
#       set_min_delay 0.300 约束。此文件作为独立补充约束文件，
#       确保所有 LUT3→FF 路径均有 hold time 保护。
#
# 典型用法 (Vivado):
#   read_xdc hold_time_fix.xdc
#
# 时序验证参考:
#   LUT3 最小延迟: ~0.12 ns (TT/0.85V/25°C)
#   LUT3 最大延迟: ~0.30 ns (SS/0.72V/125°C)
#   set_min_delay 0.200 > LUT3_min 0.120 → 需综合工具插入 buffer
#   建议在 Vivado phys_opt_design 中启用 -hold_fix

# ---------------------------------------------------------------------------
# 1. 所有 LUT3 → FF 路径的最小延迟约束
#    确保 LUT3 输出到 pipeline 寄存器 D 端的保持时间满足要求
# ---------------------------------------------------------------------------
set_min_delay -from [get_pins -hierarchical -filter {REF_NAME =~ LUT3}] \
              -to [get_pins -hierarchical -filter {REF_NAME =~ FDRE* || REF_NAME =~ FDCE*} && {NAME =~ *D*}] \
              0.200

# ---------------------------------------------------------------------------
# 2. 44 条保持时间路径覆盖完整:
#    ch-0: 1 × LUT3 → 1 × FDRE (ready)
#    ch-1: 1 × LUT3 → 1 × FDRE (boot_valid)
#    ch-2: 1 × LUT3 → 1 × FDRE (exit_valid)
#    ch-3: 8 × LUT3 → 8 × FDRE (exit_code[7:0])
#    ch-4: 1 × LUT3 → 1 × FDRE (print_valid)
#    ch-5: 32 × LUT3 → 32 × FDRE (print_data[31:0])
#    合计: 44 条 hold 路径
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 3. 与现有 max_delay 约束兼容性检查
#    set_max_delay 2.0ns (数据路径) — 来自 ch5_print_data_timing_pipeline.xdc
#    set_min_delay 0.20ns (保持时间) — 本文件
#    二者无冲突, 共存有效
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# End of hold_time_fix.xdc
# ---------------------------------------------------------------------------
