# env.py
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context

# ----------------------------------------------------------------------
# Make the project importable both locally and in Azure App Service
# ----------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# ----------------------------------------------------------------------
# Alembic Config & Logging
# ----------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ----------------------------------------------------------------------
# Import models and metadata
# ----------------------------------------------------------------------
# pylint: disable=wrong-import-position
from src.db.base import Base  # noqa: E402
from src.db import models    # noqa: F401, E402

target_metadata = Base.metadata

# ----------------------------------------------------------------------
# Resolve DATABASE_URL
# ----------------------------------------------------------------------
def _resolve_url() -> str:
    """
    Return the database URL.

    1. Explicit env-var `DATABASE_URL` (Azure, Docker, CI, etc.)
    2. Fallback to a local SQLite file for quick dev iterations.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    return "sqlite:///./dev.db"


# ----------------------------------------------------------------------
# Offline migrations
# ----------------------------------------------------------------------
def run_migrations_offline() -> None:
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


# ----------------------------------------------------------------------
# Online migrations
# ----------------------------------------------------------------------
def run_migrations_online() -> None:
    url = _resolve_url()

    # Azure PostgreSQL/MySQL connections benefit from a real pool,
    # but keep NullPool for Alembic to avoid connection-leak issues.
    connect_args: dict = {}
    if url.startswith("postgresql"):
        # Azure PostgreSQL requires SSL by default
        connect_args["sslmode"] = os.getenv("DB_SSLMODE", "require")

    engine = create_engine(
        url,
        poolclass=pool.NullPool,
        future=True,
        connect_args=connect_args,
    )

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
