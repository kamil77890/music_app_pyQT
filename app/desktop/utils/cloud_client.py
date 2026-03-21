"""
HTTP client for the local FastAPI server (cloud / B2 endpoints).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.desktop.config import config

log = logging.getLogger(__name__)


def api_base() -> str:
    return str(config.get("api_base_url", "http://127.0.0.1:8001")).rstrip("/")


def fetch_cloud_config() -> Optional[Dict[str, Any]]:
    try:
        with urlopen(f"{api_base()}/cloud/config", timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, json.JSONDecodeError):
        return None


def fetch_cloud_catalog(max_keys: int = 500) -> List[Dict[str, Any]]:
    items, _err = fetch_cloud_catalog_with_error(max_keys)
    return items


def fetch_cloud_catalog_with_error(
    max_keys: int = 500,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Returns (items, error_message). On HTTP 500, error_message is the server detail
    or response body (see server logs / .env B2_*).
    """
    url = f"{api_base()}/cloud/catalog?max_keys={max_keys}"
    try:
        with urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("items", []), None
    except HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        detail = body
        try:
            parsed = json.loads(body)
            detail = parsed.get("detail", body)
        except Exception:
            pass
        msg = f"HTTP {e.code}: {detail or e.reason}"
        log.error("GET /cloud/catalog failed - %s", msg)
        return [], msg
    except (URLError, OSError, json.JSONDecodeError) as e:
        msg = str(e)
        log.error("GET /cloud/catalog failed - %s", msg)
        return [], msg


def post_cloud_upload(directory: Optional[str] = None) -> Dict[str, Any]:
    """Trigger server-side B2 upload. `directory` defaults to server FILEPATH."""
    body = json.dumps({"directory": directory}).encode("utf-8")
    req = Request(
        f"{api_base()}/cloud/upload",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=86400) as resp:
        return json.loads(resp.read().decode("utf-8"))


def public_music_url_for_clipboard() -> str:
    cfg = fetch_cloud_config() or {}
    return (
        cfg.get("public_music_prefix")
        or cfg.get("music_base_url")
        or ""
    )
