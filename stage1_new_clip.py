#!/usr/bin/env python3
"""Stage 1: TikTok link(s) -> new clip file(s) data/clips/PP-NNN.json (from templates/tvna_clip_template.json).
Duplicates are removed here, before any clip file exists, so no TikTok download or Gemini call is spent on them.
Short links (vt.tiktok.com, vm.tiktok.com) are expanded first. Each link is cleaned to
https://www.tiktok.com/@user/video/<id> and its video id is compared with every clip in data/clips/ and
data/clips/duplicates/ (and, with --from-file, with the links above it). A video that is already there is not added.

Usage:
    python stage1_new_clip.py "https://www.tiktok.com/@user/video/7593339174695046416"
    python stage1_new_clip.py "https://vt.tiktok.com/ZSpfUj3du/" --posted-at 2026-10-22
    python stage1_new_clip.py --from-file links.txt --check-only   # report only, nothing created
    python stage1_new_clip.py --from-file links.txt                # one link per line; blank and # lines ignored
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from tvna_common import (
    CLIP_ID,
    CLIPS_DIR,
    TEMPLATES_DIR,
    display_path,
    follow_redirects,
    load_json,
    save_json,
    video_key,
)

TEMPLATE_FILE = TEMPLATES_DIR / "tvna_clip_template.json"
TIKTOK_VIDEO_URL = re.compile(r"tiktok\.com/(@[^/?#]+)/video/(\d+)")


def is_tiktok(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.netloc.lower()
    return parts.scheme in ("http", "https") and (host == "tiktok.com" or host.endswith(".tiktok.com"))


def clean_tiktok_url(url: str) -> Tuple[str, str, str]:
    """Return the link without tracking parts, the creator handle and the video id."""
    m = TIKTOK_VIDEO_URL.search(url)
    if not m:
        raise ValueError("not a TikTok video link")
    handle, video_id = m.groups()
    return f"https://www.tiktok.com/{handle}/video/{video_id}", handle, video_id


def resolve(link: str) -> Tuple[str, str, str, Optional[str]]:
    """A pasted link -> (clean link, creator, video id, the short link if one was expanded).
    Raises ValueError with a short reason."""
    url = link.strip()
    if not is_tiktok(url):
        raise ValueError("only TikTok links are in scope")
    short = None
    if not TIKTOK_VIDEO_URL.search(url):
        try:
            short, url = url, follow_redirects(url, TIKTOK_VIDEO_URL, "TikTok", "video")
        except ValueError as e:
            raise ValueError(f"couldn't expand the short link ({e}). Open it in your browser and paste the "
                             "full link (.../@user/video/<number>)") from None
    return (*clean_tiktok_url(url), short)


def read_clips(clips_dir: Path) -> List[Tuple[Path, dict]]:
    paths = sorted(clips_dir.glob("*.json")) + sorted((clips_dir / "duplicates").glob("*.json"))
    clips = []
    for path in paths:
        try:
            clips.append((path, load_json(path)))
        except ValueError as e:
            sys.exit(f"Can't read {path}: {e}\nFix or move that file, then try again. Nothing created.")
    return clips


def known_videos(clips: List[Tuple[Path, dict]]) -> Dict[str, str]:
    """Video key -> the clip that has it, e.g. "PP-002" or "PP-012 (in duplicates/)"."""
    known = {}
    for path, clip in clips:
        key = video_key((clip.get("source") or {}).get("url"))
        if key and key not in known:
            name = clip.get("clip_id") or path.stem
            known[key] = f"{name} (in duplicates/)" if path.parent.name == "duplicates" else name
    return known


def next_number(clips: List[Tuple[Path, dict]]) -> int:
    numbers = [int(m.group(1)) for path, clip in clips
               for name in (clip.get("clip_id") or "", path.stem)
               if (m := CLIP_ID.fullmatch(name))]
    return max(numbers, default=0) + 1


def create_clip(clips_dir: Path, clip_id: str, url: str, creator: str, video_id: str,
                posted_at: Optional[str]) -> Path:
    clip = load_json(TEMPLATE_FILE)
    clip["clip_id"] = clip_id
    clip["source"].update({
        "url": url,
        "video_id": video_id,
        "platform": "tiktok",
        "creator": creator,
        "posted_at": posted_at,
        "collected_at": date.today().isoformat(),
    })
    clips_dir.mkdir(parents=True, exist_ok=True)
    target = clips_dir / f"{clip_id}.json"
    save_json(target, clip)
    return target


def valid_date(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a date like 2026-10-22") from None


def read_links(path: Path) -> List[Tuple[int, str]]:
    """(line number, link) for each line that has one. Blank lines and lines starting with # are skipped;
    anything after the link (a space, then a note) is ignored."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        sys.exit(f"Can't read {path}: {e}\nNothing created.")
    return [(n, line.split()[0]) for n, line in enumerate(text.splitlines(), 1)
            if line.strip() and not line.strip().startswith("#")]


def one_link(args):
    try:
        url, creator, video_id, short = resolve(args.url)
    except ValueError as e:
        sys.exit(f"{str(e)[:1].upper()}{str(e)[1:]}: {args.url.strip()}\nNothing created.")
    if short:
        print(f"Short link expanded: {short} -> {url}")

    clips = read_clips(args.clips_dir)
    same = known_videos(clips).get(video_key(url))
    if same:
        sys.exit(f"Duplicate: same video as {same}. Nothing created.")

    clip_id = f"PP-{next_number(clips):03d}"
    if (args.clips_dir / f"{clip_id}.json").exists():
        sys.exit(f"{args.clips_dir / clip_id}.json already exists. Nothing created.")
    shown = display_path(create_clip(args.clips_dir, clip_id, url, creator, video_id, args.posted_at))
    print(f"Created {shown}")
    print(f"  url:       {url}")
    print(f"  creator:   {creator}")
    print(f"  posted_at: {args.posted_at or 'null (stage 2 fills it from TikTok)'}")
    print(f"Next: python stage2_get_audio.py {shown}")


def link_file(args):
    links = read_links(args.from_file)
    if not links:
        sys.exit(f"No links in {args.from_file}. Nothing created.")
    clips = read_clips(args.clips_dir)  # read once, before anything is created
    known = known_videos(clips)
    new, duplicates, bad = [], [], []

    # 1. Check every link first. Only then create clips, so the report is the same with or without --check-only.
    for n, link in links:
        try:
            url, creator, video_id, short = resolve(link)
        except ValueError as e:
            bad.append(f"line {n}: {link} -> {e}")
            continue
        key = video_key(url)
        if key in known:
            duplicates.append(f"line {n}: {link} -> same video as {known[key]}")
            continue
        known[key] = f"line {n}"
        new.append((n, url, creator, video_id, short))

    # 2. Create the new ones, numbered in file order.
    created = []
    number = next_number(clips)
    lines = []
    for n, url, creator, video_id, short in new:
        expanded = f" (expanded from {short})" if short else ""
        if args.check_only:
            lines.append(f"line {n}: {url}{expanded}")
            continue
        clip_id = f"PP-{number:03d}"
        number += 1
        if (args.clips_dir / f"{clip_id}.json").exists():
            bad.append(f"line {n}: {url} -> {clip_id}.json already exists")
            continue
        path = create_clip(args.clips_dir, clip_id, url, creator, video_id, None)
        created.append(display_path(path))
        lines.append(f"line {n} -> {clip_id}: {url}{expanded}")

    print(f"{args.from_file}: {len(links)} link{'s' if len(links) != 1 else ''}")
    groups = [("new videos, to create" if args.check_only else "new videos, created", lines),
              ("duplicates, not created", duplicates),
              ("bad links, not created", bad)]
    for title, group in groups:
        print(f"{title} ({len(group)}):")
        for line in group:
            print(f"  {line}")
    if args.check_only and new:
        print("Run again without --check-only to create them.")
    if created:
        print(f"Next: python stage2_get_audio.py {' '.join(created)}")
    if bad:
        sys.exit("Fix the bad links in the file." if args.check_only else
                 "Fix the bad links in the file, then run again (the clips just created are skipped as duplicates).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", help="TikTok video link (full or short)")
    ap.add_argument("--from-file", type=Path, help="Text file with one TikTok link per line")
    ap.add_argument("--check-only", action="store_true", help="With --from-file: report only, create nothing")
    ap.add_argument("--posted-at", type=valid_date, help="Date the video was posted, e.g. 2026-10-22 "
                                                         "(one link only; stage 2 fills it otherwise)")
    ap.add_argument("--clips-dir", type=Path, default=CLIPS_DIR)
    args = ap.parse_args()

    if bool(args.url) == bool(args.from_file):
        ap.error("give one link, or --from-file, not both")
    if args.from_file and args.posted_at:
        ap.error("--posted-at works with one link only (stage 2 fills the date from TikTok)")
    if args.check_only and not args.from_file:
        ap.error("--check-only works with --from-file")
    if args.from_file:
        link_file(args)
    else:
        one_link(args)


if __name__ == "__main__":
    main()
