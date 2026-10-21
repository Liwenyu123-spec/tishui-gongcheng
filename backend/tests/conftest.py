"""共享的离线 FastAPI 测试夹具。

测试固定使用哈希向量、关闭重排和知识生成、关闭 Agent 外部模型调用，
并把向量库、知识正文和照片目录都指向临时目录，不访问外部服务，也不污染
``backend/data`` 中的开发数据。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_TEMP_ROOT = tempfile.mkdtemp(prefix="water_dispatch_pytest_")
# 检索链路固定走本地确定性向量，测试结果不随模型版本变化。
os.environ.setdefault("RAG_EMBEDDING_PROVIDER", "hash")
os.environ.setdefault("RAG_RERANK_ENABLED", "0")
os.environ.setdefault("RAG_GENERATION_ENABLED", "0")
os.environ.setdefault("AGENT_LLM_ENABLED", "0")
# 启动阶段同步完成：否则后台线程会在用例结束后继续写临时 Chroma 目录，
# 造成偶发的句柄占用和「健康检查状态不稳定」。
os.environ["RAG_STARTUP_MODE"] = "blocking"
# 三类落盘数据都指向同一临时根目录，保证用例不产生仓库内文件。
os.environ["RAG_CHROMA_DIR"] = str(Path(_TEMP_ROOT) / "chroma")
os.environ["KNOWLEDGE_STORE_DIR"] = str(Path(_TEMP_ROOT) / "knowledge")
os.environ["PHOTO_STORE_DIR"] = str(Path(_TEMP_ROOT) / "site_photos")

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    """启动一次应用生命周期，确保健康检查和 RAG 状态可用。"""

    with TestClient(app) as test_client:
        yield test_client


def auth(client: TestClient, username: str = "admin", password: str = "admin123") -> dict[str, str]:
    """登录并返回可直接放入请求头的 Authorization。"""

    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def admin_headers(client):
    return auth(client)


@pytest.fixture()
def station_headers(client):
    return auth(client, "station-operator", "station123")
