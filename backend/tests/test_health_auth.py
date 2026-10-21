"""健康检查和认证边界的最小回归用例。"""

from __future__ import annotations

# 启动状态在同步模式下会走到终态，但允许「准备中」和「未开始」，
# 因为用例校验的是字段结构稳定，不是模型加载速度。
_RAG_STATUSES = {"not_started", "starting", "ready", "degraded", "failed"}


def test_health_reports_rag_lifecycle(client):
    """健康检查必须暴露启动阶段状态，供单地址模式判断 RAG 是否就绪。"""

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # 字段名是 startup；更早的版本叫 rag，前端现在按 startup.status 展示启动提示。
    startup = body["startup"]
    assert isinstance(startup, dict)
    assert startup["status"] in _RAG_STATUSES
    assert "phase" in startup


def test_protected_routes_require_valid_token(client):
    """无 Token 和错误 Token 都必须被拒绝，避免 Mock 阶段放开鉴权。"""

    assert client.get("/api/v1/stations").status_code == 401
    assert client.get("/api/v1/stations", headers={"Authorization": "Bearer invalid-token"}).status_code == 401
