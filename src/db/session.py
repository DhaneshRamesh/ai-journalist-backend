import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("src.db.session")

# --- Load DB URL at runtime, not import-time ---
def get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
    safe_url = url.replace(url.split('@')[0], "postgresql+psycopg://<hidden>:***") if "@" in url else url
    logger.info(f"🔗 Using DATABASE_URL (sanitized): {safe_url}")
    return url

def get_engine(url: str = None):
    if url is None:
        url = get_database_url()

    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args=connect_args,
        future=True,
    )
    return engine

_engine = get_engine()
SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
