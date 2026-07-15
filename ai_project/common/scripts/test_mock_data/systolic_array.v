// Systolic array matrix multiplier (2x2, 3x3, 4x4 configurable)
// Each PE (processing element) contains a multiplier and adder
// Generates very large BLIF with regular graph structure

module systolic_array (
    input wire clk,
    input wire rst_n,
    input wire [15:0] a_0, a_1, a_2, a_3,
    input wire [15:0] b_0, b_1, b_2, b_3,
    output reg [31:0] c_0, c_1, c_2, c_3,
    output reg done
);

    parameter N = 4;  // Matrix dimension (2, 3, or 4)

    // Processing Element (PE)
    // Each PE: c += a * b
    wire [31:0] pe_in_a [0:N-1][0:N-1];
    wire [31:0] pe_in_b [0:N-1][0:N-1];
    wire [31:0] pe_out_a [0:N-1][0:N-1];
    wire [31:0] pe_out_b [0:N-1][0:N-1];
    wire [31:0] pe_acc [0:N-1][0:N-1];
    reg [31:0] pe_reg [0:N-1][0:N-1];

    // Generate PE array
    genvar i, j;
    for (i = 0; i < N; i = i + 1) begin : row
        for (j = 0; j < N; j = j + 1) begin : col
            // Input routing
            assign pe_in_a[i][j] = (j == 0) ? 
                (i < N ? {16'b0, (i==0 ? a_0 : (i==1 ? a_1 : (i==2 ? a_2 : a_3)))} : 0) : 
                pe_out_a[i][j-1];
            assign pe_in_b[i][j] = (i == 0) ? 
                (j < N ? {16'b0, (j==0 ? b_0 : (j==1 ? b_1 : (j==2 ? b_2 : b_3)))} : 0) : 
                pe_out_b[i-1][j];

            // PE computation: multiply-accumulate
            wire [31:0] mult = pe_in_a[i][j][15:0] * pe_in_b[i][j][15:0];
            
            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    pe_reg[i][j] <= 0;
                end else begin
                    pe_reg[i][j] <= pe_reg[i][j] + mult;
                end
            end

            assign pe_acc[i][j] = pe_reg[i][j];
            assign pe_out_a[i][j] = pe_in_a[i][j];
            assign pe_out_b[i][j] = pe_in_b[i][j];
        end
    end

    // Output mapping
    reg [3:0] cycle_count;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cycle_count <= 0;
            c_0 <= 0; c_1 <= 0; c_2 <= 0; c_3 <= 0;
            done <= 0;
        end else begin
            if (cycle_count < N) begin
                cycle_count <= cycle_count + 1;
                done <= 0;
            end else begin
                // After N cycles, read out results
                c_0 <= pe_acc[0][0];
                c_1 <= (N > 1) ? pe_acc[1][1] : 0;
                c_2 <= (N > 2) ? pe_acc[2][2] : 0;
                c_3 <= (N > 3) ? pe_acc[3][3] : 0;
                done <= 1;
            end
        end
    end

endmodule
