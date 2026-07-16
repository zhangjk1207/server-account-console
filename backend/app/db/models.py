from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def uuid_string() -> str:
    return str(uuid4())


class TimestampedRecord:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Host(TimestampedRecord, Base):
    __tablename__ = "hosts"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    address: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_user: Mapped[str] = mapped_column(String(64), default="root")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    data_root: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host_key_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="unconfirmed")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    last_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_probe_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_probe_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class HostCredential(TimestampedRecord, Base):
    __tablename__ = "host_credentials"
    __table_args__ = (UniqueConstraint("host_id", name="uq_host_credential_host"),)

    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), index=True)
    private_key_ciphertext: Mapped[str] = mapped_column(Text)
    sudo_password_ciphertext: Mapped[str] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ssh_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sudo_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ManagedUser(TimestampedRecord, Base):
    __tablename__ = "managed_users"

    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    primary_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    shell: Mapped[str] = mapped_column(String(255), default="/bin/bash")
    home: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sudo_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    directories: Mapped[list[dict]] = mapped_column(JSON, default=list)
    symlinks: Mapped[list[dict]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SshPublicKey(TimestampedRecord, Base):
    __tablename__ = "ssh_public_keys"

    managed_user_id: Mapped[str] = mapped_column(ForeignKey("managed_users.id", ondelete="CASCADE"), index=True)
    public_key: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(128), unique=True)
    comment: Mapped[str] = mapped_column(String(255), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class PermissionTemplate(TimestampedRecord, Base):
    __tablename__ = "permission_templates"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    groups: Mapped[list[str]] = mapped_column(JSON, default=list)
    sudo_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class HostAccessGrant(TimestampedRecord, Base):
    __tablename__ = "host_access_grants"
    __table_args__ = (
        UniqueConstraint("host_id", "managed_user_id", name="uq_host_access_grant"),
        Index("uq_active_host_access_username", "host_id", "username", unique=True, sqlite_where=text("state = 'active'")),
    )

    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), index=True)
    managed_user_id: Mapped[str] = mapped_column(ForeignKey("managed_users.id", ondelete="CASCADE"), index=True)
    username: Mapped[str] = mapped_column(String(32))
    permission_template_id: Mapped[str | None] = mapped_column(
        ForeignKey("permission_templates.id", ondelete="SET NULL"), nullable=True
    )
    template_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    groups_override: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    sudo_rule_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_directory: Mapped[str] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(32), default="active", index=True)
    last_success_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)


class ScriptTemplate(TimestampedRecord, Base):
    __tablename__ = "script_templates"

    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Job(TimestampedRecord, Base):
    __tablename__ = "jobs"

    kind: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32), index=True)
    user_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    request_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    script_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobTarget(TimestampedRecord, Base):
    __tablename__ = "job_targets"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id", ondelete="RESTRICT"), index=True)
    state: Mapped[str] = mapped_column(String(32), default="pending")
    output: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobEvent(TimestampedRecord, Base):
    __tablename__ = "job_events"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    host_id: Mapped[str | None] = mapped_column(ForeignKey("hosts.id", ondelete="SET NULL"), nullable=True)
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text)


class HostUserState(TimestampedRecord, Base):
    __tablename__ = "host_user_states"
    __table_args__ = (UniqueConstraint("host_id", "managed_user_id", name="uq_host_user_state"),)

    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), index=True)
    managed_user_id: Mapped[str] = mapped_column(ForeignKey("managed_users.id", ondelete="CASCADE"), index=True)
    last_success_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    desired_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
