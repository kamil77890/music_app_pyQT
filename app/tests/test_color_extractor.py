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
