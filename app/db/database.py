import logging
import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

log = logging.getLogger(__name__)

_data_dir = Path(os.environ.get("DATA_DIR", "./data"))
_data_dir.mkdir(parents=True, exist_ok=True)

# SQLite path when Postgres is unavailable or DATABASE_URL is unset.
# For Docker Postgres: set DATABASE_URL=postgresql+psycopg2://music:music@localhost:5432/music_app
_default_sqlite = f"sqlite:///{(_data_dir / 'music_app.db').resolve()}"


def _sqlite_engine(url: str):
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )


def _try_postgres(url: str):
    eng = create_engine(url, pool_pre_ping=True)
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))
    return eng


def _create_engine():
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw or raw.startswith("sqlite"):
        target = raw if raw.startswith("sqlite") else _default_sqlite
        log.debug("Using database URL: %s", target.split("://")[0])
        return _sqlite_engine(target), target

    if "postgresql" not in raw and "postgres" not in raw:
        return create_engine(raw, pool_pre_ping=True), raw

    try:
        eng = _try_postgres(raw)
        return eng, raw
    except Exception as exc:
        log.warning(
            "DATABASE_URL PostgreSQL connection failed (%s). "
            "Using SQLite instead (%s). Remove or fix DATABASE_URL in .env to silence this.",
            exc,
            _default_sqlite,
        )
        return _sqlite_engine(_default_sqlite), _default_sqlite


engine, DATABASE_URL = _create_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope():
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
