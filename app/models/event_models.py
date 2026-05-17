from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


EventType = Literal["play", "start", "complete", "skip", "seek", "progress"]
FeedbackType = Literal["like", "dislike", "not_interested", "hide_channel"]


class ListeningEventIn(BaseModel):
    video_id: str = Field(..., min_length=6, max_length=16)
    event_type: EventType
    position_sec: float | None = None
    duration_sec: float | None = None
    session_id: str | None = None
    channel_id: str | None = None
    artist: str | None = None
    title: str | None = None
    created_at: datetime | None = None


class EventsBatchIn(BaseModel):
    events: list[ListeningEventIn] = Field(..., max_length=50)


class FeedbackIn(BaseModel):
    video_id: str = Field(..., min_length=6, max_length=16)
    feedback: FeedbackType
    channel_id: str | None = None
    artist: str | None = None


class ImpressionItemIn(BaseModel):
    video_id: str
    position: int = 0
    clicked: bool = False
    dismissed: bool = False


class ImpressionsIn(BaseModel):
    request_id: str
    items: list[ImpressionItemIn] = Field(..., max_length=50)


class ImpressionClickIn(BaseModel):
    request_id: str
    video_id: str
