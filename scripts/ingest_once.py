#!/usr/bin/env python3
"""
Improved ingestion: fetch Google News RSS and save into SQLite (dev.db)
Usage:
    python scripts/ingest_once.py
"""
import feedparser
import requests
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
import sys
from pathlib import Path
# add repo root to sys.path so imports like `from src...` work when script run directly
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
from src.db.models import Article, init_db, get_engine, get_session
import os

# configure
KEYWORDS = ["AI", "journalism", "startups"]
LIMIT_PER_KEYWORD = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

def google_news_rss_url(query: str, hl="en-US", gl="US", ceid="US:en"):
    q = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"

def fetch_feed(url: str):
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        print("Non-200 response:", resp.status_code)
        return None
    return feedparser.parse(resp.content)

def fetch_articles_for_kw(kw: str, limit: int = LIMIT_PER_KEYWORD):
    url = google_news_rss_url(kw)
    print("Fetching:", url)
    feed = fetch_feed(url)
    if not feed or not getattr(feed, "entries", None):
        print(f"No entries for {kw}")
        return []
    articles = []
    for entry in feed.entries[:limit]:
        source = ""
        if hasattr(entry, "source"):
            try:
                source = entry.source.get("title") if isinstance(entry.source, dict) else entry.source
            except Exception:
                source = ""
        articles.append({
            "title": getattr(entry, "title", ""),
            "link": getattr(entry, "link", ""),
            "published": getattr(entry, "published", ""),
            "source": source or "",
            "fetched_at": datetime.now(timezone.utc),
            "raw_text": getattr(entry, "summary", "") or ""
        })
    return articles

def main():
    # init DB
    engine = get_engine()
    init_db(engine)
    session = get_session(engine)

    inserted = 0
    for kw in KEYWORDS:
        print(f"\n🔎 Fetching for keyword: {kw}")
        arts = fetch_articles_for_kw(kw)
        print(f"Found {len(arts)} entries.")
        for a in arts:
            # avoid duplicates by link (unique constraint)
            existing = session.query(Article).filter(Article.link == a["link"]).first()
            if existing:
                print("Skipping existing:", a["link"])
                continue
            art = Article(
                title=a["title"],
                link=a["link"],
                published=a["published"],
                source=a["source"],
                fetched_at=a["fetched_at"],
                raw_text=a["raw_text"]
            )
            session.add(art)
            inserted += 1
    session.commit()
    session.close()
    print(f"\n✅ Inserted {inserted} new articles into DB.")

if __name__ == "__main__":
    main()