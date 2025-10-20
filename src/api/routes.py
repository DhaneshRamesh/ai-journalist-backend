from typing import List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from src.api.schemas import ArticleOut, MentionOut, SummarizeIn, SummarizeOut, MatchOut
from src.db import models
from src.db.session import get_db
from src.processing.summarizer import summarize_text
from src.processing.sentiment import classify  # keep if you’ll use later
from src.processing.risk_detector import risk_score  # keep if you’ll use later
from src.processing.matching import rank_journalists
from src.processing.ingest import run_ingest

# Make your routes live under /api to match the frontend
router = APIRouter(prefix="/api")

# ─────────────────────────────
# Health & readiness
# ─────────────────────────────

@router.get("/health", tags=["ops"])
def health():
    """Liveness: returns OK without external deps."""
    return {"status": "ok"}

@router.get("/ready", tags=["ops"])
def ready(db: Session = Depends(get_db)):
    """Readiness: verify DB connectivity."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────
# Data APIs
# ─────────────────────────────

@router.get("/articles", response_model=List[ArticleOut], tags=["data"])
def list_articles(limit: int = 50, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    q = (
        db.query(models.Article)
        .order_by(models.Article.published.desc().nullslast())
        .limit(limit)
    )
    return q.all()

@router.get("/mentions", response_model=List[MentionOut], tags=["data"])
def list_mentions(limit: int = 50, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    q = (
        db.query(models.Mention)
        .order_by(models.Mention.created_at.desc())
        .limit(limit)
    )
    return q.all()

# ─────────────────────────────
# Processing / utilities
# ─────────────────────────────

@router.post("/summarize", response_model=SummarizeOut, tags=["nlp"])
def summarize(payload: SummarizeIn):
    return {"summary": summarize_text(payload.text)}

@router.get("/match", response_model=List[MatchOut], tags=["nlp"])
def match_demo(text: str):
    candidates = [
        {"id": 1, "name": "Alex Smith", "outlet": "TechNews", "topics": "AI, startups, VC"},
        {"id": 2, "name": "Priya Rao", "outlet": "FinDaily", "topics": "fintech, banking, regulation"},
        {"id": 3, "name": "Liam Chen", "outlet": "Aussie Times", "topics": "Australia, policy, tech"},
    ]
    return rank_journalists(text, candidates, top_k=5)

# ─────────────────────────────
# Ingestion
# ─────────────────────────────

class IngestIn(BaseModel):
    source: Optional[str] = None
    limit: int = Field(10, ge=1, le=100)
    backfill_days: int = Field(2, ge=0, le=30)
    dry_run: bool = False

def _since_from_backfill(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)

def _ingest_handler(db: Session, payload: IngestIn):
    since = _since_from_backfill(payload.backfill_days)
    return run_ingest(
        db=db,
        source=payload.source,
        limit=payload.limit,
        since_utc=since,
        dry_run=payload.dry_run,
    )

def _check_admin(x_admin_token: Optional[str]) -> None:
    import os
    admin_token = os.environ.get("ADMIN_TOKEN")
    if admin_token:
        if not x_admin_token or x_admin_token != admin_token:
            raise HTTPException(status_code=401, detail="Unauthorized")

@router.post("/ingest", tags=["ops"])
def ingest(
    payload: IngestIn,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    """
    Kick off a synchronous demo-safe ingest.
    Body:
      { "source": "rss|demo|...", "limit": 10, "backfill_days": 2, "dry_run": false }
    """
    _check_admin(x_admin_token)
    try:
        return _ingest_handler(db, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ops/ingest", tags=["ops"])
def ingest_alias(
    payload: IngestIn,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    """
    Alias of /api/ingest to match earlier frontend wiring (/api/ops/ingest).
    """
    _check_admin(x_admin_token)
    try:
        return _ingest_handler(db, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
