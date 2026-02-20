import os
import srt
from yt_dlp import YoutubeDL
from app.config.stałe import Parameters
from app.logic.downloader.retries import safe_get_song_by_string
from app.logic.downloader.filename import sanitize_filename

subtitles_dir = Parameters.get_download_dir()


def get_subtitles_as_txt(video_id: str, lang="en") -> str:
    song_data = safe_get_song_by_string(video_id)
    snippet = song_data[0]['snippet']
    title = sanitize_filename(snippet['title'])

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
        raise FileNotFoundError(f"No subtitles found for video ID: {video_id}")

    with open(srt_path, "r", encoding="utf-8") as f:
        subtitles = list(srt.parse(f.read()))
        full_text = srt.compose(subtitles)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    return txt_path
