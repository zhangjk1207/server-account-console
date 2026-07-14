import asyncio

import httpx

from app.main import app


HOST_PAYLOAD = {
    "name": "lab-01",
    "address": "192.0.2.10",
    "port": 22,
    "ssh_user": "ops",
    "tags": ["lab", "gpu"],
}


def test_create_host_requires_login() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/hosts", json=HOST_PAYLOAD)
            assert response.status_code == 401

    asyncio.run(scenario())


def test_logged_in_admin_can_create_unconfirmed_host_with_csrf() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]

            response = await client.post("/api/hosts", json=HOST_PAYLOAD, headers={"X-CSRF-Token": token})
            assert response.status_code == 201
            assert response.json()["status"] == "unconfirmed"
            assert response.json()["tags"] == ["gpu", "lab"]

    asyncio.run(scenario())
