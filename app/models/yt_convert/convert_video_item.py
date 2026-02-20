from app.models.song import Song


def convert_video_item(item, idx: int = 0):
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    video_id = item.get("id")
    title = snippet.get("title", "Unknown Title").replace("&amp;", "&")
    artist = snippet.get(
        "channelTitle", "Unknown Artist").replace("&amp;", "&")
    cover = snippet.get("thumbnails", {}).get("high", {}).get("url", "")
    raw_views = int(stats.get("viewCount", "0"))

    if raw_views >= 1_000_000:
        views = f"{raw_views / 1_000_000:.1f}M"
    elif raw_views >= 1_000:
        views = f"{raw_views / 1_000:.1f}K"
    else:
        views = str(raw_views)

    return Song(
        id=str(video_id or idx),
        title=title,
        artist=artist,
        duration=0,
        videoId=video_id,
        cover=cover,
        fileUri="",
        views=views,
        isLocal=False
    )
