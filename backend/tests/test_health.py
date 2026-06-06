"""健康检查 endpoint 测试 — PR#1 脚手架第一个 test。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    """GET /health → 200 + status=ok"""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "hunjing-screenplay"
    assert "version" in body


def test_root_gives_guidance():
    """GET / → 给好奇用户引导"""
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["health"] == "/health"
    assert body["docs"] == "/docs"


def test_health_includes_llm_info():
    """健康检查应暴露 LLM 模型信息(供 demo / 监控用)"""
    r = client.get("/health")
    body = r.json()
    assert body["llm_model"] == "deepseek-chat"
    # llm_configured 字段:测试环境用 placeholder key,应返 False
    assert "llm_configured" in body
