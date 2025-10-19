"""Fetch Google News RSS and store into Articles (robust, with UA + AU region)."""
import time
import urllib.parse
from datetime import datetime, timezone
import sys
from pathlib import Path

import requests
import feedparser

# Make 'src' importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.session import SessionLocal
from src.db import models

GOOGLE_NEWS_QUERIES = [
    "AI startups",
    "machine learning",
    "fintech Australia",
]

UA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def _build_url(q: str) -> str:
    qs = urllib.parse.quote_plus(q)
    # AU region feed
    return f"https://news.google.com/rss/search?q={qs}&hl=en-AU&gl=AU&ceid=AU:en"

def _get_link(entry) -> str | None:
    link = getattr(entry, "link", None)
    if not link:
        links = getattr(entry, "links", None)
        if links and isinstance(links, list) and links:
            # feedparser style dicts
            if isinstance(links[0], dict):
                link = links[0].get("href")
            else:
                # sometimes it's a custom object
                link = getattr(links[0], "href", None)
    return link

def _get_published(entry):
    # Prefer parsed time if available
    pp = getattr(entry, "published_parsed", None)
    if pp:
        try:
            return datetime.fromtimestamp(time.mktime(pp), tz=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)

def fetch_and_store():
    db = SessionLocal()
    inserted = 0
    try:
        for q in GOOGLE_NEWS_QUERIES:
            url = _build_url(q)
            r = requests.get(url, headers=UA_HEADERS, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            # Debug: print summary of the feed
            # print(q, "entries:", len(feed.entries), "bozo:", getattr(feed, "bozo", False))
            for e in feed.entries:
                link = _get_link(e)
                if not link:
                    continue
                exists = db.query(models.Article).filter_by(link=link).first()
                if exists:
                    continue
                art = models.Article(
                    title=getattr(e, "title", None),
                    link=link,
                    source=(getattr(getattr(e, "source", {}), "title", None)
                            if hasattr(e, "source") and isinstance(e.source, dict)
                            else (e.source.get("title") if isinstance(getattr(e, "source", None), dict) else None)),
                    published=_get_published(e),
                    fetched_at=datetime.now(timezone.utc),
                    raw_text=None,
                )
                db.add(art)
                inserted += 1
        db.commit()
    finally:
        db.close()
    print(f"Inserted {inserted} articles")

if __name__ == "__main__":
    fetch_and_store()
