
module test_design(
    input clk,
    input rst_n,
    input [7:0] data_in,
    input [7:0] extra_data,
    output [7:0] data_out,
    output [7:0] extra_out,
    output reg [3:0] count
);

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        count <= 4'b0;
    end else begin
        count <= count + 1'b1;
    end
end

assign data_out = data_in;
assign extra_out = extra_data;

endmodule
