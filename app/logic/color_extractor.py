from PIL import Image, UnidentifiedImageError
import base64
import colorsys
from io import BytesIO
import logging
from typing import Optional

import requests

log = logging.getLogger(__name__)

# Default fallback colors (music theme)
DEFAULT_PALETTE = {
    "dominantColor": "#808080",
    "colorPalette": ["#808080", "#505050", "#1a1a1a"]
}

THUMBNAIL_SIZE = (160, 160)
CHANNEL_STEP = 24
MIN_ALPHA = 128
MIN_BRIGHTNESS = 20
MAX_BRIGHTNESS = 235
MIN_SATURATION = 0.18
MAX_COVER_BYTES = 5 * 1024 * 1024
REMOTE_CHUNK_SIZE = 64 * 1024
MAX_IMAGE_PIXELS = 25_000_000

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB tuple to hex string."""
    return f"#{r:02x}{g:02x}{b:02x}".upper()


def _fallback(reason: str) -> dict:
    log.warning('fallback_reason="%s"', reason)
    return {
        "dominantColor": DEFAULT_PALETTE["dominantColor"],
        "colorPalette": list(DEFAULT_PALETTE["colorPalette"]),
    }


def _reason_for_load_failure(source_kind: str) -> str:
    return "invalid_image"


def _image_exceeds_size_limit(image: Image.Image) -> bool:
    width, height = image.size
    return width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS


def _base64_payload_may_exceed_limit(payload: str) -> bool:
    return len(payload) * 3 // 4 > MAX_COVER_BYTES


def _read_remote_cover(cover: str) -> Optional[bytes]:
    try:
        with requests.get(cover, timeout=5, stream=True) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_COVER_BYTES:
                return None

            chunks = bytearray()
            for chunk in response.iter_content(chunk_size=REMOTE_CHUNK_SIZE):
                if not chunk:
                    continue
                chunks.extend(chunk)
                if len(chunks) > MAX_COVER_BYTES:
                    return None
            return bytes(chunks)
    except (requests.RequestException, ValueError):
        return None


def _open_cover_image(cover: str) -> tuple[Optional[Image.Image], Optional[str], str]:
    if cover.startswith(("http://", "https://")):
        content = _read_remote_cover(cover)
        if content is None:
            return None, "cover_download_failed", "remote"

        try:
            return Image.open(BytesIO(content)), None, "remote"
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
            return None, "invalid_image", "remote"

    try:
        return Image.open(cover), None, "local"
    except (FileNotFoundError, IsADirectoryError, Image.DecompressionBombError, UnidentifiedImageError, OSError):
        pass

    is_data_url = cover.startswith("data:image/")
    payload = cover.split(",", 1)[1] if is_data_url and "," in cover else cover
    if _base64_payload_may_exceed_limit(payload):
        return None, "invalid_image", "base64" if is_data_url else "local"

    try:
        decoded = base64.b64decode(payload, validate=True)
    except ValueError:
        return None, "invalid_image", "base64" if is_data_url else "local"
    if len(decoded) > MAX_COVER_BYTES:
        return None, "invalid_image", "base64"

    try:
        return Image.open(BytesIO(decoded)), None, "base64"
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        return None, "invalid_image", "base64"


def _bucket_key(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(min(255, (channel // CHANNEL_STEP) * CHANNEL_STEP) for channel in rgb)


def _pixel_stats(rgb: tuple[int, int, int]) -> tuple[float, float]:
    r, g, b = rgb
    _, saturation, _ = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    brightness = 0.299 * r + 0.587 * g + 0.114 * b
    return saturation, brightness


def _extract_accent_rgb(cover: str) -> tuple[Optional[tuple[int, int, int]], Optional[str]]:
    image, reason, source_kind = _open_cover_image(cover)
    if image is None:
        return None, reason

    try:
        if _image_exceeds_size_limit(image):
            return None, "invalid_image"
        image.thumbnail(THUMBNAIL_SIZE)
        image = image.convert("RGBA")
        buckets: dict[tuple[int, int, int], dict[str, float]] = {}
        most_saturated: Optional[tuple[float, tuple[int, int, int]]] = None

        pixels = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
        for r, g, b, alpha in pixels:
            if alpha < MIN_ALPHA:
                continue

            rgb = (r, g, b)
            saturation, brightness = _pixel_stats(rgb)
            if not (MIN_BRIGHTNESS <= brightness <= MAX_BRIGHTNESS and saturation >= MIN_SATURATION):
                continue

            if most_saturated is None or saturation > most_saturated[0]:
                most_saturated = (saturation, rgb)

            key = _bucket_key(rgb)
            bucket = buckets.setdefault(
                key,
                {"count": 0.0, "r": 0.0, "g": 0.0, "b": 0.0, "saturation": 0.0, "brightness": 0.0},
            )
            bucket["count"] += 1
            bucket["r"] += r
            bucket["g"] += g
            bucket["b"] += b
            bucket["saturation"] += saturation
            bucket["brightness"] += brightness / 255.0

        if buckets:
            def score(item: tuple[tuple[int, int, int], dict[str, float]]) -> tuple[float, tuple[int, int, int]]:
                key, bucket = item
                count = bucket["count"]
                saturation = bucket["saturation"] / count
                brightness = bucket["brightness"] / count
                mid_brightness = max(0.0, 1.0 - abs(brightness - 0.55) / 0.55)
                return count * (0.65 + saturation * 0.7 + mid_brightness * 0.5), key

            _, bucket = max(buckets.items(), key=score)
            count = bucket["count"]
            return (round(bucket["r"] / count), round(bucket["g"] / count), round(bucket["b"] / count)), None

        if most_saturated and most_saturated[0] >= MIN_SATURATION:
            return most_saturated[1], None

        return None, "no_saturated_pixels"
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        return None, _reason_for_load_failure(source_kind)


def _shade(rgb: tuple[int, int, int], brightness_multiplier: float) -> tuple[int, int, int]:
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    sr, sg, sb = colorsys.hsv_to_rgb(h, s, max(0.0, min(1.0, v * brightness_multiplier)))
    return round(sr * 255), round(sg * 255), round(sb * 255)


def _palette_from_accent(accent: tuple[int, int, int], num_colors: int = 3) -> list[tuple[int, int, int]]:
    palette = [accent, _shade(accent, 0.55), _shade(accent, 0.18)]
    while len(palette) < num_colors:
        palette.append(palette[-1])
    return palette[:num_colors]


def extract_dominant_colors(image_path: str, num_colors: int = 3) -> list[tuple[int, int, int]]:
    """
    Extract dominant colors from an image.
    Returns list of RGB tuples, sorted from brightest to darkest.
    """
    accent, _ = _extract_accent_rgb(image_path)
    if accent is None:
        return []
    return _palette_from_accent(accent, num_colors)


def extract_color_palette(image_path: Optional[str]) -> dict:
    """
    Extract color palette from image: dominant + secondary + tertiary.
    Returns dict with dominantColor (str) and colorPalette (list of 3 hex strings).
    Falls back to default colors if image cannot be processed.
    """
    if not image_path:
        return _fallback("no_cover")

    accent, reason = _extract_accent_rgb(image_path)
    if accent is None:
        return _fallback(reason or "invalid_image")

    colors = _palette_from_accent(accent, 3)
    
    hex_colors = [rgb_to_hex(r, g, b) for r, g, b in colors]
    
    return {
        "dominantColor": hex_colors[0],
        "colorPalette": hex_colors
    }
