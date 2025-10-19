from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class ArticleOut(BaseModel):
    id: int
    title: Optional[str] = None
    link: Optional[str] = None
    source: Optional[str] = None
    published: Optional[datetime] = None
    class Config: from_attributes = True

class MentionOut(BaseModel):
    id: int
    article_id: int
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    risk_score: Optional[int] = None
    created_at: Optional[datetime] = None
    class Config: from_attributes = True

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
