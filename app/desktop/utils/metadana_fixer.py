import os
import base64
from typing import Dict, Any, Optional
from io import BytesIO

from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover


def get_audio_metadata(
    file_path: str,
    include_cover_data: bool = False,
    save_cover_path: Optional[str] = None,
) -> Dict[str, Any]:

    metadata: Dict[str, Any] = {
        "title": os.path.splitext(os.path.basename(file_path))[0],
        "artist": "Unknown Artist",
        "album": "",
        "duration": 0,
        "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
        "has_cover": False,
        "cover_mime": None,
        "cover_size": 0,
        "cover_dimensions": None,
        "format": os.path.splitext(file_path)[1].lower().replace(".", ""),
    }

    if not os.path.exists(file_path):
        return metadata

    ext = metadata["format"]

    try:
        if ext == "mp3":
            return _get_mp3_metadata(file_path, include_cover_data, save_cover_path, metadata)
        if ext in ("mp4", "m4a"):
            return _get_mp4_metadata(file_path, include_cover_data, save_cover_path, metadata)
        return metadata
    except Exception:
        return metadata


def _get_mp3_metadata(
    file_path: str,
    include_cover_data: bool,
    save_cover_path: Optional[str],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:

    try:
        try:
            audio = MP3(file_path, ID3=EasyID3)
            tags = audio.tags

            if tags:
                metadata["title"] = tags.get("title", [metadata["title"]])[0]
                metadata["artist"] = tags.get("artist", [metadata["artist"]])[0]
                metadata["album"] = tags.get("album", [""])[0]

            if audio.info and hasattr(audio.info, "length"):
                metadata["duration"] = int(audio.info.length)

        except Exception:
            pass

        try:
            id3 = ID3(file_path)
            covers = []

            for apic in id3.getall("APIC"):
                if apic.data and len(apic.data) > 1024:
                    covers.append(
                        {
                            "data": apic.data,
                            "mime": getattr(apic, "mime", "image/jpeg"),
                            "size": len(apic.data),
                        }
                    )

            covers.sort(key=lambda x: x["size"], reverse=True)

            if covers:
                best = covers[0]
                metadata["has_cover"] = True
                metadata["cover_mime"] = best["mime"]
                metadata["cover_size"] = best["size"]

                try:
                    from PIL import Image

                    img = Image.open(BytesIO(best["data"]))
                    metadata["cover_dimensions"] = img.size
                except Exception:
                    pass

                if save_cover_path:
                    ext = ".jpg"
                    if "png" in best["mime"].lower():
                        ext = ".png"

                    if not save_cover_path.lower().endswith((".jpg", ".jpeg", ".png")):
                        save_cover_path = save_cover_path + ext

                    os.makedirs(os.path.dirname(save_cover_path), exist_ok=True)
                    with open(save_cover_path, "wb") as f:
                        f.write(best["data"])
                    metadata["cover_path"] = save_cover_path

                if include_cover_data:
                    metadata["cover_base64"] = base64.b64encode(best["data"]).decode("ascii")

            for tcon in id3.getall("TCON"):
                text = tcon.text[0] if isinstance(tcon.text, list) else tcon.text
                if isinstance(text, str) and len(text) == 11 and text.isalnum():
                    metadata["videoId"] = text
                    break

        except ID3NoHeaderError:
            pass

    except Exception:
        pass

    _determine_fix_needed(metadata)
    return metadata


def _get_mp4_metadata(
    file_path: str,
    include_cover_data: bool,
    save_cover_path: Optional[str],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:

    try:
        audio = MP4(file_path)

        if "\xa9nam" in audio:
            metadata["title"] = audio["\xa9nam"][0]
        if "\xa9ART" in audio:
            metadata["artist"] = audio["\xa9ART"][0]
        if "\xa9alb" in audio:
            metadata["album"] = audio["\xa9alb"][0]

        if hasattr(audio.info, "length"):
            metadata["duration"] = int(audio.info.length)

        if "covr" in audio and audio["covr"]:
            cover = audio["covr"][0]
            metadata["has_cover"] = True
            metadata["cover_size"] = len(cover)

            if cover.imageformat == MP4Cover.FORMAT_PNG:
                metadata["cover_mime"] = "image/png"
            else:
                metadata["cover_mime"] = "image/jpeg"

            try:
                from PIL import Image

                img = Image.open(BytesIO(cover))
                metadata["cover_dimensions"] = img.size
            except Exception:
                pass

            if save_cover_path:
                ext = ".png" if cover.imageformat == MP4Cover.FORMAT_PNG else ".jpg"
                if not save_cover_path.lower().endswith((".jpg", ".jpeg", ".png")):
                    save_cover_path = save_cover_path + ext

                os.makedirs(os.path.dirname(save_cover_path), exist_ok=True)
                with open(save_cover_path, "wb") as f:
                    f.write(cover)
                metadata["cover_path"] = save_cover_path

            if include_cover_data:
                metadata["cover_base64"] = base64.b64encode(cover).decode("ascii")

        if "\xa9cmt" in audio:
            comment = audio["\xa9cmt"][0]
            if len(comment) == 11 and comment.isalnum():
                metadata["videoId"] = comment

    except Exception:
        pass

    _determine_fix_needed(metadata)
    return metadata


def _determine_fix_needed(metadata: Dict[str, Any]) -> None:
    metadata["needs_fix"] = (
        not metadata.get("artist")
        or metadata.get("artist") in ("Unknown", "Unknown Artist")
        or not metadata.get("title")
        or not metadata.get("has_cover")
    )
