"""
add_cover.py - Module for embedding cover art into audio files
"""

from mutagen.id3 import ID3, ID3NoHeaderError, APIC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover 
from typing import Optional
import os
import requests

# USUNIĘTO: import imghdr

def get_image_type(image_bytes: bytes) -> Optional[str]:
    """
    Zastępuje usunięty moduł imghdr. 
    Rozpoznaje typ obrazu na podstawie nagłówka (magic bytes).
    """
    if image_bytes.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if image_bytes.startswith(b'GIF87a') or image_bytes.startswith(b'GIF89a'):
        return 'gif'
    return None

def embed_image_mp3(
    file_path: str,
    image_url: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    mime: Optional[str] = None
) -> bool:
    try:
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return False

        if image_url is None and image_bytes is None:
            print("❌ Must provide either image_url or image_bytes")
            return False

        if image_url is not None:
            try:
                resp = requests.get(image_url, timeout=15)
                resp.raise_for_status()
                image_bytes = resp.content
                mime = mime or resp.headers.get('content-type')
            except Exception as e:
                print(f"❌ Failed to download image from {image_url}: {e}")
                return False

        # ZMIANA: Użycie nowej funkcji zamiast imghdr.what
        if mime is None and image_bytes:
            img_type = get_image_type(image_bytes)
            if img_type in ['jpeg', 'jpg']:
                mime = 'image/jpeg'
            elif img_type == 'png':
                mime = 'image/png'
            else:
                mime = 'image/jpeg' # fallback

        try:
            tags = ID3(file_path)
        except ID3NoHeaderError:
            tags = ID3()
            try:
                tags.save(file_path, v2_version=3)
                tags = ID3(file_path)
            except Exception:
                try:
                    audio = MP3(file_path)
                    audio.add_tags()
                    audio.save()
                    tags = ID3(file_path)
                except Exception as e:
                    print(f"❌ Failed to add ID3 tags to {file_path}: {e}")
                    return False

        try:
            tags.delall('APIC')
        except Exception:
            for key in list(tags.keys()):
                if key.startswith('APIC'):
                    del tags[key]

        apic = APIC(
            encoding=3,
            mime=mime,
            type=3,
            desc='Cover',
            data=image_bytes
        )
        tags.add(apic)
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
    try:
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return False

        if image_url is None and image_bytes is None:
            print("❌ Must provide either image_url or image_bytes")
            return False

        if image_url is not None:
            try:
                resp = requests.get(image_url, timeout=15)
                resp.raise_for_status()
                image_bytes = resp.content
            except Exception as e:
                print(f"❌ Failed to download image from {image_url}: {e}")
                return False

        mp4 = MP4(file_path)
        
        # ZMIANA: Użycie nowej funkcji zamiast imghdr.what
        img_type = get_image_type(image_bytes) if image_bytes else None
        if img_type == 'png':
            imageformat = MP4Cover.FORMAT_PNG
        else:
            imageformat = MP4Cover.FORMAT_JPEG
        
        cover = MP4Cover(image_bytes, imageformat=imageformat)
        mp4['covr'] = [cover]
        mp4.save()
        
        print(f"✅ Successfully embedded cover art into {file_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error embedding image into MP4 {file_path}: {e}")
        return False