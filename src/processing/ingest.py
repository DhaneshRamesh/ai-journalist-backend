# src/processing/ingest.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from src.db import models

def _upsert_article(db: Session, data: Dict[str, Any]) -> models.Article:
    """
    Very small upsert on URL. Adjust if you have a unique index on Article.url.
    """
    url = data["url"]
    existing = db.query(models.Article).filter(models.Article.url == url).one_or_none()
    if existing:
        # Update minimal fields; expand as needed
        existing.title = data.get("title", existing.title)
        existing.source = data.get("source", existing.source)
        existing.published = data.get("published", existing.published)
        existing.content = data.get("content", existing.content)
        db.add(existing)
        return existing

    art = models.Article(
        url=url,
        title=data.get("title"),
        source=data.get("source"),
        published=data.get("published"),
        content=data.get("content"),
        created_at=datetime.utcnow(),
    )
    db.add(art)
    return art

def _insert_demo_mention(db: Session, article_id: int):
    m = models.Mention(
        article_id=article_id,
        entity="Silverseven",
        sentiment="neutral",
        risk=0.12,
        created_at=datetime.utcnow(),
    )
    db.add(m)
    return m

def run_ingest(
    db: Session,
    source: Optional[str],
    limit: int,
    since_utc: datetime,
    dry_run: bool = False,
):
    """
    Demo ingest:
      - Pretends to fetch 'limit' items since 'since_utc' from 'source'
      - Actually upserts ONE deterministic article so the UI shows progress
      - Inserts one mention tied to that article
    Replace later with your real fetchers (RSS, APIs, etc.).
    """
    demo_article = {
        "url": "https://example.com/ai-journalist-demo-article",
        "title": "AI Journalist monitor connected end-to-end",
        "source": source or "demo",
        "published": datetime.utcnow(),
        "content": (
            "This is a demo article created by the ingest endpoint to verify the pipeline. "
            "Replace run_ingest(...) with your real ingestion logic."
        ),
    }

    # Count before
    before_articles = db.query(func.count(models.Article.id)).scalar() or 0
    before_mentions = db.query(func.count(models.Mention.id)).scalar() or 0

    if dry_run:
        # Don’t mutate; just return a preview
        return {
            "status": "ok",
            "dry_run": True,
            "source": source or "demo",
            "since_utc": since_utc.isoformat(),
            "would_upsert_article": demo_article["url"],
            "counts_before": {"articles": before_articles, "mentions": before_mentions},
            "counts_after": {"articles": before_articles, "mentions": before_mentions},
        }

    # Upsert + mention
    art = _upsert_article(db, demo_article)
    db.flush()  # ensure art.id
    _insert_demo_mention(db, art.id)
    db.commit()

    # Count after
    after_articles = db.query(func.count(models.Article.id)).scalar() or 0
    after_mentions = db.query(func.count(models.Mention.id)).scalar() or 0

    return {
        "status": "ok",
        "dry_run": False,
        "source": source or "demo",
        "since_utc": since_utc.isoformat(),
        "upserted_article": demo_article["url"],
        "counts_before": {"articles": before_articles, "mentions": before_mentions},
        "counts_after": {"articles": after_articles, "mentions": after_mentions},
    }