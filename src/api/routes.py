from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from src.api.schemas import ArticleOut, MentionOut, SummarizeIn, SummarizeOut, MatchOut
from src.db import models
from src.db.session import get_db
from src.processing.summarizer import summarize_text
from src.processing.sentiment import classify
from src.processing.risk_detector import risk_score
from src.processing.matching import rank_journalists
from sqlalchemy import text

router = APIRouter()

@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/articles", response_model=List[ArticleOut])
def list_articles(limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(models.Article).order_by(models.Article.published.desc().nullslast()).limit(limit)
    return q.all()

@router.get("/mentions", response_model=List[MentionOut])
def list_mentions(limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(models.Mention).order_by(models.Mention.created_at.desc()).limit(limit)
    return q.all()

@router.post("/summarize", response_model=SummarizeOut)
def summarize(payload: SummarizeIn):
    return {"summary": summarize_text(payload.text)}

@router.get("/match", response_model=List[MatchOut])
def match_demo(text: str):
    candidates = [
        {"id": 1, "name": "Alex Smith", "outlet": "TechNews", "topics": "AI, startups, VC"},
        {"id": 2, "name": "Priya Rao", "outlet": "FinDaily", "topics": "fintech, banking, regulation"},
        {"id": 3, "name": "Liam Chen", "outlet": "Aussie Times", "topics": "Australia, policy, tech"},
    ]
    return rank_journalists(text, candidates, top_k=5)
