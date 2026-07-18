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
    os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'oss-cad-suite', 'bin', 'yosys.exe'),
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'oss-cad-suite', 'bin', 'yosys.exe'),
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


def find_yosys_install_dir() -> Optional[str]:
    """搜索多个可能的位置来定位 oss-cad-suite 目录。

    依次检查:
      1. 项目根目录下的 oss-cad-suite
      2. 环境变量 OSS_CAD_SUITE 指向的目录
      3. 常见安装位置（Program Files, LocalAppData 等）

    Returns:
        找到的 oss-cad-suite 目录路径，未找到时返回 None。
    """
    # 1. 项目捆绑路径
    project_oss = os.path.join(_PROJECT_ROOT, 'oss-cad-suite')
    if os.path.isdir(project_oss) and os.path.isfile(os.path.join(project_oss, 'bin', 'yosys.exe' if sys.platform == 'win32' else 'yosys')):
        return os.path.abspath(project_oss)

    # 2. 环境变量
    env_dir = os.environ.get('OSS_CAD_SUITE')
    if env_dir and os.path.isdir(env_dir):
        return os.path.abspath(env_dir)

    # 3. 常见安装路径
    candidate_dirs = []
    if sys.platform == 'win32':
        pf = os.environ.get('PROGRAMFILES', 'C:\\Program Files')
        candidate_dirs.append(os.path.join(pf, 'oss-cad-suite'))
        pf_x86 = os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)')
        candidate_dirs.append(os.path.join(pf_x86, 'oss-cad-suite'))
        local = os.environ.get('LOCALAPPDATA', '')
        if local:
            candidate_dirs.append(os.path.join(local, 'oss-cad-suite'))
        candidate_dirs.append('C:\\oss-cad-suite')
        candidate_dirs.append('C:\\tools\\oss-cad-suite')
    else:
        candidate_dirs.extend([
            '/opt/oss-cad-suite',
            os.path.expanduser('~/oss-cad-suite'),
            '/usr/local/oss-cad-suite',
        ])

    for d in candidate_dirs:
        if os.path.isdir(d):
            return os.path.abspath(d)

    return None


def install_yosys(install_dir: Optional[str] = None) -> Dict:
    """自动安装 yosys (oss-cad-suite)。

    支持平台:
      - Windows: 下载预编译的 oss-cad-suite zip 包
      - Linux: 使用 apt 或下载 tar.xz
      - macOS: 使用 brew 或下载 tar.xz

    Args:
        install_dir: 安装目录，默认使用项目根目录下的 oss-cad-suite

    Returns:
        dict: {
            "success": bool,
            "message": str,
            "yosys_path": Optional[str],
            "install_dir": Optional[str]
        }
    """
    result: Dict = {
        "success": False,
        "message": "",
        "yosys_path": None,
        "install_dir": None,
    }

    if install_dir is None:
        install_dir = os.path.join(_PROJECT_ROOT, 'oss-cad-suite')

    result["install_dir"] = install_dir

    try:
        import urllib.request
        import zipfile
        import tarfile
    except ImportError as e:
        result["message"] = f"Missing required modules: {e}"
        return result

    os.makedirs(install_dir, exist_ok=True)

    if sys.platform == "win32":
        url = "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2024-02-02/oss-cad-suite-windows-x64-20240202.zip"
        zip_path = os.path.join(install_dir, "oss-cad-suite.zip")
        extract_dir = install_dir

        try:
            result["message"] = "Downloading oss-cad-suite for Windows..."
            urllib.request.urlretrieve(url, zip_path)
            result["message"] = "Extracting oss-cad-suite..."
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)

            inner_dir = os.path.join(extract_dir, 'oss-cad-suite')
            if os.path.isdir(inner_dir):
                for item in os.listdir(inner_dir):
                    src = os.path.join(inner_dir, item)
                    dst = os.path.join(extract_dir, item)
                    if os.path.isdir(src):
                        shutil.move(src, dst)
                    else:
                        shutil.copy2(src, dst)
                shutil.rmtree(inner_dir)

            yosys_exe = os.path.join(extract_dir, 'bin', 'yosys.exe')
            if os.path.isfile(yosys_exe):
                # 验证可执行文件可用
                try:
                    ver_proc = subprocess.run(
                        [yosys_exe, '--version'],
                        capture_output=True, text=True, timeout=10,
                    )
                    if ver_proc.returncode == 0:
                        result["success"] = True
                        result["message"] = f"yosys installed successfully to {yosys_exe} ({ver_proc.stdout.strip()})"
                        result["yosys_path"] = yosys_exe
                        clear_yosys_cache()
                    else:
                        result["message"] = (
                            f"yosys.exe found but failed to execute (return code {ver_proc.returncode}): "
                            f"{ver_proc.stderr.strip()}"
                        )
                except Exception as e:
                    result["message"] = f"yosys.exe found but execution verification failed: {e}"
            else:
                # 搜索 install_dir 下所有 yosys.exe 的位置
                found_exe = []
                for root, dirs, files in os.walk(extract_dir):
                    for f in files:
                        if f.lower() == 'yosys.exe':
                            found_exe.append(os.path.join(root, f))
                # 收集目录结构（前两层）用于诊断
                dir_structure = []
                try:
                    for item in sorted(os.listdir(extract_dir)):
                        item_path = os.path.join(extract_dir, item)
                        if os.path.isdir(item_path):
                            subs = [s for s in sorted(os.listdir(item_path))[:5]]
                            dir_structure.append(f"{item}/ ({', '.join(subs)})" if subs else f"{item}/")
                        else:
                            dir_structure.append(item)
                except Exception:
                    dir_structure.append("<unable to list directory>")

                result["message"] = (
                    f"Installation failed: yosys.exe not found after extraction.\n"
                    f"  Searched in: {extract_dir}\n"
                    f"  yosys.exe files found: {found_exe if found_exe else 'None'}\n"
                    f"  Directory structure:\n    " + "\n    ".join(dir_structure)
                )

            if os.path.isfile(zip_path):
                os.remove(zip_path)

        except Exception as e:
            result["message"] = f"Installation failed: {e}"

    elif sys.platform.startswith("linux"):
        try:
            result["message"] = "Trying to install yosys via apt..."
            proc = subprocess.run(
                ["sudo", "apt-get", "update", "-y"],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode == 0:
                proc = subprocess.run(
                    ["sudo", "apt-get", "install", "-y", "yosys"],
                    capture_output=True, text=True, timeout=300,
                )
                if proc.returncode == 0:
                    yosys_path = shutil.which("yosys")
                    if yosys_path:
                        result["success"] = True
                        result["message"] = f"yosys installed via apt: {yosys_path}"
                        result["yosys_path"] = yosys_path
                        clear_yosys_cache()
                        return result

            result["message"] = "apt install failed, trying download..."
            url = "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2024-02-02/oss-cad-suite-linux-x64-20240202.tgz"
            tar_path = os.path.join(install_dir, "oss-cad-suite.tgz")

            urllib.request.urlretrieve(url, tar_path)
            with tarfile.open(tar_path, 'r:gz') as tf:
                tf.extractall(install_dir)

            yosys_bin = os.path.join(install_dir, 'oss-cad-suite', 'bin', 'yosys')
            if os.path.isfile(yosys_bin):
                os.chmod(yosys_bin, 0o755)
                result["success"] = True
                result["message"] = f"yosys installed to {yosys_bin}"
                result["yosys_path"] = yosys_bin
                clear_yosys_cache()

            if os.path.isfile(tar_path):
                os.remove(tar_path)

        except Exception as e:
            result["message"] = f"Installation failed: {e}"

    elif sys.platform == "darwin":
        try:
            result["message"] = "Trying to install yosys via brew..."
            proc = subprocess.run(
                ["brew", "install", "yosys"],
                capture_output=True, text=True, timeout=300,
            )
            if proc.returncode == 0:
                yosys_path = shutil.which("yosys")
                if yosys_path:
                    result["success"] = True
                    result["message"] = f"yosys installed via brew: {yosys_path}"
                    result["yosys_path"] = yosys_path
                    clear_yosys_cache()
                    return result

            result["message"] = "brew install failed, trying download..."
            url = "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2024-02-02/oss-cad-suite-darwin-x64-20240202.tgz"
            tar_path = os.path.join(install_dir, "oss-cad-suite.tgz")

            urllib.request.urlretrieve(url, tar_path)
            with tarfile.open(tar_path, 'r:gz') as tf:
                tf.extractall(install_dir)

            yosys_bin = os.path.join(install_dir, 'oss-cad-suite', 'bin', 'yosys')
            if os.path.isfile(yosys_bin):
                os.chmod(yosys_bin, 0o755)
                result["success"] = True
                result["message"] = f"yosys installed to {yosys_bin}"
                result["yosys_path"] = yosys_bin
                clear_yosys_cache()

            if os.path.isfile(tar_path):
                os.remove(tar_path)

        except Exception as e:
            result["message"] = f"Installation failed: {e}"

    else:
        result["message"] = f"Unsupported platform: {sys.platform}"

    return result


if __name__ == '__main__':
    result = check_yosys_availability()
    print(f"Yosys available: {result['available']}")
    print(f"Path: {result['path']}")
    print(f"Version: {result['version']}")
    if not result['available']:
        ans = input("Yosys not found. Install now? (y/n): ")
        if ans.lower() == 'y':
            install_result = install_yosys()
            print(f"Install result: {install_result}")
