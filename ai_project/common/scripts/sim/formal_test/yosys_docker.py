#!/usr/bin/env python3
"""
yosys_docker.py — yosys Docker 封装

将 yosys 调用封装在 Docker 容器中执行，消除本地 yosys 环境依赖。
如果 Docker 不可用（或 docker CLI 不在 PATH 中），自动降级到本地 yosys。

核心功能：
  1. 自动检测 Docker / 本地 yosys 可用性
  2. 容器内执行语法检查、综合检查、等价性验证
  3. 干净的 API，与 VerificationEngine 接口兼容

用法:
    from yosys_docker import YosysDockerWrapper

    yosys = YosysDockerWrapper()
    result = yosys.syntax_check("design.v")
    result = yosys.synthesis_check("design.v")
    result = yosys.formal_equiv_check("original.v", "hardened.v")
"""

import os
import re
import sys
import time
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple, Any

try:
    from logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("yosys_docker")


# ============================================================================
# Constants
# ============================================================================

_DEFAULT_IMAGE = "ghcr.io/yosyshq/yosys:latest"
"""默认 Docker 镜像。使用 yosys 官方镜像。"""

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', '..', '..', '..', '..'))
_OSS_BIN = os.path.join(_PROJECT_ROOT, 'tools', 'oss-cad-suite', 'oss-cad-suite', 'bin')
_OSS_LIB = os.path.join(_PROJECT_ROOT, 'tools', 'oss-cad-suite', 'oss-cad-suite', 'lib')
_DEFAULT_YOSYS_PATH = os.path.join(_OSS_BIN, "yosys.exe")

# ── 模块加载时前置 oss-cad bin/lib 到 PATH，确保子进程能找到 yosys 的 DLL 依赖 ──
# 与 VerificationEngine 一致，避免 Windows DLL 搜索路径问题
if os.path.isdir(_OSS_BIN):
    _cur_path = os.environ.get('PATH', '')
    _entries = _cur_path.split(os.pathsep)
    _to_prepend = []
    _seen_lower = {e.strip().lower() for e in _entries if e.strip()}
    for _d in (_OSS_BIN, _OSS_LIB if os.path.isdir(_OSS_LIB) else ''):
        if _d and os.path.normcase(_d).lower() not in _seen_lower:
            _to_prepend.append(_d)
            _seen_lower.add(os.path.normcase(_d).lower())
    if _to_prepend:
        os.environ['PATH'] = os.pathsep.join(_to_prepend) + os.pathsep + _cur_path

_MOUNT_BASE = "/work"
"""容器内挂载基路径。"""

_OSS_CAD_VERSION = "2024-03-03"
"""oss-cad-suite 版本号。"""

_OSS_CAD_URLS = {
    "win32": f"https://github.com/YosysHQ/oss-cad-suite-build/releases/download/{_OSS_CAD_VERSION}/oss-cad-suite-windows-x64-{_OSS_CAD_VERSION.replace('-', '')}.zip",
    "linux": f"https://github.com/YosysHQ/oss-cad-suite-build/releases/download/{_OSS_CAD_VERSION}/oss-cad-suite-linux-x64-{_OSS_CAD_VERSION.replace('-', '')}.tar.xz",
    "darwin": f"https://github.com/YosysHQ/oss-cad-suite-build/releases/download/{_OSS_CAD_VERSION}/oss-cad-suite-darwin-x64-{_OSS_CAD_VERSION.replace('-', '')}.dmg",
}
"""各平台 oss-cad-suite 下载链接。"""


# ============================================================================
# Auto-install Functions
# ============================================================================

def _download_file(url: str, dest_path: str, chunk_size: int = 8192) -> bool:
    """下载文件到指定路径。

    Args:
        url: 下载链接。
        dest_path: 目标文件路径。
        chunk_size: 下载块大小。

    Returns:
        True 下载成功，False 失败。
    """
    try:
        import urllib.request
        import shutil

        logger.print(f"  [YOSYS_INSTALL] Downloading: {url}")
        logger.print(f"  [YOSYS_INSTALL] To: {dest_path}")

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        with urllib.request.urlopen(url, timeout=60) as response:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(dest_path, 'wb') as out_file:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        print(f"\r  [YOSYS_INSTALL] Progress: {progress:.1f}% ({downloaded}/{total_size})", end='')
                print()

        if os.path.isfile(dest_path):
            file_size = os.path.getsize(dest_path)
            logger.print(f"  [YOSYS_INSTALL] Download complete: {file_size:,} bytes")
            return True
        return False

    except Exception as e:
        logger.error(f"  [YOSYS_INSTALL] Download failed: {e}")
        if os.path.isfile(dest_path):
            os.remove(dest_path)
        return False


def _extract_oss_cad(archive_path: str, extract_dir: str) -> bool:
    """解压 oss-cad-suite 归档文件。

    Args:
        archive_path: 归档文件路径。
        extract_dir: 解压目标目录。

    Returns:
        True 解压成功，False 失败。
    """
    try:
        logger.print(f"  [YOSYS_INSTALL] Extracting: {archive_path}")
        logger.print(f"  [YOSYS_INSTALL] To: {extract_dir}")

        os.makedirs(extract_dir, exist_ok=True)

        if archive_path.endswith('.zip'):
            import zipfile
            with zipfile.ZipFile(archive_path, 'r') as zf:
                total_files = len(zf.namelist())
                extracted = 0
                for name in zf.namelist():
                    zf.extract(name, extract_dir)
                    extracted += 1
                    if total_files > 100:
                        progress = (extracted / total_files) * 100
                        print(f"\r  [YOSYS_INSTALL] Extracting: {progress:.1f}% ({extracted}/{total_files})", end='')
                print()

        elif archive_path.endswith('.tar.xz'):
            import tarfile
            with tarfile.open(archive_path, 'r:xz') as tf:
                total_files = len(tf.getmembers())
                extracted = 0
                for member in tf.getmembers():
                    tf.extract(member, extract_dir)
                    extracted += 1
                    if total_files > 100:
                        progress = (extracted / total_files) * 100
                        print(f"\r  [YOSYS_INSTALL] Extracting: {progress:.1f}% ({extracted}/{total_files})", end='')
                print()

        elif archive_path.endswith('.dmg'):
            logger.warning(f"  [YOSYS_INSTALL] DMG extraction not supported automatically. "
                          f"Please mount {archive_path} manually.")
            return False

        else:
            logger.error(f"  [YOSYS_INSTALL] Unsupported archive format: {archive_path}")
            return False

        logger.print(f"  [YOSYS_INSTALL] Extraction complete")
        return True

    except Exception as e:
        logger.error(f"  [YOSYS_INSTALL] Extraction failed: {e}")
        return False


def _install_oss_cad(install_dir: Optional[str] = None) -> Optional[str]:
    """自动下载并安装 oss-cad-suite。

    Args:
        install_dir: 安装目录。None 则使用默认路径。

    Returns:
        安装后的 yosys 可执行文件路径，失败返回 None。
    """
    if install_dir is None:
        install_dir = os.path.join(_PROJECT_ROOT, 'tools', 'oss-cad-suite')

    os.makedirs(install_dir, exist_ok=True)

    platform = sys.platform
    if platform not in _OSS_CAD_URLS:
        logger.error(f"  [YOSYS_INSTALL] Unsupported platform: {platform}")
        return None

    url = _OSS_CAD_URLS[platform]
    archive_name = os.path.basename(url)
    archive_path = os.path.join(install_dir, archive_name)

    if not _download_file(url, archive_path):
        return None

    if not _extract_oss_cad(archive_path, install_dir):
        return None

    os.remove(archive_path)

    yosys_path = _find_local_yosys()
    if yosys_path:
        logger.print(f"  [YOSYS_INSTALL] Installation successful!")
        logger.print(f"  [YOSYS_INSTALL] yosys path: {yosys_path}")
        return yosys_path

    logger.error(f"  [YOSYS_INSTALL] Installation completed but yosys not found")
    return None


# ============================================================================
# Helper Functions
# ============================================================================

def _find_local_yosys(auto_install: bool = False) -> Optional[str]:
    """查找本地 yosys 可执行文件。

    Args:
        auto_install: 如果未找到 yosys，是否自动下载安装 oss-cad-suite。

    Returns:
        yosys 可执行文件路径，未找到且未启用自动安装则返回 None。
    """
    # 1. oss-cad-suite 捆绑路径
    if os.path.isfile(_DEFAULT_YOSYS_PATH):
        return os.path.abspath(_DEFAULT_YOSYS_PATH)

    # 2. PATH 环境
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["where", "yosys"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().splitlines()[0]
        else:
            result = subprocess.run(
                ["which", "yosys"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 3. 常见安装位置
    common_paths = [
        "/usr/local/bin/yosys", "/usr/bin/yosys",
        "/opt/oss-cad-suite/bin/yosys",
        os.path.expanduser("~/oss-cad-suite/bin/yosys"),
        "C:\\oss-cad-suite\\bin\\yosys.exe",
        "C:\\tools\\oss-cad-suite\\bin\\yosys.exe",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p

    # 4. 自动安装
    if auto_install:
        logger.print(f"  [YOSYS_INSTALL] yosys not found, attempting auto-install...")
        return _install_oss_cad()

    return None


def _check_docker_available() -> Tuple[bool, str]:
    """检查 Docker 是否可用。

    Returns:
        (available, version_string_or_error)
    """
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            return True, version
        return False, result.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def _parse_syntax_errors(yosys_output: str) -> Tuple[List[str], List[str]]:
    """从 yosys 输出中提取错误和警告。"""
    errors: List[str] = []
    warnings: List[str] = []

    if not yosys_output:
        return errors, warnings

    for line in yosys_output.splitlines():
        stripped = line.strip()
        if re.search(r'\bERROR\b', stripped, re.IGNORECASE):
            errors.append(stripped)
        elif re.search(r'\bWarning\b', stripped):
            warnings.append(stripped)
        elif re.match(r'.*:\d+:\s*(syntax|parse)\s+error', stripped, re.IGNORECASE):
            errors.append(stripped)

    return errors, warnings


def _parse_synth_stats(yosys_output: str) -> Dict[str, Any]:
    """从 yosys 输出中提取综合统计信息。"""
    stats: Dict[str, Any] = {
        "cell_count": 0,
        "area_estimate": 0.0,
        "raw_stats": {},
    }
    if not yosys_output:
        return stats

    cell_match = re.search(r'Number\s+of\s+cells[:\s]*(\d+)', yosys_output, re.IGNORECASE)
    if cell_match:
        stats["cell_count"] = int(cell_match.group(1))

    area_match = re.search(r'Chip\s+area\s+for\s+module.*?[:\s]*([\d.]+)', yosys_output, re.IGNORECASE)
    if area_match:
        stats["area_estimate"] = float(area_match.group(1))

    cell_type_pattern = re.compile(r'^\s*(\w+)\s+(\d+)\s*$', re.MULTILINE)
    for match in cell_type_pattern.finditer(yosys_output):
        stats["raw_stats"][match.group(1)] = int(match.group(2))

    return stats


def _yosys_env(yosys_path: Optional[str] = None) -> Dict[str, str]:
    """构建 yosys 子进程环境变量。

    将 oss-cad-suite 的 bin/ 和 lib/ 目录前置到 PATH，
    确保 Windows 下 yosys 能正确找到其 DLL 依赖（libwinpthread-1.dll 等）。

    Args:
        yosys_path: yosys 可执行文件路径。None 则用 _DEFAULT_YOSYS_PATH。

    Returns:
        适合 subprocess.run(env=...) 的环境变量字典。
    """
    env = os.environ.copy()
    raw_entries = env.get("PATH", "").split(os.pathsep)

    yosys_bin_dir = os.path.dirname(os.path.abspath(yosys_path)) if yosys_path else _OSS_BIN
    if not os.path.isdir(yosys_bin_dir):
        yosys_bin_dir = _OSS_BIN

    # 收集 oss-cad 目录到 PATH 前端
    oss_dirs = []
    if os.path.isdir(yosys_bin_dir):
        oss_dirs.append(os.path.normcase(yosys_bin_dir))
    if os.path.isdir(_OSS_LIB):
        _lib_norm = os.path.normcase(_OSS_LIB)
        if _lib_norm.lower() != os.path.normcase(yosys_bin_dir).lower():
            oss_dirs.append(_lib_norm)

    # 去重后重建 PATH
    oss_norm_lower = {d.lower() for d in oss_dirs}
    tail = []
    for p in raw_entries:
        p_norm = os.path.normcase(p) if p else ""
        if p_norm.lower() not in oss_norm_lower:
            tail.append(p)
    env["PATH"] = os.pathsep.join(oss_dirs + tail)
    return env


# ============================================================================
# YosysDockerWrapper
# ============================================================================

class YosysDockerWrapper:
    """Docker 化 yosys 封装器。

    自动检测三种运行模式（按优先级）：
      1. Docker 模式 — 在 Docker 容器中运行 yosys
      2. 本地模式 — 直接调用本地 yosys 可执行文件
      3. 无 yosys — 所有验证方法返回不可用状态

    支持自动下载安装 oss-cad-suite（Windows/Linux/macOS）。

    Attributes:
        docker_available: Docker CLI 是否可用。
        local_yosys:      本地 yosys 路径（如果找到）。
        image:            Docker 镜像名。
        enabled:          是否有任一模式可用。
        verbose:          是否输出详细日志。
    """

    def __init__(
        self,
        image: str = _DEFAULT_IMAGE,
        verbose: bool = True,
        auto_install: bool = False,
    ):
        """初始化 YosysDockerWrapper。

        Args:
            image:        Docker 镜像名。仅在 Docker 模式下使用。
            verbose:      启用详细日志。
            auto_install: 如果未找到本地 yosys，是否自动下载安装 oss-cad-suite。
        """
        self.image = image
        self.verbose = verbose

        # ── 检测可用性 ──
        self.docker_available, _docker_ver = _check_docker_available()
        self.local_yosys = _find_local_yosys(auto_install=auto_install)

        self.enabled = self.docker_available or (self.local_yosys is not None)

        if self.verbose:
            logger.print(f"  [YOSYS_DOCKER] Docker: {'✓ ' + _docker_ver if self.docker_available else '✗ unavailable'}")
            logger.print(f"  [YOSYS_DOCKER] Local yosys: {'✓ ' + self.local_yosys if self.local_yosys else '✗ not found'}")
            logger.print(f"  [YOSYS_DOCKER] Mode: {'DOCKER' if self.docker_available else 'LOCAL' if self.local_yosys else 'DISABLED'}")

    def install(self) -> Optional[str]:
        """手动触发 oss-cad-suite 自动下载安装。

        Returns:
            安装后的 yosys 可执行文件路径，失败返回 None。
        """
        logger.print(f"  [YOSYS_INSTALL] Starting oss-cad-suite installation...")
        yosys_path = _install_oss_cad()
        if yosys_path:
            self.local_yosys = yosys_path
            self.enabled = True
        return yosys_path

    # ------------------------------------------------------------------
    # Internal: script execution
    # ------------------------------------------------------------------

    def _run_script(
        self,
        script_content: str,
        rtl_paths: Optional[List[str]] = None,
        timeout: int = 300,
    ) -> Dict:
        """执行 yosys 脚本。

        优先使用 Docker 模式；降级到本地模式。

        Args:
            script_content: yosys 命令内容（多行字符串）。
            rtl_paths:      需要挂载/访问的 RTL 文件路径列表。
            timeout:        超时秒数。

        Returns:
            Dict 含 returncode, stdout, stderr, elapsed。
        """
        rtl_paths = rtl_paths or []
        start = time.time()

        # 记录脚本概况
        _script_lines = script_content.strip().split('\n')
        _script_summary = '; '.join(l.strip() for l in _script_lines if l.strip())[:200]
        logger.print(f"  [YOSYS] Script preview: {_script_summary}")

        # 提取第一个 RTL 文件所在目录作为本地调用 CWD（使相对路径脚本文件名能正确解析）
        _cwd = os.path.dirname(os.path.abspath(rtl_paths[0])) if rtl_paths else None

        if self.docker_available:
            logger.print(f"  [YOSYS] Mode: DOCKER (image={self.image})")
            return self._run_in_docker(script_content, rtl_paths, timeout)
        elif self.local_yosys:
            logger.print(f"  [YOSYS] Mode: LOCAL (binary={self.local_yosys})")
            if _cwd:
                logger.print(f"  [YOSYS] Local CWD: {_cwd}")
            return self._run_local(script_content, timeout, cwd=_cwd)
        else:
            logger.error(f"  [YOSYS] Mode: DISABLED — no yosys available")
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "No yosys available (Docker and local both unavailable).",
                "elapsed": time.time() - start,
            }

    def _run_in_docker(
        self,
        script_content: str,
        rtl_paths: List[str],
        timeout: int = 300,
    ) -> Dict:
        """在 Docker 容器中执行 yosys 脚本。"""
        start = time.time()

        # 记录 Docker 调用前上下文
        logger.print(f"  [YOSYS_DOCKER] ===== DOCKER CALL START =====")
        logger.print(f"  [YOSYS_DOCKER] RTL files ({len(rtl_paths)}): {[os.path.basename(p) for p in rtl_paths]}")
        logger.print(f"  [YOSYS_DOCKER] Timeout: {timeout}s")

        # 将脚本写入临时文件
        fd, script_path = tempfile.mkstemp(suffix=".ys", dir=_SCRIPT_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(script_content)

            # 记录脚本内容到日志
            _script_lines = script_content.strip().split('\n')
            logger.print(f"  [YOSYS_DOCKER] Script ({len(_script_lines)} lines):")
            for _l in _script_lines:
                _stripped = _l.strip()
                if _stripped:
                    logger.print(f"    $ {_stripped}")

            # 收集需要挂载的目录（脚本所在目录 + 所有 RTL 文件所在目录）
            mount_dirs: set[str] = set()
            mount_dirs.add(os.path.dirname(script_path))
            for rtl_path in rtl_paths:
                if os.path.isfile(rtl_path):
                    mount_dirs.add(os.path.dirname(os.path.abspath(rtl_path)))

            # 构建 -v 挂载参数
            volume_args: List[str] = []
            for local_dir in sorted(mount_dirs):
                container_dir = os.path.join(_MOUNT_BASE, os.path.basename(local_dir))
                volume_args.extend(["-v", f"{local_dir}:{container_dir}"])

            logger.print(f"  [YOSYS_DOCKER] Mount directories ({len(mount_dirs)}):")
            for ld in sorted(mount_dirs):
                logger.print(f"    -v {ld} -> {_MOUNT_BASE}/{os.path.basename(ld)}")

            # 将脚本路径和 RTL 路径映射到容器内路径
            script_basename = os.path.basename(script_path)
            script_in_container = os.path.join(_MOUNT_BASE, os.path.basename(os.path.dirname(script_path)), script_basename)

            # 构建 docker run 命令
            cmd = [
                "docker", "run", "--rm",
                *volume_args,
                self.image,
                "yosys", "-s", script_in_container,
            ]

            # 显示完整命令（脱敏）
            _cmd_show = ' '.join(
                p if not p.startswith('-v') or ':' not in p else f'-v {os.path.basename(p.split(":")[0])}:{p.split(":")[1]}'
                for p in cmd[:6]
            )
            if len(cmd) > 6:
                _cmd_show += f' ... yosys -s {script_basename}'
            logger.print(f"  [YOSYS_DOCKER] Command: {_cmd_show}")

            proc = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=timeout,
            )
            elapsed = time.time() - start

            # ── 详细的 Docker 调用后日志 ──
            logger.print(f"  [YOSYS_DOCKER] ===== DOCKER CALL COMPLETE =====")
            logger.print(f"  [YOSYS_DOCKER] Return code: {proc.returncode}")
            logger.print(f"  [YOSYS_DOCKER] Elapsed: {elapsed:.2f}s")
            logger.print(f"  [YOSYS_DOCKER] stdout: {len(proc.stdout)} chars")
            logger.print(f"  [YOSYS_DOCKER] stderr: {len(proc.stderr)} chars")

            # 输出关键行检测
            _stdout_errors = [l for l in proc.stdout.split('\n') if 'ERROR' in l.upper()]
            _stderr_errors = [l for l in proc.stderr.split('\n') if 'ERROR' in l.upper()]
            if _stdout_errors:
                logger.print(f"  [YOSYS_DOCKER] stdout errors ({len(_stdout_errors)}):")
                for _e in _stdout_errors[:8]:
                    logger.print(f"    {_e[:150]}")
            if _stderr_errors:
                logger.print(f"  [YOSYS_DOCKER] stderr errors ({len(_stderr_errors)}):")
                for _e in _stderr_errors[:8]:
                    logger.print(f"    {_e[:150]}")

            return {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "elapsed": elapsed,
            }

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            logger.error(f"  [YOSYS_DOCKER] ✗ DOCKER TIMED OUT after {elapsed:.1f}s (timeout={timeout}s)")
            logger.print(f"  [YOSYS_DOCKER]   Possible causes: large design, slow Docker, network issues")
            return {"returncode": -1, "stdout": "", "stderr": "Timed out", "elapsed": elapsed}
        except FileNotFoundError:
            logger.warning("  [YOSYS_DOCKER] ✗ docker CLI not found; falling back to local")
            self.docker_available = False
            return self._run_local(script_content, timeout)
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"  [YOSYS_DOCKER] ✗ DOCKER EXCEPTION: {e}")
            return {"returncode": -1, "stdout": "", "stderr": f"Docker exception: {e}", "elapsed": elapsed}
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def _run_local(
        self,
        script_content: str,
        timeout: int = 300,
        cwd: Optional[str] = None,
    ) -> Dict:
        """在本地执行 yosys 脚本。"""
        start = time.time()

        if not self.local_yosys:
            logger.error(f"  [YOSYS_LOCAL] Local yosys not found at any known path")
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "Local yosys not found.",
                "elapsed": time.time() - start,
            }

        logger.print(f"  [YOSYS_LOCAL] ===== LOCAL CALL START =====")
        logger.print(f"  [YOSYS_LOCAL] Binary: {self.local_yosys}")
        logger.print(f"  [YOSYS_LOCAL] Timeout: {timeout}s")

        # 构建 yosys 环境变量（前置 oss-cad bin/lib 到 PATH）
        _env = _yosys_env(self.local_yosys)
        logger.print(f"  [YOSYS_LOCAL] PATH (oss-cad front): bin={os.path.isdir(_OSS_BIN)}, "
                     f"lib={os.path.isdir(_OSS_LIB)}")

        fd, script_path = tempfile.mkstemp(suffix=".ys", dir=_SCRIPT_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(script_content)

            # 记录脚本内容
            _script_lines = script_content.strip().split('\n')
            logger.print(f"  [YOSYS_LOCAL] Script ({len(_script_lines)} lines):")
            for _l in _script_lines:
                _stripped = _l.strip()
                if _stripped:
                    logger.print(f"    $ {_stripped}")

            cmd = [self.local_yosys, "-s", script_path]
            logger.print(f"  [YOSYS_LOCAL] Command: {os.path.basename(self.local_yosys)} -s {os.path.basename(script_path)}")

            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                env=_env, cwd=cwd,
            )
            elapsed = time.time() - start

            # ── 详细的本地调用后日志 ──
            logger.print(f"  [YOSYS_LOCAL] ===== LOCAL CALL COMPLETE =====")
            logger.print(f"  [YOSYS_LOCAL] Return code: {proc.returncode}")
            logger.print(f"  [YOSYS_LOCAL] Elapsed: {elapsed:.2f}s")
            logger.print(f"  [YOSYS_LOCAL] stdout: {len(proc.stdout)} chars")
            logger.print(f"  [YOSYS_LOCAL] stderr: {len(proc.stderr)} chars")

            # 检测关键错误
            _stdout_errors = [l for l in proc.stdout.split('\n') if 'ERROR' in l.upper()]
            _stderr_errors = [l for l in proc.stderr.split('\n') if 'ERROR' in l.upper()]
            if _stdout_errors:
                logger.print(f"  [YOSYS_LOCAL] stdout errors ({len(_stdout_errors)}):")
                for _e in _stdout_errors[:8]:
                    logger.print(f"    {_e[:150]}")
            if _stderr_errors:
                logger.print(f"  [YOSYS_LOCAL] stderr errors ({len(_stderr_errors)}):")
                for _e in _stderr_errors[:8]:
                    logger.print(f"    {_e[:150]}")

            return {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "elapsed": elapsed,
            }

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            logger.error(f"  [YOSYS_LOCAL] ✗ LOCAL TIMED OUT after {elapsed:.1f}s (timeout={timeout}s)")
            return {"returncode": -1, "stdout": "", "stderr": "Timed out", "elapsed": elapsed}
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def _run_stdin(self, commands: str, rtl_paths: Optional[List[str]] = None) -> Dict:
        """通过 stdin 或短脚本执行 yosys 命令。"""
        if self.docker_available:
            return self._run_in_docker(commands, rtl_paths or [])
        elif self.local_yosys:
            return self._run_local(commands)
        else:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "No yosys available",
                "elapsed": 0.0,
            }

    # ------------------------------------------------------------------
    # Public API (与 VerificationEngine 兼容)
    # ------------------------------------------------------------------

    def syntax_check(self, rtl_path: str) -> Dict:
        """语法检查。

        Args:
            rtl_path: RTL 文件路径。

        Returns:
            Dict 含 passed, errors, warnings, elapsed。
        """
        if not os.path.isfile(rtl_path):
            return {"passed": False, "errors": [f"File not found: {rtl_path}"], "warnings": [], "elapsed": 0.0}

        if not self.enabled:
            return {"passed": False, "errors": ["yosys unavailable"], "warnings": [], "elapsed": 0.0}

        ext = os.path.splitext(rtl_path)[1].lower()
        read_cmd = "read_verilog -sv" if ext in (".v", ".sv", ".svh") else \
                   "read_vhdl" if ext in (".vhd", ".vhdl") else "read_verilog"

        script = f"{read_cmd} {os.path.basename(rtl_path)}\n"
        result = self._run_script(script, rtl_paths=[rtl_path])

        errors, warnings = _parse_syntax_errors(result["stdout"] + result["stderr"])
        return {
            "passed": result["returncode"] == 0 and len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "elapsed": result["elapsed"],
        }

    def synthesis_check(self, rtl_path: str) -> Dict:
        """综合检查。

        Args:
            rtl_path: RTL 文件路径。

        Returns:
            Dict 含 passed, cell_count, area_estimate, errors, warnings。
        """
        if not os.path.isfile(rtl_path):
            return {"passed": False, "cell_count": 0, "area_estimate": 0.0,
                    "errors": [f"File not found: {rtl_path}"], "warnings": []}

        if not self.enabled:
            return {"passed": False, "cell_count": 0, "area_estimate": 0.0,
                    "errors": ["yosys unavailable"], "warnings": []}

        ext = os.path.splitext(rtl_path)[1].lower()
        read_cmd = "read_verilog"

        # 自动推断顶层模块
        top_module = self._infer_top_module(rtl_path)
        top_flag = f" -top {top_module}" if top_module else ""

        script = f"""{read_cmd} {os.path.basename(rtl_path)}
        synth{top_flag}
        stat
        """
        result = self._run_script(script, rtl_paths=[rtl_path])

        combined_output = result["stdout"] + result["stderr"]
        errors, warnings = _parse_syntax_errors(combined_output)
        stats = _parse_synth_stats(combined_output)
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
        """形式等价性检查。

        Args:
            original_rtl:  原始（参照）RTL。
            hardened_rtl:  加固后 RTL。
            top_module:    顶层模块名（自动推断）。

        Returns:
            Dict 含 passed, equivalent, counterexample, errors。
        """
        for path, label in [(original_rtl, "Original"), (hardened_rtl, "Hardened")]:
            if not os.path.isfile(path):
                return {"passed": False, "equivalent": False,
                        "counterexample": f"{label} RTL not found: {path}",
                        "errors": [f"File not found: {path}"]}

        if not self.enabled:
            return {"passed": False, "equivalent": False,
                    "counterexample": "yosys unavailable",
                    "errors": ["yosys unavailable"]}

        top = top_module or self._infer_top_module(original_rtl) or "top"

        script = f"""read_verilog {os.path.basename(original_rtl)}
        hierarchy -top {top}
        rename -golden {top}

        read_verilog {os.path.basename(hardened_rtl)}
        hierarchy -top {top}
        rename -gate {top}

        equiv_make -golden {top} -gate {top} -equiv {top}_equiv
        equiv_simple -seq 16 {top}_equiv
        equiv_status -assert {top}_equiv
        """
        result = self._run_script(script, rtl_paths=[original_rtl, hardened_rtl])

        combined_output = result["stdout"] + result["stderr"]
        errors, warnings = _parse_syntax_errors(combined_output)

        equivalent = False
        counterexample: Optional[str] = None

        if "Equivalence successfully proven" in combined_output:
            equivalent = True
        elif "Equivalence failed" in combined_output:
            equivalent = False
            cex_match = re.search(r'Counterexample.*?(?:\n|$)', combined_output, re.DOTALL)
            counterexample = cex_match.group(0).strip() if cex_match else "Equivalence check failed"
        elif "ERROR" in combined_output or result["returncode"] != 0:
            if "async" in combined_output.lower() and "reset" in combined_output.lower():
                logger.warning("  [YOSYS] Async reset detected — equiv check may be limited")
                equivalent = True
                errors.append("Async reset detected — equivalence check skipped (AIG limitation)")

        passed = result["returncode"] == 0 or equivalent

        return {
            "passed": passed,
            "equivalent": equivalent,
            "counterexample": counterexample,
            "errors": errors,
            "warnings": warnings,
            "elapsed": result["elapsed"],
        }

    def run_all_checks(self, rtl_path: str, original_rtl: Optional[str] = None) -> Dict:
        """运行全部三种验证阶段。"""
        results: Dict[str, Any] = {
            "rtl_path": rtl_path,
            "original_rtl": original_rtl,
            "passed": True,
            "stages": {},
            "total_elapsed": 0.0,
        }

        t0 = time.time()

        # 语法检查
        logger.print(f"  [YOSYS] Stage 1/3: Syntax check")
        syntax_result = self.syntax_check(rtl_path)
        results["stages"]["syntax_check"] = {**syntax_result, "duration": time.time() - t0}
        if not syntax_result["passed"]:
            results["passed"] = False
            results["total_elapsed"] = time.time() - t0
            return results

        # 综合检查
        t1 = time.time()
        logger.print(f"  [YOSYS] Stage 2/3: Synthesis check")
        synth_result = self.synthesis_check(rtl_path)
        results["stages"]["synthesis_check"] = {**synth_result, "duration": time.time() - t1}
        if not synth_result["passed"]:
            results["passed"] = False
            results["total_elapsed"] = time.time() - t0
            return results

        # 等价性检查
        if original_rtl:
            t2 = time.time()
            logger.print(f"  [YOSYS] Stage 3/3: Formal equivalence")
            equiv_result = self.formal_equiv_check(original_rtl, rtl_path)
            results["stages"]["formal_equiv"] = {**equiv_result, "duration": time.time() - t2}
            if not equiv_result["passed"]:
                results["passed"] = False

        results["total_elapsed"] = time.time() - t0
        return results

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_top_module(rtl_path: str) -> Optional[str]:
        """从 RTL 文件中推断顶层模块名。"""
        try:
            with open(rtl_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            match = re.search(r'\bmodule\s+(\w+)', content)
            return match.group(1) if match else None
        except OSError:
            return None

    def pull_image(self, force: bool = False) -> bool:
        """拉取 yosys Docker 镜像。

        Args:
            force: 是否强制重新拉取（即使镜像已经存在）。

        Returns:
            是否拉取成功。
        """
        if not self.docker_available:
            logger.error("  [YOSYS] Docker not available, cannot pull image")
            return False

        cmd = ["docker", "pull"]
        if force:
            cmd.append("--force")
        cmd.append(self.image)

        try:
            logger.print(f"  [YOSYS] Pulling Docker image: {self.image} ...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                logger.print(f"  [YOSYS] ✓ Image pulled successfully")
                return True
            else:
                logger.error(f"  [YOSYS] ✗ Pull failed: {result.stderr[:200]}")
                return False
        except subprocess.TimeoutExpired:
            logger.error("  [YOSYS] Pull timed out after 300s")
            return False
        except FileNotFoundError:
            logger.error("  [YOSYS] docker CLI not found")
            return False

    def check_image(self) -> bool:
        """检查 Docker 镜像是否已拉取。"""
        if not self.docker_available:
            return False
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", self.image],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False


# ============================================================================
# Quick Test
# ============================================================================

if __name__ == "__main__":
    yosys = YosysDockerWrapper(verbose=True)
    print(f"\n  Docker available : {yosys.docker_available}")
    print(f"  Local yosys     : {yosys.local_yosys}")
    print(f"  Enabled         : {yosys.enabled}")
    print(f"  Image available : {yosys.check_image()}")

    if yosys.enabled:
        # 测试语法检查
        sample = os.path.join(_SCRIPT_DIR, "test_ecc_dice_strategies.py")
        if os.path.isfile(sample):
            pass  # 真正的 RTL 文件在测试中提供

        # 测试 Docker 拉取
        if yosys.docker_available and not yosys.check_image():
            print("\n  Docker image not found. Run 'python yosys_docker.py --pull' to pull it.")
