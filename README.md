# music-server

Backend for the music app built with FastAPI and Python 3.12.

## Features

- Local music library scanning
- YouTube playlist/search integration
- Local library repair and metadata handling
- Recommendation pipelines
- Cover color extraction
- Tags, events, downloads, and cloud storage helpers

## Requirements

- Python 3.12+
- `uv`

## Installation

```bash
uv sync --extra dev
cp .env.example .env
```

Edit `.env` and add the API keys/config values needed for your environment.

Important variables:

```env
FILEPATH=/path/to/music/library
API_KEY=
GEMINI_API_KEY=
DATA_DIR=./data
```

`FILEPATH` points to the local music library used by the scanner.

## Run tests

```bash
uv run --extra dev pytest -q
```

## Run the API server

```bash
uv run uvicorn app.app:app --host 0.0.0.0 --port 8000 --reload
```

## Data shape

Song list endpoints return lightweight song objects by default. Lyrics text is not included unless explicitly requested.

```bash
GET /api/songs
GET /api/songs?includeLyrics=true
GET /playlists/all-songs
GET /playlists/all-songs?includeLyrics=true
```

Lyrics are stored outside `playlist.json` in `DATA_DIR/lyrics` as `.txt` or `.lrc` files. Use the dedicated lyrics API for full text:

```bash
GET /api/lyrics?videoId=<id>
POST /api/lyrics
```

`playlist.json`, scan cache, color cache, and lyrics files are written atomically to avoid partial/corrupted saves.

## Docker

```bash
docker compose up -d
```

The compose file is intended for optional services such as PostgreSQL. SQLite is used by default when `DATABASE_URL` is not configured.
