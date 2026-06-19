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
2. A **Save to Jellyfin** button appears at the bottom‑right corner
3. Click it — the song is downloaded and saved to `/srv/music`
4. Status shows: `Saving...` → `Saved!` → clears after 3 seconds

### Sidebar (Music Library)

Open the sidebar via:
- **View → Sidebar → Music Library**, or
- Click the extension icon → **Open Sidebar**

The sidebar shows:
- **Backend status** — online / offline badge
- **Save current YouTube tab** — downloads the video from the active tab
- **URL input** — paste any YouTube URL manually
- **Search** — filter your library by title, artist, or album
- **Song list** — each entry has cover (if available) and a Play button
- **Audio player** — play songs directly in the sidebar

### Popup

Click the toolbar icon for a quick menu:
- Backend online/offline indicator
- Open Sidebar
- Save current YouTube tab
- Link to backend health check

## Manual Testing Checklist

### Backend online
```bash
cd ~/Documents/music_app_pyQT
source .venv/bin/activate
python run.py
```
Then in Firefox:
1. Open YouTube
2. Click **Save to Jellyfin** → verify `Saving...` → `Saved!`
3. Check `/srv/music/Artist/Album/NN - Title.ext` exists
4. Open sidebar → verify song appears
5. Click Play → verify audio plays

### Backend offline
1. Stop the backend
2. Click extension icon → verify "backend offline"
3. Open sidebar → verify "offline" badge
4. Try Save → verify "Backend offline" message

### URL input in sidebar
1. Paste `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
2. Click **Save** → verify song appears in library

### Search
1. Type in search field → verify list filters as you type

## Debugging

| Issue | Likely cause |
|---|---|
| Button not appearing on YouTube | Refresh the page; YouTube SPA may need a reload |
| "Backend offline" | Start the server: `python run.py` |
| Save fails | Check terminal for backend logs |
| CORS error | Backend should have `allow_origins=["*"]` (already configured) |
| Sidebar not opening | Use View → Sidebar → Music Library manually |

## Permissions Note

- The extension only communicates with `http://localhost:8000`
- No external servers are contacted
- Jellyfin API key stays in the backend `.env` file — never exposed to the extension
