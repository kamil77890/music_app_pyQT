import os
from time import sleep
from yt_dlp import YoutubeDL
from app.config.stałe import Parameters
from app.logic.metadata.add_metadata import add_metadata

download_dir = Parameters.get_download_dir()


def download_song_core(videoId: str, id: str, format: str = "mp3") -> dict:
    output_file = os.path.join(download_dir, f'{id}.{format}')
    url = f"https://www.youtube.com/watch?v={videoId}"

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(download_dir, f'{id}.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',  # Use "320" for highest MP3 bitrate
        }],
        'ffmpeg_location': r'C:\ffmpeg\bin',  # Path to ffmpeg
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        },
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        sleep(2.5)
        add_metadata(output_file, format, videoId)
        sleep(1)

        if os.path.exists(output_file):
            return {"success": True, "file_path": output_file}
        else:
            return {"success": False, "error": "File not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}
