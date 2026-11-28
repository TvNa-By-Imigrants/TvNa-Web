#!/usr/bin/env python3
"""Stage 5d check: which places still need photos, and mistakes in the photo lists. Changes nothing.
Groups: problems (fix them; exit 1), need photos (new places with none yet: add 1 to 5), ready (1 to 5 photos).

Usage:
    python stage5d_check_photos.py
"""
import argparse
import sys
from pathlib import Path

from tvna_common import PLACES_DIR, load_places
from tvna_review import photo_problems, text


def name_of(place: dict) -> str:
    return place.get("place_name") or text("checker.no_name")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--places-dir", type=Path, default=PLACES_DIR)
    args = ap.parse_args()
    try:
        places = load_places(args.places_dir)
    except ValueError as e:
        sys.exit(text("checker.cant_read", reason=e))

    problems, need, ready = [], [], []
    for place in places:
        count, found = photo_problems(place)
        if found:
            problems.append((place, found))
        elif count == 0:
            need.append(place)
        else:
            ready.append(place)

    print(text("checker.problems", count=len(problems)))
    for place, found in problems:
        print(f"  {place['place_id']}  \"{name_of(place)}\"")
        for line in found:
            print(f"    - {line}")
    print(text("checker.need", count=len(need)))
    for place in need:
        print("  " + text("checker.need_line", place_id=place["place_id"], name=name_of(place),
                          maps=place.get("google_maps_url") or ""))
    print(text("checker.ready", count=len(ready)))
    for place in ready:
        print(f"  {place['place_id']}  \"{name_of(place)}\"")
    if need:
        print(text("checker.next_add"))
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
