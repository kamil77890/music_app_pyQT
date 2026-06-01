import pytest
from app.logic.color_extractor import extract_color_palette
import os


def test_extract_color_palette_returns_dict():
    """Test that extract_color_palette returns proper structure"""
    # Create a simple test image (PIL can create in-memory)
    from PIL import Image
    import tempfile
    
    # Create a red image (255, 0, 0)
    img = Image.new('RGB', (100, 100), color=(255, 0, 0))
    
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        img.save(tmp.name)
        tmp_path = tmp.name
    
    try:
        result = extract_color_palette(tmp_path)
        
        assert isinstance(result, dict)
        assert "dominantColor" in result
        assert "colorPalette" in result
        assert isinstance(result["dominantColor"], str)
        assert isinstance(result["colorPalette"], list)
        assert len(result["colorPalette"]) == 3
        
        # Check hex format
        for color in result["colorPalette"]:
            assert color.startswith("#")
            assert len(color) == 7  # #RRGGBB
    finally:
        os.unlink(tmp_path)


def test_extract_color_palette_handles_missing_file():
    """Test that missing file returns default colors"""
    result = extract_color_palette("/nonexistent/path/image.jpg")
    
    assert isinstance(result, dict)
    assert "dominantColor" in result
    assert "colorPalette" in result
    # Should have default fallback colors
    assert result["colorPalette"] is not None


def test_extract_color_palette_hex_format():
    """Test that hex colors are properly formatted"""
    from PIL import Image
    import tempfile
    
    img = Image.new('RGB', (50, 50), color=(100, 150, 200))
    
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        img.save(tmp.name)
        tmp_path = tmp.name
    
    try:
        result = extract_color_palette(tmp_path)
        
        for color in result["colorPalette"]:
            # Verify hex format: #RRGGBB
            assert color.startswith("#")
            assert len(color) == 7
            int(color[1:], 16)  # Should not raise ValueError
    finally:
        os.unlink(tmp_path)
