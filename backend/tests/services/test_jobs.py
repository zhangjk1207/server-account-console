import pytest

from app.db.models import Job
from app.db.session import SessionLocal
from app.services import jobs
from app.services.jobs import JobStateError, ensure_executable


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

        monkeypatch.setattr(jobs, "_execute_locked_job", fail)
        result = jobs.execute_job(session, job, check=True)

        assert result.state == "preview_failed"
        assert result.finished_at is not None
