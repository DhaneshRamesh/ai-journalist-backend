from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    ForeignKey,
    CheckConstraint,
    Index,
    Boolean,
    text,
)
from sqlalchemy.orm import relationship
from .base import Base
from .utils import utcnow  # shared clock


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True)
    title = Column(String(512), nullable=False)
    link = Column(String(2048), unique=True, nullable=False)  # RSS link (unique)
    source = Column(String(128), index=True)                  # e.g. "reuters.com"
    published = Column(DateTime(timezone=True), index=True)
    fetched_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    raw_text = Column(Text)

    __table_args__ = (
        Index("ix_articles_published_source", "published", "source"),
    )

    mentions = relationship(
        "Mention",
        back_populates="article",
        cascade="all, delete-orphan",
    )


class Mention(Base):
    __tablename__ = "mentions"

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False)

    summary = Column(Text, nullable=False)

    sentiment = Column(
        String(16),
        default="neutral",
        nullable=False,
    )

    # Moderation / ops fields (backward compatible with server defaults)
    flagged = Column(Boolean, nullable=False, server_default=text("false"))
    flag_reason = Column(String(128), nullable=True)
    flagged_at = Column(DateTime(timezone=True), nullable=True)

    # Risk / NLP outputs
    risk_score = Column(Integer, default=0, nullable=False)  # integer per schema
    named_entities = Column(Text)

    created_at = Column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)

    article = relationship("Article", back_populates="mentions")

    __table_args__ = (
        CheckConstraint(
            "sentiment IN ('positive','negative','neutral')",
            name="ck_mentions_sentiment",
        ),
        # Helps dashboard queries like /mentions?flagged=true order by created_at
        Index("ix_mentions_flagged_created", "flagged", "created_at"),
    )


class Journalist(Base):
    __tablename__ = "journalists"

    id = Column(Integer, primary_key=True)
    name = Column(String(256), nullable=False)
    outlet = Column(String(256))
    email = Column(String(256))
    twitter = Column(String(128))
    topics = Column(Text)
