# synth_to_aig.tcl — yosys AIG 综合脚本 (TCL mode)
# 用途: 将 Verilog RTL 综合为 AIG (And-Inverter Graph) 格式
# 用法: yosys -c synth_to_aig.tcl
#
# 输入文件列表通过 verilog_files.txt 指定
# (每行一个文件路径)
#
# 在 TCL 模式下, yosys 命令使用 "yy" 前缀

# 读取文件列表
set file_list "verilog_files.txt"
if {[file exists $file_list]} {
    set fp [open $file_list r]
    set file_data [read $fp]
    close $fp
    foreach line [split $file_data "\n"] {
        set line [string trim $line]
        if {$line ne "" && [string index $line 0] ne "#"} {
            puts "Reading: $line"
            yy read_verilog -sv $line
        }
    }
} else {
    puts "Error: $file_list not found!"
    puts "Usage: echo <verilog_file> > verilog_files.txt; yosys -c synth_to_aig.tcl"
    exit 1
}

# 层次化展平
yy hierarchy -check -auto-top

# 进程/行为级展开
yy proc; yy opt

# 内存展开
yy memory; yy opt

# 展平设计 (去除层次)
yy flatten; yy opt

# 技术映射 - 与/或/非原语
yy techmap; yy opt

# 将 DFF 转换为 AIG 可处理的格式
yy dfflegalize -cell $_DFFE_PN0P_ $_DFF_N_ -cell $_DFFE_PP0P_ $_DFF_P_
yy opt_clean

# 将未连接信号设为不定态
yy setundef -undriven -zero

# ABC 综合为 AIG (仅 AND + INV)
yy abc -g AND

# 清理
yy clean

# 统计信息
yy stat

# 写入 AIGER 格式
yy write_aiger -map output_map.txt output.aig

# 写入 Verilog 网表 (调试用)
yy write_verilog output_netlist.v

puts "=== AIG 综合完成 ==="
puts "输出文件:"
puts "  - output.aig (AIGER 二进制格式)"
puts "  - output_map.txt (端口映射表)"
puts "  - output_netlist.v (Verilog 网表)"
