#!/usr/bin/env python3
"""Stage 6: build the final dataset for the website, one record per place.
Joins the clip files to places.json by place_id. Run after stage5c_match_places.py.
Values that can differ between clips (category, price_range, opening_hours,
area_description, menu_items) are kept as lists of unique values.

Usage:
    python stage6_build_final_dataset.py data/clips/*.json   # -> data/final_dataset.json
"""
import argparse
from pathlib import Path

from tvna_common import AREAS_FILE, DATA_DIR, PLACES_FILE, load_areas, load_json, match_districts, norm, save_json

LIST_FIELDS = ["category", "price_range", "area", "area_description", "opening_hours", "menu_items"]
CHECK_FIELDS = ["category", "price_range", "opening_hours"]


def add_unique(values, new):
    for v in new if isinstance(new, list) else [new]:
        if v and norm(v) not in {norm(x) for x in values}:
            values.append(v)


def new_record(place):
    rec = {
        "place_id": place["place_id"],
        "place_name": place["place_name"],
        "place_name_alt": [a for a in place.get("aliases", []) if norm(a) != norm(place["place_name"])],
        "category": [],
        "price_range": [],
        "area": [],
        "area_description": [],
        "google_maps_url": place.get("google_maps_url"),
        "opening_hours": [],
        "menu_items": [],
        "popularity": 0,
        "mentions": [],
    }
    add_unique(rec["area"], place.get("area"))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", help="Clip JSON files")
    ap.add_argument("--places", default=PLACES_FILE)
    ap.add_argument("--areas", default=AREAS_FILE)
    ap.add_argument("--output", default=DATA_DIR / "final_dataset.json")
    args = ap.parse_args()

    places = {e["place_id"]: e for e in load_json(args.places)}
    areas = load_areas(args.areas)
    records, warnings = {}, []

    for path in args.clips:
        clip = load_json(path)
        name = Path(path).name
        source = clip.get("source") or {}
        if not source.get("creator"):
            warnings.append(f"{name}: no creator, so this clip is not counted in popularity")

        for f in clip.get("fields") or []:
            place_id = f.get("place_id")
            if not place_id or f.get("verification_status") == "rejected":
                continue
            if place_id not in places:
                warnings.append(f'{name} "{f.get("place_name")}": {place_id} is not in places.json')
                continue
            if place_id not in records:
                records[place_id] = new_record(places[place_id])
            rec = records[place_id]

            for key in LIST_FIELDS:
                add_unique(rec[key], f.get(key))

            mention = next((m for m in rec["mentions"] if m["clip_id"] == clip.get("clip_id")), None)
            if mention:
                # Same place named twice in one clip: one mention, opinions joined.
                opinions = [mention["speaker_opinion"], f.get("speaker_opinion")]
                mention["speaker_opinion"] = "; ".join(o for o in opinions if o) or None
            else:
                rec["mentions"].append({
                    "clip_id": clip.get("clip_id"),
                    "creator": source.get("creator"),
                    "speaker_opinion": f.get("speaker_opinion"),
                })

    for rec in records.values():
        rec["popularity"] = len({norm(m["creator"]) for m in rec["mentions"] if m["creator"]})
        rec["area"], not_districts = match_districts(rec["area"], areas)
        for value in not_districts:
            warnings.append(f"{rec['place_id']}: area {value!r} is not a district in areas.json, left out")
        for key in CHECK_FIELDS:
            if len(rec[key]) > 1:
                warnings.append(f"{rec['place_id']}: clips disagree on {key}: {rec[key]}")

    result = sorted(records.values(), key=lambda r: r["place_id"])
    save_json(args.output, result)

    print(f"{len(result)} places from {len(args.clips)} clips -> {args.output}")
    print(f"warnings ({len(warnings)}):")
    for w in warnings:
        print(f"  {w}")


if __name__ == "__main__":
    main()
