"""Add encrypted per-host SSH and sudo credentials."""

from alembic import op
import sqlalchemy as sa


revision = "003_host_credentials"
down_revision = "002_user_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "host_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("host_id", sa.String(length=36), sa.ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("private_key_ciphertext", sa.Text(), nullable=False),
        sa.Column("sudo_password_ciphertext", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("ssh_verified", sa.Boolean()),
        sa.Column("sudo_verified", sa.Boolean()),
        sa.Column("last_error", sa.Text()),
        sa.UniqueConstraint("host_id", name="uq_host_credential_host"),
    )
    op.create_index("ix_host_credentials_host_id", "host_credentials", ["host_id"])


def downgrade() -> None:
    op.drop_table("host_credentials")
