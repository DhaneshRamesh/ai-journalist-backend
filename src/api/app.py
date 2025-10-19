import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

API_PREFIX = os.getenv("API_PREFIX", "/api")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")

app = FastAPI(title="AI Journalist API (Azure-ready)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS.split(",")] if ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.api.routes import router as api_router  # noqa: E402
app.include_router(api_router, prefix=API_PREFIX)

@app.get("/")
def root():
    return {"message": f"See API at {API_PREFIX}/health"}
