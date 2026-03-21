"""
Backblaze B2 — S3-compatible API (server-side).
Loads credentials from project root `.env` (B2_KEY_ID, B2_APPLICATION_KEY, BUCKET_NAME, ENDPOINT_URL).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("uvicorn.error")

_AUDIO_EXTS = {".mp3", ".m4a", ".mp4", ".flac", ".wav", ".ogg"}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_b2_env() -> Dict[str, str]:
    """Load B2 credentials from `.env` in project root (values stripped; no BOM)."""
    env_path = _project_root() / ".env"
    creds: Dict[str, str] = {}
    if env_path.exists():
        with open(env_path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                key = k.strip()
                val = v.strip().strip('"').strip("'").replace("\r", "")
                creds[key] = val
    return creds


def get_s3_client_and_bucket():
    import boto3
    from botocore.config import Config

    creds = load_b2_env()
    endpoint = creds.get("ENDPOINT_URL", "").rstrip("/")
    key_id = creds.get("B2_KEY_ID", "")
    secret = creds.get("B2_APPLICATION_KEY", "")
    bucket = creds.get("BUCKET_NAME", "")
    if not all([endpoint, key_id, secret, bucket]):
        raise RuntimeError("Missing B2 env: ENDPOINT_URL, B2_KEY_ID, B2_APPLICATION_KEY, BUCKET_NAME")

    # B2 S3-compatible API: SigV4 + placeholder region avoids SignatureDoesNotMatch on some setups.
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        region_name="us-east-1",
        config=Config(signature_version="s3v4"),
    )
    return client, bucket


def public_url_for_object(bucket: str, endpoint: str, key: str) -> str:
    """
    Build a public HTTPS URL for an object.
    B2 S3 path-style: https://s3.<region>.backblazeb2.com/<bucket>/<key>
    """
    base = endpoint.rstrip("/")
    # Encode key segments for URL
    from urllib.parse import quote

    safe_key = "/".join(quote(part, safe="") for part in key.split("/"))
    return f"{base}/{bucket}/{safe_key}"


def music_directory_public_url() -> str:
    """Base URL prefix for the `music/` folder (for copy-to-clipboard)."""
    creds = load_b2_env()
    bucket = creds.get("BUCKET_NAME", "")
    endpoint = creds.get("ENDPOINT_URL", "")
    if not bucket or not endpoint:
        return ""
    return public_url_for_object(bucket, endpoint, "music/")


def collect_local_audio_files(directory: str) -> List[str]:
    if not directory or not os.path.isdir(directory):
        return []
    out: List[str] = []
    for root, _, files in os.walk(directory):
        for f in files:
            if os.path.splitext(f)[1].lower() in _AUDIO_EXTS:
                out.append(os.path.join(root, f))
    return sorted(out)


def upload_directory_to_b2(
    local_root: str,
    prefix: str = "music",
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[int, int]:
    """
    Upload all audio files under local_root to B2 under prefix/key.
    Returns (uploaded_count, failed_count).
    """
    client, bucket = get_s3_client_and_bucket()
    files = collect_local_audio_files(local_root)
    uploaded = 0
    failed = 0
    local_root = os.path.abspath(local_root)

    for i, filepath in enumerate(files):
        rel = os.path.relpath(filepath, local_root)
        key = f"{prefix}/{rel}".replace("\\", "/")

        if on_progress:
            on_progress(i + 1, len(files), os.path.basename(filepath))

        try:
            try:
                st = os.stat(filepath)
                resp = client.head_object(Bucket=bucket, Key=key)
                if int(resp.get("ContentLength", 0)) == st.st_size:
                    uploaded += 1
                    continue
            except Exception:
                pass
            client.upload_file(filepath, bucket, key)
            uploaded += 1
        except Exception:
            failed += 1

    return uploaded, failed


def list_music_objects(max_keys: int = 1000) -> List[Dict[str, Any]]:
    """List objects under `music/` prefix with public URLs."""
    client, bucket = get_s3_client_and_bucket()

    creds = load_b2_env()
    endpoint = creds.get("ENDPOINT_URL", "")

    out: List[Dict[str, Any]] = []
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix="music/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not any(key.lower().endswith(ext) for ext in _AUDIO_EXTS):
                    continue
                out.append(
                    {
                        "key": key,
                        "size": obj.get("Size", 0),
                        "url": public_url_for_object(bucket, endpoint, key),
                    }
                )
                if len(out) >= max_keys:
                    return out
    except Exception as exc:
        logger.exception(
            "B2 list_objects_v2 bucket=%r prefix=music/ failed: %s", bucket, exc
        )
        raise
    return out


def get_cloud_config() -> Dict[str, Any]:
    creds = load_b2_env()
    bucket = creds.get("BUCKET_NAME", "")
    endpoint = creds.get("ENDPOINT_URL", "")
    base = music_directory_public_url()
    return {
        "bucket": bucket,
        "endpoint": endpoint,
        "music_base_url": base,
        "public_music_prefix": f"{base.rstrip('/')}/" if base else "",
    }
