"""What the team does to a place after stage 5c: add, remove and order its photos (1 to 5).
Used by stage5d_add_photo.py now, and by the review page later, so both follow the same rules.
Every message the team sees is in review/texts_en.json."""
import functools
import hashlib
import http.client
import json
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

from tvna_common import (
    BASE_DIR,
    IMAGE_MAX_BYTES,
    PLACE_ID,
    PLACES_DIR,
    USER_AGENT,
    cloudinary_keys,
    cloudinary_upload,
    display_path,
    load_json,
    make_jpg,
    place_file,
    save_json,
    text_or_none,
)

TEXTS_FILE = BASE_DIR / "review" / "texts_en.json"
MAX_PHOTOS = 5
PHOTO_WIDTH = 1200
MIN_SIDE = 600
SOURCES = ["Google Maps", "Shop's own page", "Own photo"]
OTHER = "Other:"
PHOTO_FOLDER = "tvna/places"


class PhotoError(Exception):
    """The photo can't be added (or removed, moved). The message says why; the place file is not changed."""


@functools.lru_cache(maxsize=None)
def _texts() -> dict:
    return load_json(TEXTS_FILE)


def text(key: str, **values) -> str:
    return _texts()[key].format(**values)


def show(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def photos_of(place: dict) -> list:
    """The place's photos; null, "" or a missing key = none yet. Anything else that is not a list is refused."""
    value = place.get("photos")
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise PhotoError(text("check.not_list", value=show(value)))
    return value


def source_ok(source) -> bool:
    if not isinstance(source, str):
        return False
    if source.startswith(OTHER):
        return bool(source[len(OTHER):].strip())
    return source in SOURCES


def check_source(source) -> str:
    source = text_or_none(source)
    if not source_ok(source):
        raise PhotoError(text("photo.bad_source", sources=", ".join(SOURCES), source=show(source)))
    return source


def read_place(place_id: str, folder: Path) -> Tuple[Path, bytes, dict]:
    """(file, its bytes as read, the place). The bytes let a save refuse when someone changed the file meanwhile."""
    path = place_file(folder, place_id) if isinstance(place_id, str) and PLACE_ID.fullmatch(place_id) else None
    try:
        raw = path.read_bytes()
        place = json.loads(raw)
    except (AttributeError, OSError, ValueError):
        raise PhotoError(text("photo.no_place", place_id=show(place_id),
                              file=display_path(path) if path else "?")) from None
    if not isinstance(place, dict) or place.get("place_id") != place_id:
        raise PhotoError(text("photo.no_place", place_id=show(place_id), file=display_path(path)))
    return path, raw, place


def save_place(path: Path, raw: bytes, place: dict) -> None:
    if path.read_bytes() != raw:
        raise PhotoError(text("photo.changed", file=display_path(path)))
    save_json(path, place)


def size_mb(n: int) -> str:
    return f"{n / 1024 / 1024:.1f}"


def get_image(image: str, dst: Path) -> None:
    """Copy a photo file, or download a photo link, into dst (20 MB at most)."""
    if image.startswith(("http://", "https://")):
        request = urllib.request.Request(image, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as answer:
                if (answer.headers.get("Content-Type") or "").strip().lower().startswith("text/"):
                    raise PhotoError(text("photo.web_page"))
                data = answer.read(IMAGE_MAX_BYTES + 1)
                if len(data) > IMAGE_MAX_BYTES:
                    raise PhotoError(text("photo.too_big", size="over 20"))
                expected = answer.headers.get("Content-Length")
                if expected and expected.isdigit() and len(data) < int(expected):
                    raise PhotoError(text("photo.download_failed", reason="cut off, try again"))
        except urllib.error.HTTPError as e:
            raise PhotoError(text("photo.download_failed", reason=f"{e.code} {e.reason}")) from None
        except urllib.error.URLError as e:
            raise PhotoError(text("photo.download_failed", reason=f"no connection: {e.reason}")) from None
        except (OSError, ValueError, http.client.HTTPException) as e:
            raise PhotoError(text("photo.download_failed", reason=type(e).__name__)) from None
        dst.write_bytes(data)
        return
    src = Path(image).expanduser()
    if not src.is_file():
        raise PhotoError(text("photo.no_file", image=image))
    if src.stat().st_size > IMAGE_MAX_BYTES:
        raise PhotoError(text("photo.too_big", size=size_mb(src.stat().st_size)))
    shutil.copyfile(src, dst)


def add_photo(place_id: str, image: str, source: str, credit: str, folder: Path = PLACES_DIR) -> dict:
    """Check the photo, make it a 1200 px JPG (no EXIF), put it on Cloudinary and add {url, source, credit, sha256}
    to the place file. Returns the new entry. Raises PhotoError; then nothing is saved."""
    path, raw, place = read_place(place_id, folder)
    photos = photos_of(place)
    if len(photos) >= MAX_PHOTOS:
        raise PhotoError(text("photo.full", max=MAX_PHOTOS))
    source = check_source(source)
    credit = text_or_none(credit)
    if not credit:
        raise PhotoError(text("photo.no_credit"))
    keys = cloudinary_keys()
    if not keys:
        raise PhotoError(text("photo.no_keys"))
    with tempfile.TemporaryDirectory(prefix="tvna-") as tmp:
        original, jpg = Path(tmp) / "original", Path(tmp) / "photo.jpg"
        get_image(image, original)
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        for number, photo in enumerate(photos, 1):
            if isinstance(photo, dict) and photo.get("sha256") == digest:
                raise PhotoError(text("photo.duplicate", number=number))
        try:
            width, height = make_jpg(original, jpg, PHOTO_WIDTH)
        except ValueError as e:
            raise PhotoError(text("photo.unreadable", reason=str(e).removeprefix("can't read this picture (").removesuffix(")"))) from None
        if min(width, height) < MIN_SIDE:
            raise PhotoError(text("photo.too_small", width=width, height=height, min=MIN_SIDE))
        try:
            url = cloudinary_upload(jpg, f"{PHOTO_FOLDER}/{place_id}-{digest[:10]}", keys)
        except ValueError as e:
            raise PhotoError(text("photo.upload_failed", reason=str(e))) from None
    entry = {"url": url, "source": source, "credit": credit, "sha256": digest}
    place["photos"] = photos + [entry]
    save_place(path, raw, place)
    return entry


def photo_at(photos: list, number) -> int:
    """The list index of photo number (1 = the first)."""
    if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= len(photos):
        raise PhotoError(text("photo.bad_number", number=number, count=len(photos)))
    return number - 1


def peek_photo(place_id: str, number: int, folder: Path = PLACES_DIR) -> dict:
    """The photo before removing it, to ask the person first."""
    _, _, place = read_place(place_id, folder)
    photos = photos_of(place)
    photo = photos[photo_at(photos, number)]
    return photo if isinstance(photo, dict) else {"url": photo}


def remove_photo(place_id: str, number: int, folder: Path = PLACES_DIR) -> dict:
    """Take photo number off the place (e.g. a wrong photo just added). The picture stays on Cloudinary."""
    path, raw, place = read_place(place_id, folder)
    photos = photos_of(place)
    removed = photos.pop(photo_at(photos, number))
    place["photos"] = photos
    save_place(path, raw, place)
    return removed if isinstance(removed, dict) else {"url": removed}


def move_photo(place_id: str, number: int, to: int, folder: Path = PLACES_DIR) -> List[dict]:
    """Move photo number to position `to` (photo 1 is the main one on the website)."""
    path, raw, place = read_place(place_id, folder)
    photos = photos_of(place)
    photo = photos.pop(photo_at(photos, number))
    photos.insert(photo_at(photos + [None], to), photo)
    place["photos"] = photos
    save_place(path, raw, place)
    return photos


def photo_problems(place: dict) -> Tuple[Optional[int], List[str]]:
    """(number of photos or None when photos is not a list, problems) for the checker and the review page."""
    try:
        photos, problems = photos_of(place), []
    except PhotoError as e:
        return None, [str(e)]
    if len(photos) > MAX_PHOTOS:
        problems.append(text("check.too_many", count=len(photos), max=MAX_PHOTOS, place_id=place.get("place_id")))
    seen = {}
    for number, photo in enumerate(photos, 1):
        if not isinstance(photo, dict):
            problems.append(text("check.not_object", number=number, value=show(photo)))
            continue
        url = photo.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            problems.append(text("check.bad_url", number=number, value=show(url)))
        if not source_ok(photo.get("source")):
            problems.append(text("check.bad_source", number=number, sources=", ".join(SOURCES),
                                 value=show(photo.get("source"))))
        if not text_or_none(photo.get("credit")):
            problems.append(text("check.no_credit", number=number))
        same = photo.get("sha256") or url
        if isinstance(same, str) and same in seen:
            problems.append(text("check.same_photo", number=number, other=seen[same]))
        elif isinstance(same, str):
            seen[same] = number
    return len(photos), problems
