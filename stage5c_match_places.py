#!/usr/bin/env python3
"""Stage 5c: give each place in the clip files a place_id from places.json.
Run after the team has cleaned the clips (Stage 5a/5b). The team then checks the report:
- matched: one place in places.json has this name or alias -> its place_id is reused.
- new: no match -> a new entry is added to places.json with a new place_id.
- unclear: more than one match -> place_id stays null; the team picks it from places.json.

Usage:
    python stage5c_match_places.py data/clips/*.json
"""
import argparse
import re
from pathlib import Path

from tvna_common import AREAS_FILE, PLACES_FILE, as_list, load_areas, load_json, match_districts, norm, save_json

ID_PREFIX = "tvna_p_"


def name_keys(names):
    return {norm(n) for n in names if norm(n)}


def build_index(places):
    index = {}
    for entry in places:
        for key in name_keys([entry["place_name"], *entry["aliases"]]):
            index.setdefault(key, set()).add(entry["place_id"])
    return index


def next_place_id(places):
    numbers = [int(m.group(1)) for e in places
               if (m := re.fullmatch(rf"{ID_PREFIX}(\d+)", e["place_id"] or ""))]
    return f"{ID_PREFIX}{max(numbers, default=0) + 1:04d}"


def add_aliases(entry, names):
    known = name_keys(entry["aliases"])
    added = []
    for name in names:
        if norm(name) and norm(name) not in known:
            entry["aliases"].append(name)
            known.add(norm(name))
            added.append(name)
    return added


def add_areas(entry, values, areas):
    entry["area"] = as_list(entry.get("area"))
    added = [d for d in match_districts(values, areas)[0] if d not in entry["area"]]
    entry["area"].extend(added)
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", help="Clip JSON files")
    ap.add_argument("--places", default=PLACES_FILE)
    ap.add_argument("--areas", default=AREAS_FILE)
    args = ap.parse_args()

    places_path = Path(args.places)
    places = load_json(places_path) if places_path.exists() else []
    areas = load_areas(args.areas)
    by_id = {e["place_id"]: e for e in places}
    index = build_index(places)
    report = {"matched": [], "new": [], "unclear": [], "unknown_id": []}
    skipped = 0
    places_changed = not places_path.exists()

    for path in args.clips:
        clip = load_json(path)
        clip_changed = False
        for f in clip.get("fields") or []:
            label = f'{Path(path).name}  "{f.get("place_name")}"'
            if f.get("place_id"):
                if f["place_id"] in by_id:
                    skipped += 1
                else:
                    report["unknown_id"].append(f"{label} -> {f['place_id']} is not in places.json")
                continue
            if f.get("verification_status") == "rejected" or not f.get("place_name"):
                skipped += 1
                continue

            names = [f["place_name"], *(f.get("place_name_alt") or [])]
            ids = set().union(*(index.get(k, set()) for k in name_keys(names)))
            if len(ids) > 1:
                report["unclear"].append(f"{label} -> candidates {', '.join(sorted(ids))} (left null)")
                continue

            if ids:
                place_id = ids.pop()
                new_aliases = add_aliases(by_id[place_id], names)
                new_areas = add_areas(by_id[place_id], f.get("area"), areas)
                notes = ([f"new aliases: {', '.join(new_aliases)}"] if new_aliases else []) + \
                        ([f"new areas: {', '.join(new_areas)}"] if new_areas else [])
                note = f" ({'; '.join(notes)})" if notes else ""
                report["matched"].append(f"{label} -> {place_id}{note}")
            else:
                place_id = next_place_id(places)
                entry = {
                    "place_id": place_id,
                    "place_name": f["place_name"],
                    "aliases": [],
                    "area": [],
                    "google_maps_url": f.get("google_maps_url"),
                }
                add_aliases(entry, names)
                add_areas(entry, f.get("area"), areas)
                places.append(entry)
                by_id[place_id] = entry
                report["new"].append(f"{label} -> {place_id}")

            for key in name_keys(names):
                index.setdefault(key, set()).add(place_id)
            f["place_id"] = place_id
            clip_changed = places_changed = True

        if clip_changed:
            save_json(path, clip)

    if places_changed:
        save_json(places_path, places)

    for group, lines in report.items():
        print(f"{group} ({len(lines)}):")
        for line in lines:
            print(f"  {line}")
    print(f"skipped ({skipped}): already have a place_id, rejected, or no name")


if __name__ == "__main__":
    main()
