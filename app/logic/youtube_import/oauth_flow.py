from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from app.db import oauth_repository

_pending_states: dict[str, datetime] = {}
SCOPES = "https://www.googleapis.com/auth/youtube.readonly"


def _client_config() -> tuple[str, str, str]:
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    redirect_uri = os.environ.get(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8000/auth/youtube/callback",
    ).strip()
    if not client_id or not client_secret:
        raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET required")
    return client_id, client_secret, redirect_uri


def start_auth_url() -> dict[str, str]:
    client_id, _, redirect_uri = _client_config()
    state = secrets.token_urlsafe(16)
    _pending_states[state] = datetime.now(timezone.utc) + timedelta(minutes=10)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {"auth_url": url, "state": state}


def exchange_code(code: str, state: str) -> None:
    expires = _pending_states.pop(state, None)
    if not expires or expires < datetime.now(timezone.utc):
        raise ValueError("Invalid or expired OAuth state")

    client_id, client_secret, redirect_uri = _client_config()
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    access = data["access_token"]
    refresh = data.get("refresh_token")
    expires_in = int(data.get("expires_in", 3600))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    oauth_repository.save_tokens("youtube", access, refresh, expires_at)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _refresh_if_needed(tokens: dict[str, Any]) -> str:
    access = tokens["access_token"]
    expires_at = _as_utc(tokens.get("expires_at"))
    if expires_at and expires_at > datetime.now(timezone.utc) + timedelta(minutes=2):
        return access

    refresh = tokens.get("refresh_token")
    if not refresh:
        return access

    client_id, client_secret, _ = _client_config()
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    access = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    oauth_repository.save_tokens("youtube", access, refresh, expires_at)
    return access


def get_authenticated_headers() -> dict[str, str]:
    tokens = oauth_repository.get_tokens("youtube")
    if not tokens:
        raise RuntimeError("YouTube account not connected")
    access = _refresh_if_needed(tokens)
    return {"Authorization": f"Bearer {access}"}
