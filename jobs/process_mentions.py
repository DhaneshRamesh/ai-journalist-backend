"""Compute summary/sentiment/risk for recent Articles and write Mentions.
Run as a scheduled job, not inside the web container.
"""
from datetime import datetime
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.session import SessionLocal
from src.db import models
from src.processing.summarizer import summarize_text
from src.processing.sentiment import classify
from src.processing.risk_detector import risk_score

BATCH_SIZE = 50

def process_recent():
    db = SessionLocal()
    try:
        q = db.query(models.Article).order_by(models.Article.fetched_at.desc()).limit(BATCH_SIZE).all()
        for art in q:
            summary = summarize_text(art.title or "")
            sentiment = classify(art.title or "")
            risk = risk_score(art.title or "")
            m = models.Mention(article_id=art.id, summary=summary, sentiment=sentiment, risk_score=risk)
            db.add(m)
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    process_recent()
