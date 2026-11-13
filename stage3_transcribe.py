#!/usr/bin/env python3
"""Stage 3: WAV -> transcript, with Gemini. Writes only "stt" in the clip file.
Khmer is written in Khmer script and English in English letters, without translation.

Usage:
    python stage3_transcribe.py data/clips/PP-002.json
    python stage3_transcribe.py data/clips/PP-002.json data/clips/PP-003.json
    python stage3_transcribe.py data/clips/PP-002.json --force      # transcribe again
"""
import argparse
import sys
import time
import unicodedata
import wave
from pathlib import Path
from typing import Optional

from google.genai import errors, types

from tvna_common import AUDIO_DIR, ClipError, display_path, gemini_client, load_json, run_each, save_json

# First model, then the backup when it is busy. stt.model records the one that did the work.
MODELS = ["gemini-3.8-flash", "gemini-3.6-flash"]
TRIES_PER_MODEL = 3
WAITS = [10, 30]  # seconds before try 2 and try 3
TRY_TIME_LIMIT_MS = 3 * 60 * 1000
BUSY_CODES = {429, 500, 503, 504}
NO_SPEECH = "[no speech]"
SETTINGS = "km+en code-switching prompt v1"
# Google allows 20 MB per request; bigger audio is uploaded with the Files API instead.
INLINE_LIMIT = 15 * 1024 * 1024
PREVIEW_LINES = 3

PROMPT = """Transcribe this audio exactly, word by word.
The speaker mixes Khmer and English (code-switching).
Rules:
- Write Khmer words in Khmer script.
- Write English words in English letters.
- Do not translate.
- Do not add words that are not spoken.
- If a part is unclear, write [unclear].
- Put each sentence on its own line.
- Do not write song lyrics or background music.
- If nobody speaks, reply only: [no speech]"""


def find_wav(clip: dict, audio_dir: Path, clip_path: Path) -> Path:
    name = clip.get("audio_file")
    if not name:
        raise ClipError(f"No audio for this clip. Run stage 2 first: python stage2_get_audio.py {display_path(clip_path)}")
    if Path(name).name != name or not name.endswith(".wav"):
        raise ClipError(f"audio_file {name!r} should be a file name like PP-002.wav. Fix the clip file.")
    wav = audio_dir / name
    if not wav.is_file():
        raise ClipError(f"No audio: {display_path(wav)} is missing. "
                        f"Run stage 2 first: python stage2_get_audio.py {display_path(clip_path)}")
    return wav


def seconds(wav: Path) -> float:
    try:
        with wave.open(str(wav), "rb") as w:
            return w.getnframes() / w.getframerate()
    except (wave.Error, EOFError) as e:
        raise ClipError(f"{display_path(wav)} is not a valid WAV ({e}). Run stage 2 again with --force.") from None


def ask_model(client, model: str, audio) -> Optional[str]:
    """Up to TRIES_PER_MODEL tries. Returns the reply text, or None when the model stays busy or is not found."""
    config = types.GenerateContentConfig(http_options=types.HttpOptions(timeout=TRY_TIME_LIMIT_MS))
    for attempt in range(1, TRIES_PER_MODEL + 1):
        try:
            return client.models.generate_content(model=model, contents=[PROMPT, audio], config=config).text or ""
        except errors.APIError as e:
            if e.code == 404:
                print(f"  {model} was not found.", flush=True)
                return None
            if e.code not in BUSY_CODES:
                raise ClipError(f"Gemini failed: {e.code} {e.status}: {e.message}") from None
            reason = f"busy ({e.code})"
        except Exception as e:
            reason = f"not answering ({type(e).__name__})"
        if attempt < TRIES_PER_MODEL:
            wait = WAITS[attempt - 1]
            print(f"  {model} is {reason}, trying again in {wait} s ({attempt + 1}/{TRIES_PER_MODEL})", flush=True)
            time.sleep(wait)
        else:
            print(f"  {model} is still {reason}.", flush=True)
    return None


def transcribe(client, wav: Path, models: list) -> tuple:
    """Return (transcript, model used). Tries each model in turn while the earlier ones are busy."""
    uploaded = None
    try:
        if wav.stat().st_size <= INLINE_LIMIT:
            audio = types.Part.from_bytes(data=wav.read_bytes(), mime_type="audio/wav")
        else:
            try:
                audio = uploaded = client.files.upload(file=str(wav), config=types.UploadFileConfig(mime_type="audio/wav"))
            except Exception as e:
                raise ClipError(f"Couldn't upload the audio to Gemini: {e}") from None
        for i, model in enumerate(models):
            if i:
                print(f"  Trying {model} instead ...", flush=True)
            text = ask_model(client, model, audio)
            if text is not None:
                break
        else:
            raise ClipError(f"Gemini is busy (tried {', '.join(models)}). Run the same command again later: "
                            "clips that already have a transcript are skipped.")
    finally:
        if uploaded:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass  # Google deletes uploads after 48 hours anyway.
    text = text.strip()
    if not text:
        raise ClipError("Gemini returned no transcript. Try again later, or listen to the WAV: does it have speech?")
    if text.lower().rstrip(".") == NO_SPEECH:
        return NO_SPEECH, model
    return unicodedata.normalize("NFC", text), model


def transcribe_clip(client, clip_path: Path, audio_dir: Path, models: list, force: bool) -> str:
    """Write the transcript for one clip. Returns "made" or "skipped"; raises ClipError."""
    try:
        clip = load_json(clip_path)
    except (OSError, ValueError) as e:
        raise ClipError(f"Can't read the clip file: {e}") from None
    clip_id = clip.get("clip_id") or clip_path.stem

    if (clip.get("stt") or {}).get("transcript") and not force:
        print(f"{clip_id}: already has a transcript. Skipped. Use --force to transcribe again.")
        return "skipped"

    wav = find_wav(clip, audio_dir, clip_path)
    print(f"{clip_id}: transcribing {display_path(wav)} ({seconds(wav):.1f} s) with {models[0]} ...", flush=True)
    text, model = transcribe(client, wav, models)

    clip["stt"] = {"tool": "gemini", "model": model, "settings": SETTINGS, "transcript": text}
    save_json(clip_path, clip)

    if text == NO_SPEECH:
        print(f"{clip_id}: no speech (music only). Saved the transcript as {NO_SPEECH}.")
        return "made"
    lines = text.splitlines()
    print(f"{clip_id}: saved transcript ({len(lines)} lines, {model})")
    for line in lines[:PREVIEW_LINES]:
        print(f"  {line}")
    if len(lines) > PREVIEW_LINES:
        print("  ...")
    return "made"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", type=Path, help="Clip files, e.g. data/clips/PP-002.json")
    ap.add_argument("--force", action="store_true", help="Transcribe again even if the clip has a transcript")
    ap.add_argument("--model", default=MODELS[0], help=f"Gemini model to try first (default {MODELS[0]})")
    ap.add_argument("--audio-dir", type=Path, default=AUDIO_DIR)
    args = ap.parse_args()
    models = [args.model] + [m for m in MODELS if m != args.model]

    try:
        client = gemini_client(attempts=1)
    except ValueError:
        sys.exit("GEMINI_API_KEY is missing. Add it to .env (see README, Setup). Nothing changed.")

    run_each(args.clips, lambda path: transcribe_clip(client, path, args.audio_dir, models, args.force),
             "python stage4_extract_places.py")


if __name__ == "__main__":
    main()
