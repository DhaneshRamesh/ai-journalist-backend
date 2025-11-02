# src/db/session.py
import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("src.db.session")

# --- Global Engine ---
_engine = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False)

def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set in environment.")
    # Sanitized log
    safe_url = "postgresql+psycopg2://<hidden>:***@" + url.split("@", 1)[1] if "@" in url else url
    logger.info(f"Using DATABASE_URL (sanitized): {safe_url}")
    return url

def get_engine():
    global _engine
    if _engine is None:
        url = get_database_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            connect_args=connect_args,
            future=True,
        )
        # Test connection
        try:
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection established successfully.")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    return _engine

def get_db():
    db = SessionLocal(bind=get_engine())
    try:
        yield db
    finally:
        db.close()
