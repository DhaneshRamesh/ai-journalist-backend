"""add flagged fields to mentions + index

Revision ID: 0003_add_flag_fields_to_mentions
Revises: 0002_add_source_to_articles
Create Date: 2025-10-28
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_add_flag_fields_to_mentions"
down_revision = "0002_add_source_to_articles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mentions", sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mentions", sa.Column("flag_reason", sa.String(length=128), nullable=True))
    op.add_column("mentions", sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_mentions_flagged_created", "mentions", ["flagged", "created_at"])
    op.alter_column("mentions", "flagged", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_mentions_flagged_created", table_name="mentions")
    op.drop_column("mentions", "flagged_at")
    op.drop_column("mentions", "flag_reason")
    op.drop_column("mentions", "flagged")
