from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from src.db.models import get_engine, get_session, Article, Mention

router = APIRouter()

class MentionOut(BaseModel):
    id: int
    article_id: int
    title: Optional[str]
    summary: Optional[str]
    sentiment: Optional[str]
    risk_score: Optional[int]
    source: Optional[str]
    url: Optional[str]

@router.get("/health")
def health():
    return {"status": "ok"}

@router.get("/mentions", response_model=List[MentionOut])
def get_mentions(limit: int = 50):
    session = get_session()
    q = session.query(Mention).order_by(Mention.created_at.desc()).limit(limit).all()
    results = []
    for m in q:
        a = m.article
        results.append({
            "id": m.id,
            "article_id": m.article_id,
            "title": a.title if a else None,
            "summary": m.summary,
            "sentiment": m.sentiment,
            "risk_score": m.risk_score,
            "source": a.source if a else None,
            "url": a.link if a else None
        })
    session.close()
    return results
