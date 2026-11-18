"""Shared helpers for the TVNA pipeline scripts (see docs/tvna_field_guide.md)."""
import difflib
import http.client
import json
import re
import shlex
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
REFERENCE_DIR = DATA_DIR / "reference"  # fixed lists, set once
RESULTS_DIR = DATA_DIR / "results"  # made by stages 5c and 6
AREAS_FILE = REFERENCE_DIR / "areas.json"
PLACES_FILE = RESULTS_DIR / "places.json"
FINAL_DATASET_FILE = RESULTS_DIR / "final_dataset.json"
CLIPS_DIR = DATA_DIR / "clips"
AUDIO_DIR = DATA_DIR / "audio"
GEMINI_ANSWERS_DIR = DATA_DIR / "gemini_answers"  # stage 4's places exactly as Gemini gave them, never edited

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

USER_AGENT = "tvna-pipeline/0.1"
MAX_REDIRECTS = 5

# Spellings that mean the same, so names match either way (add Khmer pairs the team finds here).
SAME_LETTERS = {"ឲ": "ឱ", "&": "and"}
KHMER = re.compile(r"[ក-៿]")
# The place code in a full Google Maps link (e.g. .../data=...!1s0x3109513dc76a6be3:0xeac5420f72706db0!...).
MAPS_PLACE_CODE = re.compile(r"(?:!1s|[?&]ftid=)(0x[0-9a-f]+:0x[0-9a-f]+)|[?&](query_place_id|cid)=([^&#]+)", re.I)
MAPS_SHORT_HOSTS = {"maps.app.goo.gl", "goo.gl"}

GEMINI_TRIES_PER_MODEL = 3
GEMINI_WAITS = [10, 30]  # seconds before try 2 and try 3
GEMINI_TRY_TIME_LIMIT_MS = 3 * 60 * 1000
GEMINI_BUSY_CODES = {429, 500, 503, 504}


def norm(s: Optional[str]) -> str:
    """Compare form of a text; a value that is not text (typed by hand) -> ""."""
    return "".join(unicodedata.normalize("NFC", s if isinstance(s, str) else "").split()).lower()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
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


def retry_command(failed: List[Path], clip_paths: List[Path]) -> str:
    """The command that was run, with only the clips that failed. Options such as --force are kept."""
    given = set(clip_paths)
    options = [a for a in sys.argv[1:] if Path(a) not in given]
    words = [sys.argv[0], *(display_path(p) for p in failed), *options]
    return "python " + " ".join(shlex.quote(w) for w in words)


def run_each(clip_paths: List[Path], work: Callable[[Path], str], next_command: str) -> None:
    """Run work() on each clip; it returns "made" or "skipped", or raises ClipError.
    One failing clip doesn't stop the others. Prints a summary, the next command ("{clips}" becomes
    the clips that worked) and the command to try only the failed clips again; exits 1 if any failed."""
    ok, failed, counts = [], [], {"made": 0, "skipped": 0}
    for path in clip_paths:
        try:
            counts[work(path)] += 1
            ok.append(display_path(path))
        except ClipError as e:
            print(f"{path.stem}: {e}\n  Nothing changed in {display_path(path)}.")
            failed.append(path)

    if len(clip_paths) > 1:
        print(f"Done: {counts['made']} made, {counts['skipped']} skipped, {len(failed)} failed"
              + (f" ({', '.join(p.stem for p in failed)})" if failed else ""))
    if ok:
        print(f"Next: {next_command.format(clips=' '.join(ok))}")
    if failed:
        print(f"To try only the failed clip{'s' if len(failed) > 1 else ''} again: {retry_command(failed, clip_paths)}")
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


def text_or_none(value) -> Optional[str]:
    """Text without outside spaces. "", only spaces, null or a value that is not text (typed by hand) -> None."""
    return (value.strip() or None) if isinstance(value, str) else None


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


def has_places(clip: dict) -> bool:
    """Stage 4 has run on this clip ([] = it ran and found no place). null, "" or a missing key = not yet."""
    return isinstance(clip.get("fields"), list)


def is_rejected(place: dict) -> bool:
    return place.get("verification_status") == "rejected"


def is_verified(place: dict) -> bool:
    """The team checked this place in stage 5b and approved it. Only these get a place_id and reach the website."""
    return place.get("verification_status") == "verified"


def reviewed_places(clip: dict) -> List[dict]:
    """Places the team checked in stage 5b: a name in cleaned_by, or status verified."""
    return [p for p in clip.get("fields") or [] if p.get("cleaned_by") or is_verified(p)]


def skip_reviewed(clip: dict, clip_id: str) -> bool:
    """True (and says so) when the team reviewed a place in this clip, so a stage must not redo it."""
    n = len(reviewed_places(clip))
    if n:
        print(f"{clip_id}: {n} place{'s were' if n > 1 else ' was'} reviewed by the team. "
              "Skipped, so their fixes are kept.")
    return n > 0


def video_key(url: Optional[str]) -> Optional[str]:
    """Same TikTok video -> same key (its video id). Other links, e.g. short links, use the address."""
    if not url:
        return None
    m = TIKTOK_VIDEO_ID.search(url)
    if m:
        return f"tiktok:{m.group(1)}"
    parts = urlsplit(url.strip())
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}?{parts.query}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def follow_redirects(url: str, wanted: re.Pattern, site: str, thing: str) -> str:
    """Follow a short link's redirects (without opening the page) until a link matching `wanted` appears.
    Raises ValueError with a short reason."""
    opener = urllib.request.build_opener(_NoRedirect)
    current = url
    for _ in range(MAX_REDIRECTS):
        request = urllib.request.Request(current, headers={"User-Agent": USER_AGENT})
        try:
            with opener.open(request, timeout=15):
                raise ValueError(f"{site} did not redirect to a {thing}")
        except urllib.error.HTTPError as e:
            location = e.headers.get("Location")
            if e.code not in (301, 302, 303, 307, 308) or not location:
                raise ValueError(f"{site} answered {e.code} {e.reason}") from None
            current = urljoin(current, location)
        except urllib.error.URLError as e:
            raise ValueError(f"no connection ({e.reason})") from None
        except (OSError, http.client.HTTPException) as e:  # e.g. a timeout while reading the answer
            raise ValueError(f"no connection ({type(e).__name__})") from None
        if wanted.search(current):
            return current
    raise ValueError(f"too many redirects, no {thing} link found")


def name_key(name: Optional[str]) -> str:
    """A place name ready to compare: lowercase, no spaces, punctuation or symbols, é = e, & = and.
    Khmer vowel signs and the coeng stay: dropping them would make different names look the same."""
    text = unicodedata.normalize("NFD", name or "")
    text = "".join(ch for ch in text if not "̀" <= ch <= "ͯ")  # accents on Latin letters only
    text = unicodedata.normalize("NFC", text).lower()
    for spelling, same in SAME_LETTERS.items():
        text = text.replace(spelling, same)
    return "".join(ch for ch in text if unicodedata.category(ch)[0] not in "PZSC")


def name_score(a: Optional[str], b: Optional[str]) -> int:
    """How alike two place names are, 0-100 (100 = the same after name_key). Rounded down, so 94.7 is not a 95."""
    return int(difflib.SequenceMatcher(None, name_key(a), name_key(b)).ratio() * 100)


def has_khmer(text: Optional[str]) -> bool:
    return bool(KHMER.search(text or ""))


def maps_key(url: Optional[str]) -> Optional[str]:
    """The place code in a Google Maps link, the same for every link to one place. Short Share links
    (maps.app.goo.gl) are followed first. None for no link; ValueError if the link has no place code."""
    if not url or not url.strip():
        return None
    url = url.strip()
    if not MAPS_PLACE_CODE.search(url) and urlsplit(url).netloc.lower() in MAPS_SHORT_HOSTS:
        url = follow_redirects(url, MAPS_PLACE_CODE, "Google Maps", "place")
    m = MAPS_PLACE_CODE.search(url)
    if not m:
        raise ValueError("no place code in this link (use the Share link of the place)")
    return f"fid:{m.group(1).lower()}" if m.group(1) else f"{m.group(2).lower()}:{m.group(3)}"


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
    raise ClipError(f"Gemini is busy (tried {', '.join(models)}). Try this clip again later.")
