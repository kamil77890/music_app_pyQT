# Local Whisper Subtitle Fallback Design

## Goal

When a downloaded YouTube video has subtitles or automatic captions, the app should keep using them. When YouTube does not provide captions, the app should generate lyrics/subtitles locally from the downloaded audio using Whisper.

The audio download must remain the primary operation. Subtitle failures should not fail the whole song download.

## Current Behavior

The main download path in `app/logic/ultimate_downloader.py` calls `download_audio()` without enabling subtitle download. Even when subtitles are downloaded, `app/logic/downloader/yt_dlp_client.py` is configured for `vtt` and only `en`, while later processing expects an `.en.srt` file.

`app/logic/library_repair.py` has a better subtitle fetch path that downloads English subtitles, tries `en` and `en-US`, converts to SRT, and then embeds lyrics. This behavior is not shared with the main download path, and it is still too narrow for non-English videos.

## Proposed Behavior

For every downloaded song:

1. Try to get YouTube captions first.
2. Convert captions to SRT if needed.
3. Convert SRT to plain text in the existing `lyrics/` directory.
4. Embed synced lyrics into MP3 files using the existing `SYLT` path when possible.
5. If captions are unavailable, run local Whisper transcription against the downloaded audio.
6. Save Whisper output as SRT and TXT, and embed synced lyrics for MP3 files when possible.
7. Log failures, but do not abort the audio download.

## Architecture

Add a focused subtitle pipeline under `app/logic/subtitles/` that owns three responsibilities:

- fetch captions from YouTube using `yt-dlp`, reusing the stronger SRT conversion settings from `library_repair.py`,
- generate SRT from local audio using Whisper when captions are missing,
- process any SRT into TXT and optional embedded synced lyrics.

`ultimate_downloader.py` should call this pipeline after metadata processing and before cleanup. `library_repair.py` can continue using its existing flow initially, or be moved to the shared helper as a follow-up to avoid duplicate logic.

## Whisper Choice

Use local Whisper through a Python dependency. Prefer `faster-whisper` because it is practical for local CPU use and can run without paid API access.

Configuration:

- `WHISPER_MODEL`, default `base`
- `WHISPER_DEVICE`, default `cpu`
- `WHISPER_COMPUTE_TYPE`, default `int8`

This keeps the first implementation usable on a normal machine while allowing better models later.

## Language Strategy

Caption fetching should prefer a configured language list, then fall back to the first usable caption language if none of the preferred languages exist.

Configuration:

- `SUBTITLE_LANGS`, default `pl,en,en-US`

Whisper should use automatic language detection by default. A later option can add an explicit `WHISPER_LANGUAGE`, but the first implementation should not force one language because the goal is to work across different videos.

## Data Flow

Input: downloaded audio file path, YouTube video ID, and final basename.

Output:

- `lyrics/<basename>.txt` with plain text lyrics/transcript,
- temporary or sidecar `<basename>.<lang>.srt` while processing,
- embedded `SYLT` lyrics for MP3 when SRT parsing succeeds.

The existing playlist scanner already reads `lyrics/<basename>.txt`, so generated text will appear through the current library flow.

## Error Handling

Caption download failure should fall back to Whisper.

Whisper failure should log a warning and return without raising to the user-facing download flow.

If Whisper is not installed, the warning should clearly say that local transcription is unavailable and name the missing dependency.

## Testing

Add unit tests around the subtitle pipeline with mocked `yt-dlp` and mocked Whisper model:

- uses YouTube captions when available,
- falls back to Whisper when captions are unavailable,
- writes valid SRT/TXT output from mocked Whisper segments,
- does not raise when both captions and Whisper fail.

Avoid network calls in tests.

## Out Of Scope

- Paid transcription APIs.
- Full multi-language selection UI.
- Reprocessing the entire existing library automatically.
- Guaranteeing perfect lyrics quality for music, since local speech recognition depends on audio quality, vocals, and model size.
