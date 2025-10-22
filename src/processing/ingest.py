from __future__ import annotations
import os
import time
import urllib.parse
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, NamedTuple
from functools import wraps
from dataclasses import dataclass
import requests
import feedparser
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, func
from sqlalchemy.exc import IntegrityError
from urllib.parse import urlparse
from pydantic import BaseModel, validator
from src.db import models
from src.processing.summarizer import summarize_text
from src.processing.sentiment import _analyze_sentiment
from src.processing.risk_detector import risk_score

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
@dataclass
class Config:
    """Configuration for ingestion system"""
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    timeout: int = 12
    per_keyword_limit: int = 5
    batch_commit_size: int = 10
    max_summary_length: int = 500
    min_article_length: int = 50
    calls_per_minute: int = 30

config = Config()

# Data Models
class IngestStats(NamedTuple):
    """Structured statistics for ingestion runs"""
    articles_inserted: int = 0
    articles_updated: int = 0
    mentions_inserted: int = 0
    keywords_processed: int = 0
    errors: int = 0
    fetched: int = 0

class IngestRequest(BaseModel):
    """Validated input for ingestion"""
    source: str
    limit: int
    since_utc: datetime
    dry_run: bool = False
    keywords: Optional[List[str]] = None
    per_keyword_limit: Optional[int] = None

    @validator('limit')
    def limit_must_be_positive(cls, v):
        if v < 1:
            raise ValueError('limit must be >= 1')
        return v

    @validator('per_keyword_limit')
    def per_kw_limit_must_be_positive(cls, v):
        if v is not None and v < 1:
            raise ValueError('per_keyword_limit must be >= 1')
        return v

# Utilities
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _model_columns(model) -> set[str]:
    return {c.key for c in model.__table__.columns}

def _filtered_kwargs(data: Dict[str, Any], model) -> Dict[str, Any]:
    cols = _model_columns(model)
    return {k: v for k, v in data.items() if k in cols}

def _get_unique_key_name_for_article() -> str:
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

def _get_db_stats(db: Session) -> Dict[str, int]:
    return {
        "articles": db.query(func.count(models.Article.id)).scalar() or 0,
        "mentions": db.query(func.count(models.Mention.id)).scalar() or 0,
    }

# 🔥 FIXED: DYNAMIC KEYWORDS - PRIORITY 1 = PASSED KEYWORDS
def _resolve_keywords(keywords: Optional[List[str]] = None) -> List[str]:
    """
    ✅ DYNAMIC KEYWORDS: Prioritize passed keywords over defaults
    ✅ KEEPS PHRASES INTACT: "climate change" stays "climate change"
    ✅ FRONTEND READY: keywords=["climate change", "OpenAI"] → PERFECT!
    """
    # 🔥 PRIORITY 1: Use passed keywords (from frontend!)
    if keywords and len(keywords) > 0:
        # ✅ PRESERVE PHRASES - don't split on spaces!
        return [k.strip() for k in keywords if k.strip()]

    # Priority 2: Environment variable
    kw_env = (os.getenv("INGEST_KEYWORDS") or "").strip()
    if kw_env:
        return [k.strip() for k in kw_env.split(",") if k.strip()]

    # Priority 3: Hardcoded defaults (LAST RESORT)
    return ["AI", "journalism", "startups"]

# Rate Limiting
def rate_limit(calls_per_minute: int = None):
    calls_per_minute = calls_per_minute or config.calls_per_minute
    min_interval = 60.0 / calls_per_minute
    last_called = [0.0]
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator

# RSS Fetching + Parsing
def _google_news_rss_url(query: str, hl="en-US", gl="US", ceid="US:en") -> str:
    q = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"

@rate_limit()
def _fetch_feed(url: str) -> Optional[feedparser.FeedParserDict]:
    try:
        resp = requests.get(url, headers={"User-Agent": config.user_agent}, timeout=config.timeout)
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch {url}: {resp.status_code}")
            return None
        return feedparser.parse(resp.content)
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
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
            return parsedate_to_datetime(txt).astimezone(timezone.utc)
        except Exception:
            pass
    return None

def _entry_to_article_dict(entry, unique_key: str) -> Dict[str, Any]:
    title = getattr(entry, "title", "") or "(untitled)"
    link = getattr(entry, "link", "") or ""
    published = _parse_published(entry)

    source = ""
    if hasattr(entry, "source"):
        try:
            if isinstance(entry.source, dict):
                source = entry.source.get("title") or ""
            else:
                source = getattr(entry.source, "title", "") or ""
        except Exception:
            source = ""

    if not source:
        source = _domain_from_url(link)

    snippet = getattr(entry, "summary", "") or ""

    return {
        "title": title,
        "source": source,
        "published": published,
        "raw_text": snippet,
        "fetched_at": _utcnow(),
    } | {unique_key: link}

def _should_include_article(adata: Dict[str, Any], since_utc: datetime) -> bool:
    published = adata.get("published")
    content = adata.get("raw_text", "") or adata.get("title", "")

    if published and published < since_utc:
        return False

    content_len = len(content.strip())
    if content_len < config.min_article_length:
        return False

    skip_phrases = ['read more', 'continue reading', 'loading...', 'advertisement']
    if any(phrase in content.lower() for phrase in skip_phrases):
        return False

    return True

def _fetch_articles_for_keyword(kw: str, per_kw_limit: int, unique_key: str, since_utc: datetime) -> List[Dict[str, Any]]:
    logger.debug(f"🔍 Fetching articles for keyword: '{kw}'")
    url = _google_news_rss_url(kw)
    feed = _fetch_feed(url)

    if not feed or not getattr(feed, "entries", None):
        logger.warning(f"No entries found for keyword: '{kw}'")
        return []

    entries = []
    max_entries = min(per_kw_limit, len(feed.entries))
    for entry in feed.entries[:max_entries]:
        adata = _entry_to_article_dict(entry, unique_key)
        if _should_include_article(adata, since_utc):
            entries.append(adata)

    logger.debug(f"✅ Found {len(entries)} valid articles for '{kw}'")
    return entries

# Main Processing Functions
def _fetch_and_filter_articles(keywords: List[str], limit: int, since_utc: datetime, per_keyword_limit: int) -> List[Dict[str, Any]]:
    unique_key = _get_unique_key_name_for_article()
    all_entries = []

    for kw in keywords:
        entries = _fetch_articles_for_keyword(kw, per_keyword_limit, unique_key, since_utc)
        all_entries.extend(entries)

        if len(all_entries) >= limit:
            break

    import random
    random.shuffle(all_entries)
    return all_entries[:limit]

def _insert_mention(db: Session, article_id: int, title: str, snippet: str) -> models.Mention:
    """
    Create a mention with summary, sentiment, and risk score using Azure OpenAI GPT-4o-mini.
    """
    content = snippet or title
    summary = summarize_text(content)[:config.max_summary_length]
    sentiment, sentiment_score = _analyze_sentiment(content)
    risk_score_value = risk_score(content, sentiment_score)
    named_entities = _extract_entities(content)

    payload = {
        "article_id": article_id,
        "summary": summary,
        "sentiment": sentiment,
        "sentiment_confidence": sentiment_score,  # Maps to your sentiment.py output
        "risk_score": risk_score_value,
        "named_entities": named_entities,
        "created_at": _utcnow(),
    }

    kwargs = _filtered_kwargs(payload, models.Mention)
    mention = models.Mention(**kwargs)
    db.add(mention)
    return mention

def _process_articles_batch(db: Session, articles: List[Dict[str, Any]], dry_run: bool, stats: IngestStats) -> IngestStats:
    unique_key = _get_unique_key_name_for_article()

    for i, adata in enumerate(articles):
        try:
            existing = _get_article_by_unique(db, unique_key, adata[unique_key])
            art = _upsert_article(db, adata)
            db.flush()

            if not existing:
                stats = stats._replace(articles_inserted=stats.articles_inserted + 1)
            else:
                stats = stats._replace(articles_updated=stats.articles_updated + 1)

            if not dry_run:
                snippet = adata.get("raw_text", "") or adata.get("title", "")
                _insert_mention(db, art.id, adata.get("title", ""), snippet)
                stats = stats._replace(mentions_inserted=stats.mentions_inserted + 1)

            if (i + 1) % config.batch_commit_size == 0:
                db.commit()
                logger.debug(f"💾 Committed batch at article {i + 1}")

        except Exception as e:
            logger.error(f"❌ Error processing article {i}: {e}")
            stats = stats._replace(errors=stats.errors + 1)
            continue

    return stats

def _format_results(stats: IngestStats, before_stats: Dict[str, int], after_stats: Dict[str, int], dry_run: bool, keywords: List[str]) -> Dict[str, Any]:
    return {
        "status": "ok",
        "mode": "google",
        "dry_run": dry_run,
        "keywords": keywords,
        "stats": stats._asdict(),
        "counts_before": before_stats,
        "counts_after": after_stats,
        "summary": {
            "total_articles": after_stats["articles"],
            "total_mentions": after_stats["mentions"],
            "new_articles": stats.articles_inserted,
            "new_mentions": stats.mentions_inserted,
        }
    }

# Public Entrypoint
def run_ingest(
    db: Session,
    source: str,
    limit: int,
    since_utc: datetime,
    dry_run: bool = False,
    keywords: Optional[List[str]] = None,
    per_keyword_limit: Optional[int] = None,
) -> Dict[str, Any]:
    if source.lower() != "google":
        return {"status": "error", "message": "Only 'google' source is supported"}

    try:
        req = IngestRequest(
            source=source, limit=limit, since_utc=since_utc,
            dry_run=dry_run, keywords=keywords, per_keyword_limit=per_keyword_limit
        )
    except ValueError as e:
        return {"status": "error", "message": f"Validation error: {e}"}

    if per_keyword_limit:
        config.per_keyword_limit = per_keyword_limit

    stats = IngestStats()
    keywords = _resolve_keywords(keywords)

    logger.info(f"🚀 Starting ingestion: source={source}, limit={limit}, keywords={keywords[:3]}{'...' if len(keywords) > 3 else ''}")

    try:
        before_stats = _get_db_stats(db)
        stats = stats._replace(keywords_processed=len(keywords))

        articles = _fetch_and_filter_articles(
            keywords, limit, since_utc, config.per_keyword_limit
        )
        stats = stats._replace(fetched=len(articles))

        logger.info(f"📊 Fetched {len(articles)} articles from {len(keywords)} keywords")

        if dry_run:
            return _format_results(stats, before_stats, before_stats, True, keywords)

        stats = _process_articles_batch(db, articles, False, stats)

        db.commit()
        after_stats = _get_db_stats(db)

        logger.info(f"✅ Ingestion complete: {stats.articles_inserted} new articles, {stats.mentions_inserted} mentions")

        return _format_results(stats, before_stats, after_stats, False, keywords)

    except Exception as e:
        logger.error(f"💥 Ingestion failed: {e}", exc_info=True)
        db.rollback()
        return {
            "status": "error",
            "message": f"{e.__class__.__name__}: {str(e)}",
            "stats": stats._asdict()
        }

# 🔥 FRONTEND READY: Dynamic recent ingestion
def run_recent_ingest(db: Session, limit: int = 50, hours_back: int = 24, **kwargs) -> Dict[str, Any]:
    """
    🚀 FRONTEND PERFECT: Dynamic recent ingestion by user keywords
    Usage: run_recent_ingest(db, keywords=["climate change", "OpenAI"], per_keyword_limit=5)
    """
    since_utc = _utcnow() - timedelta(hours=hours_back)
    return run_ingest(db, "google", limit, since_utc, **kwargs)

if __name__ == "__main__":
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine

    # 🔥 TEST DYNAMIC KEYWORDS (Replace with your Azure connection string)
    azure_conn_string = "postgresql+psycopg2://username:password@your-azure-server.postgres.database.azure.com:5432/yourdb?sslmode=require"
    engine = create_engine(azure_conn_string)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    # ✅ TEST 1: Dynamic keywords (FRONTEND SIMULATION)
    print("🔥 TESTING DYNAMIC KEYWORDS...")
    result1 = run_recent_ingest(
        db,
        limit=10,
        keywords=["climate change", "OpenAI", "xAI"],  # ✅ PHRASES PRESERVED!
        per_keyword_limit=3
    )
    print("✅ RESULT:", result1.get("keywords", "No keywords"), "→", result1.get("status"))

    # ✅ TEST 2: Single keyword
    result2 = run_recent_ingest(db, limit=5, keywords=["AI"])
    print("✅ SINGLE:", result2.get("keywords", "No keywords"), "→", result2.get("status"))

    db.close()
