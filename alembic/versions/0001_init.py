from alembic import op
import sqlalchemy as sa

revision = '0001_init'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('articles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(length=512)),
        sa.Column('link', sa.String(length=2048), unique=True),
        sa.Column('source', sa.String(length=128)),
        sa.Column('published', sa.DateTime(timezone=True)),
        sa.Column('fetched_at', sa.DateTime(timezone=True)),
        sa.Column('raw_text', sa.Text()),
    )
    op.create_table('mentions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('article_id', sa.Integer(), sa.ForeignKey('articles.id', ondelete='CASCADE')),
        sa.Column('summary', sa.Text()),
        sa.Column('sentiment', sa.String(length=16)),
        sa.Column('risk_score', sa.Integer()),
        sa.Column('named_entities', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )
    op.create_table('journalists',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=256)),
        sa.Column('outlet', sa.String(length=256)),
        sa.Column('email', sa.String(length=256)),
        sa.Column('twitter', sa.String(length=128)),
        sa.Column('topics', sa.Text()),
    )

def downgrade():
    op.drop_table('journalists')
    op.drop_table('mentions')
    op.drop_table('articles')
