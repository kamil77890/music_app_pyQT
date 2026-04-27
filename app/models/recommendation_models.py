from typing import Any

from pydantic import BaseModel, Field


class Song(BaseModel):
    title: str
    artist: str
    videoId: str
    url: str
    coverUrl: str


class RecommendationData(BaseModel):
    songs: list[Song]
    playlist: list[Any] = Field(default_factory=list)
    nextPageToken: str | None = None


class RecommendationResponse(BaseModel):
    success: bool
    profile: dict[str, Any]
    data: RecommendationData