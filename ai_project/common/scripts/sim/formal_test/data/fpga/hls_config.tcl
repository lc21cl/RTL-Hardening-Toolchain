set project_name "sage2_lite_64"
set project_dir "./hls_project"
set part "xc7z020clg484-1"
set clock_period 10

create_project $project_name $project_dir -part $part -force

add_files {
    sage2_lite_inference.cpp
    sage2_lite_model.h
}

add_files -tb {
    sage2_lite_test.cpp
}

set_top sage2_lite_inference

config_compile -enable_auto_rewind=false

config_interface -m_axi_addr64 0
config_interface -m_axi_offset off
config_interface -register_io off

config_resource -core Mul_LUT
config_resource -core Mul_Usage No_LUT_Mul

set_directive_resource -core Mul_LUT "sage2_lite_inference"
set_directive_resource -core AddSub_LUT "sage2_lite_inference"

set_directive_pipeline -II 1 "sage2_lite_inference/matmul_int8"
set_directive_unroll -factor 8 "sage2_lite_inference/matmul_int8"

set_directive_inline "sage2_lite_inference/relu"
set_directive_inline "sage2_lite_inference/sigmoid"
set_directive_inline "sage2_lite_inference/dequantize"

set_directive_interface -mode ap_stream -depth 1024 "sage2_lite_inference/features"
set_directive_interface -mode ap_stream -depth 1024 "sage2_lite_inference/edge_index"
set_directive_interface -mode ap_stream -depth 1024 "sage2_lite_inference/output"

set_directive_interface -mode ap_lite "sage2_lite_inference/num_nodes"
set_directive_interface -mode ap_lite "sage2_lite_inference/num_edges"
set_directive_interface -mode ap_lite "sage2_lite_inference/start"
set_directive_interface -mode ap_lite "sage2_lite_inference/done"

csynth_design

export_design -format ip_catalog -rtl verilog -vendor "trae.ai" -library "dnn" -version "1.0" -ipname "sage2_lite_64"

close_project

puts "HLS synthesis completed successfully!"
