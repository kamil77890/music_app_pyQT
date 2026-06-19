# Firefox Extension — Music Library Saver

Save YouTube videos directly to your Jellyfin music library (`/srv/music`) and
browse/play your collection from the Firefox sidebar.

## Prerequisites

- **music_app_pyQT** backend running on `http://localhost:8000`
- Python virtual environment activated (see project root `README`)
- (Optional) `JELLYFIN_API_KEY` set in `.env` for automatic library scan

## Load the Extension in Firefox

1. Open Firefox and go to `about:debugging`
2. Click **This Firefox**
3. Click **Load Temporary Add-on…**
4. Navigate to `browser_extension/firefox/` and select `manifest.json`

The extension icon appears in the toolbar.

## How to Use

### Save from YouTube

1. Go to `youtube.com` or `music.youtube.com`
2. A **♪ Save to Jellyfin** button appears at the bottom‑right corner
3. Click it — the song is downloaded and saved to `/srv/music`
4. Status shows: `Saving...` → `✓ Saved!` → clears after 3 seconds

### Sidebar (Music Library)

Open the sidebar via:
- **View → Sidebar → Music Library**, or
- Click the extension icon → **Open Sidebar**

The sidebar shows:
- **Backend status** — online / offline badge
- **Current Tab card** — detected URL, YouTube status badge, Save button
- **Manual URL input** — paste any YouTube URL and save
- **Download status** — idle / saving / saved / failed with descriptive messages
- **Search** — filter your library by title, artist, or album
- **Song list** — each entry has cover, title, artist, album, and a Play button
- **Empty state** — helpful prompt when library is empty
- **Audio player** — sticky mini‑player at the bottom to play songs in the sidebar

### Popup

Click the toolbar icon for a quick menu:
- Backend online/offline indicator
- Current tab detection with YouTube status
- Save current YouTube tab
- Open Sidebar
- Link to backend health check

### Live Tab Detection

The background script tracks the active tab across:
- Tab switches (`onActivated`)
- URL / title changes (`onUpdated`)
- Window focus changes (`onFocusChanged`)
- YouTube SPA navigation events (from content script)

The sidebar and popup receive real‑time updates via `CURRENT_TAB_CHANGED` messages.
A 2‑second fallback polling ensures the sidebar stays in sync even without events.

## Manual Testing Checklist

### Backend offline
1. Stop the backend server
2. Click extension icon → verify "offline" badge and status
3. Open sidebar → verify "offline" badge
4. Try Save → verify descriptive "Backend offline" error message

### YouTube active
1. Start the backend: `python run.py`
2. Navigate to `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
3. Verify the ♪ Save to Jellyfin button appears
4. Open sidebar → verify "YouTube detected" badge and Save button enabled
5. Open popup → verify "✓ YouTube detected" status
6. Click Save in popup → verify `Saving...` → `✓ Saved to Jellyfin`
7. Click Save button on YouTube page → verify `✓ Saved!` status

### Non-YouTube active
1. Navigate to any non-YouTube page (e.g., `https://example.com`)
2. Open sidebar → verify "Not a YouTube page" badge and Save button disabled
3. Open popup → verify "Not a YouTube page" status

### SPA navigation (YouTube single‑page app)
1. Start on YouTube, watch a video
2. Click another video in the recommendations (SPA navigation)
3. Verify the button re‑appears and captures the new video ID
4. Open sidebar → verify the URL / title updates to the new video

### yt-dlp 403 / expired cookies
1. Simulate by blocking yt-dlp or using an outdated cookies file
2. Save a YouTube video → verify "YouTube blocked the download request" error
3. The error message should suggest updating yt-dlp or enabling cookies-from-browser

### Success flow
1. Start backend
2. Navigate to a YouTube video
3. Save via in‑page button → verify `✓ Saved!`
4. Verify the file appears in `/srv/music/Artist/Album/`
5. Open sidebar → verify song appears in library
6. Click Play → verify audio streams and plays in the mini‑player
7. Search by title/artist → verify list filters correctly
8. Refresh sidebar → verify all data reloads

## Debugging

| Issue | Likely cause |
|---|---|
| Button not appearing on YouTube | Refresh the page; YouTube SPA may need a reload |
| "Backend offline" | Start the server: `python run.py` |
| Save fails | Check terminal for backend logs |
| CORS error | Backend should have `allow_origins=["*"]` (already configured) |
| Sidebar not opening | Use View → Sidebar → Music Library manually |
| YouTube 403 error | Update yt-dlp or enable cookies-from-browser in backend |

## Permissions Note

- The extension only communicates with `http://localhost:8000`
- No external servers are contacted
- Jellyfin API key stays in the backend `.env` file — never exposed to the extension
