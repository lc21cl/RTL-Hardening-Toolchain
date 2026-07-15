# yosys Windows DLL 加载失败修复日志

## 问题现象

运行 `graph_pipeline.py --docker-verify` 时，Phase 7/7 Docker Verification 降级到本地 yosys 模式后返回错误码：

```
Return code: 3221225785  (= 0xC0000139 = STATUS_ENTRYPOINT_NOT_FOUND)
stdout: 603 chars
stderr: 80 chars
```

而同一流程中 Phase 6/7 Auto-Repair 使用 `VerificationEngine` 却能成功调用 yosys。

## 根因分析

### 原因 1：DLL 搜索路径缺失（STATUS_ENTRYPOINT_NOT_FOUND）

`Status Entrypoint Not Found` (0xC0000139) 表示 Windows 找到了 yosys.exe 本身，但无法定位其依赖的 DLL 导出函数。

**关键差异对比：**

| 模块 | 环境策略 | 结果 |
|:-----|:---------|:-----|
| `VerificationEngine` | **模块加载时** 将 oss-cad-suite 的 `bin/` 和 `lib/` 目录前置到 `os.environ['PATH']` | ✅ rc=0 |
| `YosysDockerWrapper._run_local()` | 直接 `subprocess.run(cmd)`，**未设置任何环境变量** | ❌ rc=3221225785 |

oss-cad-suite 的 yosys.exe 依赖多个运行时 DLL（`libwinpthread-1.dll`、`libgcc_s_seh-1.dll`、`libstdc++-6.dll` 等），这些 DLL 位于 oss-cad-suite 的 `bin/` 和 `lib/` 目录。当子进程启动时，Windows DLL 加载器根据 `PATH` 搜索这些依赖。如果 `bin/` 和 `lib/` 不在 PATH 前端，系统可能加载了不同版本的 DLL（例如从其他 MinGW/msys2 安装），导致入口点不匹配。

### 原因 2：CWD 与 RTL 文件不匹配（File not found）

`_run_local()` 将 yosys 脚本（.ys 文件）写入 `formal_test/` 目录，但 RTL 文件位于临时目录 `C:\Users\...\Temp\harden_pipeline_xxx\`。yosys 脚本中使用 `read_verilog test_multi_strategy_harden_hardened.v`（相对路径），但 yosys 的 CWD 是 `formal_test/`，无法找到该文件。

## 修复方案

### 修复 1：模块级 PATH 前置

在 `yosys_docker.py` 模块加载时，与 `VerificationEngine` 采用相同的 PATH 初始化逻辑：

```python
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
```

### 修复 2：`_yosys_env()` 辅助函数

构建隔离的 yosys 子进程环境，确保即使 PATH 被其他模块修改，子进程也能正确加载 DLL：

```python
def _yosys_env(yosys_path=None) -> Dict[str, str]:
    env = os.environ.copy()
    # oss-cad bin/lib 前置到 PATH
    # ...
    env["PATH"] = os.pathsep.join(oss_dirs + tail)
    return env
```

### 修复 3：`_run_local()` 使用 `cwd` 参数

```python
# _run_script() 中计算 CWD
_cwd = os.path.dirname(os.path.abspath(rtl_paths[0])) if rtl_paths else None

# _run_local() 中传入 cwd
proc = subprocess.run(cmd, ..., env=_env, cwd=cwd)
```

## 修复结果验证

| 指标 | 修复前 | 修复后 |
|:-----|:-------|:-------|
| Phase 7 yosys return code | `3221225785` (STATUS_ENTRYPOINT_NOT_FOUND) | `0` (SUCCESS) |
| Phase 7 语法检查 | ❌ FAILED | ✅ PASSED (0.03s) |
| Phase 7 综合检查 | ❌ FAILED | ✅ PASSED (0.10s) |
| Phase 7 stdout | 603 chars | 1072 chars (syntax) / 20666 chars (synthesis) |
| 整体 Pipeline | 0.335s | 0.448s |

## 涉及文件

| 文件 | 变更 |
|:-----|:-----|
| [yosys_docker.py](file:///d:/learning/AI_RESEARCH/ai_project/common/scripts/sim/formal_test/yosys_docker.py) | 添加 `_OSS_LIB` 常量、模块级 PATH 初始化、`_yosys_env()` 辅助函数、`_run_local()` 添加 `cwd` 参数、清理重复的 `_run_script()` 方法 |

## Docker 模式对比

| 维度 | 本地模式（修复后） | Docker 模式（设计目标） |
|:-----|:------------------|:----------------------|
| DLL 依赖 | 依赖 Windows PATH 正确配置 | Linux 容器，无 Windows DLL 问题 |
| 文件路径 | 需正确设置 CWD 或使用绝对路径 | 通过 `-v` 挂载统一映射 |
| 环境隔离 | 受全局 PATH 污染影响 | 完全隔离，镜像内置所有依赖 |
| 版本控制 | 依赖于本地 oss-cad-suite 安装 | `docker pull` 指定版本号 |
| 本次修复 | 两项修复均已生效 | 当前环境 Docker CLI 未安装，仅验证了本地降级路径 |
