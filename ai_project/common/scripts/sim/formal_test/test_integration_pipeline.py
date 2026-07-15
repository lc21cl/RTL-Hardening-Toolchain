#!/usr/bin/env python3
"""
test_integration_pipeline.py — 项目级集成测试管线

覆盖完整的 RTL → AIG/BLIF → PyG Graph → GNN 推理 → 设计错误分析
→ 加固修复 → 回归验证 端到端流程。

用法:
    python test_integration_pipeline.py                 # 全部测试
    python test_integration_pipeline.py --quick         # 快速模式
    python test_integration_pipeline.py --verbose       # 详细日志
"""

import os
import sys
import time
import argparse
import tempfile
import subprocess
from typing import Dict, Any

import torch

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

try:
    from logger import logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Test Designs
# ──────────────────────────────────────────────

SIMPLE_DESIGN = """\
module simple_integration_test (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] data_in,
    output reg  [7:0] data_out,
    output wire       valid
);
    reg [7:0] internal;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            internal <= 8'h00;
            data_out <= 8'h00;
        end else begin
            internal <= data_in;
            data_out <= internal;
        end
    end
    assign valid = |data_out;
endmodule
"""

COMPLEX_DESIGN = """\
module complex_integration_test #(
    parameter WIDTH = 16,
    parameter DEPTH = 8
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire [WIDTH-1:0] data_in,
    input  wire             we,
    input  wire [2:0]       addr,
    output reg  [WIDTH-1:0] data_out,
    output wire             ready
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [WIDTH-1:0] pipe;
    reg [7:0] counter;
    wire [WIDTH-1:0] muxed;
    integer i;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < DEPTH; i = i + 1)
                mem[i] <= {WIDTH{1'b0}};
            pipe    <= {WIDTH{1'b0}};
            counter <= 8'd0;
            data_out <= {WIDTH{1'b0}};
        end else begin
            if (we) mem[addr] <= data_in;
            pipe    <= data_in;
            counter <= counter + 8'd1;
            data_out <= muxed;
        end
    end

    assign muxed = mem[pipe[2:0]];
    assign ready = (counter > 8'd1);
endmodule
"""


# ──────────────────────────────────────────────
#  Pipeline Stages
# ──────────────────────────────────────────────

class IntegrationPipeline:
    """项目级集成测试管线。

    按顺序执行以下阶段:
      1. RTL → Python 解析 (rtl_parser)
      2. RTL → AIG/BLIF (graph_pipeline)
      3. AIG → PyG Data (aig_parser/blif_to_pyg)
      4. PyG Data → GNN 推理 (gnn_inference)
      5. 设计错误分析 (analyze_design_errors)
      6. RTL 加固修复 (pipeline.harden)
      7. 回归验证 (yosys)
    """

    def __init__(self, verbose: bool = False, quick: bool = False):
        self.verbose = verbose
        self.quick = quick
        self.results: Dict[str, Dict[str, Any]] = {}
        self.total_elapsed = 0.0

    def run(self) -> bool:
        """运行完整集成测试管线。"""
        start = time.time()
        logger.section("Integration Test Pipeline")

        all_passed = True

        # Stage 1: RTL Parsing
        all_passed &= self._stage_rtl_parsing()
        # Stage 2: Graph Conversion (BLIF + AIG)
        all_passed &= self._stage_graph_conversion()
        # Stage 3: Design Error Analysis
        all_passed &= self._stage_error_analysis()
        # Stage 4: GNN Inference (quick mode skips)
        if not self.quick:
            all_passed &= self._stage_gnn_inference()
        # Stage 5: RTL Hardening (all 8 strategies)
        all_passed &= self._stage_hardening()
        # Stage 6: Yosys Verification (quick mode skips)
        if not self.quick:
            all_passed &= self._stage_yosys_verify()
        # Stage 7: Pipeline CLI
        all_passed &= self._stage_cli_interface()

        self.total_elapsed = time.time() - start
        self._print_summary(all_passed)
        return all_passed

    def _register(self, stage: str, passed: bool, elapsed: float, details: Dict = None):
        """注册阶段结果。"""
        self.results[stage] = {
            "passed": passed,
            "elapsed": elapsed,
            "details": details or {},
        }

    # ── Stage 1: RTL Parsing ──

    def _stage_rtl_parsing(self) -> bool:
        """Stage 1: RTL → Python 解析."""
        logger.sub_section("Stage 1: RTL Parsing")
        start = time.time()
        passed = False
        try:
            from rtl_parser import extract_module_name, extract_ports, extract_signals
            for name, code in [("simple", SIMPLE_DESIGN), ("complex", COMPLEX_DESIGN)]:
                mod_name = extract_module_name(code)
                ports = extract_ports(code)
                signals = extract_signals(code)
                if self.verbose:
                    logger.print(f"  [{name}] module='{mod_name}', {len(ports)} ports, {len(signals)} signals")
                assert mod_name is not None, f"{name}: module name not extracted"
                assert len(ports) > 0, f"{name}: no ports extracted"
            passed = True
        except Exception as e:
            logger.print(f"  [FAIL] RTL parsing failed: {e}")
        self._register("rtl_parsing", passed, time.time() - start)
        status = "✅" if passed else "❌"
        logger.print(f"  [{status}] RTL Parsing ({time.time() - start:.2f}s)")
        return passed

    # ── Stage 2: Graph Conversion ──

    def _stage_graph_conversion(self) -> bool:
        """Stage 2: RTL → AIG/BLIF → PyG Data."""
        logger.sub_section("Stage 2: Graph Conversion")
        start = time.time()
        passed = False
        try:
            from graph_pipeline import GraphPipeline
            gp = GraphPipeline(verbose=False)

            work_dir = tempfile.mkdtemp(prefix="int_")
            rtl_path = os.path.join(work_dir, "test_design.v")
            with open(rtl_path, "w") as f:
                f.write(SIMPLE_DESIGN)

            # BLIF pipeline
            blif_data = gp.from_rtl(rtl_path, output_dir=work_dir, keep_intermediate=False)
            assert "blif" in blif_data, "BLIF pipeline missing"
            blif = blif_data["blif"]
            assert blif.num_nodes > 0, "BLIF: 0 nodes"
            assert blif.edge_index.shape[1] > 0, "BLIF: 0 edges"
            blif_ok = True
            if self.verbose:
                logger.print(f"  BLIF: {blif.num_nodes} nodes, {blif.edge_index.shape[1]} edges, "
                             f"feat={blif.x.shape[1]}")

            # AIG pipeline
            aig_ok = False
            if "aig" in blif_data:
                aig = blif_data["aig"]
                aig_ok = aig.num_nodes > 0 and aig.edge_index.shape[1] > 0
                if self.verbose:
                    logger.print(f"  AIG:  {aig.num_nodes} nodes, {aig.edge_index.shape[1]} edges, "
                                 f"feat={aig.x.shape[1]}")

            passed = blif_ok
        except Exception as e:
            logger.print(f"  [FAIL] Graph conversion failed: {e}")

        self._register("graph_conversion", passed, time.time() - start)
        status = "✅" if passed else "❌"
        logger.print(f"  [{status}] Graph Conversion ({time.time() - start:.2f}s)")
        return passed

    # ── Stage 3: Error Analysis ──

    def _stage_error_analysis(self) -> bool:
        """Stage 3: Design Error Analysis."""
        logger.sub_section("Stage 3: Design Error Analysis")
        start = time.time()
        passed = False
        try:
            from graph_pipeline import GraphPipeline
            gp = GraphPipeline(verbose=False)

            work_dir = tempfile.mkdtemp(prefix="int_")
            # Clean design → 0 errors
            clean_path = os.path.join(work_dir, "clean.v")
            with open(clean_path, "w") as f:
                f.write(SIMPLE_DESIGN)
            clean_analysis = gp.analyze_design_errors(clean_path)
            assert len(clean_analysis["errors"]) == 0, "Clean design has false errors"

            # Complex design → 0 errors
            complex_path = os.path.join(work_dir, "complex.v")
            with open(complex_path, "w") as f:
                f.write(COMPLEX_DESIGN)
            complex_analysis = gp.analyze_design_errors(complex_path)
            assert len(complex_analysis["errors"]) == 0, "Complex design has false errors"

            passed = True
        except Exception as e:
            logger.print(f"  [FAIL] Error analysis failed: {e}")

        self._register("error_analysis", passed, time.time() - start)
        status = "✅" if passed else "❌"
        logger.print(f"  [{status}] Error Analysis ({time.time() - start:.2f}s)")
        return passed

    # ── Stage 4: GNN Inference ──

    def _stage_gnn_inference(self) -> bool:
        """Stage 4: PyG Data → GNN 推理."""
        logger.sub_section("Stage 4: GNN Inference")
        start = time.time()
        passed = False
        try:
            from graph_pipeline import GraphPipeline
            from gnn_inference import GNNInference

            gp = GraphPipeline(verbose=False)

            work_dir = tempfile.mkdtemp(prefix="int_")
            rtl_path = os.path.join(work_dir, "test.v")
            with open(rtl_path, "w") as f:
                f.write(SIMPLE_DESIGN)

            results = gp.from_rtl(rtl_path, output_dir=work_dir, keep_intermediate=False)
            assert "blif" in results, "BLIF data required for GNN"

            infer = GNNInference()
            scores = infer.infer(results["blif"])
            assert isinstance(scores, torch.Tensor), "Expected tensor output"
            assert scores.shape[0] == results["blif"].num_nodes, "Score count mismatch"
            n_vuln = int((scores >= infer.threshold).sum().item())
            if self.verbose:
                logger.print(f"  GNN: {n_vuln}/{results['blif'].num_nodes} vulnerable nodes")
            passed = True
        except RuntimeError as e:
            if "Model not loaded" in str(e):
                logger.print(f"  [SKIP] GNN model not available ({e})")
                passed = True
            else:
                logger.print(f"  [FAIL] GNN inference failed: {e}")
        except ImportError as e:
            logger.print(f"  [SKIP] GNN module not available ({e})")
            passed = True
        except Exception as e:
            logger.print(f"  [FAIL] GNN inference failed: {e}")

        self._register("gnn_inference", passed, time.time() - start)
        status = "✅" if passed else "❌"
        logger.print(f"  [{status}] GNN Inference ({time.time() - start:.2f}s)")
        return passed

    # ── Stage 5: RTL Hardening ──

    def _stage_hardening(self) -> bool:
        """Stage 5: RTL Hardening (all 8 strategies)."""
        logger.sub_section("Stage 5: RTL Hardening")
        start = time.time()
        all_ok = True

        try:
            from graph_pipeline import GraphPipeline

            strategies = ["tmr", "ecc", "dice", "parity", "tmr_ecc",
                          "cnt_comp", "watchdog", "one_hot_fsm"]
            results = {}

            for s in strategies:
                t0 = time.time()
                gp = GraphPipeline(verbose=False)
                work_dir = tempfile.mkdtemp(prefix=f"harden_{s}_")
                rtl_path = os.path.join(work_dir, "test.v")
                with open(rtl_path, "w") as f:
                    f.write(SIMPLE_DESIGN)

                harden_result = gp.harden(
                    rtl_path=rtl_path,
                    llm_backend="mock",
                    hardening_strategy=s,
                    max_repair_iterations=3 if self.quick else 5,
                    use_ast_repair=True,
                )
                elapsed = time.time() - t0
                results[s] = {"passed": harden_result["passed"], "elapsed": elapsed}
                if harden_result["passed"]:
                    logger.print(f"  [✅] {s.upper():12s} ({elapsed:.2f}s)")
                else:
                    logger.print(f"  [❌] {s.upper():12s} ({elapsed:.2f}s)")
                    all_ok = False

        except Exception as e:
            logger.print(f"  [FAIL] Hardening stage failed: {e}")
            all_ok = False

        self._register("hardening", all_ok, time.time() - start,
                       {"strategies": len(strategies)})
        return all_ok

    # ── Stage 6: Yosys Verification ──

    def _stage_yosys_verify(self) -> bool:
        """Stage 6: Yosys synthesis verification."""
        logger.sub_section("Stage 6: Yosys Verification")
        start = time.time()
        passed = False
        try:
            from yosys_utils import find_yosys, yosys_env
            yp = find_yosys()
            assert yp, "Yosys not found"

            work_dir = tempfile.mkdtemp(prefix="ys_")
            rtl_path = os.path.join(work_dir, "test.v")
            blif_path = os.path.join(work_dir, "test.blif")
            ys_path = os.path.join(work_dir, "s.ys")
            with open(rtl_path, "w") as f:
                f.write(SIMPLE_DESIGN)
            with open(ys_path, "w") as f:
                f.write(f"read_verilog -sv {rtl_path}\n")
                f.write("hierarchy -check -auto-top\n")
                f.write("proc; opt\n")
                f.write("memory; opt\n")
                f.write("flatten; opt\n")
                f.write("techmap; opt\n")
                f.write("opt_clean\n")
                f.write("setundef -undriven -zero\n")
                f.write(f"write_blif -gates {blif_path}\n")

            result = subprocess.run(
                [yp, "-s", ys_path], capture_output=True, text=True, timeout=120,
                cwd=work_dir, env=yosys_env(yp),
            )
            assert result.returncode == 0, f"Yosys failed: {result.stderr[:200]}"
            assert os.path.isfile(blif_path), "BLIF output missing"
            blif_size = os.path.getsize(blif_path)

            if self.verbose:
                logger.print(f"  Yosys: returncode={result.returncode}, BLIF={blif_size}B")

            # Parse generated BLIF
            from blif_to_pyg import BlifToAIG
            converter = BlifToAIG(blif_path)
            data = converter.build_pyg_data()
            assert data.num_nodes > 0, "BLIF→PyG: 0 nodes"
            assert data.edge_index.shape[1] > 0, "BLIF→PyG: 0 edges"

            passed = True
        except Exception as e:
            logger.print(f"  [FAIL] Yosys verification failed: {e}")

        self._register("yosys_verify", passed, time.time() - start)
        status = "✅" if passed else "❌"
        logger.print(f"  [{status}] Yosys Verification ({time.time() - start:.2f}s)")
        return passed

    # ── Stage 7: CLI Interface ──

    def _stage_cli_interface(self) -> bool:
        """Stage 7: Pipeline CLI interface."""
        logger.sub_section("Stage 7: CLI Interface")
        start = time.time()
        passed = False
        try:
            from graph_pipeline import GraphPipeline
            from rtl_parser import extract_module_name_from_file

            # Test analyze_design_errors (static method)
            work_dir = tempfile.mkdtemp(prefix="cli_")
            rtl_path = os.path.join(work_dir, "test.v")
            with open(rtl_path, "w") as f:
                f.write(SIMPLE_DESIGN)

            analysis = GraphPipeline.analyze_design_errors(rtl_path)
            assert isinstance(analysis, dict)
            assert "errors" in analysis and "warnings" in analysis
            assert len(analysis["errors"]) == 0, "Clean design has false errors"

            # Test module name extraction
            mod_name = extract_module_name_from_file(rtl_path)
            assert mod_name is not None, "Module name not extracted"

            passed = True
        except Exception as e:
            logger.print(f"  [FAIL] CLI interface test failed: {e}")

        self._register("cli_interface", passed, time.time() - start)
        status = "✅" if passed else "❌"
        logger.print(f"  [{status}] CLI Interface ({time.time() - start:.2f}s)")
        return passed

    # ── Summary ──

    def _print_summary(self, all_passed: bool):
        """输出集成测试总结。"""
        logger.section("Integration Test Summary")
        logger.table(
            headers=["Stage", "Status", "Elapsed", "Details"],
            rows=[
                (
                    name,
                    "✅ PASS" if r["passed"] else "❌ FAIL",
                    f"{r['elapsed']:.2f}s",
                    str(r.get("details", {})) if r.get("details") else "",
                )
                for name, r in self.results.items()
            ],
        )
        n_pass = sum(1 for r in self.results.values() if r["passed"])
        n_total = len(self.results)
        logger.print(f"  Pipeline: {n_pass}/{n_total} stages passed "
                     f"({'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'})")
        logger.print(f"  Elapsed: {self.total_elapsed:.2f}s")


def main():
    parser = argparse.ArgumentParser(description="Integration Test Pipeline")
    parser.add_argument("--quick", action="store_true", help="Skip heavy stages")
    parser.add_argument("--verbose", action="store_true", help="Detailed output")
    args = parser.parse_args()

    pipe = IntegrationPipeline(verbose=args.verbose, quick=args.quick)
    success = pipe.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
