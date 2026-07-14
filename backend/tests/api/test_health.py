import asyncio

import httpx

from app.core.config import get_settings
from app.main import app


def test_health_returns_ok() -> None:
    async def request_health() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "ansible": "ok", "credential_encryption": "ok"},
    }


def test_health_is_degraded_with_an_invalid_credential_encryption_key(monkeypatch) -> None:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "not-a-fernet-key")
    get_settings.cache_clear()

    async def request_health() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/health")

    try:
        response = asyncio.run(request_health())
        assert response.status_code == 503
        assert response.json()["checks"]["credential_encryption"] == "degraded"
    finally:
        get_settings.cache_clear()
