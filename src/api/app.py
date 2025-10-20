import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Optional: remove in Azure (App Service already uses App Settings),
# but harmless locally.
load_dotenv()

API_PREFIX = os.getenv("API_PREFIX", "/api")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")

app = FastAPI(title="AI Journalist API (Azure-ready)")

# --- CORS: make "*" work without credentials, otherwise honor your list ---
def _parse_origins(raw: str):
    if not raw or raw.strip() == "*":
        return ["*"], False  # cannot combine "*" with allow_credentials=True
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["*"], True  # credentials allowed for explicit origins

_allow_origins, _allow_credentials = _parse_origins(ALLOWED_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Optional safety net: create tables on startup until Alembic is ready ---
try:
    from sqlalchemy import text
    from src.db.session import engine
    from src.db.models import Base

    @app.on_event("startup")
    def ensure_tables():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=engine)
        except Exception as e:
            # Log but don’t crash app
            print(f"[startup] ensure_tables skipped: {e}")
except Exception as e:
    # If DB layer isn’t importable at build, skip the fallback
    print(f"[startup] DB bootstrap unavailable: {e}")

# --- Mount API routes (router itself should have NO prefix) ---
from src.api.routes import router as api_router  # noqa: E402

app.include_router(api_router, prefix=API_PREFIX)

@app.get("/")
def root():
    return {"message": f"See API at {API_PREFIX}/health"}
