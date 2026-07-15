//------------------------------------------------------------------------------
// cpu_core_tmr_core_stub.sv — Minimal stub for cpu_core_tmr_core
//
// cpu_core_tmr_uvm.sv 使用独立信号端口实例化 cpu_core_tmr_core,
// 而非 cpu_core_tmr.sv 中的 interface 端口。本文件提供一个最小桩模块。
//------------------------------------------------------------------------------

module cpu_core_tmr_core (
    input  logic        clk,
    input  logic        start,
    input  logic        rom_init_write_enable,
    input  logic [31:0] rom_init_write_addr,
    input  logic [31:0] rom_init_write_data,
    input  logic        mmio_in_valid,
    input  logic [7:0]  mmio_in_data,
    output logic        mmio_in_ready,
    output logic        mmio_out_boot_valid,
    output logic        mmio_out_exit_valid,
    output logic [7:0]  mmio_out_exit_code,
    output logic        mmio_out_print_valid,
    output logic [31:0] mmio_out_print_data
);

    // Stub: 所有输出默认 0
    always_ff @(posedge clk or negedge start) begin
        if (!start) begin
            mmio_in_ready        <= 0;
            mmio_out_boot_valid  <= 0;
            mmio_out_exit_valid  <= 0;
            mmio_out_exit_code   <= 8'h00;
            mmio_out_print_valid <= 0;
            mmio_out_print_data  <= 32'h00000000;
        end else begin
            mmio_in_ready        <= 1;  // 默认 ready
            mmio_out_boot_valid  <= 0;
            mmio_out_exit_valid  <= 0;
            mmio_out_exit_code   <= 8'h00;
            mmio_out_print_valid <= 0;
            mmio_out_print_data  <= 32'h00000000;
        end
    end

endmodule : cpu_core_tmr_core
