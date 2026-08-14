"""Add encrypted pi Agent model configuration."""

from alembic import op
import sqlalchemy as sa


revision = "007_agent_model_config"
down_revision = "006_adopt_existing_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_model_configs",
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=False),
        sa.Column("thinking_level", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("agent_model_configs")
