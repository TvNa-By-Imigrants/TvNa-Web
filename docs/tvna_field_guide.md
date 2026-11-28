# TVNA JSON field guide

We use **4 kinds of JSON files** (the 5th template, `tvna_clip_place_template.json`, is one place inside a clip file). This guide shows each one **in full**, with the **same example place** (Tea Kingdom), so you can see how they connect. Example values only, not real data.

- The full process, stage by stage: [tvna_pipeline_explained.md](tvna_pipeline_explained.md).
- How the files connect: `docs/tvna_data_model.mmd`.
- The scripts are in the repo root (`stage1_new_clip.py` … `stage6_build_final_dataset.py`); empty templates are in `templates/`.
- Where the files are: clip files in `data/clips/`, `areas.json` in `data/reference/`, `places.json` and `final_dataset.json` in `data/results/`.
- How to run each stage, and the team review steps: the [README](../README.md).

Missing information is always `null` (never `""`, "N/A" or "Unknown").

---

## 1. The 4 files, in full

### File 1: Clip file (`clips/PP-002.json`), one per video

This is the main file. Every stage adds to it. Start each new clip from `tvna_clip_template.json`.

```json
{
  "clip_id": "PP-002",
  "audio_file": "PP-002.wav",
  "source": {
    "url": "https://www.tiktok.com/@motokew/video/7000000000000000002",
    "video_id": "7000000000000000002",
    "platform": "tiktok",
    "creator": "@motokew",
    "caption": "Tea time at Tea Kingdom 🍵 #phnompenh",
    "cover_url": "https://res.cloudinary.com/<cloud name>/image/upload/v…/tvna/covers/PP-002.jpg",
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
    "model": "gemini-3.6-flash",
    "prompt_version": "v5"
  },
  "fields": [
    {
      "place_id": "tvna_p_0005",
      "place_name": "Tea Kingdom",
      "place_name_alt": [],
      "category": "cafe",
      "sub_category": "tea",
      "price_range": null,
      "area": "Boeng Keng Kang",
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

Another clip, `PP-007.json` from creator `@foodkh`, also talks about Tea Kingdom. So its place also has `"place_id": "tvna_p_0005"`.

### File 2: `places.json`, one list for the whole project

One entry per **real place**: its name, districts, map link and every name people use for it. `stage5c_match_places.py` creates and updates this file.

```json
[
  {
    "place_id": "tvna_p_0005",
    "place_name": "Tea Kingdom",
    "aliases": ["Tea Kingdom", "TeaKingdom", "(Khmer name)"],
    "area": "Boeng Keng Kang",
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

**One name per place:** `place_name` comes from places.json. Other names (`aliases` in places.json, `place_name_alt` in the clips) are **not** in this file. They stay in the pipeline only, for matching. Stage 5c only creates a place from a `verified` clip, so the name the team approved in 5b becomes the website name (section 6, "Name").

```json
{
  "place_id": "tvna_p_0005",
  "place_name": "Tea Kingdom",
  "category": ["cafe"],
  "price_range": [],
  "area": "Boeng Keng Kang",
  "area_description": [],
  "google_maps_url": "https://maps.app.goo.gl/...",
  "opening_hours": [],
  "menu_items": ["Jasmine tea", "Osmanthus Oolong tea"],
  "popularity": 2,
  "mentions": [
    {"clip_id": "PP-002", "creator": "@motokew", "speaker_opinion": "Recommends the Jasmine tea and the Osmanthus Oolong tea."},
    {"clip_id": "PP-007", "creator": "@foodkh",  "speaker_opinion": "..."}
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
| Which clip? | `mentions[].clip_id` in the final dataset | `clip_id` in the clip file | `"PP-002"` |

Stage 6 joins everything. For each `place_id` it finds all clips with that id:
- `place_name` = the name in places.json. If it is empty, the script writes `null` and warns.
- Places with no `place_id` yet are counted in one warning line. Stage 5c lists them one by one.
- `popularity` = number of **different creators** (here `@motokew` + `@foodkh` = 2).
- `mentions` = one entry per clip: `clip_id`, `creator`, `speaker_opinion`.
- `category`, `price_range`, `area_description`, `opening_hours`, `menu_items` = **lists of unique values** from all clips.
- `area` = **one district** (text, or `null`): the district in places.json, else the first one from the clips. If the clips name other districts (e.g. branches), the script warns and keeps the places.json one. One district per branch is for Capstone 2.
- The script warns when clips disagree on `category`, `price_range` or `opening_hours`. The team checks these.
- Only `verified` places with a `place_id` are published. Others are left out; one that has a `place_id` but isn't `verified` gets a warning.
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

| Stage | Who | Fields | Script |
|---|---|---|---|
| 1. Collect data | Person gives the links; script | `clip_id`, `source` (url, video_id, platform, creator, collected_at; posted_at if given). Duplicates get no clip file | `stage1_new_clip.py` |
| 2. Video to audio | Script | `audio_file`, `source.caption` (the creator's TikTok caption, hashtags included; `null` if none), `source.cover_url` (the video's cover on Cloudinary; `null` if TikTok has none, `""` = not saved yet), `source.posted_at` if empty | `stage2_get_audio.py` |
| 3. Audio to transcript | Script + Gemini | `stt`. Person: `ground_truth` (test clips only) | `stage3_transcribe.py` |
| 4. Transcript + caption to fields | LLM + code | `extraction` and every place in `fields` (see below) | `stage4_extract_places.py` |
| 5a. Remove duplicates | Script | moves duplicate clip files, adds `duplicate_of` | `stage5a_dedupe_clips.py` |
| 5b. Team review | Team | `area` (if empty), `google_maps_url`, missing values, `cleaned_by`, `cleaner_note`, status `verified` or `rejected` | edit the clip file; check it with `stage5b_validate_clips.py` |
| 5c. Match places | Script, then team | `place_id` (never the LLM; `verified` places only), places.json | `stage5c_match_places.py` |
| 6. Final dataset | Script | `final_dataset.json` | `stage6_build_final_dataset.py` |

In stage 4:
- **LLM fills:** `place_name`, `place_name_alt`, `category`, `sub_category`, `price_range`, `area`, `area_description`, `opening_hours`, `speaker_opinion`, `menu_items`, `notes`, `confidence`, `missing_reasons`, `evidence_text`, `segment_ids`.
- **Code fills:** checks `area` against areas.json, then sets `completeness`, `missing_fields`, `verification_status` and `flags`.
- **Stays null:** `place_id`, `google_maps_url`, `cleaned_by`, `cleaner_note`.

### Value rules

| Field | Rule |
|---|---|
| `place_name` | The English name if one is said or written, otherwise the Khmer name. When the TikTok caption writes that name, the caption's spelling is used (speech-to-text may mishear it). In 5b the team picks the right one (it may swap it with a name in `place_name_alt`); see "Name" in section 6 |
| `place_name_alt` | Every other name said or written **in this clip only**: Khmer name, English name, and the heard spelling when it differs from the caption (e.g. "ALWAYS selfie booth" when the caption says "Luv selfie booth"). Never a #hashtag or @account. All known names go in `aliases` in places.json. Never shown on the website |
| `category` | One value from the category list (section 9) |
| `sub_category` | Short free text, e.g. "tea", "Vietnamese" |
| `price_range` | Only if said or written (caption) for this place, as given, e.g. "$5-10", "10,000 riel" |
| `area` | **One district** from areas.json, as text, e.g. `"Chamkar Mon"`. Stage 4 fills it only when the speaker or the caption names a district (English or Khmer); if it names more than one, the first goes here and the others go in `area_description` ("also: …"). One district per branch is for Capstone 2 |
| `area_description` | What the speaker or the caption says about the location, e.g. "near Russian Market", "📍 Toul Kork". Filled even when `area` is filled |
| `opening_hours` | Only if said or written, as given, e.g. "7am-10pm" |
| `speaker_opinion` | Summary of why a visitor would go (section 4) |
| `menu_items` | List of food and drink items named for this place, in the video or the caption |
| `notes` | Other useful details about this place, e.g. a promo |

A neighborhood (BKK1, Toul Tom Poung) is **not** a district. It goes in `area_description`, and the team picks the district.

### Review helpers (clip file only, not in the final dataset)

| Field | Meaning |
|---|---|
| `confidence` | "high", "medium", "low" or null for `place_name`, `category`, `price_range`, `area` |
| `missing_reasons` | Why a field is null, e.g. "not mentioned" |
| `evidence_text` | A short piece copied exactly from the transcript or the caption that shows the place name |
| `segment_ids` | Numbers of the transcript sentences about this place. Can be `[]` when only the caption names it |
| `flags` | Warnings for the team (table below) |

| Flag | Meaning | What the team does |
|---|---|---|
| `no_place_name` | No name found, or the "name" has no letters (e.g. only "📍") | Status is already `rejected`. Check if the name was missed |
| `no_valid_segment_ids` | The LLM gave sentence numbers that do not exist (not used for a place named only in the caption) | Check the transcript |
| `evidence_not_found_in_transcript` | `evidence_text` is in neither the transcript nor the caption; the LLM may have made it up | Check the name in the transcript and caption |
| `name_from_caption` | `place_name` is written in the caption but not said in the video (not said at all, or heard differently). Set when Gemini says so or the code sees it. Every place of a `[no speech]` clip has it. Such a place is never `auto_added` | Check it is the place the video shows, not a sponsor; pick the right name from `place_name` / `place_name_alt` |
| `name_is_tag` | The "name" is only @accounts or #hashtags. Status is already `rejected` | If it really is the place, write its real name and change the status |
| `asr_spelling_or_uncertain_name` | Name confidence is medium or low; maybe a speech-to-text spelling error | Check the spelling on Google Maps |
| `low_confidence_field` | `category`, `price_range` or `area` has low confidence | Check those fields |
| `area_not_in_areas_list` | The LLM gave an area that is not a district; it was added to `area_description` (if not already there) | Pick the district |

---

## 4. `speaker_opinion` (how the LLM writes it)

- 1 to 3 sentences: why a visitor would want to go to **this** place, based only on what the speaker says or the creator writes in the caption.
- Covers what is good or interesting: taste, price or value, choices, atmosphere, space, seating, photo spots, service, decor, theme or story.
- Rewritten in clear words, with the same meaning. Never stronger than the speaker said; no added praise or facts.
- Leaves out the speaker's own story (why they came, their trip, greetings, "follow us").
- Written in the language the speaker uses for this place. Not translated.
- `null` if nothing good or interesting is said or written about the place.

Real output from an early test clip (prompt v4): "The shop has many kinds of motorbikes available starting from $9 per day, and the owner is generous and kind."

---

## 5. Completeness and status (stage 4)

`completeness` = filled fields ÷ 3. The 3 fields:
- `place_name`
- `area`: the website filters places by district.
- `speaker_opinion`: the text that makes people want to visit.

These 3 come from the team's research on 10 clips. The other fields are still extracted but not counted.

| Result | `verification_status` |
|---|---|
| No `place_name`, or the name is only a tag (`name_is_tag`) | `rejected` (kept in the file, not deleted) |
| 0.33 or 0.67 | `needs_review` (team fills missing fields) |
| 1.0 | `auto_added` (still checked later); `needs_review` if the transcript doesn't back it up (`name_from_caption`, or no valid sentence numbers) |

The rule in code: no name or below 0.3 → `rejected`; 0.7 or below → `needs_review`; above 0.7 → `auto_added`.

**`auto_added` does not add the place anywhere.** It is only a label for "looks complete". The place stays in its clip file and still needs a person to set `verified`, exactly like `needs_review`. Neither status is published.

A person changes the status to `verified` (or `rejected`) after checking. Only `verified` places go on to stage 5c and the website. The score is set once in stage 4. It is **not** calculated again after the team fills fields.

---

## 6. Location flow (team review, stage 5b)

1. Read `area_description` and `area` (what the speaker said).
2. Search the place on Google Maps.
3. Check it is the right place (name, photos, type).
4. Copy the Share link into `google_maps_url`.
5. Pick the district from areas.json, using the Maps address. Write it in `area` as text, e.g. `"Chamkar Mon"` (not a list). One district per place for now; for a branch, the district of the branch in the video.
6. Can't find it? Leave both `null`, write what you tried in `cleaner_note`, and keep the status `needs_review` (held back, not on the website). Skip step 7's status.
7. Write your name in `cleaned_by` and set the status: `verified` (it goes on to 5c and the website) or `rejected`.
8. Check your work: `python stage5b_validate_clips.py data/clips/*.json`. It changes nothing and lists mistakes, e.g. a misspelled status (`"verfied"`), a district not spelled as in areas.json (`"7 Makara"` → `"Prampi Makara"`), or `"nothing"` instead of `null`. Fix until it shows `problems (0)`, then run 5c.

Example: "near Russian Market" → found on Google Maps → address in Chamkar Mon → `"area": "Chamkar Mon"`.

Fill `google_maps_url` and `area` before stage 5c. Stage 5c copies the link into places.json only when it creates a new place, and fills the district only when places.json has none (a different one is only reported). So to fix a link or a district after 5c, edit places.json.

### Name

The website shows **one name per place**. Pick it before stage 5c:

1. Check `place_name` against the video, the caption and Google Maps.
2. If a name in `place_name_alt` is the right one, swap them: the right name in `place_name`, the other in `place_name_alt`. Keep the misheard name in `place_name_alt`, so future clips that mishear it the same way still match.

The name only counts when stage 5c **creates** the place in places.json. For a place already in places.json, the website name is `place_name` in places.json: edit it there. The old name is already in `aliases`, so matching still works. When a clip calls a known place something else, stage 5c says so once in its report: `website name stays "…"`.

### Same place, other names

Creators often call one place by different names. Gemini doesn't know the names we already have (planned for Capstone 2), so the team links them in 5b:

1. Copy the Maps link of the **right** place (for a branch, the branch in the video). 5c matches by link first, whatever the names are, so an English name in one clip and a Khmer name in another still match. Check the name, photos and address first: a wrong link joins the clip to the wrong place (if that link is already in places.json) or makes a duplicate place.
2. Search `data/results/places.json` for the name, the other names and the link. If the place is there, check it is the same shop.
3. Add every other name said, written or shown in this video to `place_name_alt`. If the video only says the Khmer name but the caption, the sign or Google Maps shows the English one (or the other way round), add that one too. 5c can't match a Khmer name with an English one by letters.
4. After 5c, decide every unclear place, and check every matched one.

---

## 7. Removing duplicates (stage 1, then 5a)

The same video must not be counted twice in `popularity`, and must not cost Gemini tokens twice.

- **Same video** = the same TikTok video number (`/video/<number>`), saved in `source.video_id` and in `source.url`.
- **Stage 1 (main check, before any tokens are spent):** every new link is turned into its video number (short `vt.tiktok.com` links are expanded first) and compared with every clip in `clips/` and `clips/duplicates/`, and with the links above it in a `--from-file` list. A duplicate gets **no** clip file. `--check-only` shows the report without creating anything.
- Stage 1 can only see clips on your computer, so run `git pull` first.
- **Stage 5a (safety net):** catches what got past stage 1, e.g. a clip file copied by hand. It keeps the clip whose file name is its `clip_id` (`PP-004.json`, not `PP-004 copy.json`); among several, the first by file name. The others move to `clips/duplicates/` with `"duplicate_of": "<kept clip_id>"`.
- Two clips with the same `clip_id` but different videos are listed as a problem: give one a new PP number (`clip_id` and file name).
- Nothing is deleted. To undo, move the file back.
- Only the link is checked, not the transcript. 5a doesn't open short links (stage 1 already expanded them).

## 8. Matching places (stage 5c)

5a asks "same **video**?" (exact video number, moves copies away); 5c asks "same **place**?" (Maps link, then names; `verified` only). How the two work together: "5a and 5c" in [tvna_pipeline_explained.md](tvna_pipeline_explained.md).

How a `verified` place gets its `place_id` (`stage5c_match_places.py`).

**Names compared:** the clip's `place_name` and every `place_name_alt` are compared with each place's `place_name` and every `aliases` entry in places.json. Names are cleaned first (Unicode NFC, no spaces or punctuation, lowercase). In order:

1. Same Google Maps link → matched.
2. Same name or alias → matched.
3. Name score 95% or more (Latin names only) → matched; the new spelling is saved as an alias.
4. Score 75–94%, one name inside the other (3+ letters), or a close Khmer name → unclear (up to 3 suggestions).

Also unclear: a Maps link or a name shared by two or more places, and the same name with a different Maps link (another branch, or a different place?).
5. Anything else → new place.

| Result | What happens | Report group |
|---|---|---|
| One place matches | Reuse its `place_id`. New names are added to `aliases`. An empty `area` is filled; a different district is reported (`another district "…", places.json keeps "…"`) | matched |
| No place matches | New entry in places.json with a new id (`tvna_p_0006`, ...) | new |
| Unclear (several places, or only close) | `place_id` stays null. The team writes the suggested id in the clip (same place) or `"new"` (a different place), then runs 5c again | unclear |

- Only `verified` places are matched. `rejected` places are skipped. Every other place is listed as `waiting for review` with its status, and nothing changes for it (not even a `place_id` the team wrote).
- A place that already has a `place_id` is not matched again. 5c only adds what is new (another name, a district or Maps link the place didn't have) and reports a different district on every run; otherwise it is counted as skipped.
- Skipped: `rejected` places, places with no name, and places with a `place_id` that add nothing new.
- A `place_id` that is not in places.json is reported as `unknown_id`.
- The team checks the report. For matched and new places, confirm it is the right place by name, aliases and `google_maps_url`.
- One alias belongs to one place only.
- Branches of one shop = one place, with one district in `area` (the first one 5c saw). One district per branch is for Capstone 2.
- Running the script again does not create duplicate places.
- A new place gets the clip's `place_name` as its name in places.json. That is the one name shown on the website. `aliases` are for matching only (see "Name" in section 6).

---

## 9. Category list

- Food & drink: `restaurant`, `cafe`, `bar`, `street_food`
- Sightseeing: `temple`, `museum`, `park`, `viewpoint`, `beach`
- Shopping: `market`, `mall`, `shop`
- Activities & stay: `entertainment`, `hotel`, `other`

---

## 10. How to run

Setup and every command, in order, are in the [README](../README.md) under **Setup** and **How to run**. The README is kept up to date after every stage is built.

Empty templates (in `templates/`): `tvna_clip_template.json`, `tvna_clip_place_template.json`, `tvna_places_template.json`, `tvna_areas_template.json`, `tvna_final_dataset_template.json`.

---

## 11. Open items (not decided or not built yet)

- **Sponsored:** removed for now. One value per clip would count for every place in a multi-place clip. If it comes back, it should be per place.
- **Final dataset extras:** `url` and `posted_at` in `mentions`, and `sub_category`, are not included.
- **Score after review:** `completeness` is not recalculated after the team fills fields.
- **Outside Phnom Penh:** places in other provinces (e.g. Siem Reap in an early test clip) are not rejected automatically. The team decides.
- **Branches:** a place has one `google_maps_url`, even with several branches (5c keeps the first link; other branches' links stay only in their clips). Every file keeps one district per place (`area` is text). **Capstone 2:** one place, many branches, each with its own district and Maps link, all shown on the website. Needs the website team's OK (changes places.json and final_dataset.json).
- **Known names as hints for Gemini (Capstone 2):** save the team's fixes, give known place names to Gemini in stage 4, and score its accuracy. Until then the team links different names in 5b (section 6).
- **STT script** (outside this repo, in the capstone folder): `audio-text/test/test_gemini.py` still writes the old format (`source.timestamp`, file `<name>_gemini.json`), not the clip template.
- **Older docs:** the Google Doc "TVNA Data Pipeline" may not match this guide. The diagram sources in `docs/` (`tvna_data_model.mmd`, `tvna_pipeline_overview.html`) were updated on 2026-11-18; the two `.png` pictures are older and still need re-exporting.
