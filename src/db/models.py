from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True)
    title = Column(String(512))
    link = Column(String(2048), unique=True)
    source = Column(String(128))
    published = Column(DateTime(timezone=True))
    fetched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    raw_text = Column(Text)
    mentions = relationship("Mention", back_populates="article", cascade="all, delete-orphan")

class Mention(Base):
    __tablename__ = "mentions"
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"))
    summary = Column(Text)
    sentiment = Column(String(16))
    risk_score = Column(Integer)
    named_entities = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    article = relationship("Article", back_populates="mentions")

class Journalist(Base):
    __tablename__ = "journalists"
    id = Column(Integer, primary_key=True)
    name = Column(String(256))
    outlet = Column(String(256))
    email = Column(String(256))
    twitter = Column(String(128))
    topics = Column(Text)
