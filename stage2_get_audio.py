#!/usr/bin/env python3
"""Stage 2: clip file -> data/audio/PP-NNN.wav (16 kHz, mono, 16-bit), ready for stage 3.
Downloads the TikTok video from the clip's source.url with yt-dlp into a temporary folder,
turns it into a WAV with ffmpeg, and sets audio_file. The video is deleted; the WAV is kept.
Also saves the TikTok caption in source.caption, and fills source.posted_at when it is empty.
A clip that already has its WAV but no caption gets the caption only (no download).

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

from tvna_common import AUDIO_DIR, CLIP_ID, ClipError, display_path, load_json, run_each, save_json

CLEAN_TIKTOK_URL = re.compile(r"https://www\.tiktok\.com/@[^/?#]+/video/\d+")
SAMPLE_RATE = 16000
# Cambodia time (UTC+7, no daylight saving), so a late-night post keeps its local date.
CAMBODIA = timezone(timedelta(hours=7))
CAPTION_PREVIEW = 60


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


def ask_tiktok(url: str, folder: Optional[Path]) -> dict:
    """The video's info from TikTok. With a folder, the video is also downloaded into it, with the sound
    viewers hear (voice-over and music mixed)."""
    options = {
        # Not "bestaudio": TikTok's separate audio file is the song the video uses, without the voice-over.
        "format": "best",
        "outtmpl": str((folder or Path(tempfile.gettempdir())) / "video.%(ext)s"),
        "noplaylist": True,
        "socket_timeout": 30,
        "color": "never",
        "logger": _QuietLogger(),
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=folder is not None)
    except yt_dlp.utils.DownloadError as e:
        reason = str(e).removeprefix("ERROR: ")
        raise ClipError(f"Download failed: {reason}\n"
                        "  Check that the link opens in your browser; the video may be deleted or private.") from None


def download(url: str, folder: Path) -> Tuple[Path, dict]:
    info = ask_tiktok(url, folder)
    files = [p for p in folder.glob("video.*") if p.suffix != ".part"]
    if not files:
        raise ClipError("Download failed: yt-dlp finished but saved no file.")
    return files[0], info


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


def fill_from_tiktok(clip: dict, info: dict) -> Optional[str]:
    """Save the caption (kept right after creator, as in the template) and fill posted_at if empty.
    Returns the posted_at it filled, if any."""
    source = clip.get("source") or {}
    caption = caption_text(info)
    if "caption" in source:
        source["caption"] = caption
    else:
        ordered = {}
        for key, value in source.items():
            ordered[key] = value
            if key == "creator":
                ordered["caption"] = caption
        ordered.setdefault("caption", caption)
        source = ordered
    posted = None
    if not source.get("posted_at"):
        posted = source["posted_at"] = posted_date(info)
    clip["source"] = source
    return posted


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
        if source.get("caption"):
            print(f"{clip_id}: already has audio ({display_path(audio_dir / old)}). Skipped. "
                  "Use --force to make it again.")
            return "skipped"
        print(f"{clip_id}: already has audio; reading the caption from TikTok (no download) ...")
        posted = fill_from_tiktok(clip, ask_tiktok(url, None))
        save_json(clip_path, clip)
        print(f"{clip_id}: saved the caption")
        print_tiktok_info(clip, posted)
        return "made"

    print(f"{clip_id}: downloading {url} ...")
    target = audio_dir / f"{clip_id}.wav"
    with tempfile.TemporaryDirectory(prefix="tvna-") as tmp:
        video, info = download(url, Path(tmp))
        wav = Path(tmp) / "audio.wav"
        to_wav(video, wav)
        seconds = check_wav(wav)
        audio_dir.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        shutil.copyfile(wav, part)
        os.replace(part, target)

    clip["audio_file"] = target.name
    posted = fill_from_tiktok(clip, info)
    save_json(clip_path, clip)

    print(f"{clip_id}: saved {display_path(target)} (16 kHz, mono, {seconds:.1f} s)")
    print_tiktok_info(clip, posted)
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
