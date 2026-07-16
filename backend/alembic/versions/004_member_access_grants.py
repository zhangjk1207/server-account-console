"""Add member-centric access grants and permission templates."""

from alembic import op
import sqlalchemy as sa


revision = "004_member_access_grants"
down_revision = "003_host_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("data_root", sa.String(length=255), nullable=True))
    op.create_table(
        "permission_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("groups", sa.JSON(), nullable=False),
        sa.Column("sudo_rule", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_permission_templates_name", "permission_templates", ["name"])
    op.create_table(
        "host_access_grants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("host_id", sa.String(length=36), sa.ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("managed_user_id", sa.String(length=36), sa.ForeignKey("managed_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("permission_template_id", sa.String(length=36), sa.ForeignKey("permission_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("template_snapshot", sa.JSON(), nullable=False),
        sa.Column("groups_override", sa.JSON(), nullable=True),
        sa.Column("sudo_rule_override", sa.Text(), nullable=True),
        sa.Column("data_directory", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("last_success_job_id", sa.String(length=36), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("host_id", "managed_user_id", name="uq_host_access_grant"),
    )
    op.create_index("ix_host_access_grants_host_id", "host_access_grants", ["host_id"])
    op.create_index("ix_host_access_grants_managed_user_id", "host_access_grants", ["managed_user_id"])
    op.create_index("ix_host_access_grants_state", "host_access_grants", ["state"])


def downgrade() -> None:
    op.drop_table("host_access_grants")
    op.drop_table("permission_templates")
    op.drop_column("hosts", "data_root")
