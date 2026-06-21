# Library Layout Groups Design

## Goal

Rebuild music library organization from artist-first fake album groups to category-first library groups:

```text
/srv/music/<library_group>/<artist>/<track>
```

When a trustworthy real album exists, the layout may include it below the artist:

```text
/srv/music/<library_group>/<artist>/<real album>/<track>
```

`library_group` is a separate hierarchy/category field. It is not a real album and must not be written into `TALB` or `©alb` to force folder layout.

## Current Context

The existing local AI grouping code is album-oriented and artist-scoped:

- `album_group_planner.py` prompts and plans groups for one artist at a time.
- Assignments write fake library categories through `album`, `album_kind`, `album_source`, and `group_id`.
- Move planning uses `Artist / Album / Track` paths through `plan_track_album_move`.
- `/api/library/songs` returns flat songs; the Firefox sidebar filters by genre/style/tags.

The new design keeps existing enrichment signals but introduces a new planner dedicated to layout groups.

## Approach

Create a new `library_layout_planner` beside the existing album group planner. It will use semantic profiles, registry markers, and current enrichment output as inputs, but it will produce a separate layout plan based on `library_group`.

The old album group code can remain for compatibility while new CLI modes and UI/API use the library layout planner. Migration logic will recognize old AI-managed fake album folders through reliable markers and move files into the new layout.

New downloads must not be placed directly into `Artist / Unknown Album` or any other fake album layout. Until a saved library layout plan includes them, downloads go to a safe staging path such as `_incoming/<sanitized artist>/<track>` or an equivalent incoming folder under the library root.

## Data Model

Enriched track metadata gains independent fields:

```json
{
  "library_group": "Nightcore",
  "library_group_source": "local_ai",
  "library_group_confidence": 0.0
}
```

Existing fields keep their meaning:

- `artist`: real artist/channel.
- `album`: real album only when trustworthy metadata exists.
- `library_group`: global category used for folders and UI.
- `collection`: optional context such as `Live`.
- `tags` and `style`: track-level descriptive attributes.

Audio metadata written by layout apply:

- ID3: `TXXX:LOCAL_AI_LIBRARY_GROUP`, `TXXX:LOCAL_AI_GROUP_ID`, optional `TXXX:LOCAL_AI_COLLECTION`.
- MP4/M4A: `----:com.apple.iTunes:LOCAL_AI_LIBRARY_GROUP`, `LOCAL_AI_GROUP_ID`, optional `LOCAL_AI_COLLECTION`.
- Existing `TPE1`/artist and `TPE2`/album artist remain real artist values when metadata writing touches them.
- `TALB`/`©alb` remains a real album when one exists.
- If no real album exists, `TALB`/`©alb` is left empty rather than populated with `Nightcore`, `Anime Piano`, `Alternative Rock`, or another category.

Legacy fake album cleanup is conservative. A fake `TALB`/`©alb` may be cleared only when the system has reliable AI-managed evidence, such as previous `LOCAL_AI_ALBUM_KIND`, registry membership, or another managed metadata marker. Real albums are never removed or overwritten.

## Library Group Rules

Grouping is global, not per artist:

1. Enrich all tracks and build semantic profiles.
2. Determine each track's `library_group` across the whole library.
3. Build the hierarchy as `library_group -> artist -> optional real album -> tracks`.
4. Generate move plans from that hierarchy.

Nightcore is an explicit global layout rule. If a track has confirmed Nightcore evidence from style, tags, title, source title, or semantic profile, its `library_group` is exactly `Nightcore`. Variants such as `Nightcore Covers`, `Nightcore Electronic Covers`, `Eiden XII Rock Nightcore`, and `Underdogs Nightcore` are normalized to `Nightcore`; the artist is represented only as the second-level folder.

Other group names remain dynamic. Local AI and deterministic fallback may produce names such as `Alternative Rock`, `Pop Rock`, `Piano Covers`, `Anime Piano`, `Anime Soundtracks`, `Classical Piano`, and `Electronic Covers`, but every candidate must pass quality validation:

- 1-3 words.
- Based on shared musical features.
- Does not contain the artist name.
- Does not contain the track title.
- Does not contain a single-track franchise/context such as `Cyberpunk` or `Tokyo Ghoul`.
- Does not contain `Official Video`, `Live`, `Lyrics`, `AMV`, `Animated Music Video`, `OP`, or `ED`.
- Does not contain `Singles`, `Unknown`, `Misc`, `General`, or `Collection`.
- Does not look like a YouTube video description.

`Live`, `Official Video`, `Lyrics`, `AMV`, and similar markers remain style/tag/collection information. They do not create top-level layout groups.

For weak or uncertain tracks from an artist with a clear dominant musical group, planner should prefer the artist's dominant group unless there is strong evidence of a different musical group. This prevents Linkin Park-like fixtures from splitting into `Live Electronic Dance`, `Music Video Rock`, and unrelated groups.

## Plan Mode

`--plan-library-layout` is read-only:

- Does not write audio metadata.
- Does not move files.
- Does not delete folders.
- Writes a snapshot plan with a deterministic `plan_id` derived from normalized plan contents, excluding `generated_at`.
- Prints a tree preview, conflicts, and move preview.
- Produces deterministic output for the same input set.

The plan snapshot contains:

- `plan_id`.
- classifier version/model metadata.
- source library path.
- generated timestamp, stored as metadata but excluded from `plan_id` calculation.
- sorted group tree.
- move operations.
- per-track fingerprint: source path, resolved path, mtime, size, track key, and videoId when present.
- metadata operations to apply.
- conflicts discovered during planning.

`plan_id` hash input includes normalized move operations, metadata operations, classifier version, model, grouping prompt/config version, and track fingerprints. `generated_at` is saved for auditability but excluded from the hash.

Plans are stored under `data/library_layout_plans/<plan_id>.json`. This directory is runtime state and must not be committed.

## Apply Mode

`--apply-library-layout <plan_id>` executes exactly the previously saved plan snapshot. It must not rerun classification, regenerate groups, or silently repair the plan.

Before each track move or metadata write, apply verifies the planned fingerprint:

- source path still exists inside the library root.
- resolved source path matches the planned source.
- mtime matches the planned mtime.
- size matches the planned size.
- track key and videoId match when available.

If the file changed since planning, apply skips that item, records a conflict, does not overwrite anything, and does not generate a new classification.

Apply safety rules:

- Never deletes audio files.
- Preserves `cover.jpg` and other cover images when moving managed folders.
- Never overwrites an existing destination.
- Uses duplicate suffixes `(1)`, `(2)`, etc. for destination conflicts.
- Blocks path traversal by sanitizing every path component and checking final resolved paths remain inside the library root.
- Does not allow `--move-files` to generate and execute a new layout plan independently.
- Refuses to apply if the `library_root` saved in the plan is not identical to the current configured music library path. This failure happens before any metadata or filesystem changes.

After the new layout system is in place, direct `--move-files` migration is disabled. Running it without `--apply-library-layout` exits with an error before any file changes:

```text
Direct file moves are disabled for library layout migration.
Run --plan-library-layout first, review the saved plan, then run:
--apply-library-layout <plan_id>
```

Cover art policy is deterministic:

- Apply never overwrites an existing `cover.jpg`.
- If multiple source folders contain covers for the same destination group/artist/album folder, apply chooses the representative cover by stable sort of planned source paths.
- Non-selected covers are recorded as skipped or conflict entries in the apply manifest.
- Existing destination covers always win over planned source covers.

## Apply Manifest

Each apply run writes a `layout_apply_manifest` / move journal under `data/library_layout_apply_manifests/` for future rollback support. Every entry records:

- `plan_id`.
- track key.
- source path.
- destination path.
- timestamp.
- status: planned, moved, metadata_written, skipped, conflict, or error.
- error message when present.
- metadata fields written.

The manifest is append-only for the apply run and is saved even when some items fail.

## API

Add:

```text
GET /api/library/groups
```

Response shape:

```json
{
  "groups": [
    {
      "name": "Nightcore",
      "cover": "...",
      "artists": [
        {
          "name": "Kenke",
          "track_count": 7,
          "tracks": []
        }
      ]
    }
  ]
}
```

This endpoint is the source of truth for the extension UI hierarchy. The hierarchy is not forced through Jellyfin album views or fake album metadata.

The endpoint must use only saved metadata, registry, cache, and filesystem scan data. It must not call Ollama or run local AI enrichment on request.

## UI

The Firefox sidebar adds a library group navigation path:

```text
Library Groups -> Group -> Artists -> Tracks
```

The UI should fetch `/api/library/groups` and render groups first, then artists, then tracks. The existing flat song list can remain as a search or fallback view.

## Migration

Existing AI-managed folders are identified through reliable metadata and registry signals, not artist-specific production mappings:

- `LOCAL_AI_GROUP_ID`.
- `LOCAL_AI_ALBUM_KIND`.
- legacy album group registry.
- local AI metadata source or managed markers.
- semantic profile and validated `library_group`.

Examples that must emerge from semantic grouping rather than hardcoded artists:

```text
Kenke/Nightcore Covers/* -> Nightcore/Kenke/*
Eiden XII/Eiden XII Rock Nightcore/* -> Nightcore/Eiden XII/*
Nightcore Nation/Nightcore Electronic Covers/* -> Nightcore/Nightcore Nation/*
Grim Cat Piano/Cyberpunk Piano/* -> Piano Covers/Grim Cat Piano/*
Linkin Park/Live Electronic Dance/* -> Alternative Rock/Linkin Park/*
Linkin Park/Music Video Rock/* -> Alternative Rock/Linkin Park/*
```

Production code must not contain artist-specific mappings for these examples.

## Tests

Add or update tests for:

1. Tracks with style/tag/title/source Nightcore map to global `Nightcore`.
2. Nightcore from different artists maps to `Nightcore/<artist>/...`.
3. Artist names are never part of `library_group`.
4. Track titles and single-track franchise names are never part of `library_group`.
5. `Live`, `Lyrics`, `AMV`, and `Official Video` do not create groups.
6. Related tracks from one artist merge to the same dominant group.
7. Linkin Park-like live/video/unknown fixture maps to one musical group.
8. `--plan-library-layout` does not change filesystem or audio metadata.
9. `--apply-library-layout` uses the saved snapshot and does not classify.
10. Apply detects fingerprint mismatches and records conflicts.
11. Apply writes a manifest with move and metadata status.
12. The same input produces identical plan output.
13. Production code has no artist-specific mapping.
14. Path traversal, overwrite, and duplicate suffix safety remain covered.
15. Old fake `TALB` is cleared only with reliable AI-managed evidence.
16. New downloads land in `_incoming`/staging, not `Artist / Unknown Album`.
17. `/api/library/groups` does not call Ollama or enrichment on request.
18. `plan_id` changes when normalized operations, config version, model, classifier version, or fingerprints change, but not when only `generated_at` changes.
19. Cover apply policy is deterministic and never overwrites existing `cover.jpg`.
20. `--move-files` cannot generate and execute a layout plan by itself.
21. Direct `--move-files` exits with the required guidance message and makes no changes.
22. Apply aborts without changes when the plan `library_root` differs from current configuration.

Verification command:

```bash
.venv/bin/python -m pytest
```

After implementation, validation must run plan mode only:

```bash
LOCAL_AI_MODEL=qwen2.5:3b .venv/bin/python scripts/run-local-ai-enrichment.py \
  --plan-library-layout \
  --use-local-ai \
  --repair-managed-tags \
  --repair-managed-albums \
  --repair-album-folders
```

The output must show plan tree, `plan_id`, conflicts, and move preview. Apply must not be executed until the user manually accepts a specific plan.
