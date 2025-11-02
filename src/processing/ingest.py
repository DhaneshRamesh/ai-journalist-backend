# src/processing/ingest.py
from __future__ import annotations

import os
import time
import random
import logging
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, NamedTuple

import requests
import feedparser
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine
from pydantic import BaseModel, validator
from dataclasses import dataclass

# ----------------------------------------------------------------------
# Project imports
# ----------------------------------------------------------------------
from src.db import models
from src.processing.summarizer import summarize_text
from src.processing.sentiment import _analyze_sentiment
from src.processing.risk_detector import risk_score

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
@dataclass
class Config:
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    timeout: int = 10
    per_keyword_limit: int = 5
    batch_commit_size: int = 10
    max_summary_length: int = 500
    min_article_length: int = 50
    calls_per_minute: int = 30


config = Config()

# ----------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------
class IngestStats(NamedTuple):
    articles_inserted: int = 0
    mentions_inserted: int = 0
    errors: int = 0
    fetched: int = 0
    keywords_processed: int = 0


class IngestRequest(BaseModel):
    source: str
    limit: int
    since_utc: datetime
    dry_run: bool = False
    keywords: Optional[List[str]] = None
    per_keyword_limit: Optional[int] = None

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _model_columns(model) -> set[str]:
    return {c.key for c in model.__table__.columns}


def _filtered_kwargs(data: dict, model) -> dict:
    cols = _model_columns(model)
    return {k: v for k, v in data.items() if k in cols}


def _unique_key_name() -> str:
    cols = _model_columns(models.Article)
    return "url" if "url" in cols else "link"


def _article_by_unique(db: Session, key: str, value: str) -> Optional[models.Article]:
    col = getattr(models.Article, key)
    return db.query(models.Article).filter(col == value).one_or_none()


def _domain_from_url(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return "unknown"


def _resolve_keywords(req_keywords: Optional[List[str]] = None) -> List[str]:
    if req_keywords:
        return [k.strip() for k in req_keywords if k.strip()]
    env = os.getenv("INGEST_KEYWORDS", "").strip()
    if env:
        return [k.strip() for k in env.split(",") if k.strip()]
    return ["AI", "journalism", "startups"]


# ----------------------------------------------------------------------
# Rate limiter
# ----------------------------------------------------------------------
def rate_limit(calls_per_minute: int | None = None):
    calls_per_minute = calls_per_minute or config.calls_per_minute
    min_interval = 60.0 / calls_per_minute
    last_called = [0.0]

    def decorator(fn):
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            ret = fn(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator


# ----------------------------------------------------------------------
# RSS fetching
# ----------------------------------------------------------------------
def _google_news_rss_url(query: str) -> str:
    q = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


@rate_limit()
def _fetch_feed(url: str) -> Optional[feedparser.FeedParserDict]:
    try:
        r = requests.get(url, headers={"User-Agent": config.user_agent}, timeout=config.timeout)
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as e:
        logger.warning(f"RSS fetch failed for {url}: {e}")
        return None


def _parse_published(entry) -> Optional[datetime]:
    if getattr(entry, "published_parsed", None):
        try:
            ts = entry.published_parsed
            return datetime(*ts[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    txt = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if txt:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(txt)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def _entry_to_article(entry, unique_key: str) -> dict:
    title = getattr(entry, "title", "") or "(untitled)"
    link = getattr(entry, "link", "")
    snippet = getattr(entry, "summary", "")
    source = getattr(getattr(entry, "source", None), "title", "") or _domain_from_url(link)
    return {
        "title": title,
        "source": source,
        "raw_text": snippet,
        "published": _parse_published(entry),
        "fetched_at": _utcnow(),
        unique_key: link,
    }


def _should_include(adata: dict, since_utc: datetime) -> bool:
    if adata.get("published") and adata["published"] < since_utc:
        return False
    content = (adata.get("raw_text") or "") + (adata.get("title") or "")
    if len(content) < config.min_article_length:
        return False
    skip = {"read more", "continue reading", "advertisement"}
    return not any(s in (adata.get("raw_text") or "").lower() for s in skip)


# ----------------------------------------------------------------------
# Fetch articles
# ----------------------------------------------------------------------
def _fetch_articles(keywords: List[str], total_limit: int, since_utc: datetime, per_keyword_limit: int) -> List[dict]:
    unique_key = _unique_key_name()
    all_entries: List[dict] = []
    for kw in keywords:
        feed = _fetch_feed(_google_news_rss_url(kw))
        if not feed or not getattr(feed, "entries", []):
            continue
        for entry in feed.entries[:per_keyword_limit]:
            adata = _entry_to_article(entry, unique_key)
            if _should_include(adata, since_utc):
                all_entries.append(adata)
        if len(all_entries) >= total_limit:
            break
    random.shuffle(all_entries)
    return all_entries[:total_limit]


# ----------------------------------------------------------------------
# DB layer
# ----------------------------------------------------------------------
def _upsert_article(db: Session, data: dict) -> models.Article:
    key = _unique_key_name()
    value = data.get(key)
    if not value:
        raise ValueError("Article payload missing unique key")

    existing = _article_by_unique(db, key, value)
    if existing:
        for k, v in data.items():
            if hasattr(existing, k):
                setattr(existing, k, v)
        existing.fetched_at = _utcnow()
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    article = models.Article(**_filtered_kwargs(data, models.Article))
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def _insert_mention(db: Session, article: models.Article) -> None:
    content = (article.raw_text or "") + (article.title or "")
    summary = summarize_text(content)[: config.max_summary_length]
    sentiment, score = _analyze_sentiment(content)
    risk = risk_score(content, score)
    payload = {
        "article_id": article.id,
        "summary": summary,
        "sentiment": sentiment,
        "risk_score": risk,
        "named_entities": "(placeholder)",
        "created_at": _utcnow(),
    }
    mention = models.Mention(**_filtered_kwargs(payload, models.Mention))
    db.add(mention)


# ----------------------------------------------------------------------
# Core ingest logic
# ----------------------------------------------------------------------
def ingest_google_news(source: str, keywords: List[str], db_url: str, limit: int, since_utc: datetime, per_kw: int, dry_run: bool = False) -> Dict[str, Any]:
    stats = IngestStats()
    articles = _fetch_articles(keywords, limit, since_utc, per_kw)
    stats = stats._replace(fetched=len(articles), keywords_processed=len(keywords))

    if dry_run or not articles:
        return {"status": "ok", "message": "Dry run or no articles found", "stats": stats._asdict()}

    logger.info(f"🔗 Connecting to DB: {db_url}")

    engine = create_engine(db_url, pool_pre_ping=True, pool_size=5, max_overflow=10, future=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = SessionLocal()

    try:
        for adata in articles:
            try:
                art = _upsert_article(db, adata)
                _insert_mention(db, art)
                stats = stats._replace(
                    articles_inserted=stats.articles_inserted + 1,
                    mentions_inserted=stats.mentions_inserted + 1,
                )
            except Exception as exc:
                db.rollback()
                logger.error(f"Error: {exc}")
                stats = stats._replace(errors=stats.errors + 1)
        db.commit()
    finally:
        db.close()

    return {"status": "ok", "message": "Ingestion complete", "stats": stats._asdict()}


# ----------------------------------------------------------------------
# Wrappers matching routes.py
# ----------------------------------------------------------------------
def run_ingest(
    db: Session,
    source: str,
    limit: int,
    since_utc: datetime,
    keywords: Optional[List[str]] = None,
    per_keyword_limit: int = 5,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Used by /api/ingest"""
    db_url = os.getenv("DATABASE_URL")  # ✅ Use encoded env var directly
    if not db_url:
        raise RuntimeError("DATABASE_URL not set in environment.")
    kw = _resolve_keywords(keywords)
    logger.info(f"[run_ingest] Using DB URL: {db_url}")
    return ingest_google_news(source, kw, db_url, limit, since_utc, per_keyword_limit, dry_run)


def run_recent_ingest(
    db: Session,
    limit: int = 10,
    keywords: Optional[List[str]] = None,
    per_keyword_limit: int = 5,
    hours_back: int = 24,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Used by /api/ingest/params"""
    db_url = os.getenv("DATABASE_URL")  # ✅ Use encoded env var directly
    if not db_url:
        raise RuntimeError("DATABASE_URL not set in environment.")
    since_utc = _utcnow() - timedelta(hours=hours_back)
    kw = _resolve_keywords(keywords)
    logger.info(f"[run_recent_ingest] Using DB URL: {db_url}")
    return ingest_google_news("google", kw, db_url, limit, since_utc, per_keyword_limit, dry_run)


# ----------------------------------------------------------------------
# CLI for local test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Google News Ingestion")
    parser.add_argument("--db", default=os.getenv("DATABASE_URL", "sqlite:///dev.db"))
    parser.add_argument("--keywords", nargs="+", default=["AI"])
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--hours", type=int, default=12)
    args = parser.parse_args()

    result = ingest_google_news(
        "google",
        args.keywords,
        args.db,
        args.limit,
        _utcnow() - timedelta(hours=args.hours),
        per_kw=5,
        dry_run=False,
    )
    print(result)
