from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Subscription(Base):
    __tablename__ = "subscriptions"

    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel_title: Mapped[str] = mapped_column(String(512), nullable=False)
    channel_thumbnail: Mapped[str] = mapped_column(String(1024), nullable=False)
    subscribed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    channel_title: Mapped[str] = mapped_column(String(512), nullable=False)
    video_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    cover: Mapped[str] = mapped_column(String(1024), nullable=False)
    published_at: Mapped[str] = mapped_column(String(64), nullable=False)
    seen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SeenVideo(Base):
    __tablename__ = "seen_video_ids"

    video_id: Mapped[str] = mapped_column(String(16), primary_key=True)


class SongTag(Base):
    __tablename__ = "song_tags"

    video_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    tag: Mapped[str] = mapped_column(String(64), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="ai")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TasteProfileCache(Base):
    __tablename__ = "taste_profile_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    profile_json: Mapped[str] = mapped_column(Text, nullable=False)
    library_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
