"""Prevent active Linux username collisions on a machine."""

from alembic import op
import sqlalchemy as sa


revision = "005_active_grant_username"
down_revision = "004_member_access_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_active_host_access_username",
        "host_access_grants",
        ["host_id", "username"],
        unique=True,
        sqlite_where=sa.text("state = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_host_access_username", table_name="host_access_grants")
