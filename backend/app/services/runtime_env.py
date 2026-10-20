"""运行时环境变量加载。

项目配置分散在系统环境变量和根目录 `.env` 两处。此前只有
`knowledge_generate` 会加载 `.env`，而 `rag_chroma` 直接读 `os.getenv`，
于是「把 RAG_EMBEDDING_PROVIDER 写进 .env」能否生效取决于模块 import 顺序：
从 `routers.knowledge` 进来刚好生效，从 `rag_chroma` 单独进来就失效。

本模块把加载逻辑集中一处，任何需要配置的模块 import 它即可，行为与顺序无关。
读取优先级：进程环境变量 > 根目录 `.env` > Windows 用户/系统变量。

本模块不读取业务数据，也不连接数据库或外部服务。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 记录本次进程是否已经扫描过 .env，避免重复 IO。
_ENV_FILE_LOADED = False

# 记录 .env 的解析结果，供状态接口排查「配置为什么没生效」。
_ENV_FILE_PATH: Path | None = None
_ENV_FILE_KEYS: list[str] = []


def project_root() -> Path:
    """定位项目根目录：backend/app/services/runtime_env.py 往上三层。"""

    return Path(__file__).resolve().parents[3]


def env_file_path() -> Path:
    """返回 .env 路径；可用 APP_ENV_FILE 覆盖，便于测试隔离。"""

    override = (os.getenv("APP_ENV_FILE") or "").strip()
    return Path(override) if override else project_root() / ".env"


def load_env_file(force: bool = False) -> None:
    """把根目录 .env 的键值并入进程环境。

    只补齐缺失的键，不覆盖已有环境变量：这样系统里显式设置的密钥和调试开关
    仍然优先，符合「临时改环境变量即可调试」的使用习惯。
    """

    global _ENV_FILE_LOADED, _ENV_FILE_PATH, _ENV_FILE_KEYS
    if _ENV_FILE_LOADED and not force:
        return
    _ENV_FILE_LOADED = True
    path = env_file_path()
    _ENV_FILE_PATH = path
    _ENV_FILE_KEYS = []
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        # 配置文件不可读不应阻止服务启动，按「没有 .env」处理。
        return
    for line in lines:
        stripped = line.strip()
        # 跳过空行、注释和没有等号的无效行。
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        # 允许值里带引号，去掉首尾引号后原样保留内部内容。
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        _ENV_FILE_KEYS.append(key)
        if key not in os.environ:
            os.environ[key] = value


def windows_env(name: str) -> str:
    """读取配置值：进程环境 → .env → Windows 用户/系统变量。

    `.env` 在进程环境缺失时已经写入，故这里先查进程环境即可覆盖前两级；
    最后再查注册表，兼容用户把密钥配在系统变量但没重启终端的场景。
    """

    load_env_file()
    value = (os.getenv(name) or "").strip()
    if value:
        return value
    if sys.platform != "win32":
        return ""
    try:
        import winreg
    except ImportError:
        return ""
    for root, path in (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ):
        try:
            with winreg.OpenKey(root, path) as key:
                found, _ = winreg.QueryValueEx(key, name)
        except OSError:
            continue
        text = str(found or "").strip()
        if text:
            return text
    return ""


def env_flag(name: str, default: bool = True) -> bool:
    """把开关型配置解析成布尔值。

    默认开启的开关用 `0 / false / off / none` 关闭；默认关闭的开关用
    `1 / true / on / yes` 打开，避免出现「写了 0 却仍然是开」的歧义。
    """

    raw = windows_env(name).strip().lower()
    if not raw:
        return default
    if raw in {"0", "false", "off", "no", "none"}:
        return False
    if raw in {"1", "true", "on", "yes"}:
        return True
    return default


def env_summary() -> dict:
    """返回配置来源摘要，供 /knowledge/rag/status 展示。"""

    load_env_file()
    return {
        "env_file": str(_ENV_FILE_PATH) if _ENV_FILE_PATH else None,
        "env_file_exists": bool(_ENV_FILE_PATH and _ENV_FILE_PATH.is_file()),
        "env_file_keys": list(_ENV_FILE_KEYS),
    }
