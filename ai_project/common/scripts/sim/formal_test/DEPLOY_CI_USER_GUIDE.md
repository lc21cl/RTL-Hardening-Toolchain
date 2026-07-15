# Deploy CI 自动化部署脚本使用手册

## 概述

`deploy_ci.py` 是一个集成了回归测试和 Git 自动提交的 CI 自动化部署脚本，用于快速验证加固策略修复逻辑并自动部署到代码仓库。

### 核心功能

| 功能 | 描述 |
|------|------|
| 回归测试 | 运行完整的回归测试套件，包含 ECC+TMR 混合策略 |
| 日志记录 | 记录 RAG 缓存命中情况、AST 修复迭代次数等详细信息 |
| Git 提交 | 自动收集测试结果并提交到 Git 仓库 |
| 报告生成 | 支持生成 JSON 格式的测试报告 |

---

## 安装与环境

### 前置依赖

- Python 3.8+
- Git（已配置远程仓库）
- 项目依赖：`test_regression_suite.py`、`rag_integration.py` 等

### 脚本位置

```
ai_project/common/scripts/sim/formal_test/deploy_ci.py
```

---

## 命令行参数

### 基本用法

```bash
python deploy_ci.py [选项]
```

### 参数列表

| 参数 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `--quick` | 开关 | 快速模式：仅运行基础测试，跳过部分验证 | `false` |
| `--dry-run` | 开关 | 模拟运行模式：执行测试但不提交到 Git | `false` |
| `--branch` | 字符串 | 指定目标分支 | 当前分支 |
| `--report-dir` | 字符串 | 指定测试报告保存目录 | 不保存 |

### 参数说明

#### `--quick`

快速模式会跳过部分深度验证，适用于日常开发中的快速检查：

```bash
python deploy_ci.py --quick
```

#### `--dry-run`

模拟运行模式用于验证脚本流程是否正常，不会实际执行 Git 提交和推送：

```bash
python deploy_ci.py --dry-run
```

#### `--branch`

指定要切换和提交的目标分支：

```bash
python deploy_ci.py --branch feature/my-feature
```

#### `--report-dir`

将测试结果保存为 JSON 报告到指定目录：

```bash
python deploy_ci.py --report-dir ./ci_reports
```

---

## 使用示例

### 示例 1：完整运行并提交

```bash
cd ai_project/common/scripts/sim/formal_test
python deploy_ci.py
```

**输出示例**：
```
[2026-07-15 13:07:13] [INFO] ============================================================
[2026-07-15 13:07:13] [INFO]   CI Automated Deployment Script
[2026-07-15 13:07:13] [INFO] ============================================================
[2026-07-15 13:07:13] [INFO]   Step 1: Running Regression Test Suite
[2026-07-15 13:07:21] [INFO]   Result: PASSED (8.66s)
[2026-07-15 13:07:21] [INFO]   Tests: 8/8 passed
[2026-07-15 13:07:21] [INFO]   RAG Cache: 0 hits, 0 misses
[2026-07-15 13:07:24] [INFO]   Step 2: Git Commit & Push
[2026-07-15 13:07:24] [INFO]   Committed: abc1234
[2026-07-15 13:07:24] [INFO] ============================================================
[2026-07-15 13:07:24] [INFO]   DEPLOYMENT COMPLETED SUCCESSFULLY (10.97s)
[2026-07-15 13:07:24] [INFO] ============================================================
```

### 示例 2：快速模式 + 模拟运行

```bash
python deploy_ci.py --quick --dry-run
```

### 示例 3：指定分支并生成报告

```bash
python deploy_ci.py --branch main --report-dir ./ci_reports
```

---

## 执行流程

### 完整流程

```
┌─────────────────────────────────────────────────────────────┐
│                      开始执行                               │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: 运行回归测试套件                                   │
│  ├── 执行 test_regression_suite.py                         │
│  ├── 收集测试结果 (passed_count/total_count)               │
│  └── 解析 RAG 缓存命中信息 (hits/misses)                    │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  测试结果判断                                               │
│  ├── 通过 → 继续下一步                                      │
│  └── 失败 → 输出错误日志并退出 (exit code: 1)               │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  (可选) 生成测试报告                                        │
│  └── 保存 JSON 格式报告到 --report-dir 指定目录             │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Git 提交与推送                                    │
│  ├── 切换到指定分支 (--branch)                              │
│  ├── 暂存所有变更 (git add .)                               │
│  ├── 检查是否有变更                                         │
│  ├── 生成提交信息 (包含测试结果)                            │
│  └── 推送代码到远程仓库                                     │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      部署完成                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 退出码说明

| 退出码 | 含义 | 处理建议 |
|--------|------|----------|
| `0` | 全部通过并提交成功 | 正常完成 |
| `1` | 测试失败 | 检查测试输出，修复代码 |
| `2` | Git 操作失败 | 检查 Git 配置和网络连接 |

---

## 常见错误排查指南

### 错误 1：回归测试失败

**现象**：
```
[2026-07-15 13:07:21] [ERROR]   Regression tests failed!
```

**排查步骤**：

1. **查看测试输出**：
   ```bash
   python test_regression_suite.py --quick
   ```

2. **检查具体失败的策略**：
   - TMR_ECC 策略失败：检查 `rag_integration.py` 中的 `_tmr_ecc_rtl` 方法
   - 其他策略失败：检查对应的模板生成逻辑

3. **检查 Verilog 语法**：
   - 使用 yosys 检查生成的 RTL 文件
   - 确认位宽表达式是常量

### 错误 2：Git 提交失败

**现象**：
```
[2026-07-15 13:07:24] [ERROR]   Failed to commit: ...
```

**排查步骤**：

1. **检查 Git 配置**：
   ```bash
   git config user.name
   git config user.email
   ```

2. **检查远程仓库连接**：
   ```bash
   git remote -v
   git fetch origin
   ```

3. **检查分支状态**：
   ```bash
   git status
   git branch -a
   ```

4. **手动执行 Git 命令**：
   ```bash
   git add .
   git commit -m "Test commit"
   git push origin <branch>
   ```

### 错误 3：RAG 缓存解析失败

**现象**：
```
ValueError: invalid literal for int() with base 10
```

**原因**：测试输出格式变化导致解析失败。

**修复方法**：
1. 检查 `test_regression_suite.py` 的输出格式
2. 更新 `deploy_ci.py` 中 `run_regression_test` 函数的解析逻辑

### 错误 4：分支切换失败

**现象**：
```
[2026-07-15 13:07:21] [ERROR]   Failed to checkout branch: xxx
```

**排查步骤**：

1. **确认分支存在**：
   ```bash
   git branch -a | grep xxx
   ```

2. **拉取远程分支**：
   ```bash
   git fetch origin xxx
   git checkout xxx
   ```

### 错误 5：推送失败（权限问题）

**现象**：
```
[2026-07-15 13:07:24] [ERROR]   Failed to push: Permission denied
```

**排查步骤**：

1. **检查远程 URL**：
   ```bash
   git remote get-url origin
   ```

2. **配置 SSH 密钥或 HTTPS 凭据**：
   - SSH 方式：确保 SSH 密钥已添加到 GitHub/GitLab
   - HTTPS 方式：使用 credential helper 保存凭据

---

## 日志说明

### 日志级别

| 级别 | 标识 | 含义 |
|------|------|------|
| INFO | `[INFO]` | 正常执行信息 |
| ERROR | `[ERROR]` | 错误信息 |

### 关键日志信息

#### 测试结果日志

```
[2026-07-15 13:07:21] [INFO]   Result: PASSED (8.66s)
[2026-07-15 13:07:21] [INFO]   Tests: 8/8 passed
[2026-07-15 13:07:21] [INFO]   RAG Cache: 0 hits, 0 misses
```

**字段说明**：
- `Result`: 测试结果（PASSED/FAILED）
- `Tests`: 通过/总数
- `RAG Cache`: RAG 缓存命中/未命中次数

#### Git 操作日志

```
[2026-07-15 13:07:24] [INFO]   Committed: abc1234
[2026-07-15 13:07:24] [INFO]   Branch:     main
```

---

## 提交信息格式

脚本自动生成的提交信息包含详细的测试结果：

```
CI: Automated deployment - 2026-07-15 13:07:24

- Regression tests: PASSED
- Tests: 8/8
- RAG Cache: 0 hits, 0 misses
- Quick mode: False

Test Details:
    - Strategy:TMR: ✅ PASS (iter=1, lines=66)
    - Strategy:ECC: ✅ PASS (iter=1, lines=66)
    - Strategy:TMR_ECC: ✅ PASS (iter=1, lines=66)

Files updated:
- ai_project/common/scripts/sim/formal_test/test_regression_suite.py
- ai_project/common/scripts/sim/formal_test/rag_integration.py
- ai_project/common/scripts/sim/formal_test/deploy_ci.py
```

---

## 测试报告格式

使用 `--report-dir` 参数生成的 JSON 报告格式如下：

```json
{
  "status": "PASSED",
  "timestamp": "2026-07-15T13:07:24.123456",
  "quick_mode": false,
  "branch": "main",
  "test_result": {
    "passed": true,
    "passed_count": 8,
    "total_count": 8,
    "elapsed": 8.66,
    "rag_cache_hits": 0,
    "rag_cache_misses": 0
  },
  "test_details": [
    {
      "name": "Strategy:TMR",
      "status": "✅",
      "elapsed": "0.27s",
      "iterations": "1",
      "hardened_lines": "66"
    }
  ]
}
```

---

## 注意事项

1. **首次运行前**：确保 Git 用户信息已配置
2. **网络环境**：需要能访问远程 Git 仓库
3. **分支保护**：如果目标分支有保护规则，需要相应权限
4. **测试时间**：完整测试约需 10-30 秒，取决于测试数量
5. **数据文件**：脚本会自动暂存所有变更，包括模型文件和测试数据

---

## 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2026-07-15 | 初始版本：支持回归测试、Git 提交、报告生成 |

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `deploy_ci.py` | CI 自动化部署脚本 |
| `test_regression_suite.py` | 回归测试套件 |
| `rag_integration.py` | RAG 集成模块（包含 TMR+ECC 混合策略） |
| `run_ci_verify.py` | CI 验证脚本 |
| `deploy_ci.sh` | Bash 版本的部署脚本 |
