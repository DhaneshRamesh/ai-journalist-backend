import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

# Make 'src' importable when running Alembic
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load .env so DATABASE_URL is available
load_dotenv()

# Alembic Config object
config = context.config

# Configure logging from alembic.ini if present
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models' metadata
from src.db.base import Base  # noqa: E402
target_metadata = Base.metadata

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in 'online' mode."""
    # Ensure SQLAlchemy URL is set from env (ignore %(DATABASE_URL)s in alembic.ini)
    config.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", "sqlite:///./dev.db"))

    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
