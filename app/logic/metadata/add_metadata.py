import os
import asyncio
import base64
from io import BytesIO
from mutagen.id3 import ID3, TIT2, TPE1, TCON, ID3NoHeaderError
from mutagen.mp4 import MP4
from PIL import Image


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
            asyncio.set_event_loop(loop)
    else:
        return loop.run_until_complete(coro)


def _compress_cover(image_data: bytes, max_size: int = 256, quality: int = 80) -> str:
    """
    Compress cover image and return as base64 WebP (much smaller than JPEG).
    Resizes to max_size x max_size and reduces quality.
    """
    try:
        img = Image.open(BytesIO(image_data))
        
        # Convert RGBA to RGB if needed
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        
        # Resize to max_size while keeping aspect ratio
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # Compress to WebP (much smaller than JPEG at same quality)
        buffer = BytesIO()
        img.save(buffer, format='WEBP', quality=quality, method=6)
        compressed_data = buffer.getvalue()
        
        return base64.b64encode(compressed_data).decode('utf-8')
    except Exception as e:
        print(f"⚠️ Cover compression failed: {e}")
        return ""


def extract_cover_from_metadata(file_path: str, format: str) -> str:
    """
    Extract cover image from song metadata, compress it, and return as base64 JPEG.
    Returns empty string if no cover found.
    """
    try:
        image_data = None
        
        if format.lower() == 'mp3':
            id3 = ID3(file_path)
            for key in id3.keys():
                if key.startswith('APIC'):
                    apic = id3[key]
                    image_data = apic.data
                    break
                    
        elif format.lower() in ('mp4', 'm4a'):
            audio = MP4(file_path)
            if 'covr' in audio:
                cover_data = audio['covr'][0]
                if hasattr(cover_data, 'data'):
                    image_data = cover_data.data
                else:
                    image_data = bytes(cover_data)
        
        if image_data:
            return _compress_cover(image_data)
                
    except Exception as e:
        print(f"❌ Error extracting cover: {e}")
    
    return ""


def verify_metadata(file_path: str, format: str) -> dict:
    try:
        cover = ""
        title = "N/A"
        artist = "N/A"
        videoId = "N/A"

        if format.lower() == 'mp3':
            id3 = ID3(file_path)
            title = str(id3.get('TIT2', 'N/A'))
            artist = str(id3.get('TPE1', 'N/A'))
            videoId = str(id3.get('TCON', 'N/A'))
            cover = extract_cover_from_metadata(file_path, format)

        elif format.lower() in ('mp4', 'm4a'):
            audio = MP4(file_path)
            title = audio.get('\xa9nam', ['N/A'])[0]
            artist = audio.get('\xa9ART', ['N/A'])[0]
            videoId = audio.get('\xa9cmt', ['N/A'])[0]
            cover = extract_cover_from_metadata(file_path, format)

        return {
            'title': title,
            'artist': artist,
            'videoId': videoId,
            'cover': cover,
            'has_cover': bool(cover)
        }
    except Exception as e:
        print(f"❌ Error reading metadata: {e}")
        return {}