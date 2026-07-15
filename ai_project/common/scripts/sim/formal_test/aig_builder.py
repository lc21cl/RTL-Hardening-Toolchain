#!/usr/bin/env python3
"""
aig_builder.py — 独立的 yosys AIG (And-Inverter Graph) 构建器

提供简洁的 API 将 Verilog RTL 综合为 AIGER 二进制格式。
封装 yosys 调用，支持自动回退到 Python BLIF→AIGER 转换器。

用法:
    from aig_builder import build_aig, build_and_parse

    # 仅构建 AIG 文件
    aig_path = build_aig("design.v")

    # 构建并解析为 AIGParser 对象
    parser = build_and_parse("design.v")
    parser.print_stats()

    # 命令行
    python aig_builder.py --rtl design.v --output output_dir/
"""

import os
import sys
import subprocess
import tempfile
import shutil
from typing import Optional

from yosys_utils import find_yosys, yosys_env

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ============================================================================
# Internal Helpers
# ============================================================================

def _ys_quote(p: str) -> str:
    """Quote a path string for yosys .ys scripts (handles spaces)."""
    p = os.path.normpath(p)
    return f'"{p}"' if ' ' in p else p


def _generate_synth_script(rtl_path: str, blif_path: str, aig_path: str,
                           map_path: str) -> str:
    """Generate yosys synthesis script (.ys format).

    Produces both BLIF and AIGER outputs in a single yosys pass.
    BLIF serves as fallback if write_aiger fails.

    Args:
        rtl_path: Path to the Verilog RTL file.
        blif_path: Desired output path for the BLIF file.
        aig_path: Desired output path for the AIGER file.
        map_path: Desired output path for the port mapping file.

    Returns:
        Script content as a string.
    """
    lines = [
        f"read_verilog -sv {_ys_quote(rtl_path)}",
        "hierarchy -check -auto-top",
        "proc; opt",
        "memory; opt",
        "flatten; opt",
        "techmap; opt",
        "dfflegalize -cell $_DFFE_PN0P_ $_DFF_N_"
        " -cell $_DFFE_PP0P_ $_DFF_P_",
        "opt_clean",
        "setundef -undriven -zero",
        "abc -g AND",
        "clean",
        "stat",
        f"write_blif -gates {_ys_quote(blif_path)}",
        f"write_aiger -map {_ys_quote(map_path)} {_ys_quote(aig_path)}",
    ]
    return '\n'.join(lines)


def _run_yosys(script_content: str, work_dir: str,
               timeout: int = 300) -> subprocess.CompletedProcess:
    """Run yosys with a generated .ys script.

    Args:
        script_content: Yosys .ys script content.
        work_dir: Working directory for the yosys process.
        timeout: Timeout in seconds (default 300).

    Returns:
        subprocess.CompletedProcess with captured stdout/stderr.

    Raises:
        RuntimeError: If yosys binary cannot be located.
    """
    yosys_path = find_yosys()
    if yosys_path is None:
        raise RuntimeError(
            "yosys not found. Install oss-cad-suite or add yosys to PATH."
        )

    script_path = os.path.join(work_dir, "synth_aig.ys")
    with open(script_path, 'w') as f:
        f.write(script_content)

    proc_env = yosys_env(yosys_path)
    logger.info(f"Running yosys: {yosys_path} -s {script_path}")

    return subprocess.run(
        [yosys_path, "-s", script_path],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=proc_env,
    )


def _try_python_converter(blif_path: str, aig_path: str,
                          map_path: Optional[str] = None) -> bool:
    """Fallback: convert BLIF to AIGER using the Python converter.

    Args:
        blif_path: Path to the BLIF file.
        aig_path: Desired output AIGER file path.
        map_path: Optional port mapping output path.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    try:
        from blif_to_aiger import blif_to_aiger
    except ImportError as e:
        logger.error(f"Python BLIF→AIGER converter unavailable: {e}")
        return False

    if not os.path.isfile(blif_path):
        logger.error(f"BLIF file not found for fallback: {blif_path}")
        return False

    logger.info("Falling back to Python BLIF→AIGER converter...")
    ok = blif_to_aiger(blif_path, aig_path, map_path, verbose=False)
    if ok and os.path.isfile(aig_path) and os.path.getsize(aig_path) > 0:
        logger.info(f"Python converter generated: {aig_path}")
        return True

    logger.error("Python BLIF→AIGER conversion failed")
    return False


def _cleanup_intermediate(work_dir: str, keep_paths: set) -> None:
    """Remove intermediate files, preserving those in keep_paths.

    Args:
        work_dir: Directory containing intermediate files.
        keep_paths: Set of absolute file paths to preserve.
    """
    for fname in os.listdir(work_dir):
        fpath = os.path.join(work_dir, fname)
        if fpath in keep_paths:
            continue
        if fname.endswith('.ys') or fname.endswith('.blif') \
                or fname == 'output_map.txt' or fname == 'output_netlist.v':
            try:
                os.remove(fpath)
            except OSError:
                pass


# ============================================================================
# Public API
# ============================================================================

def build_aig(
    rtl_path: str,
    output_dir: Optional[str] = None,
    keep_intermediate: bool = False,
) -> str:
    """Build an AIG file from a Verilog RTL file via yosys synthesis.

    The synthesis flow:
      1. Generate a yosys .ys script that produces both BLIF and AIGER.
      2. Run yosys; if write_aiger fails, fall back to Python BLIF→AIGER.
      3. Return the path to the generated .aig file.

    Args:
        rtl_path: Path to the Verilog RTL file (.v, .sv).
        output_dir: Directory for output files. If None, a temporary
                    directory is created and removed after synthesis.
        keep_intermediate: If True, preserve intermediate files (.blif,
                           .ys, port map) in the output directory.

    Returns:
        Absolute path to the generated .aig file.

    Raises:
        FileNotFoundError: If rtl_path does not exist.
        RuntimeError: If yosys is not found or synthesis fails.
    """
    rtl_path = os.path.abspath(rtl_path)
    if not os.path.isfile(rtl_path):
        raise FileNotFoundError(f"RTL file not found: {rtl_path}")

    design_name = os.path.splitext(os.path.basename(rtl_path))[0]

    # ── Setup output directory ──
    _temp_dir = None
    if output_dir is None:
        _temp_dir = tempfile.mkdtemp(prefix='aig_builder_')
        output_dir = _temp_dir
    else:
        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)

    try:
        # ── Prepare output paths ──
        aig_path = os.path.join(output_dir, f"{design_name}.aig")
        blif_path = os.path.join(output_dir, f"{design_name}.blif")
        map_path = os.path.join(output_dir, f"{design_name}_map.txt")

        # ── Generate and run synthesis script ──
        script = _generate_synth_script(rtl_path, blif_path, aig_path, map_path)
        result = _run_yosys(script, output_dir)

        # ── Check yosys exit code ──
        if result.returncode != 0:
            logger.warning(
                f"yosys returned exit code {result.returncode}. "
                f"Attempting Python BLIF→AIGER fallback..."
            )
            if not _try_python_converter(blif_path, aig_path, map_path):
                raise RuntimeError(
                    f"yosys synthesis failed (exit={result.returncode}) "
                    f"and Python fallback also failed.\n"
                    f"stderr (first 500 chars):\n{result.stderr[:500]}"
                )
        else:
            # ── Verify AIG file was generated ──
            if not os.path.isfile(aig_path) or os.path.getsize(aig_path) == 0:
                logger.warning(
                    "yosys ran successfully but AIG file is missing/empty. "
                    "Attempting Python BLIF→AIGER fallback..."
                )
                if not _try_python_converter(blif_path, aig_path, map_path):
                    raise RuntimeError(
                        "Synthesis completed but AIG file was not generated "
                        "and Python fallback failed."
                    )
            else:
                logger.info(
                    f"AIG synthesis succeeded: {aig_path} "
                    f"({os.path.getsize(aig_path)} bytes)"
                )

        # ── Cleanup ──
        if not keep_intermediate:
            _cleanup_intermediate(output_dir, {aig_path, map_path})

        return aig_path

    finally:
        # If we created a temp dir and the caller wanted it cleaned up,
        # remove it unless keep_intermediate is set.
        if _temp_dir is not None and not keep_intermediate:
            shutil.rmtree(_temp_dir, ignore_errors=True)


def build_and_parse(
    rtl_path: str,
    output_dir: Optional[str] = None,
) -> 'AIGParser':
    """Build an AIG from RTL and parse it into an AIGParser graph object.

    Combines build_aig() and AIGParser.parse_file() in one step.
    Also attempts to load the port mapping file for signal names.

    Args:
        rtl_path: Path to the Verilog RTL file.
        output_dir: Directory for intermediate files (see build_aig).
                    If None, a temporary directory is used and cleaned up.

    Returns:
        An initialized AIGParser instance with the parsed graph.

    Raises:
        FileNotFoundError: If rtl_path does not exist.
        RuntimeError: If synthesis or parsing fails.
    """
    from aig_parser import AIGParser

    rtl_path = os.path.abspath(rtl_path)
    design_name = os.path.splitext(os.path.basename(rtl_path))[0]

    # ── Build AIG file ──
    # Use a specified output_dir so we can find the map file.
    _own_dir = output_dir is None
    if _own_dir:
        output_dir = tempfile.mkdtemp(prefix='aig_build_parse_')
    else:
        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)

    try:
        aig_path = build_aig(rtl_path, output_dir=output_dir,
                             keep_intermediate=True)

        # ── Parse ──
        parser = AIGParser()
        if not parser.parse_file(aig_path):
            raise RuntimeError(f"AIGParser failed to parse: {aig_path}")

        # ── Load port mapping ──
        map_path = os.path.join(output_dir, f"{design_name}_map.txt")
        if os.path.isfile(map_path):
            parser.parse_map_file(map_path)
            logger.info(f"Loaded port map: {map_path}")
        else:
            logger.info("No port mapping file found; using default names")

        logger.info(
            f"Parsed AIG: {len(parser.nodes)} nodes, "
            f"{parser.num_inputs} inputs, {parser.num_outputs} outputs, "
            f"{parser.num_ands} AND gates"
        )
        return parser

    finally:
        if _own_dir:
            shutil.rmtree(output_dir, ignore_errors=True)


# ============================================================================
# CLI
# ============================================================================

def main() -> None:
    """Command-line entry point for aig_builder.py."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build AIG (And-Inverter Graph) from Verilog RTL via yosys",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python aig_builder.py --rtl design.v\n"
            "  python aig_builder.py --rtl design.v --output ./aig_output/\n"
            "  python aig_builder.py --rtl design.v --parse --stats\n"
        ),
    )
    parser.add_argument('--rtl', required=True,
                        help='Path to Verilog RTL file (.v/.sv)')
    parser.add_argument('--output', '-o', default=None,
                        help='Output directory for generated files '
                             '(default: temporary directory)')
    parser.add_argument('--parse', '-p', action='store_true',
                        help='Parse the generated AIG and print statistics')
    parser.add_argument('--stats', '-s', action='store_true',
                        help='Print AIG statistics (implies --parse)')
    parser.add_argument('--keep', '-k', action='store_true',
                        dest='keep_intermediate',
                        help='Keep intermediate files (.blif, .ys, etc.)')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Print yosys stdout/stderr for debugging')

    args = parser.parse_args()

    # Validate input
    if not os.path.isfile(args.rtl):
        print(f"Error: RTL file not found: {args.rtl}", file=sys.stderr)
        sys.exit(1)

    # Determine whether to parse
    do_parse = args.parse or args.stats

    if do_parse:
        try:
            aig_parser = build_and_parse(args.rtl, output_dir=args.output)
            if args.stats:
                aig_parser.print_stats()

            # Try to convert to PyG if available
            try:
                data = aig_parser.to_pyg_data()
                print(f"\nPyG Data: {data.num_nodes} nodes, "
                      f"{data.edge_index.shape[1]} edges, "
                      f"x={list(data.x.shape)}")
            except ImportError:
                print("\nPyTorch Geometric not installed; skipping PyG conversion")
            except Exception as e:
                print(f"\nPyG conversion warning: {e}")

            # Try NetworkX
            try:
                G = aig_parser.to_networkx()
                print(f"NetworkX: {G.number_of_nodes()} nodes, "
                      f"{G.number_of_edges()} edges")
            except ImportError:
                print("networkx not installed; skipping NetworkX conversion")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            logger.error("build_and_parse failed", exc_info=True)
            sys.exit(1)

    else:
        try:
            aig_path = build_aig(
                args.rtl,
                output_dir=args.output,
                keep_intermediate=args.keep_intermediate,
            )
            aig_size = os.path.getsize(aig_path)
            print(f"[OK] AIG generated: {aig_path} ({aig_size} bytes)")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            logger.error("build_aig failed", exc_info=True)
            sys.exit(1)


if __name__ == '__main__':
    main()
