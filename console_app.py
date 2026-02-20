import argparse
import asyncio
from app.logic.console.handle_song import download_song_core


async def main(yt_url: str, song_id: str):
    from urllib.parse import urlparse, parse_qs

    def extract_video_id(url):
        parsed = urlparse(url)
        if "youtube.com" in parsed.netloc:
            return parse_qs(parsed.query).get("v", [None])[0]
        elif "youtu.be" in parsed.netloc:
            return parsed.path.lstrip('/')
        return None

    video_id = extract_video_id(yt_url)
    if not video_id:
        print("❌ Invalid YouTube URL.")
        return

    print(f"📥 Downloading MP3 for video ID: {video_id}")
    result = download_song_core(video_id, song_id)

    if result["success"]:
        print(f"✅ File saved as: {result['file_path']}")
    else:
        print(f"❌ Error: {result['error']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--id", required=True)
    args = parser.parse_args()

    asyncio.run(main(args.url, args.id))
