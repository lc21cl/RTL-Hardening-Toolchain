module test_clean_design (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [8-1:0] data_in,
    output reg  [8-1:0] data_out
);

    reg [8-1:0] copy0, copy1, copy2;
    reg [8-1:0] ff_out;

    // Three redundant registers
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            copy0 <= {{(8){{1'b0}}}};
            copy1 <= {{(8){{1'b0}}}};
            copy2 <= {{(8){{1'b0}}}};
        end else begin
            copy0 <= data_in;
            copy1 <= data_in;
            copy2 <= data_in;
        end
    end

    // Majority voter (bit-wise)
    genvar gi;
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : voter
            assign ff_out[gi] = (copy0[gi] & copy1[gi]) |
                                (copy0[gi] & copy2[gi]) |
                                (copy1[gi] & copy2[gi]);
        end
    endgenerate

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            data_out <= {{(8){{1'b0}}}};
        else
            data_out <= ff_out;
    end

endmodule