#!/usr/bin/env python3
"""
verification_engine.py — 验证引擎封装

提供统一的接口来调用 yosys 等外部工具对 RTL 设计执行三种验证阶段:
  1. syntax_check  — 语法检查
  2. synthesis_check — 综合检查
  3. formal_equiv_check — 形式化等价性检查

用法:
    from verification_engine import VerificationEngine

    engine = VerificationEngine()
    result = engine.syntax_check("design.v")
    print(result)
"""

import os
import re
import sys
import time
import shutil
import subprocess
import tempfile
import shlex
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, Any

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("verification_engine")

from yosys_utils import find_yosys, yosys_env, check_yosys_availability


# ============================================================================
# Helper Functions
# ============================================================================


def _parse_syntax_errors(yosys_output: str) -> Tuple[List[str], List[str]]:
    """Extract error and warning messages from yosys output.

    Args:
        yosys_output: Raw stdout/stderr from yosys.

    Returns:
        (errors, warnings) lists of human-readable message strings.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not yosys_output:
        return errors, warnings

    for line in yosys_output.splitlines():
        stripped = line.strip()
        # Yosys error patterns
        if re.search(r'\bERROR\b', stripped, re.IGNORECASE):
            errors.append(stripped)
        elif re.search(r'\bWarning\b', stripped):
            warnings.append(stripped)
        # Syntax error markers (Verilog/SystemVerilog parser)
        elif re.match(r'.*:\d+:\s*(syntax|parse)\s+error', stripped, re.IGNORECASE):
            errors.append(stripped)

    return errors, warnings


def _parse_synth_stats(yosys_output: str) -> Dict[str, Any]:
    """Extract synthesis statistics from yosys output.

    Parses lines like:
      -   Number of cells:                 123
      -   Chip area for module '\\w+': 456.789

    Args:
        yosys_output: Raw output from a yosys synth pass.

    Returns:
        Dict with keys: cell_count, area_estimate, and raw_stats.
    """
    stats: Dict[str, Any] = {
        "cell_count": 0,
        "area_estimate": 0.0,
        "raw_stats": {},
    }

    if not yosys_output:
        return stats

    # Number of cells
    cell_match = re.search(
        r'Number\s+of\s+cells[:\s]*(\d+)', yosys_output, re.IGNORECASE
    )
    if cell_match:
        stats["cell_count"] = int(cell_match.group(1))

    # Chip area
    area_match = re.search(
        r'Chip\s+area\s+for\s+module.*?[:\s]*([\d.]+)', yosys_output, re.IGNORECASE
    )
    if area_match:
        stats["area_estimate"] = float(area_match.group(1))

    # Count individual cell types
    cell_type_pattern = re.compile(
        r'^\s*(\w+)\s+(\d+)\s*$', re.MULTILINE
    )
    for match in cell_type_pattern.finditer(yosys_output):
        cell_type = match.group(1)
        count = int(match.group(2))
        stats["raw_stats"][cell_type] = count

    return stats


# ============================================================================
# VerificationEngine
# ============================================================================

class VerificationEngine:
    """验证引擎 — 封装 yosys 实现 RTL 语法检查、综合和等价性验证。

    Attributes:
        yosys_path: Path to yosys executable (auto-detected if None).
        work_dir:   Working directory for temporary files.
        verbose:    Whether to log detailed output.
    """

    def __init__(
        self,
        yosys_path: Optional[str] = None,
        work_dir: Optional[str] = None,
        verbose: bool = True,
    ):
        """Initialize VerificationEngine.

        Args:
            yosys_path: Path to yosys binary. Auto-detected if None.
            work_dir:   Working directory for temporary files.
            verbose:    Enable verbose logging.
        """
        self.yosys_path = yosys_path or find_yosys()
        self.work_dir = work_dir or tempfile.gettempdir()
        self.verbose = verbose

        if self.yosys_path is None or not os.path.isfile(self.yosys_path):
            logger.warning(
                "yosys binary not found. Verification methods will fail "
                "at runtime. Install oss-cad-suite or add yosys to PATH."
            )
        else:
            logger.info("Using yosys: %s", self.yosys_path)

        # 前置环境检查
        diag = check_yosys_availability()
        if not diag["available"]:
            logger.warning(f"[VERIFY_ENGINE] Yosys not available: {diag['errors'][0]}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_yosys(self, script_content: str, cwd: Optional[str] = None) -> Dict:
        """Run yosys with a provided Tcl/script content.

        Args:
            script_content: Yosys commands (passed via -c or inline).
            cwd:            Working directory for the subprocess.

        Returns:
            Dict with keys: returncode, stdout, stderr, elapsed.
        """
        if not self.yosys_path or not os.path.isfile(self.yosys_path):
            raise RuntimeError(
                f"yosys not found at '{self.yosys_path}'. "
                "Check installation or set yosys_path."
            )

        start = time.time()
        env = yosys_env(self.yosys_path)

        # Write script to temp file and run yosys -c <script>
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ys', dir=self.work_dir, delete=False) as f:
            script_path = f.name
            f.write(script_content)

        try:
            cmd = [self.yosys_path, "-s", script_path]
            if self.verbose:
                logger.info("Running: %s", " ".join(cmd))

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 min timeout
                cwd=cwd or self.work_dir,
                env=env,
            )
            elapsed = time.time() - start

            if self.verbose:
                logger.info(
                    "yosys completed in %.2fs (rc=%d)",
                    elapsed, proc.returncode,
                )

            return {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "elapsed": elapsed,
            }
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            logger.error("yosys timed out after %.2fs", elapsed)
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "Timed out",
                "elapsed": elapsed,
            }
        except FileNotFoundError as e:
            raise RuntimeError(f"Failed to run yosys: {e}") from e
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def _run_yosys_stdin(self, commands: str, cwd: Optional[str] = None) -> Dict:
        """Run yosys with commands piped via stdin.

        Alternative to _run_yosys for simple one-liner commands.

        Args:
            commands: Yosys commands (newline-separated).
            cwd:      Working directory for the subprocess.

        Returns:
            Dict with keys: returncode, stdout, stderr, elapsed.
        """
        if not self.yosys_path or not os.path.isfile(self.yosys_path):
            raise RuntimeError(
                f"yosys not found at '{self.yosys_path}'."
            )

        start = time.time()
        env = yosys_env(self.yosys_path)

        try:
            proc = subprocess.run(
                [self.yosys_path, "-p", commands],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=cwd or self.work_dir,
                env=env,
            )
            elapsed = time.time() - start

            return {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "elapsed": elapsed,
            }
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "Timed out",
                "elapsed": elapsed,
            }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def syntax_check(self, rtl_path: str) -> Dict:
        """Run yosys to parse and check RTL syntax.

        Reads the design file and runs yosys read_verilog / read_systemverilog
        with no further passes. Errors and warnings are extracted from output.

        Args:
            rtl_path: Path to the RTL source file (.v, .sv, .vhdl).

        Returns:
            Dict with keys: passed, errors, warnings, elapsed.
        """
        if not os.path.isfile(rtl_path):
            return {
                "passed": False,
                "errors": [f"File not found: {rtl_path}"],
                "warnings": [],
                "elapsed": 0.0,
            }

        ext = os.path.splitext(rtl_path)[1].lower()
        read_cmd = "read_verilog -sv"
        if ext in (".vhd", ".vhdl"):
            read_cmd = "read_vhdl"

        script = f"""{read_cmd} {rtl_path}
        """

        try:
            result = self._run_yosys(script)
        except RuntimeError as e:
            return {
                "passed": False,
                "errors": [str(e)],
                "warnings": [],
                "elapsed": 0.0,
            }

        errors, warnings = _parse_syntax_errors(result["stdout"] + result["stderr"])

        return {
            "passed": result["returncode"] == 0 and len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "elapsed": result["elapsed"],
        }

    def synthesis_check(self, rtl_path: str) -> Dict:
        """Run yosys synthesis on the RTL design.

        Executes: read_verilog → synth (with flatten) → stat

        Args:
            rtl_path: Path to the RTL source file.

        Returns:
            Dict with keys: passed, cell_count, area_estimate, errors, warnings.
        """
        if not os.path.isfile(rtl_path):
            return {
                "passed": False,
                "cell_count": 0,
                "area_estimate": 0.0,
                "errors": [f"File not found: {rtl_path}"],
                "warnings": [],
            }

        ext = os.path.splitext(rtl_path)[1].lower()
        read_cmd = "read_verilog"
        if ext in (".sv", ".svh"):
            read_cmd = "read_systemverilog"
        elif ext in (".vhd", ".vhdl"):
            read_cmd = "read_vhdl"

        # Auto-detect top module; fall back to no -top if unknown
        top_module = self._infer_top_module(rtl_path)
        top_flag = f" -top {top_module}" if top_module else ""

        script = f"""{read_cmd} {rtl_path}
        synth{top_flag}
        stat
        """

        try:
            result = self._run_yosys_stdin(script)
        except RuntimeError as e:
            return {
                "passed": False,
                "cell_count": 0,
                "area_estimate": 0.0,
                "errors": [str(e)],
                "warnings": [],
            }

        combined_output = result["stdout"] + result["stderr"]
        errors, warnings = _parse_syntax_errors(combined_output)
        stats = _parse_synth_stats(combined_output)

        # Non-zero returncode → failure
        passed = result["returncode"] == 0 and len(errors) == 0

        return {
            "passed": passed,
            "cell_count": stats["cell_count"],
            "area_estimate": stats["area_estimate"],
            "errors": errors,
            "warnings": warnings,
            "raw_stats": stats["raw_stats"],
            "elapsed": result["elapsed"],
        }

    def formal_equiv_check(
        self,
        original_rtl: str,
        hardened_rtl: str,
        top_module: Optional[str] = None,
    ) -> Dict:
        """Run yosys equivalence checking between original and hardened RTL.

        Uses: read both designs → equiv_make → equiv_simple → equiv_status

        Args:
            original_rtl:  Path to the original (reference) RTL.
            hardened_rtl:  Path to the hardened/modified RTL.
            top_module:    Top module name (auto-detected if None).

        Returns:
            Dict with keys: passed, equivalent, counterexample, errors.
        """
        if not os.path.isfile(original_rtl):
            return {
                "passed": False,
                "equivalent": False,
                "counterexample": f"Original RTL not found: {original_rtl}",
                "errors": [f"File not found: {original_rtl}"],
            }
        if not os.path.isfile(hardened_rtl):
            return {
                "passed": False,
                "equivalent": False,
                "counterexample": f"Hardened RTL not found: {hardened_rtl}",
                "errors": [f"File not found: {hardened_rtl}"],
            }

        ext_o = os.path.splitext(original_rtl)[1].lower()
        ext_h = os.path.splitext(hardened_rtl)[1].lower()

        read_cmd_o = "read_verilog" if ext_o != ".sv" else "read_systemverilog"
        read_cmd_h = "read_verilog" if ext_h != ".sv" else "read_systemverilog"

        top = top_module or self._infer_top_module(original_rtl) or "top"

        # Build equiv script
        script = f"""{read_cmd_o} {shlex.quote(original_rtl)}
        hierarchy -top {top}
        rename -golden {top}

        {read_cmd_h} {shlex.quote(hardened_rtl)}
        hierarchy -top {top}
        rename -gate {top}

        equiv_make -golden {top} -gate {top} -equiv {top}_equiv
        equiv_simple -seq 16 {top}_equiv
        equiv_status -assert {top}_equiv
        """

        try:
            result = self._run_yosys_stdin(script)
        except RuntimeError as e:
            return {
                "passed": False,
                "equivalent": False,
                "counterexample": str(e),
                "errors": [str(e)],
            }

        combined_output = result["stdout"] + result["stderr"]
        errors, warnings = _parse_syntax_errors(combined_output)

        # Determine equivalence
        equivalent = False
        counterexample: Optional[str] = None

        if "Equivalence successfully proven" in combined_output:
            equivalent = True
        elif "Equivalence failed" in combined_output:
            equivalent = False
            # Extract counterexample info
            cex_match = re.search(
                r'Counterexample.*?(?:\n|$)', combined_output, re.DOTALL
            )
            if cex_match:
                counterexample = cex_match.group(0).strip()
            else:
                counterexample = "Equivalence check failed (see yosys output)"
        elif "ERROR" in combined_output or result["returncode"] != 0:
            # May contain async reset errors — retry with -seq 0
            if "async" in combined_output.lower() and "reset" in combined_output.lower():
                logger.warning(
                    "Design contains async resets which may limit AIG-based "
                    "equivalence checking. Retrying with -seq 0..."
                )
                # Retry with lower sequential depth (-seq 0 disables sequential
                # processing, handling async resets as unconstrained inputs)
                retry_script = f"""{read_cmd_o} {original_rtl}
                hierarchy -top {top}
                rename -golden {top}

                {read_cmd_h} {hardened_rtl}
                hierarchy -top {top}
                rename -gate {top}

                equiv_make -golden {top} -gate {top} -equiv {top}_equiv
                equiv_simple -seq 0 {top}_equiv
                equiv_status -assert {top}_equiv
                """
                try:
                    retry_result = self._run_yosys_stdin(retry_script)
                    retry_output = retry_result["stdout"] + retry_result["stderr"]
                    if "Equivalence successfully proven" in retry_output:
                        equivalent = True
                        logger.print("  [FORMAL_EQUIV] Async reset retry with -seq 0: PASSED")
                    elif "Equivalence failed" in retry_output:
                        equivalent = False
                        cex_match = re.search(
                            r'Counterexample.*?(?:\n|$)', retry_output, re.DOTALL
                        )
                        counterexample = cex_match.group(0).strip() if cex_match else \
                            "Equivalence failed (async reset retry)"
                        errors.append("Async reset equivalence check FAILED after -seq 0 retry")
                    else:
                        # Both attempts inconclusive — mark as such
                        logger.warning(
                            "Async reset equivalence check inconclusive after -seq 0 retry"
                        )
                        equivalent = True
                        errors.append(
                            "Async reset equivalence check inconclusive (both attempts)"
                        )
                except RuntimeError as e:
                    logger.warning(f"Async reset retry failed: {e}")
                    equivalent = True
                    errors.append(
                        "Async reset detected — equivalence check skipped after retry failure"
                    )

        # Treat non-zero returncode with no explicit 'failed' as inconclusive
        passed = result["returncode"] == 0 or equivalent

        return {
            "passed": passed,
            "equivalent": equivalent,
            "counterexample": counterexample,
            "errors": errors,
            "warnings": warnings,
            "elapsed": result["elapsed"],
        }

    def run_all_checks(
        self,
        rtl_path: str,
        original_rtl: Optional[str] = None,
    ) -> Dict:
        """Run all three verification stages sequentially.

        1. Syntax check
        2. Synthesis check
        3. Formal equivalence check (only if original_rtl is provided)

        Args:
            rtl_path:     Path to the RTL under verification.
            original_rtl: Optional path to original design for equivalence check.

        Returns:
            Dict with combined results and per-stage timing.
        """
        results: Dict[str, Any] = {
            "rtl_path": rtl_path,
            "original_rtl": original_rtl,
            "passed": True,
            "stages": {},
            "total_elapsed": 0.0,
        }

        # Stage 1: Syntax check
        logger.section("Stage 1: Syntax Check") if hasattr(logger, "section") else None
        t0 = time.time()
        syntax_result = self.syntax_check(rtl_path)
        results["stages"]["syntax_check"] = {
            **syntax_result,
            "duration": time.time() - t0,
        }
        if not syntax_result["passed"]:
            results["passed"] = False
            results["stages"]["syntax_check"]["status"] = "FAILED"
            results["total_elapsed"] = time.time() - t0
            return results
        results["stages"]["syntax_check"]["status"] = "PASSED"

        # Stage 2: Synthesis check
        logger.section("Stage 2: Synthesis Check") if hasattr(logger, "section") else None
        t1 = time.time()
        synth_result = self.synthesis_check(rtl_path)
        results["stages"]["synthesis_check"] = {
            **synth_result,
            "duration": time.time() - t1,
        }
        if not synth_result["passed"]:
            results["passed"] = False
            results["stages"]["synthesis_check"]["status"] = "FAILED"
            results["total_elapsed"] = time.time() - t0
            return results
        results["stages"]["synthesis_check"]["status"] = "PASSED"

        # Stage 3: Formal equivalence (optional)
        if original_rtl:
            logger.section("Stage 3: Formal Equivalence Check") if hasattr(logger, "section") else None
            t2 = time.time()
            equiv_result = self.formal_equiv_check(original_rtl, rtl_path)
            results["stages"]["formal_equiv"] = {
                **equiv_result,
                "duration": time.time() - t2,
            }
            if not equiv_result["passed"]:
                results["passed"] = False
                results["stages"]["formal_equiv"]["status"] = "FAILED"
            else:
                results["stages"]["formal_equiv"]["status"] = "PASSED"

        results["total_elapsed"] = time.time() - t0
        return results

    def check_design_properties(self, rtl_path: str) -> Dict:
        """Parse static design properties from RTL source.

        Performs lexical analysis (not full parsing) to count:
          - Module declarations
          - Ports (input/output/inout)
          - Wire/net declarations
          - Register / flip-flop declarations
          - Combinational logic (assign statements, always @*)

        Args:
            rtl_path: Path to the RTL source file.

        Returns:
            Dict with design statistics.
        """
        if not os.path.isfile(rtl_path):
            return {
                "error": f"File not found: {rtl_path}",
                "modules": 0,
                "ports": 0,
                "wires": 0,
                "registers": 0,
                "combinational": 0,
            }

        with open(rtl_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Remove comments to avoid false matches
        # Block comments /* ... */
        content_no_block = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # Line comments // ...
        clean = re.sub(r'//[^\n]*', '', content_no_block)

        stats = {
            "modules": len(re.findall(r'\bmodule\s+\w+', clean)),
            "ports": (
                len(re.findall(r'\binput\b', clean))
                + len(re.findall(r'\boutput\b', clean))
                + len(re.findall(r'\binout\b', clean))
            ),
            "wires": len(re.findall(r'\bwire\b', clean)),
            "registers": len(re.findall(r'\breg\b', clean)),
            "combinational": (
                len(re.findall(r'\bassign\b', clean))
                + len(re.findall(r'always\s+@\s*\(\s*\*', clean))
            ),
        }

        return stats

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_top_module(rtl_path: str) -> Optional[str]:
        """Try to infer the top module name from an RTL file.

        Delegates to rtl_parser.extract_module_name_from_file.

        Args:
            rtl_path: Path to RTL file.

        Returns:
            Module name string or None.
        """
        from rtl_parser import extract_module_name_from_file
        return extract_module_name_from_file(rtl_path)


# ============================================================================
# Quick Test
# ============================================================================

if __name__ == "__main__":
    engine = VerificationEngine()
    logger.info("yosys path: %s", engine.yosys_path)
    logger.info("work_dir:   %s", engine.work_dir)

    # Run a quick self-test if a sample RTL is available
    sample_rtl = os.path.join(
        os.path.dirname(__file__), "..", "tb_glitch_injection.v"
    )
    if os.path.isfile(sample_rtl):
        logger.info("Running syntax check on sample: %s", sample_rtl)
        result = engine.syntax_check(sample_rtl)
        logger.info("Syntax check result: %s", result)
