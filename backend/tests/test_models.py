from app.db import models  # noqa: F401
from app.db.base import Base


def test_initial_metadata_contains_mvp_tables() -> None:
    expected = {
        "hosts",
        "managed_users",
        "ssh_public_keys",
        "script_templates",
        "jobs",
        "job_targets",
        "host_user_states",
    }

    assert expected.issubset(Base.metadata.tables)
