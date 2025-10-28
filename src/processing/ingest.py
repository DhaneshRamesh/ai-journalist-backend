# src/ingest/google_news_ingester.py
from __future__ import annotations

import os
import time
import random
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, NamedTuple

import requests
import feedparser
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import create_engine, func
from pydantic import BaseModel, validator

# ----------------------------------------------------------------------
# Project imports (adjust the relative path to match your layout)
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
# Configuration (dataclass – easy to override via env vars later)
# ----------------------------------------------------------------------
from dataclasses import dataclass

@dataclass
class Config:
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    timeout: int = 12
    per_keyword_limit: int = 5
    batch_commit_size: int = 10
    max_summary_length: int = 500
    min_article_length: int = 50
    calls_per_minute: int = 30          # Google News is generous, but keep it polite

config = Config()

# ----------------------------------------------------------------------
# Pydantic / NamedTuple models
# ----------------------------------------------------------------------
class IngestStats(NamedTuple):
    articles_inserted: int = 0
    articles_updated: int = 0
    mentions_inserted: int = 0
    keywords_processed: int = 0
    errors: int = 0
    fetched: int = 0

class IngestRequest(BaseModel):
    source: str
    limit: int
    since_utc: datetime
    dry_run: bool = False
    keywords: Optional[List[str]] = None
    per_keyword_limit: Optional[int] = None

    @validator("limit")
    def limit_positive(cls, v):
        if v < 1:
            raise ValueError("limit must be >= 1")
        return v

    @validator("per_keyword_limit")
    def per_kw_positive(cls, v):
        if v is not None and v < 1:
            raise ValueError("per_keyword_limit must be >= 1")
        return v

# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _model_columns(model) -> set[str]:
    return {c.key for c in model.__table__.columns}

def _filtered_kwargs(data: dict, model) -> dict:
    cols = _model_columns(model)
    return {k: v for k, v in data.items() if k in cols}

def _unique_key_name() -> str:
    """Return the column that uniquely identifies an Article (url or link)."""
    cols = _model_columns(models.Article)
    return "url" if "url" in cols else "link"

def _article_by_unique(db: Session, key: str, value: str) -> Optional[models.Article]:
    col = getattr(models.Article, key)
    return db.query(models.Article).filter(col == value).one_or_none()

def _domain_from_url(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""

def _resolve_keywords(req_keywords: Optional[List[str]] = None) -> List[str]:
    """Fallback chain: request → env var → hard-coded defaults."""
    if req_keywords:
        return [k.strip() for k in req_keywords if k.strip()]

    env = os.getenv("INGEST_KEYWORDS", "").strip()
    if env:
        return [k.strip() for k in env.split(",") if k.strip()]

    return ["AI", "journalism", "startups"]

# ----------------------------------------------------------------------
# Rate limiting decorator (simple token-bucket style)
# ----------------------------------------------------------------------
def rate_limit(calls_per_minute: int | None = None):
    calls_per_minute = calls_per_minute or config.calls_per_minute
    min_interval = 60.0 / calls_per_minute
    last_called = [0.0]

    def decorator(fn):
        def wrapper(*args, **kwargs):
            now = time.time()
            elapsed = now - last_called[0]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            ret = fn(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator

# ----------------------------------------------------------------------
# RSS fetching & parsing
# ----------------------------------------------------------------------
def _google_news_rss_url(query: str, hl: str = "en-US", gl: str = "US", ceid: str = "US:en") -> str:
    q = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"

@rate_limit()
def _fetch_feed(url: str) -> Optional[feedparser.FeedParserDict]:
    try:
        r = requests.get(url, headers={"User-Agent": config.user_agent}, timeout=config.timeout)
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as exc:
        logger.error(f"Failed to fetch {url!r}: {exc}")
        return None

def _parse_published(entry) -> Optional[datetime]:
    # 1. struct_time from feedparser
    if getattr(entry, "published_parsed", None):
        try:
            ts = entry.published_parsed
            return datetime(*ts[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    # 2. RFC-2822 string
    txt = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if txt:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(txt)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None

def _entry_to_article_dict(entry, unique_key: str) -> Dict[str, Any]:
    title = getattr(entry, "title", "") or "(untitled)"
    link = getattr(entry, "link", "") or ""
    published = _parse_published(entry)

    # Source extraction – Google News wraps original feed inside <source>
    source = ""
    if hasattr(entry, "source"):
        try:
            src = entry.source
            source = src.get("title") if isinstance(src, dict) else getattr(src, "title", "")
        except Exception:
            pass
    if not source:
        source = _domain_from_url(link)

    snippet = getattr(entry, "summary", "") or ""
    payload = {
        "title": title,
        "source": source,
        "published": published,
        "raw_text": snippet,
        "fetched_at": _utcnow(),
    }
    payload[unique_key] = link
    return payload

def _should_include(adata: dict, since_utc: datetime) -> bool:
    pub = adata.get("published")
    if pub and pub < since_utc:
        return False

    content = (adata.get("raw_text") or "") + (adata.get("title") or "")
    if len(content.strip()) < config.min_article_length:
        return False

    skip = {"read more", "continue reading", "loading...", "advertisement"}
    if any(p in content.lower() for p in skip):
        return False

    return True

# ----------------------------------------------------------------------
# Core fetching logic
# ----------------------------------------------------------------------
def _fetch_for_keyword(
    kw: str,
    per_kw_limit: int,
    unique_key: str,
    since_utc: datetime,
) -> List[dict]:
    logger.debug(f"Fetching for keyword: {kw!r}")
    feed = _fetch_feed(_google_news_rss_url(kw))
    if not feed or not getattr(feed, "entries", []):
        logger.warning(f"No entries for keyword {kw!r}")
        return []

    collected = []
    for entry in feed.entries[:per_kw_limit]:
        adata = _entry_to_article_dict(entry, unique_key)
        if _should_include(adata, since_utc):
            collected.append(adata)
    return collected

def _fetch_and_filter(
    keywords: List[str],
    total_limit: int,
    since_utc: datetime,
    per_keyword_limit: int,
) -> List[dict]:
    unique_key = _unique_key_name()
    all_articles: List[dict] = []

    for kw in keywords:
        batch = _fetch_for_keyword(kw, per_keyword_limit, unique_key, since_utc)
        all_articles.extend(batch)
        if len(all_articles) >= total_limit:
            break

    random.shuffle(all_articles)
    return all_articles[:total_limit]

# ----------------------------------------------------------------------
# DB upserts (articles + mentions)
# ----------------------------------------------------------------------
def _upsert_article(db: Session, data: dict) -> models.Article:
    """
    Insert a new Article or update an existing one.
    Deduplication is performed on the column returned by ``_unique_key_name()``.
    """
    unique_key = _unique_key_name()
    link = data.get(unique_key)
    if not link:
        raise ValueError("Article payload missing unique key")

    existing = _article_by_unique(db, unique_key, link)
    if existing:
        # UPDATE path
        for k, v in data.items():
            if hasattr(existing, k):
                setattr(existing, k, v)
        existing.fetched_at = _utcnow()
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    # INSERT path
    article = models.Article(**_filtered_kwargs(data, models.Article))
    db.add(article)
    db.commit()
    db.refresh(article)
    return article

def _insert_mention(db: Session, article: models.Article) -> models.Mention:
    content = (article.raw_text or "") + (article.title or "")
    summary = summarize_text(content)[: config.max_summary_length]
    sentiment, score = _analyze_sentiment(content)
    risk = risk_score(content, score)

    payload = {
        "article_id": article.id,
        "summary": summary,
        "sentiment": sentiment,
        "risk_score": risk,
        "named_entities": "(placeholder)",   # replace with real NER later
        "created_at": _utcnow(),
    }
    mention = models.Mention(**_filtered_kwargs(payload, models.Mention))
    db.add(mention)
    return mention

# ----------------------------------------------------------------------
# Public entry-point
# ----------------------------------------------------------------------
def ingest_google_news(request: IngestRequest, db_url: str) -> IngestStats:
    """
    Main ingestion routine.

    * Resolves keywords (request → env → defaults)
    * Fetches RSS feeds, filters, deduplicates
    * Upserts Articles + creates a Mention per article
    * Returns structured stats
    """
    engine = create_engine(db_url, future=True)
    stats = IngestStats()
    keywords = _resolve_keywords(request.keywords)
    per_kw = request.per_keyword_limit or config.per_keyword_limit

    articles = _fetch_and_filter(
        keywords=keywords,
        total_limit=request.limit,
        since_utc=request.since_utc,
        per_keyword_limit=per_kw,
    )
    stats = stats._replace(fetched=len(articles), keywords_processed=len(keywords))

    if request.dry_run:
        logger.info(f"[DRY-RUN] Would process {len(articles)} articles.")
        return stats

    with engine.begin() as conn:          # one transaction for the whole batch
        batch = []
        for adata in articles:
            try:
                article = _upsert_article(conn, adata)
                if not _article_by_unique(conn, _unique_key_name(), adata[_unique_key_name()]):
                    stats = stats._replace(articles_inserted=stats.articles_inserted + 1)
                else:
                    stats = stats._replace(articles_updated=stats.articles_updated + 1)

                mention = _insert_mention(conn, article)
                stats = stats._replace(mentions_inserted=stats.mentions_inserted + 1)

                batch.append((article, mention))
                if len(batch) >= config.batch_commit_size:
                    conn.commit()
                    batch.clear()

            except Exception as exc:
                logger.error(f"Failed to process article {adata.get('title')!r}: {exc}")
                stats = stats._replace(errors=stats.errors + 1)
                conn.rollback()
                continue

        # final commit for remaining items
        if batch:
            conn.commit()

    logger.info(
        f"Ingestion complete → inserted {stats.articles_inserted}, "
        f"updated {stats.articles_updated}, mentions {stats.mentions_inserted}, "
        f"errors {stats.errors}"
    )
    return stats

# ----------------------------------------------------------------------
# Example CLI (optional – useful for local testing or Azure startup script)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    from datetime import timedelta

    parser = argparse.ArgumentParser(description="Google News → DB ingester")
    parser.add_argument("--db", required=True, help="SQLAlchemy DB URL")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--hours", type=int, default=6, help="Look-back window in hours")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    req = IngestRequest(
        source="google_news",
        limit=args.limit,
        since_utc=_utcnow() - timedelta(hours=args.hours),
        dry_run=args.dry_run,
    )
    stats = ingest_google_news(req, args.db)
    print(stats._asdict())
