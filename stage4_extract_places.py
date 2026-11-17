#!/usr/bin/env python3
"""Stage 4: transcript -> fields, with the Gemini API.
Reads a clip file made in stages 1-3, uses stt.transcript, and writes only "extraction"
and "fields" back into the same file.
A copy of the places as Gemini gave them goes to data/gemini_answers/<clip_id>.json. Nobody edits it,
so after the team review we can see what Gemini got wrong.
place_id stays null here; stage5c_match_places.py sets it.
Needs GEMINI_API_KEY in .env (see README.md).

Usage:
    python stage4_extract_places.py data/clips/PP-002.json [data/clips/PP-003.json ...]
    python stage4_extract_places.py data/clips/PP-002.json --force   # redo a clip that already has fields
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Literal, Optional

from google.genai import types
from pydantic import BaseModel

from tvna_common import (
    CATEGORIES,
    GEMINI_ANSWERS_DIR,
    NO_SPEECH,
    ClipError,
    completeness,
    display_path,
    gemini_client,
    generate_with_backup,
    has_places,
    load_areas,
    load_json,
    match_districts,
    models_in_order,
    norm,
    run_each,
    save_json,
    skip_reviewed,
    verification_status,
)

# First model, then the backup when it is busy. extraction.model records the one(s) that did the work.
MODELS = ["gemini-3.6-flash", "gemini-3.8-flash"]
PROMPT_VERSION = "v4"
# A normal TikTok fits in one part, so Gemini sees the whole video at once.
# Longer ones are sent in parts; each part repeats the last 10 sentences of the one before.
PART_SIZE = 60
PART_STEP = 50
# When the same place shows up again in a later part:
FILL_IF_EMPTY = ["category", "sub_category", "price_range", "area_description", "opening_hours",
                 "speaker_opinion", "notes"]
COMBINE = ["place_name_alt", "menu_items", "area"]

AREAS = load_areas()
DISTRICTS = [a["district"] for a in AREAS]

SYSTEM = f"""You extract place information from the transcript of a short video about places in Phnom Penh.
The transcript mixes Khmer and English and comes from speech recognition, so names may be misspelled.

GENERAL RULES:
- Use ONLY what the transcript says. No outside knowledge, no guessing.
- If something is not stated, return null for it. Never return "", "N/A" or a guess. Missing values must strictly be null.
- One record per distinct place. If no place is mentioned, return an empty list.
- Copy segment ids exactly as given in the input. Never invent ids or timestamps.

FIELDS (per place):
- place_name: the name as spoken, in English if an English name is spoken. Put the Khmer name and other spellings in place_name_alt.
- place_name_alt: list of the Khmer name and other spellings mentioned in the transcript (or empty list []).
- category: one of {CATEGORIES}.
- sub_category: a short detail such as "Vietnamese", or null if not stated.
- price_range: only if a price is stated for THIS place or its items. Write it as spoken, for example "$5-10" or "10,000 riel". Otherwise null.
- area: list of the districts from {DISTRICTS} that the transcript names for THIS place (also in Khmer, e.g. ចំការមន = Chamkar Mon). A place can have several branches, so list every district named for it. If a neighborhood or other area is named (for example BKK1 or Toul Tom Poung), do NOT put it here. Null if no district is named.
- area_description: any wording about where the place is (district, neighborhood, street, landmark), as spoken, or null. Fill it even when area is also filled.
- opening_hours: only if said, as spoken, or null.
- speaker_opinion: a short summary (1 to 3 sentences) of why a visitor would want to go to THIS place, based ONLY on what the speaker says.
    Include what is good, special or interesting about the place: taste, price or value, choices, atmosphere, space, seating, photo spots, service, decor, theme or story of the place.
    Rewrite it in clear, natural words instead of copying the sentence, but keep the real meaning. Do not make it stronger than the speaker said, and do not add praise or facts that were not spoken.
    Leave out the speaker's own story that does not help a visitor (why they came, their trip, greetings, asking viewers to follow).
    Write it in the same language the speaker mainly uses about this place. Do not translate.
    Null if the speaker says nothing good or interesting about the place.
- menu_items: list of food and drink items named for this place, as spoken. Null if none.
- notes: other useful details that fit no field above (for example promos about that place). Do not add details that were not spoken.
- evidence_text: one short snippet copied EXACTLY from the transcript that proves the place name. Under 200 characters.
- segment_ids: ids of the segments that talk about this place.
- confidence: for place_name, category, price_range and area, give "high", "medium", "low", or null if the value is null.
    high = clearly stated; medium = implied or spelling uncertain; low = unclear.
- missing_reasons: for each null field (price_range, area, sub_category, opening_hours, area_description, speaker_opinion, menu_items), provide a short reason such as "not mentioned" or "no price tied to this place".

DO NOT:
- Put promotional content (promo codes, subscriptions, delivery offers) into place fields. Mention it in notes only if it is about that place.
- Treat the creator's channel name or the delivery app (e.g. MotoKew, GrabFood) as a place.
- Use general price comments that are not tied to one place (for example "you can buy a drink with only 10,000").
- Fix a spelling by guessing; if a name looks like an ASR error, keep it as spoken and set confidence to "medium" or "low".
"""

ConfType = Optional[Literal["high", "medium", "low"]]


class FieldConfidence(BaseModel):
    place_name: ConfType = None
    category: ConfType = None
    price_range: ConfType = None
    area: ConfType = None


class MissingReasons(BaseModel):
    price_range: Optional[str] = None
    area: Optional[str] = None
    sub_category: Optional[str] = None
    opening_hours: Optional[str] = None
    area_description: Optional[str] = None
    speaker_opinion: Optional[str] = None
    menu_items: Optional[str] = None


class PlaceItem(BaseModel):
    place_name: Optional[str] = None
    place_name_alt: List[str] = []
    category: Optional[Literal[tuple(CATEGORIES)]] = None
    sub_category: Optional[str] = None
    price_range: Optional[str] = None
    area: Optional[List[str]] = None
    area_description: Optional[str] = None
    opening_hours: Optional[str] = None
    speaker_opinion: Optional[str] = None
    menu_items: Optional[List[str]] = None
    confidence: FieldConfidence
    missing_reasons: MissingReasons = MissingReasons()
    notes: Optional[str] = None
    evidence_text: str
    segment_ids: List[int]


class ExtractionResponse(BaseModel):
    places: List[PlaceItem]


def split_transcript(text: str) -> List[dict]:
    """Split the transcript into numbered sentences (Khmer and English punctuation)."""
    raw_sentences = [s.strip() for s in re.split(r"([.!?។៕\n]+)", text) if s.strip()]
    combined = []
    i = 0
    while i < len(raw_sentences):
        chunk = raw_sentences[i]
        if i + 1 < len(raw_sentences) and re.match(r"^[.!?។៕\n]+$", raw_sentences[i + 1]):
            chunk += raw_sentences[i + 1].strip()
            i += 1
        if len(chunk) > 1:
            combined.append(chunk)
        i += 1
    return [{"id": idx, "text": s} for idx, s in enumerate(combined or [text.strip()])]


def windows(segments, size=PART_SIZE, step=PART_STEP):
    i = 0
    while i < len(segments):
        yield segments[i:i + size]
        if i + size >= len(segments):
            break
        i += step


def call_model(client, window, models):
    text = "\n".join(f"[{s['id']}] {s['text']}" for s in window)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        response_schema=ExtractionResponse,
    )
    resp, model = generate_with_backup(client, models, f"Transcript excerpt:\n{text}", config)
    if resp.parsed is not None:
        return [p.model_dump() for p in resp.parsed.places], model
    try:
        return json.loads(resp.text or "").get("places", []), model
    except (ValueError, AttributeError):
        raise ClipError(f"{model} did not answer in the expected format. Run the same command again.") from None


def build_record(p, window):
    by_id = {s["id"]: s for s in window}
    seg_ids = [i for i in p.get("segment_ids", []) if i in by_id]
    window_text = norm(" ".join(s["text"] for s in window))
    conf = p.get("confidence") or {}
    flags = []

    area, not_districts = match_districts(p.get("area"), AREAS)
    area_description = p.get("area_description")
    if not_districts:
        flags.append("area_not_in_areas_list")
        area_description = area_description or ", ".join(not_districts)

    if not p.get("place_name"):
        flags.append("no_place_name")
    if norm(p.get("evidence_text", "")) not in window_text:
        flags.append("evidence_not_found_in_transcript")
    flags += checked_flags(conf, seg_ids)

    raw_missing = p.get("missing_reasons") or {}
    if hasattr(raw_missing, "model_dump"):
        raw_missing = raw_missing.model_dump()
    cleaned_missing = {k: v for k, v in raw_missing.items() if v}

    record = {
        "place_id": None,
        "place_name": p.get("place_name"),
        "place_name_alt": p.get("place_name_alt") or [],
        "category": p.get("category"),
        "sub_category": p.get("sub_category"),
        "price_range": p.get("price_range"),
        "area": area or None,
        "area_description": area_description,
        "google_maps_url": None,
        "opening_hours": p.get("opening_hours"),
        "speaker_opinion": p.get("speaker_opinion"),
        "menu_items": p.get("menu_items") or None,
    }
    score, missing_fields = completeness(record)
    record.update({
        "completeness": score,
        "missing_fields": missing_fields,
        "verification_status": verification_status(record, score),
        "cleaned_by": None,
        "cleaner_note": None,
        "notes": p.get("notes"),
        "confidence": conf,
        "missing_reasons": cleaned_missing,
        "evidence_text": p.get("evidence_text"),
        "segment_ids": seg_ids,
        "flags": flags,
    })
    return record


def checked_flags(conf: dict, seg_ids: List[int]) -> List[str]:
    """Flags that depend on the sentence numbers and Gemini's confidence."""
    flags = []
    if not seg_ids:
        flags.append("no_valid_segment_ids")
    if conf.get("place_name") in ["medium", "low"]:
        flags.append("asr_spelling_or_uncertain_name")
    if any(conf.get(k) == "low" for k in ("category", "price_range", "area")):
        flags.append("low_confidence_field")
    return flags


def merge_record(first: dict, later: dict) -> None:
    """Add what a later part says about a place that an earlier part already found.
    Empty details are filled, lists are combined, filled details are kept. Then the score is redone."""
    for key in COMBINE:
        combined = list(dict.fromkeys((first.get(key) or []) + (later.get(key) or [])))
        if key == "area" and not first.get("area") and combined:
            first["confidence"]["area"] = later["confidence"].get("area")
        first[key] = combined if combined or key == "place_name_alt" else None
    for key in FILL_IF_EMPTY:
        if not first.get(key) and later.get(key):
            first[key] = later[key]
            if key in ("category", "price_range"):
                first["confidence"][key] = later["confidence"].get(key)
    first["segment_ids"] = sorted(set(first["segment_ids"]) | set(later["segment_ids"]))
    first["missing_reasons"] = {k: v for k, v in first["missing_reasons"].items() if not first.get(k)}

    # evidence_text is still the first part's, so its check stays; an area problem from either part stays.
    flags = [f for f in first["flags"] if f in ("no_place_name", "evidence_not_found_in_transcript")]
    if "area_not_in_areas_list" in first["flags"] + later["flags"]:
        flags.append("area_not_in_areas_list")
    first["flags"] = flags + checked_flags(first["confidence"], first["segment_ids"])

    score, missing_fields = completeness(first)
    first.update(completeness=score, missing_fields=missing_fields,
                 verification_status=verification_status(first, score))


def extract_clip(client, path: Path, models: List[str], force: bool, answers_dir: Path = GEMINI_ANSWERS_DIR) -> str:
    """Find the places in one clip. Returns "made" or "skipped"; raises ClipError."""
    try:
        clip = load_json(path)
    except (OSError, ValueError) as e:
        raise ClipError(f"Can't read the clip file: {e}") from None
    clip_id = clip.get("clip_id") or path.stem

    if skip_reviewed(clip, clip_id):
        return "skipped"
    if has_places(clip) and not force:
        print(f"{clip_id}: already has places. Skipped. Use --force to find them again.")
        return "skipped"
    transcript = (clip.get("stt") or {}).get("transcript")
    if not transcript:
        raise ClipError(f"No transcript yet. Run stage 3 first: python stage3_transcribe.py {display_path(path)}")
    if transcript.strip() == NO_SPEECH:
        print(f"{clip_id}: no speech in this video, so no places to find. Skipped.")
        return "skipped"

    segments = split_transcript(transcript)
    print(f"{clip_id}: finding places in {len(segments)} sentences with {models[0]} ...", flush=True)
    records, seen_places, used_models = [], {}, set()
    for window in windows(segments):
        places, used_model = call_model(client, window, models)
        used_models.add(used_model)
        for p in places:
            key = norm(p.get("place_name") or "")
            if key and key in seen_places:
                merge_record(seen_places[key], build_record(p, window))
                continue
            rec = build_record(p, window)
            records.append(rec)
            if key:
                seen_places[key] = rec

    extraction = {
        "method": "llm",
        "model": ", ".join(sorted(used_models)) or None,
        "prompt_version": PROMPT_VERSION,
    }
    # Keep the template's key order: "extraction" right before "fields".
    updated = {}
    for key, value in clip.items():
        if key == "fields":
            updated["extraction"] = extraction
        if key != "extraction":
            updated[key] = value
    updated["extraction"] = extraction
    updated["fields"] = records
    answers_dir.mkdir(parents=True, exist_ok=True)
    save_json(answers_dir / f"{clip_id}.json", {"clip_id": clip_id, "extraction": extraction, "fields": records})
    save_json(path, updated)

    print(f"{clip_id}: {len(records)} place{'' if len(records) == 1 else 's'} found ({extraction['model']})")
    for r in records:
        print(f"  - {r['place_name'] or '(no name)'} ({r['category'] or 'no category'}): {r['verification_status']}")
    return "made"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", type=Path, help="Clip files made in stages 1-3, e.g. data/clips/PP-002.json")
    ap.add_argument("--model", default=MODELS[0], help=f"Gemini model to try first (default {MODELS[0]})")
    ap.add_argument("--force", action="store_true", help="Redo clips whose fields are already filled")
    ap.add_argument("--answers-dir", type=Path, default=GEMINI_ANSWERS_DIR)
    args = ap.parse_args()
    models = models_in_order(args.model, MODELS)

    try:
        client = gemini_client(attempts=1)
    except ValueError:
        sys.exit("GEMINI_API_KEY is missing. Add it to .env (see README, Setup). Nothing changed.")

    run_each(args.clips, lambda path: extract_clip(client, path, models, args.force, args.answers_dir),
             "python stage5a_dedupe_clips.py data/clips/*.json")


if __name__ == "__main__":
    main()
