import asyncio

import httpx

from app.main import app


def test_admin_can_manage_permission_templates() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            created = await client.post(
                "/api/permission-templates",
                json={"name": "Docker training", "description": "GPU training", "groups": ["docker", "video"], "sudo_rule": None},
                headers={"X-CSRF-Token": token},
            )
            assert created.status_code == 201
            assert created.json()["groups"] == ["docker", "video"]

            updated = await client.patch(
                f"/api/permission-templates/{created.json()['id']}",
                json={"groups": ["docker"]},
                headers={"X-CSRF-Token": token},
            )
            assert updated.status_code == 200
            assert updated.json()["groups"] == ["docker"]

    asyncio.run(scenario())
