"""Pydantic schemas for API responses and requests (legacy-safe)."""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from zoneinfo import ZoneInfo

# ─────────────────────────────
# Helpers
# ─────────────────────────────

def _iso_dt(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    # ensure ISO string with tz if missing
    if v.tzinfo is None:
        v = v.replace(tzinfo=ZoneInfo("UTC"))
    return v.isoformat()

# ─────────────────────────────
# Data models (responses)
# ─────────────────────────────

class ArticleOut(BaseModel):
    id: int
    title: Optional[str] = None
    # NOTE: DB uses `link` (unique). Keep name for legacy API compatibility.
    link: Optional[str] = None
    source: Optional[str] = None
    published: Optional[datetime] = None
    fetched_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {datetime: _iso_dt}

class MentionOut(BaseModel):
    id: int
    article_id: int
    summary: Optional[str] = None
    sentiment: Optional[str] = None

    # Align with DB (INTEGER). If your pipeline emits decimals, round before persisting.
    risk_score: Optional[int] = 0
    named_entities: Optional[str] = None

    created_at: Optional[datetime] = None

    # NEW: moderation/ops (optional to preserve legacy)
    flagged: Optional[bool] = False
    flag_reason: Optional[str] = None
    flagged_at: Optional[datetime] = None

    # Include nested article for UI convenience (joinedload in routes)
    article: Optional[ArticleOut] = None

    class Config:
        from_attributes = True
        json_encoders = {datetime: _iso_dt}

# ─────────────────────────────
# NLP models
# ─────────────────────────────

class SummarizeIn(BaseModel):
    text: str

class SummarizeOut(BaseModel):
    summary: str

# Backward-compatible: some rankers return topics; some return score/reason
class MatchOut(BaseModel):
    id: int
    name: str
    outlet: Optional[str] = ""
    topics: Optional[str] = ""
    score: Optional[float] = None
    reason: Optional[str] = None

# ─────────────────────────────
# Ingestion models
# ─────────────────────────────

class IngestIn(BaseModel):
    # Keep None default; backend will default to "google" if missing
    source: Optional[str] = None                  # "google", "demo", "bing", etc.
    limit: int = Field(10, ge=1, le=200)         # total max items across keywords
    backfill_days: int = Field(1, ge=0, le=30)   # if >0 and since_utc is None, compute it
    since_utc: Optional[datetime] = None         # explicit start time
    dry_run: bool = False
    keywords: Optional[List[str]] = None         # e.g., ["AI","journalism","startups"]
    per_keyword_limit: int = Field(5, ge=1, le=50)

class IngestOut(BaseModel):
    # Common
    status: str
    message: Optional[str] = None

    # New-style fields (params-based recent ingest)
    mode: Optional[str] = None
    inserted: Optional[int] = 0
    fetched: Optional[int] = None
    keywords: Optional[List[str]] = None
    planned: Optional[int] = None  # for dry_run

    # Legacy fields (JSON-body ingest via run_ingest)
    counts_before: Optional[dict] = None
    counts_after: Optional[dict] = None
    stats: Optional[dict] = None

    class Config:
        from_attributes = True
