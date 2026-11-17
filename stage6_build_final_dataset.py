#!/usr/bin/env python3
"""Stage 6: build the final dataset for the website, one record per place.
Joins the clip files to places.json by place_id. Run after stage5c_match_places.py.
Values that can differ between clips (category, price_range, opening_hours,
area_description, menu_items) are kept as lists of unique values. An empty Maps link, opinion or
creator ("", or only spaces) is written as null. Each place gets one name, place_name from places.json; other names
(aliases, place_name_alt) stay in the pipeline for matching and are not published.

Usage:
    python stage6_build_final_dataset.py data/clips/*.json   # -> data/final_dataset.json
"""
import argparse
from pathlib import Path

from tvna_common import (
    AREAS_FILE,
    DATA_DIR,
    PLACES_FILE,
    load_areas,
    load_json,
    match_districts,
    name_key,
    norm,
    save_json,
    text_or_none,
)

LIST_FIELDS = ["category", "price_range", "area", "area_description", "opening_hours", "menu_items"]
CHECK_FIELDS = ["category", "price_range", "opening_hours"]


def add_unique(values, new):
    for v in new if isinstance(new, list) else [new]:
        if v and norm(v) not in {norm(x) for x in values}:
            values.append(v)


def new_record(place):
    rec = {
        "place_id": place["place_id"],
        "place_name": text_or_none(place.get("place_name")),
        "category": [],
        "price_range": [],
        "area": [],
        "area_description": [],
        "google_maps_url": text_or_none(place.get("google_maps_url")),
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
        clip_id = clip.get("clip_id") or Path(path).stem
        source = clip.get("source") or {}
        creator = text_or_none(source.get("creator"))
        if not creator:
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
            clip_name = text_or_none(f.get("place_name"))
            if (f.get("verification_status") == "verified" and clip_name and rec["place_name"]
                    and name_key(clip_name) != name_key(rec["place_name"])):
                warn = (f'{name}: the team checked the name "{clip_name}", but the website shows '
                        f'"{rec["place_name"]}" ({place_id}). To change it, edit place_name in places.json')
                if warn not in warnings:
                    warnings.append(warn)

            for key in LIST_FIELDS:
                add_unique(rec[key], f.get(key))

            opinion = text_or_none(f.get("speaker_opinion"))
            mention = next((m for m in rec["mentions"] if m["clip_id"] == clip_id), None)
            if mention:
                # Same place named twice in one clip: one mention, different opinions joined.
                old = mention["speaker_opinion"]
                if opinion and norm(opinion) not in {norm(o) for o in (old or "").split("; ")}:
                    mention["speaker_opinion"] = f"{old}; {opinion}" if old else opinion
            else:
                rec["mentions"].append({"clip_id": clip_id, "creator": creator, "speaker_opinion": opinion})

    for rec in records.values():
        if not rec["place_name"]:
            warnings.append(f"{rec['place_id']}: no place_name in places.json, so the website shows no name")
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
