from __future__ import annotations

import os
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Iterable, List

import requests
import feedparser
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from src.db import models

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
    """
    cols = _model_columns(models.Article)
    if "url" in cols:
        return "url"
    if "link" in cols:
        return "link"
    # Fallback to url; caller will likely fail if schema mismatches.
    return "url"

def _get_article_by_unique(db: Session, unique_key: str, value: str):
    col = getattr(models.Article, unique_key)
    return db.query(models.Article).filter(col == value).one_or_none()

def _upsert_article(db: Session, data: Dict[str, Any]) -> models.Article:
    """
    Upsert Article by unique key ('url' or 'link'), copying only known columns.
    """
    unique_key = _get_unique_key_name_for_article()
    if unique_key not in data or not data[unique_key]:
        raise ValueError(f"Missing required unique field '{unique_key}' in article data.")

    create_kwargs = _filtered_kwargs(data, models.Article)
    existing = _get_article_by_unique(db, unique_key, data[unique_key])

    if existing:
        # Update existing with provided fields (except id)
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
        existing = _get_article_by_unique(db, unique_key, data[unique_key])
        if existing:
            for k, v in create_kwargs.items():
                if k != "id":
                    setattr(existing, k, v)
            db.add(existing)
            db.flush()
            return existing
        raise

def _insert_demo_mention(db: Session, article_id: int, title: str, snippet: str):
    """
    Insert a lightweight Mention so /api/mentions shows something.
    Will adapt to your Mention schema (only known columns are used).
    """
    payload = {
        "article_id": article_id,
        "summary": f"Imported: {title}"[:500] if title else "Imported article",
        "sentiment": "neutral",
        "risk_score": 0.0,
        "named_entities": "",
        "created_at": _utcnow(),
    }
    kwargs = _filtered_kwargs(payload, models.Mention)
    m = models.Mention(**kwargs)
    db.add(m)
    return m

# ----------------------------
# Google News RSS ingestion
# ----------------------------

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

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
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            # time.struct_time -> datetime
            import time
            ts = entry.published_parsed
            dt = datetime(*ts[:6], tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    # Fallback: attempt parsing text
    txt = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if txt:
        try:
            # very forgiving parse attempt
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(txt).astimezone(timezone.utc)
        except Exception:
            pass
    return None

def _entry_to_article_dict(entry, unique_key: str) -> Dict[str, Any]:
    title = getattr(entry, "title", "") or ""
    link = getattr(entry, "link", "") or ""
    published = _parse_published(entry)
    # Some feeds put source.title under entry.source
    source = ""
    if hasattr(entry, "source"):
        try:
            source = entry.source.get("title") if isinstance(entry.source, dict) else entry.source
        except Exception:
            source = ""
    snippet = getattr(entry, "summary", "") or ""

    # Build a generic dict and map url/link based on your schema:
    base = {
        "title": title,
        "source": source,
        "published": published,
        "content": snippet,        # if your Article has 'content' column
        "created_at": _utcnow(),
        "fetched_at": _utcnow(),   # if your Article has 'fetched_at'
    }
    if unique_key == "url":
        base["url"] = link
    else:
        base["link"] = link
    return base

def _fetch_articles_for_keyword(kw: str, per_kw_limit: int) -> List[Dict[str, Any]]:
    url = _google_news_rss_url(kw)
    feed = _fetch_feed(url)
    if not feed or not getattr(feed, "entries", None):
        return []
    # entries is a list of objects with attributes like title, link, published, summary
    return [feed.entries[i] for i in range(min(per_kw_limit, len(feed.entries)))]

# ----------------------------
# Public entrypoint used by your /api/ingest route
# ----------------------------

def run_ingest(
    db: Session,
    source: Optional[str],
    limit: int,
    since_utc: datetime,  # not used by RSS mode, but kept for API compatibility
    dry_run: bool = False,
    keywords: Optional[List[str]] = None,
    per_keyword_limit: int = 5,
) -> Dict[str, Any]:
    """
    If source == 'google', fetch Google News RSS for given keywords.
    Otherwise, fall back to the previous demo single-article ingest.

    Returns a dict with counts and the first article URL/link touched.
    """
    unique_key = _get_unique_key_name_for_article()

    # If not Google mode, keep the very-safe demo ingest
    if (source or "demo").lower() != "google":
        demo_article = {
            unique_key: "https://example.com/ai-journalist-demo-article",
            "title": "AI Journalist monitor connected end-to-end",
            "source": source or "demo",
            "published": _utcnow(),
            "content": "Demo article inserted by ingest endpoint.",
            "created_at": _utcnow(),
        }
        before_articles = db.query(func.count(models.Article.id)).scalar() or 0
        before_mentions = db.query(func.count(models.Mention.id)).scalar() or 0

        if dry_run:
            return {
                "mode": "demo",
                "status": "ok",
                "dry_run": True,
                "since_utc": since_utc.isoformat(),
                "would_upsert_article": demo_article[unique_key],
                "counts_before": {"articles": before_articles, "mentions": before_mentions},
                "counts_after": {"articles": before_articles, "mentions": before_mentions},
            }

        try:
            art = _upsert_article(db, demo_article)
            db.flush()
            _insert_demo_mention(db, art.id, title=demo_article.get("title", ""), snippet=demo_article.get("content", ""))
            db.commit()
        except Exception as e:
            db.rollback()
            return {
                "mode": "demo",
                "status": "error",
                "message": f"Ingest failed: {e.__class__.__name__}: {str(e)}",
                "since_utc": since_utc.isoformat(),
            }

        after_articles = db.query(func.count(models.Article.id)).scalar() or 0
        after_mentions = db.query(func.count(models.Mention.id)).scalar() or 0

        return {
            "mode": "demo",
            "status": "ok",
            "dry_run": False,
            "since_utc": since_utc.isoformat(),
            "upserted_article": demo_article[unique_key],
            "counts_before": {"articles": before_articles, "mentions": before_mentions},
            "counts_after": {"articles": after_articles, "mentions": after_mentions},
        }

    # Google News RSS mode
    kw_list = (keywords or os.environ.get("INGEST_KEYWORDS", "") or "").strip()
    if not kw_list and not keywords:
        # sensible defaults if none supplied
        keywords = ["AI", "journalism", "startups"]
    elif not keywords:
        keywords = [k.strip() for k in kw_list.split(",") if k.strip()]

    # Pre counts
    before_articles = db.query(func.count(models.Article.id)).scalar() or 0
    before_mentions = db.query(func.count(models.Mention.id)).scalar() or 0

    fetched_entries: List[Any] = []
    for kw in keywords:
        entries = _fetch_articles_for_keyword(kw, per_kw_limit=per_keyword_limit)
        fetched_entries.extend(entries)
        # optional global cap
        if len(fetched_entries) >= limit:
            fetched_entries = fetched_entries[:limit]
            break

    if dry_run:
        would = []
        for e in fetched_entries[: min(5, len(fetched_entries))]:
            link = getattr(e, "link", "")
            would.append(link)
        return {
            "mode": "google",
            "status": "ok",
            "dry_run": True,
            "keywords": keywords,
            "planned_count": len(fetched_entries),
            "example_links": would,
            "counts_before": {"articles": before_articles, "mentions": before_mentions},
            "counts_after": {"articles": before_articles, "mentions": before_mentions},
        }

    first_key_value = None
    inserted = 0
    try:
        for e in fetched_entries:
            adata = _entry_to_article_dict(e, unique_key)
            if first_key_value is None:
                first_key_value = adata.get(unique_key)
            art = _upsert_article(db, adata)
            db.flush()
            # add a tiny mention so /api/mentions shows something
            _insert_demo_mention(db, art.id, title=adata.get("title", ""), snippet=adata.get("content", "") or "")
            inserted += 1
        db.commit()
    except Exception as ex:
        db.rollback()
        return {
            "mode": "google",
            "status": "error",
            "message": f"Ingest failed: {ex.__class__.__name__}: {str(ex)}",
            "keywords": keywords,
        }

    after_articles = db.query(func.count(models.Article.id)).scalar() or 0
    after_mentions = db.query(func.count(models.Mention.id)).scalar() or 0

    return {
        "mode": "google",
        "status": "ok",
        "dry_run": False,
        "keywords": keywords,
        "ingested": inserted,
        "first_item": first_key_value,
        "counts_before": {"articles": before_articles, "mentions": before_mentions},
        "counts_after": {"articles": after_articles, "mentions": after_mentions},
    }