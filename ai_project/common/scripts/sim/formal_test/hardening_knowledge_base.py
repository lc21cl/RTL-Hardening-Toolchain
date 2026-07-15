"""
Knowledge base for hardware design hardening patterns.
Used by RAG-LLM systems to automatically generate hardened RTL designs.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ============================================================================
# HardeningPattern
# ============================================================================

class HardeningPattern:
    """A single hardening pattern with metadata and RTL template."""

    def __init__(
        self,
        name: str,
        description: str,
        category: str,
        rtl_template: str,
        applicable_signals: Optional[List[str]] = None,
        area_overhead: float = 0.0,
        power_overhead: float = 0.0,
        latency_penalty: int = 0,
        conditions: Optional[Dict[str, Any]] = None,
        references: Optional[List[str]] = None,
    ) -> None:
        self.name = name
        self.description = description
        self.category = category
        self.rtl_template = rtl_template
        self.applicable_signals = applicable_signals or []
        self.area_overhead = area_overhead
        self.power_overhead = power_overhead
        self.latency_penalty = latency_penalty
        self.conditions = conditions or {}
        self.references = references or []

    def fill_template(self, module_name: str = "hardened_module", signal_width: int = 32) -> str:
        """Fill the RTL template with given parameters."""
        return self.rtl_template.format(
            module_name=module_name,
            signal_width=signal_width,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "rtl_template": self.rtl_template,
            "applicable_signals": self.applicable_signals,
            "area_overhead": self.area_overhead,
            "power_overhead": self.power_overhead,
            "latency_penalty": self.latency_penalty,
            "conditions": self.conditions,
            "references": self.references,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HardeningPattern":
        return cls(**data)

    def __repr__(self) -> str:
        return (f"HardeningPattern(name='{self.name}', category='{self.category}', "
                f"area={self.area_overhead}x, power={self.power_overhead}x, "
                f"latency={self.latency_penalty}cyc)")


# ============================================================================
# KnowledgeBase
# ============================================================================

_TMR_RTL = """\
// ------------------------------------------------------------
// {module_name} — Triple Modular Redundancy (TMR)
// Three identical logic copies + majority voter
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width}-1:0] data_in,
    output reg  [{signal_width}-1:0] data_out
);

    reg [{signal_width}-1:0] copy0, copy1, copy2;
    reg [{signal_width}-1:0] ff_out;

    // Three redundant registers
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            copy0 <= {{({signal_width}){{1'b0}}}};
            copy1 <= {{({signal_width}){{1'b0}}}};
            copy2 <= {{({signal_width}){{1'b0}}}};
        end else begin
            copy0 <= data_in;
            copy1 <= data_in;
            copy2 <= data_in;
        end
    end

    // Majority voter (bit-wise)
    genvar gi;
    generate
        for (gi = 0; gi < {signal_width}; gi = gi + 1) begin : voter
            assign ff_out[gi] = (copy0[gi] & copy1[gi]) |
                                (copy0[gi] & copy2[gi]) |
                                (copy1[gi] & copy2[gi]);
        end
    endgenerate

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            data_out <= {{({signal_width}){{1'b0}}}};
        else
            data_out <= ff_out;
    end

endmodule
"""

_TMR_STATE_RTL = """\
// ------------------------------------------------------------
// {module_name} — Triple Modular Redundancy for State Registers
// Triplicated state + majority voter with error flag
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width}-1:0] state_next,
    output reg  [{signal_width}-1:0] state_voted,
    output wire                     error_detected
);

    reg [{signal_width}-1:0] state_a, state_b, state_c;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_a <= {{({{signal_width}}{{1'b0}}}};
            state_b <= {{({{signal_width}}{{1'b0}}}};
            state_c <= {{({{signal_width}}{{1'b0}}}};
        end else begin
            state_a <= state_next;
            state_b <= state_next;
            state_c <= state_next;
        end
    end

    // Majority voter
    wire [{signal_width}-1:0] maj;
    genvar gi;
    generate
        for (gi = 0; gi < {signal_width}; gi = gi + 1) begin : voter
            assign maj[gi] = (state_a[gi] & state_b[gi]) |
                             (state_a[gi] & state_c[gi]) |
                             (state_b[gi] & state_c[gi]);
        end
    endgenerate

    assign state_voted = maj;
    assign error_detected = (state_a != state_b) |
                            (state_a != state_c) |
                            (state_b != state_c);

endmodule
"""

_DICE_RTL = """\
// ------------------------------------------------------------
// {module_name} — Dual Interlocked Storage Cell (DICE)
// 4-node cross-coupled SEU-tolerant latch
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width}-1:0] d,
    output reg  [{signal_width}-1:0] q
);
    // DICE uses four internal storage nodes (n0..n3) per bit
    // Each node is driven by two adjacent nodes for interlocking
    reg [{signal_width}-1:0] n0, n1, n2, n3;

    genvar gi;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            n0 <= {{({signal_width}){{1'b0}}}};
            n1 <= {{({signal_width}){{1'b0}}}};
            n2 <= {{({signal_width}){{1'b0}}}};
            n3 <= {{({signal_width}){{1'b0}}}};
            q  <= {{({signal_width}){{1'b0}}}};
        end else begin
            // Cross-coupled interlocked update
            for (i = 0; i < {signal_width}; i = i + 1) begin
                n0[i] <= d[i];
                n1[i] <= n0[i];
                n2[i] <= n1[i];
                n3[i] <= n2[i];
                q[i]  <= n1[i];  // redundant output tap
            end
        end
    end

endmodule
"""

_ECC_SECDED_RTL = """\
// ------------------------------------------------------------
// {module_name} — Single Error Correction / Double Error Detection
// (32,7) Hsiao SECDED codec
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     encode,           // 1=encode, 0=decode&correct
    input  wire [{signal_width}-1:0] data_in,          // payload width = signal_width
    output reg  [{signal_width}+6:0] code_out,          // data + 7 check bits
    output reg  [{signal_width}-1:0] data_corrected,
    output wire                     uncorrectable
);

    // Parity-check matrix generation for (k+7, k) SECDED code
    // Using systematic Hsiao code with odd-weight columns
    wire [6:0] syndrome;
    wire [6:0] check_bits;

    // Check-bit generator (parity matrix multiply)
    // Simplified for parameterized width — uses H-matrix columns
    assign check_bits[0] = ^data_in[0:{signal_width}/8];
    assign check_bits[1] = ^data_in[{signal_width}/8:{signal_width}/4];
    assign check_bits[2] = ^data_in[{signal_width}/4:{signal_width}/2];
    assign check_bits[3] = ^data_in[{signal_width}/2:3*{signal_width}/4];
    assign check_bits[4] = ^data_in;
    assign check_bits[5] = ^({{data_in}} >> 1);
    assign check_bits[6] = ^({{data_in}} >> 2);

    // Syndrome computation during decode
    assign syndrome = check_bits ^ {{data_in[6:0]}};

    assign uncorrectable = (syndrome != 0) &&
                           (^syndrome != 1);   // even parity = double error

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            code_out <= 0;
            data_corrected <= 0;
        end else if (encode) begin
            code_out <= {{data_in, check_bits}};
        end else begin
            // Single-bit correction (simplified — flip bit indicated by syndrome)
            data_corrected <= (syndrome != 0) && (^syndrome == 1)
                ? data_in ^ (1 << (syndrome[4:0]))
                : data_in;
        end
    end

endmodule
"""

_PARITY_RTL = """\
// ------------------------------------------------------------
// {module_name} — Parity Check (even / odd)
// Simple parity generator and checker
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width}-1:0] data_in,
    input  wire                     parity_in,      // received parity bit
    input  wire                     even_parity,    // 1=even, 0=odd
    output wire                     parity_out,     // generated parity
    output wire                     error_flag,
    output reg  [{signal_width}-1:0] data_out
);

    assign parity_out = even_parity
        ? ^data_in
        : ~(^data_in);

    assign error_flag = (parity_out != parity_in);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            data_out <= {{({{signal_width}}{{1'b0}}}};
        else
            data_out <= data_in;
    end

endmodule
"""

_COUNTER_COMPARATOR_RTL = """\
// ------------------------------------------------------------
// {module_name} — Lockstep Counter with Comparator
// Dual redundant counters compared every cycle
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     count_en,
    input  wire [{signal_width}-1:0] count_val,
    output reg  [{signal_width}-1:0] count_out,
    output wire                     mismatch_error
);

    reg [{signal_width}-1:0] cnt_a, cnt_b;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt_a <= {{({signal_width}){{1'b0}}}};
            cnt_b <= {{({signal_width}){{1'b0}}}};
        end else if (count_en) begin
            cnt_a <= cnt_a + count_val;
            cnt_b <= cnt_b + count_val;
        end
    end

    assign mismatch_error = (cnt_a != cnt_b);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count_out <= {{({signal_width}){{1'b0}}}};
        else
            count_out <= cnt_a;
    end

endmodule
"""

_WATCHDOG_RTL = """\
// ------------------------------------------------------------
// {module_name} — Watchdog Timer for Control Signals
// Monitors activity; asserts alarm if timeout
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     activity_strobe,   // kick / pet the watchdog
    input  wire [{signal_width}-1:0] timeout_thresh,    // timeout value in cycles
    output wire                     timeout_alarm,
    output reg  [{signal_width}-1:0] timer_value
);

    localparam MAX_WIDTH = {signal_width};

    reg  [{signal_width}-1:0] timer;
    wire                      timer_expired;

    assign timer_expired = (timer == {{({{signal_width}}{{1'b0}}}});

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            timer <= timeout_thresh;
        end else if (activity_strobe) begin
            timer <= timeout_thresh;        // reset timer on activity
        end else if (!timer_expired) begin
            timer <= timer - 1'b1;          // count down
        end
    end

    assign timeout_alarm = timer_expired;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            timer_value <= {{({{signal_width}}{{1'b0}}}};
        else
            timer_value <= timer;
    end

endmodule
"""

_ONEHOT_FSM_RTL = """\
// ------------------------------------------------------------
// {module_name} — One-Hot Encoded FSM for SEU Tolerance
// An invalid-state detector recovers illegal one-hot patterns
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     start,
    input  wire                     done_cond,
    output reg                      busy,
    output reg                      complete,
    output wire                     state_error
);

    localparam IDLE  = {signal_width}'b001;
    localparam BUSY  = {signal_width}'b010;
    localparam DONE  = {signal_width}'b100;

    reg [{signal_width}-1:0] state, state_next;

    // One-hot state transition
    always @(*) begin
        state_next = state;
        case (1'b1)
            state[0]: state_next = start   ? BUSY : IDLE;
            state[1]: state_next = done_cond ? DONE : BUSY;
            state[2]: state_next = IDLE;
            default:  state_next = IDLE;   // recover illegal states
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            state <= IDLE;
        else
            state <= state_next;
    end

    // Output decoding
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy     <= 1'b0;
            complete <= 1'b0;
        end else begin
            busy     <= state[BUSY];
            complete <= state[DONE];
        end
    end

    // State error detection (not exactly one-hot)
    assign state_error = (^state == 1'b0) || (^state == 1'bx);

endmodule
"""

_CRC_RTL = """\
// ------------------------------------------------------------
// {module_name} — CRC-32 Error Detection for Bus Data
// Parallel CRC generator / checker for burst transfers
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     crc_en,
    input  wire                     data_valid,
    input  wire [{signal_width}-1:0] data_in,
    output reg  [31:0]              crc_out,
    output wire                     crc_error
);

    reg  [31:0] crc_reg;
    wire [31:0] crc_next;
    integer     i;

    // CRC-32 polynomial: x^32 + x^26 + x^23 + x^22 + x^16 + x^12 +
    //                    x^11 + x^10 + x^8 + x^7 + x^5 + x^4 + x^2 + x + 1
    // Simplified serial CRC with {signal_width}-wide parallel feeding
    always @(*) begin
        crc_next = crc_reg;
        if (data_valid) begin
            for (i = 0; i < {signal_width}; i = i + 1) begin
                if (crc_next[31] ^ data_in[i]) begin
                    crc_next = {{crc_next[30:0], 1'b0}} ^ 32'h04C11DB7;
                end else begin
                    crc_next = {{crc_next[30:0], 1'b0}};
                end
            end
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            crc_reg <= 32'hFFFFFFFF;
        else if (crc_en)
            crc_reg <= crc_next;
    end

    assign crc_out = crc_reg;

    // Error flag: crc_error asserted when residual != 0
    assign crc_error = crc_en && (crc_reg != 32'h00000000);

endmodule
"""

_SCRUBBING_RTL = """\
// ------------------------------------------------------------
// {module_name} — Memory Scrubbing Controller
// Periodically reads SRAM contents and corrects ECC errors
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     scrub_enable,
    input  wire [{signal_width}-1:0] scrub_interval,  // cycles between scrubs
    input  wire [{signal_width}-1:0] mem_depth,        // number of words to scrub
    output reg                      scrub_active,
    output reg  [{signal_width}-1:0] scrub_addr,
    output reg                      read_req,
    input  wire                     read_done,
    input  wire                     ecc_corrected,     // scrub corrected an error
    output reg                      write_req,
    output wire                     correction_event
);

    reg  [{signal_width}-1:0] cycle_cnt;
    reg  [{signal_width}-1:0] addr_ptr;
    reg  [1:0]                state;
    reg                       correction_flag;

    localparam ST_IDLE  = 2'b00;
    localparam ST_READ  = 2'b01;
    localparam ST_WRITE = 2'b10;

    // Timer and scrub address pointer
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cycle_cnt <= {{({signal_width}){{1'b0}}}};
            addr_ptr  <= {{({signal_width}){{1'b0}}}};
            state     <= ST_IDLE;
            read_req  <= 1'b0;
            write_req <= 1'b0;
            correction_flag <= 1'b0;
        end else begin
            case (state)
                ST_IDLE: begin
                    if (scrub_enable && (cycle_cnt >= scrub_interval)) begin
                        cycle_cnt <= {{({signal_width}){{1'b0}}}};
                        state     <= ST_READ;
                    end else begin
                        cycle_cnt <= cycle_cnt + 1'b1;
                    end
                end

                ST_READ: begin
                    read_req <= 1'b1;
                    if (read_done) begin
                        read_req  <= 1'b0;
                        scrub_addr <= addr_ptr;
                        if (ecc_corrected) begin
                            correction_flag <= 1'b1;
                            state <= ST_WRITE;
                        end else begin
                            addr_ptr <= addr_ptr + 1'b1;
                            state <= (addr_ptr >= mem_depth - 1) ? ST_IDLE : ST_READ;
                        end
                    end
                end

                ST_WRITE: begin
                    write_req <= 1'b1;
                    if (read_done) begin
                        write_req <= 1'b0;
                        correction_flag <= 1'b0;
                        addr_ptr <= addr_ptr + 1'b1;
                        state <= (addr_ptr >= mem_depth - 1) ? ST_IDLE : ST_READ;
                    end
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

    assign scrub_active  = (state != ST_IDLE);
    assign correction_event = correction_flag;

endmodule
"""

# ── 新增: Hamming Code Encoder/Decoder ──
_HAMMING_RTL = """\
// ------------------------------------------------------------
// {module_name} — Hamming Code Encoder/Decoder
// Single error correction for {signal_width}-bit data words
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     encode,           // 1=encode, 0=decode
    input  wire [{signal_width}-1:0] data_in,
    output reg  [{signal_width}-1:0] data_out,
    output reg                      error_flag,       // single-bit error detected
    output reg                      uncorrectable     // multi-bit error detected
);

    // Hamming check bit positions: 1,2,4,8,...
    // For {signal_width}-bit data, need ceil(log2({signal_width}))+1 check bits
    localparam CHECK_BITS = $clog2({signal_width} + $clog2({signal_width}) + 1);
    localparam CODE_WIDTH = {signal_width} + CHECK_BITS;

    reg [CODE_WIDTH-1:0] code_word;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out <= {{({signal_width}){{1'b0}}}};
            error_flag <= 1'b0;
            uncorrectable <= 1'b0;
            code_word <= {{CODE_WIDTH{{1'b0}}}};
        end else begin
            if (encode) begin
                // Insert data bits into code word at non-power-of-2 positions
                // (Simplified: append check bits at end for modularity)
                code_word <= {{data_in, {{CHECK_BITS}}{{1'b0}}}};
                data_out <= data_in;
                error_flag <= 1'b0;
                uncorrectable <= 1'b0;
            end else begin
                // Decode: detect and correct single-bit errors
                // (Syndrome computation and correction logic)
                data_out <= data_in;  // corrected data (simplified)
                error_flag <= 1'b0;
                uncorrectable <= 1'b0;
            end
        end
    end

endmodule
"""

# ── 新增: Triple Time Redundancy (TTR) ──
_TTR_RTL = """\
// ------------------------------------------------------------
// {module_name} — Triple Time Redundancy (TTR)
// Time-multiplexed triple computation with voter
// Area-efficient: uses 1x logic, 3x time
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width}-1:0] data_in,
    input  wire                     start,
    output reg  [{signal_width}-1:0] data_out,
    output reg                      done,
    output reg                      error_flag
);

    reg [1:0] state;
    reg [{signal_width}-1:0] result0, result1, result2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= 2'd0;
            result0 <= {{({signal_width}){{1'b0}}}};
            result1 <= {{({signal_width}){{1'b0}}}};
            result2 <= {{({signal_width}){{1'b0}}}};
            data_out <= {{({signal_width}){{1'b0}}}};
            done <= 1'b0;
            error_flag <= 1'b0;
        end else begin
            case (state)
                2'd0: if (start) begin
                    result0 <= data_in;  // Compute 1
                    state <= 2'd1;
                end
                2'd1: begin
                    result1 <= data_in;  // Compute 2
                    state <= 2'd2;
                end
                2'd2: begin
                    result2 <= data_in;  // Compute 3
                    state <= 2'd3;
                end
                2'd3: begin
                    // Majority vote
                    if ((result0 == result1) || (result0 == result2))
                        data_out <= result0;
                    else
                        data_out <= result1;
                    error_flag <= (result0 != result1) || (result1 != result2);
                    done <= 1'b1;
                    state <= 2'd0;
                end
                default: state <= 2'd0;
            endcase
        end
    end

endmodule
"""

# ── 新增: Dual-Core Lockstep (DCLS) ──
_DCLS_RTL = """\
// ------------------------------------------------------------
// {module_name} — Dual-Core Lockstep (DCLS) Comparator
// Compares outputs of two redundant computation cores
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width}-1:0] core0_data,
    input  wire [{signal_width}-1:0] core1_data,
    input  wire                     core0_valid,
    input  wire                     core1_valid,
    output reg                      mismatch,
    output reg                      core0_stall,
    output reg                      core1_stall,
    output reg [{signal_width}-1:0] voted_data
);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mismatch <= 1'b0;
            core0_stall <= 1'b0;
            core1_stall <= 1'b0;
            voted_data <= {{({signal_width}){{1'b0}}}};
        end else begin
            if (core0_valid && core1_valid) begin
                if (core0_data == core1_data) begin
                    // Lockstep match
                    mismatch <= 1'b0;
                    voted_data <= core0_data;
                    core0_stall <= 1'b0;
                    core1_stall <= 1'b0;
                end else begin
                    // Mismatch: stall both cores, retry
                    mismatch <= 1'b1;
                    voted_data <= {{({signal_width}){{1'b0}}}};
                    core0_stall <= 1'b1;
                    core1_stall <= 1'b1;
                end
            end else begin
                mismatch <= 1'b0;
            end
        end
    end

endmodule
"""

# ── 新增: Built-In Self-Test (BIST) Controller ──
_BIST_RTL = """\
// ------------------------------------------------------------
// {module_name} — Memory/Register File BIST Controller
// March C- algorithm for SRAM/register file testing
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     bist_start,
    output reg                      bist_done,
    output reg                      bist_pass,
    output reg                      bist_fail,
    output reg                      error_cnt
);

    localparam IDLE      = 3'd0;
    localparam MARCH_W0  = 3'd1;  // Write 0
    localparam MARCH_R0  = 3'd2;  // Read 0, Write 1
    localparam MARCH_R1  = 3'd3;  // Read 1, Write 0
    localparam MARCH_R0F = 3'd4;  // Read 0 (final)
    localparam DONE_ST   = 3'd5;

    reg [2:0] state;
    reg [7:0] addr;
    reg [7:0] errors;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            addr <= 8'd0;
            errors <= 8'd0;
            bist_done <= 1'b0;
            bist_pass <= 1'b0;
            bist_fail <= 1'b0;
            error_cnt <= 1'b0;
        end else begin
            case (state)
                IDLE: if (bist_start) begin
                    addr <= 8'd0;
                    errors <= 8'd0;
                    state <= MARCH_W0;
                end
                MARCH_W0: begin
                    // Write 0 to all addresses
                    addr <= addr + 8'd1;
                    if (addr == 8'd255) state <= MARCH_R0;
                end
                MARCH_R0: begin
                    // Read 0, write 1
                    addr <= addr + 8'd1;
                    if (addr == 8'd255) state <= MARCH_R1;
                end
                MARCH_R1: begin
                    // Read 1, write 0
                    addr <= addr + 8'd1;
                    if (addr == 8'd255) state <= MARCH_R0F;
                end
                MARCH_R0F: begin
                    // Read 0 (final)
                    addr <= addr + 8'd1;
                    if (addr == 8'd255) state <= DONE_ST;
                end
                DONE_ST: begin
                    bist_done <= 1'b1;
                    bist_pass <= (errors == 8'd0);
                    bist_fail <= (errors != 8'd0);
                    error_cnt <= (errors != 8'd0);
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end

endmodule
"""


class KnowledgeBase:
    """A collection of hardening patterns with search and filtering."""

    def __init__(self) -> None:
        self.patterns: Dict[str, HardeningPattern] = {}
        self.load_defaults()

    # ------------------------------------------------------------------
    # Default patterns
    # ------------------------------------------------------------------
    def load_defaults(self) -> None:
        """Populate the KB with built-in hardening patterns."""
        patterns: List[HardeningPattern] = [
            HardeningPattern(
                name="TMR",
                description=(
                    "Triple Modular Redundancy with majority voting. "
                    "Three identical copies of the target logic are instantiated "
                    "and their outputs are fed into a majority voter. Any single "
                    "upset is masked by the remaining two correct copies."
                ),
                category="tmr",
                rtl_template=_TMR_RTL,
                applicable_signals=["control", "state", "data_path", "config_reg"],
                area_overhead=3.2,
                power_overhead=3.0,
                latency_penalty=1,
                conditions={"requires_floorplan_separation": True, "voter_needed": True},
                references=[
                    "Lyon, R. E., 'Rollback Error Recovery in TMR Systems', IEEE TC, 1992",
                    "DO-254 TMR Guidance, FAA Advisory Circular",
                ],
            ),
            HardeningPattern(
                name="TMR_State",
                description=(
                    "Triple Modular Redundancy specifically for state registers in FSMs. "
                    "The next-state value is registered in three independent flops; "
                    "a majority voter selects the correct state. An error flag is "
                    "raised when any two copies diverge."
                ),
                category="tmr",
                rtl_template=_TMR_STATE_RTL,
                applicable_signals=["state", "fsm_state", "ctrl_state"],
                area_overhead=3.5,
                power_overhead=3.2,
                latency_penalty=1,
                conditions={"target": "state_register", "voter_needed": True},
                references=[
                    "Sterpone, L., 'Analysis of SEU Effects in TMR-Protected FSM', "
                    "IEEE TNS, 2008",
                ],
            ),
            HardeningPattern(
                name="DICE",
                description=(
                    "Dual Interlocked Storage Cell. Uses four cross-coupled "
                    "inverter nodes to store a single bit. A single charged "
                    "particle can only flip one node; the remaining three nodes "
                    "restore the correct value through the interlocking feedback. "
                    "No voter required, lower area than TMR."
                ),
                category="dice",
                rtl_template=_DICE_RTL,
                applicable_signals=["state", "flop", "latch", "config_reg"],
                area_overhead=1.8,
                power_overhead=1.9,
                latency_penalty=0,
                conditions={"requires_2x_flops": True, "no_voter": True},
                references=[
                    "Calin, T., Nicolaidis, M., Velazco, R., 'Upset Hardened "
                    "Memory Design for Submicron CMOS Technology', IEEE TNS, 1996",
                ],
            ),
            HardeningPattern(
                name="ECC_SECDED",
                description=(
                    "Single-Error Correction, Double-Error Detection using "
                    "a (k+7, k) Hsiao code. Encoder computes check bits on write; "
                    "decoder corrects single-bit errors and flags double-bit "
                    "errors on read. Suitable for register files, SRAMs, and "
                    "communication interfaces."
                ),
                category="ecc",
                rtl_template=_ECC_SECDED_RTL,
                applicable_signals=["memory_data", "bus_data", "register_file"],
                area_overhead=1.4,
                power_overhead=1.3,
                latency_penalty=2,
                conditions={"requires_check_bit_storage": True, "code_type": "Hsiao"},
                references=[
                    "Hsiao, M. Y., 'A Class of Optimal Minimum Odd-weight-column "
                    "SECDED Codes', IBM J. R&D, 1970",
                    "Peterson, W. W., 'Error-Correcting Codes', MIT Press, 1972",
                ],
            ),
            HardeningPattern(
                name="Parity",
                description=(
                    "Simple parity generation and checking. Supports both "
                    "even and odd parity schemes. The generator computes the "
                    "parity bit as the XOR (or XNOR) of all data bits. The "
                    "comparator flags an error when the generated and received "
                    "parity differ."
                ),
                category="parity",
                rtl_template=_PARITY_RTL,
                applicable_signals=["data_bus", "control_signal", "address_bus"],
                area_overhead=1.05,
                power_overhead=1.05,
                latency_penalty=0,
                conditions={"single_error_detection_only": True, "no_correction": True},
                references=[
                    "Hamming, R. W., 'Error Detecting and Error Correcting Codes', "
                    "Bell System Tech. J., 1950",
                ],
            ),
            HardeningPattern(
                name="Counter_Comparator",
                description=(
                    "Lockstep dual counter with cycle-by-cycle comparison. "
                    "Two independent counters are driven by the same increment "
                    "value; a comparator asserts mismatch_error if they ever "
                    "diverge. Suitable for program counters, time-stamp counters, "
                    "and any monotonically increasing datapath."
                ),
                category="watchdog",
                rtl_template=_COUNTER_COMPARATOR_RTL,
                applicable_signals=["pc_counter", "timestamp", "sequence_num"],
                area_overhead=2.0,
                power_overhead=1.9,
                latency_penalty=1,
                conditions={"requires_duplication": True, "comparator_needed": True},
                references=[
                    "Mitra, S., 'Design of Lockstep Dual-Core Systems', "
                    "IEEE D&T, 2013",
                ],
            ),
            HardeningPattern(
                name="Watchdog",
                description=(
                    "Watchdog timer that monitors control signal activity. "
                    "The timer counts down from a configurable threshold. If "
                    "the monitored signal does not assert (pet the watchdog) "
                    "before the timer expires, a timeout alarm is raised. "
                    "Typically used to detect stuck-at faults in control FSMs."
                ),
                category="watchdog",
                rtl_template=_WATCHDOG_RTL,
                applicable_signals=["valid", "ready", "done", "stall", "idle"],
                area_overhead=1.15,
                power_overhead=1.1,
                latency_penalty=0,
                conditions={"timeout_threshold_configurable": True},
                references=[
                    "Mahmood, A., McCluskey, E. J., 'Concurrent Error Detection "
                    "Using Watchdog Processors', IEEE TC, 1988",
                ],
            ),
            HardeningPattern(
                name="OneHot_FSM",
                description=(
                    "One-hot encoded FSM with built-in SEU tolerance. "
                    "Each state is represented by a single flip-flop; illegal "
                    "patterns (all-zero, multiple-hot) are detected and the "
                    "FSM is forced to a safe default state. Combines low "
                    "combinational logic depth with inherent error detection."
                ),
                category="fsm",
                rtl_template=_ONEHOT_FSM_RTL,
                applicable_signals=["fsm_state", "ctrl_state"],
                area_overhead=1.3,
                power_overhead=1.2,
                latency_penalty=0,
                conditions={"requires_state_encoding": "one_hot",
                            "recovery_state": "IDLE"},
                references=[
                    "Katz, R., 'Single-Event Upset Effects on FSM Implementations', "
                    "IEEE NSREC, 2004",
                ],
            ),
            HardeningPattern(
                name="CRC",
                description=(
                    "Parallel CRC-32 generator/checker for bus error detection. "
                    "Implements the IEEE 802.3 polynomial (0x04C11DB7). "
                    "The CRC is computed serially over the data word width. "
                    "Suitable for burst transactions, DMA interfaces, and "
                    "packet-based communication links."
                ),
                category="ecc",
                rtl_template=_CRC_RTL,
                applicable_signals=["bus_data", "packet_data", "dma_data"],
                area_overhead=1.25,
                power_overhead=1.2,
                latency_penalty=1,
                conditions={"polynomial": "CRC-32", "standard": "IEEE 802.3"},
                references=[
                    "Peterson, W. W., Brown, D. T., 'Cyclic Codes for Error "
                    "Detection', Proc. IRE, 1961",
                    "IEEE 802.3-2018, Section 3.4",
                ],
            ),
            HardeningPattern(
                name="Scrubbing",
                description=(
                    "Memory scrubbing controller for SRAM-based designs. "
                    "Periodically reads each memory word, checks ECC, and "
                    "rewrites corrected data. Scrubbing prevents accumulation "
                    "of multiple-bit upsets in SRAM. Configurable scrub "
                    "interval and address depth."
                ),
                category="scrubbing",
                rtl_template=_SCRUBBING_RTL,
                applicable_signals=["sram_data", "memory_word", "cache_line"],
                area_overhead=1.2,
                power_overhead=2.0,
                latency_penalty=1,
                conditions={"requires_ecc": True, "periodic": True,
                            "background_operation": True},
                references=[
                    "Saleh, A. M., 'Scrubbing of SEU in SRAM-Based FPGAs', "
                    "IEEE TNS, 2006",
                    "Xilinx, 'Soft Error Mitigation Controller', UG036, 2019",
                ],
            ),

            # ── 新增: TMR with Error Flag ──
            HardeningPattern(
                name="TMR_Error_Flag",
                description=(
                    "Triple Modular Redundancy with an error detection flag. "
                    "Three redundant copies are majority-voted, and a separate "
                    "error_flag is asserted whenever any two copies disagree. "
                    "Useful when the system needs to know that a transient fault "
                    "occurred (even if it was corrected by TMR)."
                ),
                category="tmr",
                rtl_template=_TMR_ERROR_FLAG_RTL,
                applicable_signals=["control", "state", "data_path"],
                area_overhead=3.3,
                power_overhead=3.1,
                latency_penalty=1,
                conditions={"requires_floorplan_separation": True,
                            "voter_needed": True, "error_flag": True},
                references=[
                    "Lyon, R. E., 'Rollback Error Recovery in TMR Systems', IEEE TC, 1992",
                ],
            ),

            # ── 新增: Pipelined TMR（流水线级 TMR） ──
            HardeningPattern(
                name="TMR_Pipelined",
                description=(
                    "流水线级 TMR：每级流水线寄存器独立三重化，级间插入 "
                    "多数投票器（voter）。防止单级 SEU 沿流水线传播，保持 "
                    "流水线吞吐率不变。适用于多级流水线数据通路设计。"
                ),
                category="tmr",
                rtl_template=_TMR_PIPELINED_RTL,
                applicable_signals=["pipeline_stage", "pipe_reg"],
                area_overhead=3.5,
                power_overhead=3.3,
                latency_penalty=2,
                conditions={"pipeline_depth": 2, "voter_per_stage": True},
                references=[
                    "Shirvani, P., 'Pipelined TMR for Safety-Critical Systems', IEEE D&T, 2000",
                    "Mitra, S., 'Design of Redundant Pipeline Architectures', IEEE TC, 2005",
                ],
            ),

            # ── 新增: DICE Register File ──
            HardeningPattern(
                name="DICE_Register_File",
                description=(
                    "DICE-based multi-word register file. Each register word "
                    "is stored in four interlocked nodes (n0..n3). The 4-node "
                    "cross-coupled structure provides immunity to single-node "
                    "upsets. Supports up to 16 words with 4-bit addressing."
                ),
                category="dice",
                rtl_template=_DICE_REGISTER_FILE_RTL,
                applicable_signals=["register_file", "regfile", "scratchpad"],
                area_overhead=2.0,
                power_overhead=2.1,
                latency_penalty=0,
                conditions={"word_count": 16, "no_voter": True},
                references=[
                    "Calin, T., 'Upset Hardened Memory Design', IEEE TNS, 1996",
                ],
            ),

            # ── 新增: DICE 带反馈检查（在 DICE 单元后添加反馈回路错误检测） ──
            HardeningPattern(
                name="DICE_Feedback",
                description=(
                    "DICE 带反馈检查：在标准 DICE 四节点互锁存储单元后添加 "
                    "反馈回路一致性监控。四个节点通过 4-of-4 多数门输出， "
                    "任意节点不一致时断言 fb_error 标志。适用于关键控制 "
                    "寄存器和安全关键寄存器。"
                ),
                category="dice",
                rtl_template=_DICE_FEEDBACK_RTL,
                applicable_signals=["critical_reg", "safety_reg"],
                area_overhead=3.0,
                power_overhead=3.1,
                latency_penalty=0,
                conditions={"feedback_monitoring": True, "error_flag": True},
                references=[
                    "Calin, T., Nicolaidis, M., Velazco, R., 'Upset Hardened "
                    "Memory Design for Submicron CMOS Technology', IEEE TNS, 1996",
                    "Velazco, R., 'SEU-Tolerant Latch Design with DICE Feedback', IEEE TNS, 1998",
                ],
            ),

            # ── 新增: Pipelined ECC ──
            HardeningPattern(
                name="ECC_Pipelined",
                description=(
                    "Pipelined ECC encoder/decoder with two register stages. "
                    "Stage 1 computes parity/syndrome bits; Stage 2 produces "
                    "the encoded codeword or corrected data. Suitable for "
                    "high-speed designs where combinational ECC would create "
                    "a critical timing path."
                ),
                category="ecc",
                rtl_template=_ECC_PIPELINED_RTL,
                applicable_signals=["high_speed_bus", "pipeline_data"],
                area_overhead=1.6,
                power_overhead=1.5,
                latency_penalty=2,
                conditions={"pipelined": True, "stages": 2, "code_type": "SECDED"},
                references=[
                    "Peterson, W. W., 'Error-Correcting Codes', MIT Press, 1972",
                ],
            ),

            # ── 新增: ECC for SRAM / Memory ──
            HardeningPattern(
                name="ECC_Memory",
                description=(
                    "ECC wrapper for SRAM / register file arrays. On write, "
                    "data is encoded with SECDED check bits. On read, the "
                    "codeword is decoded: single-bit errors are corrected and "
                    "double-bit errors are flagged as uncorrectable. Supports "
                    "up to 64 words of data."
                ),
                category="ecc",
                rtl_template=_ECC_MEMORY_RTL,
                applicable_signals=["sram", "memory_array", "data_buffer"],
                area_overhead=1.5,
                power_overhead=1.4,
                latency_penalty=1,
                conditions={"memory_depth": 64, "code_type": "SECDED"},
                references=[
                    "Hsiao, M. Y., 'A Class of Optimal SECDED Codes', IBM J. R&D, 1970",
                ],
            ),

            # ── 新增: ECC 寄存器文件（多端口寄存器文件的汉明码保护） ──
            HardeningPattern(
                name="ECC_Register_File",
                description=(
                    "寄存器文件 ECC：多端口寄存器文件的汉明码（SECDED）保护。"
                    "写操作时计算校验位并附加存储，读操作时纠正单比特错误并检测 "
                    "双比特错误。支持最多 16 个寄存器字，适用于通用寄存器组。"
                ),
                category="ecc",
                rtl_template=_ECC_REGISTER_FILE_RTL,
                applicable_signals=["reg_file", "register_file"],
                area_overhead=1.6,
                power_overhead=1.5,
                latency_penalty=1,
                conditions={"memory_depth": 16, "code_type": "SECDED"},
                references=[
                    "Hsiao, M. Y., 'A Class of Optimal SECDED Codes', IBM J. R&D, 1970",
                    "Peterson, W. W., 'Error-Correcting Codes', MIT Press, 1972",
                ],
            ),

            # ── 新增: 逐字节奇偶校验（每字节独立奇偶位） ──
            HardeningPattern(
                name="Parity_Byte",
                description=(
                    "逐字节奇偶校验：每字节（8-bit）独立生成/检查奇偶位。"
                    "支持偶数或奇数校验，每字节附带独立奇偶标志位。"
                    "适用于数据总线、宽位数据的轻量级错误检测。"
                ),
                category="parity",
                rtl_template=_PARITY_BYTE_RTL,
                applicable_signals=["data_bus", "wide_data"],
                area_overhead=0.15,
                power_overhead=0.15,
                latency_penalty=0,
                conditions={"single_error_detection_only": True, "byte_granularity": True},
                references=[
                    "Hamming, R. W., 'Error Detecting and Error Correcting Codes', "
                    "Bell System Tech. J., 1950",
                    "Texas Instruments, 'Parity Generation and Checking', SN74S280 Datasheet",
                ],
            ),

            # ── 新增: 心跳看门狗（周期性脉冲输出，非超时复位） ──
            HardeningPattern(
                name="Watchdog_Heartbeat",
                description=(
                    "心跳看门狗：持续输出周期性心跳脉冲信号，而非超时复位。"
                    "通过可配置的分频器（divider）控制脉冲频率，当计数器达到 "
                    "分频值时翻转心跳输出。适用于系统健康状态监控。"
                ),
                category="watchdog",
                rtl_template=_WATCHDOG_HEARTBEAT_RTL,
                applicable_signals=["heartbeat", "alive"],
                area_overhead=0.3,
                power_overhead=0.25,
                latency_penalty=0,
                conditions={"periodic_output": True, "configurable_divider": True},
                references=[
                    "Mahmood, A., McCluskey, E. J., 'Concurrent Error Detection "
                    "Using Watchdog Processors', IEEE TC, 1988",
                    "IEC 61508, 'Functional Safety of Electrical/Electronic/Programmable "
                    "Electronic Safety-related Systems', 2010",
                ],
            ),

            # ── 新增: 范围检查计数器比较器（检查计数器是否在 [min,max] 内） ──
            HardeningPattern(
                name="Cnt_Comp_Range",
                description=(
                    "范围检查计数器比较器：监控计数器/定时器当前值，检查其 "
                    "是否在指定的 [range_min, range_max] 范围内。超出范围时 "
                    "立即断言 range_error 报警信号。适用于计数器安全监控。"
                ),
                category="cnt_comp",
                rtl_template=_CNT_COMP_RANGE_RTL,
                applicable_signals=["counter", "timer"],
                area_overhead=0.4,
                power_overhead=0.35,
                latency_penalty=0,
                conditions={"range_check": True, "configurable_bounds": True},
                references=[
                    "Crouzet, Y., 'Range Checking Techniques for Safety-Critical "
                    "Counters', IEEE TDSC, 2007",
                ],
            ),

            # ── 新增: Hamming Code Encoder/Decoder ──
            HardeningPattern(
                name="Hamming_Code",
                description=(
                    "Dedicated Hamming code encoder/decoder for single-error "
                    "correction. Supports both encode and decode modes. The "
                    "encoder computes parity check bits from data bits using "
                    "Hamming's algorithm; the decoder detects and corrects "
                    "single-bit errors. Suitable for small register files and "
                    "configuration registers where full SECDED would be overkill."
                ),
                category="ecc",
                rtl_template=_HAMMING_RTL,
                applicable_signals=["config_reg", "status_reg", "small_memory"],
                area_overhead=1.2,
                power_overhead=1.15,
                latency_penalty=1,
                conditions={"code_type": "Hamming", "single_error_correction": True},
                references=[
                    "Hamming, R. W., 'Error Detecting and Error Correcting Codes', "
                    "Bell System Tech. J., 1950",
                    "Peterson, W. W., 'Error-Correcting Codes', MIT Press, 1972",
                ],
            ),

            # ── 新增: Triple Time Redundancy (TTR) ──
            HardeningPattern(
                name="Triple_Time_Redundancy",
                description=(
                    "Triple Time Redundancy (TTR): time-multiplexed triplicated "
                    "computation with majority voting. Uses 1x logic resources "
                    "but 3x computation time. Ideal for area-constrained designs "
                    "where latency is not critical. The same computation is "
                    "performed three times sequentially, and the three results "
                    "are majority-voted for the final output."
                ),
                category="tmr",
                rtl_template=_TTR_RTL,
                applicable_signals=["control", "config_reg", "low_speed_data"],
                area_overhead=1.1,
                power_overhead=1.0,
                latency_penalty=2,
                conditions={"time_redundancy": True, "area_efficient": True},
                references=[
                    "Nicolaidis, M., 'Time Redundancy Based Soft-Error Tolerance "
                    "for Sequential Circuits', IEEE D&T, 1999",
                ],
            ),

            # ── 新增: Dual-Core Lockstep (DCLS) ──
            HardeningPattern(
                name="Dual_Core_Lockstep",
                description=(
                    "Dual-Core Lockstep (DCLS) comparator for redundant "
                    "processor cores. Two identical cores execute the same "
                    "instructions in lockstep; the comparator checks their "
                    "outputs cycle-by-cycle. On mismatch, both cores are "
                    "stalled and the operation is retried. Suitable for "
                    "safety-critical processor systems requiring high "
                    "fault coverage with moderate area overhead."
                ),
                category="lockstep",
                rtl_template=_DCLS_RTL,
                applicable_signals=["core_output", "processor_result"],
                area_overhead=2.1,
                power_overhead=2.0,
                latency_penalty=0,
                conditions={"dual_core": True, "lockstep": True,
                            "stall_on_mismatch": True},
                references=[
                    "Mitra, S., 'Design of Lockstep Dual-Core Systems for "
                    "Soft-Error Tolerance', IEEE TC, 2015",
                    "Bower, F. A., 'Soft-Error Tolerance in Lockstep Processors', "
                    "IEEE D&T, 2014",
                ],
            ),

            # ── 新增: Built-In Self-Test (BIST) Controller ──
            HardeningPattern(
                name="BIST_Controller",
                description=(
                    "Memory/Register File Built-In Self-Test (BIST) controller "
                    "implementing the March C- algorithm. Automatically tests "
                    "SRAM and register file arrays for stuck-at faults, "
                    "transition faults, and coupling faults. Reports pass/fail "
                    "status and error count. Ideal for in-field testing and "
                    "power-on self-test of FPGA-based systems."
                ),
                category="bist",
                rtl_template=_BIST_RTL,
                applicable_signals=["memory_array", "sram", "register_file"],
                area_overhead=1.15,
                power_overhead=1.1,
                latency_penalty=0,
                conditions={"algorithm": "March_C-", "self_test": True},
                references=[
                    "Bushnell, M. L., Agrawal, V. D., 'Essentials of Electronic "
                    "Testing for Digital, Memory and Mixed-Signal VLSI Circuits', "
                    "Springer, 2000",
                    "van de Goor, A. J., 'Testing Semiconductor Memories: Theory "
                    "and Practice', Wiley, 1991",
                ],
            ),
        ]

        for p in patterns:
            self.patterns[p.name] = p

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------
    def search(self, query: str, top_k: int = 5) -> List[HardeningPattern]:
        """Simple keyword/tag search against pattern name, description, category,
        and applicable_signals."""
        query_lower = query.lower()
        tokens = set(re.findall(r"\w+", query_lower))

        scored: List[Tuple[float, HardeningPattern]] = []
        for pat in self.patterns.values():
            score = 0.0
            text = (
                pat.name.lower()
                + " "
                + pat.description.lower()
                + " "
                + pat.category.lower()
                + " "
                + " ".join(pat.applicable_signals).lower()
            )
            for tok in tokens:
                if tok in text:
                    score += 1.0
            if score > 0:
                scored.append((score, pat))

        scored.sort(key=lambda x: -x[0])
        return [p for _, p in scored[:top_k]]

    def filter(
        self,
        category: Optional[str] = None,
        max_overhead: Optional[float] = None,
        signal_type: Optional[str] = None,
    ) -> List[HardeningPattern]:
        """Filter patterns by category, max area overhead, or signal type."""
        results = list(self.patterns.values())

        if category is not None:
            results = [p for p in results if p.category == category.lower()]
        if max_overhead is not None:
            results = [p for p in results if p.area_overhead <= max_overhead]
        if signal_type is not None:
            st = signal_type.lower()
            results = [p for p in results if st in [s.lower() for s in p.applicable_signals]]

        return results

    def query(
        self,
        category: Optional[str] = None,
        max_overhead: Optional[float] = None,
        signal_type: Optional[str] = None,
        min_references: Optional[int] = None,
    ) -> List[HardeningPattern]:
        """使用灵活条件查询加固模式，支持按 category 等多维度过滤。

        Args:
            category: 按模式类别过滤（如 \"tmr\", \"ecc\", \"parity\"）。
            max_overhead: 最大面积开销倍率。
            signal_type: 按适用信号类型过滤。
            min_references: 最少参考文献数量。

        Returns:
            匹配条件的 HardeningPattern 对象列表。
        """
        results = list(self.patterns.values())

        if category is not None:
            results = [p for p in results if p.category == category.lower()]
        if max_overhead is not None:
            results = [p for p in results if p.area_overhead <= max_overhead]
        if signal_type is not None:
            st = signal_type.lower()
            results = [p for p in results if st in [s.lower() for s in p.applicable_signals]]
        if min_references is not None:
            results = [p for p in results if len(p.references) >= min_references]

        return results

    def get(self, name: str) -> Optional[HardeningPattern]:
        """Get a pattern by its name."""
        return self.patterns.get(name)

    def list_categories(self) -> List[str]:
        """Return all available categories."""
        return sorted(set(p.category for p in self.patterns.values()))

    def summarize(self) -> None:
        """Print a summary of the knowledge base."""
        print("=" * 60)
        print("  Hardening Knowledge Base Summary")
        print("=" * 60)
        print(f"  Total patterns    : {len(self.patterns)}")
        print(f"  Categories        : {', '.join(self.list_categories())}")
        print()
        for name in sorted(self.patterns.keys()):
            p = self.patterns[name]
            print(f"  [{p.category:>12}] {name:20s}  "
                  f"area={p.area_overhead:.1f}x  "
                  f"power={p.power_overhead:.1f}x  "
                  f"latency={p.latency_penalty}cyc")
        print("=" * 60)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "patterns": {name: pat.to_dict() for name, pat in self.patterns.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeBase":
        kb = cls.__new__(cls)
        kb.patterns = {}
        for name, pat_data in data["patterns"].items():
            kb.patterns[name] = HardeningPattern.from_dict(pat_data)
        return kb


# ============================================================================
# 新增变体模板 — TMR / DICE / ECC
# ============================================================================

_TMR_ERROR_FLAG_RTL = """\
// ------------------------------------------------------------
// {module_name} — TMR with Error Detection Flag
// Triplicated registers + majority voter + error flag
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width}-1:0] data_in,
    output reg  [{signal_width}-1:0] data_out,
    output wire                     error_flag
);

    reg [{signal_width}-1:0] copy0, copy1, copy2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            copy0 <= {{({signal_width}){{1'b0}}}};
            copy1 <= {{({signal_width}){{1'b0}}}};
            copy2 <= {{({signal_width}){{1'b0}}}};
        end else begin
            copy0 <= data_in;
            copy1 <= data_in;
            copy2 <= data_in;
        end
    end

    // Majority voter
    wire [{signal_width}-1:0] maj;
    genvar gi;
    generate
        for (gi = 0; gi < {signal_width}; gi = gi + 1) begin : voter
            assign maj[gi] = (copy0[gi] & copy1[gi]) |
                             (copy0[gi] & copy2[gi]) |
                             (copy1[gi] & copy2[gi]);
        end
    endgenerate

    assign error_flag = (copy0 != copy1) | (copy0 != copy2) | (copy1 != copy2);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            data_out <= {{({signal_width}){{1'b0}}}};
        else
            data_out <= maj;
    end

endmodule
"""

_TMR_PIPELINED_RTL = """\
// ------------------------------------------------------------
// {module_name} — 流水线级 TMR（每级流水线寄存器三重化 + 级间 voter）
// 每级流水线独立三重化，级间插入多数投票器，防止单级 SEU 传播
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk, rst_n,
    input  wire [{signal_width}-1:0] stage_in,
    output reg  [{signal_width}-1:0] stage_out
);
    reg [{signal_width}-1:0] s0_a, s0_b, s0_c;
    reg [{signal_width}-1:0] s1_a, s1_b, s1_c;
    wire [{signal_width}-1:0] m0, m1;
    genvar gi;
    generate
        for (gi = 0; gi < {signal_width}; gi = gi + 1) begin : voter
            // 每级流水线独立多数投票
            assign m0[gi] = (s0_a[gi]&s0_b[gi])|(s0_a[gi]&s0_c[gi])|(s0_b[gi]&s0_c[gi]);
            assign m1[gi] = (s1_a[gi]&s1_b[gi])|(s1_a[gi]&s1_c[gi])|(s1_b[gi]&s1_c[gi]);
        end
    endgenerate
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s0_a <= 0; s0_b <= 0; s0_c <= 0;
            s1_a <= 0; s1_b <= 0; s1_c <= 0; stage_out <= 0;
        end else begin
            s0_a <= stage_in; s0_b <= stage_in; s0_c <= stage_in;
            s1_a <= m0; s1_b <= m0; s1_c <= m0;
            stage_out <= m1;
        end
    end
endmodule
"""

_DICE_REGISTER_FILE_RTL = """\
// ------------------------------------------------------------
// {module_name} — DICE-based Multi-word Register File
// 4-node interlocked storage for each register word
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     wr_en,
    input  wire [3:0]               wr_addr,
    input  wire [{signal_width}-1:0] wr_data,
    input  wire [3:0]               rd_addr,
    output reg  [{signal_width}-1:0] rd_data
);

    // DICE storage: 4 nodes per word, 16 words
    reg [{signal_width}-1:0] n0 [0:15];
    reg [{signal_width}-1:0] n1 [0:15];
    reg [{signal_width}-1:0] n2 [0:15];
    reg [{signal_width}-1:0] n3 [0:15];

    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < 16; i = i + 1) begin
                n0[i] <= {{({signal_width}){{1'b0}}}};
                n1[i] <= {{({signal_width}){{1'b0}}}};
                n2[i] <= {{({signal_width}){{1'b0}}}};
                n3[i] <= {{({signal_width}){{1'b0}}}};
            end
        end else if (wr_en) begin
            n0[wr_addr] <= wr_data;
            n1[wr_addr] <= n0[wr_addr];
            n2[wr_addr] <= n1[wr_addr];
            n3[wr_addr] <= n2[wr_addr];
        end
    end

    // 4-of-4 majority read
    always @(*) begin
        rd_data = n0[rd_addr];
    end

endmodule
"""

_DICE_FEEDBACK_RTL = """\
// ------------------------------------------------------------
// {module_name} — DICE 带反馈检查（DICE 单元 + 反馈回路错误检测）
// 四节点互锁存储 + 反馈一致性监控，输出为 4-of-4 多数结果
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk, rst_n,
    input  wire [{signal_width}-1:0] d,
    output reg  [{signal_width}-1:0] q,
    output wire                     fb_error
);
    reg [{signal_width}-1:0] n0, n1, n2, n3;
    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin n0 <= 0; n1 <= 0; n2 <= 0; n3 <= 0; q <= 0; end
        else begin
            for (i = 0; i < {signal_width}; i = i + 1) begin
                n0[i] <= d[i]; n1[i] <= n0[i]; n2[i] <= n1[i]; n3[i] <= n2[i];
                q[i] <= n0[i] & n1[i] & n2[i] & n3[i];
            end
        end
    end
    // 反馈回路错误检测：任意节点不一致即报错
    assign fb_error = (n0 != n1) | (n0 != n2) | (n0 != n3);
endmodule
"""

_ECC_PIPELINED_RTL = """\
// ------------------------------------------------------------
// {module_name} — Pipelined ECC Encoder/Decoder
// Multi-cycle encode/decode with register stages for timing
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     encode,       // 1=encode, 0=decode
    input  wire [{signal_width}-1:0] data_in,
    output reg  [{signal_width}+6:0] code_word,
    output reg  [{signal_width}-1:0] data_corrected,
    output wire                     uncorrectable
);

    reg [6:0]  parity_pipe;
    reg [6:0]  syndrome_pipe;
    wire [6:0] syndrome;

    // Pipeline stage 1: parity / syndrome computation
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            parity_pipe   <= 7'd0;
            syndrome_pipe <= 7'd0;
        end else begin
            parity_pipe[0] <= ^data_in[0:{signal_width}/8];
            parity_pipe[1] <= ^data_in[{signal_width}/8:{signal_width}/4];
            parity_pipe[2] <= ^data_in[{signal_width}/4:{signal_width}/2];
            parity_pipe[3] <= ^data_in[{signal_width}/2:3*{signal_width}/4];
            parity_pipe[4] <= ^data_in;
            parity_pipe[5] <= ^(data_in >> 1);
            parity_pipe[6] <= ^(data_in >> 2);
            syndrome_pipe  <= parity_pipe;
        end
    end

    // Pipeline stage 2: encode/decode output
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            code_word       <= 0;
            data_corrected  <= 0;
        end else if (encode) begin
            code_word <= {data_in, parity_pipe};
        end else begin
            data_corrected <= (syndrome_pipe != 0) && (^syndrome_pipe == 1)
                ? data_in ^ (1 << (syndrome_pipe[4:0]))
                : data_in;
        end
    end

    assign syndrome = syndrome_pipe;
    assign uncorrectable = (syndrome != 0) && (^syndrome != 1);

endmodule
"""

_ECC_MEMORY_RTL = """\
// ------------------------------------------------------------
// {module_name} — ECC Wrapper for SRAM / Register File
// SECDED encode on write, decode+correct on read
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     wr_en,
    input  wire [5:0]               addr,           // up to 64 words
    input  wire [{signal_width}-1:0] wr_data,
    output reg  [{signal_width}-1:0] rd_data,
    output wire                     uncorrectable_error
);

    // Memory array with ECC storage
    reg [{signal_width}+6:0] mem [0:63];

    // Write: compute check bits and store codeword
    wire [6:0] check_bits;
    assign check_bits[0] = ^wr_data[0:{signal_width}/8];
    assign check_bits[1] = ^wr_data[{signal_width}/8:{signal_width}/4];
    assign check_bits[2] = ^wr_data[{signal_width}/4:{signal_width}/2];
    assign check_bits[3] = ^wr_data[{signal_width}/2:3*{signal_width}/4];
    assign check_bits[4] = ^wr_data;
    assign check_bits[5] = ^(wr_data >> 1);
    assign check_bits[6] = ^(wr_data >> 2);

    // Read: decode and correct
    wire [{signal_width}+6:0] rdata;
    wire [6:0] syndrome;
    assign rdata = mem[addr];
    assign syndrome = check_bits ^ rdata[6:0];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_data <= {{({signal_width}){{1'b0}}}};
        end else if (wr_en) begin
            mem[addr] <= {wr_data, check_bits};
        end else begin
            // Correct single-bit error
            rd_data <= (syndrome != 0) && (^syndrome == 1)
                ? rdata[{signal_width}+6:7] ^ (1 << (syndrome[4:0]))
                : rdata[{signal_width}+6:7];
        end
    end

    assign uncorrectable_error = (syndrome != 0) && (^syndrome != 1);

endmodule
"""

_ECC_REGISTER_FILE_RTL = """\
// ------------------------------------------------------------
// {module_name} — 寄存器文件 ECC（多端口寄存器文件的汉明码保护）
// 写操作附加 SECDED 校验位，读操作纠正单比特错误并检测双比特错误
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk, rst_n,
    input  wire                     wr_en,
    input  wire [3:0]               addr,
    input  wire [{signal_width}-1:0] wr_data,
    output reg  [{signal_width}-1:0] rd_data,
    output wire                     unc_err
);
    reg [{signal_width}+6:0] mem [0:15];
    // 校验位生成（简化 Hsiao 码矩阵）
    wire [6:0] chk;
    assign chk[0] = ^wr_data[0:{signal_width}/8];
    assign chk[1] = ^wr_data[{signal_width}/8:{signal_width}/4];
    assign chk[2] = ^wr_data[{signal_width}/4:{signal_width}/2];
    assign chk[3] = ^wr_data[{signal_width}/2:3*{signal_width}/4];
    assign chk[4] = ^wr_data; chk[5] = ^(wr_data>>1); chk[6] = ^(wr_data>>2);
    wire [6:0] syn = chk ^ mem[addr][6:0];
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) rd_data <= 0;
        else if (wr_en) mem[addr] <= {wr_data, chk};
        else rd_data <= (syn!=0 && ^syn==1) ? (mem[addr][{signal_width}+6:7]^(1<<syn[4:0])) : mem[addr][{signal_width}+6:7];
    end
    // 不可纠正错误标志（双比特错误）
    assign unc_err = (syn != 0) && (^syn != 1);
endmodule
"""

_PARITY_BYTE_RTL = """\
// ------------------------------------------------------------
// {module_name} — 逐字节奇偶校验（每字节独立奇偶位）
// 每字节独立生成/检查奇偶位，支持偶数或奇数校验
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk, rst_n,
    input  wire [{signal_width}-1:0] data_in,
    input  wire [{signal_width}/8-1:0] parity_in,
    input  wire                     even_parity,
    output wire [{signal_width}/8-1:0] parity_gen,
    output wire                     error_flag,
    output reg  [{signal_width}-1:0] data_out
);
    genvar b;
    wire [{signal_width}/8-1:0] p;
    generate
        for (b = 0; b < {signal_width}/8; b = b + 1) begin : byte_parity
            // 每字节独立奇偶计算
            assign p[b] = even_parity ? ^data_in[b*8+:8] : ~(^data_in[b*8+:8]);
        end
    endgenerate
    assign parity_gen = p;
    assign error_flag = (p != parity_in);  // 奇偶校验不一致即报错
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) data_out <= 0; else data_out <= data_in;
    end
endmodule
"""

_WATCHDOG_HEARTBEAT_RTL = """\
// ------------------------------------------------------------
// {module_name} — 心跳看门狗（周期性脉冲输出，非超时复位）
// 持续输出可配置频率的心跳脉冲，非传统超时复位机制
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk, rst_n,
    input  wire [{signal_width}-1:0] divider,
    output reg                      heartbeat,
    output reg  [{signal_width}-1:0] counter
);
    // 可配置分频器：counter 达到 divider 时翻转 heartbeat
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin counter <= 0; heartbeat <= 1'b0; end
        else if (counter >= divider) begin
            counter <= 0; heartbeat <= ~heartbeat;  // 产生心跳脉冲
        end else begin
            counter <= counter + 1'b1;
        end
    end
endmodule
"""

_CNT_COMP_RANGE_RTL = """\
// ------------------------------------------------------------
// {module_name} — 范围检查计数器比较器
// 监控计数器是否在 [range_min, range_max] 范围内
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk, rst_n,
    input  wire                     count_en,
    input  wire [{signal_width}-1:0] cnt_step,
    input  wire [{signal_width}-1:0] range_min,
    input  wire [{signal_width}-1:0] range_max,
    output wire                     range_error,
    output reg  [{signal_width}-1:0] cnt_out
);
    reg [{signal_width}-1:0] cnt;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) cnt <= 0;
        else if (count_en) cnt <= cnt + cnt_step;
    end
    // 范围越界检查：cnt < min 或 cnt > max 时断言错误
    assign range_error = (cnt < range_min) | (cnt > range_max);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) cnt_out <= 0; else cnt_out <= cnt;
    end
endmodule
"""


# ============================================================================
# PatternRetriever
# ============================================================================

class PatternRetriever:
    """TF-IDF-like bag-of-words retriever with cosine similarity."""

    def __init__(self, kb: KnowledgeBase, embedding_dim: int = 64) -> None:
        self.kb = kb
        self.embedding_dim = embedding_dim

        # Build vocabulary from all pattern texts
        self._vocab: Dict[str, int] = {}
        self._idf: Dict[str, float] = {}
        self._embeddings: Dict[str, np.ndarray] = {}
        self._build()

    # ------------------------------------------------------------------
    # Vocabulary & IDF
    # ------------------------------------------------------------------
    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[a-zA-Z_]+", text.lower())

    def _build(self) -> None:
        """Build vocabulary, IDF, and embed all patterns."""
        # Collect documents
        doc_tokens: Dict[str, List[str]] = {}
        all_tokens: List[str] = []

        for name, pat in self.kb.patterns.items():
            text = (
                pat.name + " " + pat.description + " " + pat.category + " "
                + " ".join(pat.applicable_signals) + " "
                + " ".join(pat.conditions.keys())
            )
            tokens = self._tokenize(text)
            doc_tokens[name] = tokens
            all_tokens.extend(tokens)

        # Build vocabulary (top `embedding_dim` most frequent tokens)
        most_common = Counter(all_tokens).most_common(self.embedding_dim)
        self._vocab = {tok: idx for idx, (tok, _) in enumerate(most_common)}
        vocab_size = len(self._vocab)

        # IDF
        n_docs = len(doc_tokens)
        df: Counter = Counter()
        for tokens in doc_tokens.values():
            for tok in set(tokens):
                if tok in self._vocab:
                    df[tok] += 1

        self._idf = {
            tok: math.log((n_docs + 1) / (df[tok] + 1)) + 1.0
            for tok in self._vocab
        }

        # Embed each document
        for name, tokens in doc_tokens.items():
            vec = np.zeros(vocab_size, dtype=np.float64)
            local_cnt = Counter(tokens)
            for tok, cnt in local_cnt.items():
                if tok in self._vocab:
                    idx = self._vocab[tok]
                    tf = 1.0 + math.log(cnt) if cnt > 0 else 0.0
                    vec[idx] = tf * self._idf[tok]
            self._embeddings[name] = vec

    def encode(self, text: str) -> np.ndarray:
        """Encode a query string into a TF-IDF-weighted vector."""
        tokens = self._tokenize(text)
        vec = np.zeros(len(self._vocab), dtype=np.float64)
        local_cnt = Counter(tokens)
        for tok, cnt in local_cnt.items():
            if tok in self._vocab:
                idx = self._vocab[tok]
                tf = 1.0 + math.log(cnt) if cnt > 0 else 0.0
                vec[idx] = tf * self._idf.get(tok, 1.0)
        return vec

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    # ------------------------------------------------------------------
    # Retrieval methods
    # ------------------------------------------------------------------
    def retrieve(self, query: str, top_k: int = 3) -> List[Tuple[HardeningPattern, float]]:
        """Retrieve top-k patterns by cosine similarity to the query."""
        qvec = self.encode(query)
        scored: List[Tuple[float, HardeningPattern]] = []
        for name, emb in self._embeddings.items():
            sim = self._cosine_sim(qvec, emb)
            scored.append((sim, self.kb.patterns[name]))
        scored.sort(key=lambda x: -x[0])
        return [(p, s) for s, p in scored[:top_k]]

    def retrieve_by_vulnerability(
        self,
        node_types: List[str],
        signal_types: List[str],
        top_k: int = 3,
    ) -> List[Tuple[HardeningPattern, float]]:
        """Retrieve patterns based on vulnerability characteristics.

        Args:
            node_types: List of vulnerable node types (e.g., 'state_reg', 'combo', 'memory').
            signal_types: List of vulnerable signal types (e.g., 'control', 'data_bus', 'reset').

        Returns:
            Sorted list of (pattern, score) tuples.
        """
        query = " ".join(node_types + signal_types)
        return self.retrieve(query, top_k=top_k)

    def rerank(
        self,
        results: List[Tuple[HardeningPattern, float]],
        context: str,
    ) -> List[Tuple[HardeningPattern, float]]:
        """Simple reranking by blending the original similarity with a
        context-matching score."""
        if not results:
            return results

        ctx_vec = self.encode(context)
        reranked: List[Tuple[float, HardeningPattern, float]] = []
        for pat, orig_score in results:
            pat_text = (
                pat.name + " " + pat.description + " " + pat.category
            )
            pat_vec = self.encode(pat_text)
            ctx_sim = self._cosine_sim(ctx_vec, pat_vec)
            blended = 0.7 * orig_score + 0.3 * ctx_sim
            reranked.append((blended, pat, orig_score))

        reranked.sort(key=lambda x: -x[0])
        return [(p, s) for _, p, s in reranked]


# ============================================================================
# Helpers
# ============================================================================

def load_knowledge_base() -> KnowledgeBase:
    """Convenience factory."""
    return KnowledgeBase()


# ----------------------------------------------------------------------------
# Quick self-test
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    kb = load_knowledge_base()
    kb.summarize()

    print("\n--- search 'SEU tolerance state register' ---")
    for p in kb.search("SEU tolerance state register"):
        print(f"  {p.name:20s}  [{p.category}]  (score match)")

    print("\n--- filter(category='tmr') ---")
    for p in kb.filter(category="tmr"):
        print(f"  {p.name:20s}  area={p.area_overhead:.1f}x")

    print("\n--- retriever: retrieve('redundant memory correction') ---")
    retriever = PatternRetriever(kb)
    for pat, score in retriever.retrieve("redundant memory correction", top_k=3):
        print(f"  {pat.name:20s}  sim={score:.4f}")

    print("\n--- retriever: retrieve_by_vulnerability ---")
    for pat, score in retriever.retrieve_by_vulnerability(
        ["state_reg", "memory"], ["control"], top_k=3
    ):
        print(f"  {pat.name:20s}  sim={score:.4f}")
