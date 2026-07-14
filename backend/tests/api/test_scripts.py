import asyncio

import httpx

from app.main import app


def test_updating_script_body_increments_its_version() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            headers = {"X-CSRF-Token": token}

            created = await client.post("/api/script-templates", json={"name": "prepare-home", "body": "mkdir -p /srv/home"}, headers=headers)
            assert created.status_code == 201
            assert created.json()["version"] == 1

            updated = await client.patch(f"/api/script-templates/{created.json()['id']}", json={"body": "chmod 0750 /srv/home"}, headers=headers)
            assert updated.status_code == 200
            assert updated.json()["version"] == 2

    asyncio.run(scenario())
