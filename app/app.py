import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config.stałe import Parameters
from app.db.database import init_db
from app.db.migrate_json import migrate_json_to_postgres
from app.logic.api_handler.handle_feed import run_subscription_poll

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
    recommendations,
    events,
)
from app.endpoints import cloud as cloud_router
from app.endpoints import subscriptions as subs_router
from app.endpoints import tags as tags_router
from app.endpoints import youtube_auth as yt_auth_router

log = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1800
OAUTH_IMPORT_INTERVAL_SECONDS = 86400


def _oauth_import_loop() -> None:
    from app.db import oauth_repository
    from app.logic.youtube_import.importer import run_import

    while True:
        time.sleep(OAUTH_IMPORT_INTERVAL_SECONDS)
        if not oauth_repository.is_connected():
            continue
        try:
            run_import()
        except Exception:
            log.exception("YouTube OAuth import failed")


def _polling_loop() -> None:
    while True:
        try:
            run_subscription_poll()
        except Exception:
            log.exception("Subscription poll failed")
        time.sleep(POLL_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        migrate_json_to_postgres()
    except Exception:
        log.exception("JSON migration to PostgreSQL failed")
    thread = threading.Thread(
        target=_polling_loop, daemon=True, name="subscription-poller"
    )
    thread.start()
    oauth_thread = threading.Thread(
        target=_oauth_import_loop, daemon=True, name="youtube-oauth-import"
    )
    oauth_thread.start()
    yield


class Application:
    def __init__(self) -> None:
        self.app = FastAPI(
            title="Music API",
            description="FastAPI version of Flask app",
            version="1.0.0",
            lifespan=lifespan,
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
        self.app.include_router(recommendations.router)
        self.app.include_router(subs_router.router)
        self.app.include_router(subs_router.notifications_router)
        self.app.include_router(subs_router.video_router)
        self.app.include_router(tags_router.router)
        self.app.include_router(events.router)
        self.app.include_router(yt_auth_router.router)

    def run(self) -> FastAPI:
        self.set_up()
        self.register_routers()
        return self.app


app = Application().run()
