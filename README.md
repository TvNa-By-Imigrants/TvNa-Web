# TvNa

<p align="center">
  <strong>TvNa</strong> is a platform designed to help you discover new hangout spots and food places in your area. Whether you’re looking for a cozy café, a trendy restaurant, or a fun place to chill with friends, <strong>TvNa</strong> makes it easy to find the perfect spot.<br/>
  But <strong>TvNa</strong> is more than just a discovery tool — it’s also a community. Users can share their experiences, post about hidden gems, and recommend places that others may have never known about. Explore, share, and connect with fellow foodies and adventurers on <strong>TvNa</strong>!
</p>

---

## Data pipeline

Turns **TikTok videos about places in Phnom Penh** into `data/final_dataset.json`: one record per place, for the TvNa website.

**Scope:** TikTok videos only. Places in Phnom Penh only.

**Contents:** [The pipeline in one picture](#the-pipeline-in-one-picture) · [How a clip file grows](#how-a-clip-file-grows) · [The 5 JSON files](#the-5-json-files-templates) · [How `place_id` works](#how-place_id-works) · [Where we are now](#where-we-are-now) · [Setup](#setup-once-per-computer) · [How to run](#how-to-run) · [Test stages 1–6 yourself](#test-stages-16-yourself) · [Stages 1–6](#stage-1-add-videos) · [Team review (5b)](#stage-5b-team-review) · [Team rules](#team-rules)

---

## The pipeline in one picture

```
 TikTok links ─► 1 Collect ─► 2 Audio ─► 3 Transcript ─► 4 Places ─► 5b Team review ─► 5c Match ─► 6 Final dataset
 (links.txt)    (duplicates   (TikTok)   (Gemini)        (Gemini)    (people)          (places.json) (website file)
                 removed here)
```

Each video is **one clip file**, `data/clips/PP-001.json`. Every stage reads it, fills its own part, prints what it did and the next command, then stops so you can check.

| Stage | Who | Reads | Writes |
|---|---|---|---|
| **1. Collect** | script | TikTok link(s) | a **new clip file** `data/clips/PP-NNN.json` with `clip_id` and `source` (link, video id, creator, date). A video we already have gets **no** file |
| **2. Audio** | script (TikTok) | `source.url` | `data/audio/PP-NNN.wav`; in the clip: `audio_file`, `source.caption`, `source.posted_at` |
| **3. Transcript** | Gemini | the WAV | in the clip: `stt` (the transcript, Khmer + English) |
| **4. Places** | Gemini + code | `stt.transcript` + `source.caption` | in the clip: `fields` (one object per place) and `extraction`; a copy in `data/gemini_answers/PP-NNN.json` |
| **5a. Duplicates** | script | all clip files | moves a second copy of a video to `data/clips/duplicates/` (safety net; stage 1 already stops most) |
| **5b. Team review** | **people** | places that are not `verified` yet | fills what is missing, then sets `verification_status` to `verified` or `rejected` |
| **5c. Match** | script | `verified` places | `fields[].place_id` in the clip; `data/places.json` (one entry per real place) |
| **6. Final dataset** | script | clips + `places.json` + `areas.json` | `data/final_dataset.json` (only `verified` places) |

Stages 2, 3 and 4 cost time and Gemini tokens, so duplicates are stopped **before** them, in stage 1.

---

## How a clip file grows

One real clip, PP-002. Each stage adds these parts (everything else stays `null`):

| After stage | New in the clip file |
|---|---|
| 1 | `clip_id: "PP-002"`, `source.url`, `source.video_id`, `source.platform`, `source.creator`, `source.collected_at` |
| 2 | `audio_file`, `source.caption` ("…dope Tteobokki… 🛵Hanjan Coffee"), `source.posted_at` |
| 3 | `stt.transcript` (30 lines), `stt.model` |
| 4 | `extraction` (model, `prompt_version: "v5"`) and `fields`: one place, below |
| 5b | the team fills `area`, `google_maps_url`, `cleaned_by`, sets `verification_status: "verified"` |
| 5c | `fields[0].place_id: "tvna_p_0001"` |

The place in `fields` right after stage 4 (real values, some fields left out). **This is what the team reviews:**

```json
{
  "place_name": "Hanjan Coffee",
  "place_name_alt": ["Hanjang Coffee & Eatery"],
  "area": null,
  "area_description": "Toul Tompoung area",
  "google_maps_url": null,
  "completeness": 0.67,
  "missing_fields": ["area"],
  "verification_status": "needs_review",
  "flags": ["name_from_caption"],
  "cleaned_by": null,
  "cleaner_note": null
}
```

Read it like this: `missing_fields` says the **district** is missing; `flags` says the name **comes from the caption** (check it); `google_maps_url` is always empty after stage 4 (the team finds it). [Stage 5b](#stage-5b-team-review) explains every one.

---

## The 5 JSON files (templates)

Each file type has an empty template in `templates/`. You never copy them by hand; the scripts do.

| Template | Becomes | Made by | Then used by |
|---|---|---|---|
| `tvna_clip_template.json` | one clip file per video, `data/clips/PP-NNN.json` | stage 1 copies it | stages 2, 3, 4 fill it; 5b people fix it; 5c adds `place_id`; 6 reads it |
| `tvna_clip_place_template.json` | one object in a clip's `fields` list (one per place in the video) | stage 4 | 5b, 5c, 6 |
| `tvna_places_template.json` | `data/places.json`: one entry per **real** place | stage 5c | stage 6 (the website name) |
| `tvna_areas_template.json` | `data/areas.json`: the 14 districts (fixed, nobody runs it) | the team, once | stages 4, 5c, 6 check districts against it |
| `tvna_final_dataset_template.json` | `data/final_dataset.json`: one record per place, for the website | stage 6 | the website |

```
clip file (one per video) ──5c──► places.json (one per real place) ──6──► final_dataset.json (website)
   fields[] = places in it            all names of the place                one record per place
                                          ▲
                              areas.json (districts) is checked by 4, 5c, 6
```

---

## How `place_id` works

A **clip** is one video. A **place** is one real shop. Many videos can show the same shop, sometimes spelled differently. `place_id` says "these are the same shop", so the website shows it **once**, with every video under it.

```
PP-001.json  "Hanjan Coffee"            (@motokhiev.bydm) ─┐
                                                            ├─► tvna_p_0001 ─► one record in final_dataset.json
PP-005.json  "Hanjang Coffee & Eatery"  (@another.creator) ─┘                  popularity = 2 creators
PP-003.json  "Luv selfie booth"                            ───► tvna_p_0002
```

(Practice run, see [Test stages 1–6 yourself](#test-stages-16-yourself). PP-005 was made up to show two clips joining.)

**Where it lives:** the same `place_id` is written in 3 files:
- the clip: `fields[].place_id` (which shop is this place?)
- `data/places.json`: the shop itself: website name, all other names (`aliases`), districts, Maps link
- `data/final_dataset.json`: one record per `place_id`

**Who sets it:** only stage 5c, and only for `verified` places. Gemini never does. You type one only when 5c asks (below).

**How 5c decides** (each `verified` place, in order):

| Check | Result |
|---|---|
| Same Google Maps link as a place in places.json | same place |
| Same name as a place's name or alias (capitals, spaces, punctuation don't matter) | same place |
| Name 95% alike (not for Khmer names) | same place; the new spelling is added to `aliases` |
| 75–94% alike, one name inside the other, or a close Khmer name | **unclear**: `place_id` stays `null`, 5c suggests one |
| Anything else | **new** place, `tvna_p_0003`…, named after this clip's `place_name` |

Every name that gets a `place_id` is added to that place's `aliases`, so next time it matches exactly. That's why "Hanjang Coffee & Eatery" (the misheard name, kept in `place_name_alt`) matched PP-005 above.

**What you do:**
- **Unclear:** write the suggested id in the clip's `place_id` if it's the same shop, or `"new"` if it's a different one. Run 5c again.
- **Wrong match** (two different shops got one id): in the clip, write `"new"` (or the right id) in `place_id`, **and** in `data/places.json` remove the wrong name from the old place's `aliases`. If you skip the second part, the next video with that name comes out "unclear" (checked: `candidates tvna_p_0001, tvna_p_0003`).
- **Change the website name:** edit `place_name` in `data/places.json`. Keep the old name in `aliases`.
- **Branches** of one shop are one place, with each branch's district in `area`.

---

## Where we are now

_Last updated: 2026-11-18_

| Stage | Script | Status |
|---|---|---|
| 1. Collect (one link or a list, duplicates removed) | `stage1_new_clip.py` | ✅ |
| 2. Audio + caption | `stage2_get_audio.py` | ✅ |
| 3. Transcript | `stage3_transcribe.py` | ✅ |
| 4. Places (transcript + caption, prompt v5) | `stage4_extract_places.py` | ✅ (Phnom Penh check planned) |
| 5a. Duplicates safety net | `stage5a_dedupe_clips.py` | ✅ |
| 5b. Team review | by hand (this README) | ✅ by hand · ⏳ helper script planned |
| 5c. Match places | `stage5c_match_places.py` | ✅ |
| 6. Final dataset | `stage6_build_final_dataset.py` | ✅ |

**Coming next, in order:**
1. Stages 2–4 refuse a clip file that is a copy of another clip (no TikTok or Gemini call)
2. Review helper for 5b: lists every place to review and what is missing (the "validator")
3. The improvement loop: save the team's fixes (3), give them to Gemini as hints (4), a test score (5). Done: keep Gemini's first answer (1), use the TikTok caption (2)
4. The Phnom Penh check in stage 4

**Next milestone (noted, not built):** view/like/comment/share counts; every plan follows one real clip through all stages; GitHub runs the tests on every push (CI changes only with the team's OK).

---

## Setup (once per computer)

You need **Python 3.12**, **ffmpeg** and **git**. On a Mac:

```sh
brew install python@3.12 ffmpeg
git clone https://github.com/VorngViseth/TvNa-Web.git
cd TvNa-Web
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
cp .env.example .env
```

Open `.env` and add your Gemini API key after `GEMINI_API_KEY=` (from aistudio.google.com). **Never commit `.env`.**

**Every time you open a terminal:**

```sh
cd TvNa-Web
source .venv/bin/activate
```

This makes `python` mean the project's Python 3.12 with our exact packages (`requirements.lock.txt`), so everyone runs the same thing. Check: `which python` ends in `.venv/bin/python`.

| You see | Fix |
|---|---|
| `command not found: python` or `No module named 'yt_dlp'` | Run `source .venv/bin/activate`, then your command again |

VS Code: Cmd+Shift+P → **Python: Select Interpreter** → `./.venv`. Windows: `py -3.12 -m venv .venv`, then `.venv\Scripts\activate`.

---

## How to run

```sh
source .venv/bin/activate
git pull                                                   # get the team's clips first (needed for the duplicate check)

python stage1_new_clip.py --from-file links.txt --check-only   # 1. see what is new / duplicate / bad (creates nothing)
python stage1_new_clip.py --from-file links.txt                # 1. create clip files for the new videos only
python stage2_get_audio.py data/clips/PP-005.json data/clips/PP-006.json        # 2. stage 1 prints this line
python stage3_transcribe.py data/clips/PP-005.json data/clips/PP-006.json       # 3.
python stage4_extract_places.py data/clips/PP-005.json data/clips/PP-006.json   # 4.

python stage5a_dedupe_clips.py data/clips/*.json           # 5a. safety net
# 5b. team review, by hand (see Stage 5b)
python stage5c_match_places.py data/clips/*.json           # 5c.
python stage6_build_final_dataset.py data/clips/*.json     # 6.
```

- Every command prints the next one. Copy it.
- Stages 2–4 take one or many clips. One failing doesn't stop the others.
- `--force` redoes a clip. Stages 3 and 4 never redo a clip the team already reviewed, even with `--force`.
- Every stage is safe to **run twice**: the second run changes nothing and makes no TikTok or Gemini call (one exception: a short `vt.tiktok.com` link asks TikTok once which video it is).

---

## Test stages 1–6 yourself

Use a **practice folder outside the repo**, so `data/` and git are never touched. Every stage has an option for where its files go.

```sh
source .venv/bin/activate
T=~/tvna-try                                     # the practice folder (set it again in every new terminal)

python stage1_new_clip.py "<a Phnom Penh TikTok link>" --clips-dir $T/clips
python stage2_get_audio.py $T/clips/PP-001.json --audio-dir $T/audio
python stage3_transcribe.py $T/clips/PP-001.json --audio-dir $T/audio
python stage4_extract_places.py $T/clips/PP-001.json --answers-dir $T/answers
python stage5a_dedupe_clips.py $T/clips/*.json
# 5b: open $T/clips/PP-001.json and review the place (see Stage 5b); set "verification_status": "verified"
python stage5c_match_places.py $T/clips/*.json --places $T/places.json
python stage6_build_final_dataset.py $T/clips/*.json --places $T/places.json --output $T/final_dataset.json
```

- Stages 2–4 really call TikTok and Gemini (a few free-tier calls per video). Stages 1, 5a, 5b, 5c and 6 cost nothing.
- The "Next:" line some stages print says `data/clips/*.json`. In practice, use `$T/clips/*.json` instead.
- In the practice folder, stage 1 only sees practice clips, so a video you already have in `data/` is **not** a duplicate there.

**After each stage, open the file and look:**

| After | Open | You should see |
|---|---|---|
| 1 | `$T/clips/PP-001.json` | `source.url`, `video_id`, `creator` filled; everything else `null` |
| 2 | the same file, and `$T/audio/PP-001.wav` | `audio_file`, `source.caption`; the WAV plays the video's sound |
| 3 | the same file | `stt.transcript` matches what is said |
| 4 | the same file | `fields`: one object per place, with `verification_status`, `missing_fields`, `flags` |
| 5b | (you edit it) | `cleaned_by` = your name, `"verified"` |
| 5c | `$T/places.json`, and the clip | a new `tvna_p_0001`; the clip's `place_id` is now `tvna_p_0001` |
| 6 | `$T/final_dataset.json` | one record with your place, `popularity: 1` |

**Then try these:**

| Try | You should see |
|---|---|
| Stage 1 again with the same link | `Duplicate: same video as PP-001` |
| Any stage again | `Skipped`, nothing changes |
| Copy `PP-001.json` to `PP-001 copy.json`, run 5a | the copy moves to `$T/clips/duplicates/` |
| 5c and 6 **before** you set `verified` | 5c: `waiting for review`; 6: `0 places` |
| A second video of the same place, through all stages | 5c gives it the same `tvna_p_0001`; 6: `popularity: 2` |

When you're done, delete the practice folder (`rm -rf ~/tvna-try`). Nothing in it is shared.

---

## Folder layout

```
TvNa-Web/
├── README.md                     ← you are here
├── stage1_new_clip.py … stage6_build_final_dataset.py   ← one script per stage
├── tvna_common.py                ← shared helpers
├── requirements.txt / requirements.lock.txt              ← packages (install from the lock file)
├── .env.example                  ← copy to .env, add your key
├── data/
│   ├── clips/                    ← one file per video: PP-001.json …
│   │   └── duplicates/           ← second copies of a video (still count as "already collected")
│   ├── audio/                    ← WAVs from stage 2 (not in git)
│   ├── gemini_answers/           ← Gemini's first answer from stage 4 (never edit)
│   ├── areas.json                ← the 14 Phnom Penh districts (fixed)
│   ├── places.json               ← made by 5c
│   └── final_dataset.json        ← made by 6
├── templates/                    ← empty JSON templates
├── docs/                         ← field guide, decisions, diagrams
└── tests/                        ← offline checks: python tests/run_all.py
```

There is no database: these JSON files in git **are** the data. `git pull` gives you everyone's clips.

---

## Stage 1: add videos

**In:** TikTok links. **Out:** one new clip file per **new** video.

Put the links in a text file, one per line (blank lines and `# notes` are ignored):

```
# links for this week
https://www.tiktok.com/@motokhiev.bydm/video/7706878472664222982?is_from_webapp=1
https://vt.tiktok.com/ZSpfUj3du/
```

```sh
python stage1_new_clip.py --from-file links.txt --check-only
```

**How duplicates are found:** every TikTok link has the video's number (`/video/7706878472664222982`). Stage 1 takes that number from each link (short links are expanded first) and compares it with every clip in `data/clips/` and `data/clips/duplicates/`, and with the links above it in the file. A match creates nothing, so no tokens are spent on it.

You'll see (real run, `--check-only`):

```
links.txt: 4 links
new videos, to create (1):
  line 3: https://www.tiktok.com/@example/video/7000000000000000123
duplicates, not created (2):
  line 2: https://www.tiktok.com/@motokhiev.bydm/video/7706878472664222982?is_from_webapp=1 -> same video as PP-002
  line 4: https://www.tiktok.com/@example/video/7000000000000000123 -> same video as line 3
bad links, not created (1):
  line 5: https://www.youtube.com/watch?v=abc -> only TikTok links are in scope
Run again without --check-only to create them.
Fix the bad links in the file.
```

Without `--check-only`, the new ones are created (`line 3 -> PP-005: …`) and it prints the stage 2 command. One bad link doesn't stop the others. Run the same file again: everything is a duplicate, nothing is created.

One link also works: `python stage1_new_clip.py "<link>"` (add `--posted-at 2026-10-22` if you know the date; otherwise stage 2 fills it).

| Try this | You should see |
|---|---|
| A new TikTok link | `Created data/clips/PP-00N.json` |
| A video we have (full, short or `?…` link) | `Duplicate: same video as PP-00N` / `-> same video as PP-00N` |
| A YouTube link | `only TikTok links are in scope` |

---

## Stage 2: get the audio

**In:** `source.url`. **Out:** `data/audio/PP-002.wav` (16 kHz mono), `source.caption`, `source.posted_at`.

```
PP-002: saved data/audio/PP-002.wav (16 kHz, mono, 73.3 s)
  caption: This yet-to-discover restaurant, has such a dope Tteobokki.  …
  posted_at: 2026-11-11 (from TikTok)
Next: python stage3_transcribe.py data/clips/PP-002.json
```

- WAVs are not in git. For a teammate's clip, run stage 2 on it.
- No caption on the video → `source.caption` is `null`.
- A clip with a WAV but no caption gets the caption only (no download).

| Try this | You should see |
|---|---|
| The same command again | `already has audio … Skipped.` |
| A deleted or private video | `Download failed: …` then `Nothing changed` |

---

## Stage 3: get the transcript

**In:** the WAV. **Out:** `stt.transcript`: Khmer in Khmer script, English in English, no translation. Audio only (the caption is not used here, so the name as spoken is kept).

```
PP-002: saved transcript (37 lines, gemini-3.6-flash)
  ហាងម្ហូបកូរ៉េឆ្ងាញ់
  មួយកន្លែងទៀតនៅ Toul Tompoung
Next: python stage4_extract_places.py data/clips/PP-002.json
```

- Uses `gemini-3.8-flash`; if Google is busy it retries, then switches to `gemini-3.6-flash`. This can take minutes.
- `Gemini is busy … Try this clip again later` → run the `To try only the failed clips again` command it prints.
- Music only → `[no speech]`.
- `--force` also clears the clip's places (run stage 4 again).

---

## Stage 4: find the places

**In:** the transcript **and** the TikTok caption. **Out:** `fields`, one object per place, plus a copy of Gemini's answer in `data/gemini_answers/` (**never edit it**: it shows later what Gemini got wrong).

```
PP-002: 1 place found (gemini-3.6-flash)
  - Hanjan Coffee (restaurant): needs_review, name from caption; also called Hanjang Coffee & Eatery
Next: python stage5a_dedupe_clips.py data/clips/*.json
```

**Names:** the creator types the caption, so its spelling is usually right; speech-to-text can mishear.
- **When the TikTok caption writes the place's name, the caption's spelling wins.** That spelling goes in `place_name` (the English name if there is one).
- Example: the speaker says "Hanjang Coffee & Eatery", the caption writes "Hanjan Coffee" → `place_name` = "Hanjan Coffee".
- `place_name_alt` = every other name said or written (e.g. the misheard "Hanjang Coffee & Eatery"). Nothing is lost; the team picks in 5b.
- A place named only in the caption gets the flag `name_from_caption`. Sponsors, @accounts and #hashtags are not places (`name_is_tag`, `rejected`).
- `[no speech]` clip with a caption → read from the caption. No caption either → skipped.

**Code then scores each place** (`completeness` = how many of `place_name`, `area`, `speaker_opinion` are filled, out of 3) and sets the status:

| Result | `verification_status` |
|---|---|
| No name, or only a tag | `rejected` (kept, not deleted) |
| 1 or 2 of the 3 filled | `needs_review` |
| All 3 filled | `auto_added` (still needs a person to check) |

---

## Stage 5a: duplicates safety net

```sh
python stage5a_dedupe_clips.py data/clips/*.json
```

Stage 1 already stops duplicates. 5a catches what slips through, e.g. a clip file copied by hand. It keeps the file whose name is its `clip_id` (`PP-004.json`) and moves the other to `duplicates/` with `"duplicate_of": "PP-004"`. Nothing is deleted. Run it before stage 2 too, if you're unsure.

---

## Stage 5b: team review

**Only `verified` places reach the website.** Every place Gemini found waits here until a person checks it.

### 1. Find what to review

```sh
grep -l -e '"needs_review"' -e '"auto_added"' data/clips/*.json
```

This lists the clip files that have places nobody checked yet. (Stage 5c also lists them under `waiting for review`.)

### 2. In each place, these fields tell you what to do

| Field | What it tells you |
|---|---|
| `verification_status` | `needs_review`: something is missing. `auto_added`: looks complete, still check it. `rejected`: no name or only a tag; skip unless it's really a place |
| `missing_fields` | which of `place_name`, `area`, `speaker_opinion` is empty. **Fill these** |
| `flags` | what to double-check (table below) |
| `google_maps_url` | always empty after stage 4. **You find it** |

| Flag | Check |
|---|---|
| `name_from_caption` | the name is written in the caption but not said. Is it the place shown, not a sponsor? |
| `asr_spelling_or_uncertain_name` | the spelling may be misheard. Check on Google Maps |
| `area_not_in_areas_list` | Gemini gave a place that isn't a district (moved to `area_description`). Pick the district |
| `low_confidence_field` | `category`, `price_range` or `area` may be wrong |
| `evidence_not_found_in_transcript` | Gemini's quote isn't in the transcript or caption. It may be made up |
| `no_valid_segment_ids` | Gemini pointed to sentences that don't exist. Check the transcript |
| `no_place_name`, `name_is_tag` | already `rejected`. Fix only if it really is a place |

### 3. Fix it (watch the video, read the caption)

1. **Name:** is `place_name` right? If a name in `place_name_alt` is better, swap them. Keep the wrong spelling in `place_name_alt` (it helps match future clips). This becomes the website name.
2. **Google Maps:** search the place, check name and photos, copy the Share link into `google_maps_url`.
3. **District:** from the Maps address, write it in `area` as a list, spelled exactly as in `data/areas.json`, e.g. `["Chamkar Mon"]`. Branches: one district each. A neighborhood like "BKK1" or "Toul Tompoung" is not a district; it stays in `area_description`.
4. **Other missing fields:** fill only what the video or caption says. Unknown stays `null`.
5. **Sign it:** your name in `cleaned_by`, a short note in `cleaner_note` (e.g. "district from Google Maps").
6. **Status:** `"verified"` (correct, goes to the website) or `"rejected"` (not a place, not in Phnom Penh, or wrong).

Can't find the place on Maps? Leave `area` and `google_maps_url` as `null` and explain in `cleaner_note`. Then decide the status as above.

**Done =** every place is `verified` or `rejected`. Then commit, push, and run 5c.

Example, PP-002: `missing_fields: ["area"]` → find "Hanjan Coffee" on Maps → write its district in `area` and the link in `google_maps_url` → `name_from_caption`: check the video really shows Hanjan Coffee → `cleaned_by`, `"verified"`.

---

## Stage 5c: match places

**In:** `verified` places. **Out:** a `place_id` for each, and `data/places.json` (one entry per real place, with all its names in `aliases`).

So two clips about the same café count as **one place**. How it decides, and what to do with **unclear** or a **wrong match**: [How `place_id` works](#how-place_id-works).

```
new (1):
  PP-003.json  "Luv selfie booth" -> tvna_p_0001
waiting for review (1):
  PP-002.json  "Hanjan Coffee" (verification_status "needs_review")
```

- **Waiting for review:** not checked in 5b yet. Nothing changes for it.
- When a clip calls a known place something else, 5c says `website name stays "…"` (the name in places.json).

---

## Stage 6: final dataset

**In:** clips + `places.json` + `areas.json`. **Out:** `data/final_dataset.json`, one record per place:

- **one name** (`place_name` from places.json); other names never reach the website
- `category`, `price_range`, `area`, `opening_hours`, `menu_items`: every different value from all clips
- `mentions`: one per clip (`clip_id`, `creator`, `speaker_opinion`)
- `popularity`: number of different creators who posted about it

Only `verified` places with a `place_id` are published. It warns about the rest, and when clips disagree (e.g. two price ranges). It rebuilds the file from scratch each time.

> **Website team:** `final_dataset.json` has **no `place_name_alt`** (since 2026-11-17). Use `place_name`. Fields: `templates/tvna_final_dataset_template.json`.

---

## Team rules

**Collecting**
- `git pull` before stage 1, and push your new clips soon. Each computer picks the next free `PP-` number, so two people at the same time can get the same number.
- Collect with `--from-file … --check-only` first. Only new videos go on to stages 2–4.

**Data**
- Missing = `null`. Never `""`, "N/A" or "Unknown".
- Districts exactly as in `data/areas.json` ("Boeung Keng Kang" ≠ "Boeng Keng Kang").
- Only a person sets `verified`. Only `verified` places get a `place_id` and reach the website.
- The caption's spelling of a name wins over the spoken one. One name per place on the website; other names are kept for matching only.
- Never edit `data/gemini_answers/`. Clips are never deleted, only moved to `duplicates/` (5a).

**Git and safety**
- Never commit `.env`, videos or WAVs (`.gitignore` blocks them). Never put your API key in code.
- Before every push: `python tests/run_all.py` must say `Total: N/N passed`. The tests use fake TikTok and Gemini, cost nothing and never touch `data/`.
- Every "skip if already done" check is tested with a filled value, `null`, `""` and a missing key, and a second run must change nothing and call nothing.

---

## More detail

- [`docs/tvna_pipeline_explained.md`](docs/tvna_pipeline_explained.md): the whole pipeline on 4 pages (for the supervisor): each stage, its gate, key takeaways, limits.
- [`docs/tvna_field_guide.md`](docs/tvna_field_guide.md): every field, who fills it, value rules, category list.
- [`docs/decisions.md`](docs/decisions.md): key decisions and why.
- [`docs/tvna_data_model.mmd`](docs/tvna_data_model.mmd): how the JSON files connect (the `.png` picture is older: it still shows `place_name_alt` in the final dataset).
