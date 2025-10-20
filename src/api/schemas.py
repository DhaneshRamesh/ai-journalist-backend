from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

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

    class Config:
        from_attributes = True  # pydantic v2-compatible shorthand

class MentionOut(BaseModel):
    id: int
    article_id: int
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    # risk_score should be float (pipeline emits decimals)
    risk_score: Optional[float] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ─────────────────────────────
# NLP models
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
# Ingestion request
# ─────────────────────────────
# Supports both styles:
#  - backfill_days (preferred by routes.py wrapper)
#  - since_utc (if you want to pass an explicit timestamp)
class IngestIn(BaseModel):
    source: Optional[str] = None
    limit: int = Field(10, ge=1, le=100)
    # routes.py computes since_utc from this if since_utc not supplied
    backfill_days: int = Field(2, ge=0, le=30)
    # optional explicit timestamp (ISO 8601). If provided, your route can override backfill_days.
    since_utc: Optional[datetime] = None
    dry_run: bool = False
