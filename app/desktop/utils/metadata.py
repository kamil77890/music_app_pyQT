import os
import base64
from typing import Dict, Any, Optional
from io import BytesIO

from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

try:
    from PIL import Image
except Exception:
    Image = None


def _determine_fix_needed(metadata: Dict[str, Any]) -> None:
    artist = metadata.get("artist", "")
    title = metadata.get("title", "")
    has_cover = metadata.get("has_cover", False)
    cover_size = metadata.get("cover_size", 0)

    needs_fix = False
    if not artist or artist in ("", "Unknown Artist", "Unknown"):
        needs_fix = True
    if not title or title.startswith("Unknown"):
        needs_fix = True
    if not has_cover or cover_size < 1024:
        needs_fix = True

    metadata["needs_fix"] = needs_fix


def _read_mp3(file_path: str, metadata: Dict[str, Any], include_cover_data: bool, save_cover_path: Optional[str]) -> Dict[str, Any]:
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
            # collect APIC frames
            for apic in id3.getall("APIC"):
                if getattr(apic, "data", None) and len(apic.data) > 1024:
                    covers.append({
                        "data": apic.data,
                        "mime": getattr(apic, "mime", "image/jpeg"),
                        "size": len(apic.data)
                    })

            # fallback: other frames that may contain image-like binary
            for key in list(id3.keys()):
                if key.startswith("APIC") and hasattr(id3[key], "data"):
                    frame = id3[key]
                    if getattr(frame, "data", None) and len(frame.data) > 1024:
                        covers.append({
                            "data": frame.data,
                            "mime": getattr(frame, "mime", "image/jpeg"),
                            "size": len(frame.data)
                        })

            covers.sort(key=lambda x: x["size"], reverse=True)
            if covers:
                best = covers[0]
                metadata["has_cover"] = True
                metadata["cover_mime"] = best.get("mime")
                metadata["cover_size"] = best.get("size", 0)

                if Image is not None:
                    try:
                        img = Image.open(BytesIO(best["data"]))
                        metadata["cover_dimensions"] = img.size
                    except Exception:
                        pass

                if save_cover_path:
                    try:
                        ext = ".jpg"
                        mime = (best.get("mime") or "").lower()
                        if "png" in mime:
                            ext = ".png"
                        if not save_cover_path.lower().endswith((".jpg", ".jpeg", ".png")):
                            save_path = save_cover_path + ext
                        else:
                            save_path = save_cover_path
                        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
                        with open(save_path, "wb") as fh:
                            fh.write(best["data"])
                        metadata["cover_path"] = save_path
                    except Exception:
                        pass

                if include_cover_data:
                    try:
                        metadata["cover_base64"] = base64.b64encode(best["data"]).decode("ascii")
                    except Exception:
                        pass

            # try to find videoId in TCON or other frames
            try:
                tcons = id3.getall("TCON")
                if tcons:
                    txt = getattr(tcons[0], "text", None)
                    if isinstance(txt, (list, tuple)) and len(txt) > 0:
                        candidate = str(txt[0])
                        if len(candidate) == 11:
                            metadata["videoId"] = candidate
                    elif isinstance(txt, str) and len(txt) == 11:
                        metadata["videoId"] = txt
            except Exception:
                pass

        except ID3NoHeaderError:
            pass
        except Exception:
            pass

    except Exception:
        pass

    return metadata


def _read_mp4(file_path: str, metadata: Dict[str, Any], include_cover_data: bool, save_cover_path: Optional[str]) -> Dict[str, Any]:
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
            try:
                cover = audio["covr"][0]
                metadata["has_cover"] = True
                metadata["cover_size"] = len(cover)
                if hasattr(cover, "imageformat"):
                    if cover.imageformat == MP4Cover.FORMAT_PNG:
                        metadata["cover_mime"] = "image/png"
                    else:
                        metadata["cover_mime"] = "image/jpeg"
                if Image is not None:
                    try:
                        img = Image.open(BytesIO(cover))
                        metadata["cover_dimensions"] = img.size
                    except Exception:
                        pass

                if save_cover_path:
                    try:
                        ext = ".png" if getattr(cover, "imageformat", None) == MP4Cover.FORMAT_PNG else ".jpg"
                        if not save_cover_path.lower().endswith((".jpg", ".jpeg", ".png")):
                            save_path = save_cover_path + ext
                        else:
                            save_path = save_cover_path
                        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
                        with open(save_path, "wb") as fh:
                            fh.write(cover)
                        metadata["cover_path"] = save_path
                    except Exception:
                        pass

                if include_cover_data:
                    try:
                        metadata["cover_base64"] = base64.b64encode(cover).decode("ascii")
                    except Exception:
                        pass
            except Exception:
                pass

        if "\xa9cmt" in audio:
            try:
                comment = audio["\xa9cmt"][0]
                if isinstance(comment, str) and len(comment) == 11:
                    metadata["videoId"] = comment
            except Exception:
                pass

    except Exception:
        pass

    return metadata


def get_audio_metadata(file_path: str, include_cover_data: bool = False, save_cover_path: Optional[str] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {
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
        result["error"] = "file_not_found"
        _determine_fix_needed(result)
        return result

    ext = result["format"]

    try:
        if ext == "mp3":
            result = _read_mp3(file_path, result, include_cover_data, save_cover_path)
        elif ext in ("mp4", "m4a"):
            result = _read_mp4(file_path, result, include_cover_data, save_cover_path)
    except Exception:
        pass

    _determine_fix_needed(result)
    return result


get_mp3_metadata = get_audio_metadata
