from PIL import Image
import colorsys
from typing import Optional
import logging

log = logging.getLogger(__name__)

# Default fallback colors (music theme)
DEFAULT_PALETTE = {
    "dominantColor": "#808080",
    "colorPalette": ["#808080", "#505050", "#1a1a1a"]
}


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB tuple to hex string."""
    return f"#{r:02x}{g:02x}{b:02x}".upper()


def extract_dominant_colors(image_path: str, num_colors: int = 3) -> list[tuple[int, int, int]]:
    """
    Extract dominant colors from an image.
    Returns list of RGB tuples, sorted from brightest to darkest.
    """
    try:
        img = Image.open(image_path)
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize for faster processing
        img.thumbnail((150, 150))
        
        # Get all pixels
        pixels = list(img.getdata())
        
        if not pixels:
            return []
        
        # Simple dominant color extraction: cluster by brightness
        # Sort pixels by brightness (HSV Value)
        def brightness(rgb):
            r, g, b = rgb
            return colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)[2]
        
        sorted_pixels = sorted(set(pixels), key=brightness, reverse=True)
        
        # Take top unique colors, spaced by brightness
        dominant_colors = []
        if sorted_pixels:
            dominant_colors.append(sorted_pixels[0])  # Brightest
            
            if len(sorted_pixels) > 1:
                # Find darker shade
                mid_idx = len(sorted_pixels) // 2
                dominant_colors.append(sorted_pixels[mid_idx])
            
            if len(sorted_pixels) > 2:
                # Find darkest shade
                dominant_colors.append(sorted_pixels[-1])
        
        # Pad with darkest if not enough colors
        while len(dominant_colors) < num_colors:
            dominant_colors.append((0, 0, 0))
        
        return dominant_colors[:num_colors]
    
    except Exception as e:
        log.error(f"Error extracting colors from {image_path}: {e}")
        return []


def extract_color_palette(image_path: Optional[str]) -> dict:
    """
    Extract color palette from image: dominant + secondary + tertiary.
    Returns dict with dominantColor (str) and colorPalette (list of 3 hex strings).
    Falls back to default colors if image cannot be processed.
    """
    if not image_path:
        return DEFAULT_PALETTE
    
    colors = extract_dominant_colors(image_path, num_colors=3)
    
    if not colors:
        return DEFAULT_PALETTE
    
    hex_colors = [rgb_to_hex(r, g, b) for r, g, b in colors]
    
    return {
        "dominantColor": hex_colors[0],
        "colorPalette": hex_colors
    }
