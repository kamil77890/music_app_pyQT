import os
import time
import asyncio
import zipfile
from time import sleep
from typing import Optional
from urllib.parse import urlparse, parse_qs
from fastapi import HTTPException

from app.config.stałe import Parameters
from app.logic.subtitles.handle_subtitles import embed_sylt, parse_srt_to_sync, convert_srt_to_txt
from app.logic.downloader.filename import sanitize_filename
from app.logic.downloader.retries import safe_get_song_by_string
from app.logic.downloader.cleanup import cleanup_temp_files
from app.logic.downloader.yt_dlp_client import download_song_mp3
from app.logic.api_handler.handle_yt import get_video_by_id


def _download_dir() -> str:
    return Parameters.get_download_dir()


FILE_SEARCH_WINDOW_SECONDS = 10


def run_async(coro):
    try:
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
    except Exception as e:
        raise Exception(f"Async error: {e}")


def extract_video_id(video_input: str) -> str:
    if len(video_input) == 11 and all(c.isalnum() or c in '_-' for c in video_input):
        return video_input
    
    try:
        parsed = urlparse(video_input)
        
        if parsed.hostname == 'youtu.be':
            return parsed.path[1:] if parsed.path.startswith('/') else parsed.path
        
        if 'youtube.com' in (parsed.hostname or ''):
            qs = parse_qs(parsed.query)
            if 'v' in qs:
                return qs['v'][0]
        
        return video_input
    except Exception:
        return video_input


def fetch_video_title(video_id: str) -> str:
    try:
        song = run_async(get_video_by_id(video_id))

        if song:
            if hasattr(song, 'snippet'):
                snippet = song.snippet
                if hasattr(snippet, 'title'):
                    return snippet.title
                elif hasattr(snippet, '__getitem__') and 'title' in snippet:
                    return snippet['title']
            elif isinstance(song, dict):
                snippet = song.get('snippet', {})
                return snippet.get('title', video_id)

        return video_id
    
    except Exception as e:
        print(f"Warning: Could not fetch metadata: {e}")
        return video_id


def find_downloaded_file(base_path: str, video_id: str, expected_path: str, format_ext: str) -> Optional[str]:
    if os.path.exists(expected_path):
        return expected_path
    
    try:
        files = [f for f in os.listdir(base_path) if f.endswith(f'.{format_ext}')]
        current_time = time.time()
        
        for file in files:
            file_path = os.path.join(base_path, file)
            
            if video_id in file:
                return file_path
            
            if os.path.getmtime(file_path) > current_time - FILE_SEARCH_WINDOW_SECONDS:
                return file_path
        
        return None
    except Exception:
        return None


def process_metadata(file_path: str, format_ext: str, video_id: str):
    """
    Embed metadata (title, artist, videoId, cover) into downloaded audio file.
    Uses add_cover.py and add_metadata.py functions for consistency.
    """
    import os as os_module
    import re
    import logging
    
    log = logging.getLogger(__name__)
    
    print(f"\n{'='*60}")
    print(f"🎵 Processing metadata for: {os_module.path.basename(file_path)}")
    print(f"📹 Video ID: {video_id}")
    print(f"{'='*60}")
    
    try:
        from mutagen.id3 import ID3, TIT2, TPE1, TCON, APIC, ID3NoHeaderError
        from mutagen.mp4 import MP4
        
        if not os_module.path.exists(file_path):
            print(f"❌ File not found for metadata: {file_path}")
            log.warning("File not found for metadata: %s", file_path)
            return
        
        ext = os_module.path.splitext(file_path)[1].lower()
        
        # Parse artist and title from filename if possible
        basename = os_module.path.splitext(os_module.path.basename(file_path))[0]
        artist = "Unknown Artist"
        title = basename
        
        # Try to parse "Artist - Title.mp3" format
        if " - " in basename:
            parts = basename.split(" - ", 1)
            artist = parts[0].strip()
            title = parts[1].strip()
            print(f"✅ Parsed from filename: '{artist}' - '{title}'")
        
        # Clean title from common YouTube artifacts
        original_title = title
        for pat in [
            r'\s*\[.*?\]', r'\s*\(.*?\)', r'\s*【.*?】',
            r'\s*[|•].*', r'\s*ft\.\s.*', r'\s*feat\.\s.*',
            r'\s*-\s*Official.*', r'\s*-\s*Lyrics.*',
            r'\s*-\s*Audio.*', r'\s*-\s*Video.*',
            r'\s*HD$', r'\s*HQ$', r'\s*4K$',
        ]:
            title = re.sub(pat, '', title, flags=re.IGNORECASE)
        title = title.strip()
        
        if title != original_title:
            print(f"🧹 Cleaned title: '{original_title}' → '{title}'")
        
        if ext == '.mp3':
            # MP3: Set ID3 tags
            try:
                id3 = ID3(file_path)
            except ID3NoHeaderError:
                id3 = ID3()
                id3.save(file_path, v2_version=3)
                id3 = ID3(file_path)
            
            # Set title and artist
            if title:
                id3.delall("TIT2")
                id3.add(TIT2(encoding=3, text=title))
                print(f"📝 Set title: {title}")
            
            if artist and artist != "Unknown Artist":
                id3.delall("TPE1")
                id3.add(TPE1(encoding=3, text=artist))
                print(f"🎤 Set artist: {artist}")
            
            # Store videoId in TCON (genre) field
            if video_id:
                id3.delall("TCON")
                id3.add(TCON(encoding=3, text=video_id))
                print(f"🆔 Set videoId: {video_id}")
            
            id3.save(file_path, v2_version=3, v1=2)
            
            # Embed cover art from YouTube
            try:
                from app.logic.api_handler.handle_yt import get_video_by_id
                from app.logic.metadata.add_cover import embed_image_mp3
                
                async def get_thumb():
                    video_info = await get_video_by_id(video_id)
                    if video_info:
                        snippet = video_info.get("snippet", {})
                        thumbs = snippet.get("thumbnails", {})
                        return (
                            thumbs.get("maxres", {}).get("url")
                            or thumbs.get("standard", {}).get("url")
                            or thumbs.get("high", {}).get("url")
                        )
                    return None
                
                print(f"🖼️  Fetching cover art...")
                thumb_url = run_async(get_thumb())
                if thumb_url:
                    print(f"📸 Cover URL: {thumb_url[:80]}...")
                    success = embed_image_mp3(file_path, image_url=thumb_url)
                    if success:
                        print(f"✅ Embedded cover art successfully")
                        log.info("✅ Embedded cover art for: %s", os_module.path.basename(file_path))
                    else:
                        print(f"❌ Failed to embed cover")
                else:
                    print(f"⚠️ No cover URL found")
            except Exception as e:
                print(f"❌ Cover embedding failed: {e}")
                log.warning("Failed to embed cover: %s", e)
            
            print(f"✅ MP3 metadata complete: {artist} - {title} [{video_id}]")
            log.info("✅ Metadata embedded for MP3: %s - %s [%s]", artist, title, video_id)
            
        elif ext in ('.mp4', '.m4a'):
            # MP4: Set atoms
            try:
                audio = MP4(file_path)
                
                if title:
                    audio["\xa9nam"] = [title]
                    print(f"📝 Set title: {title}")
                if artist and artist != "Unknown Artist":
                    audio["\xa9ART"] = [artist]
                    print(f"🎤 Set artist: {artist}")
                if video_id:
                    audio["\xa9cmt"] = [video_id]
                    print(f"🆔 Set videoId: {video_id}")
                
                audio.save()
                
                # Embed cover
                try:
                    from app.logic.api_handler.handle_yt import get_video_by_id
                    from app.logic.metadata.add_cover import embed_image_mp4
                    
                    async def get_thumb():
                        video_info = await get_video_by_id(video_id)
                        if video_info:
                            snippet = video_info.get("snippet", {})
                            thumbs = snippet.get("thumbnails", {})
                            return (
                                thumbs.get("maxres", {}).get("url")
                                or thumbs.get("standard", {}).get("url")
                                or thumbs.get("high", {}).get("url")
                            )
                        return None
                    
                    print(f"🖼️  Fetching cover art...")
                    thumb_url = run_async(get_thumb())
                    if thumb_url:
                        success = embed_image_mp4(file_path, image_url=thumb_url)
                        if success:
                            print(f"✅ Embedded cover art successfully")
                            log.info("✅ Embedded cover art for: %s", os_module.path.basename(file_path))
                except Exception as e:
                    print(f"❌ Cover embedding failed: {e}")
                    log.warning("Failed to embed cover: %s", e)
                
                print(f"✅ MP4 metadata complete: {artist} - {title} [{video_id}]")
                log.info("✅ Metadata embedded for MP4: %s - %s [%s]", artist, title, video_id)
            except Exception as e:
                print(f"❌ Failed to set MP4 metadata: {e}")
                log.error("Failed to set MP4 metadata: %s", e)
        
        print(f"{'='*60}\n")
    
    except Exception as e:
        import logging
        print(f"❌ process_metadata error: {e}")
        logging.getLogger(__name__).error("process_metadata error: %s", e)


def process_subtitles(file_path: str, srt_path: str):
    if not os.path.exists(srt_path):
        return
    
    try:
        sync = parse_srt_to_sync(srt_path)
        embed_sylt(file_path, sync)
        convert_srt_to_txt(srt_path)
    except Exception as e:
        print(f"Warning: Failed to process subtitles: {e}")


def download_song(videoId: str, id: str = "0", format_ext: str = "mp3", base_path: str = None) -> str:
    try:
        print(f"Starting download for: {videoId}")
        clean_video_id = extract_video_id(videoId)
        
        if id in ["0", 0]:
            title = fetch_video_title(clean_video_id)
            id = sanitize_filename(title)
        else:
            id = sanitize_filename(id)
        
        base = base_path or _download_dir()
        file_path = os.path.join(base, f"{id}.{format_ext}")
        srt_path = os.path.join(base, f"{id}.en.srt")
        
        if os.path.exists(file_path):
            print(f"File already exists: {file_path}")
            return file_path
        
        youtube_url = f"https://www.youtube.com/watch?v={clean_video_id}"
        print(f"Downloading from: {youtube_url}")
        print(f"Output path: {file_path}")
        
        download_song_mp3(youtube_url, base, audio_format=format_ext, quality="320")
        sleep(2)
        
        found_path = find_downloaded_file(base, clean_video_id, file_path, format_ext)
        
        if found_path and found_path != file_path:
            try:
                if not os.path.exists(file_path):
                    os.rename(found_path, file_path)
                    found_path = file_path
            except Exception:
                pass
        
        final_path = found_path or file_path
        
        if not os.path.exists(final_path):
            raise Exception(f"Download failed: {final_path} not created")
        
        process_metadata(final_path, format_ext, clean_video_id)
        process_subtitles(final_path, srt_path)
        cleanup_temp_files(os.path.join(base, id))
        
        return final_path
    
    except Exception as e:
        print(f"Error in download_song: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def process_playlist_entry(entry: dict, index: int, playlist_dir: str, audio_format: str) -> Optional[str]:
    if not entry:
        return None
    
    video_id = entry.get("id", f"unknown_{index}")
    title = sanitize_filename(entry.get("title", f"unknown_{index}"))
    file_path = os.path.join(playlist_dir, f"{title}.{audio_format}")
    srt_path = os.path.join(playlist_dir, f"{title}.en.srt")
    
    if not os.path.exists(file_path):
        print(f"Skipping missing file: {file_path}")
        return None
    
    process_metadata(file_path, audio_format, video_id)
    process_subtitles(file_path, srt_path)
    
    return file_path


def create_playlist_zip(processed_files: list, playlist_title: str) -> str:
    zip_name = sanitize_filename(playlist_title) + ".zip"
    zip_path = os.path.join(_download_dir(), zip_name)
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file in processed_files:
            arcname = os.path.basename(file)
            zipf.write(file, arcname)
    
    return zip_path


def download_playlist(playlistId: str, audio_format: str = "mp3") -> str:
    try:
        playlist_url = f"https://www.youtube.com/playlist?list={playlistId}"
        playlist_dir = _download_dir()
        os.makedirs(playlist_dir, exist_ok=True)
        
        info = download_song_mp3(playlist_url, playlist_dir, audio_format=audio_format, quality="320")
        
        entries = info.get("entries", []) or [info]
        processed_files = []
        
        for i, entry in enumerate(entries):
            result = process_playlist_entry(entry, i, playlist_dir, audio_format)
            if result:
                processed_files.append(result)
        
        if not processed_files:
            raise Exception("No files were processed")
        
        playlist_title = info.get("title", "playlist")
        return create_playlist_zip(processed_files, playlist_title)
    
    except Exception as e:
        print(f"Error in download_playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))