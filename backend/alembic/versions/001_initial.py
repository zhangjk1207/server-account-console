"""Create the initial desired-state and job tables."""

from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "hosts",
        *timestamp_columns(),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("ssh_user", sa.String(length=64), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("host_key_fingerprint", sa.String(length=128)),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("last_probe_at", sa.DateTime(timezone=True)),
        sa.Column("last_probe_latency_ms", sa.Integer()),
        sa.Column("last_probe_error", sa.Text()),
    )
    op.create_index("ix_hosts_name", "hosts", ["name"])
    op.create_table(
        "managed_users",
        *timestamp_columns(),
        sa.Column("username", sa.String(length=32), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("primary_group", sa.String(length=64)),
        sa.Column("groups", sa.JSON(), nullable=False),
        sa.Column("shell", sa.String(length=255), nullable=False),
        sa.Column("home", sa.String(length=255)),
        sa.Column("sudo_rule", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_managed_users_username", "managed_users", ["username"])
    op.create_table(
        "ssh_public_keys",
        *timestamp_columns(),
        sa.Column("managed_user_id", sa.String(length=36), sa.ForeignKey("managed_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False, unique=True),
        sa.Column("comment", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_ssh_public_keys_managed_user_id", "ssh_public_keys", ["managed_user_id"])
    op.create_table(
        "script_templates",
        *timestamp_columns(),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "jobs",
        *timestamp_columns(),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("user_snapshot", sa.JSON(), nullable=False),
        sa.Column("request_snapshot", sa.JSON(), nullable=False),
        sa.Column("script_snapshot", sa.JSON()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_jobs_state", "jobs", ["state"])
    op.create_table(
        "job_targets",
        *timestamp_columns(),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("host_id", sa.String(length=36), sa.ForeignKey("hosts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_job_targets_job_id", "job_targets", ["job_id"])
    op.create_index("ix_job_targets_host_id", "job_targets", ["host_id"])
    op.create_table(
        "job_events",
        *timestamp_columns(),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("host_id", sa.String(length=36), sa.ForeignKey("hosts.id", ondelete="SET NULL")),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])
    op.create_table(
        "host_user_states",
        *timestamp_columns(),
        sa.Column("host_id", sa.String(length=36), sa.ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("managed_user_id", sa.String(length=36), sa.ForeignKey("managed_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("last_success_job_id", sa.String(length=36), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("desired_hash", sa.String(length=64)),
        sa.UniqueConstraint("host_id", "managed_user_id", name="uq_host_user_state"),
    )
    op.create_index("ix_host_user_states_host_id", "host_user_states", ["host_id"])
    op.create_index("ix_host_user_states_managed_user_id", "host_user_states", ["managed_user_id"])


def downgrade() -> None:
    for table in ["host_user_states", "job_events", "job_targets", "jobs", "script_templates", "ssh_public_keys", "managed_users", "hosts"]:
        op.drop_table(table)
