from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class PlaylistSong(BaseModel):
    videoId: str
    title: str
    artist: str
    viewed: bool = False
    duration: int
    cover: Optional[str] = None
    path: str

    model_config = ConfigDict(from_attributes=True)


class Playlist(BaseModel):
    name: str
    songs: List[PlaylistSong] = []

    model_config = ConfigDict(from_attributes=True)


class Song(BaseModel):
    id: str
    title: str
    artist: str
    duration: int
    videoId: str
    cover: str
    fileUri: str
    views: str
    isLocal: bool

    model_config = ConfigDict(from_attributes=True)
