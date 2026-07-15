# FPGA Deployment Guide

## Overview
This directory contains all files needed to deploy the vulnerability predictor on FPGA.

## Directory Structure
```
fpga/
├── create_project.tcl    # Vivado HLS project creation script
├── deploy.sh             # Deployment script
├── quantization_config.json  # Quantization configuration
└── src/
    ├── vulnerability_predictor.h  # Header file
    ├── vulnerability_predictor.cpp # Main kernel implementation
    ├── weights.cpp       # Model weights (generated)
    └── test_bench.cpp    # Test bench

## Requirements
- Xilinx Vivado HLS 2020.2 or later
- Python 3.8+ (for weight extraction)
- Target FPGA: xc7z020clg484-1

## Deployment Steps

1. Generate weights:
   python fpga_deploy.py --seed 42

2. Create HLS project:
   vivado_hls -f create_project.tcl

3. Run synthesis:
   vivado_hls -c solution1/syn/report/vulnerability_predictor_csynth.rpt

4. Export IP:
   vivado_hls -f export_ip.tcl

5. Generate bitstream:
   vivado -mode batch -source generate_bitstream.tcl

## Quantization
To enable quantization for better FPGA utilization:
1. Modify quantization_config.json
2. Run: python fpga_deploy.py --quantize

## Performance Notes
- Maximum nodes: 10,000
- Hidden dimension: 128
- Target clock: 100 MHz
- Expected latency: ~1ms for 1000-node graphs

## License
MIT License
