#!/usr/bin/env python3
"""Stage 5c: give each place in the clip files a place_id from places.json.
Run after the team review (stage 5b). Each place is checked in this order:
1. same Google Maps link -> matched
2. same name or alias (ignoring capitals, spaces and punctuation) -> matched
3. name score 95 or more (Latin names only) -> matched; the new spelling is saved as an alias
4. score 75-94, one name inside the other, or a close Khmer name -> unclear: place_id stays null
5. anything else -> new entry in places.json with a new place_id
For an unclear place, the team writes the suggested place_id in the clip (same place) or "new" (a different
place), then runs this again. Every name that gets a place_id is saved as an alias, so it matches exactly next time.

Usage:
    python stage5c_match_places.py data/clips/*.json
"""
import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from tvna_common import (
    AREAS_FILE,
    PLACES_FILE,
    as_list,
    has_khmer,
    load_areas,
    load_json,
    maps_key,
    match_districts,
    name_key,
    name_score,
    save_json,
)

ID_PREFIX = "tvna_p_"
NEW = "new"  # what the team writes in place_id for "a different place"
SAME_SCORE = 95
UNCLEAR_SCORE = 75
MIN_INSIDE = 3  # a name at least this long that sits inside another name makes it "unclear"
MAX_SUGGESTIONS = 3


class MapsLinks:
    """Place codes of Google Maps links. Each link is read once per run; problems are kept for the report."""

    def __init__(self):
        self.keys: Dict[str, Optional[str]] = {}
        self.problems: List[str] = []

    def key(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        if url not in self.keys:
            try:
                self.keys[url] = maps_key(url)
            except ValueError as e:
                self.problems.append(f"{url}: {e}. Checked by name instead.")
                self.keys[url] = None
        return self.keys[url]


def name_keys(names) -> Set[str]:
    return {name_key(n) for n in names if name_key(n)}


def entry_names(entry: dict) -> List[str]:
    return [entry["place_name"], *entry["aliases"]]


def next_place_id(places):
    numbers = [int(m.group(1)) for e in places
               if (m := re.fullmatch(rf"{ID_PREFIX}(\d+)", e["place_id"] or ""))]
    return f"{ID_PREFIX}{max(numbers, default=0) + 1:04d}"


def add_aliases(entry, names):
    known = name_keys(entry["aliases"])
    added = []
    for name in names:
        if name_key(name) and name_key(name) not in known:
            entry["aliases"].append(name)
            known.add(name_key(name))
            added.append(name)
    return added


def add_areas(entry, values, areas):
    entry["area"] = as_list(entry.get("area"))
    added = [d for d in match_districts(values, areas)[0] if d not in entry["area"]]
    entry["area"].extend(added)
    return added


def remember(entry: dict, place: dict, names: List[str], areas) -> List[str]:
    """Save what this clip adds to the places.json entry: names, districts, Maps link."""
    notes = []
    new_aliases = add_aliases(entry, names)
    if new_aliases:
        notes.append(f"new aliases: {', '.join(new_aliases)}")
    new_areas = add_areas(entry, place.get("area"), areas)
    if new_areas:
        notes.append(f"new areas: {', '.join(new_areas)}")
    if place.get("google_maps_url") and not entry.get("google_maps_url"):
        entry["google_maps_url"] = place["google_maps_url"]
        notes.append("Maps link added")
    return notes


def closest(names: List[str], by_id: Dict[str, dict]) -> List[Tuple[int, bool, bool, str, str]]:
    """For each place in places.json, its closest name: (score, one name inside the other, Khmer, place_id, name).
    Best first."""
    found = []
    for place_id, entry in by_id.items():
        best = None
        for ours in names:
            for theirs in entry_names(entry):
                a, b = name_key(ours), name_key(theirs)
                if not a or not b:
                    continue
                short, long_ = sorted((a, b), key=len)
                inside = len(short) >= MIN_INSIDE and short in long_
                candidate = (name_score(ours, theirs), inside, has_khmer(ours) or has_khmer(theirs), place_id, theirs)
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
        if best:
            found.append(best)
    return sorted(found, key=lambda c: c[:2], reverse=True)


def describe(candidates) -> str:
    return ", ".join(f'{pid} "{name}" ({"name inside the other" if inside and score < UNCLEAR_SCORE else f"{score}%"})'
                     for score, inside, _, pid, name in candidates[:MAX_SUGGESTIONS])


def find_match(place, names, name_index, link_index, by_id, links) -> Tuple[str, Optional[str], str]:
    """Returns (group, place_id, note); group is "matched", "unclear" or "new"."""
    link = links.key(place.get("google_maps_url"))
    if link and link_index.get(link):
        ids = sorted(link_index[link])
        if len(ids) == 1:
            return "matched", ids[0], "same Google Maps link"
        return "unclear", None, f"same Google Maps link as {', '.join(ids)}"

    ids = sorted(set().union(*(name_index.get(k, set()) for k in name_keys(names))))
    if len(ids) > 1:
        return "unclear", None, f"candidates {', '.join(ids)}"
    if ids:
        other = links.key(by_id[ids[0]].get("google_maps_url"))
        if link and other and link != other:
            return "unclear", None, (f"same name as {ids[0]}, but a different Google Maps link: another branch "
                                     f"(write {ids[0]}) or a different place (write \"{NEW}\")?")
        return "matched", ids[0], ""

    candidates = closest(names, by_id)
    sure = [c for c in candidates if c[0] >= SAME_SCORE]
    if len(sure) == 1 and not sure[0][2]:
        score, _, _, place_id, name = sure[0]
        return "matched", place_id, f'fuzzy {score}% like "{name}"'
    maybe = [c for c in candidates if c[0] >= UNCLEAR_SCORE or c[1]]
    if maybe:
        khmer = " Khmer names are always checked by the team." if any(c[2] for c in sure) else ""
        return "unclear", None, f"maybe {describe(maybe)}.{khmer}"
    return "new", None, ""


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
    links = MapsLinks()
    name_index: Dict[str, Set[str]] = {}
    link_index: Dict[str, Set[str]] = {}

    def index(entry):
        for key in name_keys(entry_names(entry)):
            name_index.setdefault(key, set()).add(entry["place_id"])
        link = links.key(entry.get("google_maps_url"))
        if link:
            link_index.setdefault(link, set()).add(entry["place_id"])

    for entry in places:
        index(entry)
    report = {"matched": [], "new": [], "unclear": [], "unknown_id": []}
    skipped = 0
    places_changed = not places_path.exists()

    for path in args.clips:
        clip = load_json(path)
        clip_changed = False
        for f in clip.get("fields") or []:
            label = f'{Path(path).name}  "{f.get("place_name")}"'
            names = [f.get("place_name"), *(f.get("place_name_alt") or [])]
            set_by_team = f.get("place_id")
            if set_by_team and set_by_team != NEW:
                if set_by_team not in by_id:
                    report["unknown_id"].append(f"{label} -> {set_by_team} is not in places.json")
                    continue
                notes = remember(by_id[set_by_team], f, names, areas)
                if notes:
                    index(by_id[set_by_team])
                    report["matched"].append(f"{label} -> {set_by_team} (set by the team; {'; '.join(notes)})")
                    places_changed = True
                else:
                    skipped += 1
                continue
            if f.get("verification_status") == "rejected" or not f.get("place_name"):
                skipped += 1
                continue

            if set_by_team == NEW:
                group, place_id, why = "new", None, "the team said: a different place"
            else:
                group, place_id, why = find_match(f, names, name_index, link_index, by_id, links)
            if group == "unclear":
                report["unclear"].append(f"{label} -> {why} (left null)")
                continue
            if group == "new":
                place_id = next_place_id(places)
                entry = {"place_id": place_id, "place_name": f["place_name"], "aliases": [], "area": [],
                         "google_maps_url": f.get("google_maps_url")}
                places.append(entry)
                by_id[place_id] = entry
            notes = ([why] if why else []) + remember(by_id[place_id], f, names, areas)
            if group == "new":
                notes = [n for n in notes if not n.startswith("new aliases")]
            report[group].append(f"{label} -> {place_id}" + (f" ({'; '.join(notes)})" if notes else ""))
            index(by_id[place_id])
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
    if links.problems:
        print(f"Maps link problems ({len(links.problems)}):")
        for line in links.problems:
            print(f"  {line}")
    if report["unclear"]:
        print(f'For each unclear place: write the place_id in the clip if it is the same place, or "{NEW}" if not. '
              "Then run this again.")
    print("Next: python stage6_build_final_dataset.py data/clips/*.json")


if __name__ == "__main__":
    main()
