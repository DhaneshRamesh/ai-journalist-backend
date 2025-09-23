#!/usr/bin/env python3
"""
Process articles -> create mentions with summary, sentiment (VADER), risk.
Usage:
    PYTHONPATH=. python3 scripts/process_mentions.py
"""

import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

# DB models
from src.db.models import get_engine, get_session, Article, Mention, init_db

# Processing helpers (your stubs)
from src.processing.risk_detector import detect_risk
from src.processing.summarizer import summarize_text
# VADER sentiment helper (see src/processing/sentiment.py)
from src.processing.sentiment import map_sentiment_from_text

def process_all(batch_limit: int = 200):
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)

    # Grab recent articles (you can change ordering / filtering)
    articles = session.query(Article).order_by(Article.id.desc()).limit(batch_limit).all()
    created = 0
    updated = 0

    for art in articles:
        # Skip if mention already exists for this article
        existing = session.query(Mention).filter(Mention.article_id == art.id).first()
        if existing:
            # print("Skipping (mention exists):", art.id)
            continue

        # Source of text for processing (prefer raw_text, fall back to title)
        text_source = (art.raw_text or "").strip() or (art.title or "")

        # 1) Summary
        summary = summarize_text(text_source)

        # 2) Sentiment (VADER)
        try:
            sentiment_label, sentiment_score = map_sentiment_from_text(summary or text_source)
        except Exception as e:
            print("Sentiment error:", e)
            sentiment_label, sentiment_score = "Neutral", 0.0

        # 3) Risk detection
        try:
            risk = detect_risk(text_source)
            risk_score = int(risk.get("risk_score", 0))
            risk_hits = ",".join(risk.get("hits", []))
        except Exception as e:
            print("Risk detection error:", e)
            risk_score = 0
            risk_hits = ""

        # 4) Create mention row
        mention = Mention(
            article_id=art.id,
            summary=summary,
            sentiment=sentiment_label,
            sentiment_score=str(sentiment_score),
            risk_score=risk_score,
            risk_hits=risk_hits
        )
        session.add(mention)
        created += 1

    session.commit()
    session.close()
    print(f"✅ Created {created} mention(s).")

if __name__ == "__main__":
    process_all()