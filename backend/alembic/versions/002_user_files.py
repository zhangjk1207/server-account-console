"""Add declarative directory and symlink state to managed users."""

from alembic import op
import sqlalchemy as sa


revision = "002_user_files"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("managed_users") as batch:
        batch.add_column(sa.Column("directories", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch.add_column(sa.Column("symlinks", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
    with op.batch_alter_table("managed_users") as batch:
        batch.drop_column("symlinks")
        batch.drop_column("directories")
