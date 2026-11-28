#!/usr/bin/env python3
"""Stage 4: transcript + TikTok caption -> fields, with the Gemini API.
Reads a clip file made in stages 1-3, uses stt.transcript and source.caption, and writes only "extraction"
and "fields" back into the same file.
The caption's spelling of a place name becomes place_name; every other name (the spoken one too) goes in
place_name_alt, so no name is lost. A [no speech] clip with a caption is read from the caption only.
Stage 2 must have read the caption first (a saved null = the video has no caption).
A copy of the places as stage 4 made them (Gemini's answer after the code's checks) goes to
data/gemini_answers/<clip_id>.json. Nobody edits it, so after the team review we can see what Gemini got wrong.
area is one district as text: the first one Gemini names; any other district goes in area_description.
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
import unicodedata
from pathlib import Path
from typing import List, Literal, Optional

from google.genai import types
from pydantic import BaseModel, ValidationError

from tvna_common import (
    CATEGORIES,
    GEMINI_ANSWERS_DIR,
    NO_SPEECH,
    ClipError,
    as_list,
    completeness,
    display_path,
    gemini_client,
    generate_with_backup,
    has_khmer,
    has_places,
    load_areas,
    load_json,
    match_districts,
    models_in_order,
    name_key,
    norm,
    run_each,
    save_json,
    skip_reviewed,
    verification_status,
)

# First model, then the backup when it is busy. extraction.model records the one(s) that did the work.
MODELS = ["gemini-3.6-flash", "gemini-3.8-flash"]
PROMPT_VERSION = "v5"
# A normal TikTok fits in one part, so Gemini sees the whole video at once.
# Longer ones are sent in parts; each part repeats the last 10 sentences of the one before.
PART_SIZE = 60
PART_STEP = 50
# When the same place shows up again in a later part:
FILL_IF_EMPTY = ["category", "sub_category", "price_range", "area", "opening_hours", "speaker_opinion", "notes"]
COMBINE = ["place_name_alt", "menu_items"]
# A "name" that is only @accounts or #hashtags: the prompt forbids it; the code catches slips.
TAG_ONLY = re.compile(r"(?:[@#]\S+\s*)+")

AREAS = load_areas()
DISTRICTS = [a["district"] for a in AREAS]

SYSTEM = f"""You extract place information from a short video about places in Phnom Penh. You get two sources:
- TRANSCRIPT: what is said. It mixes Khmer and English and comes from speech recognition, so names may be misheard or misspelled.
- TIKTOK CAPTION, between <caption> and </caption>: what the creator wrote under the video, when there is one. It is typed, so names are usually spelled right. It may also have hashtags, @accounts, emojis and sponsor text. It has no segment ids.

GENERAL RULES:
- Use ONLY what the transcript and the caption say. No outside knowledge, no guessing.
- If something is not stated, return null for it. Never return "", "N/A" or a guess. Missing values must strictly be null.
- One record per distinct place that the video shows or visits. If no place is named, return an empty list.
- A place named only in the caption (not said in the video) still gets a record.
- Copy segment ids exactly as given in the input. Never invent ids or timestamps.

FIELDS (per place):
- place_name: the place's English name if one is said or written, otherwise its Khmer name. If the caption writes that name, use the caption's spelling (the transcript may mishear it).
- place_name_alt: list of every OTHER name for the same place that is said in the transcript or written in the caption: the Khmer name, the English name, and the spoken spelling when it differs from the caption's. Example: caption "Moonlight Noodle House", transcript "Moon Night Noodle House" -> place_name "Moonlight Noodle House", place_name_alt ["Moon Night Noodle House"]. Only names that are actually said or written. Never a hashtag written as one word (like #luvselfiebooth) or an @account. Empty list [] if there are none.
- name_source: where place_name comes from: "spoken" (said in the video; the caption does not write it), "caption" (written in the caption but not said, or said differently), or "both" (said and written the same way).
- category: one of {CATEGORIES}.
- sub_category: a short detail such as "Vietnamese", or null if not stated.
- price_range: only if a price is stated for THIS place or its items, in the transcript or the caption. Write it as given, for example "$5-10" or "10,000 riel". Otherwise null.
- area: list of the districts from {DISTRICTS} that the transcript or the caption names for THIS place (also in Khmer, e.g. ចំការមន = Chamkar Mon). A place can have several branches, so list every district named for it. If a neighborhood or other area is named (for example BKK1 or Toul Tom Poung), do NOT put it here. Null if no district is named.
- area_description: any wording about where the place is (district, neighborhood, street, landmark), as said or written (for example the caption's "📍 Toul Kork"), or null. Fill it even when area is also filled.
- opening_hours: only if said or written, as given, or null.
- speaker_opinion: a short summary (1 to 3 sentences) of why a visitor would want to go to THIS place, based ONLY on what the speaker says or the creator writes in the caption.
    Include what is good, special or interesting about the place: taste, price or value, choices, atmosphere, space, seating, photo spots, service, decor, theme or story of the place.
    Rewrite it in clear, natural words instead of copying the sentence, but keep the real meaning. Do not make it stronger than the speaker said, and do not add praise or facts that were not said or written.
    Leave out the speaker's own story that does not help a visitor (why they came, their trip, greetings, asking viewers to follow).
    Write it in the same language the speaker mainly uses about this place. Do not translate.
    Null if nothing good or interesting is said or written about the place.
- menu_items: list of food and drink items named for this place, in the transcript or the caption. Null if none.
- notes: other useful details that fit no field above (for example promos about that place). Do not add details that were not said or written.
- evidence_text: one short snippet copied EXACTLY from the transcript or the caption that proves the place name. Under 200 characters.
- segment_ids: ids of the transcript segments that talk about this place. Never give an id for something only the caption says. Empty list [] if no segment talks about it (only the caption names it).
- confidence: for place_name, category, price_range and area, give "high", "medium", "low", or null if the value is null.
    high = clearly said or written; medium = implied or spelling uncertain; low = unclear.
- missing_reasons: for each null field (price_range, area, sub_category, opening_hours, area_description, speaker_opinion, menu_items), provide a short reason such as "not mentioned" or "no price tied to this place".

DO NOT:
- Make a record for anything the video does not show or visit: sponsors, tagged @accounts, the creator's own channel, delivery apps (e.g. MotoKew, GrabFood), or hashtags of other places or general topics (#phnompenh, #fyp). A hashtag or an @account alone is never a place.
- Put promotional content (promo codes, subscriptions, delivery offers) into place fields. Mention it in notes only if it is about that place.
- Use general price comments that are not tied to one place (for example "you can buy a drink with only 10,000").
- Fix a spelling by guessing. Only the caption may correct a heard name. If a heard name looks like a speech recognition error and the caption does not name the place, keep it as spoken and set confidence to "medium" or "low".
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
    name_source: Optional[Literal["spoken", "caption", "both"]] = None
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


def gemini_input(window: List[dict], caption: Optional[str]) -> str:
    """What Gemini reads: the numbered transcript part (or "[no speech]"), then the caption if there is one."""
    if window:
        text = "Transcript excerpt:\n" + "\n".join(f"[{s['id']}] {s['text']}" for s in window)
    else:
        text = f"Transcript: {NO_SPEECH} (nobody speaks in this video)"
    if caption:
        text += f"\n\nTikTok caption (written by the creator; it has no segment ids):\n<caption>\n{caption}\n</caption>"
    return text


def call_model(client, window, models, caption=None):
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        response_schema=ExtractionResponse,
    )
    resp, model = generate_with_backup(client, models, gemini_input(window, caption), config)
    if resp.parsed is not None:
        return [p.model_dump() for p in resp.parsed.places], model
    try:  # the answer only as JSON text: check it against the same format
        return [p.model_dump() for p in ExtractionResponse.model_validate(json.loads(resp.text or "")).places], model
    except (ValueError, ValidationError):
        raise ClipError(f"{model} did not answer in the expected format. Try this clip again.") from None


def clean_names(values, main: Optional[str]) -> List[str]:
    """Other names: text only, no #hashtags or @accounts, no repeats and not the main name
    (compared like stage 5c does, ignoring capitals, spaces and punctuation)."""
    names, seen = [], {name_key(main)}
    for v in as_list(values):
        v = v.strip() if isinstance(v, str) else ""
        if v and not TAG_ONLY.fullmatch(v) and name_key(v) not in seen:
            names.append(v)
            seen.add(name_key(v))
    return names


def place_status(record: dict, score: float, flags: List[str]) -> str:
    """The usual status, but no real name or a tag-only name is rejected, and a place the transcript doesn't
    back up (name from the caption, or no valid sentence) is never auto_added: it may be a sponsor."""
    if "no_place_name" in flags or "name_is_tag" in flags:
        return "rejected"
    status = verification_status(record, score)
    unbacked = "name_from_caption" in flags or not record["segment_ids"]
    return "needs_review" if status == "auto_added" and unbacked else status


def already_said(text: Optional[str], words: str) -> bool:
    """words are in text as whole words (capitals and extra spaces ignored): "street 5" is not in "street 51"."""
    def clean(t):
        return " ".join(unicodedata.normalize("NFC", t or "").lower().split())
    found = clean(words)
    if has_khmer(found):  # Khmer has no spaces between words, so there are no word edges to check
        return bool(found) and found in clean(text)
    return bool(found) and re.search(rf"(?<!\w){re.escape(found)}(?!\w)", clean(text)) is not None


def add_location(description: Optional[str], extra: Optional[str]) -> Optional[str]:
    """area_description with extra added after "; ", unless it already says it, so no location words are lost."""
    if not extra or already_said(description, extra):
        return description
    return f"{description}; {extra}" if description else extra


def add_new_names(description: Optional[str], names: List[str], prefix: str = "") -> Optional[str]:
    """Add the names (districts, neighborhoods) that area_description doesn't say yet, each checked on its own."""
    new = [n for n in names if not already_said(description, n)]
    return add_location(description, prefix + ", ".join(new)) if new else description


def merge_descriptions(description: Optional[str], later: Optional[str], own_district: Optional[str]) -> Optional[str]:
    """Add a later part's area_description piece by piece ("; "), so nothing is written twice and
    "also: <district>" never names the place's own district."""
    for piece in (later or "").split(";"):
        piece = piece.strip()
        if piece.startswith("also:"):
            names = [n.strip() for n in piece[len("also:"):].split(",")]
            description = add_new_names(description, [n for n in names if n and norm(n) != norm(own_district)], "also: ")
        else:
            description = add_location(description, piece or None)
    return description


def build_record(p, window, caption=None):
    by_id = {s["id"]: s for s in window}
    raw_ids = p.get("segment_ids") or []
    seg_ids = [i for i in raw_ids if i in by_id]
    spoken = " ".join(s["text"] for s in window)
    window_text, caption_text = norm(spoken), norm(caption)
    conf = p.get("confidence") or {}
    flags = []

    area, not_districts = match_districts(p.get("area"), AREAS)
    area_description = p.get("area_description")
    if not_districts:
        flags.append("area_not_in_areas_list")
        area_description = add_new_names(area_description, not_districts)
    # One district per place for now (branches: Capstone 2).
    area_description = add_new_names(area_description, area[1:], "also: ")

    name = name_key(p.get("place_name"))
    if not name:
        flags.append("no_place_name")
    elif TAG_ONLY.fullmatch(p["place_name"].strip()):
        flags.append("name_is_tag")
    evidence = norm(p.get("evidence_text") or "")
    if not evidence or (evidence not in window_text and evidence not in caption_text):
        flags.append("evidence_not_found_in_transcript")
    # With no speech, every name comes from the caption. Otherwise Gemini says so, or the code sees it.
    if name and (not window or p.get("name_source") == "caption"
                 or (name not in name_key(spoken) and name in name_key(caption))):
        flags.append("name_from_caption")
    # No sentence numbers is fine for a place only the caption names, but not when Gemini gave wrong ones.
    ids_problem = not seg_ids and (bool(raw_ids) or "name_from_caption" not in flags)
    flags += checked_flags(conf, ids_problem)

    raw_missing = p.get("missing_reasons") or {}
    if hasattr(raw_missing, "model_dump"):
        raw_missing = raw_missing.model_dump()
    cleaned_missing = {k: v for k, v in raw_missing.items() if v}

    record = {
        "place_id": None,
        "place_name": p.get("place_name"),
        "place_name_alt": clean_names(p.get("place_name_alt"), p.get("place_name")),
        "category": p.get("category"),
        "sub_category": p.get("sub_category"),
        "price_range": p.get("price_range"),
        "area": area[0] if area else None,
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
        "verification_status": None,
        "cleaned_by": None,
        "cleaner_note": None,
        "notes": p.get("notes"),
        "confidence": conf,
        "missing_reasons": cleaned_missing,
        "evidence_text": p.get("evidence_text"),
        "segment_ids": seg_ids,
        "flags": flags,
    })
    record["verification_status"] = place_status(record, score, flags)
    return record


def checked_flags(conf: dict, ids_problem: bool) -> List[str]:
    """Flags that depend on the sentence numbers and Gemini's confidence."""
    flags = []
    if ids_problem:
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
        first[key] = combined if combined or key == "place_name_alt" else None
    first["place_name_alt"] = clean_names(first["place_name_alt"], first.get("place_name"))
    for key in FILL_IF_EMPTY:
        if not first.get(key) and later.get(key):
            first[key] = later[key]
            if key in ("category", "price_range", "area"):
                first["confidence"][key] = later["confidence"].get(key)
    # Every part's location words are kept (its "also: ..." districts too), and its district if it differs.
    desc = merge_descriptions(first.get("area_description"), later.get("area_description"), first.get("area"))
    if first.get("area") and later.get("area") and later["area"] != first["area"]:
        desc = add_new_names(desc, [later["area"]], "also: ")
    first["area_description"] = desc
    first["segment_ids"] = sorted(set(first["segment_ids"]) | set(later["segment_ids"]))
    first["missing_reasons"] = {k: v for k, v in first["missing_reasons"].items() if not first.get(k)}

    # Name and evidence_text are the first part's, so their checks stay; so does an area problem from either part.
    flags = [f for f in first["flags"] if f in ("no_place_name", "name_is_tag", "evidence_not_found_in_transcript")]
    if "area_not_in_areas_list" in first["flags"] + later["flags"]:
        flags.append("area_not_in_areas_list")
    # Spoken in any part = not only from the caption.
    if "name_from_caption" in first["flags"] and "name_from_caption" in later["flags"]:
        flags.append("name_from_caption")
    ids_problem = not first["segment_ids"] and "no_valid_segment_ids" in first["flags"] + later["flags"]
    first["flags"] = flags + checked_flags(first["confidence"], ids_problem)

    score, missing_fields = completeness(first)
    first.update(completeness=score, missing_fields=missing_fields,
                 verification_status=place_status(first, score, first["flags"]))


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
    source = clip.get("source") or {}
    if source.get("caption", "") == "":
        raise ClipError("The TikTok caption hasn't been read yet. Run stage 2 (it reads the caption only, no download): "
                        f"python stage2_get_audio.py {display_path(path)}\n"
                        "  If the video is gone, write null in source.caption.")
    caption = source["caption"].strip() if isinstance(source["caption"], str) else ""
    if transcript.strip() == NO_SPEECH:
        if not caption:
            print(f"{clip_id}: no speech and no caption, so no places to find. Skipped.")
            return "skipped"
        parts = [[]]
        print(f"{clip_id}: no speech; finding places in the TikTok caption with {models[0]} ...", flush=True)
    else:
        segments = split_transcript(transcript)
        parts = list(windows(segments))
        print(f"{clip_id}: finding places in {len(segments)} sentences{' and the caption' if caption else ''} "
              f"with {models[0]} ...", flush=True)

    records, seen_places, used_models = [], {}, set()
    for window in parts:
        places, used_model = call_model(client, window, models, caption)
        used_models.add(used_model)
        for p in places:
            key = name_key(p.get("place_name"))
            if key and TAG_ONLY.fullmatch(p["place_name"].strip()):
                key = "tag:" + key  # never joined to the real place, so its name can't be lost
            if key and key in seen_places:
                merge_record(seen_places[key], build_record(p, window, caption))
                continue
            rec = build_record(p, window, caption)
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
        also = f"; also called {', '.join(r['place_name_alt'])}" if r["place_name_alt"] else ""
        source = (", only a tag, not a place name" if "name_is_tag" in r["flags"]
                  else ", name from caption" if "name_from_caption" in r["flags"] else "")
        print(f"  - {r['place_name'] or '(no name)'} ({r['category'] or 'no category'}): "
              f"{r['verification_status']}{source}{also}")
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
