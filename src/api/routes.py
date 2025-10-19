# src/api/routes.py
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.schemas import ArticleOut, MentionOut, SummarizeIn, SummarizeOut, MatchOut
from src.db import models
from src.db.session import get_db
from src.processing.summarizer import summarize_text
from src.processing.sentiment import classify  # (kept in case you use later)
from src.processing.risk_detector import risk_score  # (kept in case you use later)
from src.processing.matching import rank_journalists

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