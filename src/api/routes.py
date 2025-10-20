from typing import List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload  # ← ADDED joinedload
from pydantic import BaseModel, Field

from src.api.schemas import (
    ArticleOut,
    MentionOut,
    SummarizeIn,
    SummarizeOut,
    MatchOut,
    IngestIn,  # ← NOW IMPORTED FROM schemas.py
    IngestOut,  # ← NEW: For ingest response
)
from src.db import models
from src.db.session import get_db
from src.processing.summarizer import summarize_text
from src.processing.matching import rank_journalists
from src.processing.ingest import run_ingest

# IMPORTANT: no prefix here; app.py provides /api via include_router(..., prefix=API_PREFIX)
router = APIRouter()

# ─────────────────────────────
# Health & readiness (UNCHANGED)
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
# Data APIs - FIXED FOR NESTED ARTICLES
# ─────────────────────────────

@router.get("/articles", response_model=List[ArticleOut], tags=["data"])
def list_articles(
    limit: int = Query(50, ge=1, le=200),  # ← Added Query validation
    source: Optional[str] = Query(None),   # ← Added source filter
    db: Session = Depends(get_db)
):
    q = db.query(models.Article)
    
    if source:
        q = q.filter(models.Article.source.ilike(f"%{source}%"))
    
    return (
        q.order_by(models.Article.published.desc().nullslast())
         .limit(limit)
         .all()
    )

@router.get("/mentions", response_model=List[MentionOut], tags=["data"])
def list_mentions(
    limit: int = Query(50, ge=1, le=200),   # ← Added Query validation
    source: Optional[str] = Query(None),    # ← Added source filter
    db: Session = Depends(get_db)
):
    """List recent mentions WITH NESTED ARTICLES"""
    q = (
        db.query(models.Mention)
        .options(joinedload(models.Mention.article))  # ← KEY FIX: EAGER LOAD ARTICLE
    )
    
    if source:
        # Filter by article source (requires join)
        q = q.join(models.Mention.article).filter(
            models.Article.source.ilike(f"%{source}%")
        )
    
    return (
        q.order_by(models.Mention.created_at.desc())
         .limit(limit)
         .all()
    )

# ─────────────────────────────
# Processing / utilities (UNCHANGED)
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
# Ingestion - UPDATED TO USE schemas.py + IngestOut
# ─────────────────────────────

def _since_from_backfill(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)

def _check_admin(x_admin_token: Optional[str]) -> None:
    import os
    admin_token = os.environ.get("ADMIN_TOKEN")
    if admin_token and (not x_admin_token or x_admin_token != admin_token):
        raise HTTPException(status_code=401, detail="Unauthorized")

@router.post("/ingest", response_model=IngestOut, tags=["ops"])  # ← FIXED: IngestOut response
def ingest(
    payload: IngestIn,  # ← NOW FROM schemas.py
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    """
    Kick off a synchronous demo-safe ingest.
    Body:
      { "source": "demo", "limit": 1, "backfill_days": 2, "dry_run": false }
    """
    _check_admin(x_admin_token)
    
    # Convert backfill_days -> since_utc (your ingest.py expects since_utc)
    since_utc = payload.since_utc
    if payload.backfill_days > 0 and not since_utc:
        since_utc = _since_from_backfill(payload.backfill_days)
    
    # Default source="google" if None
    source = payload.source or "google"
    
    try:
        result = run_ingest(
            db=db,
            source=source,
            limit=payload.limit,
            since_utc=since_utc or datetime.now(timezone.utc) - timedelta(hours=24),
            keywords=payload.keywords,
            per_keyword_limit=payload.per_keyword_limit,
            dry_run=payload.dry_run,
        )
        return IngestOut(**result)  # ← WRAP IN IngestOut
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ops/ingest", response_model=IngestOut, tags=["ops"])  # ← FIXED response
def ingest_alias(
    payload: IngestIn,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    """Alias to support older frontend path /api/ops/ingest."""
    return ingest(payload, db, x_admin_token)