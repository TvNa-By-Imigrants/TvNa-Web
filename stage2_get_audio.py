#!/usr/bin/env python3
"""Stage 2: clip file -> data/audio/PP-NNN.wav (16 kHz, mono, 16-bit), ready for stage 3.
Downloads the TikTok video from the clip's source.url with yt-dlp into a temporary folder,
turns it into a WAV with ffmpeg, and sets audio_file. The video is deleted; the WAV is kept.
Also saves the TikTok caption in source.caption, fills source.posted_at when it is empty, and puts the
video's cover picture on Cloudinary (tvna/covers/PP-NNN, 720 px JPG) with its link in source.cover_url.
A clip that already has its WAV but no caption or cover gets those only (no download).
A cover that can't be saved (no Cloudinary keys in .env, no internet) is printed and tried on the next run.

Usage:
    python stage2_get_audio.py data/clips/PP-002.json
    python stage2_get_audio.py data/clips/PP-002.json data/clips/PP-003.json
    python stage2_get_audio.py data/clips/PP-002.json --force      # make the WAV again
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

import yt_dlp
from yt_dlp.networking import Request

from tvna_common import (AUDIO_DIR, CLIP_ID, IMAGE_MAX_BYTES, ClipError, cloudinary_keys, cloudinary_upload,
                         display_path, load_json, make_jpg, run_each, save_json)

CLEAN_TIKTOK_URL = re.compile(r"https://www\.tiktok\.com/@[^/?#]+/video/\d+")
SAMPLE_RATE = 16000
# Cambodia time (UTC+7, no daylight saving), so a late-night post keeps its local date.
CAMBODIA = timezone(timedelta(hours=7))
CAPTION_PREVIEW = 60
COVER_WIDTH = 720
COVER_FOLDER = "tvna/covers"


class _QuietLogger:
    """Keeps yt-dlp silent. Its errors still arrive as DownloadError."""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def fetch_cover(ydl, info: dict, dst: Path) -> Tuple[Optional[Path], Optional[str]]:
    """Save the video's cover picture, trying TikTok's best one first, with TikTok's own headers.
    Returns (file, None), (None, None) when TikTok has no cover, or (None, why) when none could be fetched."""
    pictures = [p for p in info.get("thumbnails") or [] if p.get("url")]
    if not pictures and info.get("thumbnail"):
        pictures = [{"url": info["thumbnail"]}]
    if not pictures:
        return None, None
    reason = "no picture came back"
    for picture in reversed(pictures):  # yt-dlp sorts them worst first; moving covers are the worst
        try:
            with ydl.urlopen(Request(picture["url"], headers=picture.get("http_headers") or {})) as answer:
                data = answer.read(IMAGE_MAX_BYTES + 1)
        except (yt_dlp.utils.YoutubeDLError, OSError) as e:
            reason = f"{type(e).__name__}: {e}"
            continue
        if len(data) > IMAGE_MAX_BYTES:
            reason = "the picture is over 20 MB"
        elif data:
            dst.write_bytes(data)
            return dst, None
    return None, f"couldn't download it ({reason})"


def ask_tiktok(url: str, folder: Path, video: bool, cover: bool) -> Tuple[dict, Optional[Path], Optional[str]]:
    """The video's info from TikTok. With video, the video is also downloaded into folder, with the sound
    viewers hear (voice-over and music mixed). With cover, its cover picture is saved in folder too.
    Returns (info, cover file, why there is no cover file)."""
    options = {
        # Not "bestaudio": TikTok's separate audio file is the song the video uses, without the voice-over.
        "format": "best",
        "outtmpl": str(folder / "video.%(ext)s"),
        "noplaylist": True,
        "socket_timeout": 30,
        "color": "never",
        "logger": _QuietLogger(),
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=video)
            if not cover:
                return info, None, None
            return (info, *fetch_cover(ydl, info, folder / "cover.img"))
    except yt_dlp.utils.DownloadError as e:
        reason = str(e).removeprefix("ERROR: ")
        raise ClipError(f"Download failed: {reason}\n"
                        "  Check that the link opens in your browser; the video may be deleted or private.") from None


def download(url: str, folder: Path, cover: bool) -> Tuple[Path, dict, Optional[Path], Optional[str]]:
    info, picture, problem = ask_tiktok(url, folder, True, cover)
    files = [p for p in folder.glob("video.*") if p.suffix != ".part"]
    if not files:
        raise ClipError("Download failed: yt-dlp finished but saved no file.")
    return files[0], info, picture, problem


def to_wav(video: Path, wav: Path) -> None:
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
         "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(wav)],
        capture_output=True, text=True)
    if result.returncode == 0:
        return
    if "does not contain any stream" in result.stderr:
        raise ClipError("The video has no sound, so there is nothing to transcribe.")
    lines = result.stderr.strip().splitlines()
    raise ClipError(f"ffmpeg couldn't make the WAV: {lines[-1] if lines else f'exit code {result.returncode}'}")


def check_wav(wav: Path) -> float:
    """Return the length in seconds, after checking the WAV is 16 kHz, mono, 16-bit and not empty."""
    with wave.open(str(wav), "rb") as w:
        shape = (w.getframerate(), w.getnchannels(), w.getsampwidth())
        frames = w.getnframes()
    if shape != (SAMPLE_RATE, 1, 2):
        raise ClipError(f"The WAV came out wrong (rate, channels, bytes = {shape}).")
    if frames == 0:
        raise ClipError("The WAV is empty: the video has no sound.")
    return frames / SAMPLE_RATE


def posted_date(info: dict) -> Optional[str]:
    if info.get("timestamp"):
        return datetime.fromtimestamp(info["timestamp"], CAMBODIA).date().isoformat()
    try:
        return datetime.strptime(info.get("upload_date") or "", "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def caption_text(info: dict) -> Optional[str]:
    """The creator's caption (hashtags included), NFC; null when there is none."""
    text = unicodedata.normalize("NFC", info.get("description") or "").strip()
    return text or None


def still_to_read(source: dict, key: str) -> bool:
    """A missing key (clip from before it existed) or "" = read it from TikTok. A value or null = done."""
    value = source.get(key, "")
    return isinstance(value, str) and not value.strip()


def put_after(source: dict, after: str, key: str, value) -> dict:
    """source with key set, a new key placed right after `after` (as in the clip template)."""
    if key in source:
        source[key] = value
        return source
    ordered = {}
    for k, v in source.items():
        ordered[k] = v
        if k == after:
            ordered[key] = value
    ordered.setdefault(key, value)
    return ordered


def fill_from_tiktok(clip: dict, info: dict, caption: bool = True) -> Optional[str]:
    """Save the caption (when asked) and fill posted_at if empty. Returns the posted_at it filled, if any."""
    source = clip.get("source") or {}
    if caption:
        source = put_after(source, "creator", "caption", caption_text(info))
    posted = None
    if not source.get("posted_at"):
        posted = source["posted_at"] = posted_date(info)
    clip["source"] = source
    return posted


def save_cover(clip: dict, clip_id: str, picture: Optional[Path], problem: Optional[str], keys) -> bool:
    """Put the fetched cover on Cloudinary and its link in source.cover_url (null when TikTok has none).
    Prints what happened. A cover that fails leaves cover_url as it was, so the next run tries again.
    Returns True when cover_url changed."""
    if problem:
        print(f"  cover: not saved, {problem}. The next run tries again.")
        return False
    if picture is None:
        link = None
    else:
        jpg = picture.with_name("cover.jpg")
        try:
            make_jpg(picture, jpg, COVER_WIDTH)
            link = cloudinary_upload(jpg, f"{COVER_FOLDER}/{clip_id}", keys)
        except ValueError as e:
            print(f"  cover: not saved, {e}. The next run tries again.")
            return False
    clip["source"] = put_after(clip["source"], "caption", "cover_url", link)
    print(f"  cover: {link}" if link else "  cover: none (TikTok has no cover picture for this video)")
    return True


NO_KEYS = "  cover: not saved, the Cloudinary keys are not in .env (see README, Setup)."


def has_cover_link(source: dict) -> bool:
    return isinstance(source.get("cover_url"), str) and source["cover_url"].strip() != ""


def wants_cover(source: dict, force: bool, downloading: bool) -> bool:
    """Save the cover when cover_url is missing or "", or on --force; also on a download when it has no link yet."""
    return force or still_to_read(source, "cover_url") or (downloading and not has_cover_link(source))


def print_tiktok_info(clip: dict, posted: Optional[str]) -> None:
    caption = clip["source"].get("caption")
    if caption:
        line = " ".join(caption.split())
        print(f"  caption: {line[:CAPTION_PREVIEW]}{' …' if len(line) > CAPTION_PREVIEW else ''}")
    else:
        print("  caption: none (the video has no caption)")
    if posted:
        print(f"  posted_at: {posted} (from TikTok)")


def get_audio(clip_path: Path, audio_dir: Path, force: bool) -> str:
    """Make the WAV for one clip. Returns "made" or "skipped"; raises ClipError."""
    try:
        clip = load_json(clip_path)
    except (OSError, ValueError) as e:
        raise ClipError(f"Can't read the clip file: {e}") from None
    clip_id = clip.get("clip_id") or ""
    if not CLIP_ID.fullmatch(clip_id):
        raise ClipError(f"clip_id {clip_id!r} is not like PP-001. Fix the clip file.")
    source = clip.get("source") or {}
    url = source.get("url")
    if not url:
        raise ClipError("No TikTok link in this clip (source.url is empty). Run stage 1 first.")
    if not CLEAN_TIKTOK_URL.fullmatch(url):
        raise ClipError(f"source.url is not a TikTok video link like stage 1 makes: {url}")

    old = clip.get("audio_file")
    if old and (audio_dir / old).is_file() and not force:
        need_caption = still_to_read(source, "caption")
        need_cover = wants_cover(source, False, False)
        keys = cloudinary_keys() if need_cover else None
        if not need_caption and not keys:
            print(f"{clip_id}: already has audio ({display_path(audio_dir / old)}). Skipped. "
                  "Use --force to make it again.")
            if need_cover:
                print(NO_KEYS)
            return "skipped"
        if need_cover and not keys:
            print(NO_KEYS)
        wanted = " and ".join(w for w, on in (("caption", need_caption), ("cover", keys)) if on)
        print(f"{clip_id}: already has audio; reading the {wanted} from TikTok (no download) ...")
        with tempfile.TemporaryDirectory(prefix="tvna-") as tmp:
            try:
                info, picture, problem = ask_tiktok(url, Path(tmp), False, bool(keys))
            except ClipError as e:
                print(f"{clip_id}: couldn't read the {wanted}. {e}\n  The audio is fine, so stage 3 can go on. "
                      "Skipped; nothing changed.")
                return "skipped"
            posted = fill_from_tiktok(clip, info, need_caption)
            if need_caption:
                print(f"{clip_id}: saved the caption")
                print_tiktok_info(clip, posted)
            elif posted:
                print(f"  posted_at: {posted} (from TikTok)")
            cover_changed = bool(keys) and save_cover(clip, clip_id, picture, problem, keys)
        if not (need_caption or posted or cover_changed):
            print(f"{clip_id}: Skipped; nothing changed.")
            return "skipped"
        save_json(clip_path, clip)
        return "made"

    print(f"{clip_id}: downloading {url} ...")
    target = audio_dir / f"{clip_id}.wav"
    need_cover = wants_cover(source, force, True)
    no_cover_before = bool(old) and "cover_url" in source and source["cover_url"] is None
    keys = cloudinary_keys() if need_cover else None
    with tempfile.TemporaryDirectory(prefix="tvna-") as tmp:
        video, info, picture, problem = download(url, Path(tmp), bool(keys))
        wav = Path(tmp) / "audio.wav"
        to_wav(video, wav)
        seconds = check_wav(wav)
        audio_dir.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        shutil.copyfile(wav, part)
        os.replace(part, target)

        clip["audio_file"] = target.name
        posted = fill_from_tiktok(clip, info)
        print(f"{clip_id}: saved {display_path(target)} (16 kHz, mono, {seconds:.1f} s)")
        print_tiktok_info(clip, posted)
        saved = bool(keys) and save_cover(clip, clip_id, picture, problem, keys)
        if need_cover and not keys:
            print(NO_KEYS)
        if need_cover and not saved and not has_cover_link(clip["source"]) and not no_cover_before:
            # "" (not null, which means "no cover"), so the next run tries again
            clip["source"] = put_after(clip["source"], "caption", "cover_url", "")
    save_json(clip_path, clip)
    return "made"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", type=Path, help="Clip files, e.g. data/clips/PP-002.json")
    ap.add_argument("--force", action="store_true", help="Make the WAV again even if the clip already has one")
    ap.add_argument("--audio-dir", type=Path, default=AUDIO_DIR)
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is not installed. Install it with: brew install ffmpeg (see README, Setup). Nothing changed.")

    run_each(args.clips, lambda path: get_audio(path, args.audio_dir, args.force), "python stage3_transcribe.py {clips}")


if __name__ == "__main__":
    main()
