import asyncio

import httpx

from app.main import app


def test_login_creates_http_only_session_and_me_requires_it() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            unauthenticated = await client.get("/api/auth/me")
            assert unauthenticated.status_code == 401

            login = await client.post("/api/auth/login", json={"password": "correct-horse"})
            assert login.status_code == 204
            assert "httponly" in login.headers["set-cookie"].lower()

            authenticated = await client.get("/api/auth/me")
            assert authenticated.status_code == 200
            assert authenticated.json() == {"authenticated": True}

    asyncio.run(scenario())
