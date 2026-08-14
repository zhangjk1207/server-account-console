import asyncio

import httpx

from app.db.models import Host, HostAccessGrant, ManagedUser, SshPublicKey
from app.db.session import SessionLocal
from app.main import app


def test_agent_overview_requires_authentication() -> None:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/agent-context/overview")

    assert asyncio.run(request()).status_code == 401


def test_agent_overview_aggregates_sanitized_domain_health() -> None:
    with SessionLocal() as session:
        reachable = Host(name="gpu-01", address="10.0.0.1", status="reachable")
        offline = Host(name="gpu-02", address="10.0.0.2", status="unreachable")
        member = ManagedUser(username="lin", display_name="Lin", enabled=True)
        session.add_all([reachable, offline, member])
        session.flush()
        session.add(SshPublicKey(managed_user_id=member.id, public_key="ssh-ed25519 test", fingerprint="SHA256:test"))
        session.add(HostAccessGrant(host_id=reachable.id, managed_user_id=member.id, username="lin", state="active"))
        session.commit()

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            return await client.get("/api/agent-context/overview")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.json() == {
        "machines": {"total": 2, "reachable": 1, "attention": 1},
        "members": {"active": 1, "with_keys": 1},
        "grants": {"active": 1},
        "runs": {"active": 0, "failed_recently": 0},
    }
