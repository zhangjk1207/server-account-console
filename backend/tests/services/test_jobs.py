import pytest

from app.services.jobs import JobStateError, ensure_executable


def test_only_ready_preview_can_execute() -> None:
    with pytest.raises(JobStateError):
        ensure_executable("preview_running")

    ensure_executable("ready_to_confirm")
