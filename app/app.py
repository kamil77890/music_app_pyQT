from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.stałe import Parameters

from app.endpoints import (
    download,
    home,
    songs,
    data,
    like,
    file_download,
    search,
    song_id,
    song_title,
    subtitles,
    video_url,
    register,
    playlists,
)
from app.endpoints import cloud as cloud_router


class Application:
    def __init__(self) -> None:
        self.app = FastAPI(
            title="Music API",
            description="FastAPI version of Flask app",
            version="1.0.0",
        )

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def set_up(self) -> None:
        Parameters()

    def register_routers(self) -> None:
        print("Registering routers...")
        self.app.include_router(home.router)
        self.app.include_router(songs.router)
        self.app.include_router(download.router)
        self.app.include_router(data.router)
        self.app.include_router(like.router)
        self.app.include_router(file_download.router)
        self.app.include_router(search.router)
        self.app.include_router(song_id.router)
        self.app.include_router(song_title.router)
        self.app.include_router(subtitles.router)
        self.app.include_router(video_url.router)
        self.app.include_router(register.router)
        self.app.include_router(cloud_router.router)
        self.app.include_router(playlists.router)

    def run(self) -> FastAPI:
        self.set_up()
        self.register_routers()
        return self.app


app = Application().run()
