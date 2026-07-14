from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import Host, Job, JobTarget, ManagedUser
from app.db.session import SessionLocal
from app.services import jobs
from app.services.jobs import (
    JobStateError,
    apply_runner_events,
    create_and_start_job,
    ensure_executable,
    expire_ready_previews,
    finalize_host_user_states,
    utc_now,
)


def test_only_ready_preview_can_execute() -> None:
    with pytest.raises(JobStateError):
        ensure_executable("preview_running")

    ensure_executable("ready_to_confirm")


def test_failed_preview_finishes_when_fingerprint_validation_fails(monkeypatch) -> None:
    with SessionLocal() as session:
        job = Job(kind="sync", state="preview_running")
        session.add(job)
        session.commit()

        def fail(*_args, **_kwargs):
            raise JobStateError("主机 lab-01 的指纹校验失败")

        monkeypatch.setattr(jobs, "_run_job", fail)
        result = jobs.execute_job(session, job, check=True)

        assert result.state == "preview_failed"
        assert result.finished_at is not None


def test_ready_preview_expires_after_thirty_minutes() -> None:
    with SessionLocal() as session:
        job = Job(kind="sync", state="ready_to_confirm", finished_at=utc_now() - timedelta(minutes=31))
        session.add(job)
        session.commit()

        assert expire_ready_previews(session, now=utc_now()) == 1
        assert session.get(Job, job.id).state == "expired"


def test_runner_failure_only_marks_the_affected_target() -> None:
    with SessionLocal() as session:
        first = Host(name="lab-01", address="192.0.2.10")
        second = Host(name="lab-02", address="192.0.2.11")
        job = Job(
            kind="sync",
            state="running",
            request_snapshot={"hosts": [{"id": "first", "name": "lab-01"}, {"id": "second", "name": "lab-02"}]},
        )
        session.add_all([first, second, job])
        session.flush()
        session.add_all([
            JobTarget(job_id=job.id, host_id=first.id, state="pending"),
            JobTarget(job_id=job.id, host_id=second.id, state="pending"),
        ])
        session.commit()

        apply_runner_events(session, job, [{"event": "runner_on_failed", "stdout": "permission denied", "event_data": {"host": "lab-02"}}])

        targets = {target.host_id: target for target in session.scalars(select(JobTarget).where(JobTarget.job_id == job.id))}
        assert targets[first.id].state == "pending"
        assert targets[second.id].state == "failed"
        assert targets[second.id].error == "permission denied"


def test_successful_targets_update_user_host_state() -> None:
    with SessionLocal() as session:
        host = Host(name="lab-01", address="192.0.2.10")
        user = ManagedUser(username="alice", home="/home/alice")
        job = Job(kind="sync", state="succeeded", request_snapshot={"user_id": "placeholder"})
        session.add_all([host, user, job])
        session.flush()
        job.request_snapshot = {"user_id": user.id}
        session.add(JobTarget(job_id=job.id, host_id=host.id, state="succeeded"))
        session.commit()

        finalize_host_user_states(session, job, desired_hash="desired-state-hash")

        state = session.execute(select(jobs.HostUserState).where(jobs.HostUserState.host_id == host.id)).scalar_one()
        assert state.last_success_job_id == job.id
        assert state.desired_hash == "desired-state-hash"


def test_lock_conflict_does_not_create_an_orphan_preview() -> None:
    assert jobs.RUNNER_LOCK.acquire(blocking=False)
    try:
        with SessionLocal() as session:
            with pytest.raises(JobStateError, match="已有任务正在运行"):
                create_and_start_job(session, None, [], None, check=True)
            assert list(session.scalars(select(Job))) == []
    finally:
        jobs.RUNNER_LOCK.release()
