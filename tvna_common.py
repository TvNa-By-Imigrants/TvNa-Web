"""Shared helpers for the TVNA pipeline scripts (see docs/tvna_field_guide.md)."""
import json
import re
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple
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


def gemini_client():
    """Gemini client with GEMINI_API_KEY from .env. Retries busy/temporary errors (429, 5xx) with growing waits."""
    # Imported here so the scripts that never call Gemini don't load the package.
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types

    load_dotenv(BASE_DIR / ".env")
    return genai.Client(http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=5)))
