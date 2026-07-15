# ============================================================
# package_ip.tcl — Vivado IP 打包脚本
#
# 将 tmr_voter_6ch_xilinx RTL 打包为 Vivado 可识别 IP 核。
#
# 用法:
#   cd scripts/
#   vivado -source package_ip.tcl -mode batch
# ============================================================

# 创建临时工程
create_project -force ip_pack ./ip_pack -part xc7a100tcsg324-1

# 设置 IP 仓库路径
set_property ip_repo_paths [list .] [current_project]

# 读取 RTL 源码
read_verilog ../src/tmr_voter_6ch_xilinx.v

# 更新 IP 目录
update_ip_catalog -name tmr_voter_6ch -version 1.0 -vendor user.org

# 打包 IP 到目标目录
ipx::package_project -root_dir ../ip -vendor user.org -library tmr -name tmr_voter_6ch

puts "IP 核打包完成: ip/tmr_voter_6ch/"

# 关闭工程
close_project

# 清理临时文件
file delete -force ./ip_pack
