# Cover Color Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace gray fallback-heavy cover color extraction with deterministic, representative accent color extraction and palette generation.

**Architecture:** Keep the public contract in `extract_color_palette()` unchanged: it returns only `dominantColor` and `colorPalette`. Move the smarter filtering, quantization, accent selection, darker palette generation, and fallback logging into `app/logic/color_extractor.py`; update `/api/songs` to enrich songs using the same extractor already used by `/playlists/all-songs`.

**Tech Stack:** Python 3.12, Pillow, FastAPI, pytest.

---

## File Structure

- Modify: `app/logic/color_extractor.py`
  - Responsibility: open local/remote/base64 covers, extract one accent color, generate a 3-color palette, and log fallback reasons.
- Modify: `app/endpoints/songs.py`
  - Responsibility: include `dominantColor` and `colorPalette` in `/api/songs` entries when a cover exists, preserving existing fields.
- Modify: `app/tests/test_color_extractor.py`
  - Responsibility: unit-test color extraction behavior and fallback cases.
- Modify: `app/tests/test_color_integration.py`
  - Responsibility: verify song-list responses include compatible color fields.

---

### Task 1: Add Failing Extractor Tests

**Files:**
- Modify: `app/tests/test_color_extractor.py`

- [ ] **Step 1: Replace `app/tests/test_color_extractor.py` with focused behavior tests**

```python
import os
import tempfile

from PIL import Image, ImageDraw

from app.logic.color_extractor import DEFAULT_PALETTE, extract_color_palette


def _save_temp_image(img: Image.Image) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    img.save(tmp.name)
    return tmp.name


def _is_gray(hex_color: str) -> bool:
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return max(r, g, b) - min(r, g, b) <= 8


def _assert_palette_shape(result: dict) -> None:
    assert set(result) == {"dominantColor", "colorPalette"}
    assert isinstance(result["dominantColor"], str)
    assert result["dominantColor"].startswith("#")
    assert len(result["dominantColor"]) == 7
    assert isinstance(result["colorPalette"], list)
    assert len(result["colorPalette"]) == 3
    for color in result["colorPalette"]:
        assert color.startswith("#")
        assert len(color) == 7
        int(color[1:], 16)


def test_colorful_cover_returns_non_gray_dominant_color():
    img = Image.new("RGB", (120, 120), color=(30, 120, 255))
    path = _save_temp_image(img)

    try:
        result = extract_color_palette(path)

        _assert_palette_shape(result)
        assert result["dominantColor"] != DEFAULT_PALETTE["dominantColor"]
        assert not _is_gray(result["dominantColor"])
    finally:
        os.unlink(path)


def test_same_image_returns_same_result():
    img = Image.new("RGB", (120, 120), color=(190, 35, 150))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 119, 20), fill=(15, 15, 15))
    path = _save_temp_image(img)

    try:
        first = extract_color_palette(path)
        second = extract_color_palette(path)

        assert first == second
    finally:
        os.unlink(path)


def test_missing_cover_returns_gray_fallback():
    assert extract_color_palette(None) == DEFAULT_PALETTE
    assert extract_color_palette("") == DEFAULT_PALETTE
    assert extract_color_palette("/nonexistent/path/image.jpg") == DEFAULT_PALETTE


def test_monochromatic_gray_cover_returns_gray_fallback():
    img = Image.new("RGB", (120, 120), color=(128, 128, 128))
    path = _save_temp_image(img)

    try:
        assert extract_color_palette(path) == DEFAULT_PALETTE
    finally:
        os.unlink(path)


def test_black_letterbox_bars_do_not_dominate_colorful_center():
    img = Image.new("RGB", (160, 160), color=(5, 5, 5))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 45, 159, 115), fill=(20, 185, 90))
    path = _save_temp_image(img)

    try:
        result = extract_color_palette(path)
        dominant = result["dominantColor"]
        r = int(dominant[1:3], 16)
        g = int(dominant[3:5], 16)
        b = int(dominant[5:7], 16)

        _assert_palette_shape(result)
        assert dominant != DEFAULT_PALETTE["dominantColor"]
        assert g > r
        assert g > b
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run extractor tests and verify they fail on current implementation**

Run: `pytest app/tests/test_color_extractor.py -v`

Expected: at least `test_monochromatic_gray_cover_returns_gray_fallback` fails because the current implementation returns image-derived gray variants instead of the fallback; other tests may fail depending on brightness ordering.

---

### Task 2: Implement Smart Color Extraction

**Files:**
- Modify: `app/logic/color_extractor.py`
- Test: `app/tests/test_color_extractor.py`

- [ ] **Step 1: Replace `app/logic/color_extractor.py` with deterministic extractor implementation**

```python
import base64
import colorsys
from collections import defaultdict
from io import BytesIO
import logging
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image, UnidentifiedImageError

log = logging.getLogger(__name__)

DEFAULT_PALETTE = {
    "dominantColor": "#808080",
    "colorPalette": ["#808080", "#505050", "#1a1a1a"],
}

MAX_IMAGE_SIZE = (160, 160)
MIN_ALPHA = 128
MIN_BRIGHTNESS = 20
MAX_BRIGHTNESS = 235
MIN_SATURATION = 0.18
QUANTIZATION_STEP = 24


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}".upper()


def _fallback(reason: str, image_path: Optional[str] = None) -> dict:
    log.info("Color extraction fallback: fallback_reason=%s cover=%r", reason, image_path)
    return DEFAULT_PALETTE.copy()


def _open_image(image_path: str) -> Image.Image:
    if image_path.startswith(("http://", "https://")):
        try:
            with urlopen(image_path, timeout=8) as response:
                return Image.open(BytesIO(response.read()))
        except (OSError, URLError) as exc:
            raise RuntimeError("cover_download_failed") from exc

    try:
        return Image.open(image_path)
    except (FileNotFoundError, IsADirectoryError):
        raise RuntimeError("invalid_image")
    except (OSError, UnidentifiedImageError):
        try:
            return Image.open(BytesIO(base64.b64decode(image_path, validate=True)))
        except Exception as exc:
            raise RuntimeError("invalid_image") from exc


def _pixel_stats(pixel: tuple[int, int, int, int]) -> tuple[int, int, int, float, float]:
    r, g, b, _ = pixel
    hue, saturation, value = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return r, g, b, saturation, value * 255


def _quantize(value: int) -> int:
    bucket = round(value / QUANTIZATION_STEP) * QUANTIZATION_STEP
    return max(0, min(255, bucket))


def _mid_brightness_score(brightness: float) -> float:
    return 1.0 - min(abs(brightness - 128.0) / 128.0, 1.0)


def _bucket_average(colors: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    total = len(colors)
    return (
        round(sum(color[0] for color in colors) / total),
        round(sum(color[1] for color in colors) / total),
        round(sum(color[2] for color in colors) / total),
    )


def _choose_quantized_accent(pixels: list[tuple[int, int, int, int]]) -> Optional[tuple[int, int, int]]:
    buckets: dict[tuple[int, int, int], list[tuple[int, int, int]]] = defaultdict(list)

    for pixel in pixels:
        if pixel[3] < MIN_ALPHA:
            continue

        r, g, b, saturation, brightness = _pixel_stats(pixel)
        if brightness < MIN_BRIGHTNESS or brightness > MAX_BRIGHTNESS:
            continue
        if saturation < MIN_SATURATION:
            continue

        key = (_quantize(r), _quantize(g), _quantize(b))
        buckets[key].append((r, g, b))

    if not buckets:
        return None

    total = sum(len(colors) for colors in buckets.values())
    best_color = None
    best_score = -1.0

    for colors in buckets.values():
        r, g, b = _bucket_average(colors)
        _, saturation, value = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        brightness = value * 255
        frequency_score = len(colors) / total
        score = frequency_score * 0.65 + saturation * 0.25 + _mid_brightness_score(brightness) * 0.10

        if score > best_score:
            best_score = score
            best_color = (r, g, b)

    return best_color


def _choose_most_saturated_accent(pixels: list[tuple[int, int, int, int]]) -> Optional[tuple[int, int, int]]:
    best = None
    best_score = -1.0

    for pixel in pixels:
        if pixel[3] < MIN_ALPHA:
            continue

        r, g, b, saturation, brightness = _pixel_stats(pixel)
        if brightness < MIN_BRIGHTNESS or brightness > MAX_BRIGHTNESS:
            continue
        if saturation < MIN_SATURATION:
            continue

        score = saturation * 0.8 + _mid_brightness_score(brightness) * 0.2
        if score > best_score:
            best_score = score
            best = (r, g, b)

    return best


def _darken(rgb: tuple[int, int, int], value_multiplier: float) -> tuple[int, int, int]:
    r, g, b = rgb
    hue, saturation, value = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    value = max(0.0, min(1.0, value * value_multiplier))
    saturation = max(0.0, min(1.0, saturation * 0.95))
    rr, gg, bb = colorsys.hsv_to_rgb(hue, saturation, value)
    return round(rr * 255), round(gg * 255), round(bb * 255)


def _build_palette(accent: tuple[int, int, int]) -> list[str]:
    return [
        rgb_to_hex(*accent),
        rgb_to_hex(*_darken(accent, 0.58)),
        rgb_to_hex(*_darken(accent, 0.16)),
    ]


def extract_dominant_colors(image_path: str, num_colors: int = 3) -> list[tuple[int, int, int]]:
    try:
        img = _open_image(image_path).convert("RGBA")
        img.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
        pixels = list(img.getdata())
        accent = _choose_quantized_accent(pixels) or _choose_most_saturated_accent(pixels)
        if not accent:
            return []
        return [accent, _darken(accent, 0.58), _darken(accent, 0.16)][:num_colors]
    except RuntimeError as exc:
        log.info("Color extraction fallback: fallback_reason=%s cover=%r", exc, image_path)
        return []
    except Exception as exc:
        log.warning("Color extraction fallback: fallback_reason=invalid_image cover=%r error=%s", image_path, exc)
        return []


def extract_color_palette(image_path: Optional[str]) -> dict:
    if not image_path:
        return _fallback("no_cover", image_path)

    colors = extract_dominant_colors(image_path, num_colors=3)

    if not colors:
        return _fallback("no_saturated_pixels", image_path)

    hex_colors = [rgb_to_hex(r, g, b) for r, g, b in colors]

    return {
        "dominantColor": hex_colors[0],
        "colorPalette": hex_colors,
    }
```

- [ ] **Step 2: Run extractor tests and verify they pass**

Run: `pytest app/tests/test_color_extractor.py -v`

Expected: all tests in `app/tests/test_color_extractor.py` pass.

- [ ] **Step 3: Commit extractor tests and implementation if requested by user**

Run only if the user requested commits:

```bash
git add app/logic/color_extractor.py app/tests/test_color_extractor.py
git commit -m "fix: extract representative cover colors"
```

---

### Task 3: Enrich `/api/songs` With Compatible Color Fields

**Files:**
- Modify: `app/endpoints/songs.py`
- Modify: `app/tests/test_color_integration.py`

- [ ] **Step 1: Add integration test for `/api/songs` color field compatibility**

Append this test to `app/tests/test_color_integration.py`:

```python
def test_api_songs_includes_color_fields():
    response = client.get("/api/songs")

    assert response.status_code == 200
    data = response.json()
    assert "songs" in data

    if data["songs"]:
        song = data["songs"][0]
        assert "dominantColor" in song
        assert "colorPalette" in song

        if song.get("dominantColor"):
            assert song["dominantColor"].startswith("#")
            assert len(song["dominantColor"]) == 7

        if song.get("colorPalette"):
            assert isinstance(song["colorPalette"], list)
            assert len(song["colorPalette"]) == 3
            for color in song["colorPalette"]:
                assert color.startswith("#")
                assert len(color) == 7
```

- [ ] **Step 2: Run the new integration test and verify it fails when songs exist without color fields**

Run: `pytest app/tests/test_color_integration.py::test_api_songs_includes_color_fields -v`

Expected: in a fixture/environment with downloaded songs, FAIL because `/api/songs` currently omits `dominantColor` and `colorPalette`; if there are no songs, the test may pass vacuously.

- [ ] **Step 3: Modify `/api/songs` to add color fields**

Update `app/endpoints/songs.py` imports and `song_entry` construction:

```python
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.logic.metadata.add_metadata import verify_metadata
from app.logic.color_extractor import extract_color_palette
from app.config.stałe import Parameters
import os
```

Inside the loop, after `meta = verify_metadata(file_path, ext)`, add:

```python
                cover = meta.get("cover", "")
                color_data = extract_color_palette(cover) if cover else {"dominantColor": None, "colorPalette": None}
```

Then build `song_entry` as:

```python
                song_entry = {
                    "filename": filename,
                    "title": meta.get("title", os.path.splitext(filename)[0]),
                    "artist": meta.get("artist", "Unknown Artist"),
                    "videoId": meta.get("videoId", ""),
                    "cover": cover,
                    "dominantColor": color_data.get("dominantColor"),
                    "colorPalette": color_data.get("colorPalette"),
                    "format": ext,
                    "size_bytes": os.path.getsize(file_path),
                }
```

- [ ] **Step 4: Run integration tests**

Run: `pytest app/tests/test_color_integration.py -v`

Expected: all tests in `app/tests/test_color_integration.py` pass.

- [ ] **Step 5: Commit endpoint integration if requested by user**

Run only if the user requested commits:

```bash
git add app/endpoints/songs.py app/tests/test_color_integration.py
git commit -m "fix: include cover colors in songs endpoint"
```

---

### Task 4: Full Verification

**Files:**
- Verify: `app/logic/color_extractor.py`
- Verify: `app/endpoints/songs.py`
- Verify: `app/tests/test_color_extractor.py`
- Verify: `app/tests/test_color_integration.py`

- [ ] **Step 1: Run targeted test suite**

Run: `pytest app/tests/test_color_extractor.py app/tests/test_color_integration.py -v`

Expected: all targeted tests pass.

- [ ] **Step 2: Run full backend tests**

Run: `pytest -q`

Expected: full test suite passes, or any unrelated pre-existing failures are documented with exact failing test names and errors.

- [ ] **Step 3: Inspect changed files**

Run: `git diff -- app/logic/color_extractor.py app/endpoints/songs.py app/tests/test_color_extractor.py app/tests/test_color_integration.py docs/superpowers/specs/2026-06-02-cover-color-extraction-design.md docs/superpowers/plans/2026-06-02-cover-color-extraction.md`

Expected: diff contains only the extractor fix, endpoint color enrichment, tests, and documentation created for this work.

- [ ] **Step 4: Final commit if requested by user and not already committed**

Run only if the user requested commits:

```bash
git add app/logic/color_extractor.py app/endpoints/songs.py app/tests/test_color_extractor.py app/tests/test_color_integration.py docs/superpowers/specs/2026-06-02-cover-color-extraction-design.md docs/superpowers/plans/2026-06-02-cover-color-extraction.md
git commit -m "fix: improve cover color extraction"
```

---

## Self-Review

- Spec coverage: The plan covers representative accent extraction, gray/black/white filtering, saturated-color fallback, final gray fallback, server-side fallback logging, compatible JSON shape, and required tests.
- Placeholder scan: No implementation step relies on unspecified behavior; each code step includes concrete code or exact insertion content.
- Type consistency: `extract_color_palette(image_path: Optional[str]) -> dict` remains the public API and returns `dominantColor` plus `colorPalette` in all non-exception paths.
