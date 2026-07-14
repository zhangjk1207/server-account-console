import asyncio

import httpx
import pytest

from app.db.models import Host, Job, JobTarget, ManagedUser
from app.db.session import SessionLocal
from app.main import app


def test_job_detail_returns_frozen_snapshots_and_per_host_results() -> None:
    with SessionLocal() as session:
        host = Host(name="lab-01", address="192.0.2.10")
        user = ManagedUser(username="alice", home="/home/alice")
        job = Job(
            kind="sync",
            state="ready_to_confirm",
            user_snapshot={"username": "alice"},
            request_snapshot={"user_id": "user-1", "hosts": []},
            script_snapshot={"name": "prepare-home", "version": 3},
        )
        session.add_all([host, user, job])
        session.flush()
        session.add(JobTarget(job_id=job.id, host_id=host.id, state="succeeded", output="ok"))
        session.commit()
        job_id = job.id
        host_id = host.id

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            response = await client.get(f"/api/jobs/{job_id}")

            assert response.status_code == 200
            payload = response.json()
            assert payload["user_snapshot"] == {"username": "alice"}
            assert payload["script_snapshot"] == {"name": "prepare-home", "version": 3}
            assert payload["targets"] == [{
                "host_id": host_id,
                "host_name": "lab-01",
                "state": "succeeded",
                "output": "ok",
                "error": None,
                "started_at": None,
                "finished_at": None,
            }]

    asyncio.run(scenario())


def test_preview_starts_background_job_and_returns_without_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as session:
        host = Host(name="lab-01", address="192.0.2.10", status="reachable", host_key_fingerprint="SHA256:confirmed")
        user = ManagedUser(username="alice", home="/home/alice")
        session.add_all([host, user])
        session.commit()
        host_id, user_id = host.id, user.id

    def fake_start(session, user, hosts, script, *, check):
        job = Job(kind="sync", state="preview_running", request_snapshot={"user_id": user.id, "host_ids": [hosts[0].id], "hosts": []})
        session.add(job)
        session.flush()
        session.add(JobTarget(job_id=job.id, host_id=hosts[0].id, state="pending"))
        session.commit()
        return job

    monkeypatch.setattr("app.api.jobs.create_and_start_job", fake_start)

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            response = await client.post("/api/jobs/preview", json={"user_id": user_id, "host_ids": [host_id]}, headers={"X-CSRF-Token": token})

            assert response.status_code == 202
            assert response.json()["state"] == "preview_running"

    asyncio.run(scenario())


def test_execute_rejects_a_preview_that_is_not_ready_to_confirm() -> None:
    with SessionLocal() as session:
        job = Job(kind="sync", state="preview_running")
        session.add(job)
        session.commit()
        job_id = job.id

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/login", json={"password": "correct-horse"})
            token = (await client.get("/api/auth/csrf")).json()["token"]
            response = await client.post(f"/api/jobs/{job_id}/execute", headers={"X-CSRF-Token": token})

            assert response.status_code == 409
            assert response.json()["detail"] == "只有预检完成的任务可以执行"

    asyncio.run(scenario())
