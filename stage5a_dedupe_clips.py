#!/usr/bin/env python3
"""Stage 5a: move duplicate clips (the same video) to a duplicates/ folder.
Run before stage5c_match_places.py, so a video is never counted twice in popularity.
Stage 1 already refuses duplicates; this is a safety check over all clips.
Two clips are the same video when source.url has the same TikTok video id or, for other
links, the same address.
The first clip by file name is kept. Each moved clip gets "duplicate_of": <kept clip_id>.
Nothing is deleted: to undo, move the file back out of duplicates/.

Usage:
    python stage5a_dedupe_clips.py data/clips/*.json
"""
import argparse
from pathlib import Path

from tvna_common import load_json, save_json, video_key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", help="Clip JSON files")
    args = ap.parse_args()

    kept, moved, no_url, problems = {}, [], [], []
    # The same file given twice (e.g. two globs) is one clip, not a duplicate of itself.
    unique = {}
    for p in args.clips:
        unique.setdefault(Path(p).resolve(), Path(p))
    for path in sorted(unique.values()):
        if not path.is_file():
            problems.append(f"{path.name}: not found (already moved to duplicates/?), skipped")
            continue
        clip = load_json(path)
        key = video_key((clip.get("source") or {}).get("url"))
        if not key:
            no_url.append(path.name)
            continue
        if key not in kept:
            kept[key] = (clip.get("clip_id"), path.name)
            continue

        kept_id, kept_name = kept[key]
        target = path.parent / "duplicates" / path.name
        if target.exists():
            problems.append(f"{path.name}: duplicates/{path.name} already exists, not moved")
            continue
        target.parent.mkdir(exist_ok=True)
        clip["duplicate_of"] = kept_id
        save_json(target, clip)
        path.unlink()
        moved.append(f"{path.name} -> duplicates/ (same video as {kept_name})")

    for title, lines in [("moved", moved), ("no url, not checked", no_url), ("problems", problems)]:
        print(f"{title} ({len(lines)}):")
        for line in lines:
            print(f"  {line}")


if __name__ == "__main__":
    main()
