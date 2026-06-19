#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.jellyfin_config import JellyfinConfig
from app.logic.jellyfin_sync import compare_jellyfin_metadata, fetch_jellyfin_music_items, match_jellyfin_item_to_local_song
from app.logic.local_ai.enrichment_service import enrich_library_batch
from app.logic.library_scanner import scan_music_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local metadata enrichment for the Jellyfin music library.")
    parser.add_argument("--dry-run", action="store_true", help="Analyze and cache results without writing audio metadata or moving files.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of tracks to analyze.")
    parser.add_argument("--only-missing-genre", action="store_true", help="Only process tracks with missing or garbage genre.")
    parser.add_argument("--only-low-quality", action="store_true", help="Only process tracks with low metadata quality.")
    parser.add_argument("--write-tags", action="store_true", help="Write cleaned genre and AI-managed tags back into audio files.")
    parser.add_argument("--write-albums", action="store_true", help="Write cleaned album metadata back into audio files.")
    parser.add_argument("--repair-managed-tags", action="store_true", help="Recompute enrichment and replace stale AI-managed tags in audio files.")
    parser.add_argument("--repair-managed-albums", action="store_true", help="Recompute enrichment and replace Unknown Album, fake category albums, or stale AI-managed albums.")
    parser.add_argument("--repair-album-folders", action="store_true", help="Alias for --repair-managed-albums; also moves files out of fake category album folders.")
    parser.add_argument("--move-files", action="store_true", help="Move files from Unknown Album or fake category album folders into cleaned album folders.")
    parser.add_argument("--group-preview", action="store_true", help="Print grouped classification summary.")
    parser.add_argument("--jellyfin-check", action="store_true", help="Run read-only Jellyfin metadata diagnostics.")
    parser.add_argument("--use-local-ai", action="store_true", help="Enable local AI classification for this run.")
    return parser.parse_args()


def run_jellyfin_check() -> dict:
    jf = fetch_jellyfin_music_items()
    if not jf.get("enabled"):
        return {"enabled": False, "message": jf.get("message"), "jellyfin_items": 0, "matched": 0, "differences": 0}
    items = jf.get("items", [])
    songs = scan_music_files(JellyfinConfig.get_music_library_path())
    matched = 0
    differences = 0
    for song in songs:
        item = match_jellyfin_item_to_local_song(song, items)
        comparison = compare_jellyfin_metadata(song, item)
        if comparison.get("matched"):
            matched += 1
        if comparison.get("differences"):
            differences += 1
    return {"enabled": True, "message": jf.get("message"), "jellyfin_items": len(items), "matched": matched, "differences": differences}


def main() -> int:
    args = parse_args()
    if args.use_local_ai:
        os.environ["LOCAL_AI_METADATA_ENABLED"] = "true"
    will_write = args.write_tags or args.write_albums
    will_move = args.move_files and not args.dry_run
    dry_run = args.dry_run or not (will_write or will_move)
    summary = enrich_library_batch(
        music_dir=JellyfinConfig.get_music_library_path(),
        limit=args.limit,
        only_missing_genre=args.only_missing_genre,
        only_low_quality=args.only_low_quality,
        dry_run=dry_run,
        write_tags=args.write_tags,
        write_albums=args.write_albums,
        move_files=args.move_files,
        group_preview=args.group_preview,
        force_local_ai=args.use_local_ai,
        repair_managed_tags=args.repair_managed_tags,
        repair_managed_albums=args.repair_managed_albums or args.repair_album_folders,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if args.group_preview:
        print("Group preview:")
        for group, count in sorted(summary.get("groups", {}).items()):
            print(f"{group}: {count} tracks")
        for subgenre, count in sorted(summary.get("subgenres", {}).items()):
            print(f"  {subgenre}: {count}")
    if args.jellyfin_check:
        print("Jellyfin check:")
        print(json.dumps(run_jellyfin_check(), ensure_ascii=False, indent=2, sort_keys=True))
    if dry_run:
        print("Dry run complete. Re-run with --write-tags or --write-albums to persist metadata.")
    return 0 if summary.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
