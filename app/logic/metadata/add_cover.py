"""
add_cover.py - Module for embedding cover art into audio files
"""

from mutagen.id3 import ID3, ID3NoHeaderError, APIC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover 
from typing import Optional
import os
import requests
import imghdr


def embed_image_mp3(
    file_path: str,
    image_url: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    mime: Optional[str] = None
) -> bool:
    """
    Embed cover art into MP3 file.
    
    Args:
        file_path: Path to the MP3 file
        image_url: URL of the image to embed (optional)
        image_bytes: Raw image bytes (optional)
        mime: MIME type of the image (optional, will be auto-detected)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return False

        if image_url is None and image_bytes is None:
            print("❌ Must provide either image_url or image_bytes")
            return False

        # Fetch if URL given
        if image_url is not None:
            try:
                resp = requests.get(image_url, timeout=15)
                resp.raise_for_status()
                image_bytes = resp.content
                # Try to get mime from headers
                mime = mime or resp.headers.get('content-type')
            except Exception as e:
                print(f"❌ Failed to download image from {image_url}: {e}")
                return False

        # Try to detect mime if still None
        if mime is None:
            img_type = imghdr.what(None, h=image_bytes)
            if img_type == 'jpeg' or img_type == 'jpg':
                mime = 'image/jpeg'
            elif img_type == 'png':
                mime = 'image/png'
            else:
                # fallback
                mime = 'image/jpeg'

        # Load or create ID3 tags
        try:
            tags = ID3(file_path)
        except ID3NoHeaderError:
            # File has no ID3 tags, create them
            tags = ID3()
            try:
                tags.save(file_path, v2_version=3)
                tags = ID3(file_path)
            except Exception:
                # If that fails, try using MP3 class
                try:
                    audio = MP3(file_path)
                    audio.add_tags()
                    audio.save()
                    tags = ID3(file_path)
                except Exception as e:
                    print(f"❌ Failed to add ID3 tags to {file_path}: {e}")
                    return False

        # Remove existing cover art
        try:
            tags.delall('APIC')
        except Exception:
            # If delall doesn't work, manually remove APIC frames
            for key in list(tags.keys()):
                if key.startswith('APIC'):
                    del tags[key]

        # Add new cover art
        apic = APIC(
            encoding=3,         # UTF-8
            mime=mime,
            type=3,             # Front cover
            desc='Cover',
            data=image_bytes
        )
        tags.add(apic)

        # Save tags
        tags.save(file_path, v2_version=3)
        print(f"✅ Successfully embedded cover art into {file_path}")
        return True

    except Exception as e:
        print(f"❌ Error embedding image into MP3 {file_path}: {e}")
        return False


def embed_image_mp4(
    file_path: str, 
    image_url: Optional[str] = None,
    image_bytes: Optional[bytes] = None
) -> bool:
    """
    Embed cover art into MP4/M4A file.
    
    Args:
        file_path: Path to the MP4 file
        image_url: URL of the image to embed (optional)
        image_bytes: Raw image bytes (optional)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return False

        if image_url is None and image_bytes is None:
            print("❌ Must provide either image_url or image_bytes")
            return False

        # Fetch if URL given
        if image_url is not None:
            try:
                resp = requests.get(image_url, timeout=15)
                resp.raise_for_status()
                image_bytes = resp.content
            except Exception as e:
                print(f"❌ Failed to download image from {image_url}: {e}")
                return False

        # Load MP4 file
        mp4 = MP4(file_path)
        
        # Detect image format
        img_type = imghdr.what(None, h=image_bytes)
        if img_type == 'png':
            imageformat = MP4Cover.FORMAT_PNG
        else:
            imageformat = MP4Cover.FORMAT_JPEG
        
        # Create and add cover
        cover = MP4Cover(image_bytes, imageformat=imageformat)
        mp4['covr'] = [cover]
        mp4.save()
        
        print(f"✅ Successfully embedded cover art into {file_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error embedding image into MP4 {file_path}: {e}")
        return False