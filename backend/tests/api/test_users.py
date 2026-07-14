import asyncio

import httpx

from app.main import app


VALID_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAGkvVkSy22CofC/G8JlQVqBe1HMv/b8MWBNkdQ1spaR test-key"


async def authenticated_client() -> tuple[httpx.AsyncClient, str]:
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    await client.post("/api/auth/login", json={"password": "correct-horse"})
    token = (await client.get("/api/auth/csrf")).json()["token"]
    return client, token


def test_rejects_invalid_linux_username() -> None:
    async def scenario() -> None:
        client, token = await authenticated_client()
        try:
            response = await client.post("/api/users", json={"username": "not valid"}, headers={"X-CSRF-Token": token})
            assert response.status_code == 422
        finally:
            await client.aclose()

    asyncio.run(scenario())


def test_adds_public_key_and_rejects_duplicate_fingerprint() -> None:
    async def scenario() -> None:
        client, token = await authenticated_client()
        try:
            user = await client.post("/api/users", json={"username": "alice", "display_name": "Alice"}, headers={"X-CSRF-Token": token})
            assert user.status_code == 201

            first = await client.post(f"/api/users/{user.json()['id']}/keys", json={"public_key": VALID_KEY}, headers={"X-CSRF-Token": token})
            assert first.status_code == 201
            assert first.json()["fingerprint"].startswith("SHA256:")

            duplicate = await client.post(f"/api/users/{user.json()['id']}/keys", json={"public_key": VALID_KEY}, headers={"X-CSRF-Token": token})
            assert duplicate.status_code == 409
        finally:
            await client.aclose()

    asyncio.run(scenario())
