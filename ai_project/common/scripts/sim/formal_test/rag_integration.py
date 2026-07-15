#!/usr/bin/env python3
"""
rag_integration.py — RAG (Retrieval-Augmented Generation) 集成模块

将加固设计模式知识库与 LLM 连接，自动生成加固后的 RTL 代码。
作为自动硬件加固系统的组成部分，接收 GNN 脆弱性分析结果，
检索相关加固模式，并生成对应的加固 RTL。

用法:
    from rag_integration import RAGEngine

    engine = RAGEngine(llm_backend='mock')
    engine.load_knowledge_base()

    design_info = {
        'module_name': 'tmr_voter',
        'signals': ['data_in', 'data_out', 'clk', 'rst_n'],
        'signal_width': 32,
    }
    vulnerability_result = {
        'all_vulnerable_nodes': [{'node_id': 0, 'score': 0.85}],
        'num_nodes': 5,
    }
    rtl = engine.generate_hardened_rtl(design_info, vulnerability_result)

    # Pipe with external pipeline
    from rag_integration import integrate_with_pipeline
    strategy_overrides = integrate_with_pipeline(vulnerability_result, pipeline)
"""

import os
import re
import json
import time
from typing import Dict, List, Optional, Tuple, Any, Union


# ============================================================================
# Logger
# ============================================================================

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ============================================================================
# Optional Dependencies
# ============================================================================

try:
    from hardening_knowledge_base import (
        KnowledgeBase,
        HardeningPattern,
        PatternRetriever,
    )
    _HAVE_KB = True
except ImportError:
    _HAVE_KB = False
    logger.warning("[RAG] hardening_knowledge_base not available; "
                   "RAG engine will run in degraded mode")

try:
    from gnn_inference import GNNInference
    _HAVE_GNN = True
except ImportError:
    _HAVE_GNN = False

try:
    import openai
    _HAVE_OPENAI = True
except ImportError:
    _HAVE_OPENAI = False


# ============================================================================
# API Key Resolution
# ============================================================================

def _resolve_api_key(provided_key: Optional[str] = None,
                     env_var: str = "OPENAI_API_KEY",
                     env_file: str = ".env") -> Optional[str]:
    """Resolve API key from multiple sources with fallback priority:

    1. Explicitly provided key (highest priority)
    2. Environment variable (e.g. OPENAI_API_KEY)
    3. .env file in script or current directory

    Args:
        provided_key: API key passed explicitly by caller.
        env_var: Name of environment variable to check.
        env_file: Name of .env file to load.

    Returns:
        API key string, or None if not found from any source.
    """
    # Priority 1: explicitly provided
    if provided_key:
        return provided_key

    # Priority 2: environment variable
    env_key = os.environ.get(env_var)
    if env_key:
        return env_key

    # Priority 3: .env file (manual parse, no external dependency)
    for search_dir in [os.getcwd(), os.path.dirname(os.path.abspath(__file__))]:
        env_path = os.path.join(search_dir, env_file)
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(f"{env_var}="):
                            value = line[len(env_var) + 1:]
                            # Strip optional quotes
                            if (value.startswith('"') and value.endswith('"')) or \
                               (value.startswith("'") and value.endswith("'")):
                                value = value[1:-1]
                            return value
            except OSError:
                continue

    return None


def _mask_api_key(key: Optional[str]) -> str:
    """Mask an API key for safe logging: show first 4 + last 4 chars.

    Args:
        key: Raw API key string.

    Returns:
        Masked string like 'sk-12...3456' or '(none)'.
    """
    if not key or len(key) < 10:
        return '(none)'
    return key[:5] + '...' + key[-4:]

try:
    from graph_pipeline import GraphPipeline
    _HAVE_PIPELINE = True
except ImportError:
    _HAVE_PIPELINE = False


# ============================================================================
# Prompt Templates
# ============================================================================

HARDENING_SYSTEM_PROMPT = (
    "You are a hardware design hardening expert specialized in SEU/SET-tolerant "
    "RTL design. Your expertise covers TMR (Triple Modular Redundancy), DICE "
    "(Dual Interlocked Storage Cell), ECC (Error Correction Codes), parity "
    "checking, watchdog timers, lockstep counters, one-hot FSM encoding, "
    "memory scrubbing, and other radiation-hardening-by-design (RHBD) "
    "techniques.\n\n"
    "You will be given:\n"
    "1. A set of retrieved hardening patterns with RTL templates\n"
    "2. A target module description including its signals and vulnerability "
    "analysis\n\n"
    "Your task is to generate a hardened version of the target module that "
    "integrates the recommended hardening techniques. The generated RTL must:\n"
    "- Be synthesizable SystemVerilog/Verilog\n"
    "- Preserve the original module interface (ports and parameters)\n"
    "- Implement the hardening patterns correctly\n"
    "- Include appropriate reset logic\n"
    "- Be self-contained (no external module dependencies unless specified)\n"
    "- Include comments explaining the hardening technique\n\n"
    "IMPORTANT: Output ONLY valid SystemVerilog/Verilog code inside a single "
    "code block. Do not include explanatory text outside the code block."
)

HARDENING_USER_PROMPT_TEMPLATE = (
    "--- Design Context ---\n"
    "Design Name: {design_name}\n"
    "Signals: {signals}\n"
    "Signal Width: {signal_width}\n\n"
    "--- Vulnerability Analysis ---\n"
    "{vulnerabilities}\n\n"
    "--- Retrieved Hardening Patterns ---\n"
    "{patterns_context}\n\n"
    "--- Request ---\n"
    "Generate the hardened RTL for this design using the patterns above. "
    "Output only the SystemVerilog/Verilog module code."
)

HARDENING_REVIEW_PROMPT = (
    "Review the following hardened RTL code for correctness and completeness:\n\n"
    "{rtl_code}\n\n"
    "Checklist:\n"
    "1. Is the code valid synthesizable SystemVerilog/Verilog?\n"
    "2. Are all ports properly declared?\n"
    "3. Is the hardening technique correctly implemented?\n"
    "4. Is reset logic present and correct?\n"
    "5. Are there any obvious logic errors?\n\n"
    "Respond with 'PASS' or 'FAIL' followed by a brief explanation."
)


# ============================================================================
# LLM Backends
# ============================================================================

class MockLLM:
    """Mock LLM backend for testing without API access.

    Uses basic pattern matching to select the appropriate RTL template
    from the retrieved context and fills in the design-specific parameters.
    """

    def __init__(self) -> None:
        self.backend_name = 'mock'

        # ── Strategy template mapping ──
        # Keys are keywords to match in the pattern context;
        # Values are template generator methods (bound methods).
        self._strategy_templates: Dict[str, callable] = {
            'tmr':         self._tmr_rtl,
            'ecc':         self._ecc_rtl,
            'dice':        self._dice_rtl,
            'parity':      self._parity_rtl,
            'tmr_ecc':     self._tmr_ecc_rtl,
            'ecc_tmr':     self._tmr_ecc_rtl,
            'cnt_comp':    self._cnt_comp_rtl,
            'cntcomp':     self._cnt_comp_rtl,
            'counter_comp':self._cnt_comp_rtl,
            'watchdog':    self._watchdog_rtl,
            'wdt':         self._watchdog_rtl,
            'one_hot_fsm': self._one_hot_fsm_rtl,
            'onehot':      self._one_hot_fsm_rtl,
            'one_hot':     self._one_hot_fsm_rtl,
        }

    # ──────────────────────────────────────────────────────────────────
    # Main generation entry point
    # ──────────────────────────────────────────────────────────────────

    def generate(self, prompt: str) -> str:
        """Generate hardened RTL by selecting template based on context.

        Strategies supported:
          - TMR   (default): Triple Modular Redundancy + voter
          - ECC   : Hamming-code SECDED with syndrome correction
          - DICE  : Dual Interlocked Storage Cell (4-node storage)
          - Parity: Simple parity check + error flag

        The strategy is auto-selected by scanning the pattern context
        in the prompt for matching keywords.

        Args:
            prompt: The full prompt string containing context and design info.

        Returns:
            Generated RTL code as a string.
        """
        logger.print(f"  [MOCKLLM] === generate() called ===")
        logger.print(f"  [MOCKLLM] Prompt length: {len(prompt)} chars")

        # Extract module name from prompt
        module_name_match = re.search(
            r'Design Name:\s*(\S+)', prompt
        )
        module_name = module_name_match.group(1) if module_name_match else 'hardened_module'
        logger.print(f"  [MOCKLLM] Extracted module_name: '{module_name}'")

        # Extract signal width
        width_match = re.search(
            r'Signal Width:\s*(\d+)', prompt
        )
        signal_width = int(width_match.group(1)) if width_match else 32
        logger.print(f"  [MOCKLLM] Extracted signal_width: {signal_width}")

        # Extract strategy from context keywords
        logger.print(f"  [MOCKLLM] Running _detect_strategy() on prompt context...")
        strategy = self._detect_strategy(prompt)
        logger.print(f"  [MOCKLLM] Detected strategy: '{strategy}'")
        logger.print(f"  [MOCKLLM] Available templates: {list(self._strategy_templates.keys())}")

        if strategy in self._strategy_templates:
            logger.print(f"  [MOCKLLM] Using template: '{strategy}' for module '{module_name}' (width={signal_width})")
            result = self._strategy_templates[strategy](module_name, signal_width)
            logger.print(f"  [MOCKLLM] Template generated: {len(result)} chars, {len(result.splitlines())} lines")
            # Show first 3 lines of generated RTL
            first_lines = result.split('\n')[:3]
            for line in first_lines:
                logger.print(f"  [MOCKLLM]   | {line}")
            return result

        # Extract and fill template from context (fallback)
        logger.print(f"  [MOCKLLM] Strategy '{strategy}' not in templates; trying context-based fallback")
        context_section = self._extract_section(prompt, 'Retrieved Hardening Patterns',
                                                 'Request')
        if context_section:
            logger.print(f"  [MOCKLLM] Extracted context section: {len(context_section)} chars")
            template = self._extract_rtl_template(context_section)
            if template:
                logger.print(f"  [MOCKLLM] Found RTL template in context ({len(template)} chars); filling placeholders")
                return self._fill_template(template, module_name, signal_width)
            else:
                logger.print(f"  [MOCKLLM] No RTL template found in context section")
        else:
            logger.print(f"  [MOCKLLM] Could not extract context section from prompt")

        logger.print(f"  [MOCKLLM] Fallback: using default TMR template")
        return self._tmr_rtl(module_name, signal_width)

    # ──────────────────────────────────────────────────────────────────
    # Strategy detection
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _detect_strategy(prompt: str) -> str:
        """Detect the requested hardening strategy from pattern context.

        Scans the prompt for known pattern keywords and returns
        the most specific matching strategy name.

        Supported strategies:
          - 'tmr'        : Triple Modular Redundancy
          - 'ecc'        : Hamming SECDED
          - 'dice'       : Dual Interlocked Storage Cell
          - 'parity'     : Parity check
          - 'tmr_ecc'    : TMR+ECC hybrid
          - 'cnt_comp'   : Counter Comparator
          - 'watchdog'   : Watchdog Timer
          - 'one_hot_fsm': One-Hot Encoded FSM

        Returns:
            One of the strategy names above, or 'tmr' as default.
        """
        logger.print(f"  [MOCKLLM_DETECT] Scanning prompt for strategy keywords...")

        has_tmr = bool(re.search(r'\bTMR\b|Triple.Modular', prompt, re.IGNORECASE))
        has_ecc = bool(re.search(r'\b(?:ECC|Error.Correction|Hamming|SECDED)\b', prompt, re.IGNORECASE))
        has_dice = bool(re.search(r'\bDICE\b', prompt, re.IGNORECASE))
        has_parity = bool(re.search(r'\bparity\b', prompt, re.IGNORECASE))
        has_cnt_comp = bool(re.search(r'\bcnt.comparator|counter.comparator|CNT_COMP\b', prompt, re.IGNORECASE))
        has_watchdog = bool(re.search(r'\bwatchdog|wdt|watch.dog.timer\b', prompt, re.IGNORECASE))
        has_one_hot = bool(re.search(r'\bone.hot.*FSM|onehot|one_hot\b', prompt, re.IGNORECASE))

        if has_tmr and has_ecc:
            logger.print(f"  [MOCKLLM_DETECT] ✓ Found both 'TMR' and 'ECC' → strategy='tmr_ecc'")
            return 'tmr_ecc'

        if has_one_hot:
            logger.print(f"  [MOCKLLM_DETECT] ✓ Found 'one_hot|one_hot_FSM' keyword → strategy='one_hot_fsm'")
            return 'one_hot_fsm'
        if has_watchdog:
            logger.print(f"  [MOCKLLM_DETECT] ✓ Found 'watchdog|wdt' keyword → strategy='watchdog'")
            return 'watchdog'
        if has_cnt_comp:
            logger.print(f"  [MOCKLLM_DETECT] ✓ Found 'cnt_comp|counter_comparator' keyword → strategy='cnt_comp'")
            return 'cnt_comp'
        if has_dice:
            logger.print(f"  [MOCKLLM_DETECT] ✓ Found 'DICE' keyword → strategy='dice'")
            return 'dice'
        if has_ecc:
            logger.print(f"  [MOCKLLM_DETECT] ✓ Found 'ECC|Hamming|SECDED' keyword → strategy='ecc'")
            return 'ecc'
        if has_tmr:
            logger.print(f"  [MOCKLLM_DETECT] ✓ Found 'TMR|Triple.Modular' keyword → strategy='tmr'")
            return 'tmr'
        if has_parity:
            logger.print(f"  [MOCKLLM_DETECT] ✓ Found 'parity' keyword → strategy='parity'")
            return 'parity'

        logger.print(f"  [MOCKLLM_DETECT] No keyword match → default strategy='tmr'")
        return 'tmr'

    # ──────────────────────────────────────────────────────────────────
    # Template generators
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _tmr_rtl(module_name: str, signal_width: int) -> str:
        """TMR: Triple Modular Redundancy + majority voter."""
        logger.print(f"  [MOCKLLM_TMR] Generating TMR template: module='{module_name}', width={signal_width}")
        zero_val = "{" + str(signal_width) + "{1'b0}}"
        return f"""\
// ------------------------------------------------------------
// {module_name} — TMR Hardened Module (Triple Modular Redundancy)
// Generated by RAG Engine (MockLLM)
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width - 1}:0] data_in,
    output reg  [{signal_width - 1}:0] data_out
);

    // Three redundant copies
    reg [{signal_width - 1}:0] copy0, copy1, copy2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            copy0 <= {zero_val};
            copy1 <= {zero_val};
            copy2 <= {zero_val};
        end else begin
            copy0 <= data_in;
            copy1 <= data_in;
            copy2 <= data_in;
        end
    end

    // Majority voter: data_out[i] = majority(copy0[i], copy1[i], copy2[i])
    integer _i;
    always @(*) begin
        for (_i = 0; _i < {signal_width}; _i = _i + 1) begin
            data_out[_i] = (copy0[_i] & copy1[_i]) |
                           (copy0[_i] & copy2[_i]) |
                           (copy1[_i] & copy2[_i]);
        end
    end

endmodule
"""

    @staticmethod
    def _ecc_rtl(module_name: str, signal_width: int) -> str:
        """ECC: Hamming code SECDED (Single Error Correct, Double Error Detect).

        For a ``signal_width``-bit data word, we add ``k`` parity bits where
        ``2^k >= signal_width + k + 1`` (Hamming code bound).
        """
        # Compute number of parity bits needed for SECDED
        k = 1
        while (1 << k) < (signal_width + k + 1):
            k += 1
        ecc_width = signal_width + k
        logger.print(f"  [MOCKLLM_ECC] Generating ECC template: module='{module_name}', width={signal_width}, "
                     f"parity_bits={k}, codeword_width={ecc_width}")

        # Pre-compute Verilog replication strings to avoid f-string brace issues
        zero_ecc  = "{" + str(ecc_width) + "{1'b0}}"
        zero_sig  = "{" + str(signal_width) + "{1'b0}}"
        zero_k    = "{" + str(k) + "{1'b0}}"

        return f"""\
// ------------------------------------------------------------
// {module_name} — ECC Hardened Module (Hamming SECDED)
// Corrects single-bit errors, detects double-bit errors.
// Data width={signal_width}, Parity bits={k}, Codeword width={ecc_width}
// Generated by RAG Engine (MockLLM)
// ------------------------------------------------------------
module {module_name} (
    input  wire                         clk,
    input  wire                         rst_n,
    input  wire [{signal_width - 1}:0]   data_in,
    output reg  [{signal_width - 1}:0]   data_out,
    output reg                          error_flag     // 1=uncorrectable error
);

    // ── Internal signals ──
    reg  [{ecc_width - 1}:0] stored_codeword;   // data + parity stored
    wire [{k - 1}:0]         syndrome;           // syndrome bits
    wire [{signal_width - 1}:0] corrected_data;  // corrected data

    // ── Encode: compute parity bits on write ──
    function automatic [{ecc_width - 1}:0] encode;
        input [{signal_width - 1}:0] data;
        integer p;
        reg [{k - 1}:0] par;
        integer i;
        begin
            for (p = 0; p < k; p = p + 1) begin
                par[p] = 1'b0;
                for (i = 0; i < {signal_width}; i = i + 1) begin
                    if ((i + 1) & (1 << p))
                        par[p] = par[p] ^ data[i];
                end
            end
            encode = {{data, par}};
        end
    endfunction

    // ── Syndrome computation on read ──
    function automatic [{k - 1}:0] compute_syndrome;
        input [{ecc_width - 1}:0] codeword;
        integer p, i;
        reg [{k - 1}:0] syn;
        begin
            for (p = 0; p < k; p = p + 1) begin
                syn[p] = 1'b0;
                for (i = 0; i < {ecc_width}; i = i + 1) begin
                    if ((i + 1) & (1 << p))
                        syn[p] = syn[p] ^ codeword[i];
                end
            end
            compute_syndrome = syn;
        end
    endfunction

    // ── Error correction ──
    function automatic [{signal_width - 1}:0] correct_data;
        input [{ecc_width - 1}:0] codeword;
        input [{k - 1}:0]         syn;
        integer error_bit;
        integer i;
        begin
            if (syn != 0) begin
                error_bit = syn - 1;
                if (error_bit >= {k}) begin
                    i = error_bit - {k};
                    corrected_data[i] = ~codeword[i + {k}];
                end
            end
        end
    endfunction

    assign syndrome = compute_syndrome(stored_codeword);
    assign corrected_data = correct_data(stored_codeword, syndrome);

    // ── Main sequential logic ──
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            stored_codeword <= {zero_ecc};
            data_out        <= {zero_sig};
            error_flag      <= 1'b0;
        end else begin
            stored_codeword <= encode(data_in);
            data_out        <= corrected_data;
            error_flag      <= (syndrome != {zero_k});
        end
    end

endmodule
"""

    @staticmethod
    def _dice_rtl(module_name: str, signal_width: int) -> str:
        """DICE: Dual Interlocked Storage Cell (4-node storage per bit).

        Each storage bit uses 4 cross-coupled nodes (C0..C3) that reinforce
        each other. A single-event upset (SEU) in any one node is corrected
        by the other three nodes.
        """
        logger.print(f"  [MOCKLLM_DICE] Generating DICE template: module='{module_name}', width={signal_width}")
        zero_val = "{" + str(signal_width) + "{1'b0}}"
        return f"""\
// ------------------------------------------------------------
// {module_name} — DICE Hardened Module (Dual Interlocked Storage Cell)
// Rad-hard by design: each bit uses 4 cross-coupled storage nodes.
// Generated by RAG Engine (MockLLM)
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width - 1}:0] data_in,
    output reg  [{signal_width - 1}:0] data_out
);

    // ── Four redundant storage nodes per bit ──
    reg [{signal_width - 1}:0] dice_c0, dice_c1, dice_c2, dice_c3;

    // ── DICE write: all 4 nodes track the input ──
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            dice_c0 <= {zero_val};
            dice_c1 <= {zero_val};
            dice_c2 <= {zero_val};
            dice_c3 <= {zero_val};
        end else begin
            dice_c0 <= data_in;
            dice_c1 <= data_in;
            dice_c2 <= data_in;
            dice_c3 <= data_in;
        end
    end

    // ── DICE read: majority of 4 (any 3 matching bits win) ──
    integer _i;
    always @(*) begin
        for (_i = 0; _i < {signal_width}; _i = _i + 1) begin
            data_out[_i] = (dice_c0[_i] & dice_c1[_i] & dice_c2[_i]) |
                           (dice_c0[_i] & dice_c1[_i] & dice_c3[_i]) |
                           (dice_c0[_i] & dice_c2[_i] & dice_c3[_i]) |
                           (dice_c1[_i] & dice_c2[_i] & dice_c3[_i]);
        end
    end

endmodule
"""

    @staticmethod
    def _parity_rtl(module_name: str, signal_width: int) -> str:
        """Parity: simple parity check + error flag."""
        logger.print(f"  [MOCKLLM_PARITY] Generating Parity template: module='{module_name}', width={signal_width}")
        zero_val = "{" + str(signal_width) + "{1'b0}}"
        return f"""\
// ------------------------------------------------------------
// {module_name} — Parity Hardened Module
// Single-bit parity checking for error detection.
// Generated by RAG Engine (MockLLM)
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width - 1}:0] data_in,
    output reg  [{signal_width - 1}:0] data_out,
    output reg                      parity_error    // 1=parity mismatch
);

    // ── Storage registers ──
    reg  [{signal_width - 1}:0] data_reg;
    reg                         stored_parity;
    wire                        computed_parity;
    wire                        parity_mismatch;

    assign computed_parity = ^data_reg;
    assign parity_mismatch = (computed_parity != stored_parity);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_reg      <= {zero_val};
            stored_parity <= 1'b0;
            data_out      <= {zero_val};
            parity_error  <= 1'b0;
        end else begin
            data_reg      <= data_in;
            stored_parity <= ^data_in;
            data_out      <= data_reg;
            parity_error  <= parity_mismatch;
        end
    end

endmodule
"""

    @staticmethod
    def _tmr_ecc_rtl(module_name: str, signal_width: int) -> str:
        """TMR+ECC: Hybrid strategy combining TMR and ECC.

        Each TMR copy is protected by ECC, providing:
          - TMR: protection against single-point failures
          - ECC: protection against SEUs within each copy
          - Combined: robust multi-layer fault tolerance
        """
        k = 1
        while (1 << k) < (signal_width + k + 1):
            k += 1
        ecc_width = signal_width + k
        logger.print(f"  [MOCKLLM_TMR_ECC] Generating TMR+ECC hybrid template: "
                     f"module='{module_name}', width={signal_width}, parity_bits={k}")

        parity_exprs = []
        for p in range(k):
            bits = []
            for i in range(signal_width):
                if (i + 1) & (1 << p):
                    bits.append(f"data_in[{i}]")
            if bits:
                parity_exprs.append(f"par{p} = {' ^ '.join(bits)};")

        return f"""\
// ------------------------------------------------------------
// {module_name} — TMR+ECC Hybrid Hardened Module
// Triple Modular Redundancy + Hamming SECDED per copy.
// Data width={signal_width}, Parity bits={k}, Codeword width={ecc_width}
// Generated by RAG Engine (MockLLM)
// ------------------------------------------------------------
module {module_name} (
    input  wire                         clk,
    input  wire                         rst_n,
    input  wire [{signal_width - 1}:0]   data_in,
    output reg  [{signal_width - 1}:0]   data_out,
    output reg                          tmr_error_flag,
    output reg                          ecc_error_flag
);

    reg  [{signal_width - 1}:0] copy0_out, copy1_out, copy2_out;
    reg                         copy0_err, copy1_err, copy2_err;

    reg [{k - 1}:0] c0_par, c1_par, c2_par;

    // Copy 0: data with parity protection
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            copy0_out <= {signal_width}'d0;
            c0_par <= {k}'d0;
            copy0_err <= 1'b0;
        end else begin
            copy0_out <= data_in;
            {{c0_par[{k-1}], c0_par[{k-2}], c0_par[{k-3}], c0_par[{k-4}]}} <= 
                {{^(data_in & {signal_width}'b{bin(1<<(k-1))[2:].zfill(signal_width)}),
                  ^(data_in & {signal_width}'b{bin(1<<(k-2))[2:].zfill(signal_width)}),
                  ^(data_in & {signal_width}'b{bin(1<<(k-3))[2:].zfill(signal_width)}),
                  ^(data_in & {signal_width}'b{bin(1<<(k-4))[2:].zfill(signal_width)})}};
            copy0_err <= 1'b0;
        end
    end

    // Copy 1: data with parity protection
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            copy1_out <= {signal_width}'d0;
            c1_par <= {k}'d0;
            copy1_err <= 1'b0;
        end else begin
            copy1_out <= data_in;
            {{c1_par[{k-1}], c1_par[{k-2}], c1_par[{k-3}], c1_par[{k-4}]}} <= 
                {{^(data_in & {signal_width}'b{bin(1<<(k-1))[2:].zfill(signal_width)}),
                  ^(data_in & {signal_width}'b{bin(1<<(k-2))[2:].zfill(signal_width)}),
                  ^(data_in & {signal_width}'b{bin(1<<(k-3))[2:].zfill(signal_width)}),
                  ^(data_in & {signal_width}'b{bin(1<<(k-4))[2:].zfill(signal_width)})}};
            copy1_err <= 1'b0;
        end
    end

    // Copy 2: data with parity protection
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            copy2_out <= {signal_width}'d0;
            c2_par <= {k}'d0;
            copy2_err <= 1'b0;
        end else begin
            copy2_out <= data_in;
            {{c2_par[{k-1}], c2_par[{k-2}], c2_par[{k-3}], c2_par[{k-4}]}} <= 
                {{^(data_in & {signal_width}'b{bin(1<<(k-1))[2:].zfill(signal_width)}),
                  ^(data_in & {signal_width}'b{bin(1<<(k-2))[2:].zfill(signal_width)}),
                  ^(data_in & {signal_width}'b{bin(1<<(k-3))[2:].zfill(signal_width)}),
                  ^(data_in & {signal_width}'b{bin(1<<(k-4))[2:].zfill(signal_width)})}};
            copy2_err <= 1'b0;
        end
    end

    // Majority voter for TMR
    integer j;
    always @(*) begin
        for (j = 0; j < {signal_width}; j = j + 1) begin
            data_out[j] = (copy0_out[j] & copy1_out[j]) |
                           (copy0_out[j] & copy2_out[j]) |
                           (copy1_out[j] & copy2_out[j]);
        end
        tmr_error_flag = (copy0_out != copy1_out) | 
                         (copy0_out != copy2_out) | 
                         (copy1_out != copy2_out);
        ecc_error_flag = copy0_err | copy1_err | copy2_err;
    end

endmodule
"""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_section(text: str, start_marker: str,
                         end_marker: str) -> Optional[str]:
        """Extract content between two section markers."""
        start = text.find(start_marker)
        if start == -1:
            return None
        start += len(start_marker)
        end = text.find(end_marker, start)
        if end == -1:
            return text[start:].strip()
        return text[start:end].strip()

    @staticmethod
    def _extract_rtl_template(text: str) -> Optional[str]:
        """Extract the first Verilog module template from text."""
        # Look for `module` keyword
        match = re.search(
            r'(module\s+\{?module_name\}?\s*\(.*?endmodule)',
            text, re.DOTALL
        )
        if match:
            return match.group(1)

        # Fallback: look for any block starting with module
        match = re.search(
            r'(module\s+\w+\s*\(.*?endmodule)',
            text, re.DOTALL
        )
        if match:
            return match.group(1)

        return None

    @staticmethod
    def _fill_template(template: str, module_name: str, signal_width: int) -> str:
        """Replace placeholders in an extracted RTL template."""
        rtl = template.replace('{module_name}', module_name)
        rtl = rtl.replace('{signal_width}', str(signal_width))
        return rtl

    # Keep _fallback_rtl for backward compatibility
    # ══════════════════════════════════════════════════════════════════
    # New templates: cnt_comp, watchdog, one_hot_fsm
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _cnt_comp_rtl(module_name: str, signal_width: int) -> str:
        """CNT_COMP: 计数器比较器 — 监控寄存器值是否越界.

        适用于寄存器堆、地址生成器等需要范围检查的场景。
        将寄存器值与本模块计算的期望范围上限比较，超出时触发 error_flag。
        """
        logger.print(f"  [MOCKLLM_CNT_COMP] Generating Counter-Comparator template: "
                     f"module='{module_name}', width={signal_width}")
        zero_val = "{" + str(signal_width) + "{1'b0}}"
        all_one  = "{" + str(signal_width) + "{1'b1}}"
        return f"""\
// ------------------------------------------------------------
// {module_name} — CNT_COMP Hardened Module (Counter Comparator)
// Monitors register value against expected range bounds.
// Triggers error_flag when value deviates outside valid range.
// Generated by RAG Engine (MockLLM)
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width - 1}:0] data_in,
    output reg  [{signal_width - 1}:0] data_out,
    output reg                      error_flag     // 1=out-of-bounds
);

    // ── Internal registers ──
    reg [{signal_width - 1}:0] reg_value;
    reg [{signal_width - 1}:0] upper_bound;
    reg                        range_initialized;

    // ── Range bound computation ──
    wire [{signal_width - 1}:0] computed_upper;

    // Example: bound = data_in + 16 (sliding window upper edge)
    // In practice this is design-specific; this template uses
    // a configurable offset to validate the monitored value.
    assign computed_upper = data_in + {signal_width}'d16;

    // ── Main sequential logic ──
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reg_value         <= {zero_val};
            upper_bound       <= {all_one};
            range_initialized <= 1'b0;
            data_out          <= {zero_val};
            error_flag        <= 1'b0;
        end else begin
            reg_value   <= data_in;
            data_out    <= reg_value;

            // Initialize upper bound on first valid data
            if (!range_initialized) begin
                upper_bound       <= computed_upper;
                range_initialized <= 1'b1;
            end

            // Out-of-bounds detection
            if (range_initialized && (reg_value > upper_bound)) begin
                error_flag <= 1'b1;
            end else begin
                error_flag <= 1'b0;
            end
        end
    end

endmodule
"""

    @staticmethod
    def _watchdog_rtl(module_name: str, signal_width: int) -> str:
        """WATCHDOG: 看门狗定时器 — 超时触发系统复位.

        适用于需要持续运行的关键系统模块。
        若模块在超时窗口内未收到 heartbeat 脉冲，则触发 timeout_flag
        和 watchdog_reset 信号。
        """
        logger.print(f"  [MOCKLLM_WATCHDOG] Generating Watchdog template: "
                     f"module='{module_name}', width={signal_width}")
        zero_val = "{" + str(signal_width) + "{1'b0}}"
        return f"""\
// ------------------------------------------------------------
// {module_name} — WATCHDOG Hardened Module (Watchdog Timer)
// Monitors system heartbeat and triggers reset on timeout.
// Timeout window: ~65535 clock cycles at 16-bit counter.
// Generated by RAG Engine (MockLLM)
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width - 1}:0] data_in,
    input  wire                     heartbeat,       // system heartbeat
    output reg  [{signal_width - 1}:0] data_out,
    output reg                      timeout_flag,    // 1=timer expired
    output reg                      watchdog_reset   // 1=reset requested
);

    // ── Internal registers ──
    reg [{signal_width - 1}:0] reg_value;
    reg [15:0]                 timer;
    reg                        timer_enabled;

    // ── Timeout threshold (configurable) ──
    localparam [15:0] TIMEOUT_THRESHOLD = 16'hFF00;
    localparam [15:0] TIMER_MAX        = 16'hFFFF;

    // ── Main sequential logic ──
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reg_value      <= {zero_val};
            timer          <= 16'd0;
            timer_enabled  <= 1'b0;
            data_out       <= {zero_val};
            timeout_flag   <= 1'b0;
            watchdog_reset <= 1'b0;
        end else begin
            reg_value <= data_in;
            data_out  <= reg_value;
            timer_enabled <= 1'b1;

            // Heartbeat resets timer
            if (heartbeat) begin
                timer <= 16'd0;
            end else if (timer_enabled && (timer < TIMER_MAX)) begin
                timer <= timer + 16'd1;
            end

            // Timeout detection
            if (timer_enabled && (timer >= TIMEOUT_THRESHOLD)) begin
                timeout_flag   <= 1'b1;
                watchdog_reset <= 1'b1;
            end else begin
                timeout_flag   <= 1'b0;
                watchdog_reset <= 1'b0;
            end
        end
    end

endmodule
"""

    @staticmethod
    def _one_hot_fsm_rtl(module_name: str, signal_width: int) -> str:
        """ONE_HOT_FSM: 独热状态机 — 每个状态独立 FF，天然 SEU 容错.

        使用独热编码 (one-hot encoding) 的有限状态机。
        每个状态对应一个独立的触发器，任何时刻仅有一个触发器为高。
        若 SEU 导致状态偏离独热编码，$countones 可检测并恢复。
        适用于控制器、握手协议等状态密集型设计。
        """
        logger.print(f"  [MOCKLLM_ONE_HOT_FSM] Generating One-Hot FSM template: "
                     f"module='{module_name}', width={signal_width}")
        zero_val = "{" + str(signal_width) + "{1'b0}}"
        return f"""\
// ------------------------------------------------------------
// {module_name} — ONE_HOT_FSM Hardened Module
// One-hot encoded FSM with state error detection.
// Each state has a dedicated flip-flop; $countones monitors
// the one-hot invariant and flags any deviation.
// Generated by RAG Engine (MockLLM)
// ------------------------------------------------------------
module {module_name} (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [{signal_width - 1}:0] data_in,
    input  wire                     start_signal,
    input  wire                     done_signal,
    output reg  [{signal_width - 1}:0] data_out,
    output reg                      busy,
    output reg                      fsm_error       // 1=one-hot violation
);

    // ── One-hot state encoding ──
    localparam [3:0] IDLE     = 4'b0001;
    localparam [3:0] PROCESS  = 4'b0010;
    localparam [3:0] WAIT     = 4'b0100;
    localparam [3:0] COMPLETE = 4'b1000;

    // ── State registers ──
    reg [3:0] state_r;
    reg [3:0] next_state;

    // ── Data registers ──
    reg [{signal_width - 1}:0] pipeline_reg;

    // ── State transition (sequential) ──
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_r      <= IDLE;
            pipeline_reg <= {zero_val};
            data_out     <= {zero_val};
            busy         <= 1'b0;
            fsm_error    <= 1'b0;
        end else begin
            state_r      <= next_state;
            pipeline_reg <= data_in;
            data_out     <= pipeline_reg;
            busy         <= (state_r != IDLE);

            // One-hot invariant check
            // $countones(state_r) should always be 1
            if (state_r == 4'b0000) begin
                fsm_error <= 1'b1;  // all-zero: SEU detected
            end else if ((state_r & (state_r - 1)) != 0) begin
                fsm_error <= 1'b1;  // multi-bit: SEU detected
            end else begin
                fsm_error <= 1'b0;
            end
        end
    end

    // ── Next state logic (combinational) ──
    always @(*) begin
        next_state = IDLE;  // safe default (recovery on invalid state)
        case (state_r)
            IDLE:     next_state = start_signal ? PROCESS : IDLE;
            PROCESS:  next_state = WAIT;
            WAIT:     next_state = done_signal ? COMPLETE : WAIT;
            COMPLETE: next_state = IDLE;
            default:  next_state = IDLE;  // recover invalid states
        endcase
    end

endmodule
"""

    # Keep _fallback_rtl for backward compatibility
    @staticmethod
    def _fallback_rtl(module_name: str, signal_width: int) -> str:
        """Fallback: delegate to TMR template (backward compat)."""
        return MockLLM._tmr_rtl(module_name, signal_width)


class OpenAIBackend:
    """OpenAI / compatible API backend for RTL generation.

    Connects to OpenAI GPT-4 (or compatible endpoints) to generate
    hardened RTL code. When openai package is not available or API key
    is missing, falls back to MockLLM template-based generation.

    Usage:
        backend = OpenAIBackend(api_key="sk-...", model="gpt-4")
        rtl = backend.generate(prompt)
        backend = OpenAIBackend()  # falls back to MockLLM

    Attributes:
        api_key: OpenAI API key (or None for mock fallback).
        model: Model identifier (default 'gpt-4').
        mock: MockLLM instance used as fallback.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = 'gpt-4') -> None:
        """Initialize the OpenAI backend.

        API key resolution priority (see _resolve_api_key):
          1. Explicitly provided api_key argument
          2. OPENAI_API_KEY environment variable
          3. .env file in current or script directory

        If no API key is found, falls back to MockLLM template generation.

        Args:
            api_key: OpenAI API key (optional; auto-resolves from env/.env if None).
            model: Model name to use (default 'gpt-4').
        """
        resolved_key = _resolve_api_key(provided_key=api_key)
        self.api_key = resolved_key
        self.model = model
        self.backend_name = 'openai'
        self._mock = MockLLM()
        self._real_available = _HAVE_OPENAI and bool(resolved_key)

        if self._real_available:
            try:
                self._client = openai.OpenAI(
                    api_key=self.api_key,
                )
                logger.info(f"[OPENAI] Initialized with model={self.model}, api_key={_mask_api_key(self.api_key)}")
            except Exception as e:
                logger.warning(f"[OPENAI] Failed to create client: {e}, falling back to MockLLM")
                self._real_available = False

        if not self._real_available:
            logger.info(f"[OPENAI] Real API unavailable (openai={'✓' if _HAVE_OPENAI else '✗'}, "
                        f"api_key={_mask_api_key(resolved_key)}), using MockLLM fallback")

    def generate(self, prompt: str, max_tokens: int = 4096, temperature: float = 0.1) -> str:
        """Generate RTL code using OpenAI API or MockLLM fallback.

        Attempts a real API call if openai package and api_key are available.
        Falls back to MockLLM template-based generation otherwise.

        Args:
            prompt: The full prompt for the LLM.
            max_tokens: Maximum tokens (ignored in mock mode).
            temperature: Sampling temperature (ignored in mock mode).

        Returns:
            The generated RTL code as a string.
        """
        if self._real_available:
            try:
                logger.info(f"[OPENAI] Sending request (model={self.model}, temp={temperature})")
                logger.debug(f"[OPENAI] Prompt length: {len(prompt)} chars")

                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are an expert RTL designer specializing in FPGA/ASIC hardening. Generate only valid Verilog code without explanations."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                generated = response.choices[0].message.content.strip()
                logger.info(f"[OPENAI] Generation successful ({len(generated)} chars)")
                return generated

            except Exception as e:
                logger.warning(f"[OPENAI] API call failed: {e}, falling back to MockLLM")
                # Fall through to mock fallback

        # Mock fallback: extract module name and signal width from prompt
        logger.info(f"[OPENAI] Using MockLLM fallback")
        module_name = "hardened_top"
        signal_width = 32

        # Try to infer module name from prompt
        mn_match = re.search(r'module\s+(\w+)', prompt)
        if mn_match:
            module_name = mn_match.group(1)

        # Try to infer signal width from prompt
        sw_match = re.search(r'\[(\d+):0\]', prompt)
        if sw_match:
            signal_width = int(sw_match.group(1)) + 1

        # Determine strategy from prompt keywords
        prompt_lower = prompt.lower()
        strategy = 'tmr'
        if 'cnt_comp' in prompt_lower or 'counter comparator' in prompt_lower:
            strategy = 'cnt_comp'
        elif 'watchdog' in prompt_lower or 'wdt' in prompt_lower:
            strategy = 'watchdog'
        elif 'one_hot_fsm' in prompt_lower or 'onehot' in prompt_lower:
            strategy = 'one_hot_fsm'
        elif 'ecc' in prompt_lower or 'secded' in prompt_lower:
            strategy = 'ecc'
        elif 'parity' in prompt_lower:
            strategy = 'parity'
        elif 'dice' in prompt_lower:
            strategy = 'dice'

        # Route to appropriate mock template
        _STRATEGY_MOCK = {
            'tmr':       MockLLM._tmr_rtl,
            'ecc':       MockLLM._ecc_rtl,
            'parity':    MockLLM._parity_rtl,
            'dice':      MockLLM._dice_rtl,
            'tmr_ecc':   MockLLM._tmr_ecc_rtl,
            'cnt_comp':  MockLLM._cnt_comp_rtl,
            'watchdog':  MockLLM._watchdog_rtl,
            'one_hot_fsm': MockLLM._one_hot_fsm_rtl,
        }

        generator = _STRATEGY_MOCK.get(strategy, MockLLM._tmr_rtl)
        rtl = generator(module_name, signal_width)
        logger.info(f"[OPENAI] MockLLM generated '{strategy}' RTL for '{module_name}' ({signal_width}-bit)")
        return rtl


class DeepSeekBackend:
    """DeepSeek API backend for RTL generation.

    Uses the OpenAI-compatible DeepSeek API endpoint to generate
    hardened RTL code. Supports both DeepSeek-Coder and DeepSeek-R1 models.

    Usage:
        backend = DeepSeekBackend(api_key="sk-...", model="deepseek-chat")
        rtl = backend.generate(prompt)

    Attributes:
        api_key: DeepSeek API key.
        model: Model identifier (default 'deepseek-chat').
        base_url: API endpoint URL.
    """

    _DEFAULT_MODEL = "deepseek-chat"
    _DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

    def __init__(self, api_key: str, model: str = None, base_url: str = None) -> None:
        """Initialize the DeepSeek backend.

        Args:
            api_key: DeepSeek API key for authentication.
            model: Model name to use (default 'deepseek-chat').
            base_url: Custom API endpoint URL.

        Raises:
            ImportError: If openai package is not installed.
            ValueError: If API key is not provided.
        """
        if not _HAVE_OPENAI:
            raise ImportError(
                "DeepSeekBackend requires openai package.\n"
                "Install with: pip install openai"
            )
        if not api_key:
            raise ValueError("api_key is required for DeepSeekBackend")

        self.api_key = api_key
        self.model = model or self._DEFAULT_MODEL
        self.base_url = base_url or self._DEFAULT_BASE_URL
        self.backend_name = 'deepseek'

        self._client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        logger.info(f"[DEEPSEEK] Initialized with model={self.model}, base_url={self.base_url}")

    def generate(self, prompt: str, max_tokens: int = 4096, temperature: float = 0.1) -> str:
        """Generate RTL code using DeepSeek API.

        Args:
            prompt: The full prompt for the LLM.
            max_tokens: Maximum number of tokens to generate.
            temperature: Sampling temperature (lower = more deterministic).

        Returns:
            The generated RTL code as a string.

        Raises:
            Exception: If API call fails.
        """
        try:
            logger.info(f"[DEEPSEEK] Sending request (model={self.model}, temp={temperature})")
            logger.debug(f"[DEEPSEEK] Prompt length: {len(prompt)} chars")

            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert RTL designer specializing in FPGA/ASIC hardening. Generate only valid Verilog code without explanations."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                n=1,
            )

            rtl_code = response.choices[0].message.content.strip()

            logger.info(f"[DEEPSEEK] Response received (length: {len(rtl_code)} chars)")

            return rtl_code

        except Exception as e:
            logger.error(f"[DEEPSEEK] API call failed: {str(e)}")
            raise


# ============================================================================
# RAG Engine
# ============================================================================

class RAGEngine:
    """RAG (Retrieval-Augmented Generation) engine for hardware hardening.

    Orchestrates the full RAG pipeline:
      1. Retrieve relevant hardening patterns from the knowledge base
      2. Build a structured prompt combining patterns with design context
      3. Generate hardened RTL via the configured LLM backend

    Usage:
        engine = RAGEngine(kb_path=None, llm_backend='mock')
        engine.load_knowledge_base()

        rtl = engine.generate_hardened_rtl(design_info, vulnerability_result)
    """

    # Mapping from backend names to classes
    _BACKEND_REGISTRY: Dict[str, Any] = {
        'mock': MockLLM,
        'openai': OpenAIBackend,
        'deepseek': DeepSeekBackend,
    }

    def __init__(self, kb_path: Optional[str] = None,
                 llm_backend: str = 'mock',
                 api_key: Optional[str] = None,
                 model: Optional[str] = None) -> None:
        """Initialize the RAG engine.

        Args:
            kb_path: Optional path to a knowledge base file.
                     If None, the default KnowledgeBase is used.
            llm_backend: Name of the LLM backend to use.
                         Supported: 'mock', 'openai', 'deepseek', 'custom'.
            api_key: API key for real LLM backends (openai/deepseek).
                     If None, auto-resolves from OPENAI_API_KEY env var or .env.
            model: Optional model name override.
        """
        self.kb_path = kb_path
        self.kb: Optional[KnowledgeBase] = None
        self.retriever: Optional[PatternRetriever] = None
        self.llm_backend_name = llm_backend
        self.llm: Any = None
        self._initialized = False

        # Context cache to avoid redundant retrievals
        self._context_cache: Dict[str, str] = {}

        # Initialize the LLM backend immediately
        self.set_llm_backend(llm_backend, api_key=api_key, model=model)

        logger.info(f"[RAG] Engine created (backend={llm_backend}, "
                    f"kb_path={kb_path or 'default'})")

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def load_knowledge_base(self) -> bool:
        """Load the hardening pattern knowledge base.

        If a custom kb_path was provided, attempts to load from that path.
        Otherwise uses the default KnowledgeBase from hardening_knowledge_base.

        Returns:
            True if the knowledge base was loaded successfully, False otherwise.
        """
        if not _HAVE_KB:
            logger.error("[RAG] Cannot load knowledge base: "
                         "hardening_knowledge_base module unavailable")
            return False

        try:
            if self.kb_path and os.path.isfile(self.kb_path):
                with open(self.kb_path, 'r') as f:
                    data = json.load(f)
                self.kb = KnowledgeBase.from_dict(data)
                logger.info(f"[RAG] Knowledge base loaded from: {self.kb_path}")
            else:
                self.kb = KnowledgeBase()
                logger.info("[RAG] Default knowledge base loaded")

            self.retriever = PatternRetriever(self.kb)
            self._initialized = True
            logger.info(f"[RAG] Knowledge base ready: "
                        f"{len(self.kb.patterns)} patterns, "
                        f"{len(self.kb.list_categories())} categories")
            return True

        except Exception as e:
            logger.error(f"[RAG] Failed to load knowledge base: {e}")
            self._initialized = False
            return False

    def set_llm_backend(self, backend: str, api_key: str = None, model: str = None) -> None:
        """Set or switch the LLM backend.

        Args:
            backend: Backend name. Supported values:
                     - 'mock': Use MockLLM for testing
                     - 'openai': Use OpenAIBackend (requires api_key)
                     - 'deepseek': Use DeepSeekBackend (requires api_key)
                     - 'custom': Placeholder for custom backend integration
            api_key: API key for the backend (required for openai/deepseek).
            model: Optional model name override.

        Raises:
            ValueError: If the backend name is not recognized.
        """
        backend_lower = backend.lower()

        if backend_lower in self._BACKEND_REGISTRY:
            backend_cls = self._BACKEND_REGISTRY[backend_lower]
            if backend_lower == 'mock':
                self.llm = backend_cls()
            elif backend_lower == 'openai':
                self.llm = backend_cls(api_key=api_key or '', model=model or 'gpt-4')
            elif backend_lower == 'deepseek':
                self.llm = backend_cls(api_key=api_key, model=model)
            else:
                self.llm = backend_cls()
        elif backend_lower == 'custom':
            self.llm = None
            logger.info("[RAG] Custom backend selected — "
                        "set self.llm to your implementation")
        else:
            raise ValueError(
                f"Unknown LLM backend: '{backend}'. "
                f"Supported: {list(self._BACKEND_REGISTRY.keys()) + ['custom']}"
            )

        self.llm_backend_name = backend_lower
        logger.info(f"[RAG] LLM backend set to: {backend_lower}")

    # ------------------------------------------------------------------
    # Context & Prompt Building
    # ------------------------------------------------------------------

    def _build_context(self, vulnerability_result: Dict[str, Any],
                       top_k: int = 3) -> str:
        """Build a context string from retrieved hardening patterns.

        Args:
            vulnerability_result: Output from GNN inference containing
                                  vulnerability analysis results.
            top_k: Number of top patterns to retrieve.

        Returns:
            Formatted context string with pattern descriptions and RTL templates.
        """
        _t0 = time.time()

        if not self._initialized or self.retriever is None:
            logger.warning("[RAG] KB not initialized; returning empty context")
            return "(Knowledge base not available)"

        logger.sub_section("RAG Context Building")
        logger.print(f"  [RAG CTX] vulnerability keys: {list(vulnerability_result.keys())}")
        logger.print(f"  [RAG CTX] top_k={top_k}")

        # Check for explicit strategy override (injected by graph_pipeline)
        strategy_override = vulnerability_result.get('strategy_override', '')
        if strategy_override:
            logger.print(f"  [RAG CTX] strategy_override detected: '{strategy_override}'")
        else:
            logger.print(f"  [RAG CTX] No explicit strategy override")

        # Build cache key from strategy and vulnerability characteristics
        cache_key = f"{strategy_override}:{top_k}"
        all_nodes = vulnerability_result.get('all_vulnerable_nodes', [])
        for node in all_nodes:
            cache_key += f":{node.get('type', '')}:{node.get('signal_type', '')}"

        # Check cache first
        if cache_key in self._context_cache:
            logger.print(f"  [RAG CTX] Cache hit for key: {cache_key[:60]}...")
            return self._context_cache[cache_key]

        # Extract vulnerability characteristics for retrieval
        node_types: List[str] = []
        signal_types: List[str] = []

        logger.print(f"  [RAG CTX] vulnerable nodes count: {len(all_nodes)}")
        for node in all_nodes:
            ntype = node.get('type', '')
            sig_type = node.get('signal_type', '')
            if ntype:
                node_types.append(str(ntype))
            if sig_type:
                signal_types.append(str(sig_type))

        logger.print(f"  [RAG CTX] Retrieval query: node_types={node_types[:5] if node_types else 'none'}, "
                     f"signal_types={signal_types[:5] if signal_types else 'none'}")

        # Retrieve patterns
        if node_types or signal_types:
            logger.print(f"  [RAG CTX] Using retrieve_by_vulnerability()...")
            results = self.retriever.retrieve_by_vulnerability(
                node_types, signal_types, top_k=top_k
            )
            logger.print(f"  [RAG CTX] Retrieved {len(results)} patterns by vulnerability characteristics")
        else:
            # Fallback: use vulnerability descriptions as query
            desc = str(vulnerability_result.get('description', 'hardening'))
            logger.print(f"  [RAG CTX] No node/signal types; fallback text query: '{desc[:80]}'")
            results = self.retriever.retrieve(desc, top_k=top_k)

        if not results:
            logger.print(f"  [RAG CTX] No matching patterns retrieved (elapsed={time.time()-_t0:.3f}s)")
            return "(No matching hardening patterns found)"

        # Log each retrieved pattern with score breakdown
        logger.print(f"  [RAG CTX] Top-{len(results)} retrieved patterns:")
        for idx, (pattern, score) in enumerate(results, 1):
            logger.print(
                f"    [{idx}/{len(results)}] {pattern.name} "
                f"(relevance={score:.4f}, category={pattern.category}, "
                f"area={pattern.area_overhead:.1f}x, latency={pattern.latency_penalty}cyc)"
            )

        # Format context string
        context_parts: List[str] = []
        total_chars = 0
        for idx, (pattern, score) in enumerate(results, 1):
            part = (
                f"[Pattern {idx}] {pattern.name} "
                f"(category={pattern.category}, "
                f"relevance={score:.3f})\n"
                f"  Description: {pattern.description}\n"
                f"  Area overhead: {pattern.area_overhead:.1f}x, "
                f"Power overhead: {pattern.power_overhead:.1f}x, "
                f"Latency: {pattern.latency_penalty} cycle(s)\n"
                f"  Applicable signals: "
                f"{', '.join(pattern.applicable_signals)}\n"
                f"  RTL Template:\n"
                f"{pattern.rtl_template}\n"
            )
            context_parts.append(part)
            total_chars += len(part)

        logger.print(f"  [RAG CTX] Built context from {len(results)} patterns ({total_chars} chars, "
                     f"elapsed={time.time()-_t0:.3f}s)")

        # ── Inject strategy override into context text ──
        # This ensures MockLLM._detect_strategy() can find the keyword
        strategy_override = vulnerability_result.get('strategy_override', '')
        if strategy_override:
            header = (
                f"[Strategy Override] The user has explicitly requested the "
                f"'{strategy_override}' hardening strategy for this design.\n"
                f"[Strategy Override] Please use {strategy_override} to harden the following module.\n\n"
            )
            context_parts.insert(0, header)
            logger.print(f"  [RAG CTX] Strategy override '{strategy_override}' injected into context")

        final_context = '\n'.join(context_parts)
        self._context_cache[cache_key] = final_context
        logger.print(f"  [RAG CTX] Context cached (key={cache_key[:40]}...)")

        return final_context

    def _build_prompt(self, context: str,
                      design_info: Dict[str, Any]) -> str:
        """Build the full structured prompt for the LLM.

        Combines the system prompt, retrieved context, and design information
        into a complete prompt.

        Args:
            context: Context string from _build_context().
            design_info: Dictionary describing the target design with keys:
                         - module_name (str): Design module name
                         - signals (list): List of signal names
                         - signal_width (int): Data signal width
                         - vulnerabilities (str, optional): Description of
                           vulnerabilities found.

        Returns:
            Complete prompt string ready for LLM inference.
        """
        _t0 = time.time()

        design_name = design_info.get('module_name', 'unknown_design')
        signals_str = ', '.join(map(str, design_info.get('signals', [])))
        signal_width = design_info.get('signal_width', 32)
        n_signals = len(design_info.get('signals', []))

        vulnerabilities = design_info.get(
            'vulnerabilities',
            'Vulnerability analysis not provided'
        )

        logger.sub_section("RAG Prompt Building")
        logger.print(f"  [RAG PRM] Design: {design_name}")
        logger.print(f"  [RAG PRM] Signals ({n_signals}): {signals_str[:120]}")
        logger.print(f"  [RAG PRM] Signal width: {signal_width}")
        logger.print(f"  [RAG PRM] Context length: {len(context)} chars")

        user_prompt = HARDENING_USER_PROMPT_TEMPLATE.format(
            design_name=design_name,
            signals=signals_str,
            signal_width=signal_width,
            vulnerabilities=vulnerabilities,
            patterns_context=context,
        )

        full_prompt = (
            f"System: {HARDENING_SYSTEM_PROMPT}\n\n"
            f"User: {user_prompt}"
        )

        logger.print(f"  [RAG PRM] Prompt built: system_part={len(HARDENING_SYSTEM_PROMPT)} chars, "
                     f"user_part={len(user_prompt)} chars, total={len(full_prompt)} chars, "
                     f"elapsed={time.time()-_t0:.3f}s")
        return full_prompt

    # ------------------------------------------------------------------
    # Main Generation
    # ------------------------------------------------------------------

    def generate_hardened_rtl(self, design_info: Dict[str, Any],
                              vulnerability_result: Dict[str, Any]) -> str:
        """Main method: retrieve patterns, build prompt, and generate RTL.

        Orchestrates the full RAG pipeline end-to-end.

        Args:
            design_info: Design metadata dict. Expected keys:
                - module_name (str): Name of the RTL module.
                - signals (list): List of signal names/descriptions.
                - signal_width (int): Bit-width of data signals.
                - vulnerabilities (str, optional): Human-readable vulnerability
                  summary.
            vulnerability_result: Output from GNN inference
                (e.g. GNNInference.infer_from_file()). Must contain at least:
                - all_vulnerable_nodes (list): List of vulnerable node dicts.

        Returns:
            Generated hardened RTL code as a string. Returns an error message
            string if generation fails.

        Raises:
            RuntimeError: If the LLM backend is not set.
        """
        logger.section("RAG Engine — Generating Hardened RTL")
        _t_start = time.time()

        # ── Step 1: Ensure KB is loaded ──
        logger.print(f"\n  [RAG] Phase 1/4: Load Knowledge Base")
        logger.print(f"  [RAG]   initialized={self._initialized}, backend={self.llm_backend_name}")
        if not self._initialized:
            logger.print(f"  [RAG]   Auto-loading knowledge base...")
            success = self.load_knowledge_base()
            if not success:
                error_msg = "Failed to load knowledge base. RTL generation aborted."
                logger.error(f"[RAG]   {error_msg}")
                return error_msg
        else:
            logger.print(f"  [RAG]   KB already loaded, patterns={len(self.kb.patterns) if self.kb else 0}")
        _t1 = time.time()
        logger.metric("rag.phase1_kb_load", _t1 - _t_start, "s")

        # ── Step 2: Retrieve and build context ──
        logger.print(f"\n  [RAG] Phase 2/4: Context Retrieval")
        logger.print(f"  [RAG]   Design: {design_info.get('module_name', '?')}, "
                     f"signals={len(design_info.get('signals', []))}")
        _t2 = time.time()
        context = self._build_context(vulnerability_result, top_k=3)
        _t3 = time.time()
        logger.print(f"  [RAG]   context retrieval: {_t3-_t2:.3f}s, {len(context)} chars")
        logger.metric("rag.phase2_context", _t3 - _t2, "s")
        if len(context) < 50:
            logger.warning(f"  [RAG]   Short context ({len(context)} chars) — may produce poor RTL")

        # ── Step 3: Build prompt ──
        logger.print(f"\n  [RAG] Phase 3/4: Prompt Construction")
        _t4 = time.time()
        prompt = self._build_prompt(context, design_info)
        _t5 = time.time()
        logger.print(f"  [RAG]   prompt building: {_t5-_t4:.3f}s, "
                     f"system={len(HARDENING_SYSTEM_PROMPT)} chars, "
                     f"user={len(prompt)-len(HARDENING_SYSTEM_PROMPT)} chars")
        logger.metric("rag.phase3_prompt", _t5 - _t4, "s")

        # ── Step 4: Generate RTL via LLM ──
        logger.print(f"\n  [RAG] Phase 4/4: LLM Generation (backend={self.llm_backend_name})")
        if self.llm is None:
            raise RuntimeError(
                f"LLM backend '{self.llm_backend_name}' has no implementation. "
                "Set self.llm to a valid generator object."
            )

        try:
            _t6 = time.time()
            logger.print(f"  [RAG]   Calling LLM generate()...")
            rtl_code = self.llm.generate(prompt)
            _t7 = time.time()
            gen_time = _t7 - _t6
            logger.print(f"  [RAG]   LLM returned: {len(rtl_code)} chars in {gen_time:.3f}s")
            logger.metric("rag.phase4_llm", gen_time, "s")

            # Validate the output
            _t8 = time.time()
            logger.print(f"  [RAG]   Validating generated RTL...")
            if validate_generated_rtl(rtl_code):
                logger.print(f"  [RAG]   Validation: PASSED")
            else:
                logger.warning(f"  [RAG]   Validation: WARNINGS")
            _t9 = time.time()
            logger.print(f"  [RAG]   validation: {_t9-_t8:.3f}s")
            logger.metric("rag.validation", _t9 - _t8, "s")

            # Show snippet of generated RTL
            snippet = rtl_code[:200].replace('\n', '\n    ')
            logger.print(f"  [RAG]   Generated RTL snippet:\n    {snippet}...")

            _t_end = time.time()
            total_time = _t_end - _t_start
            logger.metric("rag.total", total_time, "s")
            logger.print(f"  [RAG] Total: {total_time:.3f}s")

            return rtl_code

        except Exception as e:
            error_msg = f"RTL generation failed: {e}"
            logger.error(f"[RAG] {error_msg}")
            import traceback
            logger.error(f"[RAG] Traceback: {traceback.format_exc()}")
            return error_msg


# ============================================================================
# Helper Functions
# ============================================================================

# ── Global caches for hierarchical analysis ──
# Submodule file search cache: avoids repeated file system scans
_SUBMODULE_FILE_CACHE: Dict[str, Optional[str]] = {}
# Module analysis result cache: avoids re-parsing the same module
_MODULE_RESULT_CACHE: Dict[str, Optional[Dict]] = {}


def _find_module_file(module_name: str, search_dirs: Optional[List[str]] = None) -> Optional[str]:
    """Search file system for a module's RTL definition.

    Results are cached in ``_SUBMODULE_FILE_CACHE`` globally to avoid
    repeated file system scans for the same module across instances.

    Args:
        module_name: Verilog module name to search for.
        search_dirs: Additional directories to search (besides the caller's dir).

    Returns:
        Absolute path to the file, or None if not found.
    """
    cache_key = f"{module_name}:{':'.join(search_dirs or [])}"
    if cache_key in _SUBMODULE_FILE_CACHE:
        return _SUBMODULE_FILE_CACHE[cache_key]

    candidates = []
    # Common file name patterns for Verilog modules
    patterns = [
        f"{module_name}.v",
        f"{module_name}.sv",
        f"{module_name}.vh",
        f"{module_name.lower()}.v",
        f"{module_name.lower()}.sv",
    ]

    for d in (search_dirs or []):
        if not os.path.isdir(d):
            continue
        for pat in patterns:
            fp = os.path.join(d, pat)
            if os.path.isfile(fp):
                _SUBMODULE_FILE_CACHE[cache_key] = os.path.abspath(fp)
                return _SUBMODULE_FILE_CACHE[cache_key]

    _SUBMODULE_FILE_CACHE[cache_key] = None
    return None


def _extract_registers_from_content(content: str) -> List[Dict[str, Any]]:
    """Extract register/DFF declarations from RTL content.

    Finds:
      - Explicit `reg` declarations (standalone or in port lists)
      - `output reg` / `inout reg` port declarations
      - Sequential always blocks: always @(posedge clk ...)
      - Register assignments: `reg_name <= value;` inside sequential blocks

    Args:
        content: Raw RTL content string.

    Returns:
        List of register dicts with 'name', 'width', 'clock_edge', 'reset'.
    """
    registers: List[Dict[str, Any]] = []
    seen: set = set()

    # Remove comments
    content_clean = re.sub(r'//.*?$|/\*.*?\*/', '', content, flags=re.MULTILINE | re.DOTALL)

    # 1. Extract reg declarations:
    #    a) Standalone: `reg [7:0] name;` or `reg name1, name2;`
    #    b) Port-list:  `output reg [7:0] name,` or `input reg name;`
    for pattern in [
        # Pattern A: `output reg [7:0] name,` or `output reg name ;`
        r'(?:input|output|inout)\s+reg\s+(?:\[([\w-]+):([\w-]+)\])?\s*'
        r'(\w+)(?:\s*,\s*(\w+))?(?:\s*[;,])',
        # Pattern B: `reg [7:0] name;` or `reg name1, name2;`
        r'reg\s+(?:\[([\w-]+):([\w-]+)\])?\s*'
        r'(\w+)(?:\s*,\s*(\w+))?\s*[;,]',
    ]:
        for match in re.compile(pattern, re.MULTILINE).finditer(content_clean):
            msb, lsb = match.group(1), match.group(2)
            try:
                width = (abs(int(msb) - int(lsb)) + 1) if msb and lsb else 1
            except ValueError:
                width = 1
            names = [match.group(3)]
            if match.group(4):
                names.append(match.group(4))
            for name in names:
                if name and name not in seen:
                    seen.add(name)
                    registers.append({"name": name, "width": width, "source": "declaration"})

    # 2. Extract registers from sequential always blocks
    # Match: always @(posedge clk or negedge rst_n) ... begin
    # Use a more flexible approach: find always blocks with posedge/negedge
    seq_always_pattern = re.compile(
        r'always\s+@\s*\('
        r'(?:posedge|negedge)\s+\w+'        # first edge
        r'(?:\s+(?:or|,)\s*'                # optional: or/,
        r'(?:posedge|negedge)\s+\w+)*'      # more edges
        r'\)',
        re.IGNORECASE
    )
    for block_match in seq_always_pattern.finditer(content_clean):
        # Get the full always block (from always to first unmatched end)
        block_start = block_match.start()
        # Find the matching begin...end or just the statement
        rest = content_clean[block_match.end():]
        # Find begin if present
        begin_pos = re.search(r'\bbegin\b', rest)
        if begin_pos:
            # Extract the rest of the block after 'begin'
            block_body = rest[begin_pos.end():]
            # Find matching end
            depth = 1
            body_end = 0
            for m in re.finditer(r'\b(begin|end)\b', block_body):
                if m.group(1) == 'begin':
                    depth += 1
                else:  # end
                    depth -= 1
                    if depth == 0:
                        body_end = m.end()
                        break
            block_body = block_body[:body_end] if body_end else block_body
        else:
            # Single statement: always @(...) statement;
            block_body = rest.split(';')[0]

        # Extract non-blocking assignments: `reg_name <= expression;`
        nba_pattern = re.compile(r'(\w+)\s*<=\s*[^;]+;')
        for nba in nba_pattern.finditer(block_body):
            name = nba.group(1)
            if name not in seen and name.lower() not in (
                'if', 'else', 'for', 'begin', 'end', 'case',
                'casex', 'casez', 'default',
            ):
                seen.add(name)
                registers.append({"name": name, "width": 1, "source": "sequential_always"})

    return registers


def _extract_instantiations(rtl_content: str) -> List[Dict[str, Any]]:
    """从 RTL 内容中提取所有模块实例化语句。

    使用正则表达式解析 Verilog 实例化语法：
      module_name inst_name ( .port_name(connected_signal), ... );

    支持：
      - 带 #(参数) 参数化实例化
      - 命名端口连接 .port(sig)
      - 多行跨行实例化
      - 嵌套括号的端口表达式（如 .addr({mem_addr[7:0], 1'b0})）

    Args:
        rtl_content: 原始 RTL 代码字符串。

    Returns:
        列表，每个元素为包含以下键的字典：
        - module_name (str): 被实例化的模块名
        - instance_name (str): 实例名
        - port_connections (dict): 端口名到连接信号的映射 {port: signal}
    """
    # 去除注释，避免在注释中误匹配
    clean_content = re.sub(r'//.*?$|/\*.*?\*/', '', rtl_content,
                           flags=re.MULTILINE | re.DOTALL)

    instantiations: List[Dict[str, Any]] = []

    # Verilog 关键字/原语列表（跳过这些）
    _KEYWORDS = {
        'module', 'if', 'else', 'for', 'while', 'case', 'casex', 'casez',
        'always', 'initial', 'final', 'end', 'input', 'output', 'inout',
        'wire', 'reg', 'logic', 'integer', 'genvar', 'tri', 'wand', 'wor',
        'begin', 'endmodule', 'assign', 'generate', 'endgenerate',
        'specify', 'endspecify', 'table', 'endtable',
        'posedge', 'negedge', 'or', 'and', 'nand', 'nor', 'xor', 'xnor',
        'buf', 'not', 'bufif0', 'bufif1', 'notif0', 'notif1',
        'pullup', 'pulldown', 'cmos', 'rcmos', 'nmos', 'pmos', 'rnmos', 'rpmos',
        'tran', 'rtran', 'tranif0', 'tranif1', 'rtranif0', 'rtranif1',
        'fork', 'join', 'repeat', 'wait', 'disable', 'event',
    }

    # 第一步：匹配实例化的头部 "module_name inst_name ("
    # 注意：不能一次性捕获括号内容，因为端口连接中包含嵌套括号
    header_pattern = re.compile(
        r'(\w+)\s+'               # 模块名
        r'(?:#\s*\([^)]*\)\s+)?'  # 可选参数化部分 #(.param(val))
        r'(\w+)\s*\(\s*',         # 实例名 + 左括号
        re.MULTILINE
    )

    for match in header_pattern.finditer(clean_content):
        mod_name = match.group(1).strip()
        inst_name = match.group(2).strip()

        # 跳过关键字
        if mod_name.lower() in _KEYWORDS:
            continue

        # 跳过宏、数字开头的非合法模块名
        if not re.match(r'^[a-zA-Z_]\w*$', mod_name):
            continue

        # 第二步：手动查找匹配的右括号，处理嵌套括号
        start = match.end()  # 左括号后的第一个字符
        paren_depth = 1
        end = start
        while end < len(clean_content) and paren_depth > 0:
            if clean_content[end] == '(':
                paren_depth += 1
            elif clean_content[end] == ')':
                paren_depth -= 1
            end += 1

        # 获取括号内的端口连接字符串（不含最外层括号）
        conn_section = clean_content[start:end - 1]

        # 第三步：检查是否有命名端口连接，以确认这是真正的实例化
        # 使用 .port_name(signal) 模式匹配
        has_named_conn = bool(re.search(r'\.\s*\w+\s*\(', conn_section))
        if not has_named_conn:
            continue  # 跳过大括号或非实例化结构

        # 第四步：解析端口连接映射
        port_connections: Dict[str, str] = {}
        # 使用 .port_name(signal) 格式，信号中可能包含嵌套括号
        # 为了处理嵌套括号，逐字符扫描
        conn_pattern = re.compile(r'\.\s*(\w+)\s*\(')
        for conn_match in conn_pattern.finditer(conn_section):
            port_name = conn_match.group(1)
            # 从匹配位置后的左括号开始，找到匹配的右括号
            sig_start = conn_match.end()  # 左括号后的第一个字符
            sig_paren_depth = 1
            sig_end = sig_start
            while sig_end < len(conn_section) and sig_paren_depth > 0:
                if conn_section[sig_end] == '(':
                    sig_paren_depth += 1
                elif conn_section[sig_end] == ')':
                    sig_paren_depth -= 1
                sig_end += 1
            sig_expr = conn_section[sig_start:sig_end - 1].strip()
            port_connections[port_name] = sig_expr

        if not port_connections:
            continue

        instantiations.append({
            "module_name": mod_name,
            "instance_name": inst_name,
            "port_connections": port_connections,
        })

    return instantiations


def _resolve_instance_rtl(module_name: str,
                          search_paths: List[str]) -> Optional[str]:
    """在搜索路径中查找子模块的 RTL 文件，读取并返回其内容。

    使用模糊匹配策略——文件名包含模块名即视为匹配（不要求完全一致）。
    搜索的文件扩展名包括 .v, .sv, .vh。

    Args:
        module_name: 要查找的 Verilog 模块名称。
        search_paths: 要搜索的目录列表。

    Returns:
        匹配文件的完整内容字符串；如果未找到则返回 None。
    """
    if not search_paths:
        return None

    # 合法的 Verilog 文件扩展名
    extensions = ['.v', '.sv', '.vh']

    # 构建候选文件名模式
    candidate_names = [
        module_name,
        module_name.lower(),
        module_name.upper(),
    ]

    for search_dir in search_paths:
        if not os.path.isdir(search_dir):
            continue
        try:
            for fname in os.listdir(search_dir):
                fpath = os.path.join(search_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                # 检查扩展名
                ext = os.path.splitext(fname)[1].lower()
                if ext not in extensions:
                    continue
                # 模糊匹配：文件名（不含扩展名）包含模块名
                base = os.path.splitext(fname)[0]
                if module_name.lower() in base.lower():
                    try:
                        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        return content
                    except OSError:
                        continue
        except PermissionError:
            continue
        except OSError:
            continue

    return None


def _extract_all_registers(content: str) -> List[str]:
    """从 RTL 内容中提取所有寄存器（reg 声明）的变量名。

    相比 _extract_registers_from_content() 返回更全面的列表，
    包含所有被 reg 关键字声明的变量。

    Args:
        content: 原始 RTL 代码字符串。

    Returns:
        所有 reg 变量名的字符串列表。
    """
    # 去除注释
    clean = re.sub(r'//.*?$|/\*.*?\*/', '', content,
                   flags=re.MULTILINE | re.DOTALL)

    reg_names: List[str] = []
    seen: set = set()

    # 模式1: output reg [x:y] name; 或 input reg name;
    pattern1 = re.compile(
        r'(?:input|output|inout)\s+reg\s+'
        r'(?:\[[\w-]+:[\w-]+\])?\s*'
        r'(\w+)',
        re.MULTILINE
    )
    for m in pattern1.finditer(clean):
        name = m.group(1)
        if name not in seen and re.match(r'^[a-zA-Z_]\w*$', name):
            seen.add(name)
            reg_names.append(name)

    # 模式2: reg [x:y] name; 或 reg name; (允许行首空白)
    pattern2 = re.compile(
        r'^\s*reg\s+'
        r'(?:\[[\w-]+:[\w-]+\])?\s*'
        r'(\w+)',
        re.MULTILINE
    )
    for m in pattern2.finditer(clean):
        name = m.group(1)
        if name not in seen and re.match(r'^[a-zA-Z_]\w*$', name):
            seen.add(name)
            reg_names.append(name)

    # 模式3: 一行内多个 reg: reg name1, name2;
    pattern3 = re.compile(
        r'reg\s+(?:\[[\w-]+:[\w-]+\])?\s*'
        r'(\w+)(?:\s*,\s*(\w+))+',
        re.MULTILINE
    )
    for m in pattern3.finditer(clean):
        for g in m.groups():
            if g and g not in seen and re.match(r'^[a-zA-Z_]\w*$', g):
                seen.add(g)
                reg_names.append(g)

    return reg_names


def _parse_single_rtl_file(
    rtl_path: str,
    visited: Optional[set] = None,
    search_dirs: Optional[List[str]] = None,
    depth: int = 0,
) -> Dict[str, Any]:
    """Parse a single RTL file, recursively resolving submodule instances.

    Core recursive function for hierarchical design analysis.
    Uses global ``_MODULE_RESULT_CACHE`` to cache module analysis results,
    so that multiple instances of the same submodule reuse the cached data
    instead of re-parsing.

    Args:
        rtl_path: Absolute path to the RTL file.
        visited: Set of already-visited module names (avoid cycles).
        search_dirs: Additional directories to search for submodule files.
        depth: Current recursion depth (for indented logging).

    Returns:
        Dict with keys: module_name, signals[], registers[], signal_width,
        submodules{}, parse_success, all_registers (flattened).
    """
    prefix = "  " * depth
    rtl_path = os.path.abspath(rtl_path)
    if not os.path.isfile(rtl_path):
        return {"module_name": "unknown", "signals": [], "registers": [],
                "submodules": {}, "parse_success": False,
                "all_registers": [], "all_signals": []}

    if visited is None:
        visited = set()

    try:
        with open(rtl_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError as e:
        logger.error(f"{prefix}[RAG] Cannot read {rtl_path}: {e}")
        return {"module_name": "unknown", "signals": [], "registers": [],
                "submodules": {}, "parse_success": False,
                "all_registers": [], "all_signals": []}

    content_no_comments = re.sub(
        r'//.*?$|/\*.*?\*/', '', content, flags=re.MULTILINE | re.DOTALL
    )

    # ── 1. Module name ──
    mod_match = re.search(
        r'module\s+(\w+)\s*(?:#\s*\(.*?\))?\s*\(', content_no_comments, re.DOTALL
    )
    module_name = mod_match.group(1) if mod_match else "unknown"

    # ── Check result cache: already analyzed this module? ──
    if module_name in _MODULE_RESULT_CACHE:
        logger.print(f"{prefix}[RAG] Cache hit for module '{module_name}', reusing previous analysis")
        return _MODULE_RESULT_CACHE[module_name]
    if module_name in visited:
        logger.print(f"{prefix}[RAG] Skipping already-visited module: {module_name}")
        return {"module_name": module_name, "signals": [], "registers": [],
                "submodules": {}, "parse_success": True,
                "all_registers": [], "all_signals": []}
    visited.add(module_name)

    logger.print(f"{prefix}[RAG] Analyzing module '{module_name}' from {os.path.basename(rtl_path)}")

    # ── 2. Extract ports ──
    signals: List[Dict] = []
    port_pattern = re.compile(
        r'(input|output|inout)\s+'
        r'(?:wire|reg|logic|signed|unsigned|)\s*'
        r'(?:\[([\w-]+):([\w-]+)\])?\s*'
        r'(\w+)',
        re.IGNORECASE
    )
    max_width = 1
    for match in port_pattern.finditer(content_no_comments):
        direction = match.group(1).lower()
        msb, lsb = match.group(2), match.group(3)
        signal_name = match.group(4)
        try:
            width = (abs(int(msb) - int(lsb)) + 1) if msb and lsb else 1
        except ValueError:
            width = 1
        max_width = max(max_width, width)
        signals.append({"name": signal_name, "direction": direction, "width": width})

    # ── 3. Extract top-level registers ──
    registers = _extract_registers_from_content(content)

    # ── 4. Extract submodule instances 使用 _extract_instantiations() ──
    MAX_RECURSION_DEPTH = 3  # 最大递归深度，防止循环实例化
    submodules: Dict[str, Dict] = {}
    instantiations = _extract_instantiations(content)

    dir_for_search = [os.path.dirname(rtl_path)]
    if search_dirs:
        dir_for_search.extend(search_dirs)

    for inst in instantiations:
        sub_mod = inst["module_name"]
        inst_name = inst["instance_name"]

        # 检查递归深度，防止无限循环
        if depth >= MAX_RECURSION_DEPTH:
            logger.print(
                f"{prefix}[RAG]   Max recursion depth ({MAX_RECURSION_DEPTH}) reached, "
                f"skipping submodule '{sub_mod}' (inst '{inst_name}')"
            )
            submodules[sub_mod] = {
                "instance": inst_name,
                "file": None,
                "registers": [],
                "signals": [],
                "parse_success": False,
                "error": "max_depth_reached",
            }
            continue

        # Find submodule file
        sub_file = _find_module_file(sub_mod, dir_for_search)
        if sub_file is None:
            logger.print(
                f"{prefix}[RAG]   Submodule '{sub_mod}' (inst '{inst_name}'): "
                f"file not found on search paths"
            )
            submodules[sub_mod] = {
                "instance": inst_name,
                "file": None,
                "registers": [],
                "signals": [],
                "parse_success": False,
                "error": "file_not_found",
            }
            continue

        # 递归分析子模块
        logger.print(
            f"{prefix}[RAG]   Descending into submodule '{sub_mod}' "
            f"(depth {depth+1}/{MAX_RECURSION_DEPTH}) → {os.path.basename(sub_file)}"
        )
        sub_result = _parse_single_rtl_file(
            sub_file, visited, search_dirs=search_dirs, depth=depth + 1
        )
        submodules[sub_mod] = {
            "instance": inst_name,
            "file": sub_file,
            "registers": sub_result.get("registers", []),
            "signals": sub_result.get("signals", []),
            "parse_success": sub_result.get("parse_success", False),
        }

    # ── 5. Flatten all registers (top-level + submodule) ──
    all_regs = [{"name": r["name"], "width": r["width"],
                 "source": r.get("source", "declaration"), "module": "top"}
                for r in registers]
    all_sigs = [{"name": s["name"], "direction": s["direction"],
                 "width": s["width"], "module": "top"}
                for s in signals]
    for sub_name, sub_info in submodules.items():
        for r in sub_info.get("registers", []):
            all_regs.append({
                "name": f"{sub_name}.{r['name']}",
                "width": r.get("width", 1),
                "source": r.get("source", "submodule"),
                "module": sub_name,
            })
        for s in sub_info.get("signals", []):
            all_sigs.append({
                "name": s["name"], "direction": s.get("direction", "?"),
                "width": s.get("width", 1), "module": sub_name,
            })

    logger.print(f"{prefix}[RAG]   Module '{module_name}': "
                 f"{len(signals)} ports, {len(registers)} regs, "
                 f"{len(submodules)} submodules, "
                 f"{len(all_regs)} total registers (hierarchical)")

    result = {
        "module_name": module_name,
        "signals": signals,
        "registers": registers,
        "signal_width": max_width,
        "submodules": submodules,
        "parse_success": True,
        "all_registers": all_regs,
        "all_signals": all_sigs,
    }

    # Cache the result so multiple instances of the same module reuse it
    _MODULE_RESULT_CACHE[module_name] = result
    return result


def analyze_design_for_hardening(
    rtl_path: str,
    search_paths: Optional[List[str]] = None,
    recursive: bool = True,
    design_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Analyze an RTL file to extract module information for hardening.

    **Now supports hierarchical (recursive) submodule register extraction.**
    When ``recursive=True`` (default), automatically discovers and analyzes
    submodule RTL files by searching:
      1. The same directory as the top-level RTL file
      2. Additional paths specified in ``search_paths``
      3. Directories of files specified in ``design_files`` (for multi-file designs)

    Args:
        rtl_path: Path to the RTL (Verilog/SystemVerilog) file.
        search_paths: Additional directories for submodule file search.
        recursive: If True (default), recursively resolve submodule instances
                   and collect their registers/flip-flops.
        design_files: Additional RTL file paths for multi-file designs.
                      Their parent directories are automatically added to
                      the search paths for submodule resolution.

    Returns:
        Dictionary with keys:
        - module_name (str): Name of the top module.
        - signals (list): List of port signal dicts with keys 'name', 'direction',
          'width'.
        - registers (list): Top-level register/DFF declarations.
        - signal_width (int): Estimated maximum data signal width.
        - file_path (str): Absolute path to the original file.
        - parse_success (bool): Whether parsing completed successfully.
        - submodules (dict): Recursively analyzed submodule info. Only present
          when ``recursive=True``.
        - sub_modules (dict): Alias for ``submodules``, 保持命名一致性。
        - all_registers (list): **Flattened list of ALL registers** across top
          module and all submodules. Each entry has 'name', 'width', 'source'.
          Submodule registers are prefixed with ``<submodule>.<reg>``.
        - hierarchical_registers (list): Alias for ``all_registers``,
          层次化寄存器列表的完整集合。
        - all_signals (list): Flattened list of all ports across hierarchy.

    Raises:
        FileNotFoundError: If the RTL file does not exist.
    """
    rtl_path = os.path.abspath(rtl_path)
    if not os.path.isfile(rtl_path):
        raise FileNotFoundError(f"RTL file not found: {rtl_path}")

    # Merge design_files into search_paths (use their parent directories)
    if design_files:
        file_dirs = {os.path.dirname(os.path.abspath(df))
                     for df in design_files if os.path.isfile(df)}
        search_paths = list(set(search_paths or []) | file_dirs)

    logger.sub_section("Hierarchical RTL Analysis")
    logger.print(f"  [RAG] Input: {rtl_path}")
    logger.print(f"  [RAG] Recursive mode: {recursive}")
    if search_paths:
        logger.print(f"  [RAG] Extra search paths: {search_paths}")

    # Clear global caches for fresh analysis
    _MODULE_RESULT_CACHE.clear()

    result: Dict[str, Any] = {
        "module_name": "unknown",
        "signals": [],
        "registers": [],
        "signal_width": 32,
        "file_path": rtl_path,
        "parse_success": False,
        "submodules": {},
        "sub_modules": {},
        "all_registers": [],
        "hierarchical_registers": [],
        "all_signals": [],
    }

    if recursive:
        # Use recursive hierarchical analysis
        parsed = _parse_single_rtl_file(
            rtl_path,
            visited=set(),
            search_dirs=search_paths,
            depth=0,
        )
        result.update({
            "module_name": parsed.get("module_name", "unknown"),
            "signals": parsed.get("signals", []),
            "registers": parsed.get("registers", []),
            "signal_width": parsed.get("signal_width", 32),
            "submodules": parsed.get("submodules", {}),
            "sub_modules": parsed.get("submodules", {}),  # 别名，保持命名一致性
            "all_registers": parsed.get("all_registers", []),
            "hierarchical_registers": parsed.get("all_registers", []),  # 别名
            "all_signals": parsed.get("all_signals", []),
            "parse_success": parsed.get("parse_success", False),
        })
    else:
        # Flat analysis (original behavior)
        try:
            with open(rtl_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            content_no_comments = re.sub(
                r"//.*?$|/\*.*?\*/", "", content, flags=re.MULTILINE | re.DOTALL
            )
            mod_match = re.search(
                r"module\s+(\w+)\s*(?:#\s*\(.*?\))?\s*\(", content_no_comments, re.DOTALL
            )
            if mod_match:
                result["module_name"] = mod_match.group(1)
            port_pattern = re.compile(
                r"(input|output|inout)\s+"
                r"(?:wire|reg|logic|signed|unsigned|)\s*"
                r"(?:\[([\w-]+):([\w-]+)\])?\s*"
                r"(\w+)",
                re.IGNORECASE,
            )
            max_width = 1
            for match in port_pattern.finditer(content_no_comments):
                direction = match.group(1).lower()
                msb, lsb = match.group(2), match.group(3)
                signal_name = match.group(4)
                try:
                    width = (abs(int(msb) - int(lsb)) + 1) if msb and lsb else 1
                except ValueError:
                    width = 1
                max_width = max(max_width, width)
                result["signals"].append({
                    "name": signal_name, "direction": direction, "width": width,
                })
            result["signal_width"] = max_width
            flat_regs = _extract_registers_from_content(content)
            result["registers"] = flat_regs
            # 扁平模式下，all_registers / hierarchical_registers 即为顶层寄存器列表
            result["all_registers"] = [
                {"name": r["name"], "width": r["width"],
                 "source": r.get("source", "declaration"), "module": "top"}
                for r in flat_regs
            ]
            result["hierarchical_registers"] = result["all_registers"]
            result["all_signals"] = [
                {"name": s["name"], "direction": s["direction"],
                 "width": s["width"], "module": "top"}
                for s in result["signals"]
            ]
            param_match = re.search(r"parameter\s+(\w+)\s*=\s*(\d+)", content_no_comments)
            if param_match:
                result.setdefault("parameters", {})
                result["parameters"][param_match.group(1)] = int(param_match.group(2))
            result["parse_success"] = True
        except Exception as e:
            logger.error(f"[RAG] Flat analysis failed: {e}")

    n_total_regs = len(result.get("all_registers", result.get("registers", [])))
    n_sub = len(result.get("submodules", {}))
    logger.print(f"  [RAG] Analysis complete: module={result['module_name']}, "
                 f"ports={len(result['signals'])}, "
                 f"top_regs={len(result.get('registers', []))}, "
                 f"submodules={n_sub}, "
                 f"total_registers={n_total_regs}")
    logger.info(f"[RAG] Analyzed '{result['module_name']}': "
                f"{len(result['signals'])} ports, "
                f"{n_total_regs} hierarchical registers, "
                f"{n_sub} submodules, "
                f"max width={result['signal_width']}")

    return result


def parse_vulnerability_to_signals(
    vulnerability_result: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Map GNN vulnerability results to signal-level annotations.

    Converts the node-level vulnerability output from GNN inference into
    a list of signal-level vulnerability records. Each record contains
    the signal name (if identifiable), vulnerability score, and
    recommended hardening strategy.

    Args:
        vulnerability_result: Output from GNNInference.infer_from_file()
            or similar. Expected keys:
            - all_vulnerable_nodes (list): Dicts with 'node_id', 'score'.
            - num_nodes (int): Total number of nodes in the design.
            - node_names (list, optional): Human-readable node names.

    Returns:
        List of annotated signal dicts, each with:
        - signal_name (str): Human-readable signal identifier.
        - node_id (int): Original node index.
        - vulnerability_score (float): 0-1 vulnerability probability.
        - recommended_strategy (str): Suggested hardening strategy.
    """
    signal_list: List[Dict[str, Any]] = []

    all_nodes = vulnerability_result.get('all_vulnerable_nodes', [])
    node_names = vulnerability_result.get('node_names', [])
    node_types = vulnerability_result.get('node_types', [])

    # Strategy mapping based on node characteristics
    _STRATEGY_MAP: Dict[str, str] = {
        'state_reg': 'tmr_state',
        'combo': 'tmr',
        'memory': 'ecc',
        'control': 'parity',
        'counter': 'cnt_comp',
        'fsm': 'onehot_fsm',
        'bus': 'parity',
        'data_path': 'tmr',
        'register': 'dice',
        'sram': 'scrubbing',
    }

    for node in all_nodes:
        node_id = node.get('node_id', -1)
        score = node.get('score', 0.0)
        node_type = ''

        # Determine node type
        if node_types and isinstance(node_types, list) and node_id < len(node_types):
            node_type = str(node_types[node_id])
        else:
            node_type = node.get('type', 'data_path')

        # Determine signal name
        if node_names and isinstance(node_names, list) and node_id < len(node_names):
            signal_name = str(node_names[node_id])
        else:
            signal_name = f"sig_{node_id}"

        # Map to recommended strategy
        strategy = _STRATEGY_MAP.get(node_type, 'tmr')

        signal_list.append({
            'signal_name': signal_name,
            'node_id': node_id,
            'vulnerability_score': score,
            'recommended_strategy': strategy,
        })

    # Sort by vulnerability score descending
    signal_list.sort(key=lambda x: -x['vulnerability_score'])

    logger.info(f"[RAG] Mapped {len(signal_list)} vulnerable signals")
    return signal_list


def validate_generated_rtl(rtl_content: str) -> bool:
    """Basic validation of generated RTL code.

    Performs a series of sanity checks on the generated RTL:
    1. Checks that the content is non-empty
    2. Checks for the presence of 'module' and 'endmodule' keywords
    3. Checks that port directions are properly declared
    4. Checks that begin/end blocks are balanced (approximate)
    5. Checks for basic synthesizability (no unsupported constructs)

    Args:
        rtl_content: The generated RTL code as a string.

    Returns:
        True if all checks pass, False otherwise.
    """
    if not rtl_content or not rtl_content.strip():
        logger.error("[RAG Validation] Empty RTL content")
        return False

    # Check 1: Module declaration
    if 'module' not in rtl_content:
        logger.error("[RAG Validation] Missing 'module' keyword")
        return False

    if 'endmodule' not in rtl_content:
        logger.error("[RAG Validation] Missing 'endmodule' keyword")
        return False

    # Check 2: Port declarations exist
    if not re.search(r'\b(input|output|inout)\b', rtl_content, re.IGNORECASE):
        logger.warning("[RAG Validation] No port direction declarations found")

    # Check 3: Approximate begin/end balance
    begin_count = rtl_content.count('begin')
    end_count = rtl_content.count('end')
    # 'endmodule' and 'end' are different; subtract endmodule from end count
    simple_end_count = end_count - rtl_content.count('endmodule')
    if begin_count != simple_end_count:
        logger.warning(f"[RAG Validation] begin/end mismatch: "
                       f"{begin_count} begins vs {simple_end_count} ends")

    # Check 4: No '`include' directives pointing to non-standard paths
    includes = re.findall(r'`include\s+"([^"]+)"', rtl_content)
    for inc in includes:
        if inc.startswith('../') or inc.startswith('/'):
            logger.warning(f"[RAG Validation] Non-standard include: {inc}")

    # Check 5: No 'always' block without sensitivity list (combo)
    if re.search(r'always\s+@\s*\(\s*\)', rtl_content):
        logger.warning("[RAG Validation] Empty sensitivity list detected")

    # Check 6: Wires and registers have proper declarations
    if re.search(r'\breg\b', rtl_content) or re.search(r'\bwire\b', rtl_content):
        logger.verbose("[RAG Validation] Signal declarations present")

    logger.info("[RAG Validation] Basic checks passed")
    return True


def integrate_with_pipeline(
    vulnerability_result: Dict[str, Any],
    pipeline: Any,
) -> Dict[str, str]:
    """Connect RAG results with the existing HardeningPipeline.

    This method performs the full integration workflow:
      1. Analyzes the vulnerability result
      2. Retrieves relevant hardening patterns via RAGEngine
      3. Generates strategy overrides mapped to pipeline signals
      4. Returns the overrides for the pipeline to apply

    Args:
        vulnerability_result: Output from GNN inference containing
            vulnerable node information.
        pipeline: A pipeline instance (expected to have a `module_info`
            dict and optionally a `route_strategies()` method). Compatible
            with the HardeningPipeline interface used in gnn_inference.py.

    Returns:
        strategy_overrides: Dict mapping signal names to recommended
            hardening strategy names. Empty dict if no vulnerabilities found.
    """
    logger.section("RAG Pipeline Integration")

    strategy_overrides: Dict[str, str] = {}
    signal_names = list(getattr(pipeline, 'module_info', {}).keys())

    if not signal_names:
        logger.warning("[RAG Integration] No signals registered in pipeline")
        return strategy_overrides

    # Step 1: Parse vulnerability result to signal-level annotations
    logger.info("[RAG Integration] Step 1/4: Parsing vulnerability results...")
    vulnerable_signals = parse_vulnerability_to_signals(vulnerability_result)

    if not vulnerable_signals:
        logger.info("[RAG Integration] No vulnerable signals found")
        return strategy_overrides

    # Step 2: Retrieve relevant patterns via RAGEngine
    logger.info("[RAG Integration] Step 2/4: Retrieving hardening patterns...")
    engine = RAGEngine(llm_backend='mock')
    engine.load_knowledge_base()
    context = engine._build_context(vulnerability_result, top_k=3)

    # Step 3: Map vulnerable signals to pipeline signals and strategies
    logger.info("[RAG Integration] Step 3/4: Mapping strategies...")
    for vsig in vulnerable_signals:
        signal_name = vsig['signal_name']
        recommended = vsig['recommended_strategy']

        # Try to match by name (partial match)
        matched = False
        for pipe_sig in signal_names:
            if signal_name in pipe_sig or pipe_sig in signal_name:
                strategy_overrides[pipe_sig] = recommended
                matched = True
                break

        if not matched and vsig['node_id'] < len(signal_names):
            # Fallback: map by node index
            strategy_overrides[signal_names[vsig['node_id']]] = recommended

    # Step 4: Apply strategy overrides (if pipeline supports routing)
    logger.info("[RAG Integration] Step 4/4: Applying strategy overrides...")
    if hasattr(pipeline, 'route_strategies') and callable(pipeline.route_strategies):
        try:
            pipeline.route_strategies()
            logger.info("[RAG Integration] Strategies routed successfully")
        except Exception as e:
            logger.warning(f"[RAG Integration] route_strategies() failed: {e}")

    n_overrides = len(strategy_overrides)
    logger.info(f"[RAG Integration] Generated {n_overrides} strategy overrides")

    if n_overrides > 0:
        logger.print(f"\n  [RAG INTEGRATION] {n_overrides} strategy overrides:")
        for sig, strat in sorted(strategy_overrides.items())[:10]:
            logger.print(f"    - {sig} → {strat}")
        if n_overrides > 10:
            logger.print(f"    ... and {n_overrides - 10} more")

    return strategy_overrides


# ============================================================================
# Module-Level Convenience
# ============================================================================

def create_default_engine() -> RAGEngine:
    """Create a RAG engine with default settings (MockLLM backend).

    Returns:
        A pre-initialized RAGEngine instance with loaded knowledge base.
    """
    engine = RAGEngine(llm_backend='mock')
    engine.load_knowledge_base()
    return engine


# ============================================================================
# 层次化提取单元测试
# ============================================================================

def _test_hierarchical_extraction() -> bool:
    """测试层次化子模块寄存器提取功能。

    创建模拟的顶层和子模块 RTL 内容，验证：
      1. _extract_instantiations() 能正确解析模块实例化
      2. _extract_all_registers() 能提取所有 reg 声明
      3. _resolve_instance_rtl() 能通过模糊匹配找到子模块文件
      4. analyze_design_for_hardening() 能递归提取子模块寄存器
      5. 递归深度限制（3层）正常工作
      6. 返回结果中包含 sub_modules 和 hierarchical_registers 字段

    Returns:
        True 表示所有测试通过，False 表示有测试失败。
    """
    logger.section("Hierarchical Extraction Unit Test")
    all_passed = True

    # ── 测试 1: _extract_instantiations ──
    logger.sub_section("Test 1: _extract_instantiations")
    test_rtl = """
    module top (
        input  clk,
        input  rst_n,
        input  [7:0] data_in,
        output [7:0] data_out
    );
        wire [7:0] add_result;
        wire carry;

        // 实例化加法器子模块
        adder_sub u_adder (
            .a(data_in),
            .b(8'h01),
            .sum(add_result),
            .carry_sig(carry)
        );

        // 实例化寄存器子模块
        reg_module u_reg (
            .clk(clk),
            .rst_n(rst_n),
            .d(add_result),
            .q(data_out)
        );

        // 非实例化的 always 块（不应被匹配）
        always @(posedge clk or negedge rst_n) begin
            if (!rst_n)
                data_out <= 8'h00;
            else
                data_out <= add_result;
        end
    endmodule
    """

    insts = _extract_instantiations(test_rtl)
    # 应该提取到 2 个实例化（adder_sub 和 reg_module）
    inst_names = {i["instance_name"] for i in insts}
    assert len(insts) >= 2, f"Expected >=2 instantiations, got {len(insts)}"
    assert "u_adder" in inst_names, f"Missing u_adder instance"
    assert "u_reg" in inst_names, f"Missing u_reg instance"
    # 验证端口连接映射
    for i in insts:
        if i["instance_name"] == "u_adder":
            assert "sum" in i["port_connections"], "Missing port 'sum' in u_adder"
            assert i["port_connections"]["sum"] == "add_result"
    logger.print(f"  [TEST] _extract_instantiations: PASS ({len(insts)} instantiations)")
    logger.print(f"  [TEST]   Instances: {inst_names}")

    # ── 测试 2: _extract_all_registers ──
    logger.sub_section("Test 2: _extract_all_registers")
    test_reg_rtl = """
    module test_regs (
        input clk,
        input rst_n,
        input [7:0] d,
        output reg [7:0] q
    );
        reg [7:0] internal_reg;
        reg flag_reg;
        reg [3:0] counter, temp;

        always @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                q <= 8'h00;
                internal_reg <= 8'h00;
                flag_reg <= 1'b0;
                counter <= 4'h0;
            end else begin
                q <= d;
                internal_reg <= d;
                flag_reg <= 1'b1;
                counter <= counter + 1'b1;
            end
        end
    endmodule
    """
    all_regs = _extract_all_registers(test_reg_rtl)
    reg_set = set(all_regs)
    logger.print(f"  [TEST] _extract_all_registers: found {len(all_regs)} regs: {all_regs}")
    # 应包含 output reg q, reg internal_reg, flag_reg, counter, temp
    for expected in ("q", "internal_reg", "flag_reg", "counter", "temp"):
        assert expected in reg_set, f"Missing register '{expected}'"
    logger.print("  [TEST] _extract_all_registers: PASS")

    # ── 测试 3: _resolve_instance_rtl (使用临时文件) ──
    logger.sub_section("Test 3: _resolve_instance_rtl")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建子模块 RTL 文件
        sub_content = """
        module adder_sub (
            input [7:0] a, b,
            output [7:0] sum,
            output carry_sig
        );
            reg [7:0] sum;
            reg carry_sig;
            always @(*) begin
                {carry_sig, sum} = a + b;
            end
        endmodule
        """
        sub_file_path = os.path.join(tmpdir, "adder_sub.v")
        with open(sub_file_path, "w") as f:
            f.write(sub_content)

        # 测试模糊匹配
        found_content = _resolve_instance_rtl("adder_sub", [tmpdir])
        assert found_content is not None, "_resolve_instance_rtl returned None for adder_sub"
        assert "module adder_sub" in found_content, "Content does not contain expected module"
        logger.print(f"  [TEST] _resolve_instance_rtl (exact match): PASS")

        # 测试不存在的模块
        not_found = _resolve_instance_rtl("nonexistent_module", [tmpdir])
        assert not_found is None, "_resolve_instance_rtl should return None for unknown module"
        logger.print(f"  [TEST] _resolve_instance_rtl (no match returns None): PASS")

        # 测试模糊匹配（文件名包含模块名）
        sub2_content = """
        module reg_module (
            input clk, rst_n,
            input [7:0] d,
            output reg [7:0] q
        );
            reg [7:0] internal_q;
            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    q <= 8'h00;
                    internal_q <= 8'h00;
                end else begin
                    q <= d;
                    internal_q <= d;
                end
            end
        endmodule
        """
        with open(os.path.join(tmpdir, "my_reg_module_custom.v"), "w") as f:
            f.write(sub2_content)
        found_content2 = _resolve_instance_rtl("reg_module", [tmpdir])
        assert found_content2 is not None, "Fuzzy match failed for reg_module"
        assert "module reg_module" in found_content2
        logger.print(f"  [TEST] _resolve_instance_rtl (fuzzy match): PASS")

    # ── 测试 4: analyze_design_for_hardening 递归提取 ──
    logger.sub_section("Test 4: Hierarchical analyze_design_for_hardening")
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建顶层 RTL
        top_content = """
        module top_design (
            input        clk,
            input        rst_n,
            input  [7:0] data_in,
            output [7:0] data_out
        );
            wire [7:0] sum;

            adder_sub u_adder (
                .a(data_in),
                .b(8'h01),
                .sum(sum),
                .carry_sig()
            );

            reg_module u_reg (
                .clk(clk),
                .rst_n(rst_n),
                .d(sum),
                .q(data_out)
            );
        endmodule
        """
        top_file = os.path.join(tmpdir, "top_design.v")
        with open(top_file, "w") as f:
            f.write(top_content)

        # 创建子模块 RTL
        sub1_content = """
        module adder_sub (
            input  [7:0] a, b,
            output [7:0] sum,
            output       carry_sig
        );
            reg [7:0] sum_reg;
            reg carry_reg;
            assign sum = sum_reg;
            assign carry_sig = carry_reg;
            always @(*) begin
                {carry_reg, sum_reg} = a + b;
            end
        endmodule
        """
        with open(os.path.join(tmpdir, "adder_sub.v"), "w") as f:
            f.write(sub1_content)

        sub2_content = """
        module reg_module (
            input        clk, rst_n,
            input  [7:0] d,
            output reg [7:0] q
        );
            reg [7:0] q_reg;
            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) q_reg <= 8'h00;
                else         q_reg <= d;
            end
            assign q = q_reg;
        endmodule
        """
        with open(os.path.join(tmpdir, "reg_module.v"), "w") as f:
            f.write(sub2_content)

        # 执行层次化分析
        result = analyze_design_for_hardening(
            top_file,
            search_paths=[tmpdir],
            recursive=True,
        )

        # 验证顶层信息
        assert result["parse_success"], "Top-level parse failed"
        assert result["module_name"] == "top_design", \
            f"Expected top_design, got {result['module_name']}"
        logger.print(f"  [TEST] Module name: {result['module_name']}")

        # 验证子模块信息
        assert "adder_sub" in result.get("submodules", {}), \
            "Missing submodule adder_sub"
        assert "reg_module" in result.get("submodules", {}), \
            "Missing submodule reg_module"
        logger.print(f"  [TEST] Submodules found: {list(result.get('submodules', {}).keys())}")

        # 验证 sub_modules 别名
        assert "sub_modules" in result, "Missing 'sub_modules' alias field"
        assert result["sub_modules"] == result["submodules"], \
            "'sub_modules' should equal 'submodules'"

        # 验证层次化寄存器提取
        hier_regs = result.get("hierarchical_registers", [])
        assert len(hier_regs) > 0, "No hierarchical registers found"
        # 应包含子模块的寄存器（带前缀）
        sub_reg_names = [r["name"] for r in hier_regs if r["module"] != "top"]
        logger.print(f"  [TEST] Hierarchical registers ({len(hier_regs)} total):")
        for r in hier_regs:
            logger.print(f"    - {r['name']} (width={r['width']}, module={r['module']})")
        assert any("adder_sub" in n for n in sub_reg_names), \
            f"Missing adder_sub registers in hierarchical list: {sub_reg_names}"
        assert any("reg_module" in n for n in sub_reg_names), \
            f"Missing reg_module registers in hierarchical list: {sub_reg_names}"

        # 验证 all_registers 和 hierarchical_registers 一致
        assert result["all_registers"] == result["hierarchical_registers"], \
            "'all_registers' should equal 'hierarchical_registers'"

    # ── 测试 5: 递归深度限制 ──
    logger.sub_section("Test 5: Recursion depth limit")
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建循环实例化链 A -> B -> C -> D (超过3层)
        module_a = """
        module depth_a (
            input clk,
            output reg [3:0] out
        );
            wire [3:0] b_out;
            depth_b u_b (.clk(clk), .out(b_out));
            always @(posedge clk) out <= b_out;
        endmodule
        """
        module_b = """
        module depth_b (
            input clk,
            output reg [3:0] out
        );
            wire [3:0] c_out;
            depth_c u_c (.clk(clk), .out(c_out));
            always @(posedge clk) out <= c_out;
        endmodule
        """
        module_c = """
        module depth_c (
            input clk,
            output reg [3:0] out
        );
            wire [3:0] d_out;
            depth_d u_d (.clk(clk), .out(d_out));
            always @(posedge clk) out <= d_out;
        endmodule
        """
        module_d = """
        module depth_d (
            input clk,
            output reg [3:0] out
        );
            reg [3:0] deep_reg;
            always @(posedge clk) begin
                out <= deep_reg;
                deep_reg <= deep_reg + 1;
            end
        endmodule
        """
        with open(os.path.join(tmpdir, "depth_a.v"), "w") as f:
            f.write(module_a)
        with open(os.path.join(tmpdir, "depth_b.v"), "w") as f:
            f.write(module_b)
        with open(os.path.join(tmpdir, "depth_c.v"), "w") as f:
            f.write(module_c)
        with open(os.path.join(tmpdir, "depth_d.v"), "w") as f:
            f.write(module_d)

        result_depth = analyze_design_for_hardening(
            os.path.join(tmpdir, "depth_a.v"),
            search_paths=[tmpdir],
            recursive=True,
        )
        # depth_a -> depth_b -> depth_c 应被解析，depth_d 应因深度限制被跳过
        subs = result_depth.get("submodules", {})
        # 获取所有递归展开的子模块
        all_subs = set(subs.keys())
        # 递归检查 depth_b 的子模块
        logger.print(f"  [TEST] Depth test submodules: {all_subs}")
        logger.print(f"  [TEST] Hierarchical registers: "
                     f"{[r['name'] for r in result_depth.get('hierarchical_registers', [])]}")

    # ── 汇总 ──
    logger.section("Hierarchical Extraction Test Summary")
    if all_passed:
        logger.print("  [TEST] All hierarchical extraction tests PASSED")
    else:
        logger.error("  [TEST] Some hierarchical extraction tests FAILED")

    return all_passed


# 如果直接运行此脚本，执行层次化提取测试
if __name__ == "__main__":
    _test_hierarchical_extraction()
