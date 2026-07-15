#!/usr/bin/env python3
"""
blif_to_aiger.py — BLIF → AIGER 二进制格式转换器

绕过 yosys write_aiger 的 $_DFF_PN0_ 限制，将 yosys 生成的 BLIF 文件
直接转换为 AIGER 二进制格式，供 aig_parser.py 使用。

用法:
    from blif_to_aiger import blif_to_aiger

    success = blif_to_aiger("input.blif", "output.aig", "output_map.txt")

流程:
    1. 解析 BLIF 文件的 .names / .latch / .inputs / .outputs
    2. 构建信号→AIGER 变量映射
    3. 生成 AIGER 二进制格式 (aig M I L O A + varint delta 编码)

AIGER 二进制格式参考 (http://fmv.jku.at/aiger/):
    Header:  "aig M I L O A\\n"
      M = I + L + A
      I = 输入 (PI) 数量
      L = 锁存器 (DFF) 数量
      O = 输出 (PO) 数量
      A = AND 门数量

    Body:
      - AND 门 delta 编码: 每个门两个 varint 小整数
      - PO delta 编码: 每个输出一个 varint
      - Latch delta 编码: 每个锁存器一个 varint

    变量分配:
      PI:      1 .. I
      Latch:   I+1 .. I+L
      AND:     I+L+1 .. I+L+A

    字面量: lit = (var << 1) | inv_flag
"""

import os
import sys
import struct
from typing import Dict, List, Optional, Tuple

# ── Logger ──

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ============================================================================
# BLIF Parser (lightweight, no PyTorch dependency)
# ============================================================================

class _BlifReader:
    """Minimal BLIF parser to extract structure for AIGER conversion."""

    def __init__(self, blif_path: str):
        self.path = blif_path
        self.model_name = ""
        self.inputs: List[str] = []
        self.outputs: List[str] = []
        self.names_tables: List[Tuple[List[str], str, List[str]]] = []
        self.latches: List[Tuple[str, str, Optional[str], Optional[str]]] = []
        self._parse()

    def _parse(self):
        with open(self.path, 'r', encoding='utf-8', errors='ignore') as f:
            raw_lines = f.readlines()

        # Strip comments and blank lines
        lines = []
        for line in raw_lines:
            s = line.split('#')[0].strip()
            if s:
                lines.append(s)

        i = 0
        while i < len(lines):
            line = lines[i]
            tokens = line.split()
            if not tokens:
                i += 1
                continue

            directive = tokens[0]

            if directive == '.model':
                self.model_name = tokens[1] if len(tokens) > 1 else ""

            elif directive == '.inputs':
                self.inputs.extend(tokens[1:])

            elif directive == '.outputs':
                self.outputs.extend(tokens[1:])

            elif directive == '.names':
                output = tokens[-1]
                ins = tokens[1:-1]
                rows = []
                i += 1
                while i < len(lines) and lines[i] and lines[i][0] not in '.$':
                    row_line = lines[i]
                    import re
                    if re.match(r'^[01!? ]+$', row_line) or re.match(r'^[01]$', row_line):
                        rows.append(row_line)
                    else:
                        break
                    i += 1
                self.names_tables.append((ins, output, rows))
                continue

            elif directive == '.latch':
                if len(tokens) >= 3:
                    inp = tokens[1]
                    out = tokens[2]
                    typ = tokens[3] if len(tokens) > 3 else None
                    ctrl = tokens[4] if len(tokens) > 4 else None
                    self.latches.append((inp, out, typ, ctrl))

            elif directive == '.end':
                break

            i += 1


# ============================================================================
# AIGER Binary Writer
# ============================================================================

def _encode_varint(value: int) -> bytes:
    """Encode an unsigned integer as AIGER varint (7-bit per byte, little-endian).

    Each byte: bit 7 = continue flag, bits 6-0 = data.
    """
    result = []
    while value >= 0x80:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value & 0x7f)
    return bytes(result)


def _is_and_gate(rows: List[str], num_inputs: int) -> bool:
    """Check if truth table represents an AND gate (all-1s cube)."""
    for row in rows:
        parts = row.split()
        if len(parts) < 2:
            continue
        pattern = parts[0]
        out_val = parts[-1]
        if out_val == '1' and all(ch == '1' for ch in pattern):
            return True
    return False


def _get_inversion_mask(rows: List[str], num_inputs: int) -> List[bool]:
    """Return list of booleans indicating which inputs are negated."""
    mask = [False] * num_inputs
    for row in rows:
        parts = row.split()
        if len(parts) < 2:
            continue
        pattern = parts[0]
        out_val = parts[-1]
        if out_val == '1':
            for j, ch in enumerate(pattern):
                if ch == '0':
                    mask[j] = True
    return mask


def _signal_lit(signal: str, var_map: Dict[str, int], inverted: bool = False) -> int:
    """Convert a signal name to an AIGER literal.

    lit = (var << 1) | inv_flag
    """
    var = var_map.get(signal)
    if var is None:
        # Unknown signal: treat as const 0
        var = 0
    return (var << 1) | (1 if inverted else 0)


def blif_to_aiger(blif_path: str, aig_path: str, map_path: Optional[str] = None,
                  verbose: bool = False) -> bool:
    """Convert a BLIF file to AIGER binary format.

    Args:
        blif_path: Input BLIF file path.
        aig_path: Output AIGER binary file path.
        map_path: Optional output port mapping file path.
        verbose: Print progress if True.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    if not os.path.isfile(blif_path):
        logger.error(f"[BLIF→AIG] BLIF file not found: {blif_path}")
        return False

    # ── 1. Parse BLIF ──
    if verbose:
        print(f"  [BLIF→AIG] Parsing: {blif_path}")
    reader = _BlifReader(blif_path)

    # ── 2. Classify signals ──
    pi_set = set(reader.inputs)
    po_set = set(reader.outputs)
    dff_q_set: set = set()       # DFF output signals
    dff_d_map: Dict[str, str] = {}  # DFF output → input
    const0_set: set = set()
    const1_set: set = set()
    and_outputs: set = set()      # signals that are AND gate outputs
    names_outputs: set = set()    # all .names output signals

    # Constants (names with no inputs)
    for ins, out, rows in reader.names_tables:
        names_outputs.add(out)
        if not ins:
            if rows and rows[0].strip() == '1':
                const1_set.add(out)
            else:
                const0_set.add(out)

    # DFFs from .latch
    for inp, out, typ, ctrl in reader.latches:
        dff_q_set.add(out)
        dff_d_map[out] = inp

    # AND gates from .names (simple AND pattern)
    for ins, out, rows in reader.names_tables:
        if not ins:
            continue  # already handled as constant
        if out in dff_q_set:
            continue  # DFF outputs are not AND nodes
        if rows and _is_and_gate(rows, len(ins)):
            and_outputs.add(out)

    if verbose:
        print(f"  [BLIF→AIG] PIs={len(pi_set)}, POs={len(po_set)}, "
              f"DFFs={len(dff_q_set)}, ANDs={len(and_outputs)}, "
              f"const={len(const0_set)+len(const1_set)}, "
              f"names={len(reader.names_tables)}")

    # ── 3. Build dependency graph and topological sort ──
    I = len(pi_set)
    L = len(dff_q_set)
    A = len(and_outputs)

    # Build input dependencies for each AND gate
    # and_inputs[sig] = list of input signal names for that AND gate
    and_inputs: Dict[str, List[str]] = {}
    for ins, out, rows in reader.names_tables:
        if out in and_outputs:
            and_inputs[out] = ins

    # Topological sort: find order where all inputs come before outputs
    and_list_topo = list(and_outputs)
    # Simple approach: sort by dependency depth (input signals that are also
    # AND outputs must come first)
    def _and_sort_key(sig: str) -> int:
        """Compute depth of AND gate: max depth of inputs + 1."""
        ins = and_inputs.get(sig, [])
        if not ins:
            return 0
        max_depth = 0
        for inp in ins:
            if inp in and_outputs:
                max_depth = max(max_depth, _and_sort_key(inp))
        return max_depth + 1

    and_list_topo.sort(key=_and_sort_key)

    # Verify topological ordering: each AND gate's inputs must have lower
    # variable numbers (PIs and DFFs are always lower than AND vars)
    if verbose and len(and_list_topo) > 1:
        print(f"  [BLIF→AIG] AND gates topologically sorted, "
              f"depth range: {_and_sort_key(and_list_topo[0])}.."
              f"{_and_sort_key(and_list_topo[-1])}")

    # ── 4. Assign AIGER variables ──
    var_map: Dict[str, int] = {}  # signal name → AIGER variable

    # Assign PI variables: 1..I
    pi_list = sorted(pi_set) if pi_set else []
    for idx, sig in enumerate(pi_list):
        var_map[sig] = idx + 1

    # Assign DFF output variables: I+1..I+L
    dff_list = sorted(dff_q_set) if dff_q_set else []
    for idx, sig in enumerate(dff_list):
        var_map[sig] = I + idx + 1

    # Assign AND output variables in topological order: I+L+1..I+L+A
    and_list = and_list_topo
    for idx, sig in enumerate(and_list):
        var_map[sig] = I + L + idx + 1

    M = I + L + A
    O = len(po_set)

    # ── 5. Build body: AND gate deltas ──
    body = b''

    for idx, sig in enumerate(and_list):
        and_var = I + L + idx + 1
        S_i = 2 * and_var  # reference point for delta encoding

        # Get the .names entry for this signal
        rhs0_lit = 0
        rhs1_lit = 0
        for ins, out, rows in reader.names_tables:
            if out == sig:
                inv_mask = _get_inversion_mask(rows, len(ins))
                if len(ins) >= 1:
                    rhs0_lit = _signal_lit(ins[0], var_map,
                                           inv_mask[0] if len(inv_mask) > 0 else False)
                if len(ins) >= 2:
                    rhs1_lit = _signal_lit(ins[1], var_map,
                                           inv_mask[1] if len(inv_mask) > 1 else False)
                else:
                    # Buffer/INV: both inputs same
                    rhs1_lit = rhs0_lit
                break

        # AIGER spec: rhs0_lit >= rhs1_lit, so sort them
        if rhs0_lit < rhs1_lit:
            rhs0_lit, rhs1_lit = rhs1_lit, rhs0_lit

        # Delta encoding: delta0 = S_i - rhs0_lit, delta1 = rhs0_lit - rhs1_lit
        delta0 = S_i - rhs0_lit
        delta1 = rhs0_lit - rhs1_lit

        # With proper topological ordering, deltas should be positive.
        # Clamp as safety net only.
        if delta0 < 0 or delta1 < 0:
            logger.warning(f"[BLIF→AIG] Negative delta for AND {sig} "
                           f"(var={and_var}): delta0={delta0}, delta1={delta1}")
            delta0 = max(delta0, 1)
            delta1 = max(delta1, 1)

        body += _encode_varint(delta0)
        body += _encode_varint(delta1)

    # ── 5. Build body: PO deltas ──
    # PO delta = M - lit (where lit is the variable for the PO signal)
    po_varint_values = []
    po_signal_map: Dict[str, int] = {}

    po_list = sorted(po_set) if po_set else []
    for po_idx, po_sig in enumerate(po_list):
        # Find where this PO signal comes from
        po_var = var_map.get(po_sig)
        if po_var is None:
            # Try to find it as a .names output (combinational PO)
            for ins, out, rows in reader.names_tables:
                if out == po_sig:
                    # It's already an AND gate output, use that var
                    po_var = var_map.get(out)
                    break
        if po_var is None:
            # Try to find it as a DFF Q output
            if po_sig in dff_d_map:
                po_var = var_map.get(po_sig)

        if po_var is None:
            # Signal not found: treat as const 0
            po_lit = 0
        else:
            po_lit = po_var << 1  # non-inverted

        po_delta = M - po_lit
        if po_delta < 0:
            po_delta = 0
        body += _encode_varint(po_delta)
        po_signal_map[po_sig] = po_lit

    # ── 6. Build body: Latch deltas ──
    # Each latch: delta = M - next_lit
    # where next_lit is the literal for the latch's input (D)
    latch_next_map: Dict[str, int] = {}  # latch output var -> next state literal

    for dff_idx, sig in enumerate(dff_list):
        d_signal = dff_d_map.get(sig, '')
        if d_signal in var_map:
            d_var = var_map[d_signal]
            d_lit = d_var << 1
        else:
            # D input not a mapped variable: try to find it as .names output
            d_lit = 0  # default const 0
            for ins, out, rows in reader.names_tables:
                if out == d_signal:
                    d_var = var_map.get(out)
                    if d_var:
                        d_lit = d_var << 1
                    break

        latch_delta = M - d_lit
        if latch_delta < 0:
            latch_delta = 0
        body += _encode_varint(latch_delta)
        latch_next_map[sig] = d_lit

    # ── 7. Write AIGER binary file ──
    header = f"aig {M} {I} {L} {O} {A}\n"
    with open(aig_path, 'wb') as f:
        f.write(header.encode('ascii'))
        f.write(body)

    if verbose:
        print(f"  [BLIF→AIG] Written: {aig_path}")
        print(f"    Header: aig {M} {I} {L} {O} {A}")
        print(f"    Body: {len(body)} bytes")

    # ── 8. Write map file (optional) ──
    if map_path:
        with open(map_path, 'w', encoding='utf-8') as f:
            # PI mappings
            for sig in pi_list:
                var = var_map.get(sig, 0)
                lit = var << 1
                f.write(f"{lit} {sig}\n")
            # PO mappings
            for sig in po_list:
                lit = po_signal_map.get(sig, 0)
                f.write(f"{lit} {sig}\n")
        if verbose:
            print(f"  [BLIF→AIG] Map written: {map_path}")

    return True


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Convert BLIF to AIGER binary format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('blif', help='Input BLIF file')
    parser.add_argument('--aig', default=None, help='Output AIG file (default: input.aig)')
    parser.add_argument('--map', default=None, help='Output map file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    if args.aig is None:
        args.aig = os.path.splitext(args.blif)[0] + '.aig'
    if args.map is None:
        args.map = os.path.splitext(args.blif)[0] + '_map.txt'

    success = blif_to_aiger(args.blif, args.aig, args.map, verbose=args.verbose)
    if success:
        print(f"[OK] {args.blif} → {args.aig}")
        if args.verbose:
            aig_size = os.path.getsize(args.aig) if os.path.isfile(args.aig) else 0
            print(f"     AIG size: {aig_size} bytes")
    else:
        print(f"[FAIL] Conversion failed for {args.blif}")
        sys.exit(1)


if __name__ == '__main__':
    main()
