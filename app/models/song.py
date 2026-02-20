from pydantic import BaseModel, ConfigDict


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
