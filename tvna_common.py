"""Shared helpers for the TVNA pipeline scripts (see docs/tvna_field_guide.md)."""
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
AREAS_FILE = DATA_DIR / "areas.json"
PLACES_FILE = DATA_DIR / "places.json"
CLIPS_DIR = DATA_DIR / "clips"
AUDIO_DIR = DATA_DIR / "audio"

CATEGORIES = [
    "restaurant", "cafe", "bar", "street_food",
    "temple", "museum", "park", "viewpoint", "beach",
    "market", "mall", "shop",
    "entertainment", "hotel", "other",
]

COMPLETENESS_FIELDS = ["place_name", "area", "speaker_opinion"]

TIKTOK_VIDEO_ID = re.compile(r"tiktok\.com/.*/video/(\d+)")
CLIP_ID = re.compile(r"PP-(\d+)")
NO_SPEECH = "[no speech]"  # stage 3's transcript for a video where nobody speaks

GEMINI_TRIES_PER_MODEL = 3
GEMINI_WAITS = [10, 30]  # seconds before try 2 and try 3
GEMINI_TRY_TIME_LIMIT_MS = 3 * 60 * 1000
GEMINI_BUSY_CODES = {429, 500, 503, 504}


def norm(s: Optional[str]) -> str:
    return "".join(unicodedata.normalize("NFC", s or "").split()).lower()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def display_path(path) -> str:
    """Path relative to the current folder when it is inside it, else the full path."""
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


class ClipError(Exception):
    """This clip can't be done. The message says why; the clip file is not changed."""


def run_each(clip_paths: List[Path], work: Callable[[Path], str], next_command: str) -> None:
    """Run work() on each clip; it returns "made" or "skipped", or raises ClipError.
    One failing clip doesn't stop the others. Prints a summary and the next command ("{clips}" becomes
    the clips that worked); exits 1 if any failed."""
    ok, failed, counts = [], [], {"made": 0, "skipped": 0}
    for path in clip_paths:
        try:
            counts[work(path)] += 1
            ok.append(display_path(path))
        except ClipError as e:
            print(f"{path.stem}: {e}\n  Nothing changed in {display_path(path)}.")
            failed.append(path.stem)

    if len(clip_paths) > 1:
        print(f"Done: {counts['made']} made, {counts['skipped']} skipped, {len(failed)} failed"
              + (f" ({', '.join(failed)})" if failed else ""))
    if ok:
        print(f"Next: {next_command.format(clips=' '.join(ok))}")
    if failed:
        sys.exit(1)


def load_areas(path=AREAS_FILE) -> List[dict]:
    return load_json(path)


def match_district(text: Optional[str], areas: List[dict]) -> Optional[str]:
    """Return the exact district name if text equals a district (English or Khmer), else None."""
    key = norm(text)
    if not key:
        return None
    for a in areas:
        if key in (norm(a["district"]), norm(a["district_km"])):
            return a["district"]
    return None


def as_list(value) -> list:
    """None -> [], one value -> [value], list -> list (for fields the team may type by hand)."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def match_districts(values, areas: List[dict]) -> Tuple[List[str], List[str]]:
    """Split values into exact district names (no repeats) and values that are not districts."""
    matched, unmatched = [], []
    for v in as_list(values):
        district = match_district(v, areas)
        if district and district not in matched:
            matched.append(district)
        elif not district and v:
            unmatched.append(v)
    return matched, unmatched


def completeness(place: dict) -> Tuple[float, List[str]]:
    missing = [f for f in COMPLETENESS_FIELDS if not place.get(f)]
    filled = len(COMPLETENESS_FIELDS) - len(missing)
    return round(filled / len(COMPLETENESS_FIELDS), 2), missing


def verification_status(place: dict, score: float) -> str:
    if not place.get("place_name") or score < 0.3:
        return "rejected"
    if score <= 0.7:
        return "needs_review"
    return "auto_added"


def video_key(url: Optional[str]) -> Optional[str]:
    """Same TikTok video -> same key (its video id). Other links, e.g. short links, use the address."""
    if not url:
        return None
    m = TIKTOK_VIDEO_ID.search(url)
    if m:
        return f"tiktok:{m.group(1)}"
    parts = urlsplit(url.strip())
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}?{parts.query}"


def gemini_client(attempts: int = 5):
    """Gemini client with GEMINI_API_KEY from .env. Retries busy/temporary errors (429, 5xx) with growing waits.
    attempts=1 turns the built-in retries off, for scripts that retry and report by themselves."""
    # Imported here so the scripts that never call Gemini don't load the package.
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types

    load_dotenv(BASE_DIR / ".env")
    return genai.Client(http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=attempts)))


def models_in_order(first: str, models: List[str]) -> List[str]:
    """The chosen model first, then the others as backups."""
    return [first] + [m for m in models if m != first]


def generate_with_backup(client, models: List[str], contents, config=None):
    """Ask Gemini, trying each model in turn while the earlier ones are busy. Every wait is printed.
    Returns (response, model used). Raises ClipError when all models stay busy, or on any other API error.
    Use with gemini_client(attempts=1), so the waits are not doubled by the library's own retries."""
    from google.genai import errors, types

    config = (config or types.GenerateContentConfig()).model_copy(
        update={"http_options": types.HttpOptions(timeout=GEMINI_TRY_TIME_LIMIT_MS)})
    for i, model in enumerate(models):
        if i:
            print(f"  Trying {model} instead ...", flush=True)
        for attempt in range(1, GEMINI_TRIES_PER_MODEL + 1):
            try:
                return client.models.generate_content(model=model, contents=contents, config=config), model
            except errors.APIError as e:
                if e.code == 404:
                    print(f"  {model} was not found.", flush=True)
                    break
                if e.code not in GEMINI_BUSY_CODES:
                    raise ClipError(f"Gemini failed: {e.code} {e.status}: {e.message}") from None
                reason = f"busy ({e.code})"
            except Exception as e:
                reason = f"not answering ({type(e).__name__})"
            if attempt < GEMINI_TRIES_PER_MODEL:
                wait = GEMINI_WAITS[attempt - 1]
                print(f"  {model} is {reason}, trying again in {wait} s ({attempt + 1}/{GEMINI_TRIES_PER_MODEL})",
                      flush=True)
                time.sleep(wait)
            else:
                print(f"  {model} is still {reason}.", flush=True)
    raise ClipError(f"Gemini is busy (tried {', '.join(models)}). Run the same command again later: "
                    "clips that are already done are skipped.")
