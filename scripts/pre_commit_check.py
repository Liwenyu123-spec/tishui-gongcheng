"""提交前快速回归检查。

与 ``完整回归.ps1`` 的分工：

- 本脚本是「提交门禁」，只跑后端快链路（编译、单元用例、Mock 冒烟），
  目标是在几十秒到两分钟内明确告诉提交人「能不能提交」；
- ``完整回归.ps1`` 是发布前的完整回归，额外包含前端生产构建和 RAG 质量评测。

用法::

    python scripts/pre_commit_check.py           # 编译 + 单元用例 + Mock 冒烟 + 差异检查
    python scripts/pre_commit_check.py --full    # 再叠加 RAG 质量回归
    python scripts/pre_commit_check.py --no-smoke # 赶时间时跳过最慢的冒烟

跳过本次检查：``git commit --no-verify``，或设置环境变量 ``SKIP_PRECOMMIT=1``。

全部子命令都在独立进程中运行并带硬超时，某个检查卡住时不会拖死终端；
输出统一按 UTF-8 解码，避免 Windows 控制台代码页把中文提示变成乱码。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# 仓库根目录：本文件位于 <root>/scripts/，因此取两级父目录。
ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"


def python_executable() -> Path:
    """返回项目虚拟环境里的解释器；缺失时回退到当前解释器。

    仓库根的 ``.venv`` 是指向 ``agent/.venv`` 的目录联接，直接调用它可以让
    钩子和手工执行使用同一套依赖。
    """

    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.is_file():
            return candidate
    return Path(sys.executable)


def run_step(name: str, command: list[str], *, cwd: Path, timeout: int, tail: int = 12) -> tuple[bool, str]:
    """执行一个被检查的子命令，返回（是否通过, 供失败排查的输出尾部）。"""

    started = time.monotonic()
    print(f"[{name}] 开始（超时 {timeout}s）", flush=True)
    environment = dict(os.environ)
    # 子进程统一用 UTF-8 输出，父进程按同一编码解码，避免中文提示乱码。
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            timeout=timeout,
            capture_output=True,
            env=environment,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"[{name}] 超时，已结束该子进程。", flush=True)
        return False, "超时"
    except OSError as exc:
        # 解释器或依赖缺失时给出明确原因，而不是抛出回溯。
        print(f"[{name}] 无法启动：{exc}", flush=True)
        return False, str(exc)

    stdout = completed.stdout.decode("utf-8", errors="replace").strip()
    stderr = completed.stderr.decode("utf-8", errors="replace").strip()
    elapsed = time.monotonic() - started
    if completed.returncode != 0:
        print(f"[{name}] 失败（退出码 {completed.returncode}，耗时 {elapsed:.1f}s）", flush=True)
        # 失败时打印输出尾部，便于直接定位是哪个断言或哪个用例挂掉。
        detail = "\n".join(line for line in (stdout, stderr) if line)
        lines = detail.splitlines()[-tail:] if detail else []
        for line in lines:
            print(f"    {line}", flush=True)
        return False, "\n".join(lines)
    print(f"[{name}] 通过（{elapsed:.1f}s）", flush=True)
    return True, ""


def changed_files() -> list[str]:
    """返回本次提交涉及的文件，用于判断是否只改了文档。"""

    try:
        output = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(ROOT),
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line for line in output.stdout.decode("utf-8", errors="replace").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="提交前快速回归检查")
    parser.add_argument("--full", action="store_true", help="额外执行 RAG 质量回归")
    parser.add_argument("--no-smoke", action="store_true", help="跳过最慢的 Mock 冒烟检查")
    args = parser.parse_args()

    if os.environ.get("SKIP_PRECOMMIT") == "1":
        print("已设置 SKIP_PRECOMMIT=1，跳过提交前检查。")
        return 0

    interpreter = str(python_executable())
    # 只改了文档时不值得跑整套后端检查，但仍然执行差异检查防止空白字符问题。
    staged = changed_files()
    docs_only = bool(staged) and all(
        Path(item).suffix.lower() in {".md", ".txt"} or item.startswith(".test-temp/") for item in staged
    )

    print(f"解释器：{interpreter}")
    if docs_only:
        print("本次提交只包含文档，跳过代码检查。")

    steps: list[tuple[str, list[str], Path, int]] = []
    if not docs_only:
        # 编译检查：语法错误会让服务直接起不来，必须先拦住。
        steps.append(("后端编译", [interpreter, "-m", "compileall", "-q", "app"], BACKEND_DIR, 60))
        # 单元用例：秒级反馈，覆盖健康检查、认证边界、权限范围和 Agent 契约。
        steps.append(("后端单元用例", [interpreter, "-m", "pytest", "tests", "-q"], BACKEND_DIR, 180))
        if not args.no_smoke:
            # Mock 冒烟：进程内跑完整业务闭环，是最慢但最有价值的一环。
            steps.append(("Mock 冒烟", [interpreter, "-u", "smoke_test.py"], BACKEND_DIR, 180))
        if args.full:
            # RAG 质量回归只在 --full 下执行，避免每次提交都等重排模型。
            steps.append(("RAG 质量回归", [interpreter, "rag_eval.py", "--provider", "hash"], BACKEND_DIR, 240))
    # 差异检查：防止行尾空白等会让补丁变脏的问题进入仓库。
    steps.append(("差异检查", ["git", "diff", "--check"], ROOT, 30))

    failures: list[str] = []
    for name, command, cwd, timeout in steps:
        passed, _ = run_step(name, command, cwd=cwd, timeout=timeout)
        if not passed:
            failures.append(name)

    if failures:
        print("\n提交前检查未通过：" + "、".join(failures), flush=True)
        print("修复后重新提交；确实需要先提交时可用 git commit --no-verify。", flush=True)
        return 1
    print("\n提交前检查全部通过。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
