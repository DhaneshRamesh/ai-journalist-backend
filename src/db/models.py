# src/db/models.py
import os
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, create_engine, UniqueConstraint, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

Base = declarative_base()

class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    link = Column(String, nullable=False, unique=True)
    published = Column(String, nullable=True)
    source = Column(String, nullable=True)
    fetched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    raw_text = Column(Text, nullable=True)

    mentions = relationship("Mention", back_populates="article")

class Mention(Base):
    __tablename__ = "mentions"
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    sentiment = Column(String, nullable=True)        # Positive / Neutral / Negative
    sentiment_score = Column(String, nullable=True)  # raw score string (for debugging)
    risk_score = Column(Integer, nullable=True)
    risk_hits = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    article = relationship("Article", back_populates="mentions")

    __table_args__ = (
        UniqueConstraint("article_id", name="uq_mention_article"),
    )

def get_engine(url: str = DATABASE_URL):
    # sqlite needs check_same_thread False in many dev setups
    return create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})

def get_session(engine=None):
    if engine is None:
        engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()

def init_db(engine=None):
    engine = engine or get_engine()
    Base.metadata.create_all(bind=engine)