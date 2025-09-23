#!/usr/bin/env python3
"""
scripts/update_mentions.py
Safe in-place update of existing Mention rows:
- re-summarize (strip HTML)
- recompute sentiment with current sentiment module
- recompute risk

Usage:
  PYTHONPATH=. python3 scripts/update_mentions.py
"""
import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from src.db.models import get_engine, get_session, Article, Mention, init_db
from src.processing.summarizer import summarize_text
from src.processing.sentiment import map_sentiment_from_text
from src.processing.risk_detector import detect_risk

def update_all(batch_limit: int = None):
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)

    q = session.query(Mention).order_by(Mention.id.asc())
    if batch_limit:
        q = q.limit(batch_limit)
    mentions = q.all()
    updated = 0

    for m in mentions:
        art = session.query(Article).filter(Article.id == m.article_id).first()
        text_source = (art.raw_text or "").strip() or (art.title or "")
        # new summary (summarizer strips HTML)
        new_summary = summarize_text(text_source)
        # sentiment
        try:
            label, score = map_sentiment_from_text(new_summary or text_source)
        except Exception:
            label, score = ("Neutral", 0.0)
        # risk
        try:
            risk = detect_risk(text_source)
            risk_score = int(risk.get("risk_score", 0))
            risk_hits = ",".join(risk.get("hits", []))
        except Exception:
            risk_score = 0
            risk_hits = ""

        changed = False
        if (m.summary or "") != new_summary:
            m.summary = new_summary
            changed = True
        if (m.sentiment or "") != label:
            m.sentiment = label
            changed = True
        if (m.sentiment_score or "") != str(score):
            m.sentiment_score = str(score)
            changed = True
        if (m.risk_score or 0) != risk_score:
            m.risk_score = risk_score
            changed = True
        if (m.risk_hits or "") != risk_hits:
            m.risk_hits = risk_hits
            changed = True

        if changed:
            updated += 1

    session.commit()
    session.close()
    print(f"✅ Updated {updated} mention(s). Total mentions scanned: {len(mentions)}")

if __name__ == "__main__":
    update_all()
