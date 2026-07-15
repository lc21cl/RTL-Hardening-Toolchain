#!/bin/bash

echo "=== FPGA Deployment Script ==="

PROJECT_DIR="D:\learning\AI_RESEARCH\ai_project\common\scripts\sim\formal_test\data\fpga"
HLS_DIR="$PROJECT_DIR/hls_project"
SRC_DIR="$PROJECT_DIR/src"

echo "1. Creating HLS project..."
vivado_hls -f "$PROJECT_DIR/create_project.tcl"

echo "2. Synthesizing design..."
cd "$HLS_DIR"
vivado_hls -c -f solution1/syn/report/vulnerability_predictor_csynth.rpt

echo "3. Exporting IP..."
vivado_hls -f "$PROJECT_DIR/export_ip.tcl"

echo "4. Generating bitstream..."
vivado -mode batch -source "$PROJECT_DIR/generate_bitstream.tcl"

echo "=== Deployment Complete ==="
