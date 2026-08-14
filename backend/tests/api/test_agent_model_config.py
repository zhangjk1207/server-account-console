import asyncio

import httpx
from sqlalchemy import select

from app.db.models import AgentModelConfig
from app.db.session import SessionLocal
from app.main import app


def test_model_config_is_encrypted_redacted_and_runtime_scoped() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            csrf = (await client.get("/api/auth/csrf")).json()["token"]
            response = await client.put(
                "/api/agent-model-config",
                headers={"X-CSRF-Token": csrf},
                json={"provider": "openai-compatible", "model": "deepseek-chat", "base_url": "https://models.example.test/v1", "api_key": "model-secret", "thinking_level": "high", "enabled": True},
            )
            assert response.status_code == 200
            assert response.json()["api_key_configured"] is True
            assert "model-secret" not in response.text
            public = await client.get("/api/agent-model-config")
            assert public.status_code == 200
            assert "model-secret" not in public.text
            assert (await client.get("/api/agent-model-config/internal")).status_code == 401
            internal = await client.get("/api/agent-model-config/internal", headers={"X-Agent-Runtime-Token": "test-agent-runtime-token"})
            assert internal.status_code == 200
            assert internal.json()["api_key"] == "model-secret"
            assert internal.json()["enabled"] is True
        with SessionLocal() as session:
            record = session.scalar(select(AgentModelConfig))
            assert record is not None
            assert "model-secret" not in record.api_key_ciphertext
    asyncio.run(scenario())


def test_updating_model_without_key_preserves_existing_ciphertext() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            csrf = (await client.get("/api/auth/csrf")).json()["token"]
            initial = {"provider": "openai", "model": "gpt-5.2", "api_key": "keep-me", "thinking_level": "medium", "enabled": True}
            assert (await client.put("/api/agent-model-config", headers={"X-CSRF-Token": csrf}, json=initial)).status_code == 200
            update = {"provider": "openai", "model": "gpt-5.2", "api_key": None, "thinking_level": "low", "enabled": True}
            assert (await client.put("/api/agent-model-config", headers={"X-CSRF-Token": csrf}, json=update)).status_code == 200
            internal = await client.get("/api/agent-model-config/internal", headers={"X-Agent-Runtime-Token": "test-agent-runtime-token"})
            assert internal.json()["api_key"] == "keep-me"
            assert internal.json()["thinking_level"] == "low"
    asyncio.run(scenario())
