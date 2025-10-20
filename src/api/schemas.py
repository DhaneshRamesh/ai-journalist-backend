from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from zoneinfo import ZoneInfo

# ─────────────────────────────
# Data models (responses)
# ─────────────────────────────

class ArticleOut(BaseModel):
    id: int
    title: Optional[str] = None
    # If your DB/model uses `url` not `link`, consider renaming this field or adding aliasing.
    link: Optional[str] = None
    source: Optional[str] = None
    published: Optional[datetime] = None
    fetched_at: Optional[datetime] = None  # ← ADDED (optional)

    class Config:
        from_attributes = True  # pydantic v2-compatible shorthand
        json_encoders = {
            datetime: lambda v: v.replace(tzinfo=ZoneInfo("UTC")).isoformat()
        }

class MentionOut(BaseModel):
    id: int
    article_id: int
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    # risk_score should be float (pipeline emits decimals)
    risk_score: Optional[float] = None
    created_at: Optional[datetime] = None
    article: ArticleOut = None  # ← KEY FIX: NESTED ARTICLE!

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.replace(tzinfo=ZoneInfo("UTC")).isoformat()
        }

# ─────────────────────────────
# NLP models (UNCHANGED)
# ─────────────────────────────

class SummarizeIn(BaseModel):
    text: str

class SummarizeOut(BaseModel):
    summary: str

class MatchOut(BaseModel):
    id: int
    name: str
    outlet: str
    score: float
    reason: str

# ─────────────────────────────
# Ingestion request (YOUR VERSION - UNCHANGED)
# ─────────────────────────────
class IngestIn(BaseModel):
    source: Optional[str] = None                  # "google" for RSS mode, anything else -> demo
    limit: int = Field(10, ge=1, le=200)         # total max items across keywords
    backfill_days: int = Field(1, ge=0, le=30)   # kept for compatibility (not used in RSS mode)
    since_utc: Optional[datetime] = None         # optional explicit TS (not used in RSS mode)
    dry_run: bool = False
    keywords: Optional[List[str]] = None         # e.g., ["AI","journalism","startups"]
    per_keyword_limit: int = Field(5, ge=1, le=50)

# ─────────────────────────────
# Ingestion response (NEW - matches your ingest.py output)
# ─────────────────────────────
class IngestOut(BaseModel):
    status: str
    mode: str
    inserted: int = 0
    fetched: Optional[int] = None
    keywords: Optional[List[str]] = None
    counts_before: dict
    counts_after: dict
    message: Optional[str] = None  # For errors/dry_run
    planned: Optional[int] = None  # For dry_run mode

    class Config:
        from_attributes = True