"""Add metadata for adopting existing Linux accounts."""

from alembic import op
import sqlalchemy as sa


revision = "006_adopt_existing_accounts"
down_revision = "005_active_grant_username"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("host_access_grants") as batch:
        batch.add_column(sa.Column("account_origin", sa.String(length=16), nullable=False, server_default="created"))
        batch.add_column(sa.Column("remote_uid", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("remote_primary_group", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("remote_home", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("managed_public_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch.add_column(sa.Column("managed_key_fingerprints", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch.alter_column("data_directory", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("host_access_grants") as batch:
        batch.alter_column("data_directory", existing_type=sa.String(length=255), nullable=False)
        batch.drop_column("managed_key_fingerprints")
        batch.drop_column("managed_public_keys")
        batch.drop_column("remote_home")
        batch.drop_column("remote_primary_group")
        batch.drop_column("remote_uid")
        batch.drop_column("account_origin")
