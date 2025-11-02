import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# --- Logging setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("src.db.session")

# --- Globals ---
_engine = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False)


def get_database_url() -> str:
    """Safely read DATABASE_URL from environment and log a sanitized version."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("❌ DATABASE_URL is not set in environment.")

    # Sanitize for logs
    if "@" in url:
        safe_url = "postgresql+psycopg2://<hidden>:***@" + url.split("@", 1)[1]
    else:
        safe_url = url

    logger.info(f"🔗 Using DATABASE_URL (sanitized): {safe_url}")
    return url


def get_engine():
    """Lazily create the SQLAlchemy engine only once."""
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

        # --- Optional: Quick connectivity test ---
        try:
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.info("✅ Database connection established successfully.")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")

    return _engine


def get_db():
    """Provide a SQLAlchemy session for FastAPI routes."""
    db = SessionLocal(bind=get_engine())
    try:
        yield db
    finally:
        db.close()
