#!/bin/sh
# 提交前快速回归门禁。复制本文件为 .git/hooks/pre-commit 后，git commit 会先跑它。
#
# 只跑后端快链路：编译检查 + pytest 单元用例 + Mock 冒烟 + 差异检查。
# 前端生产构建和 RAG 质量回归不在这次检查里，需要时单独执行。
#
# 需要跳过时：git commit --no-verify

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$ROOT" ]; then
    echo "无法定位仓库根目录，跳过提交前检查。" >&2
    exit 0
fi

PY="$ROOT/.venv/Scripts/python.exe"
if [ ! -f "$PY" ]; then
    PY="$ROOT/.venv/bin/python"
fi
if [ ! -f "$PY" ]; then
    echo "未找到项目虚拟环境解释器，跳过提交前检查。" >&2
    exit 0
fi

exec "$PY" "$ROOT/scripts/pre_commit_check.py"
