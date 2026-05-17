from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from app.db.database import session_scope
from app.db.models import ImportedYtItem, OAuthToken


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fernet():
    raw = os.environ.get("FERNET_KEY", "").strip()
    if not raw:
        return None
    try:
        from cryptography.fernet import Fernet

        return Fernet(raw.encode())
    except (ImportError, ValueError):
        return None


def _encrypt(plain: str) -> str:
    f = _fernet()
    if not f:
        return base64.urlsafe_b64encode(plain.encode()).decode()
    return f.encrypt(plain.encode()).decode()


def _decrypt(token: str) -> str:
    f = _fernet()
    if not f:
        return base64.urlsafe_b64decode(token.encode()).decode()
    try:
        return f.decrypt(token.encode()).decode()
    except Exception:
        return base64.urlsafe_b64decode(token.encode()).decode()


def save_tokens(
    provider: str,
    access_token: str,
    refresh_token: str | None,
    expires_at: datetime | None,
) -> None:
    now = _utc_now()
    with session_scope() as session:
        row = session.get(OAuthToken, provider)
        if row:
            row.access_token_enc = _encrypt(access_token)
            row.refresh_token_enc = _encrypt(refresh_token) if refresh_token else None
            row.expires_at = expires_at
            row.updated_at = now
        else:
            session.add(
                OAuthToken(
                    provider=provider,
                    access_token_enc=_encrypt(access_token),
                    refresh_token_enc=_encrypt(refresh_token) if refresh_token else None,
                    expires_at=expires_at,
                    updated_at=now,
                )
            )


def get_tokens(provider: str = "youtube") -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(OAuthToken, provider)
        if not row:
            return None
        return {
            "access_token": _decrypt(row.access_token_enc),
            "refresh_token": _decrypt(row.refresh_token_enc) if row.refresh_token_enc else None,
            "expires_at": row.expires_at,
            "last_import_at": row.last_import_at,
        }


def delete_tokens(provider: str = "youtube") -> bool:
    with session_scope() as session:
        row = session.get(OAuthToken, provider)
        if not row:
            return False
        session.delete(row)
        session.execute(delete(ImportedYtItem))
        return True


def set_last_import(provider: str = "youtube") -> None:
    now = _utc_now()
    with session_scope() as session:
        row = session.get(OAuthToken, provider)
        if row:
            row.last_import_at = now


def is_connected(provider: str = "youtube") -> bool:
    with session_scope() as session:
        return session.get(OAuthToken, provider) is not None


def upsert_imported_items(items: list[dict[str, Any]]) -> int:
    if not items:
        return 0
    now = _utc_now()
    with session_scope() as session:
        for item in items:
            vid = item["video_id"]
            existing = session.get(ImportedYtItem, vid)
            meta = item.get("raw_meta")
            payload = json.dumps(meta, ensure_ascii=False) if meta else None
            if existing:
                existing.source = item.get("source", existing.source)
                existing.title = item.get("title")
                existing.channel_id = item.get("channel_id")
                existing.channel_title = item.get("channel_title")
                existing.raw_meta_json = payload
                existing.imported_at = now
            else:
                session.add(
                    ImportedYtItem(
                        video_id=vid,
                        source=item.get("source", "unknown"),
                        title=item.get("title"),
                        channel_id=item.get("channel_id"),
                        channel_title=item.get("channel_title"),
                        raw_meta_json=payload,
                        imported_at=now,
                    )
                )
        return len(items)


def list_imported_by_source(source: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    with session_scope() as session:
        stmt = select(ImportedYtItem).order_by(ImportedYtItem.imported_at.desc()).limit(limit)
        if source:
            stmt = stmt.where(ImportedYtItem.source == source)
        rows = session.scalars(stmt).all()
        return [
            {
                "video_id": r.video_id,
                "source": r.source,
                "title": r.title,
                "channel_id": r.channel_id,
                "channel_title": r.channel_title,
            }
            for r in rows
        ]
