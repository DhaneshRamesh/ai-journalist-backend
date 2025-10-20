# src/processing/ingest.py

from __future__ import annotations

import os
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import requests
import feedparser
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from urllib.parse import urlparse

from src.db import models


# ----------------------------
# Constants
# ----------------------------
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ----------------------------
# Utilities
# ----------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _model_columns(model) -> set[str]:
    return {c.key for c in model.__table__.columns}


def _filtered_kwargs(data: Dict[str, Any], model) -> Dict[str, Any]:
    cols = _model_columns(model)
    return {k: v for k, v in data.items() if k in cols}


def _get_unique_key_name_for_article() -> str:
    """
    Prefer 'url' if it exists, otherwise 'link'.
    Fallback is 'url' (callers should ensure schema alignment).
    """
    cols = _model_columns(models.Article)
    if "url" in cols:
        return "url"
    if "link" in cols:
        return "link"
    return "url"


def _get_article_by_unique(db: Session, unique_key: str, value: str):
    col = getattr(models.Article, unique_key)
    return db.query(models.Article).filter(col == value).one_or_none()


def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _upsert_article(db: Session, data: Dict[str, Any]) -> models.Article:
    """
    Upsert Article by unique key ('url' or 'link'), copying only known columns.
    Backfills missing fields for existing rows (e.g., title/source).
    """
    unique_key = _get_unique_key_name_for_article()
    if unique_key not in data or not data[unique_key]:
        raise ValueError(f"Missing required unique field '{unique_key}' in article data.")

    create_kwargs = _filtered_kwargs(data, models.Article)
    existing = _get_article_by_unique(db, unique_key, data[unique_key])

    if existing:
        for k, v in create_kwargs.items():
            if k != "id" and v not in (None, ""):
                setattr(existing, k, v)
        db.add(existing)
        return existing

    art = models.Article(**create_kwargs)
    db.add(art)
    try:
        db.flush()
        return art
    except IntegrityError:
        # race-safe upsert
        db.rollback()
        existing = _get_article_by_unique(db, unique_key, data[unique_key])
        if existing:
            for k, v in create_kwargs.items():
                if k != "id" and v not in (None, ""):
                    setattr(existing, k, v)
            db.add(existing)
            db.flush()
            return existing
        raise


def _insert_demo_mention(db: Session, article_id: int, title: str, snippet: str):
    """
    Insert a lightweight Mention so /api/mentions shows something in demo mode.
    Uses only known columns from your Mention model.
    """
    payload = {
        "article_id": article_id,
        "summary": f"Imported: {title}"[:500] if title else "Imported article",
        "sentiment": "neutral",
        "risk_score": 0,  # Integer in your schema
        "named_entities": "",
        "created_at": _utcnow(),
    }
    kwargs = _filtered_kwargs(payload, models.Mention)
    m = models.Mention(**kwargs)
    db.add(m)
    return m


# ----------------------------
# RSS fetching + parsing
# ----------------------------
def _google_news_rss_url(query: str, hl="en-US", gl="US", ceid="US:en") -> str:
    q = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


def _fetch_feed(url: str) -> Optional[feedparser.FeedParserDict]:
    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=12)
    if resp.status_code != 200:
        return None
    return feedparser.parse(resp.content)


def _parse_published(entry) -> Optional[datetime]:
    # Prefer structured time if present
    if getattr(entry, "published_parsed", None):
        try:
            ts = entry.published_parsed  # time.struct_time
            return datetime(*ts[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    # Fallback: parse text if available
    txt = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if txt:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(txt).astimezone(timezone.utc)
        except Exception:
            pass
    return None


def _entry_to_article_dict(entry, unique_key: str) -> Dict[str, Any]:
    title = getattr(entry, "title", "") or "(untitled)"
    link = getattr(entry, "link", "") or ""
    published = _parse_published(entry)

    # Try feed source; else derive from domain
    source = ""
    if hasattr(entry, "source"):
        try:
            # feedparser may expose dict-like or object with 'title'
            if isinstance(entry.source, dict):
                source = entry.source.get("title") or ""
            else:
                source = getattr(entry.source, "title", "") or ""
        except Exception:
            source = ""
    if not source:
        source = _domain_from_url(link)

    snippet = getattr(entry, "summary", "") or ""

    base = {
        "title": title,
        "source": source,
        "published": published,
        "raw_text": snippet,
        "fetched_at": _utcnow(),
    }
    base[unique_key] = link
    return base


def _fetch_articles_for_keyword(kw: str, per_kw_limit: int, unique_key: str) -> List[Dict[str, Any]]:
    url = _google_news_rss_url(kw)
    feed = _fetch_feed(url)
    if not feed or not getattr(feed, "entries", None):
        return []
    entries = feed.entries[:min(per_kw_limit, len(feed.entries))]
    return [_entry_to_article_dict(entry, unique_key) for entry in entries]


def _should_include_article(adata: Dict[str, Any], since_utc: datetime) -> bool:
    published = adata.get("published")
    # Include if published is missing (some feeds) OR it’s recent enough
    return published is None or published >= since_utc


# ----------------------------
# Demo mode
# ----------------------------
def _run_demo_mode(db: Session, limit: int, dry_run: bool) -> Dict[str, Any]:
    """
    Insert exactly one demo article + mention (so the UI shows something).
    """
    unique_key = _get_unique_key_name_for_article()
    demo_article = {
        unique_key: f"https://example.com/demo-{int(time.time())}",
        "title": "AI Journalist Demo Article",
        "source": "demo",
        "published": _utcnow(),
        "raw_text": "This is a demo article inserted by the ingest system.",
        "fetched_at": _utcnow(),
    }

    before_articles = db.query(func.count(models.Article.id)).scalar() or 0
    before_mentions = db.query(func.count(models.Mention.id)).scalar() or 0

    if dry_run:
        return {
            "mode": "demo",
            "status": "ok",
            "dry_run": True,
            "planned": 1,
            "counts_before": {"articles": before_articles, "mentions": before_mentions},
            "counts_after": {"articles": before_articles, "mentions": before_mentions},
        }

    art = _upsert_article(db, demo_article)
    db.flush()
    _insert_demo_mention(db, art.id, demo_article["title"], demo_article["raw_text"])
    db.commit()

    after_articles = db.query(func.count(models.Article.id)).scalar() or 0
    after_mentions = db.query(func.count(models.Mention.id)).scalar() or 0

    return {
        "mode": "demo",
        "status": "ok",
        "inserted": 1,
        "counts_before": {"articles": before_articles, "mentions": before_mentions},
        "counts_after": {"articles": after_articles, "mentions": after_mentions},
    }


# ----------------------------
# Public entrypoint
# ----------------------------
def run_ingest(
    db: Session,
    source: str,
    limit: int,
    since_utc: datetime,
    dry_run: bool = False,
    keywords: Optional[List[str]] = None,
    per_keyword_limit: int = 5,
) -> Dict[str, Any]:
    """
    Ingestion entrypoint.
      - source == "demo": inserts a single demo article + mention.
      - otherwise: Google News RSS mode for provided keywords (or defaults/env).
    """
    unique_key = _get_unique_key_name_for_article()
    limit = max(1, int(limit or 1))

    # --- DEMO MODE ---
    if (source or "").lower() == "demo":
        return _run_demo_mode(db, limit, dry_run)

    # --- GOOGLE NEWS MODE ---
    # keyword resolution: explicit > env > defaults
    if not keywords:
        kw_env = (os.getenv("INGEST_KEYWORDS") or "").strip()
        if kw_env:
            keywords = [k.strip() for k in kw_env.split(",") if k.strip()]
        else:
            keywords = ["AI", "journalism", "startups"]

    before_articles = db.query(func.count(models.Article.id)).scalar() or 0
    before_mentions = db.query(func.count(models.Mention.id)).scalar() or 0

    fetched_entries: List[Dict[str, Any]] = []
    for kw in keywords:
        entries = _fetch_articles_for_keyword(kw, per_keyword_limit, unique_key)
        fetched_entries.extend(entries)  # use extend, not +=
        if len(fetched_entries) >= limit:
            fetched_entries = fetched_entries[:limit]
            break

    if dry_run:
        return {
            "mode": "google",
            "status": "ok",
            "dry_run": True,
            "planned": len(fetched_entries),
            "keywords": keywords,
            "counts_before": {"articles": before_articles, "mentions": before_mentions},
            "counts_after": {"articles": before_articles, "mentions": before_mentions},
        }

    inserted_count = 0
    try:
        for i, adata in enumerate(fetched_entries):
            # Use since_utc filter if present
            if not _should_include_article(adata, since_utc):
                continue

            # Check existing BEFORE upsert to count real inserts
            existing = _get_article_by_unique(db, unique_key, adata[unique_key])
            _upsert_article(db, adata)
            if not existing:
                inserted_count += 1

            # Batch commits to keep the session healthy
            if i % 10 == 9:
                db.commit()
        db.commit()
    except Exception as ex:
        db.rollback()
        return {
            "mode": "google",
            "status": "error",
            "message": f"{ex.__class__.__name__}: {str(ex)}",
            "keywords": keywords,
        }

    after_articles = db.query(func.count(models.Article.id)).scalar() or 0
    after_mentions = db.query(func.count(models.Mention.id)).scalar() or 0

    return {
        "mode": "google",
        "status": "ok",
        "keywords": keywords,
        "fetched": len(fetched_entries),
        "inserted": inserted_count,  # actual new rows
        "counts_before": {"articles": before_articles, "mentions": before_mentions},
        "counts_after": {"articles": after_articles, "mentions": after_mentions},
    }
