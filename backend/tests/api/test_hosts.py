import asyncio

import httpx

from app.api import hosts as hosts_api
from app.db.models import Job, JobTarget
from app.db.session import SessionLocal
from app.main import app
from app.services.hosts import HostProbeResult


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


def test_fingerprint_confirmation_rejects_a_key_that_changed_since_test(monkeypatch) -> None:
    monkeypatch.setattr(hosts_api, "_scan_ed25519_key", lambda _host: ("SHA256:current", "lab-01 ssh-ed25519 AAAA", None), raising=False)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            host = await client.post("/api/hosts", json=HOST_PAYLOAD, headers={"X-CSRF-Token": token})
            response = await client.post(
                f"/api/hosts/{host.json()['id']}/confirm-fingerprint",
                json={"fingerprint": "SHA256:stale"},
                headers={"X-CSRF-Token": token},
            )

            assert response.status_code == 409

    asyncio.run(scenario())


def test_fingerprint_confirmation_runs_authenticated_probe_and_enables_host(monkeypatch) -> None:
    monkeypatch.setattr(hosts_api, "_scan_ed25519_key", lambda _host: ("SHA256:current", "lab-01 ssh-ed25519 AAAA", None))
    monkeypatch.setattr(
        hosts_api,
        "probe_host",
        lambda _host: HostProbeResult(fingerprint="SHA256:current", reachable=True, latency_ms=12, known_host_line="lab-01 ssh-ed25519 AAAA"),
    )

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            host = await client.post("/api/hosts", json=HOST_PAYLOAD, headers={"X-CSRF-Token": token})
            response = await client.post(
                f"/api/hosts/{host.json()['id']}/confirm-fingerprint",
                json={"fingerprint": "SHA256:current"},
                headers={"X-CSRF-Token": token},
            )

            assert response.status_code == 200
            assert response.json()["status"] == "reachable"
            assert response.json()["last_probe_latency_ms"] == 12

    asyncio.run(scenario())


def test_cannot_archive_host_referenced_by_active_job() -> None:
    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            host = await client.post("/api/hosts", json=HOST_PAYLOAD, headers={"X-CSRF-Token": token})
            host_id = host.json()["id"]
            with SessionLocal() as session:
                job = Job(kind="sync", state="running")
                session.add(job)
                session.flush()
                session.add(JobTarget(job_id=job.id, host_id=host_id, state="running"))
                session.commit()

            response = await client.delete(f"/api/hosts/{host_id}", headers={"X-CSRF-Token": token})
            assert response.status_code == 409

    asyncio.run(scenario())
