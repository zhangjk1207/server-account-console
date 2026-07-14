import asyncio

import httpx

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
