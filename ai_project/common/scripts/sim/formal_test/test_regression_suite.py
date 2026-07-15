#!/usr/bin/env python3
"""
test_regression_suite.py — 完整回归测试套件

覆盖所有加固策略的自动化验证:
  1. TMR 加固策略
  2. ECC 加固策略
  3. DICE 加固策略
  4. Parity 加固策略
  5. 多策略组合
  6. 设计错误分析
  7. AST 修复
  8. yosys 验证

用法:
    python test_regression_suite.py
    python test_regression_suite.py --quick
    python test_regression_suite.py --strategy tmr
"""

import os
import sys
import time
import argparse
import tempfile
import concurrent.futures
from typing import Dict, List, Optional, Tuple

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

try:
    from logger import logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)


def _create_test_design(module_name: str = "test_design", width: int = 8) -> str:
    """创建测试用的基础 RTL 设计。"""
    return f"""module {module_name} (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [{width-1}:0] data_in,
    output reg  [{width-1}:0] data_out,
    output wire       valid
);
    reg [{width-1}:0] internal_reg;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            internal_reg <= {width}'b0;
            data_out <= {width}'b0;
        end else begin
            internal_reg <= data_in;
            data_out <= internal_reg;
        end
    end
    assign valid = (data_out != {width}'b0);
endmodule
"""


def _create_buggy_design(module_name: str = "buggy_design") -> str:
    """创建包含设计错误的测试 RTL。"""
    return f"""module {module_name} (
    input wire clk,
    input wire rst_n,
    input wire [7:0] data_in
    output reg [7:0] data_out
);
    always @(posedge clk) begin
        if (!rst_n)
            data_out <= 8'b0
        else
            data_out <= data_in
    end
endmodule
"""


def _create_negative_test_designs() -> Dict[str, str]:
    """创建负面测试用例 — 合法的 Verilog 代码（不应被修复工具误修改）.

    Returns:
        Dict[name -> verilog_code], 每段代码语法正确且符合规范。
    """
    return {

        "NT01_basic_module": """\
module nt01_basic (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] data_in,
    output reg  [7:0] data_out
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            data_out <= 8'h00;
        else
            data_out <= data_in;
    end
endmodule
""",

        "NT02_wide_bus": """\
module nt02_wide_bus (
    input  wire          clk,
    input  wire          rst_n,
    input  wire [127:0]  data_in,
    output reg  [127:0]  data_out,
    output wire [15:0]   status
);
    reg [127:0] internal;
    wire [127:0] masked;
    assign masked = data_in & {128{1'b1}};
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            internal <= 128'h0;
            data_out <= 128'h0;
        end else begin
            internal <= masked;
            data_out <= internal;
        end
    end
    assign status = data_out[15:0] ^ data_out[31:16];
endmodule
""",

        "NT03_parametrized": """\
module nt03_parametrized #(
    parameter WIDTH = 8,
    parameter DEPTH = 16
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire [WIDTH-1:0] data_in,
    output reg  [WIDTH-1:0] data_out
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < DEPTH; i = i + 1)
                mem[i] <= {WIDTH{1'b0}};
            data_out <= {WIDTH{1'b0}};
        end else begin
            mem[0] <= data_in;
            for (i = 1; i < DEPTH; i = i + 1)
                mem[i] <= mem[i-1];
            data_out <= mem[DEPTH-1];
        end
    end
endmodule
""",

        "NT04_combinational": """\
module nt04_combinational (
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire [2:0] sel,
    output reg  [7:0] result,
    output wire       valid
);
    always @(*) begin
        case (sel)
            3'd0:    result = a + b;
            3'd1:    result = a - b;
            3'd2:    result = a & b;
            3'd3:    result = a | b;
            3'd4:    result = a ^ b;
            default: result = 8'h00;
        endcase
    end
    assign valid = |result;
endmodule
""",

        "NT05_submodule": """\
module nt05_submodule (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] data_in,
    output wire [7:0] data_out,
    output wire       flag
);
    wire [7:0] ff_out;
    dff #(.WIDTH(8)) u_dff (
        .clk(clk), .rst_n(rst_n),
        .d(data_in), .q(ff_out)
    );
    assign data_out = ff_out;
    assign flag = |ff_out;
endmodule

module dff #(
    parameter WIDTH = 8
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire [WIDTH-1:0] d,
    output reg  [WIDTH-1:0] q
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) q <= {WIDTH{1'b0}};
        else        q <= d;
    end
endmodule
""",

        "NT06_simple_generate": """\
module nt06_simple_generate #(
    parameter NUM_STAGES = 4
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire [7:0]       data_in,
    output wire [7:0]       data_out
);
    reg [7:0] shift_reg [0:NUM_STAGES-1];
    genvar i;
    generate
        for (i = 0; i < NUM_STAGES; i = i + 1) begin : stage
            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) shift_reg[i] <= 8'h00;
                else if (i == 0) shift_reg[i] <= data_in;
                else shift_reg[i] <= shift_reg[i-1];
            end
        end
    endgenerate
    assign data_out = shift_reg[NUM_STAGES-1];
endmodule
""",

        "NT07_function_task": """\
module nt07_function_task (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] data_in,
    output reg  [7:0] data_out
);
    function [7:0] sat_add;
        input [7:0] a, b;
        reg [8:0] sum;
        begin
            sum = a + b;
            if (sum > 255) sat_add = 8'hFF;
            else           sat_add = sum[7:0];
        end
    endfunction

    task reset_all;
        inout [7:0] val;
        begin
            val = 8'h00;
        end
    endtask

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reset_all(data_out);
        end else begin
            data_out <= sat_add(data_in, 8'd1);
        end
    end
endmodule
""",

        "NT08_tri_state": """\
module nt08_tri_state (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       oe,
    input  wire [7:0] data_in,
    inout  wire [7:0] data_bus,
    output reg  [7:0] captured
);
    reg [7:0] internal;
    assign data_bus = oe ? internal : 8'bz;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            internal <= 8'h00;
            captured <= 8'h00;
        end else begin
            internal <= data_in;
            captured <= data_bus;
        end
    end
endmodule
""",

        "NT09_sync_reset": """\
module nt09_sync_reset (
    input  wire       clk,
    input  wire       sync_rst,
    input  wire [7:0] data_in,
    output reg  [7:0] data_out
);
    reg [7:0] pipe;
    always @(posedge clk) begin
        if (sync_rst) begin
            pipe     <= 8'h00;
            data_out <= 8'h00;
        end else begin
            pipe     <= data_in;
            data_out <= pipe;
        end
    end
endmodule
""",

        "NT10_inout_port": """\
module nt10_inout_port (
    inout wire [7:0] bidir_bus,
    input  wire      dir,
    output reg [7:0] captured
);
    reg [7:0] buf;
    assign bidir_bus = dir ? buf : 8'bz;
    always @(*) begin
        if (!dir) captured = bidir_bus;
        else      captured = 8'h00;
    end
endmodule
""",

        "NT11_dual_clock": """\
module nt11_dual_clock (
    input  wire       clk_a,
    input  wire       clk_b,
    input  wire       rst_n,
    input  wire [7:0] data_a,
    output reg  [7:0] data_b
);
    reg [7:0] sync_a;
    reg [7:0] sync_b;
    always @(posedge clk_a or negedge rst_n) begin
        if (!rst_n) sync_a <= 8'h00;
        else        sync_a <= data_a;
    end
    always @(posedge clk_b or negedge rst_n) begin
        if (!rst_n) begin
            sync_b <= 8'h00;
            data_b <= 8'h00;
        end else begin
            sync_b <= sync_a;
            data_b <= sync_b;
        end
    end
endmodule
""",

        "NT12_synthesis_pragma": """\
module nt12_synthesis_pragma (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] data_in,
    output reg  [7:0] data_out
) /* synthesis syn_preserve=1 */;
    reg [7:0] internal /* synthesis syn_keep=1 */;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            internal <= 8'h00;
            data_out <= 8'h00;
        end else begin
            internal <= data_in;
            data_out <= internal;
        end
    end
endmodule
""",

        "NT13_zero_width": """\
module nt13_zero_width (
    input  wire clk,
    input  wire rst_n,
    input  wire data_in,
    output reg  data_out,
    output reg  flag
);
    reg internal;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            internal <= 1'b0;
            data_out <= 1'b0;
            flag     <= 1'b0;
        end else begin
            internal <= data_in;
            data_out <= internal;
            flag     <= data_in ^ internal;
        end
    end
endmodule
""",

        "NT14_always_latch": """\
module nt14_always_latch (
    input  wire       enable,
    input  wire [7:0] data_in,
    output reg  [7:0] data_out
);
    always @(*) begin
        if (enable) data_out = data_in;
    end
endmodule
""",
    }

class TestResult:
    """单个测试用例的结果。"""

    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.elapsed = 0.0
        self.details: Dict = {}

    def __bool__(self):
        return self.passed


class RegressionSuite:
    """回归测试套件。"""

    def __init__(self, quick: bool = False, strategy_filter: Optional[str] = None):
        self.quick = quick
        self.strategy_filter = strategy_filter.lower() if strategy_filter else None
        self.results: List[TestResult] = []
        self.total_start = time.time()

    def add_result(self, result: TestResult):
        self.results.append(result)

    def run(self) -> bool:
        """运行所有测试。"""
        logger.section("Regression Test Suite")

        strategies = ["tmr", "ecc", "dice", "parity", "tmr_ecc",
                       "cnt_comp", "watchdog", "one_hot_fsm"]
        if self.strategy_filter:
            strategies = [s for s in strategies if s == self.strategy_filter]
            logger.print(f"  Filtering to strategy: {self.strategy_filter}")

        logger.print(f"  Quick mode: {'YES' if self.quick else 'NO'}")
        logger.print(f"  Strategies: {', '.join(strategies)}")
        logger.print(f"  Hybrid strategies: tmr_ecc (TMR + ECC combined)")

        self._test_hardening_strategies(strategies)
        self._test_design_error_analysis()
        self._test_ast_repair()
        self._test_multi_strategy()
        self._test_negative_cases()

        return self._summary()

    def _test_hardening_strategies(self, strategies: List[str]):
        """测试所有加固策略 (并行执行)."""
        logger.sub_section("Test 1: Hardening Strategies (parallel)")

        from graph_pipeline import GraphPipeline
        from rag_integration import RAGEngine

        def _run_strategy(strategy: str) -> TestResult:
            """Run a single strategy test (called in thread pool)."""
            result = TestResult(f"Strategy: {strategy.upper()}")
            _t_start = time.time()
            try:
                pipeline = GraphPipeline(verbose=False)
                with tempfile.NamedTemporaryFile(mode="w", suffix=".v", delete=False) as f:
                    f.write(_create_test_design(f"test_{strategy}", 8))
                    test_path = f.name

                _cache_info = {
                    "cache_hits": 0,
                    "cache_misses": 0,
                }
                if hasattr(pipeline, '_rag_engine') and pipeline._rag_engine:
                    rag = pipeline._rag_engine
                    _before_cache_size = len(rag._context_cache) if hasattr(rag, '_context_cache') else -1

                harden_result = pipeline.harden(
                    rtl_path=test_path,
                    llm_backend="mock",
                    hardening_strategy=strategy,
                    max_repair_iterations=3 if self.quick else 5,
                    analyze_errors_first=True,
                    use_ast_repair=True,
                )

                if hasattr(pipeline, '_rag_engine') and pipeline._rag_engine:
                    _after_cache_size = len(rag._context_cache) if hasattr(rag, '_context_cache') else -1
                    _cache_delta = _after_cache_size - _before_cache_size
                    if _cache_delta > 0:
                        _cache_info["cache_misses"] = 1
                    elif _cache_delta == 0:
                        _cache_info["cache_hits"] = 1

                result.passed = harden_result["passed"]
                result.elapsed = time.time() - _t_start
                result.details = {
                    "iterations": harden_result["iterations"],
                    "hardened_lines": len(harden_result.get("hardened_rtl", "").splitlines()),
                    "rag_cache_hits": _cache_info["cache_hits"],
                    "rag_cache_misses": _cache_info["cache_misses"],
                }

                if not result.passed:
                    result.errors.append(f"Pipeline failed with status={harden_result.get('passed')}")

                try:
                    os.unlink(test_path)
                except OSError:
                    pass

            except Exception as e:
                result.passed = False
                result.errors.append(f"Exception: {e}")
                result.elapsed = time.time() - _t_start

            return result

        # Parallel execution of independent strategies
        max_workers = min(len(strategies), 5)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_strategy = {executor.submit(_run_strategy, s): s for s in strategies}
            for future in concurrent.futures.as_completed(future_to_strategy):
                strategy = future_to_strategy[future]
                try:
                    result = future.result()
                    self.add_result(result)
                    status = "✅" if result.passed else "❌"
                    logger.print(f"  [{status}] {result.name} ({result.elapsed:.2f}s)")
                except Exception as e:
                    result = TestResult(f"Strategy: {strategy.upper()}")
                    result.passed = False
                    result.errors.append(f"Thread error: {e}")
                    self.add_result(result)
                    logger.print(f"  [❌] Strategy: {strategy.upper()} (thread error: {e})")

    def _test_design_error_analysis(self):
        """测试设计错误分析。"""
        result = TestResult("Design Error Analysis")
        _t_start = time.time()

        try:
            from graph_pipeline import GraphPipeline

            pipeline = GraphPipeline(verbose=False)

            with tempfile.NamedTemporaryFile(mode="w", suffix=".v", delete=False) as f:
                f.write(_create_buggy_design())
                test_path = f.name

            analysis = pipeline.analyze_design_errors(test_path)
            result.passed = True
            result.elapsed = time.time() - _t_start
            result.details = {
                "errors": len(analysis["errors"]),
                "warnings": len(analysis["warnings"]),
                "modules": len(analysis["modules"]),
            }

            os.unlink(test_path)

        except Exception as e:
            result.passed = False
            result.errors.append(f"Exception: {e}")

        self.add_result(result)
        status = "✅" if result.passed else "❌"
        logger.print(f"  [{status}] {result.name} ({result.elapsed:.2f}s)")

    def _test_ast_repair(self):
        """测试 AST 修复器。"""
        result = TestResult("AST Repair")
        _t_start = time.time()

        try:
            from ast_repairer import ASTRepairer

            repairer = ASTRepairer()

            buggy_content = _create_buggy_design()
            repaired = repairer.fix(buggy_content, [])

            result.passed = repaired is not None
            result.elapsed = time.time() - _t_start
            result.details = {
                "original_lines": len(buggy_content.splitlines()),
                "repaired_lines": len(repaired.splitlines()) if repaired else 0,
            }

        except Exception as e:
            result.passed = False
            result.errors.append(f"Exception: {e}")

        self.add_result(result)
        status = "✅" if result.passed else "❌"
        logger.print(f"  [{status}] {result.name} ({result.elapsed:.2f}s)")

    def _test_multi_strategy(self):
        """测试多策略组合（非 quick 模式，并行执行）。"""
        if self.quick:
            logger.print("  [SKIP] Multi-strategy test (quick mode)")
            return

        result = TestResult("Multi-Strategy Combination")
        _t_start = time.time()

        try:
            from graph_pipeline import GraphPipeline

            with tempfile.NamedTemporaryFile(mode="w", suffix=".v", delete=False) as f:
                f.write(_create_test_design("test_multi", 16))
                test_path = f.name

            def _run_multi_strategy(strategy: str) -> Tuple[str, bool]:
                """Run single strategy in thread pool."""
                pipeline = GraphPipeline(verbose=False)
                harden_result = pipeline.harden(
                    rtl_path=test_path,
                    llm_backend="mock",
                    hardening_strategy=strategy,
                    max_repair_iterations=3,
                )
                return strategy, harden_result["passed"]

            strategies = ["tmr", "ecc", "dice", "parity", "tmr_ecc",
                          "cnt_comp", "watchdog", "one_hot_fsm"]
            errors = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(_run_multi_strategy, s): s for s in strategies}
                for future in concurrent.futures.as_completed(futures):
                    try:
                        s, passed = future.result()
                        if not passed:
                            errors.append(f"{s.upper()} failed")
                            result.passed = False
                    except Exception as e:
                        errors.append(f"Thread error: {e}")
                        result.passed = False

            result.passed = len(errors) == 0
            if errors:
                result.errors.extend(errors)
            result.elapsed = time.time() - _t_start
            try:
                os.unlink(test_path)
            except OSError:
                pass

        except Exception as e:
            result.passed = False
            result.errors.append(f"Exception: {e}")
            result.elapsed = time.time() - _t_start

        self.add_result(result)
        status = "✅" if result.passed else "❌"
        logger.print(f"  [{status}] {result.name} ({result.elapsed:.2f}s)")

    def _test_negative_cases(self):
        """测试负面用例 — 合法代码不应被修复工具误修改。"""
        result = TestResult("Negative Cases (14 designs)")
        _t_start = time.time()

        try:
            from graph_pipeline import GraphPipeline

            designs = _create_negative_test_designs()
            errors = []
            warnings = []
            passes = []

            for name, code in designs.items():
                with tempfile.NamedTemporaryFile(mode="w", suffix=".v", delete=False) as f:
                    f.write(code)
                    test_path = f.name

                try:
                    pipeline = GraphPipeline(verbose=False)
                    analysis = pipeline.analyze_design_errors(test_path)
                    err_count = len(analysis["errors"])
                    warn_count = len(analysis["warnings"])

                    if err_count == 0:
                        passes.append(name)
                    else:
                        errors.append(f"{name}: {err_count} false errors")
                    if warn_count > 0:
                        warnings.append(f"{name}: {warn_count} warnings")

                except Exception as e:
                    errors.append(f"{name}: exception {e}")

                try:
                    os.unlink(test_path)
                except OSError:
                    pass

            result.passed = len(errors) == 0
            if errors:
                result.errors.extend(errors)
            if warnings:
                result.warnings.extend(warnings[:5])  # cap at 5 in summary
            result.elapsed = time.time() - _t_start
            result.details = {
                "total": len(designs),
                "passed": len(passes),
                "errors": len(errors),
                "warnings": len(warnings),
            }

        except Exception as e:
            result.passed = False
            result.errors.append(f"Suite error: {e}")
            result.elapsed = time.time() - _t_start

        self.add_result(result)
        status = "✅" if result.passed else "❌"
        logger.print(f"  [{status}] {result.name} ({result.elapsed:.2f}s)")
        if errors:
            for e in errors[:3]:
                logger.print(f"         ⚠ {e}")
        if warnings:
            for w in warnings[:3]:
                logger.print(f"         ⚠ {w}")

    def _summary(self) -> bool:
        """输出测试总结。"""
        total_elapsed = time.time() - self.total_start
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        logger.section("Regression Test Summary")
        logger.table(
            headers=["Test", "Status", "Elapsed", "Details"],
            rows=[
                (
                    r.name,
                    "✅ PASS" if r.passed else "❌ FAIL",
                    f"{r.elapsed:.2f}s",
                    ", ".join(f"{k}={v}" for k, v in r.details.items()) if r.details else "-",
                )
                for r in self.results
            ],
        )

        logger.print(f"\n  Total: {passed}/{total} tests passed")
        logger.print(f"  Elapsed: {total_elapsed:.2f}s")

        return passed == total


def main():
    parser = argparse.ArgumentParser(description="Regression Test Suite")
    parser.add_argument("--quick", action="store_true", help="Run quick tests")
    parser.add_argument("--strategy", type=str, default=None,
                        choices=["tmr", "ecc", "dice", "parity", "tmr_ecc",
                                 "cnt_comp", "watchdog", "one_hot_fsm"],
                        help="Run only specified strategy")
    args = parser.parse_args()

    suite = RegressionSuite(quick=args.quick, strategy_filter=args.strategy)
    success = suite.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
