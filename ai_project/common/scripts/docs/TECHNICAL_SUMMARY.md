# RTL 加固流水线 — 技术总结

## 1. Windows 本地 yosys 路径问题排查

### 1.1 问题现象

| 场景 | 症状 | exit code |
|:-----|:-----|:---------:|
| Phase 6 Auto-Repair（VerificationEngine） | ✅ 正常通过 | 0 |
| Phase 7 Docker Verify（YosysDockerWrapper） | ❌ `STATUS_ENTRYPOINT_NOT_FOUND` | 3221225785 (0xC0000139) |

初看诡异——同一个 `yosys.exe`，同一个 RTL 文件，Auto-Repair 阶段成功、Docker 验证阶段失败。

### 1.2 排查步骤

#### 步骤 1：确认二进制路径一致

```
yosys.exe 路径: <project>/tools/oss-cad-suite/oss-cad-suite/bin/yosys.exe
```
两个模块都指向同一路径，排除"调用了不同 yosys"的可能。

#### 步骤 2：对比环境差异

用 `Process Monitor` 或 `sysinternals` 查看子进程的 DLL 加载顺序：

| 模块 | 调用方式 | 环境 |
|:-----|:---------|:-----|
| `VerificationEngine` | `subprocess.run(cmd)` | **`os.environ['PATH']` 已包含 oss-cad-suite/bin + oss-cad-suite/lib** |
| `YosysDockerWrapper._run_local()` | `subprocess.run(cmd)` | **未设置 PATH→子进程继承系统 PATH，oss-cad 目录不在前端** |

#### 步骤 3：确认 DLL 依赖

`dumpbin /dependents yosys.exe` 显示依赖:

```
libwinpthread-1.dll
libgcc_s_seh-1.dll
libstdc++-6.dll
libffi-8.dll
libreadline8.dll
```

这些 DLL 位于 `oss-cad-suite/lib/`。当子进程的 PATH 未指向此目录时，Windows DLL 加载器从系统路径 `C:\Windows\System32` 或其他 MinGW 安装加载了不同版本的 DLL，导致入口点不匹配。

#### 步骤 4：验证修复

在 `_run_local()` 中：
1. 构建 `env` 时将 `oss-cad-suite/bin/` 和 `oss-cad-suite/lib/` 前置到 PATH
2. `subprocess.run(cmd, env=env)` 传递修正后的环境
3. 指定 `cwd` 为 RTL 文件所在目录

### 1.3 根因结论

```
子进程未继承正确的 DLL 搜索路径
    ↓
Windows 加载了错误版本的运行时 DLL
    ↓
入口点地址不匹配 → STATUS_ENTRYPOINT_NOT_FOUND (0xC0000139)
```

---

## 2. Docker 与本地模式对比

### 2.1 性能基准

测试环境测试用例 `test_multi_strategy_harden.v`（4 模块、37 信号、304 行）：

| 模式 | 语法检查 | 综合检查 | 总计 |
|:-----|:--------:|:--------:|:----:|
| **Local** (oss-cad-suite win) | 0.03s | 0.10s | **0.13s** |
| **Docker** (predicted) | ~0.05s* | ~0.15s* | **~0.20s** |

*> Docker 受容器初始化开销影响（首次 ~1-2s），后续热容器差异缩小*

### 2.2 优劣势对比

| 维度 | 本地模式 | Docker 模式 |
|:-----|:---------|:------------|
| **首次启动** | 即开即用 | ~1-2s 初始化 |
| **持续调用** | 0.13s/次 | ~0.2s/次（热容器） |
| **DLL 依赖** | ❌ 依赖 Windows PATH 配置 | ✅ Linux 容器+官方镜像 |
| **环境隔离** | ❌ 受全局 PATH 污染 | ✅ 完全隔离 |
| **版本控制** | ❌ 依赖本地 oss-cad 版本 | ✅ `docker pull ghcr.io/yosyshq/yosys:tag` |
| **跨平台** | ❌ Windows 专用二进制 | ✅ 一份镜像 Windows/Mac/Linux 通用 |
| **网络需求** | ✅ 离线可用 | ❌ 首次需要 pull 镜像 |

### 2.3 推荐方案

```
┌─────────────────────────────────────────────────┐
│          环境选择策略（按优先级）                   │
├─────────────────────────────────────────────────┤
│  1. Docker 可用 → 优先 Docker 模式               │
│     - 版本确定，环境隔离，无 DLL 问题              │
│  2. Docker 不可用 + 本地 yosys 可用 → 本地模式     │
│     - 自动降级，需正确设置 oss-cad PATH            │
│  3. 两者均不可用 → graceful 跳过验证               │
│     - 日志记录"验证跳过"，不影响管线完整性           │
└─────────────────────────────────────────────────┘
```

---

## 3. CI 自动化验证

### 3.1 脚本

[run_ci_verify.py](file:///d:/learning/AI_RESEARCH/ai_project/common/scripts/sim/formal_test/run_ci_verify.py) — 4 阶段验证：

| Phase | 检查项 | 超时 | 失败退出码 |
|:-----:|:-------|:----:|:----------:|
| 1 | yosys 语法检查 | 60s | 1 |
| 2 | yosys 综合检查 | 120s | 2 |
| 3 | 全管线验证（tmr 策略，1 轮迭代） | 120s | 3 |
| 4 | 多策略验证（dice, ecc） | 120s | 3 |

### 3.2 用法

```powershell
# 完整验证
python run_ci_verify.py

# 快速验证（仅语法检查）
python run_ci_verify.py --quick

# 保存 JSON 报告
python run_ci_verify.py --report-dir ./ci_reports

# CI 模式
python run_ci_verify.py --ci-mode
```

### 3.3 GitHub Actions 集成示例

```yaml
name: oss-cad verify

on:
  schedule:
    - cron: '0 8 * * 1'  # 每周一 8:00 UTC
  push:
    paths:
      - 'common/scripts/sim/formal_test/**'

jobs:
  verify:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Run CI verify
        run: |
          python common/scripts/sim/formal_test/run_ci_verify.py
```

---

## 4. AST 修复器 TMR 扩展

### 4.1 新增方法

| 方法 | 功能 |
|:-----|:------|
| `_detect_tmr_patterns()` | 检测 triplicate registers（copy0/1/2）、triplicate always blocks、voter 存在性 |
| `_fix_tmr_missing_voter()` | 自动生成 2-of-3 majority voter + error flag（generate-loop 结构） |
| `_fix_tmr_width_mismatch()` | 统一 triplicate 副本位宽为三者最大值 |

### 4.2 检测模式

```
TMR Pattern 1: triplicate_reg
  reg [7:0] copy0;     reg [7:0] copy1;     reg [7:0] copy2;

TMR Pattern 2: triplicate_always
  always @(posedge clk or negedge rst_n) state0 <= ...
  always @(posedge clk or negedge rst_n) state1 <= ...
  always @(posedge clk or negedge rst_n) state2 <= ...

Voter Pattern:
  assign out = (a & b) | (a & c) | (b & c);  → 已存在投票器
  assign out = a | b | c;                     → 非 majority（需修复）
```

---

## 5. 7 阶段管线总览

```
Phase 1/7: Read Input RTL
Phase 2/7: Design Error Analysis
Phase 3/7: RTL Analysis for Hardening
Phase 4/7: RAG Generation (MockLLM: TMR/ECC/DICE/Parity)
Phase 5/7: AST Repair + TMR Detection
Phase 6/7: Auto-Repair Verification Loop
Phase 7/7: Docker Verification (Docker→Local→Skip 三模式降级)
```

### 5.1 典型耗时

| Phase | 典型耗时 | 瓶颈 |
|:-----:|:--------:|:-----|
| 1-4 | < 50ms | RAG 模板生成 |
| 5 | < 30ms | AST 解析 / 正则扫描 |
| 6 | 100-300ms | yosys 语法+综合检查 × 迭代次数 |
| 7 | 50-200ms | yosys 语法+综合检查 |

**完整管线：** 0.3-0.5s（1 次迭代）

---

## 6. 已知限制与后续优化

1. **TMR 修复当前只添加 voting + error flag**，未自动去除冗余副本（需要人工决策哪些保留）
2. **AST 解析成功率受 pyverilog 版本限制**：复杂 SystemVerilog 结构（interface、modport）尚不支持
3. **Docker 模式依赖 `docker` CLI**：当前环境未安装，仅验证了本地降级路径
4. **形式等价性检查**：设计不通过，因为加固前后的 RTL 结构差异大（非直接映射）
5. **`_fix_tmr_missing_voter()` 位宽推导**：当副本声明位于 generate 块或条件编译块时，正则可能遗漏
