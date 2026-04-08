import os
import json
import logging
import urllib.request
import srt
from yt_dlp import YoutubeDL
from app.config.stałe import Parameters
from app.logic.downloader.retries import safe_get_song_by_string

log = logging.getLogger(__name__)
subtitles_dir = Parameters.get_download_dir()


def get_subtitles_srt(video_id: str, lang="en") -> str:
    """
    Download subtitles for a video and return as raw SRT string.
    Does NOT save to file - returns content directly.

    Returns: SRT content string
    Raises: FileNotFoundError if no subtitles available
    """
    log.info("Lyrics download start: videoId=%s lang=%s", video_id, lang)

    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [lang],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            if info is None:
                log.warning("Lyrics extract_info returned None: videoId=%s", video_id)
                raise FileNotFoundError(f"No info found for video ID: {video_id}")

            # Get subtitles - check both manual and automatic
            subtitles_data = info.get("subtitles", {}) or {}
            automatic_captions = info.get("automatic_captions", {}) or {}

            # Merge both sources
            all_subs = {**automatic_captions, **subtitles_data}

            if not all_subs:
                log.warning("Lyrics not available: videoId=%s has no subtitles/captions", video_id)
                raise FileNotFoundError(f"No subtitles found for video ID: {video_id}")

            # Find the requested language
            lang_subs = all_subs.get(lang)
            if not lang_subs:
                # Try to find any similar language
                available = list(all_subs.keys())
                log.warning("Lyrics lang %s not found for videoId=%s, available: %s", lang, video_id, available)
                raise FileNotFoundError(f"No '{lang}' subtitles found for video ID: {video_id}. Available: {available}")

            # Find SRT format (prefer vtt or srt, fallback to json3)
            srt_entry = None
            for sub in lang_subs:
                if sub.get("ext") in ("srt", "vtt", "ttml"):
                    srt_entry = sub
                    break

            if not srt_entry:
                # Try json3 and convert
                for sub in lang_subs:
                    if sub.get("ext") == "json3":
                        srt_entry = sub
                        break

            if not srt_entry:
                log.warning("Lyrics: no supported format found for videoId=%s lang=%s, formats: %s",
                           video_id, lang, [s.get("ext") for s in lang_subs])
                raise FileNotFoundError(f"No supported subtitle format for video ID: {video_id}")

            log.info("Lyrics downloading: videoId=%s url=%s", video_id, srt_entry["url"][:100])

            # Download the subtitle file
            with urllib.request.urlopen(srt_entry["url"]) as response:
                raw_content = response.read().decode("utf-8")

            # Convert if needed
            if srt_entry.get("ext") == "json3":
                # Convert YouTube json3 format to SRT
                log.info("Lyrics converting json3 to SRT: videoId=%s", video_id)
                json_data = json.loads(raw_content)
                events = json_data.get("events", [])
                srt_content = ""
                for i, event in enumerate(events, 1):
                    if "segs" not in event or "tStartMs" not in event or "dDurationMs" not in event:
                        continue
                    text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
                    if not text:
                        continue
                    start_ms = event["tStartMs"]
                    duration_ms = event["dDurationMs"]
                    end_ms = start_ms + duration_ms
                    start_srt = _ms_to_srt_time(start_ms)
                    end_srt = _ms_to_srt_time(end_ms)
                    srt_content += f"{i}\n{start_srt} --> {end_srt}\n{text}\n\n"
            elif srt_entry.get("ext") == "vtt":
                # Convert VTT to SRT (simple conversion)
                log.info("Lyrics converting VTT to SRT: videoId=%s", video_id)
                srt_content = raw_content.replace("WEBVTT", "").replace("WEBVTT -", "")
                # VTT uses . for milliseconds, SRT uses ,
                import re
                srt_content = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", srt_content)
            elif srt_entry.get("ext") == "ttml":
                # Convert TTML to SRT
                log.info("Lyrics converting TTML to SRT: videoId=%s", video_id)
                srt_content = _convert_ttml_to_srt(raw_content)
            else:
                # Already SRT
                srt_content = raw_content

            log.info("Lyrics downloaded successfully: videoId=%s size=%d bytes", video_id, len(srt_content))
            return srt_content

    except FileNotFoundError:
        raise
    except Exception as exc:
        log.error("Lyrics download error: videoId=%s error=%s", video_id, exc)
        raise FileNotFoundError(f"Failed to download subtitles for {video_id}: {exc}")


def _ms_to_srt_time(ms: int) -> str:
    """Convert milliseconds to SRT time format (HH:MM:SS,mmm)."""
    total_seconds = ms // 1000
    milliseconds = ms % 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _convert_ttml_to_srt(ttml_content: str) -> str:
    """Convert TTML subtitle format to SRT."""
    import re
    from xml.etree import ElementTree as ET

    try:
        root = ET.fromstring(ttml_content)
        # Find all <p> elements (TTML paragraphs)
        ns = {"ttml": "http://www.w3.org/ns/ttml"}

        # Try with namespace first, then without
        paragraphs = root.findall(".//ttml:p", ns)
        if not paragraphs:
            paragraphs = root.findall(".//p")

        srt_content = ""
        for i, p in enumerate(paragraphs, 1):
            begin = p.get("begin", "")
            end = p.get("end", "")

            # TTML time formats: "12.345s" or "00:00:12.345" or "00:00:12,345"
            def convert_time(time_str: str) -> str:
                if not time_str:
                    return "00:00:00,000"
                # Remove trailing 's' if present
                time_str = time_str.rstrip("s")
                # Handle different formats
                if ":" in time_str:
                    # HH:MM:SS.mmm or HH:MM:SS,mmm
                    parts = time_str.replace(",", ".").split(":")
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    sec_parts = parts[2].split(".")
                    seconds = int(sec_parts[0])
                    ms = int(sec_parts[1].ljust(3, "0")[:3]) if len(sec_parts) > 1 else 0
                else:
                    # Seconds only
                    total_sec = float(time_str)
                    hours = int(total_sec // 3600)
                    minutes = int((total_sec % 3600) // 60)
                    seconds = int(total_sec % 60)
                    ms = int((total_sec % 1) * 1000)
                return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"

            begin_srt = convert_time(begin)
            end_srt = convert_time(end)

            # Get text content, handling nested <span> elements
            text_parts = []
            for child in p:
                if child.text:
                    text_parts.append(child.text.strip())
            if not text_parts and p.text:
                text_parts.append(p.text.strip())

            text = " ".join(text_parts).strip()
            if text:
                srt_content += f"{i}\n{begin_srt} --> {end_srt}\n{text}\n\n"

        if not srt_content:
            log.warning("TTML conversion produced empty SRT")
            return ""

        return srt_content

    except ET.ParseError as e:
        log.error("TTML parse error: %s", e)
        return ""


def get_subtitles_as_txt(video_id: str, lang="en") -> str:
    log.info("Lyrics generation start (API): videoId=%s lang=%s", video_id, lang)
    song_data = safe_get_song_by_string(video_id)
    snippet = song_data[0]['snippet']
    title = sanitize_filename(snippet['title'])
    log.info("Lyrics resolved title: videoId=%s title=%s", video_id, title)

    base_path = os.path.join(subtitles_dir, title)
    srt_path = f"{base_path}.{lang}.srt"
    txt_path = f"{base_path}.txt"

    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [lang],
        "subtitlesformat": "srt",
        "outtmpl": base_path + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

    if not os.path.exists(srt_path):
        log.warning("Lyrics not found (API): videoId=%s lang=%s", video_id, lang)
        raise FileNotFoundError(f"No subtitles found for video ID: {video_id}")

    with open(srt_path, "r", encoding="utf-8") as f:
        subtitles = list(srt.parse(f.read()))
        full_text = srt.compose(subtitles)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    log.info("Lyrics generated successfully (API): videoId=%s txt_path=%s", video_id, txt_path)
    return txt_path
