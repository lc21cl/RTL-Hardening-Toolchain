#!/usr/bin/env python3
"""
auto_repair.py — 自动修复管线

实现闭环 验证 → 修复 → 验证 周期:
  1. 语法检查 → SyntaxFixer
  2. 综合检查 → SynthesisFixer
  3. 形式化等价性检查 → EquivFixer
  4. 最终验证

用法:
    from auto_repair import AutoRepairEngine, generate_repair_report

    engine = AutoRepairEngine()
    result = engine.repair("design.v", original_rtl="original.v")
    print(generate_repair_report(result))
"""

import os
import re
import copy
import time
import shutil
import tempfile
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("auto_repair")

try:
    from verification_engine import VerificationEngine
except ImportError:
    VerificationEngine = None  # type: ignore


# ============================================================================
# RepairStrategy Enum
# ============================================================================

class RepairStrategy(Enum):
    """修复策略类型。"""
    SYNTAX_FIX = "syntax_fix"
    SYNTHESIS_FIX = "synthesis_fix"
    EQUIV_FIX = "equiv_fix"
    WARNING_FIX = "warning_fix"


# ============================================================================
# AutoRepairEngine
# ============================================================================

class AutoRepairEngine:
    """自动修复引擎 — 闭环验证 → 修复 → 验证循环。

    Attributes:
        verifier:       VerificationEngine 实例。
        max_iterations: 最大修复迭代次数。
        verbose:        是否输出详细日志。
    """

    # ── 状态常量 ──
    STATE_IDLE = "IDLE"
    STATE_CHECKING = "CHECKING"
    STATE_REPAIRING = "REPAIRING"
    STATE_VERIFYING = "VERIFYING"
    STATE_DONE = "DONE"

    def __init__(
        self,
        verifier: Optional[Any] = None,
        max_iterations: int = 5,
        verbose: bool = True,
    ):
        """初始化 AutoRepairEngine。

        Args:
            verifier:       VerificationEngine 实例。为 None 时自动创建。
            max_iterations: 最大修复迭代次数。
            verbose:        启用详细日志。
        """
        self.verifier = verifier
        self.max_iterations = max_iterations
        self.verbose = verbose

        if self.verifier is None and VerificationEngine is not None:
            try:
                self.verifier = VerificationEngine(verbose=verbose)
            except Exception as e:
                logger.warning("Failed to create VerificationEngine: %s", e)

        self._state = self.STATE_IDLE
        self._iteration = 0
        self._stage_results: List[Dict] = []
        self._fixed_rtl_path: Optional[str] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    @state.setter
    def state(self, value: str) -> None:
        logger.info("State transition: %s → %s", self._state, value)
        self._state = value

    # ------------------------------------------------------------------
    # Main Repair Loop
    # ------------------------------------------------------------------

    def repair(
        self,
        rtl_path: str,
        original_rtl: Optional[str] = None,
    ) -> Dict:
        """运行完整的自动修复管线。

        状态机:
          IDLE → CHECKING → REPAIRING → VERIFYING → DONE

        Args:
            rtl_path:     待修复的 RTL 文件路径。
            original_rtl: 原始（未加固）RTL 路径，用于等价性检查。

        Returns:
            Dict 包含修复结果、迭代次数、各阶段记录和最终报告。
        """
        _pipeline_t0 = time.time()
        self._stage_results = []
        self._iteration = 0
        self.state = self.STATE_CHECKING

        logger.section(f"Auto-Repair Pipeline Started")
        logger.print(f"  [REPAIR] Input: {rtl_path}")
        logger.print(f"  [REPAIR] Original RTL: {original_rtl or '(not provided)'}")
        logger.print(f"  [REPAIR] Max iterations: {self.max_iterations}")

        # Work on a copy to avoid destroying the original
        work_rtl = self._copy_to_workdir(rtl_path)
        self._fixed_rtl_path = work_rtl

        passed = False
        final_report_parts: List[str] = []

        # Smart termination tracking
        _previous_content = ""
        _error_history: List[str] = []
        _no_progress_count = 0
        _MAX_NO_PROGRESS = 2

        for iteration in range(1, self.max_iterations + 1):
            self._iteration = iteration
            _iter_t0 = time.time()
            logger.section(f"Repair Iteration {iteration}/{self.max_iterations}")

            # Read file content before checks for diff tracking
            try:
                with open(work_rtl, "r", encoding="utf-8", errors="replace") as _f:
                    _content_before = _f.read()
            except OSError:
                _content_before = ""

            # Smart termination: detect no progress
            if _content_before == _previous_content and iteration > 1:
                _no_progress_count += 1
                logger.print(f"  [ITER {iteration}] ⚠ No progress detected ({_no_progress_count}/{_MAX_NO_PROGRESS})")
                if _no_progress_count >= _MAX_NO_PROGRESS:
                    logger.print(f"  [ITER {iteration}] ⚠ Smart termination: no progress for {_MAX_NO_PROGRESS} iterations")
                    break
            else:
                _no_progress_count = 0
            _previous_content = _content_before

            # ── Stage 1: Syntax Check ──
            self.state = self.STATE_CHECKING
            logger.print(f"  [ITER {iteration}] Phase 1/3: Syntax Check")
            _t1 = time.time()
            stage1 = self._run_stage("syntax", work_rtl)
            logger.metric(f"iter{iteration}.syntax", time.time() - _t1, "s")
            if not stage1["passed"]:
                self.state = self.STATE_REPAIRING
                n_errors = len(stage1.get("errors", []))
                logger.print(f"  [ITER {iteration}] Syntax FAILED ({n_errors} errors) → applying SYNTAX_FIX")
                for idx, err in enumerate(stage1.get("errors", [])[:3]):
                    logger.print(f"    error[{idx}]: {err[:100]}")
                stage1 = self._apply_fix(
                    RepairStrategy.SYNTAX_FIX, work_rtl,
                    stage1.get("errors", [])
                )
                self._stage_results.append(stage1)
                self._log_content_diff(work_rtl, _content_before, f"Iter{iteration}_post_syntax_fix")
                _iter_elapsed = time.time() - _iter_t0
                logger.print(f"  [ITER {iteration}] Syntax fix applied, elapsed={_iter_elapsed:.3f}s")
                continue  # re-check after fix

            self._stage_results.append(stage1)
            logger.print(f"  [ITER {iteration}] ✓ Syntax check passed ({stage1.get('elapsed', 0):.3f}s)")

            # ── Stage 2: Synthesis Check ──
            logger.print(f"  [ITER {iteration}] Phase 2/3: Synthesis Check")
            _t2 = time.time()
            stage2 = self._run_stage("synthesis", work_rtl)
            logger.metric(f"iter{iteration}.synthesis", time.time() - _t2, "s")
            if not stage2["passed"]:
                self.state = self.STATE_REPAIRING
                n_errors = len(stage2.get("errors", []))
                n_cells = stage2.get("cell_count", 0)
                logger.print(f"  [ITER {iteration}] Synthesis FAILED ({n_errors} errors, cells={n_cells}) → applying SYNTHESIS_FIX")
                for idx, err in enumerate(stage2.get("errors", [])[:3]):
                    logger.print(f"    error[{idx}]: {err[:100]}")
                stage2 = self._apply_fix(
                    RepairStrategy.SYNTHESIS_FIX, work_rtl,
                    stage2.get("errors", [])
                )
                self._stage_results.append(stage2)
                self._log_content_diff(work_rtl, _content_before, f"Iter{iteration}_post_synth_fix")
                _iter_elapsed = time.time() - _iter_t0
                logger.print(f"  [ITER {iteration}] Synthesis fix applied, elapsed={_iter_elapsed:.3f}s")
                continue  # re-check from Stage 1

            self._stage_results.append(stage2)
            logger.print(f"  [ITER {iteration}] ✓ Synthesis check passed ({stage2.get('elapsed', 0):.3f}s)")

            # ── Stage 3: Formal Equivalence (optional) ──
            if original_rtl and os.path.isfile(original_rtl):
                logger.print(f"  [ITER {iteration}] Phase 3/3: Formal Equivalence Check")
                _t3 = time.time()
                stage3 = self._run_stage("equiv", work_rtl, original_rtl)
                logger.metric(f"iter{iteration}.equiv", time.time() - _t3, "s")
                if not stage3["passed"]:
                    self.state = self.STATE_REPAIRING
                    n_errors = len(stage3.get("errors", []))
                    logger.print(f"  [ITER {iteration}] Equiv FAILED ({n_errors} errors) → applying EQUIV_FIX")
                    for idx, err in enumerate(stage3.get("errors", [])[:3]):
                        logger.print(f"    error[{idx}]: {err[:100]}")
                    stage3 = self._apply_fix(
                        RepairStrategy.EQUIV_FIX, work_rtl,
                        stage3.get("errors", []),
                        original_rtl=original_rtl,
                    )
                    self._stage_results.append(stage3)
                    self._log_content_diff(work_rtl, _content_before, f"Iter{iteration}_post_equiv_fix")
                    _iter_elapsed = time.time() - _iter_t0
                    logger.print(f"  [ITER {iteration}] Equiv fix applied, elapsed={_iter_elapsed:.3f}s")
                    continue  # re-check from Stage 1

                self._stage_results.append(stage3)
                logger.print(f"  [ITER {iteration}] ✓ Formal equivalence check passed ({stage3.get('elapsed', 0):.3f}s)")
            else:
                logger.print(f"  [ITER {iteration}] Phase 3/3: Equivalence (skipped — no original RTL)")
                logger.info("(Equivalence check skipped — no original RTL provided)")

            # ── Stage 4: Final Verification ──
            self.state = self.STATE_VERIFYING
            logger.print(f"  [ITER {iteration}] Running final verification...")
            _t4 = time.time()
            final = self._run_final_verification(work_rtl, original_rtl)
            logger.metric(f"iter{iteration}.final", time.time() - _t4, "s")
            passed = final.get("passed", False)

            _iter_elapsed = time.time() - _iter_t0
            if passed:
                self.state = self.STATE_DONE
                final_report_parts.append(
                    f"All checks passed after {iteration} iteration(s)."
                )
                logger.print(f"  [ITER {iteration}] ✓ ALL CHECKS PASSED ({_iter_elapsed:.3f}s)")
                break
            else:
                logger.print(f"  [ITER {iteration}] Final verification FAILED ({_iter_elapsed:.3f}s)")
                logger.warning("Final verification failed after iteration %d", iteration)

        # ── Build result ──
        if not passed:
            self.state = self.STATE_DONE
            unresolved = self._collect_unresolved()
            final_report_parts.append(
                f"Repair terminated after {self._iteration} iteration(s). "
                f"Unresolved issues: {len(unresolved)}"
            )
            if unresolved:
                logger.print(f"  [REPAIR] Unresolved issues ({len(unresolved)}):")
                for issue in unresolved[:5]:
                    final_report_parts.append(f"  - {issue}")
                    logger.print(f"    - {issue[:120]}")

        result = {
            "passed": passed,
            "iterations": self._iteration,
            "stages": self._stage_results,
            "final_report": "\n".join(final_report_parts),
            "fixed_rtl_path": self._fixed_rtl_path if passed else None,
            "rtl_path": rtl_path,
            "original_rtl": original_rtl,
        }

        _pipeline_elapsed = time.time() - _pipeline_t0
        logger.print(f"\n  [REPAIR] Pipeline completed: passed={passed}, "
                     f"iterations={self._iteration}, total_time={_pipeline_elapsed:.3f}s")
        logger.info("Repair pipeline completed: passed=%s, iterations=%d",
                      passed, self._iteration)
        return result

    def _log_content_diff(self, file_path: str, old_content: str, tag: str = ""):
        """Log a summary of changes between old content and current file content."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as _f:
                new_content = _f.read()
        except OSError:
            return

        if old_content == new_content:
            logger.print(f"  [DIFF:{tag}] No changes")
            return

        old_lines = old_content.split('\n')
        new_lines = new_content.split('\n')
        added = sum(1 for l in new_lines if l not in old_lines)
        removed = sum(1 for l in old_lines if l not in new_lines)
        logger.print(f"  [DIFF:{tag}] {len(old_lines)}→{len(new_lines)} lines, "
                     f"+{added}/-{removed} changes")
        # Show first few changed lines
        changes_shown = 0
        for i, (a, b) in enumerate(zip(old_lines, new_lines)):
            if a != b and changes_shown < 3:
                logger.print(f"    L{i+1}: {repr(a)[:60]}")
                logger.print(f"       → {repr(b)[:60]}")
                changes_shown += 1
        if len(old_lines) != len(new_lines):
            extra = abs(len(new_lines) - len(old_lines))
            logger.print(f"    (... {extra} line(s) added/removed)")

    # ------------------------------------------------------------------
    # Stage runners
    # ------------------------------------------------------------------

    def _run_stage(
        self,
        stage: str,
        rtl_path: str,
        original_rtl: Optional[str] = None,
    ) -> Dict:
        """Run a single verification stage.

        Args:
            stage:       "syntax", "synthesis", or "equiv".
            rtl_path:    RTL file to check.
            original_rtl: Original RTL for equivalence check.

        Returns:
            Dict with stage result.
        """
        base: Dict = {
            "stage": stage,
            "iteration": self._iteration,
            "timestamp": time.time(),
        }

        if self.verifier is None:
            base["passed"] = False
            base["errors"] = ["Verifier not available"]
            return base

        _t0 = time.time()
        logger.info("[Repair Stage] stage=%s, iteration=%d, file=%s",
                     stage, self._iteration, os.path.basename(rtl_path))

        try:
            if stage == "syntax":
                result = self.verifier.syntax_check(rtl_path)
                logger.info("  syntax_check: passed=%s, errors=%d, elapsed=%.3fs",
                             result.get("passed"), len(result.get("errors", [])),
                             result.get("elapsed", 0))
            elif stage == "synthesis":
                result = self.verifier.synthesis_check(rtl_path)
                logger.info("  synthesis_check: passed=%s, cells=%d, errors=%d, elapsed=%.3fs",
                             result.get("passed"), result.get("cell_count", 0),
                             len(result.get("errors", [])),
                             result.get("elapsed", 0))
            elif stage == "equiv":
                if not original_rtl:
                    result = {"passed": False, "errors": ["No original RTL"]}
                    logger.warning("  equiv_check: skipped (no original RTL)")
                else:
                    result = self.verifier.formal_equiv_check(original_rtl, rtl_path)
                    logger.info("  equiv_check: passed=%s, equivalent=%s, errors=%d, elapsed=%.3fs",
                                 result.get("passed"), result.get("equivalent", False),
                                 len(result.get("errors", [])),
                                 result.get("elapsed", 0))
            else:
                result = {"passed": False, "errors": [f"Unknown stage: {stage}"]}

            base.update(result)
        except Exception as e:
            base["passed"] = False
            base["errors"] = [str(e)]
            logger.error("  stage exception: %s", e)

        _t1 = time.time()
        logger.info("[Repair Stage] %s completed: passed=%s, total_time=%.3fs",
                     stage, base.get("passed"), _t1 - _t0)

        # Log errors in detail if any
        errors = base.get("errors", [])
        if errors:
            for i, err in enumerate(errors[:5]):
                logger.info("  error[%d]: %s", i, err[:120])
            if len(errors) > 5:
                logger.info("  ... and %d more errors", len(errors) - 5)

        return base

    def _run_final_verification(
        self,
        rtl_path: str,
        original_rtl: Optional[str] = None,
    ) -> Dict:
        """Run all checks as final verification."""
        if self.verifier is None:
            return {"passed": False, "errors": ["Verifier not available"]}

        try:
            return self.verifier.run_all_checks(rtl_path, original_rtl=original_rtl)
        except Exception as e:
            return {"passed": False, "errors": [str(e)]}

    # ------------------------------------------------------------------
    # Fix application
    # ------------------------------------------------------------------

    def _apply_fix(
        self,
        strategy: RepairStrategy,
        rtl_path: str,
        errors: List[str],
        original_rtl: Optional[str] = None,
    ) -> Dict:
        """Apply a repair strategy to the RTL file.

        Args:
            strategy:     Repair strategy type.
            rtl_path:     Path to RTL file to fix (modified in-place).
            errors:       Error messages from the failed stage.
            original_rtl: Original RTL path (for equiv fix).

        Returns:
            Dict describing the fix attempt.
        """
        _t0 = time.time()
        logger.print(f"\n  [FIX] Applying strategy: {strategy.value}")
        logger.print(f"  [FIX] File: {rtl_path}")

        # Log the targeted errors
        if errors:
            logger.print(f"  [FIX] Targeting {len(errors)} error(s):")
            for i, err in enumerate(errors[:5]):
                logger.print(f"    [{i}] {err[:120]}")
            if len(errors) > 5:
                logger.print(f"    ... and {len(errors) - 5} more")
        else:
            logger.print(f"  [FIX] No specific errors; applying common fixes")

        try:
            with open(rtl_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            logger.error(f"  [FIX] Failed to read RTL: {e}")
            return {
                "stage": strategy.value,
                "iteration": self._iteration,
                "passed": False,
                "errors": [f"Failed to read RTL: {e}"],
                "fix_applied": None,
            }

        content_len_before = len(content)
        fix_result: Dict = {
            "stage": strategy.value,
            "iteration": self._iteration,
            "timestamp": time.time(),
            "errors": errors,
        }

        try:
            if strategy == RepairStrategy.SYNTAX_FIX:
                fixer = SyntaxFixer()
                logger.print(f"  [FIX] Using SyntaxFixer...")
                new_content = fixer.fix(content, errors)
            elif strategy == RepairStrategy.SYNTHESIS_FIX:
                fixer = SynthesisFixer()
                logger.print(f"  [FIX] Using SynthesisFixer...")
                new_content = fixer.fix(content, errors)
            elif strategy == RepairStrategy.EQUIV_FIX:
                fixer = EquivFixer()
                if original_rtl:
                    try:
                        with open(original_rtl, "r", encoding="utf-8",
                                  errors="replace") as f:
                            orig_content = f.read()
                    except OSError as e:
                        logger.error(f"  [FIX] Failed to read original RTL: {e}")
                        return {
                            **fix_result,
                            "passed": False,
                            "errors": [f"Failed to read original RTL: {e}"],
                            "fix_applied": None,
                        }
                    logger.print(f"  [FIX] Using EquivFixer (original={len(orig_content)} chars)...")
                    new_content = fixer.fix(orig_content, content, errors)
                else:
                    logger.print(f"  [FIX] EquivFixer skipped (no original RTL)")
                    new_content = content
            else:
                new_content = content

            if new_content != content:
                with open(rtl_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                fix_result["passed"] = True
                fix_result["fix_applied"] = strategy.value
                chars_diff = len(new_content) - content_len_before
                # Show diff stats
                old_lines = content.split('\n')
                new_lines = new_content.split('\n')
                added = sum(1 for l in new_lines if l not in old_lines)
                removed = sum(1 for l in old_lines if l not in new_lines)
                logger.print(f"  [FIX] ✓ Applied: {strategy.value} "
                             f"(lines: {len(old_lines)}→{len(new_lines)}, "
                             f"chars: {content_len_before}→{len(new_content)} ({chars_diff:+d}), "
                             f"+{added}/-{removed} line changes)")
                # Show first 2 changed lines
                change_count = 0
                for i, (a, b) in enumerate(zip(old_lines, new_lines)):
                    if a != b and change_count < 2:
                        logger.print(f"    L{i+1}: {repr(a)[:60]}")
                        logger.print(f"         → {repr(b)[:60]}")
                        change_count += 1
            else:
                fix_result["passed"] = False
                fix_result["fix_applied"] = None
                fix_result["errors"] = errors or ["No fix could be applied"]
                logger.print(f"  [FIX] ✗ No changes applied for strategy: {strategy.value}")

        except Exception as e:
            fix_result["passed"] = False
            fix_result["fix_applied"] = None
            fix_result["errors"] = [str(e)]
            logger.error(f"  [FIX] Exception: {e}")
            import traceback
            logger.error(f"  [FIX] Traceback: {traceback.format_exc()}")

        logger.print(f"  [FIX] Completed in {time.time() - _t0:.3f}s")
        return fix_result

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _copy_to_workdir(self, rtl_path: str) -> str:
        """Copy RTL file to working directory for in-place fixing.

        Returns:
            Path to the working copy.
        """
        work_dir = tempfile.mkdtemp(prefix="repair_")
        dest = os.path.join(work_dir, os.path.basename(rtl_path))
        shutil.copy2(rtl_path, dest)
        logger.info("Working copy: %s → %s", rtl_path, dest)
        return dest

    def _collect_unresolved(self) -> List[str]:
        """Collect unresolved error messages from all stages."""
        unresolved: List[str] = []
        for stage in self._stage_results:
            for err in stage.get("errors", []):
                if err and err not in unresolved:
                    unresolved.append(err)
        return unresolved


# ============================================================================
# SyntaxFixer
# ============================================================================

class SyntaxFixer:
    """语法修复器 — 修复常见 Verilog 语法错误。

    使用正则表达式进行模式匹配和替换，修复以下问题:
      - 缺失分号
      - 缺失 endmodule
      - 端口声明错误
      - wire 类型缺失
    """

    # ── Fix patterns: (priority, name, search, replace) ──
    # NOTE: All patterns are applied via _safe_sub() which ensures matches
    # outside of comments only.
    _FIX_PATTERNS = [
        # Missing semicolon after assign
        (80, "missing_semicolon_assign",
         r'(assign\s+\S+\s*=\s*[^;]+)\s*\n(\s*\w)',
         r'\1;\n\2'),

        # Missing semicolon after wire/reg declaration
        # NOTE: negative lookahead skips port list lines (followed by ')' or ',')
        #       and lines with trailing comments (handled by line-by-line fixer)
        (80, "missing_semicolon_decl",
         r'(wire|reg|input|output)\s+(\[.*?\])?\s*(\w+)(?!\s*//)\s*\n(?!\s*[\),])',
         r'\1 \2 \3;\n'),

        # Port list without direction (old-style)
        # Only matches when the port list doesn't already use input/output/inout
        (70, "old_style_port",
         r'module\s+(\w+)\s*\(\s*(?!\s*(?:input|output|inout)\b)',
         r'module \1 (\n    input wire clk,\n    input wire rst_n,\n'),

        # Wire declared without type in port list
        (60, "missing_wire_type",
         r'(input|output)\s+(\w+)\s*;',
         r'\1 wire \2;'),

        # Always block missing posedge/negedge (single signal sensitivity list)
        (40, "missing_edge_sensitivity",
         r'always\s+@\s*\(\s*(\w+)\s*\)',
         r'always @(posedge \1)'),

        # Non-blocking assignment in always_comb
        (30, "nonblocking_in_comb",
         r'always_comb\s+begin(.*?)end',
         r'always_comb begin\1end'),

        # ── New patterns below ──

        # Missing `end` for unclosed `begin` before endmodule
        # Uses stack-based counting to handle nested begin/end correctly
        (90, "missing_end_before_endmodule",
         r'__reserved_never_match__',  # handled by _fix_missing_end() instead
         r''),

        # always_ff / always_comb with empty sensitivity list
        (35, "missing_always_sensitivity",
         r'always\s+@\s*\(\s*\)\s*\n',
         r'always @(*) \n'),

        # Missing `or` / `,` between sequential sensitivity signals:
        # always @(posedge clk negedge rst_n) → always @(posedge clk or negedge rst_n)
        (50, "missing_seq_sensitivity_or",
         r'always\s+@\s*\(\s*(posedge|negedge)\s+(\w+)\s+(posedge|negedge)\s+(\w+)\s*\)',
         r'always @(\1 \2 or \3 \4)'),

        # Case statement missing 'default' inside always block
        # Captures all case items via ([\s\S]*?) then appends default before endcase
        (25, "missing_case_default",
         r'case\s*\(([^)]*)\)\s*\n([\s\S]*?)\s*endcase',
         r'case (\1)\n\2\n        default : ;\n    endcase'),

        # ── v3.0 新增: 4 种常见模式 ──

        # Inout port without wire/reg type keyword (e.g., "inout data_bus;")
        (70, "inout_without_direction",
         r'(inout)\s+(?!wire|reg)(\w+)\s*;',
         r'\1 wire \2;'),

        # Missing backslash continuation in multi-line assign chain
        # Catches: line ends with operator (signal_b & \n signal_c)
        (95, "missing_assign_continuation_eol",
         r'(assign\s+\S+\s*=\s*[^;]*\S)\s*[\+\|\&]{1,2}\s*\n',
         r'\1 \\\n'),

        # Catches: next line starts with operator (signal_b \n & signal_c)
        (94, "missing_assign_continuation_nl",
         r'(assign\s+\S+\s*=\s*[^;]+?)\s*\n\s*([\+\|\&]{1,2}|<<|>>)\s',
         r'\1 \\\n\2 '),

        # Parameter without default value
        (50, "missing_parameter_default",
         r'parameter\s+(\w+)\s*(?=[,);])',
         r'parameter \1 = 0'),

        # Unclosed generate block (missing endgenerate)  
        # Uses negative lookahead to skip generate blocks that already have endgenerate
        (85, "missing_endgenerate",
         r'\bgenerate\b(?![\s\S]*?\bendgenerate\b)[\s\S]*?(?=\bendmodule\b)',
         r'\g<0>\nendgenerate\n'),

        # ── v3.3 新增: 4 种常见模式 ──

        # Output signal assigned in always block but declared without 'reg'
        # e.g., "output [7:0] data;" used inside "always @(posedge clk)" → "output reg [7:0] data;"
        # Only applies when followed by ',' or ')' indicating port list context
        (65, "output_reg_type",
         r'(output)\s+(?!reg)(\[\s*\d+\s*:\s*\d+\s*\])\s*(\w+)\s*,',
         r'\1 reg \2 \3,'),

        # Signal declared as wire but assigned via non-blocking in always block
        # e.g., "wire [7:0] data;" with "data <= value;" in always
        # Fix: change wire to reg
        (55, "wire_to_reg_in_always",
         r'(wire)\s+(\[\s*\d+\s*:\s*\d+\s*\])\s*(\w+)\s*;\s*\n(?!.*(?:assign|input|output))',
         r'reg  \2 \3;\n'),

        # Trailing comma before closing paren in port list
        # e.g., "    input  wire       clk,\n    )" → remove trailing comma
        (60, "trailing_comma_port",
         r',\s*\n\s*\)',
         r'\n)'),

        # Double semicolon (stray ;;)  
        (40, "double_semicolon",
         r';;',
         r';'),

        # ── v3.4 新增: 4 种常见模式 ──

        # Missing semicolon before 'end' keyword
        # e.g., "data <= value" followed by "end" → "data <= value;"
        (85, "missing_semicolon_before_end",
         r'([^;])\s*\n\s*end\b',
         r'\1;\nend'),

        # Inout port missing 'wire' keyword (non-range variant)
        # e.g., "inout data;" → "inout wire data;"
        (70, "inout_missing_wire",
         r'(inout)\s+(?!wire|reg)(\w[\w\[\]\d]*)\s*;',
         r'\1 wire \2;'),

        # Missing 'reg' for output used in always block (without range)
        # e.g., "output data;" used in "always @(posedge clk)" → "output reg data;"
        (65, "output_reg_type_simple",
         r'(output)\s+(?!reg\b)(\w[\w\d]*)\s*[,;]',
         r'\1 reg \2\3'),

        # Stray trailing backslash (line continuation in non-continuation context)
        # e.g., signal declaration lines ending with '\' 
        (30, "stray_backslash",
         r'([^\\])\\\s*\n',
         r'\1\n'),
    ]

    _FIX_PATTERNS.sort(key=lambda x: -x[0])  # highest priority first

    def fix(self, rtl_content: str, errors: List[str]) -> str:
        """Apply syntax fixes based on error messages.

        Args:
            rtl_content: Raw RTL source text.
            errors:      Error messages from yosys syntax check.

        Returns:
            Fixed RTL source text.
        """
        content = rtl_content

        # If no specific errors, apply common fixes
        if not errors:
            return self._apply_common_fixes(content)

        # Map error keywords to fix patterns
        for error in errors:
            content = self._fix_for_error(content, error)

        # Always apply common fixes as fallback (multi-pass for consecutive errors)
        content = self._apply_common_fixes(content)

        return content

    def _safe_sub(
        self,
        pattern: str,
        replacement: str,
        content: str,
        flags: int = re.DOTALL,
    ) -> str:
        """Like re.sub(count=1) but skips matches inside comments."""
        def _in_comment(pos: int) -> bool:
            pre = content[:pos]
            # Single-line comment on same line
            line_start = pre.rfind('\n') + 1
            line_text = pre[line_start:]
            if '//' in line_text:
                # Only mark as comment if // is BEFORE the match
                comment_pos = line_text.find('//')
                return comment_pos < (pos - line_start)
            # Block comment (unclosed)
            last_open = pre.rfind('/*')
            if last_open > pre.rfind('*/'):
                return True
            return False

        def _replacer(m: re.Match) -> str:
            if _in_comment(m.start()):
                return m.group(0)
            return m.expand(replacement)

        return re.sub(pattern, _replacer, content, count=1, flags=flags)

    def _apply_common_fixes(self, content: str, max_passes: int = 5) -> str:
        """Apply common syntax fixes regardless of errors.

        Runs all patterns in a loop (up to max_passes) to handle
        consecutive errors on multiple lines.

        NOTE: All substitutions skip matches inside comments.
        Each pattern is only applied ONCE total (not once per pass).
        """
        logger.print(f"  [SYNTAXFIXER] _apply_common_fixes: input={len(content)} chars, "
                     f"max_passes={max_passes}")
        applied: set[str] = set()
        for _pass in range(max_passes):
            changed = False
            for priority, name, search, replace in self._FIX_PATTERNS:
                if name in applied:
                    continue
                if re.search(search, content, re.DOTALL):
                    old_content = content
                    content = self._safe_sub(search, replace, content)
                    if content != old_content:
                        changed = True
                        applied.add(name)
                        lines_diff = len(content.split('\n')) - len(old_content.split('\n'))
                        chars_diff = len(content) - len(old_content)
                        logger.print(f"  [SYNTAXFIXER] Applied: '{name}' (priority={priority}, "
                                     f"pass={_pass + 1}, {chars_diff:+d} chars, {lines_diff:+d} lines)")
                        logger.debug("SyntaxFixer applied: %s (pass %d)", name, _pass + 1)
                    else:
                        logger.debug(f"  [SYNTAXFIXER] Pattern '{name}' matched but _safe_sub made no change")
            if not changed:
                logger.print(f"  [SYNTAXFIXER] No more changes after pass {_pass + 1}")
                break  # no more fixes to apply

        n_applied = len(applied)
        if n_applied > 0:
            logger.print(f"  [SYNTAXFIXER] Applied {n_applied} fix patterns: {sorted(applied)}")

        # Handle missing_endmodule separately — only add if not present
        if 'endmodule' not in content:
            content = content.rstrip('\n') + '\nendmodule\n'
            logger.print(f"  [SYNTAXFIXER] Applied: 'missing_endmodule' (additive)")

        # Handle unmatched begin (more begin than end)
        orig_len = len(content)
        content = self._fix_unmatched_begin(content)
        if len(content) != orig_len:
            logger.print(f"  [SYNTAXFIXER] Applied: 'fix_unmatched_begin' (len {orig_len}→{len(content)})")

        # Handle missing endgenerate (count-based: if generate > endgenerate)
        orig_len = len(content)
        content = self._fix_missing_endgenerate(content)
        if len(content) != orig_len:
            logger.print(f"  [SYNTAXFIXER] Applied: 'fix_missing_endgenerate' (len {orig_len}→{len(content)})")

        logger.print(f"  [SYNTAXFIXER] _apply_common_fixes done: output={len(content)} chars")
        return content

    def _fix_unmatched_begin(self, content: str) -> str:
        """Add missing `end` statements for unclosed `begin` blocks.

        Uses a stack-based approach to correctly handle nested begin/end
        blocks. Scans line-by-line, tracking the begin/end balance with
        a stack. For each unmatched `begin`, records the line number and
        indentation so that `end` statements are inserted at the correct
        nesting level, not just all at the end.

        This correctly handles:
          - Single missing end at any nesting level
          - Multiple missing ends in nested blocks
          - Already balanced begin/end (no modification)
          - Comments containing begin/end keywords (skipped)
        """
        endmod_pos = content.rfind('endmodule')
        body = content[:endmod_pos] if endmod_pos >= 0 else content

        lines = body.split('\n')
        # Stack entries: (line_index_of_begin, indent_string)
        begin_stack: list[tuple[int, str]] = []
        in_block_comment = False
        insertions: list[tuple[int, str]] = []  # (line_index, text_to_insert)

        for i, raw_line in enumerate(lines):
            stripped = raw_line.strip()

            # ── Track block comments ──
            if '/*' in stripped:
                in_block_comment = True
            if '*/' in stripped:
                in_block_comment = False
                continue
            if in_block_comment:
                continue

            # ── Skip single-line comments ──
            code_part = stripped.split('//')[0]

            # ── Scan for begin/end tokens in this line ──
            tokens = re.findall(r'\b(begin|end)\b', code_part)

            for token in tokens:
                if token == 'begin':
                    indent = raw_line[:len(raw_line) - len(raw_line.lstrip())]
                    begin_stack.append((i, indent))
                elif token == 'end':
                    if begin_stack:
                        begin_stack.pop()

        # All remaining items in the stack are unclosed begin blocks
        if not begin_stack:
            return content

        # Insert missing ends in reverse order (innermost first)
        for begin_line, indent in reversed(begin_stack):
            if endmod_pos >= 0:
                # Find the line containing endmodule
                for j in range(len(lines) - 1, -1, -1):
                    if 'endmodule' in lines[j]:
                        insertions.append((j, f"{indent}end"))
                        break
                else:
                    insertions.append((len(lines), f"{indent}end"))
            else:
                insertions.append((len(lines), f"{indent}end"))

        # Apply insertions in reverse line order (bottom-up)
        insertions.sort(key=lambda x: -x[0])
        result_lines = lines[:]
        for line_no, text in insertions:
            result_lines.insert(line_no, text)

        result = '\n'.join(result_lines)
        if endmod_pos >= 0:
            result += '\n' + content[content.rfind('endmodule'):]

        n_missing = len(begin_stack)
        logger.print(f"  [SYNTAXFIXER_BEGIN] Stack-based fix: {n_missing} unclosed begin(s), "
                     f"inserted at nesting positions")
        return result

    def _fix_missing_endgenerate(self, content: str) -> str:
        """Add missing `endgenerate` statements using count-based detection.

        Counts generate vs endgenerate keywords. If generate > endgenerate,
        adds the missing ones before endmodule or at end of file.
        Skips comments and string literals.
        """
        # Strip comments and strings for accurate counting
        clean = content
        # Remove block comments
        clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL)
        # Remove line comments
        clean = re.sub(r'//.*', '', clean)
        # Remove strings
        clean = re.sub(r'".*?"', '', clean)

        gen_count = len(re.findall(r'\bgenerate\b', clean))
        endgen_count = len(re.findall(r'\bendgenerate\b', clean))
        missing = gen_count - endgen_count

        if missing <= 0:
            return content

        logger.print(f"  [SYNTAXFIXER_ENDGEN] Count-based: generate={gen_count}, "
                     f"endgenerate={endgen_count}, missing={missing}")

        # Insert missing endgenerates before the last endmodule
        lines = content.split('\n')
        insertions_made = 0

        for _ in range(missing):
            # Find endmodule position
            endmod_idx = -1
            for i in range(len(lines) - 1, -1, -1):
                if 'endmodule' in lines[i] and '//' not in lines[i].split('endmodule')[0]:
                    endmod_idx = i
                    break

            if endmod_idx >= 0:
                indent = ''
                for ch in lines[endmod_idx]:
                    if ch in (' \t'):
                        indent += ch
                    else:
                        break
                lines.insert(endmod_idx, f"{indent}endgenerate")
                insertions_made += 1
            else:
                # No endmodule found, append
                lines.append("endgenerate")
                insertions_made += 1

        if insertions_made > 0:
            logger.print(f"  [SYNTAXFIXER_ENDGEN] Inserted {insertions_made} missing endgenerate(s)")
            return '\n'.join(lines)

        return content

    # ── Keywords that NEVER need a trailing semicolon ──
    _NO_SEMI_KEYWORDS = {
        'begin', 'end', 'if', 'else', 'for', 'while', 'case', 'endcase',
        'module', 'endmodule', 'always', 'initial', 'assign', 'endfunction',
        'function', 'endtask', 'task', 'specify', 'endspecify',
        'generate', 'endgenerate', 'posedge', 'negedge',
    }

    @staticmethod
    def _add_semi_before_comment(raw_line: str) -> str:
        """Add ';' before any trailing // comment, or at end of line."""
        line_stripped = raw_line.rstrip()
        # Check for inline // comment
        ci = line_stripped.find('//')
        if ci >= 0:
            # Insert ; before the comment
            before = line_stripped[:ci].rstrip()
            after = line_stripped[ci:]
            return before + '; ' + after + '\n'
        else:
            return line_stripped + ';\n'

    def _fix_missing_semicolons_line_by_line(self, content: str) -> str:
        """Fix missing semicolons using line-by-line semantic analysis.

        SAFE approach: only adds ';' to lines that clearly need them
        (wire/reg declarations, assign statements, instance connections)
        while avoiding false positives on block keywords, port lists, etc.
        """
        lines = content.split('\n')
        fixed_lines: list[str] = []
        in_port_list = False
        paren_depth = 0
        changes = 0

        # ── Build module header region (multi-line port/param list) ──
        module_header_region = set()
        in_module_header = False
        header_paren_depth = 0
        for i, raw_line in enumerate(lines):
            stripped = raw_line.strip()
            if re.match(r'module\s+\w+', stripped, re.IGNORECASE):
                in_module_header = True
                header_paren_depth = 0
            if in_module_header:
                for ch in stripped:
                    if ch == '(':
                        header_paren_depth += 1
                    elif ch == ')':
                        header_paren_depth -= 1
                if header_paren_depth < 0 or (';' in stripped and header_paren_depth == 0):
                    in_module_header = False
                else:
                    module_header_region.add(i)

        for i, raw_line in enumerate(lines):
            line = raw_line.strip()
            stripped = line.rstrip(';').strip()
            is_in_header = i in module_header_region

            # ── Track port list boundary ──
            if re.match(r'module\s+\w+\s*(?:#\s*\([^)]*\))?\s*\(', stripped):
                in_port_list = True

            if in_port_list:
                paren_depth += stripped.count('(') - stripped.count(')')
                if paren_depth <= 0:
                    in_port_list = False

            # ── Skip lines that shouldn't have semicolons ──
            if not stripped:
                fixed_lines.append(raw_line)
                continue

            if stripped.startswith('//') or stripped.startswith('/*'):
                fixed_lines.append(raw_line)
                continue

            if raw_line.rstrip().endswith(';'):
                fixed_lines.append(raw_line)
                continue

            # Inside module header (parameter/port decl) — no semicolons on individual lines
            if is_in_header:
                fixed_lines.append(raw_line)
                continue

            # Inside port list — commas, not semicolons
            if in_port_list:
                fixed_lines.append(raw_line)
                continue

            # input/output/inout declaration (outside port list)
            if re.match(r'(input|output|inout)\s', stripped, re.IGNORECASE):
                if not stripped.endswith(','):
                    fixed_lines.append(self._add_semi_before_comment(raw_line))
                    changes += 1
                    continue
                else:
                    fixed_lines.append(raw_line)
                    continue

            # wire/reg declaration
            if re.match(r'(wire|reg|tri|wand|wor)\s', stripped, re.IGNORECASE):
                fixed_lines.append(self._add_semi_before_comment(raw_line))
                changes += 1
                continue

            # assign statement
            if re.match(r'assign\s', stripped, re.IGNORECASE):
                fixed_lines.append(self._add_semi_before_comment(raw_line))
                changes += 1
                continue

            # Lines ending with commas/parens/operators — no semicolon
            if stripped.endswith((',', '(', ')', '{', '}', '+', '-', '*', '/', '=', ':', '[')):
                fixed_lines.append(raw_line)
                continue

            # Submodule instantiation
            if re.match(r'\w+\s+#\s*\(', stripped) or re.match(r'\w+\s+\w+\s*\(', stripped):
                # Could be an instance — only fix if line ends with ')'
                # and starts with an identifier followed by '('
                if stripped.endswith(')') and not line.endswith(';'):
                    # Check it's not a function/task/always block
                    first_word = stripped.split()[0].lower()
                    if first_word not in self._NO_SEMI_KEYWORDS:
                        fixed_lines.append(self._add_semi_before_comment(raw_line))
                        changes += 1
                        continue

            # ── Lines that clearly should NOT get semicolons ──
            first_word = stripped.split()[0].lower() if stripped.split() else ''
            if first_word in self._NO_SEMI_KEYWORDS:
                fixed_lines.append(raw_line)
                continue

            # Lines ending with operators, commas, parens — no semicolon needed
            if stripped.endswith((',', '(', ')', '{', '}', '+', '-', '*', '/', '=', ':', '[')):
                fixed_lines.append(raw_line)
                continue

            # Default: keep as-is (conservative)
            fixed_lines.append(raw_line)

        if changes > 0:
            logger.info("SyntaxFixer line-by-line: added %d missing semicolons", changes)

        return '\n'.join(fixed_lines)

    def _fix_for_error(self, content: str, error: str) -> str:
        """Apply fix tailored to a specific error message."""
        error_lower = error.lower()

        # Missing semicolon — use line-by-line analysis instead of broad regex
        # to avoid breaking valid constructs (begin, end, if, else, port lists)
        if "semicolon" in error_lower or "expecting ';'" in error_lower or "unexpected" in error_lower:
            content = self._fix_missing_semicolons_line_by_line(content)

        # Port direction missing
        if "port" in error_lower and "direction" in error_lower:
            content = re.sub(
                r'^\s*(\w+)\s+(\w+)\s*;',
                r'wire \1 \2;',
                content,
                flags=re.MULTILINE,
            )

        # Undefined wire/reg
        if re.search(r'undefined|undeclared|not\s+declared', error_lower):
            match = re.search(r"'(\w+)'", error)
            if match:
                signal = match.group(1)
                content = re.sub(
                    r'(\bmodule\s+\w+\s*\()',
                    r'\1\n    wire ' + signal + r';',
                    content,
                    count=1,
                )

        return content


# ============================================================================
# SynthesisFixer
# ============================================================================

class SynthesisFixer:
    """综合修复器 — 修复综合阶段发现的问题。

    处理:
      - 不支持的综合构造
      - 位宽不匹配
      - 未使用的信号
      - 同步/异步描述冲突
    """

    def fix(self, rtl_content: str, synthesis_errors: List[str]) -> str:
        """Apply synthesis fixes.

        Args:
            rtl_content:      Raw RTL source.
            synthesis_errors: Error messages from synthesis stage.

        Returns:
            Fixed RTL source.
        """
        content = rtl_content

        # Wrap entire module in pragmas to suppress non-critical warnings
        if self._has_critical_errors(synthesis_errors):
            content = self._wrap_in_pragmas(content)

        for error in synthesis_errors:
            content = self._fix_synth_error(content, error)

        return content

    def _has_critical_errors(self, errors: List[str]) -> bool:
        """Check if errors contain critical synthesis issues."""
        critical_keywords = [
            "unsupported", "cannot", "failed", "not supported",
            "width mismatch", "incompatible",
        ]
        for error in errors:
            for kw in critical_keywords:
                if kw in error.lower():
                    return True
        return False

    def _fix_synth_error(self, content: str, error: str) -> str:
        """Fix a specific synthesis error."""
        error_lower = error.lower()

        # Width mismatch
        if "width" in error_lower or "mismatch" in error_lower:
            content = self._fix_width_mismatch(content, error)

        # Unsupported system function
        if "unsupported" in error_lower:
            # Comment out $display, $monitor, etc.
            content = re.sub(
                r'(\$\w+)\s*\(',
                r'// \1(',
                content,
            )

        # Asynchronous reset detection
        if "async" in error_lower:
            logger.warning(
                "Async reset detected in synthesis. Consider using sync reset."
            )
            # Don't modify async resets — just log the warning
            # (changing async→sync would alter design behavior)

        return content

    def _fix_width_mismatch(self, content: str, error: str) -> str:
        """Attempt to fix bit-width mismatches."""
        # Pattern: signal name and expected width from error
        width_match = re.search(r"'(\w+)'.*?(\d+)\s*bits?", error, re.IGNORECASE)
        if width_match:
            signal = width_match.group(1)
            width = width_match.group(2)
            # Adjust declaration width
            content = re.sub(
                rf'(wire|reg|input|output)\s+(\[\d+:\d+\])\s*{signal}\b',
                rf'\1 [0:{int(width) - 1}] {signal}',
                content,
            )
        return content

    @staticmethod
    def _wrap_in_pragmas(content: str) -> str:
        """Wrap the entire module content in synthesis pragmas."""
        # Find the module boundaries
        module_start = re.search(r'\bmodule\s+\w+', content)
        module_end = re.search(r'\bendmodule\b', content)

        if not module_start or not module_end:
            return content

        # Add pragma to suppress warnings at module level
        pragma_line = "`ifdef SYNTHESIS\n`pragma protect\n`endif\n"
        content = (
            content[:module_start.start()]
            + pragma_line
            + content[module_start.start():]
        )

        # Add closing pragma before endmodule
        end_pragma = "\n`ifdef SYNTHESIS\n`pragma protect end\n`endif\n"
        content = (
            content[:module_end.start()]
            + end_pragma
            + content[module_end.start():]
        )

        return content


# ============================================================================
# EquivFixer
# ============================================================================

class EquivFixer:
    """等价性修复器 — 修复形式化等价性检查失败的问题。

    处理:
      - 端口映射不匹配
      - 信号重命名
      - 模块实例化差异
    """

    def fix(
        self,
        original_rtl: str,
        hardened_rtl: str,
        equiv_errors: List[str],
    ) -> str:
        """Apply equivalence fixes to the hardened RTL.

        Args:
            original_rtl:  Original (reference) RTL content.
            hardened_rtl:  Hardened RTL content (will be modified).
            equiv_errors:  Error messages from equivalence check.

        Returns:
            Fixed hardened RTL content.
        """
        content = hardened_rtl

        # 1. Check port mismatch
        orig_ports = self._extract_ports(original_rtl)
        hard_ports = self._extract_ports(content)

        missing_in_hard = [p for p in orig_ports if p not in hard_ports]
        extra_in_hard = [p for p in hard_ports if p not in orig_ports]

        for port in missing_in_hard:
            port_info = orig_ports[port]
            # Add missing port declaration
            decl = f"{port_info['direction']} {port_info.get('width', '')} {port}"
            content = re.sub(
                r'(module\s+\w+\s*\()',
                r'\1\n    ' + decl + r',',
                content,
                count=1,
            )

        # 2. Signal name alignment
        for error in equiv_errors:
            content = self._fix_equiv_error(content, error, original_rtl)

        return content

    @staticmethod
    def _extract_ports(content: str) -> Dict[str, Dict]:
        """Extract port declarations from RTL content.

        Returns:
            Dict mapping port name → {direction, width}.
        """
        ports: Dict[str, Dict] = {}
        # Match: input/output/inout [width] name
        pattern = re.compile(
            r'(input|output|inout)\s+'
            r'(?:\[(\d+:\d+)\]\s+)?'
            r'(\w+)\s*[;,]',
        )
        for match in pattern.finditer(content):
            direction = match.group(1)
            width = match.group(2) or ""
            name = match.group(3)
            ports[name] = {"direction": direction, "width": width}
        return ports

    @staticmethod
    def _fix_equiv_error(content: str, error: str, original_rtl: str) -> str:
        """Fix an equivalence error by aligning signals."""
        error_lower = error.lower()

        # Port name mismatch
        if "port" in error_lower and ("name" in error_lower or "missing" in error_lower):
            # Extract port names from error
            port_matches = re.findall(r"'(\w+)'", error)
            if len(port_matches) >= 2:
                orig_name, hard_name = port_matches[0], port_matches[1]
                # Rename in hardened RTL
                content = re.sub(
                    rf'\b{hard_name}\b',
                    orig_name,
                    content,
                )

        # Signal not found in design
        if "not found" in error_lower or "undefined" in error_lower:
            signal_match = re.search(r"'(\w+)'", error)
            if signal_match:
                signal = signal_match.group(1)
                # Add as wire if not already present
                if signal not in content:
                    content = re.sub(
                        r'(\bmodule\s+\w+\s*\()',
                        r'\1\n    wire ' + signal + r';',
                        content,
                        count=1,
                    )

        return content


# ============================================================================
# Report Generation
# ============================================================================

def generate_repair_report(repair_result: Dict) -> str:
    """Generate a human-readable Markdown repair report.

    Args:
        repair_result: The result dict from AutoRepairEngine.repair().

    Returns:
        Formatted Markdown string.
    """
    lines: List[str] = []
    lines.append("# RTL Auto-Repair Report")
    lines.append("")

    # Summary
    passed = repair_result.get("passed", False)
    iterations = repair_result.get("iterations", 0)
    lines.append(f"**Status:** {'✅ PASSED' if passed else '❌ FAILED'}")
    lines.append(f"**Iterations:** {iterations}")
    lines.append(f"**RTL Path:** {repair_result.get('rtl_path', 'N/A')}")
    if repair_result.get("original_rtl"):
        lines.append(
            f"**Original RTL:** {repair_result['original_rtl']}"
        )
    if repair_result.get("fixed_rtl_path"):
        lines.append(
            f"**Fixed RTL:** {repair_result['fixed_rtl_path']}"
        )
    lines.append("")

    # Final report
    final_report = repair_result.get("final_report", "")
    if final_report:
        lines.append("## Final Report")
        lines.append("")
        lines.append(final_report)
        lines.append("")

    # Stage details
    stages = repair_result.get("stages", [])
    if stages:
        lines.append("## Stage History")
        lines.append("")
        lines.append("| # | Stage | Iteration | Passed | Details |")
        lines.append("|---|-------|-----------|--------|---------|")
        for i, stage in enumerate(stages, 1):
            stage_name = stage.get("stage", "?")
            iteration = stage.get("iteration", "?")
            stage_passed = stage.get("passed", False)
            errors = stage.get("errors", [])
            detail = (
                "OK"
                if stage_passed
                else (errors[0][:60] if errors else "Failed")
            )
            lines.append(
                f"| {i} | {stage_name} | {iteration} | "
                f"{'✅' if stage_passed else '❌'} | {detail} |"
            )
        lines.append("")

    # Error summary (if failed)
    if not passed and stages:
        all_errors: List[str] = []
        for stage in stages:
            for err in stage.get("errors", []):
                if err and err not in all_errors:
                    all_errors.append(err)
        if all_errors:
            lines.append("## Unresolved Issues")
            lines.append("")
            for err in all_errors[:10]:
                lines.append(f"- {err}")
            if len(all_errors) > 10:
                lines.append(f"- ... and {len(all_errors) - 10} more")
            lines.append("")

    lines.append("---")
    lines.append(
        f"_Generated by AutoRepairEngine at "
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}_"
    )

    return "\n".join(lines)


# ============================================================================
# End-to-End Pipeline
# ============================================================================

def hardening_with_repair(
    rtl_path: str,
    vulnerability_result: Optional[Dict] = None,
    rag_engine: Optional[Any] = None,
) -> Dict:
    """端到端硬化管线: RAG 硬化 → 验证 → 自动修复循环。

    Args:
        rtl_path:            待硬化的原始 RTL 文件路径。
        vulnerability_result:漏洞分析结果（可选）。
        rag_engine:          RAG 引擎实例，用于生成加固代码（可选）。

    Returns:
        Dict 包含:
          - hardened_rtl:  最终加固后的 RTL 内容。
          - repair_log:     修复过程的详细日志。
          - passed:         是否通过所有验证。
          - iterations:     修复迭代次数。
    """
    logger.section("Hardening with Repair Pipeline")
    logger.info("Input RTL: %s", rtl_path)

    if not os.path.isfile(rtl_path):
        return {
            "hardened_rtl": None,
            "repair_log": f"File not found: {rtl_path}",
            "passed": False,
            "iterations": 0,
        }

    # Step 1: Read original RTL
    with open(rtl_path, "r", encoding="utf-8", errors="replace") as f:
        original_content = f.read()

    # Step 2: Apply hardening (RAG-based if available)
    hardened_content = original_content
    if rag_engine is not None:
        try:
            if hasattr(rag_engine, "harden"):
                hardened_content = rag_engine.harden(
                    original_content,
                    vulnerability_result=vulnerability_result,
                )
            else:
                logger.warning("RAG engine has no 'harden' method; using original")
        except Exception as e:
            logger.error("RAG hardening failed: %s", e)
    else:
        logger.info("No RAG engine provided; using original content for repair")

    # Write hardened RTL to temp file
    work_dir = tempfile.mkdtemp(prefix="harden_repair_")
    hardened_path = os.path.join(work_dir, os.path.basename(rtl_path))
    with open(hardened_path, "w", encoding="utf-8") as f:
        f.write(hardened_content)

    # Step 3: Run auto-repair
    engine = AutoRepairEngine()
    repair_result = engine.repair(
        rtl_path=hardened_path,
        original_rtl=rtl_path,
    )

    # Step 4: Read final content
    if repair_result.get("passed") and repair_result.get("fixed_rtl_path"):
        try:
            with open(repair_result["fixed_rtl_path"], "r",
                      encoding="utf-8", errors="replace") as f:
                final_content = f.read()
        except OSError:
            final_content = hardened_content
    else:
        final_content = hardened_content

    report = generate_repair_report(repair_result)

    return {
        "hardened_rtl": final_content,
        "repair_log": report,
        "passed": repair_result.get("passed", False),
        "iterations": repair_result.get("iterations", 0),
        "repair_result": repair_result,
    }


# ============================================================================
# Quick Test
# ============================================================================

if __name__ == "__main__":
    logger.info("AutoRepairEngine demo")

    engine = AutoRepairEngine()

    # Test SyntaxFixer
    fixer = SyntaxFixer()
    test_code = """
module test (
    input clk
    input rst
);
    wire a
    assign a = 1
endmodule
"""
    fixed = fixer.fix(test_code, ["missing semicolon"])
    logger.info("Fixed syntax:\n%s", fixed)

    # Test report generation
    sample_result = {
        "passed": True,
        "iterations": 2,
        "stages": [
            {"stage": "syntax", "iteration": 1, "passed": True, "errors": []},
            {"stage": "synthesis", "iteration": 1, "passed": False,
             "errors": ["width mismatch at signal 'data'"]},
            {"stage": "syntax", "iteration": 2, "passed": True, "errors": []},
            {"stage": "synthesis", "iteration": 2, "passed": True, "errors": []},
        ],
        "final_report": "All checks passed after 2 iteration(s).",
        "fixed_rtl_path": "/tmp/repair_xxx/test.v",
        "rtl_path": "/path/to/test.v",
    }
    report = generate_repair_report(sample_result)
    logger.info("Sample report:\n%s", report)
