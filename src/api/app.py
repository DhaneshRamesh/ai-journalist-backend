import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load .env locally; harmless on Azure
load_dotenv()

API_PREFIX = os.getenv("API_PREFIX", "/api")  # e.g., "/api"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")

app = FastAPI(title="AI Journalist API (Azure-ready)")

# --- CORS: keep browsers happy (no credentials with "*") ---
def _parse_origins(raw: str):
    if not raw or raw.strip() == "*":
        return ["*"], False  # cannot combine "*" with allow_credentials=True
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["*"], True

_allow_origins, _allow_credentials = _parse_origins(ALLOWED_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Optional safety net: create tables on startup until Alembic is fully wired ---
# Uses DATABASE_URL directly to avoid import timing issues in Azure.
try:
    from sqlalchemy import create_engine, text
    from src.db.models import Base  # your models define Base
    _db_url = os.environ.get("DATABASE_URL")
    if _db_url:
        _bootstrap_engine = create_engine(_db_url, pool_pre_ping=True)

        @app.on_event("startup")
        def ensure_tables():
            try:
                with _bootstrap_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                Base.metadata.create_all(bind=_bootstrap_engine)
            except Exception as e:
                print(f"[startup] ensure_tables skipped: {e}")
    else:
        print("[startup] DATABASE_URL not set; skipping ensure_tables")
except Exception as e:
    print(f"[startup] DB bootstrap unavailable: {e}")

# --- Mount API routes (router itself has NO prefix) ---
from src.api.routes import router as api_router  # noqa: E402
app.include_router(api_router, prefix=API_PREFIX)

@app.get("/")
def root():
    return {"message": f"See API at {API_PREFIX}/health"}
