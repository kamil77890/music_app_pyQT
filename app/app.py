import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

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
    upload,
    library_repair,
)
from app.endpoints import cloud as cloud_router
from app.endpoints import subscriptions as subs_router
from app.endpoints import tags as tags_router
from app.endpoints import youtube_auth as yt_auth_router

log = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1800
OAUTH_IMPORT_INTERVAL_SECONDS = 86400

# Background auto-tagging: keep the library as fully tagged as possible.
AUTO_TAG_ENABLED = os.environ.get("AUTO_TAG_ENABLED", "1") == "1"
AUTO_TAG_INTERVAL_SECONDS = int(os.environ.get("AUTO_TAG_INTERVAL_SECONDS", "1200"))  # 20 min
AUTO_TAG_BATCH = int(os.environ.get("AUTO_TAG_BATCH", "12"))

# Background recommendation discovery feed.
REC_FEED_ENABLED = os.environ.get("RECOMMENDATION_FEED_ENABLED", "1") == "1"
REC_FEED_START_DELAY_SECONDS = int(os.environ.get("RECOMMENDATION_FEED_START_DELAY_SECONDS", "120"))
REC_FEED_DAILY_TIME = os.environ.get("RECOMMENDATION_FEED_DAILY_TIME", "00:00")
REC_FEED_MAX_RESULTS = int(os.environ.get("RECOMMENDATION_REFRESH_RESULTS", "25"))
REC_FEED_MODE = os.environ.get("RECOMMENDATION_FEED_MODE", "discover")


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


def _auto_tag_loop() -> None:
    import asyncio as _asyncio
    from app.logic.tags.auto_tagger import run_auto_tag_pass

    # Small initial delay so startup isn't blocked.
    time.sleep(30)
    while True:
        try:
            _asyncio.run(run_auto_tag_pass(batch_limit=AUTO_TAG_BATCH))
        except Exception:
            log.exception("Auto-tag pass failed")
        time.sleep(AUTO_TAG_INTERVAL_SECONDS)


def _recommendation_feed_loop() -> None:
    import asyncio as _asyncio
    from app.logic.recommendations.recommendation_feed import get_feed, refresh_feed

    def seconds_until_daily_refresh() -> float:
        try:
            hour_s, minute_s = REC_FEED_DAILY_TIME.split(":", 1)
            hour = int(hour_s)
            minute = int(minute_s)
        except (ValueError, TypeError):
            hour, minute = 0, 0
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return max(1.0, (target - now).total_seconds())

    time.sleep(REC_FEED_START_DELAY_SECONDS)
    try:
        if not get_feed(limit=1).get("items"):
            _asyncio.run(
                refresh_feed(
                    max_results=REC_FEED_MAX_RESULTS,
                    mode=REC_FEED_MODE,
                    replace=True,
                    reason="startup_empty_cache",
                )
            )
    except Exception:
        log.exception("Initial recommendation feed refresh failed")

    while True:
        time.sleep(seconds_until_daily_refresh())
        try:
            _asyncio.run(
                refresh_feed(
                    max_results=REC_FEED_MAX_RESULTS,
                    mode=REC_FEED_MODE,
                    replace=True,
                    reason="daily_midnight",
                )
            )
        except Exception:
            log.exception("Recommendation feed refresh failed")


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
    if AUTO_TAG_ENABLED:
        threading.Thread(
            target=_auto_tag_loop, daemon=True, name="auto-tagger"
        ).start()
    if REC_FEED_ENABLED:
        threading.Thread(
            target=_recommendation_feed_loop, daemon=True, name="recommendation-feed"
        ).start()
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
        self.app.include_router(upload.router)
        self.app.include_router(library_repair.router)

    def run(self) -> FastAPI:
        self.set_up()
        self.register_routers()
        return self.app


app = Application().run()
