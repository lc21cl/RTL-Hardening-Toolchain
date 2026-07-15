#!/usr/bin/env python3
"""yosys_utils.py — 统一的 yosys 路径查找和环境变量构建。

消除 verification_engine.py 和 graph_pipeline.py 中的重复代码。
所有模块统一通过此模块定位 yosys 并构建子进程环境。
"""

import os
import sys
import subprocess
import shutil
from typing import Dict, Optional, List

# ── 项目路径常量 ──
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.join(_SCRIPT_DIR, '..', '..', '..', '..', '..')
_OSS_BIN = os.path.join(_PROJECT_ROOT, 'oss-cad-suite', 'bin')
_DEFAULT_YOSYS_PATH = os.path.join(_OSS_BIN, "yosys.exe")
_FALLBACK_YOSYS = "yosys"

# 常见安装路径
_COMMON_YOSYS_PATHS: List[str] = [
    "/usr/local/bin/yosys",
    "/usr/bin/yosys",
    "/opt/oss-cad-suite/bin/yosys",
    os.path.expanduser("~/oss-cad-suite/bin/yosys"),
    "C:\\oss-cad-suite\\bin\\yosys.exe",
    "C:\\tools\\oss-cad-suite\\bin\\yosys.exe",
]

# ── 缓存，避免重复文件系统查询 ──
_find_yosys_cache: Optional[str] = None


def find_yosys(use_cache: bool = True) -> Optional[str]:
    """定位 yosys 二进制文件路径。

    搜索顺序:
      1. oss-cad-suite 捆绑路径
      2. PATH 环境变量（where/which）
      3. 常见安装位置

    Args:
        use_cache: 是否使用缓存（默认 True，避免重复查询）。

    Returns:
        yosys 的绝对路径，未找到时返回 None。
    """
    global _find_yosys_cache
    if use_cache and _find_yosys_cache is not None:
        return _find_yosys_cache

    # 1. 检查默认捆绑路径
    if os.path.isfile(_DEFAULT_YOSYS_PATH):
        result = os.path.abspath(_DEFAULT_YOSYS_PATH)
        if use_cache:
            _find_yosys_cache = result
        return result

    # 2. 检查 PATH
    try:
        yosys_in_path = shutil.which('yosys')
        if yosys_in_path:
            if use_cache:
                _find_yosys_cache = yosys_in_path
            return yosys_in_path
    except Exception:
        pass

    # 备用：使用 where/which 命令
    try:
        if sys.platform == "win32":
            cmd = ["where", "yosys"]
        else:
            cmd = ["which", "yosys"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            resolved = result.stdout.strip().splitlines()[0]
            if use_cache:
                _find_yosys_cache = resolved
            return resolved
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 3. 常见安装位置
    for p in _COMMON_YOSYS_PATHS:
        if os.path.isfile(p):
            if use_cache:
                _find_yosys_cache = p
            return p

    return None


def clear_yosys_cache() -> None:
    """清除 yosys 查找缓存（测试或环境变更时使用）。"""
    global _find_yosys_cache
    _find_yosys_cache = None


def yosys_env(yosys_path: Optional[str] = None) -> Dict[str, str]:
    """构建 yosys 子进程环境变量。

    确保 oss-cad-suite 的 bin 和 lib 目录在 PATH 最前面，
    以便 yosys 能找到其辅助 DLL/工具。

    Args:
        yosys_path: yosys 可执行文件路径。为 None 时使用 _DEFAULT_YOSYS_PATH。

    Returns:
        适合 subprocess 的环境变量字典。
    """
    env = os.environ.copy()
    raw_entries = env.get("PATH", "").split(os.pathsep)

    yosys_bin = None
    if yosys_path:
        yosys_bin = os.path.dirname(os.path.abspath(yosys_path))
    if not yosys_bin or not os.path.isdir(yosys_bin):
        yosys_bin = os.path.dirname(os.path.abspath(_DEFAULT_YOSYS_PATH))

    # 收集 oss-cad 目录，推到 PATH 最前面
    oss_dirs: List[str] = []
    if os.path.isdir(yosys_bin):
        oss_dirs.append(os.path.normcase(yosys_bin))
        lib_dir = os.path.join(os.path.dirname(yosys_bin), 'lib')
        if os.path.isdir(lib_dir):
            oss_dirs.append(os.path.normcase(lib_dir))

    # 去重构建新路径
    oss_norm_set = {d.lower() for d in oss_dirs}
    tail = []
    for p in raw_entries:
        p_norm = os.path.normcase(p) if p else ""
        if p_norm.lower() not in oss_norm_set:
            tail.append(p)
    env["PATH"] = os.pathsep.join(oss_dirs + tail)
    return env


def check_yosys_availability() -> Dict:
    """全面检查 yosys 可用性，返回诊断报告。

    Returns:
        dict: {
            "available": bool,
            "path": Optional[str],
            "version": Optional[str],
            "errors": List[str]
        }
    """
    result: Dict = {
        "available": False,
        "path": None,
        "version": None,
        "errors": [],
    }

    path = find_yosys(use_cache=False)
    if not path:
        result["errors"].append(
            "yosys not found in PATH, bundled path, or common install locations. "
            "Install oss-cad-suite or add yosys to PATH."
        )
        return result

    result["path"] = path
    result["available"] = True

    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        result["version"] = (proc.stdout or proc.stderr).strip()
    except Exception as e:
        result["errors"].append(f"Failed to get yosys version: {e}")

    return result
