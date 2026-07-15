###############################################################################
# ch5_print_data_timing.xdc
# Xilinx XDC Timing Constraints for ch-5 print_data Channel
#
# Target FPGA : Xilinx 7-series (Artix-7 / Kintex-7)
# Tool       : Vivado 2023+
# Clock      : 10 MHz (100 ns period)
# Clock Domain: Single clock domain (clk)
#
# Based on VCD timing analysis:
#   - Worst-case delay path : ch-5 print_data (32-bit)
#   - Measured delay        : ~51 ns (core output to voted output)
#   - Timing margin         : ~49 ns (49%)
#   - Clock jitter          : 0 ps (RTL ideal)
###############################################################################

# ---------------------------------------------------------------------------
# 1. Primary Clock Constraints
# ---------------------------------------------------------------------------
create_clock -period 100.000 -name clk [get_ports clk]

# Clock uncertainty (setup: 0.5 ns, hold: 0.3 ns)
set_clock_uncertainty -setup 0.500 [get_clocks clk]
set_clock_uncertainty -hold  0.300 [get_clocks clk]

# ---------------------------------------------------------------------------
# 2. Input Delay Constraints
#    print_data from core registers -> voter inputs
#    Core register clock-to-Q ~0.5 ns, routing ~2 ns
# ---------------------------------------------------------------------------
set_input_delay -clock [get_clocks clk] -max 3.000 \
    [get_ports {core1_print_data[*] core2_print_data[*] core3_print_data[*]}]

set_input_delay -clock [get_clocks clk] -min 0.500 \
    [get_ports {core1_print_data[*] core2_print_data[*] core3_print_data[*]}]

# ---------------------------------------------------------------------------
# 3. Output Delay Constraints
#    voted_print_data -> downstream registers (mmio_out)
# ---------------------------------------------------------------------------
set_output_delay -clock [get_clocks clk] -max 5.000 \
    [get_ports {mmio_out_print_data[*]}]

set_output_delay -clock [get_clocks clk] -min 1.000 \
    [get_ports {mmio_out_print_data[*]}]

# ---------------------------------------------------------------------------
# 4. Max Delay Constraint
#    Ensures 32-bit print_data combinational delay from core outputs to
#    voted output meets requirement. Based on VCD analysis:
#       Measured delay: ~51 ns, Margin: ~49 ns
#    Setting to 30 ns for aggressive timing closure.
# ---------------------------------------------------------------------------
set_max_delay -from [get_ports {core1_print_data[*] core2_print_data[*] core3_print_data[*]}] \
              -to   [get_ports {mmio_out_print_data[*]}] 30.000

# ---------------------------------------------------------------------------
# 5. Multicycle Path (Optional)
#    Uncomment if downstream registers sample multiple cycles later.
#    Not required for current 10 MHz design with 49% margin.
# ---------------------------------------------------------------------------
# set_multicycle_path -setup 2 \
#     -from [get_ports {core1_print_data[*] core2_print_data[*] core3_print_data[*]}] \
#     -to   [get_ports {mmio_out_print_data[*]}]

# ---------------------------------------------------------------------------
# 6. False Path (Optional)
#    For non-critical control signals to avoid unnecessary timing optimization.
#    Do NOT enable for print_data — it is a critical data path.
# ---------------------------------------------------------------------------
# set_false_path -from [get_ports {core1_print_data[*] core3_print_data[*]}]

# ---------------------------------------------------------------------------
# 7. Path Grouping
#    Groups all print_data paths for focused timing reports.
# ---------------------------------------------------------------------------
group_path -name print_data_path \
    -from [get_ports {core1_print_data[*] core2_print_data[*] core3_print_data[*]}]

###############################################################################
# End of ch5_print_data_timing.xdc
###############################################################################
