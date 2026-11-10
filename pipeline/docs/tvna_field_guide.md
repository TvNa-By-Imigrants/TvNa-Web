# TVNA JSON field guide

We use **4 kinds of JSON files**. This guide shows each one **in full**, with the **same example place** (Tea Kingdom), so you can see how they connect. Example values only, not real data.

- The full process is in the Google Doc "TVNA Data Pipeline".
- The class diagram is in `audio-text/docs/tvna_data_model.png`.
- The scripts and empty templates are in `text-json/`.

Missing information is always `null` (never `""`, "N/A" or "Unknown").

---

## 1. The 4 files, in full

### File 1: Clip file (`clips/02.json`), one per video

This is the main file. Every stage adds to it. Start each new clip from `tvna_clip_template.json`.

```json
{
  "clip_id": "02",
  "audio_file": "02.wav",
  "source": {
    "url": "https://www.tiktok.com/@motokew/video/...",
    "platform": "tiktok",
    "creator": "@motokew",
    "posted_at": "2026-10-22",
    "collected_at": "2026-11-08"
  },
  "stt": {
    "tool": "gemini",
    "model": "gemini-3.8-flash",
    "settings": "km+en code-switching prompt",
    "transcript": "... Next stop is a tea place called Tea Kingdom ..."
  },
  "ground_truth": null,
  "extraction": {
    "method": "llm",
    "model": "gemini-3.5-flash",
    "prompt_version": "v4"
  },
  "fields": [
    {
      "place_id": "tvna_p_0005",
      "place_name": "Tea Kingdom",
      "place_name_alt": [],
      "category": "cafe",
      "sub_category": "tea",
      "price_range": null,
      "area": ["Boeng Keng Kang"],
      "area_description": null,
      "google_maps_url": "https://maps.app.goo.gl/...",
      "opening_hours": null,
      "speaker_opinion": "Recommends the Jasmine tea and the Osmanthus Oolong tea.",
      "menu_items": ["Jasmine tea", "Osmanthus Oolong tea"],
      "completeness": 0.67,
      "missing_fields": ["area"],
      "verification_status": "verified",
      "cleaned_by": "team member name",
      "cleaner_note": "Area and map link found on Google Maps.",
      "notes": null,
      "confidence": {
        "place_name": "high",
        "category": "high",
        "price_range": null,
        "area": null
      },
      "missing_reasons": {
        "price_range": "not mentioned",
        "area": "not mentioned",
        "area_description": "not mentioned",
        "opening_hours": "not mentioned"
      },
      "evidence_text": "Next stop is a tea place called Tea Kingdom",
      "segment_ids": [3],
      "flags": []
    }
  ],
  "notes": null
}
```

Here `completeness` is 0.67 because stage 4 found no district. The team added `area` later (see section 5).

Another clip, `07.json` from creator `@foodkh`, also talks about Tea Kingdom. So its place also has `"place_id": "tvna_p_0005"`.

### File 2: `places.json`, one list for the whole project

One entry per **real place**: its name, districts, map link and every name people use for it. `match_places.py` creates and updates this file (stage 5c).

```json
[
  {
    "place_id": "tvna_p_0005",
    "place_name": "Tea Kingdom",
    "aliases": ["Tea Kingdom", "TeaKingdom", "(Khmer name)"],
    "area": ["Boeng Keng Kang"],
    "google_maps_url": "https://maps.app.goo.gl/..."
  }
]
```

### File 3: `areas.json`, the fixed district list

Phnom Penh's 14 districts. Code and team **pick** from this list; nobody types a district by hand.

```json
[
  { "district": "Boeng Keng Kang", "district_km": "បឹងកេងកង" },
  { "district": "Chamkar Mon", "district_km": "ចំការមន" },
  { "district": "Chbar Ampov", "district_km": "ច្បារអំពៅ" },
  { "district": "Chrouy Changvar", "district_km": "ជ្រោយចង្វារ" },
  { "district": "Dangkao", "district_km": "ដង្កោ" },
  { "district": "Daun Penh", "district_km": "ដូនពេញ" },
  { "district": "Kamboul", "district_km": "កំបូល" },
  { "district": "Mean Chey", "district_km": "មានជ័យ" },
  { "district": "Pou Senchey", "district_km": "ពោធិ៍សែនជ័យ" },
  { "district": "Prampi Makara", "district_km": "ប្រាំពីរមករា" },
  { "district": "Prek Pnov", "district_km": "ព្រែកព្នៅ" },
  { "district": "Russey Keo", "district_km": "ឫស្សីកែវ" },
  { "district": "Sen Sok", "district_km": "សែនសុខ" },
  { "district": "Tuol Kouk", "district_km": "ទួលគោក" }
]
```

The English and the Khmer name both match. For example, ចំការមន becomes `"Chamkar Mon"`.

### File 4: `final_dataset.json`, one record per place, for the website

Made automatically in stage 6 from the 3 files above.

```json
{
  "place_id": "tvna_p_0005",
  "place_name": "Tea Kingdom",
  "place_name_alt": ["TeaKingdom", "(Khmer name)"],
  "category": ["cafe"],
  "price_range": [],
  "area": ["Boeng Keng Kang"],
  "area_description": [],
  "google_maps_url": "https://maps.app.goo.gl/...",
  "opening_hours": [],
  "menu_items": ["Jasmine tea", "Osmanthus Oolong tea"],
  "popularity": 2,
  "mentions": [
    {"clip_id": "02", "creator": "@motokew", "speaker_opinion": "Recommends the Jasmine tea and the Osmanthus Oolong tea."},
    {"clip_id": "07", "creator": "@foodkh",  "speaker_opinion": "..."}
  ]
}
```

---

## 2. How they connect

A link means the **same value is written in two files**.

| Link | Written in | Points to | Example |
|---|---|---|---|
| Which place? | `fields[].place_id` in the clip file | `place_id` in places.json | `"tvna_p_0005"` |
| Which district? | `fields[].area` and `area` in places.json | `district` in areas.json | `"Boeng Keng Kang"` |
| Which clip? | `mentions[].clip_id` in the final dataset | `clip_id` in the clip file | `"02"` |

Stage 6 joins everything. For each `place_id` it finds all clips with that id:
- `popularity` = number of **different creators** (here `@motokew` + `@foodkh` = 2).
- `mentions` = one entry per clip: `clip_id`, `creator`, `speaker_opinion`.
- `category`, `price_range`, `area`, `area_description`, `opening_hours`, `menu_items` = **lists of unique values** from all clips. `area` also takes the districts from places.json.
- The script warns when clips disagree on `category`, `price_range` or `opening_hours`. The team checks these.
- Places that are `rejected`, or have no `place_id`, are left out.
- A clip with no `creator` is still listed in `mentions`, but it does not count in `popularity`.

**Key rule:** linked values must be spelled **exactly the same**. "Boeung Keng Kang" and "Boeng Keng Kang" do not match.

### One clip, many places

One video can review 3 or 4 places. Then `fields` has one object per place. Each object has its own `area`, `speaker_opinion`, score and status.
- Each place gets its own `place_id` in stage 5c.
- In the final dataset, the clip is one mention in **each** place's record and adds +1 `popularity` to each.
- If the same place is named twice in one clip, it becomes one mention, with both opinions joined by "; ".
- Team: check list videos ("top 5 cafes") carefully. The LLM can mix up opinions or areas between places.

---

## 3. Who fills what (clip file)

Anything not filled yet stays `null`.

| Stage | Who | Fields | Script (in `text-json/`) |
|---|---|---|---|
| 1. Collect data | Person | `clip_id`, `source` (url, platform, creator, posted_at, collected_at) | none, start from `tvna_clip_template.json` |
| 2. Video to audio | Script | `audio_file` | in `audio-text/` |
| 3. Audio to transcript | Script + Gemini | `stt`. Person: `ground_truth` (test clips only) | in `audio-text/` |
| 4. Transcript to fields | LLM + code | `extraction` and every place in `fields` (see below) | `extract_places_gemini.py` |
| 5a. Remove duplicates | Script | moves duplicate clip files, adds `duplicate_of` | `dedupe_clips.py` |
| 5b. Team review | Team | `area` (if empty), `google_maps_url`, missing values, `cleaned_by`, `cleaner_note`, status `verified` or `rejected` | none, edit the clip file |
| 5c. Match places | Script, then team | `place_id` (never the LLM), places.json | `match_places.py` |
| 6. Final dataset | Script | `final_dataset.json` | `build_final_dataset.py` |

In stage 4:
- **LLM fills:** `place_name`, `place_name_alt`, `category`, `sub_category`, `price_range`, `area`, `area_description`, `opening_hours`, `speaker_opinion`, `menu_items`, `notes`, `confidence`, `missing_reasons`, `evidence_text`, `segment_ids`.
- **Code fills:** checks `area` against areas.json, then sets `completeness`, `missing_fields`, `verification_status` and `flags`.
- **Stays null:** `place_id`, `google_maps_url`, `cleaned_by`, `cleaner_note`.

### Value rules

| Field | Rule |
|---|---|
| `place_name` | Name as spoken, in English if an English name is said |
| `place_name_alt` | Khmer name and other names said **in this clip only**. All known names go in `aliases` in places.json |
| `category` | One value from the category list (section 9) |
| `sub_category` | Short free text, e.g. "tea", "Vietnamese" |
| `price_range` | Only if said for this place, as spoken, e.g. "$5-10", "10,000 riel" |
| `area` | **List** of districts from areas.json. Code fills it only when the speaker names a district (English or Khmer). A list because one place can have branches in several districts |
| `area_description` | What the speaker said about the location, e.g. "near Russian Market". Filled even when `area` is filled |
| `opening_hours` | Only if said, as spoken, e.g. "7am-10pm" |
| `speaker_opinion` | Summary of why a visitor would go (section 4) |
| `menu_items` | List of food and drink items named for this place, as spoken |
| `notes` | Other useful details about this place, e.g. a promo |

A neighborhood (BKK1, Toul Tom Poung) is **not** a district. It goes in `area_description`, and the team picks the district.

### Review helpers (clip file only, not in the final dataset)

| Field | Meaning |
|---|---|
| `confidence` | "high", "medium", "low" or null for `place_name`, `category`, `price_range`, `area` |
| `missing_reasons` | Why a field is null, e.g. "not mentioned" |
| `evidence_text` | A short piece copied exactly from the transcript that shows the place name |
| `segment_ids` | Numbers of the transcript sentences about this place |
| `flags` | Warnings for the team (table below) |

| Flag | Meaning | What the team does |
|---|---|---|
| `no_place_name` | No name found | Status is already `rejected`. Check if the name was missed |
| `no_valid_segment_ids` | The LLM gave sentence numbers that do not exist | Check the transcript |
| `evidence_not_found_in_transcript` | `evidence_text` is not in the transcript; the LLM may have made it up | Check the name in the transcript |
| `asr_spelling_or_uncertain_name` | Name confidence is medium or low; maybe a speech-to-text spelling error | Check the spelling on Google Maps |
| `low_confidence_field` | `category`, `price_range` or `area` has low confidence | Check those fields |
| `area_not_in_areas_list` | The LLM gave an area that is not a district; it was moved to `area_description` | Pick the district |

---

## 4. `speaker_opinion` (how the LLM writes it)

- 1 to 3 sentences: why a visitor would want to go to **this** place, based only on what the speaker says.
- Covers what is good or interesting: taste, price or value, choices, atmosphere, space, seating, photo spots, service, decor, theme or story.
- Rewritten in clear words, with the same meaning. Never stronger than the speaker said; no added praise or facts.
- Leaves out the speaker's own story (why they came, their trip, greetings, "follow us").
- Written in the language the speaker uses for this place. Not translated.
- `null` if the speaker says nothing good or interesting about the place.

Real output from `clips/02.json` (prompt v4): "The shop has many kinds of motorbikes available starting from $9 per day, and the owner is generous and kind."

---

## 5. Completeness and status (stage 4)

`completeness` = filled fields ÷ 3. The 3 fields:
- `place_name`
- `area`: the website filters places by district.
- `speaker_opinion`: the text that makes people want to visit.

These 3 come from the team's research on 10 clips. The other fields are still extracted but not counted.

| Result | `verification_status` |
|---|---|
| No `place_name` | `rejected` (kept in the file, not deleted) |
| 0.33 or 0.67 | `needs_review` (team fills missing fields) |
| 1.0 | `auto_added` (still checked later) |

The rule in code: no name or below 0.3 → `rejected`; 0.7 or below → `needs_review`; above 0.7 → `auto_added`.

A person changes the status to `verified` (or `rejected`) after checking. The score is set once in stage 4. It is **not** calculated again after the team fills fields.

---

## 6. Location flow (team review, stage 5b)

1. Read `area_description` and `area` (what the speaker said).
2. Search the place on Google Maps.
3. Check it is the right place (name, photos, type).
4. Copy the Share link into `google_maps_url`.
5. Pick the district from areas.json, using the Maps address. Write it in `area` as a list, e.g. `["Chamkar Mon"]`. For branches, add one district per branch.
6. Can't find it? Leave both `null` and explain in `cleaner_note`.
7. Write your name in `cleaned_by` and set the status.

Example: "near Russian Market" → found on Google Maps → address in Chamkar Mon → `"area": ["Chamkar Mon"]`.

Fill `google_maps_url` before stage 5c. `match_places.py` copies it into places.json only when it creates a new place. After that, edit the link in places.json.

---

## 7. Removing duplicates (stage 5a)

The same video must not be counted twice in `popularity`.

- **Same video** = same video id in `source.url` (TikTok `/video/<number>`, YouTube, Instagram reel), or the same address for other links.
- The first clip by file name is kept. The others move to `clips/duplicates/` with `"duplicate_of": "<kept clip_id>"`.
- Nothing is deleted. To undo, move the file back.
- Only the URL is checked, not the transcript.
- Short links (`vt.tiktok.com/...`) are not opened. A short link and a full link to the same video are **not** caught. Paste the full link when you can.
- It only reads `source.url`, so you can also run it before stage 4 to save API calls.

---

## 8. Matching places (stage 5c)

How a clip place gets its `place_id` (`match_places.py`):

1. Clean the name: Unicode NFC, remove all spaces, lowercase.
2. Compare `place_name` and `place_name_alt` with `place_name` and `aliases` of every entry in places.json. **Exact match only.**

| Result | What happens | Report group |
|---|---|---|
| One place matches | Reuse its `place_id`. New names are added to `aliases`, new districts to `area` | matched |
| No place matches | New entry in places.json with a new id (`tvna_p_0006`, ...) | new |
| More than one place matches | `place_id` stays null. The team picks the id from places.json and writes it in the clip | unclear |

- Skipped: places that already have a `place_id`, `rejected` places, places with no name.
- A `place_id` that is not in places.json is reported as `unknown_id`.
- The team checks the report. For matched and new places, confirm it is the right place by name, aliases and `google_maps_url`.
- One alias belongs to one place only.
- Branches of one shop = one place, with every branch's district in `area`.
- Running the script again does not create duplicate places.

---

## 9. Category list

- Food & drink: `restaurant`, `cafe`, `bar`, `street_food`
- Sightseeing: `temple`, `museum`, `park`, `viewpoint`, `beach`
- Shopping: `market`, `mall`, `shop`
- Activities & stay: `entertainment`, `hotel`, `other`

---

## 10. How to run (in `text-json/`)

Setup, once:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then put your GEMINI_API_KEY in .env
```

Run in this order:

```sh
.venv/bin/python extract_places_gemini.py clips/02.json   # stage 4 (add --force to redo a clip)
.venv/bin/python dedupe_clips.py clips/*.json             # stage 5a
# stage 5b: team review in the clip files
.venv/bin/python match_places.py clips/*.json             # stage 5c
.venv/bin/python build_final_dataset.py clips/*.json      # stage 6 -> final_dataset.json
```

Empty templates: `tvna_clip_template.json`, `tvna_clip_place_template.json`, `tvna_places_template.json`, `tvna_areas_template.json`, `tvna_final_dataset_template.json`.

---

## 11. Open items (not decided or not built yet)

- **Sponsored:** removed for now. One value per clip would count for every place in a multi-place clip. If it comes back, it should be per place.
- **Similar names:** only exact matches. A typo ("Tea Kingdon") becomes a new place. A similarity score (for example 95 = same, 75–95 = team decides) is not built.
- **Final dataset extras:** `url` and `posted_at` in `mentions`, and `sub_category`, are not included.
- **Score after review:** `completeness` is not recalculated after the team fills fields.
- **Outside Phnom Penh:** places in other provinces (e.g. Siem Reap in `clips/02.json`) are not rejected automatically. The team decides.
- **Branches:** a place has one `google_maps_url`, even with several branches.
- **STT script:** `audio-text/test/test_gemini.py` still writes the old format (`source.timestamp`, file `<name>_gemini.json`), not the clip template.
- **Older docs:** the Google Doc and the older diagrams (`tvna_json_files_diagram.png`, `tvna_pipeline_overview.png`) may not match this guide.
