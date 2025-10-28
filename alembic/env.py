from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ─────────────────────────────────────────────────────────────
# Make project importable in both local and Azure App Service
# ─────────────────────────────────────────────────────────────
# 1) repo root at runtime (App Service sets cwd to /home/site/wwwroot)
sys.path.append(os.getcwd())
# 2) also add the parent of the alembic/ folder (repo root fallback)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ─────────────────────────────────────────────────────────────
# Alembic Config
# ─────────────────────────────────────────────────────────────
config = context.config

# Configure logging from alembic.ini if present
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ─────────────────────────────────────────────────────────────
# Import metadata (ensure Base + models are imported)
# ─────────────────────────────────────────────────────────────
from src.db.base import Base  # noqa: E402
from src.db import models     # noqa: F401  # register tables

target_metadata = Base.metadata

# ─────────────────────────────────────────────────────────────
# Resolve database URL
# ─────────────────────────────────────────────────────────────
DB_URL_ENV = os.getenv("DATABASE_URL")

def _resolve_url() -> str:
    """
    Prefer DATABASE_URL (prod/Azure). If missing, fall back to local SQLite
    to keep developer experience smooth.
    """
    if DB_URL_ENV:
        return DB_URL_ENV
    # Local dev fallback
    return "sqlite:///./dev.db"

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode'."""
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode'."""
    url = _resolve_url()
    # Inject sqlalchemy.url at runtime (don’t hardcode in .ini)
    config.set_main_option("sqlalchemy.url", url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
