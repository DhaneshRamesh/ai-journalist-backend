# src/processing/ingest.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from src.db import models

def _model_columns(model) -> set[str]:
    return {c.key for c in model.__table__.columns}

def _filtered_kwargs(data: Dict[str, Any], model) -> Dict[str, Any]:
    cols = _model_columns(model)
    return {k: v for k, v in data.items() if k in cols}

def _get_article_by_url(db: Session, url: str):
    return db.query(models.Article).filter(models.Article.url == url).one_or_none()

def _upsert_article(db: Session, data: Dict[str, Any]) -> models.Article:
    """
    Upsert by URL. Only writes fields that exist on the Article model.
    Handles IntegrityError (unique constraint) by reloading the existing row.
    """
    url = data["url"]
    # Filter to existing columns
    create_kwargs = _filtered_kwargs(data, models.Article)

    existing = _get_article_by_url(db, url)
    if existing:
        # Update existing fields ONLY if they exist
        for k, v in create_kwargs.items():
            if k != "id":
                setattr(existing, k, v)
        db.add(existing)
        return existing

    art = models.Article(**create_kwargs)
    db.add(art)
    try:
        db.flush()  # attempt insert
        return art
    except IntegrityError:
        db.rollback()
        # Another request may have created it; load and update it
        existing = _get_article_by_url(db, url)
        if existing:
            for k, v in create_kwargs.items():
                if k != "id":
                    setattr(existing, k, v)
            db.add(existing)
            db.flush()
            return existing
        raise  # re-raise if truly unexpected

def _insert_demo_mention(db: Session, article_id: int):
    """
    Insert one mention tied to the article.
    Only sets fields that exist on Mention model.
    """
    payload = {
        "article_id": article_id,
        "entity": "Silverseven",
        "sentiment": "neutral",
        "risk": 0.12,
        "created_at": datetime.utcnow(),
        # Add more fields here if your Mention model has them (summary, title, etc.)
    }
    kwargs = _filtered_kwargs(payload, models.Mention)
    m = models.Mention(**kwargs)
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
      - Pretends to fetch 'limit' items since 'since_utc'
      - Upserts ONE deterministic article by URL
      - Inserts one mention for that article
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
        "created_at": datetime.utcnow(),  # will be ignored if column doesn't exist
    }

    # Counts before
    before_articles = db.query(func.count(models.Article.id)).scalar() or 0
    before_mentions = db.query(func.count(models.Mention.id)).scalar() or 0

    if dry_run:
        return {
            "status": "ok",
            "dry_run": True,
            "source": source or "demo",
            "since_utc": since_utc.isoformat(),
            "would_upsert_article": demo_article["url"],
            "counts_before": {"articles": before_articles, "mentions": before_mentions},
            "counts_after": {"articles": before_articles, "mentions": before_mentions},
        }

    try:
        art = _upsert_article(db, demo_article)
        db.flush()  # ensure art.id
        _insert_demo_mention(db, art.id)
        db.commit()
    except Exception as e:
        db.rollback()
        # Return a structured error so you see the root cause in the frontend
        return {
            "status": "error",
            "message": f"Ingest failed: {e.__class__.__name__}: {str(e)}",
            "source": source or "demo",
            "since_utc": since_utc.isoformat(),
        }

    # Counts after
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
