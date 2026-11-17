#!/usr/bin/env python3
"""Stage 5a: move duplicate clips (the same video) to a duplicates/ folder.
Run before stage5c_match_places.py, so a video is never counted twice in popularity.
Stage 1 already refuses duplicates; this is a safety check over all clips.
Two clips are the same video when source.url has the same TikTok video id or, for other
links, the same address.
The clip whose file name is its clip_id (PP-004.json for "PP-004") is kept, so a copied file like
"PP-004 copy.json" is the one moved; among several such clips, the first by file name. Each moved clip gets
"duplicate_of": <kept clip_id>. Nothing is deleted: to undo, move the file back out of duplicates/.
Two clips with the same clip_id but different videos are listed under problems (two people picked the same number).

Usage:
    python stage5a_dedupe_clips.py data/clips/*.json
"""
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tvna_common import load_json, save_json, video_key


def keep_first(item: Tuple[Path, dict]):
    """Sort order for clips of one video: the clip whose file name is its clip_id first, then by file name."""
    path, clip = item
    return clip.get("clip_id") != path.stem, path.name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", help="Clip JSON files")
    args = ap.parse_args()

    moved, no_url, problems = [], [], []
    # The same file given twice (e.g. two globs) is one clip, not a duplicate of itself.
    unique = {}
    for p in args.clips:
        unique.setdefault(Path(p).resolve(), Path(p))
    videos: Dict[str, List[Tuple[Path, dict]]] = {}
    clip_ids: Dict[str, List[Tuple[str, Optional[str]]]] = {}
    for path in sorted(unique.values()):
        if not path.is_file():
            problems.append(f"{path.name}: not found (already moved to duplicates/?), skipped")
            continue
        clip = load_json(path)
        key = video_key((clip.get("source") or {}).get("url"))
        if isinstance(clip.get("clip_id"), str) and clip["clip_id"]:
            clip_ids.setdefault(clip["clip_id"], []).append((path.name, key))
        if not key:
            no_url.append(path.name)
            continue
        videos.setdefault(key, []).append((path, clip))

    for clip_id, files in clip_ids.items():
        if len({key for _, key in files}) > 1:
            names = ", ".join(name for name, _ in files)
            problems.append(f"{names}: same clip_id {clip_id} but different videos. "
                            "Give one a new PP number (clip_id and file name)")

    for group in videos.values():
        (kept_path, kept_clip), *others = sorted(group, key=keep_first)
        for path, clip in others:
            target = path.parent / "duplicates" / path.name
            if target.exists():
                problems.append(f"{path.name}: duplicates/{path.name} already exists, not moved")
                continue
            target.parent.mkdir(exist_ok=True)
            copied = clip.get("clip_id") and clip.get("clip_id") == kept_clip.get("clip_id")
            clip["duplicate_of"] = kept_clip.get("clip_id")
            save_json(target, clip)
            path.unlink()
            moved.append(f"{path.name} -> duplicates/ (same video as {kept_path.name}"
                         f"{'; same clip_id, so probably a copied file' if copied else ''})")

    for title, lines in [("moved", moved), ("no url, not checked", no_url), ("problems", problems)]:
        print(f"{title} ({len(lines)}):")
        for line in lines:
            print(f"  {line}")


if __name__ == "__main__":
    main()
