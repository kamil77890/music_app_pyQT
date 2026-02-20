import os
import asyncio
from mutagen.id3 import ID3, TIT2, TPE1, TCON, ID3NoHeaderError
from mutagen.mp4 import MP4

from app.logic.api_handler.handle_yt import get_song_by_string
from app.logic.metadata.add_cover import embed_image_mp3, embed_image_mp4


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


def add_metadata(file_path: str, format: str, videoId: str) -> bool:
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    if not videoId or len(videoId) != 11:
        print(f"❌ Invalid videoId: {videoId}")
        return False
    
    try:
        song_data = run_async(get_song_by_string(videoId))
        
        if not song_data:
            print(f"❌ No data returned for videoId: {videoId}")
            return False
        
        # Handle different response formats
        # If it's a list, get the first item
        if isinstance(song_data, list):
            if len(song_data) == 0:
                print(f"❌ Empty list returned for videoId: {videoId}")
                return False
            song = song_data[0]
        else:
            song = song_data
        
        # Handle Song object vs dictionary
        title = None
        artist = None
        thumbnails = None
        
        if hasattr(song, 'snippet'):
            snippet = song.snippet
            
            # Try to get title
            if hasattr(snippet, 'title'):
                title = snippet.title
            elif hasattr(snippet, '__getitem__') and 'title' in snippet:
                title = snippet['title']
            
            # Try to get artist/channelTitle
            if hasattr(snippet, 'channelTitle'):
                artist = snippet.channelTitle
            elif hasattr(snippet, 'channel_title'):
                artist = snippet.channel_title
            elif hasattr(snippet, '__getitem__') and 'channelTitle' in snippet:
                artist = snippet['channelTitle']
            
            # Try to get thumbnails
            if hasattr(snippet, 'thumbnails'):
                thumbnails = snippet.thumbnails
            elif hasattr(snippet, '__getitem__') and 'thumbnails' in snippet:
                thumbnails = snippet['thumbnails']
                
        elif isinstance(song, dict):
            snippet = song.get('snippet', {})
            title = snippet.get('title')
            artist = snippet.get('channelTitle')
            thumbnails = snippet.get('thumbnails', {})
        else:
            print(f"⚠️ Unexpected data format for videoId: {videoId}")
            print(f"   Type: {type(song)}")
            print(f"   Dir: {dir(song)}")
        
        # Set defaults if still None
        if not title:
            title = "Unknown Title"
            print(f"⚠️ Could not extract title from song data")
        if not artist:
            artist = "Unknown Artist"
            print(f"⚠️ Could not extract artist from song data")
        
        # Extract thumbnail URL
        thumbnail_url = None
        if thumbnails:
            if isinstance(thumbnails, dict):
                thumbnail_url = (
                    thumbnails.get('maxres', {}).get('url') or
                    thumbnails.get('standard', {}).get('url') or
                    thumbnails.get('high', {}).get('url') or
                    thumbnails.get('medium', {}).get('url') or
                    thumbnails.get('default', {}).get('url')
                )
            elif hasattr(thumbnails, '__iter__'):
                # Handle object with attributes
                for attr in ['maxres', 'standard', 'high', 'medium', 'default']:
                    if hasattr(thumbnails, attr):
                        thumb = getattr(thumbnails, attr)
                        if thumb:
                            if hasattr(thumb, 'url'):
                                thumbnail_url = thumb.url
                                break
                            elif isinstance(thumb, dict) and 'url' in thumb:
                                thumbnail_url = thumb['url']
                                break
                            elif hasattr(thumb, '__getitem__'):
                                try:
                                    thumbnail_url = thumb['url']
                                    break
                                except:
                                    pass
        
        if not thumbnail_url:
            print(f"⚠️ No thumbnail URL found for videoId: {videoId}")
            if thumbnails:
                print(f"   Thumbnails type: {type(thumbnails)}")
                if hasattr(thumbnails, '__dict__'):
                    print(f"   Thumbnails attributes: {thumbnails.__dict__}")
        
    except Exception as e:
        print(f"❌ Failed to fetch YouTube metadata: {e}")
        import traceback
        traceback.print_exc()
        return False

    if format.lower() == 'mp3':
        try:
            try:
                id3 = ID3(file_path)
            except ID3NoHeaderError:
                id3 = ID3()
            
            id3.add(TIT2(encoding=3, text=title))
            id3.add(TPE1(encoding=3, text=artist))
            id3.add(TCON(encoding=3, text=videoId))
            
            id3.save(file_path, v2_version=3)
            print(f"✅ Saved MP3 metadata: {title} - {artist}")
            print(f"✅ Saved videoId {videoId} to TCON tag")
            
            if thumbnail_url:
                success = embed_image_mp3(file_path, image_url=thumbnail_url)
                if not success:
                    print(f"⚠️ Failed to embed cover art, but metadata was saved")
            
            return True
            
        except Exception as e:
            print(f"❌ MP3 metadata error: {e}")
            return False

    elif format.lower() == 'mp4' or format.lower() == 'm4a':
        try:
            audio = MP4(file_path)
            
            audio['\xa9nam'] = title
            audio['\xa9ART'] = artist
            audio['\xa9cmt'] = videoId
            
            audio.save()
            print(f"✅ Saved MP4 metadata: {title} - {artist}")
            print(f"✅ Saved videoId {videoId} to comment tag")
            
            if thumbnail_url:
                success = embed_image_mp4(file_path, image_url=thumbnail_url)
                if not success:
                    print(f"⚠️ Failed to embed cover art, but metadata was saved")
            
            return True
            
        except Exception as e:
            print(f"❌ MP4 metadata error: {e}")
            return False

    else:
        print(f"❌ Unsupported format: {format}")
        return False


def verify_metadata(file_path: str, format: str) -> dict:
    try:
        if format.lower() == 'mp3':
            id3 = ID3(file_path)
            return {
                'title': str(id3.get('TIT2', 'N/A')),
                'artist': str(id3.get('TPE1', 'N/A')),
                'videoId': str(id3.get('TCON', 'N/A')),
                'has_cover': 'APIC:Cover' in id3 or any(k.startswith('APIC') for k in id3.keys())
            }
        elif format.lower() == 'mp4' or format.lower() == 'm4a':
            audio = MP4(file_path)
            return {
                'title': audio.get('\xa9nam', ['N/A'])[0],
                'artist': audio.get('\xa9ART', ['N/A'])[0],
                'videoId': audio.get('\xa9cmt', ['N/A'])[0],
                'has_cover': 'covr' in audio
            }
    except Exception as e:
        print(f"❌ Error reading metadata: {e}")
        return {}