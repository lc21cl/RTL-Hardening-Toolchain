set project_name "sage2_lite_fpga"
set project_dir "./vivado_project"
set part "xc7z020clg484-1"

create_project $project_name $project_dir -part $part -force

set_property board_part em.avnet.com:zed:part0:1.4 [current_project]

read_ip ./hls_project/exported_ip/*.xci

generate_target all [get_files *.xci]

create_bd_design "sage2_lite_design"

create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} [get_bd_cells processing_system7_0]

create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 axi_dma_0
set_property -dict [list CONFIG.c_sg_include_stscntrl_strm {0} CONFIG.c_include_sg {0} CONFIG.c_include_mm2s {1} CONFIG.c_include_s2mm {1} CONFIG.c_mm2s_data_width {128} CONFIG.c_s2mm_data_width {32}] [get_bd_cells axi_dma_0]

create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_interconnect_0
set_property -dict [list CONFIG.NUM_MI {2} CONFIG.NUM_SI {1}] [get_bd_cells axi_interconnect_0]

create_bd_cell -type ip -vlnv trae.ai:dnn:sage2_lite_64:1.0 sage2_lite_64_0

connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins axi_interconnect_0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M00_AXI] [get_bd_intf_pins axi_dma_0/S_AXI_LITE]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M01_AXI] [get_bd_intf_pins sage2_lite_64_0/s_axi_control]

connect_bd_intf_net [get_bd_intf_pins axi_dma_0/M_AXIS_MM2S] [get_bd_intf_pins sage2_lite_64_0/s_axis_features]
connect_bd_intf_net [get_bd_intf_pins sage2_lite_64_0/m_axis_output] [get_bd_intf_pins axi_dma_0/S_AXIS_S2MM]

connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins axi_dma_0/s_axi_lite_aclk]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins axi_interconnect_0/aclk]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins sage2_lite_64_0/ap_clk]

connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins axi_dma_0/s_axi_lite_aresetn]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins axi_interconnect_0/aresetn]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] [get_bd_pins sage2_lite_64_0/ap_rst_n]

assign_bd_address
set_property offset 0x40000000 [get_bd_addr_segs {processing_system7_0/Data/SEG_axi_dma_0_reg}]
set_property offset 0x40010000 [get_bd_addr_segs {processing_system7_0/Data/SEG_sage2_lite_64_0_reg}]

validate_bd_design
save_bd_design

make_wrapper -files [get_files $project_dir/$project_name.srcs/sources_1/bd/sage2_lite_design/sage2_lite_design.bd] -top
add_files -norecurse $project_dir/$project_name.srcs/sources_1/bd/sage2_lite_design/hdl/sage2_lite_design_wrapper.v

update_compile_order -fileset sources_1

puts "Vivado project created successfully!"
