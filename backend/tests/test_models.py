import pytest
from sqlalchemy.exc import IntegrityError

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import Host, HostAccessGrant, ManagedUser, PermissionTemplate
from app.db.session import SessionLocal


def test_initial_metadata_contains_mvp_tables() -> None:
    expected = {
        "hosts",
        "managed_users",
        "ssh_public_keys",
        "script_templates",
        "jobs",
        "job_targets",
        "host_user_states",
        "permission_templates",
        "host_access_grants",
    }

    assert expected.issubset(Base.metadata.tables)


def test_host_access_grant_is_unique_for_a_member_and_machine() -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-01", address="192.0.2.10", data_root="/mnt/train")
        user = ManagedUser(username="alice")
        session.add_all([host, user])
        session.flush()
        session.add_all(
            [
                HostAccessGrant(
                    host_id=host.id,
                    managed_user_id=user.id,
                    username="alice",
                    data_directory="/mnt/train/alice",
                ),
                HostAccessGrant(
                    host_id=host.id,
                    managed_user_id=user.id,
                    username="alice2",
                    data_directory="/mnt/train/alice2",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_active_grants_cannot_reuse_a_linux_username_on_the_same_machine() -> None:
    with SessionLocal() as session:
        host = Host(name="gpu-username", address="192.0.2.11", data_root="/mnt/train")
        first = ManagedUser(username="alice")
        second = ManagedUser(username="bob")
        session.add_all([host, first, second])
        session.flush()
        session.add_all([
            HostAccessGrant(host_id=host.id, managed_user_id=first.id, username="shared", data_directory="/mnt/train/shared"),
            HostAccessGrant(host_id=host.id, managed_user_id=second.id, username="shared", data_directory="/mnt/train/shared"),
        ])
        with pytest.raises(IntegrityError):
            session.commit()


def test_permission_template_keeps_its_access_defaults() -> None:
    with SessionLocal() as session:
        template = PermissionTemplate(name="Docker training", groups=["docker"], sudo_rule="ALL=(ALL) NOPASSWD: /usr/bin/nvidia-smi")
        session.add(template)
        session.flush()
        assert template.enabled is True
        assert template.groups == ["docker"]
