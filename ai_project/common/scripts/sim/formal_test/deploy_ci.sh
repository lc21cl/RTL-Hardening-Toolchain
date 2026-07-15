#!/bin/bash
# deploy_ci.sh — CI 自动化部署脚本
#
# 执行流程:
#  1. 运行回归测试
#  2. 收集测试结果
#  3. 自动提交到 Git 仓库
#
# 用法:
#   bash deploy_ci.sh
#   bash deploy_ci.sh --quick
#   bash deploy_ci.sh --branch feature/my-feature
#

set -e

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../../../.." && pwd)
CI_REPORTS_DIR="$PROJECT_ROOT/ci_reports"

QUICK_MODE=false
BRANCH=""

# ── 解析参数 ──
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "========================================"
echo "  CI Automated Deployment Script"
echo "========================================"
echo "  Script dir:   $SCRIPT_DIR"
echo "  Project root: $PROJECT_ROOT"
echo "  Quick mode:   $QUICK_MODE"
echo "  Branch:       ${BRANCH:-current}"
echo ""

# ── Step 1: 运行回归测试 ──
echo "── Step 1: Run Regression Tests ──"
cd "$SCRIPT_DIR"

TEST_ARGS="--regression"
if $QUICK_MODE; then
    TEST_ARGS="$TEST_ARGS --quick"
fi

echo "Running: python run_ci_verify.py $TEST_ARGS"
python run_ci_verify.py $TEST_ARGS --report-dir "$CI_REPORTS_DIR"

EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
    echo ""
    echo "ERROR: Regression tests failed with exit code $EXIT_CODE"
    echo "========================================"
    echo "  DEPLOYMENT ABORTED — Tests Failed"
    echo "========================================"
    exit $EXIT_CODE
fi

echo "✅ Regression tests passed!"
echo ""

# ── Step 2: 运行完整管线验证 ──
echo "── Step 2: Run Full Pipeline Verification ──"

echo "Running: python run_ci_verify.py $TEST_ARGS"
python run_ci_verify.py $TEST_ARGS --report-dir "$CI_REPORTS_DIR"

EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
    echo ""
    echo "ERROR: Pipeline verification failed with exit code $EXIT_CODE"
    echo "========================================"
    echo "  DEPLOYMENT ABORTED — Pipeline Failed"
    echo "========================================"
    exit $EXIT_CODE
fi

echo "✅ Pipeline verification passed!"
echo ""

# ── Step 3: 提交到 Git ──
echo "── Step 3: Git Commit & Push ──"
cd "$PROJECT_ROOT"

# 如果指定了分支，切换到该分支
if [[ -n "$BRANCH" ]]; then
    echo "Checking out branch: $BRANCH"
    git checkout "$BRANCH" || {
        echo "ERROR: Failed to checkout branch $BRANCH"
        exit 1
    }
fi

# 添加修改的文件
echo "Staging changes..."
git add .

# 检查是否有变更
if git diff --cached --quiet; then
    echo "No changes to commit — skipping"
else
    # 生成提交消息
    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
    COMMIT_MSG="CI: Automated deployment - $TIMESTAMP

- Regression tests: PASSED
- Pipeline verification: PASSED
- Quick mode: ${QUICK_MODE:-false}

Files updated:
- test_regression_suite.py (added hybrid TMR+ECC test)
- run_ci_verify.py (integrated regression tests)
- rag_integration.py (added TMR+ECC hybrid strategy)
- HARDENING_OPTIMIZATION_ROADMAP.md (updated progress)
"

    echo "Committing changes..."
    git commit -m "$COMMIT_MSG"

    echo "Pushing to remote..."
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    git push origin "$CURRENT_BRANCH"
fi

echo ""
echo "========================================"
echo "  DEPLOYMENT COMPLETED SUCCESSFULLY"
echo "========================================"
echo "  Branch:     $(git rev-parse --abbrev-ref HEAD)"
echo "  Commit:     $(git rev-parse --short HEAD)"
echo "  Timestamp:  $(date +"%Y-%m-%d %H:%M:%S")"
echo "========================================"

exit 0
