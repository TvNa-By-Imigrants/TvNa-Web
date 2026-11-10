#!/usr/bin/env python3
"""Stage 1: paste a TikTok link -> a new clip file data/clips/PP-NNN.json (from templates/tvna_clip_template.json).
Short links (vt.tiktok.com, vm.tiktok.com) are expanded first. The link is cleaned to
https://www.tiktok.com/@user/video/<id> and checked against every clip in data/clips/ and
data/clips/duplicates/. A video that is already there is not added again.

Usage:
    python stage1_new_clip.py "https://www.tiktok.com/@user/video/7593339174695046416"
    python stage1_new_clip.py "https://vt.tiktok.com/ZSpfUj3du/" --posted-at 2026-10-22
"""
import argparse
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urljoin, urlsplit

from tvna_common import CLIPS_DIR, TEMPLATES_DIR, display_path, load_json, save_json, video_key

TEMPLATE_FILE = TEMPLATES_DIR / "tvna_clip_template.json"
TIKTOK_VIDEO_URL = re.compile(r"tiktok\.com/(@[^/?#]+)/video/(\d+)")
CLIP_ID = re.compile(r"PP-(\d+)")
USER_AGENT = "tvna-pipeline/0.1"
MAX_REDIRECTS = 5


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def is_tiktok(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.netloc.lower()
    return parts.scheme in ("http", "https") and (host == "tiktok.com" or host.endswith(".tiktok.com"))


def expand_short_link(url: str) -> str:
    """Follow TikTok's redirects (without opening the page) until a /@user/video/<id> link appears."""
    opener = urllib.request.build_opener(_NoRedirect)
    current = url
    for _ in range(MAX_REDIRECTS):
        request = urllib.request.Request(current, headers={"User-Agent": USER_AGENT})
        try:
            with opener.open(request, timeout=15):
                raise ValueError("TikTok did not redirect to a video")
        except urllib.error.HTTPError as e:
            location = e.headers.get("Location")
            if e.code not in (301, 302, 303, 307, 308) or not location:
                raise ValueError(f"TikTok answered {e.code} {e.reason}") from None
            current = urljoin(current, location)
        except urllib.error.URLError as e:
            raise ValueError(f"no connection ({e.reason})") from None
        if TIKTOK_VIDEO_URL.search(current):
            return current
    raise ValueError("too many redirects, no video link found")


def clean_tiktok_url(url: str) -> Tuple[str, str]:
    """Return the link without tracking parts, and the creator handle."""
    m = TIKTOK_VIDEO_URL.search(url)
    if not m:
        raise ValueError("not a TikTok video link")
    handle, video_id = m.groups()
    return f"https://www.tiktok.com/{handle}/video/{video_id}", handle


def read_clips(clips_dir: Path) -> List[Tuple[Path, dict]]:
    paths = sorted(clips_dir.glob("*.json")) + sorted((clips_dir / "duplicates").glob("*.json"))
    clips = []
    for path in paths:
        try:
            clips.append((path, load_json(path)))
        except ValueError as e:
            sys.exit(f"Can't read {path}: {e}\nFix or move that file, then try again. Nothing created.")
    return clips


def next_clip_id(clips: List[Tuple[Path, dict]]) -> str:
    numbers = [int(m.group(1)) for path, clip in clips
               for name in (clip.get("clip_id") or "", path.stem)
               if (m := CLIP_ID.fullmatch(name))]
    return f"PP-{max(numbers, default=0) + 1:03d}"


def valid_date(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a date like 2026-10-22") from None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="TikTok video link (full or short)")
    ap.add_argument("--posted-at", type=valid_date, help="Date the video was posted, e.g. 2026-10-22")
    ap.add_argument("--clips-dir", type=Path, default=CLIPS_DIR)
    args = ap.parse_args()

    url = args.url.strip()
    if not is_tiktok(url):
        sys.exit(f"Only TikTok links are in scope: {url}\nNothing created.")

    if not TIKTOK_VIDEO_URL.search(url):
        try:
            short, url = url, expand_short_link(url)
        except ValueError as e:
            sys.exit(f"Couldn't expand the short link: {e}\n"
                     "Open it in your browser and paste the full link (.../@user/video/<number>). Nothing created.")
        print(f"Short link expanded: {short} -> {url}")
    url, creator = clean_tiktok_url(url)

    clips = read_clips(args.clips_dir)
    key = video_key(url)
    for path, clip in clips:
        if video_key((clip.get("source") or {}).get("url")) == key:
            sys.exit(f"Duplicate: same video as {clip.get('clip_id')} ({path}). Nothing created.")

    clip_id = next_clip_id(clips)
    target = args.clips_dir / f"{clip_id}.json"
    if target.exists():
        sys.exit(f"{target} already exists. Nothing created.")

    clip = load_json(TEMPLATE_FILE)
    clip["clip_id"] = clip_id
    clip["source"].update({
        "url": url,
        "platform": "tiktok",
        "creator": creator,
        "posted_at": args.posted_at,
        "collected_at": date.today().isoformat(),
    })
    args.clips_dir.mkdir(parents=True, exist_ok=True)
    save_json(target, clip)

    shown = display_path(target)
    print(f"Created {shown}")
    print(f"  url:       {url}")
    print(f"  creator:   {creator}")
    print(f"  posted_at: {args.posted_at or 'null (add it by hand, or use --posted-at)'}")
    print(f"Next: python stage2_get_audio.py {shown}")


if __name__ == "__main__":
    main()
