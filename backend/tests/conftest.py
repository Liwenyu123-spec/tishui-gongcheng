"""共享的离线 FastAPI 测试夹具。

测试默认使用临时 RAG 目录和规则 Agent，不访问外部模型，也不污染
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
os.environ.setdefault("RAG_EMBEDDING_PROVIDER", "hash")
os.environ.setdefault("RAG_RERANK_ENABLED", "0")
os.environ.setdefault("RAG_GENERATION_ENABLED", "0")
os.environ.setdefault("AGENT_LLM_ENABLED", "0")
os.environ["RAG_CHROMA_DIR"] = str(Path(_TEMP_ROOT) / "chroma")
os.environ["KNOWLEDGE_STORE_DIR"] = str(Path(_TEMP_ROOT) / "knowledge")

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    """启动一次应用生命周期，确保健康检查和 RAG 状态可用。"""

    with TestClient(app) as test_client:
        yield test_client


def auth(client: TestClient, username: str = "admin", password: str = "admin123") -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def admin_headers(client):
    return auth(client)


@pytest.fixture()
def station_headers(client):
    return auth(client, "station-operator", "station123")
