# src/api/routes.py
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.api.schemas import ArticleOut, MentionOut, SummarizeIn, SummarizeOut, MatchOut
from src.db import models
from src.db.session import get_db
from src.processing.summarizer import summarize_text
from src.processing.sentiment import classify  # kept if you hook this into ingest later
from src.processing.risk_detector import risk_score  # kept if you hook this into ingest later
from src.processing.matching import rank_journalists
from src.processing.ingest import run_ingest  # NEW

router = APIRouter()

# ─────────────────────────────
# Health & readiness
# ─────────────────────────────

@router.get("/health", tags=["ops"])
def health():
    """
    Liveness: returns OK without touching external deps.
    Useful for Azure/App Service health checks.
    """
    return {"status": "ok"}

@router.get("/ready", tags=["ops"])
def ready(db: Session = Depends(get_db)):
    """
    Readiness: verify DB connectivity.
    Returns 500 with error detail if DB isn't reachable/authenticated.
    """
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
    q = (
        db.query(models.Article)
        .order_by(models.Article.published.desc().nullslast())
        .limit(limit)
    )
    return q.all()

@router.get("/mentions", response_model=List[MentionOut], tags=["data"])
def list_mentions(limit: int = 50, db: Session = Depends(get_db)):
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
    limit: int = 10
    backfill_days: int = 2
    dry_run: bool = False

def _ingest_handler(db: Session, payload: IngestIn):
    since = datetime.utcnow() - timedelta(days=payload.backfill_days)
    return run_ingest(
        db=db,
        source=payload.source,
        limit=payload.limit,
        since_utc=since,
        dry_run=payload.dry_run,
    )

@router.post("/ingest", tags=["ops"])
def ingest(payload: IngestIn, db: Session = Depends(get_db)):
    """
    Kick off a synchronous ingest (demo-safe). Frontend button can call this.
    Body (JSON):
      { "source": "rss|demo|...", "limit": 10, "backfill_days": 2, "dry_run": false }
    """
    try:
        return _ingest_handler(db, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ops/ingest", tags=["ops"])
def ingest_alias(payload: IngestIn, db: Session = Depends(get_db)):
    """
    Alias of /ingest to match earlier frontend wiring (/api/ops/ingest).
    """
    try:
        return _ingest_handler(db, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
