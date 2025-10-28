from typing import List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import text, func
from sqlalchemy.orm import Session, joinedload
from src.api.schemas import (
    ArticleOut,
    MentionOut,
    SummarizeIn,
    SummarizeOut,
    MatchOut,
    IngestIn,
    IngestOut,
)
from src.db import models
    # models.Article, models.Mention, models.Journalist
from src.db.session import get_db
from src.processing.summarizer import summarize_text
from src.processing.matching import rank_journalists
from src.processing.ingest import run_ingest, run_recent_ingest
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

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
def list_articles(
    limit: int = Query(50, ge=1, le=200),
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
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
    limit: int = Query(50, ge=1, le=200),
    source: Optional[str] = Query(None),
    sentiment: Optional[str] = Query(None),
    flagged: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """List recent mentions with nested articles, supporting sentiment and flagged filters."""
    q = db.query(models.Mention).options(joinedload(models.Mention.article))

    if source:
        q = q.join(models.Mention.article).filter(models.Article.source.ilike(f"%{source}%"))
    if sentiment:
        q = q.filter(models.Mention.sentiment == sentiment.lower())

    # Defensive guard: avoid 500s if DB not yet migrated
    if flagged is not None:
        try:
            _ = models.Mention.flagged
            q = q.filter(models.Mention.flagged == flagged)
        except AttributeError:
            logger.warning("Mention.flagged not available yet; ignoring 'flagged' filter")

    return (
        q.order_by(models.Mention.created_at.desc())
         .limit(limit)
         .all()
    )

# ─────────────────────────────
# Processing / utilities
# ─────────────────────────────
@router.post("/summarize", response_model=SummarizeOut, tags=["nlp"])
def summarize(payload: SummarizeIn):
    """Generate a summary in 2-3 bullet points using GPT-4o-mini."""
    try:
        summary = summarize_text(payload.text)
        return {"summary": summary}
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        raise HTTPException(status_code=500, detail="Summarization failed")

# ─────────────────────────────
# Matching
# ─────────────────────────────
@router.get("/match", response_model=List[MatchOut], tags=["nlp"])
def match_from_db(
    text: str = Query(..., description="Text to match journalists against"),
    top_k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Match journalists from database against input text.
    GET /api/match?text=AI%20startups&top_k=3
    """
    journalists = db.query(models.Journalist).all()
    if not journalists:
        logger.warning("No journalists found in database")
        return []

    candidates = [
        {
            "id": j.id,
            "name": j.name,
            "outlet": getattr(j, "outlet", ""),
            "topics": getattr(j, "topics", ""),
        }
        for j in journalists
    ]
    logger.info(f"Matching '{text}' against {len(candidates)} journalists")
    matches = rank_journalists(text, candidates, top_k=top_k)
    return matches

# ─────────────────────────────
# Ingestion — preserve legacy + add params endpoint
# ─────────────────────────────
def _since_from_backfill(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)

def _check_admin(x_admin_token: Optional[str] = None) -> None:
    import os
    expected = os.environ.get("ADMIN_API_TOKEN") or os.environ.get("ADMIN_TOKEN")
    if expected and (not x_admin_token or x_admin_token != expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

# NEW: params-based ingestion lives at /ingest/params (avoid path conflict)
@router.post("/ingest/params", response_model=dict, tags=["ops"])
def ingest_query_params(
    keywords: Optional[List[str]] = Query(None, description="Search keywords"),
    per_keyword_limit: int = Query(5, ge=1, le=20),
    limit: int = Query(50, ge=1, le=200),
    hours_back: int = Query(24, ge=1, le=168),
    dry_run: bool = Query(False),
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    """
    Dynamic ingestion via query params.

    POST /api/ingest/params?keywords=India&per_keyword_limit=5&limit=50
    """
    _check_admin(x_admin_token)

    if not keywords:
        keywords = ["AI", "journalism"]
        logger.warning("No keywords provided, using defaults")

    logger.info(
        f"Param ingest: keywords={keywords}, per_kw={per_keyword_limit}, "
        f"limit={limit}, hours_back={hours_back}, dry_run={dry_run}"
    )

    result = run_recent_ingest(
        db=db,
        limit=limit,
        keywords=keywords,
        per_keyword_limit=per_keyword_limit,
        hours_back=hours_back,
        dry_run=dry_run,
    )

    if result.get("status") == "ok":
        stats = result.get("stats", {})
        return {
            "status": "success",
            "message": f"Fetched articles for {len(keywords)} keywords",
            "inserted": stats.get("articles_inserted", 0),
            "total_fetched": stats.get("fetched", 0),
            "mentions_created": stats.get("mentions_inserted", 0),
            "keywords_searched": keywords,
            "per_keyword_limit": per_keyword_limit,
            "total_articles": result.get("counts_after", {}).get("articles", 0),
            "total_mentions": result.get("counts_after", {}).get("mentions", 0),
            "full_stats": result,
        }
    else:
        logger.error(f"Param ingest failed: {result}")
        raise HTTPException(status_code=400, detail=result.get("message", "Ingestion failed"))

# LEGACY: JSON body endpoint remains at /ingest
@router.post("/ingest", response_model=IngestOut, tags=["ops"])
def ingest_json_body(
    payload: IngestIn,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    """
    Legacy ingestion via JSON body.

    POST /api/ingest
    Body: { "source": "google", "limit": 10, "backfill_days": 2, "dry_run": false }
    """
    _check_admin(x_admin_token)

    since_utc = payload.since_utc
    if payload.backfill_days > 0 and not since_utc:
        since_utc = _since_from_backfill(payload.backfill_days)

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
        return IngestOut(**result)
    except Exception as e:
        logger.error(f"JSON body ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# LEGACY alias keeps working
@router.post("/ops/ingest", response_model=IngestOut, tags=["ops"])
def ingest_alias(
    payload: IngestIn,
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    """Alias for older frontend path /api/ops/ingest."""
    return ingest_json_body(payload, db, x_admin_token)

# ─────────────────────────────
# Stats endpoint
# ─────────────────────────────
@router.get("/stats", tags=["data"])
def get_stats(db: Session = Depends(get_db)):
    """Dashboard statistics"""
    try:
        sentiment_stats = db.query(
            models.Mention.sentiment,
            func.count(models.Mention.id),
        ).group_by(models.Mention.sentiment).all()

        return {
            "total_articles": db.query(func.count(models.Article.id)).scalar() or 0,
            "total_mentions": db.query(func.count(models.Mention.id)).scalar() or 0,
            "sentiment_distribution": dict(sentiment_stats),
            "recent_mentions": db.query(func.count(models.Mention.id)).filter(
                models.Mention.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
            ).scalar() or 0,
        }
    except Exception as e:
        logger.error(f"Stats failed: {e}")
        raise HTTPException(status_code=500, detail="Stats failed")

# ─────────────────────────────
# Flag endpoint
# ─────────────────────────────
@router.post("/flag", tags=["ops"])
def flag_article(
    article_id: int = Query(..., description="Article ID to flag"),
    reason: str = Query("urgent", description="Flag reason"),
    db: Session = Depends(get_db),
    x_admin_token: Optional[str] = Header(default=None),
):
    """
    Flag an article for manual review.
    POST /api/flag?article_id=19&reason=urgent
    """
    _check_admin(x_admin_token)

    mention = db.query(models.Mention).filter(models.Mention.article_id == article_id).first()
    if not mention:
        raise HTTPException(status_code=404, detail="Article not found")

    mention.flagged = True
    mention.flag_reason = reason
    mention.flagged_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(f"Flagged article {article_id}: {reason}")
    return {"status": "flagged", "article_id": article_id, "reason": reason}
