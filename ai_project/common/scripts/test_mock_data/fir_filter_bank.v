// Parameterized multi-channel FIR filter bank
// Generates a large circuit with complex fan-in/fan-out patterns

module fir_filter_bank (
    input wire clk,
    input wire rst_n,
    input wire [15:0] data_in,
    output reg [15:0] data_out_0,
    output reg [15:0] data_out_1,
    output reg [15:0] data_out_2,
    output reg valid_out
);

    parameter TAPS = 8;        // Number of filter taps
    parameter CHANNELS = 4;    // Number of parallel channels
    parameter W = 16;          // Data width

    // Coefficient ROM (fixed coefficients for each channel)
    // Each channel has different coefficient patterns
    reg [W-1:0] coeff [0:CHANNELS-1][0:TAPS-1];
    integer ci, cj;
    initial begin
        for (ci = 0; ci < CHANNELS; ci = ci + 1)
            for (cj = 0; cj < TAPS; cj = cj + 1)
                coeff[ci][cj] = (ci * TAPS + cj) * 257 + 12345;
    end

    // Delay line (shift register)
    reg [W-1:0] delay_line [0:TAPS-1];
    integer dly;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (dly = 0; dly < TAPS; dly = dly + 1)
                delay_line[dly] <= 0;
        end else begin
            delay_line[0] <= data_in;
            for (dly = 1; dly < TAPS; dly = dly + 1)
                delay_line[dly] <= delay_line[dly-1];
        end
    end

    // ── Channel 0: Low-pass (all positive coefficients) ──
    reg [W*2-1:0] accum_0;
    wire [W-1:0] ch0_tap [0:TAPS-1];

    generate
        genvar t, ch;
        for (t = 0; t < TAPS; t = t + 1) begin
            assign ch0_tap[t] = delay_line[t] * coeff[0][t];
        end
    endgenerate

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            accum_0 <= 0;
        end else begin
            accum_0 <= ch0_tap[0];
            for (dly = 1; dly < TAPS; dly = dly + 1)
                accum_0 <= accum_0 + ch0_tap[dly];
        end
    end

    // ── Channel 1: High-pass (alternating signs) ──
    reg signed [W*2-1:0] accum_1;
    wire signed [W*2-1:0] ch1_tap [0:TAPS-1];

    for (t = 0; t < TAPS; t = t + 1) begin
        assign ch1_tap[t] = ((t % 2) ? -1 : 1) * delay_line[t] * coeff[1][t];
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            accum_1 <= 0;
        end else begin
            accum_1 <= ch1_tap[0];
            for (dly = 1; dly < TAPS; dly = dly + 1)
                accum_1 <= accum_1 + ch1_tap[dly];
        end
    end

    // ── Channel 2: Band-pass ──
    reg signed [W*2-1:0] accum_2;
    wire signed [W*2-1:0] ch2_tap [0:TAPS-1];

    for (t = 0; t < TAPS; t = t + 1) begin
        assign ch2_tap[t] = ((t > 1 && t < 6) ? 1 : 0) * delay_line[t] * coeff[2][t];
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            accum_2 <= 0;
        end else begin
            accum_2 <= ch2_tap[0];
            for (dly = 1; dly < TAPS; dly = dly + 1)
                accum_2 <= accum_2 + ch2_tap[dly];
        end
    end

    // ── Output ──
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out_0 <= 0;
            data_out_1 <= 0;
            data_out_2 <= 0;
            valid_out <= 0;
        end else begin
            data_out_0 <= accum_0[W-1:0];
            data_out_1 <= accum_1[W-1:0];
            data_out_2 <= accum_2[W-1:0];
            valid_out <= 1'b1;
        end
    end

endmodule
