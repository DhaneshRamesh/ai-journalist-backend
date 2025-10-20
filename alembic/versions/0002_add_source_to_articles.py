"""add source column to articles with backfill and index

Revision ID: 0002_add_source_to_articles
Revises: 0001_init
Create Date: 2025-10-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "0002_add_source_to_articles"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade():
    # 1️⃣ Add the column as nullable so existing rows pass
    with op.batch_alter_table("articles") as batch_op:
        batch_op.add_column(sa.Column("source", sa.String(length=128), nullable=True))

    # 2️⃣ Backfill from link domain (drop www.)
    op.execute(text("""
        UPDATE articles 
        SET source = COALESCE(
            NULLIF(REGEXP_REPLACE(SPLIT_PART(link, '/', 3), '^www\\.', '', 'g'), ''),
            'unknown'
        )
        WHERE source IS NULL AND link IS NOT NULL
    """))

    # 3️⃣ Create indexes
    op.create_index("ix_articles_source", "articles", ["source"], unique=False)
    op.create_index("ix_articles_published_source", "articles", ["published", "source"])

    # 4️⃣ Enforce NOT NULL now that data is populated
    with op.batch_alter_table("articles") as batch_op:
        batch_op.alter_column("source", existing_type=sa.String(length=128), nullable=False)


def downgrade():
    # Safe rollback
    op.drop_index("ix_articles_published_source", table_name="articles")
    op.drop_index("ix_articles_source", table_name="articles")
    with op.batch_alter_table("articles") as batch_op:
        batch_op.drop_column("source")
