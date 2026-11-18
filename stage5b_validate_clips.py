#!/usr/bin/env python3
"""Stage 5b helper: check the team's review before stage 5c. Reads the clip files and changes nothing.
Lists, per place:
- problems: mistakes to fix, e.g. a misspelled status ("verfied"), a district that is not in data/reference/areas.json,
  "nothing" or "" instead of null, a verified place with no district, Maps link or reviewer name;
- to review: places nobody has approved yet, with what is still missing;
- ready: verified places with no problems (stage 5c will give them a place_id).
Exits with 1 when there are problems, so nothing broken goes on to 5c by accident.

Usage:
    python stage5b_validate_clips.py data/clips/*.json
"""
import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import List
from urllib.parse import urlsplit

from tvna_common import AREAS_FILE, CATEGORIES, as_list, load_areas, load_json, match_district

STATUSES = ["rejected", "needs_review", "auto_added", "verified"]
WAITING = ["needs_review", "auto_added"]
PLACEHOLDERS = {"", "n/a", "na", "none", "nothing", "unknown", "null", "-", "—"}  # should be null
MAPS_HOSTS = {"maps.app.goo.gl", "goo.gl", "google.com", "maps.google.com"}
KEY_FIELDS = 3  # place_name, area, speaker_opinion (completeness)


def close_to(value: str, choices: List[str]) -> str:
    match = difflib.get_close_matches(value, choices, n=1, cutoff=0.6)
    return f' Did you mean "{match[0]}"?' if match else ""


def show(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def is_maps_link(url: str) -> bool:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    if parts.scheme not in ("http", "https") or host not in MAPS_HOSTS:
        return False
    return host in ("maps.app.goo.gl", "maps.google.com") or parts.path.startswith("/maps")


def placeholder_fields(place: dict) -> List[str]:
    """Fields holding text like "", "N/A" or "nothing" where the team rule says null."""
    found = []
    for key, value in place.items():
        values = value if isinstance(value, list) else [value]
        if any(isinstance(v, str) and v.strip().lower() in PLACEHOLDERS for v in values):
            found.append(key)
    return found


def check_place(place: dict, areas: List[dict]) -> List[str]:
    """Mistakes in one place record. An empty list means no problems."""
    problems = []
    status = place.get("verification_status")
    if status not in STATUSES:
        hint = close_to(status, STATUSES) if isinstance(status, str) else ""
        problems.append(f"verification_status {show(status)} is not a status (use {', '.join(STATUSES)}).{hint}")

    for key in placeholder_fields(place):
        problems.append(f"{key}: write null, not {show(place[key])}")

    area = place.get("area")
    if area is not None and not isinstance(area, list):
        problems.append(f'area must be a list, e.g. ["{area}"]' if isinstance(area, str) else "area must be a list")
    names = [a["district"] for a in areas] + [a["district_km"] for a in areas]
    for value in as_list(area):
        if isinstance(value, str) and value.strip().lower() not in PLACEHOLDERS and not match_district(value, areas):
            problems.append(f'area "{value}" is not one of the 14 districts in data/reference/areas.json. '
                            f"Write it exactly as there.{close_to(value, names)}")

    category = place.get("category")
    if category is not None and category not in CATEGORIES:
        problems.append(f'category "{category}" is not in the category list (field guide, section 9).'
                        f"{close_to(str(category), CATEGORIES)}")

    url = place.get("google_maps_url")
    if isinstance(url, str) and url.strip() and not is_maps_link(url):
        problems.append(f"google_maps_url is not a Google Maps link: {url}")

    score, missing = place.get("completeness"), place.get("missing_fields")
    if isinstance(score, (int, float)) and isinstance(missing, list) and len(missing) != KEY_FIELDS - round(score * KEY_FIELDS):
        problems.append(f"missing_fields {missing} doesn't match completeness {score}. Don't edit these two: "
                        "they record what stage 4 found (see data/gemini_answers/)")

    if status == "verified":
        if not place.get("place_name"):
            problems.append("verified, but place_name is empty")
        if not place.get("cleaned_by"):
            problems.append("verified, but cleaned_by is empty: write your name")
        if not as_list(area):
            problems.append("verified, but area is empty. Not found on Google Maps? Keep needs_review (team rule)")
        if not place.get("google_maps_url"):
            problems.append("verified, but google_maps_url is empty. Not found on Google Maps? Keep needs_review")
    elif status in WAITING and place.get("cleaned_by") and not place.get("cleaner_note"):
        problems.append(f"cleaned_by is filled but the status is still {status}. If you are holding it back "
                        "(not found on Google Maps), say why in cleaner_note; if it is checked, write \"verified\"")
    return problems


def still_to_do(place: dict) -> str:
    todo = [f for f in ("area", "google_maps_url") if not place.get(f)]
    flags = [f for f in as_list(place.get("flags")) if isinstance(f, str)]
    parts = [f"fill {', '.join(todo)}"] if todo else []
    if flags:
        parts.append(f"check flags: {', '.join(flags)}")
    if place.get("cleaned_by") and place.get("cleaner_note"):
        parts.append(f"held back: {place['cleaner_note']}")
    elif not todo:
        parts.append('district and Maps link filled: check it, then your name in cleaned_by and "verified"')
    return "; ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", type=Path, help="Clip files, e.g. data/clips/*.json")
    ap.add_argument("--areas", type=Path, default=AREAS_FILE)
    args = ap.parse_args()
    areas = load_areas(args.areas)

    problems, waiting, ready = [], [], []
    rejected = not_yet = 0
    for path in args.clips:
        name = path.name
        try:
            clip = load_json(path)
        except (OSError, ValueError) as e:
            problems.append((name, [f"can't read the file: {e}. A comma or quote is probably missing near there"]))
            continue
        if not isinstance(clip, dict):
            problems.append((name, ["not a clip file (no clip_id or fields)"]))
            continue
        fields = clip.get("fields")
        if fields is None:
            not_yet += 1
            continue
        if not isinstance(fields, list):
            problems.append((name, ["fields must be a list of places"]))
            continue
        for place in fields:
            if not isinstance(place, dict):
                problems.append((name, ["a place in fields is not an object {...}"]))
                continue
            label = f'{name}  "{place.get("place_name")}"'
            found = check_place(place, areas)
            status = place.get("verification_status")
            if found:
                problems.append((label, found))
            elif status == "rejected":
                rejected += 1
            elif status == "verified":
                ready.append(label)
            else:
                waiting.append(f"{label} ({status}): {still_to_do(place)}")

    print(f"problems ({len(problems)}):")
    for label, lines in problems:
        print(f"  {label}")
        for line in lines:
            print(f"    - {line}")
    print(f"to review ({len(waiting)}):")
    for line in waiting:
        print(f"  {line}")
    print(f"ready ({len(ready)}): verified, no problems")
    for line in ready:
        print(f"  {line}")
    print(f"rejected ({rejected}), not at stage 4 yet ({not_yet} clip{'' if not_yet == 1 else 's'})")
    if problems:
        sys.exit("Fix the problems above, then run this again. Nothing was changed.")
    print("Next: python stage5c_match_places.py data/clips/*.json")


if __name__ == "__main__":
    main()
