@echo off
REM Batch synthesize Verilog designs to BLIF using OSS CAD Suite
set OSS_DIR=D:\learning\AI_RESEARCH\oss-cad-suite
set SRC_DIR=D:\learning\AI_RESEARCH\ai_project\common\scripts\test_mock_data
set ENV=%OSS_DIR%\environment.bat

call %ENV%

echo === Synthesizing: cnt_comp_down ===
yosys -p "read_verilog -sv cnt_comp_template.v; synth -top cnt_comp_down; write_blif output_cnt_comp_down.blif" 2>&1 | findstr /V "debug|suppressed"

echo === Synthesizing: cnt_comp_mod ===
yosys -p "read_verilog -sv cnt_comp_template.v; synth -top cnt_comp_mod; write_blif output_cnt_comp_mod.blif" 2>&1 | findstr /V "debug|suppressed"

echo === Synthesizing: parity_gen ===
yosys -p "read_verilog -sv parity_template.v; synth -top parity_gen; write_blif output_parity_gen.blif" 2>&1 | findstr /V "debug|suppressed"

echo === Synthesizing: parity_check ===
yosys -p "read_verilog -sv parity_template.v; synth -top parity_check; write_blif output_parity_check.blif" 2>&1 | findstr /V "debug|suppressed"

echo === Synthesizing: parity_register ===
yosys -p "read_verilog -sv parity_template.v; synth -top parity_register; write_blif output_parity_register.blif" 2>&1 | findstr /V "debug|suppressed"

echo === Synthesizing: parity_bus ===
yosys -p "read_verilog -sv parity_template.v; synth -top parity_bus; write_blif output_parity_bus.blif" 2>&1 | findstr /V "debug|suppressed"

echo === Synthesizing: parity_byte ===
yosys -p "read_verilog -sv parity_template.v; synth -top parity_byte; write_blif output_parity_byte.blif" 2>&1 | findstr /V "debug|suppressed"

echo === Synthesizing: mixed_design_ecc ===
yosys -p "read_verilog -sv mixed_design_ecc.v; synth -top mixed_design_ecc; write_blif output_mixed_design_ecc.blif" 2>&1 | findstr /V "debug|suppressed"

echo === Synthesizing: mixed_design (hardened) ===
yosys -p "read_verilog -sv mixed_design_hardened.v; synth -top mixed_design; write_blif output_mixed_design_hardened.blif" 2>&1 | findstr /V "debug|suppressed"

echo === Synthesizing: ecc_bus ===
yosys -p "read_verilog -sv ecc_template.v; synth -top ecc_bus; write_blif output_ecc_bus.blif" 2>&1 | findstr /V "debug|suppressed"

echo === Synthesizing: dice_register ===
yosys -p "read_verilog -sv dice_template.v; synth -top dice_register; write_blif output_dice_register.blif" 2>&1 | findstr /V "debug|suppressed"

echo === Synthesizing: dice_tmr_register ===
yosys -p "read_verilog -sv dice_template.v; synth -top dice_tmr_register; write_blif output_dice_tmr_register.blif" 2>&1 | findstr /V "debug|suppressed"

echo === DONE ===
dir /b output_*.blif
