# TvNa

<p align="center">
  <strong>TvNa</strong> is a platform designed to help you discover new hangout spots and food places in your area. Whether you’re looking for a cozy café, a trendy restaurant, or a fun place to chill with friends, <strong>TvNa</strong> makes it easy to find the perfect spot.<br/>
  But <strong>TvNa</strong> is more than just a discovery tool — it’s also a community. Users can share their experiences, post about hidden gems, and recommend places that others may have never known about. Explore, share, and connect with fellow foodies and adventurers on <strong>TvNa</strong>!
</p>

---

## Data pipeline

Turns **TikTok videos about places in Phnom Penh** into `data/results/final_dataset.json`: one record per place, for the TvNa website.

**Scope:** TikTok videos only. Places in Phnom Penh only.

**Contents:** [Words you'll see](#words-youll-see) · [The pipeline in one picture](#the-pipeline-in-one-picture) · [How a clip file grows](#how-a-clip-file-grows) · [The status of a place](#the-status-of-a-place) · [The 5 JSON files](#the-5-json-files-templates) · [How `place_id` works](#how-place_id-works) · [Where we are now](#where-we-are-now) · [Setup](#setup-once-per-computer) · [How to run](#how-to-run) · [Test stages 1–6 yourself](#test-stages-16-yourself) · [Stages 1–6](#stage-1-add-videos) · [Team review (5b)](#stage-5b-team-review) · [Photos (5d)](#stage-5d-photos-for-new-places) · [The team's flow](#the-teams-flow) · [Team rules](#team-rules)

---

## Words you'll see

| Word | Meaning |
|---|---|
| **clip** | one TikTok video |
| **clip file** | the JSON file for one clip, e.g. `data/clips/PP-002.json`. Every stage adds to it |
| **place** | a shop, café or other spot in a video. One video can show several places |
| **place record** | one place inside a clip file (the `fields` list has one record per place) |
| **place file** | one file per **real** place, `data/places/tvna_p_0001.json`: its website name, other names, district, Maps link and photos |
| **photo** | a picture of a place (1–5 per place), on Cloudinary; the place file keeps its link, source, credit and fingerprint (`sha256`) |
| **cover** | the TikTok video's own cover picture, shown next to the creator's mention |
| **status** | `verification_status` of a place: `rejected`, `needs_review`, `auto_added` or `verified` ([see below](#the-status-of-a-place)) |
| **`place_id`** | the ID of a real place, e.g. `tvna_p_0001`. Two videos about the same café get the same one |
| **caption** | the text the creator typed under the TikTok video |
| **transcript** | the words spoken in the video, written down by Gemini |
| **district** | one of Phnom Penh's 14 districts, from `data/reference/areas.json` |

---

## The pipeline in one picture

```
 TikTok links ─► 1 Collect ─► 2 Audio ─► 3 Transcript ─► 4 Places ─► 5b Team review ─► 5c Match ─► 5d Photos ─► 6 Final dataset
 (links.txt)    (duplicates   (TikTok)   (Gemini)        (Gemini)    (people)          (data/places/) (people,    (website file)
                 removed here)                                                                        new places)
```

Each video is **one clip file**, `data/clips/PP-001.json`. Every stage reads it, fills its own part, prints what it did and the next command, then stops so you can check.

| Stage | Who | Reads | Writes |
|---|---|---|---|
| **1. Collect** | script | TikTok link(s) | a **new clip file** `data/clips/PP-NNN.json` with `clip_id` and `source` (link, video id, creator, date). A video we already have gets **no** file |
| **2. Audio** | script (TikTok, Cloudinary) | `source.url` | `data/audio/PP-NNN.wav`; in the clip: `audio_file`, `source.caption`, `source.cover_url`, `source.posted_at` |
| **3. Transcript** | Gemini | the WAV | in the clip: `stt` (the transcript, Khmer + English) |
| **4. Places** | Gemini + code | `stt.transcript` + `source.caption` | in the clip: `fields` (one object per place) and `extraction`; a copy in `data/gemini_answers/PP-NNN.json` |
| **5a. Duplicates** | script | all clip files | moves a second copy of a video to `data/clips/duplicates/` (safety net; stage 1 already stops most) |
| **5b. Team review** | **people** | places that are not `verified` yet | fills what is missing, then sets `verification_status` to `verified` or `rejected` |
| **5c. Match** | script | `verified` places | `fields[].place_id` in the clip; one file per real place, `data/places/<place_id>.json` |
| **5d. Photos** | **people** + script (Cloudinary) | new places (0 photos) | 1–5 photos in the place file: `photos: [{url, source, credit, sha256}]` |
| **6. Final dataset** | script | clips + `data/places/` + `areas.json` | `data/results/final_dataset.json` (only `verified` places with at least 1 photo; with photos, video links and covers) |

Stages 2, 3 and 4 cost time and Gemini tokens, so duplicates are stopped **before** them, in stage 1.

---

## How a clip file grows

One real clip, PP-002. Each stage adds these parts (everything else stays `null`):

| After stage | New in the clip file |
|---|---|
| 1 | `clip_id: "PP-002"`, `source.url`, `source.video_id`, `source.platform`, `source.creator`, `source.collected_at` |
| 2 | `audio_file`, `source.caption` ("…dope Tteobokki… 🛵Hanjan Coffee"), `source.cover_url` (the video's cover picture on Cloudinary), `source.posted_at` |
| 3 | `stt.transcript` (30 lines), `stt.model` |
| 4 | `extraction` (model, `prompt_version: "v5"`) and `fields`: one place, below |
| 5b | the team fills `area`, `google_maps_url`, `cleaned_by`, sets `verification_status: "verified"` |
| 5c | `fields[0].place_id` (after the review; PP-002 is still waiting for it) |

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

## The status of a place

Every place record has a status (`verification_status`). It decides what happens next.

| Status | Set by | Means | On the website? |
|---|---|---|---|
| `rejected` | stage 4 or a person | not a real place: no name, only a #hashtag or @account, or a person decided it's wrong or outside Phnom Penh | **no**, never |
| `needs_review` | stage 4 | found, but something is missing or uncertain | **no**, waits for a person |
| `auto_added` | stage 4 | found, with all 3 key fields (name, district, opinion) | **no**, waits for a person |
| `verified` | **a person** (5b) | checked and approved | **yes**, after 5c gives it a `place_id` and 5d at least 1 photo |

**`auto_added` does not add the place anywhere.** It is only a label meaning "this place looks complete". The place stays in its clip file like every other place, and a person must still check it and set `verified`, exactly like `needs_review`. The reviewer just has less to fill in. (The name comes from an old plan to publish complete places without review. That plan was dropped.)

```
stage 4:     rejected        needs_review        auto_added
                                   └────────┬─────────┘
stage 5b:          a person checks it:   verified   or   rejected
                   (not found on Google Maps: stays needs_review, held back)
stage 5c, 6:       only verified places get a place_id and go on the website (with at least 1 photo, 5d)
```

---

## The 5 JSON files (templates)

Each file type has an empty template in `templates/`. You never copy them by hand; the scripts do.

| Template | Becomes | Made by | Then used by |
|---|---|---|---|
| `tvna_clip_template.json` | one clip file per video, `data/clips/PP-NNN.json` | stage 1 copies it | stages 2, 3, 4 fill it; 5b people fix it; 5c adds `place_id`; 6 reads it |
| `tvna_clip_place_template.json` | one object in a clip's `fields` list (one per place in the video) | stage 4 | 5b, 5c, 6 |
| `tvna_places_template.json` | one file per **real** place, `data/places/<place_id>.json` (names, district, Maps link, `photos`) | stage 5c | stage 6 (the website name) |
| `tvna_areas_template.json` | `data/reference/areas.json`: the 14 districts (fixed, nobody runs it) | the team, once | stages 4, 5c, 6 check districts against it |
| `tvna_final_dataset_template.json` | `data/results/final_dataset.json`: one record per place, for the website | stage 6 | the website |

```
clip file (one per video) ──5c──► place file (one per real place) ──6──► final_dataset.json (website)
   fields[] = places in it            all names of the place                one record per place
                                          ▲
                              areas.json (districts) is checked by 4, 5c, 6
```

---

## How `place_id` works

A **clip** is one video. A **place** is one real shop. Many videos can show the same shop, sometimes spelled differently. `place_id` says "these are the same shop", so the website shows it **once**, with every video under it.

```
PP-005.json  "Beans Barley", also "Beans Bali"        (@motokhiev.bydm) ─┐
                                                                          ├─► tvna_p_0001 ─► one record in final_dataset.json
PP-007.json  "Beans Barley", also "Beans and Barley"  (@pengpos)        ─┘                  popularity = 2 creators
```

(Real data: two creators, one café, the same Maps link. Its place file keeps all three names in `aliases`.)

**Where it lives:** the same `place_id` is written in 3 files:
- the clip: `fields[].place_id` (which shop is this place?)
- its place file, `data/places/<place_id>.json`: the shop itself: website name, all other names (`aliases`), district, Maps link, photos
- `data/results/final_dataset.json`: one record per `place_id`

**Who sets it:** only stage 5c, and only for `verified` places. Gemini never does. You type one only when 5c asks (below).

**Before matching:** only `verified` places are matched. `rejected` places are skipped. A place that already has a `place_id` only adds what is new (another name, a district or Maps link the place didn't have) and a note when its district differs; every other status is listed as "waiting for review" and nothing changes. A `place_id` written by the team that has no place file is reported as `unknown_id`.

**Names compared:** the clip's `place_name` and every `place_name_alt` are compared with each place's `place_name` and every `aliases` entry in the place files. Before comparing, names are cleaned: capitals, spaces, punctuation and accents don't matter, `&` = `and`, `ឲ` = `ឱ`.

**How 5c decides** (each `verified` place, in order; the first check that fits wins):

| # | Check | Result |
|---|---|---|
| 1 | Same Google Maps link as **one** place | same place |
| 1b | Same Maps link as **two or more** places | **unclear** |
| 2 | Same name as **one** place (name or alias) | same place |
| 2b | Same name as **two or more** places | **unclear** ("candidates …") |
| 2c | Same name, but a **different** Maps link | **unclear**: "another branch, or a different place?" |
| 3 | Name 95% or more alike with exactly one place (not for Khmer names) | same place; the new spelling is added to `aliases` |
| 4 | 75–94% alike, one name inside the other (3+ letters), or a close Khmer name | **unclear**: `place_id` stays `null`; 5c suggests up to 3 places |
| 5 | Anything else | **new** place, named after this clip's `place_name`, with the next number (`tvna_p_0002`, `tvna_p_0003`…) |

**New ids are numbers:** the next free one after the highest (`tvna_p_0001` → `tvna_p_0002`). Two computers running 5c at once would both pick the same number, so **one person runs 5c at a time** until the database gives out the ids.

**One file per place** (`data/places/`), so people matching different places never edit the same file. The first 5c run after 2026-11-28 moves the old `data/results/places.json` into these files and deletes it (git keeps its history).

**Team rule, so 5c runs never clash:**
1. **One person at a time** runs 5c. Say in the team chat before you start.
2. `git pull` right before 5c, and commit + `git push` right after.
3. If git still shows a conflict in a place file, keep both sides: every name in `aliases`.

Every name that gets a `place_id` is added to that place's `aliases`, so next time it matches exactly. That's why "Beans Bali" (PP-005's other name) and "Beans and Barley" (PP-007's) are both in `aliases` now: a future video with either spelling matches at once.

**What you do:**
- **Unclear:** write the suggested id in the clip's `place_id` if it's the same shop, or `"new"` if it's a different one. Run 5c again.
- **Wrong match** (two different shops got one id): in the clip, write `"new"` (or the right id) in `place_id`, **and** in the old place's file (`data/places/<place_id>.json`) remove the wrong name from `aliases`. If you skip the second part, the next video with that name comes out "unclear" (checked: `candidates tvna_p_0001, tvna_p_…`).
- **Change the website name:** edit `place_name` in the place's file. Keep the old name in `aliases`.
- **Fix a district or Maps link after 5c:** edit the place's file. 5c fills a district only when the file has none; a different one is only reported (`another district "…", the place file keeps "…"`).
- **Branches** of one shop are one place, with **one** district in `area` (the first one; another branch's district is only reported). Same name but a different Maps link → 5c says **unclear** ("another branch or a different place?"): write the existing id for a branch, `"new"` for a different shop. **Limit:** the place keeps only its **first** Maps link, and the website file shows only **one** district (the first); other branches' links stay only in their clips (Capstone 2: one district and link per branch).

---

## Where we are now

_Last updated: 2026-11-28_

| Stage | Script | Status |
|---|---|---|
| 1. Collect (one link or a list, duplicates removed) | `stage1_new_clip.py` | ✅ |
| 2. Audio + caption + cover picture | `stage2_get_audio.py` | ✅ (cover: new, waiting for the Cloudinary keys) |
| 3. Transcript | `stage3_transcribe.py` | ✅ |
| 4. Places (transcript + caption, prompt v5) | `stage4_extract_places.py` | ✅ (Phnom Penh check planned) |
| 5a. Duplicates safety net | `stage5a_dedupe_clips.py` | ✅ |
| 5b. Team review | by hand, checked by `stage5b_validate_clips.py` | ✅ |
| 5c. Match places (one file per place; one person at a time) | `stage5c_match_places.py` | ✅ |
| 5d. Photos for new places (1–5, on Cloudinary) | `stage5d_add_photo.py`, checked by `stage5d_check_photos.py` | ✅ (waiting for the Cloudinary keys) |
| 6. Final dataset (with photos, video links and covers) | `stage6_build_final_dataset.py` | ✅ |

**Coming next, in order:**
1. The review page for the team (clean, match and add photos in the browser)
2. Load the places into the website's database (TvNa-Prototype), once the field differences are agreed with the website team

Later: stages 2–4 refuse a clip file that is a copy of another clip; the Phnom Penh check in stage 4.

**Capstone 2 (the next milestone; noted, not built):**
- **The improvement loop:** save the team's fixes, give the known place names to Gemini as hints (so it spells a place the same way for every creator), and a test score. Done already: keep Gemini's first answer, use the TikTok caption. Until then, the team links the different names in 5b (see "Same place, other names").
- **Branches: one place, many branches, linked as one.** Each branch keeps its own district and Google Maps link, so the website shows every branch's link to click. Today a place keeps only one Maps link and the website file shows one district. (Changes the place files and `final_dataset.json`: agree with the website team first.)
- View/like/comment/share counts.
- Every plan follows one real clip through all stages.
- GitHub runs the tests on every push (CI changes only with the team's OK).

---

## Setup (once per computer)

You need **Python 3.12**, **ffmpeg** (with its `ffprobe`; Homebrew installs both; tested with ffmpeg 9.0.2, iPhone HEIC photos included) and **git**. On a Mac:

```sh
brew install python@3.12 ffmpeg
git clone https://github.com/VorngViseth/TvNa-Web.git
cd TvNa-Web
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
cp .env.example .env
```

Open `.env` and add your keys. **Never commit `.env`.**
- `GEMINI_API_KEY=`: from aistudio.google.com.
- `CLOUDINARY_CLOUD_NAME=`, `CLOUDINARY_API_KEY=`, `CLOUDINARY_API_SECRET=`: from the team's Cloudinary account (ask the team lead). In the Cloudinary Console they are under **Settings → API Keys**. The secret is like a password: only in `.env`, never in a chat, code or a screenshot. Stage 2 uses them to save each video's cover picture, and 5d for the place photos. Without them stage 2 still makes the audio and says the cover was not saved; 5d says the keys are missing and adds nothing.

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
# 5b. team review, by hand (see Stage 5b), then check it:
python stage5b_validate_clips.py data/clips/*.json         # 5b. check the review (changes nothing)
git pull                                                   # 5c. right before matching
python stage5c_match_places.py data/clips/PP-0[4-7]?.json  # 5c. your range only (here PP-040–079), one person at a time
git add data/places data/clips && git commit -m "Match my clips" && git push   # 5c. right after
python stage5d_check_photos.py                             # 5d. which new places need photos (changes nothing)
python stage5d_add_photo.py tvna_p_0002 front.jpg inside.jpg --source "Google Maps" --credit "Dara S."   # 5d.
git add data/places && git commit -m "Photos" && git push  # 5d. right after
python stage6_build_final_dataset.py data/clips/*.json     # 6. all clips
```

- Every command prints the next one. Copy it.
- Stages 2–4 take one or many clips. One failing doesn't stop the others.
- `--force` redoes a clip. Stages 3 and 4 never redo a clip the team already reviewed, even with `--force`.
- Every stage is safe to **run twice**: the second run changes nothing and makes no TikTok or Gemini call (one exception: a short `vt.tiktok.com` link asks TikTok once which video it is). Adding the same photo twice is refused. `--remove` and `--move` in 5d are hand edits by photo number: they print the new list, so check it instead of running them again.

---

## Test stages 1–6 yourself

Use a **practice folder outside the repo**, so `data/` and git are never touched. Every stage has an option for where its files go.

```sh
source .venv/bin/activate
T=~/tvna-try                                     # the practice folder (set it again in every new terminal)

python stage1_new_clip.py "<a Phnom Penh TikTok link>" --clips-dir $T/clips
CLOUDINARY_CLOUD_NAME= python stage2_get_audio.py $T/clips/PP-001.json --audio-dir $T/audio   # no cover upload in practice
python stage3_transcribe.py $T/clips/PP-001.json --audio-dir $T/audio
python stage4_extract_places.py $T/clips/PP-001.json --answers-dir $T/answers
python stage5a_dedupe_clips.py $T/clips/*.json
# 5b: open $T/clips/PP-001.json and review the place (see Stage 5b); set "verification_status": "verified"
python stage5b_validate_clips.py $T/clips/*.json
python stage5c_match_places.py $T/clips/*.json --places-dir $T/places
python stage5d_add_photo.py tvna_p_0001 <a photo of the place> --source "Own photo" --credit "<your name>" --places-dir $T/places
python stage6_build_final_dataset.py $T/clips/*.json --places-dir $T/places --output $T/final_dataset.json
```

- Stages 2–4 really call TikTok and Gemini (a few free-tier calls per video). Stage 5d really uploads to the team's Cloudinary (free plan; the practice photo stays there, under `tvna/places/`). Stages 1, 5a, 5b, 5c and 6 cost nothing.
- `CLOUDINARY_CLOUD_NAME=` in front of stage 2 turns the cover upload off for that one command (it says `cover: not saved`). Without it, the practice clip `PP-001` would upload its cover as `tvna/covers/PP-001` and could replace a real clip's cover.
- The "Next:" line some stages print says `data/clips/*.json`. In practice, use `$T/clips/*.json` instead.
- In the practice folder, stage 1 only sees practice clips, so a video you already have in `data/` is **not** a duplicate there.

**After each stage, open the file and look:**

| After | Open | You should see |
|---|---|---|
| 1 | `$T/clips/PP-001.json` | `source.url`, `video_id`, `creator` filled; everything else `null` |
| 2 | the same file, and `$T/audio/PP-001.wav` | `audio_file`, `source.caption`, `source.cover_url: ""` (not saved in practice); the WAV plays the video's sound |
| 3 | the same file | `stt.transcript` matches what is said |
| 4 | the same file | `fields`: one object per place, with `verification_status`, `missing_fields`, `flags` |
| 5b | (you edit it) | `cleaned_by` = your name, `"verified"` |
| 5c | `$T/places/`, and the clip | a new place file `tvna_p_0001.json`; the clip's `place_id` is `tvna_p_0001` |
| 5d | `$T/places/tvna_p_0001.json` | `photos`: one entry with a `https://res.cloudinary.com/…` link, your source and credit |
| 6 | `$T/final_dataset.json` | one record with your place, its photo, `popularity: 1` |

**Then try these:**

| Try | You should see |
|---|---|
| Stage 1 again with the same link | `Duplicate: same video as PP-001` |
| Any stage again | `Skipped`, nothing changes |
| Copy `PP-001.json` to `PP-001 copy.json`, run 5a | the copy moves to `$T/clips/duplicates/` |
| 5c and 6 **before** you set `verified` | 5c: `waiting for review`; 6: `No place files in … Run stage 5c first` |
| A second video of the same place, through all stages | 5c gives it the same `tvna_p_0001`; 6: `popularity: 2` |
| 6 **before** 5d (no photo yet) | `no photo yet, so not published`; `Nothing to publish`: no file is made (an old one is kept) |
| 5d with the same photo again | `This photo is already on this place (photo 1)` |

When you're done, delete the practice folder (`rm -rf ~/tvna-try`). Nothing in it is shared.

---

## Folder layout

```
TvNa-Web/
├── README.md                     ← you are here
├── stage1_new_clip.py … stage6_build_final_dataset.py   ← one script per stage (5d: stage5d_add_photo.py, stage5d_check_photos.py)
├── tvna_common.py                ← shared helpers
├── tvna_review.py                ← photo rules (add, remove, move, check), for 5d now and the review page later
├── review/texts_en.json          ← every message the team sees in 5d (English)
├── requirements.txt / requirements.lock.txt              ← packages (install from the lock file)
├── .env.example                  ← copy to .env, add your key
├── data/
│   ├── reference/                ← fixed lists, set once
│   │   └── areas.json            ← the 14 Phnom Penh districts
│   ├── clips/                    ← one file per video: PP-001.json … (stages 1–5b work here)
│   │   └── duplicates/           ← second copies of a video (still count as "already collected")
│   ├── audio/                    ← WAVs from stage 2 (not in git)
│   ├── gemini_answers/           ← Gemini's first answer from stage 4 (never edit)
│   ├── places/                   ← made by 5c: one file per real place, tvna_p_….json (the team may edit names here; 5d adds photos)
│   └── results/
│       └── final_dataset.json    ← made by 6 (the website reads this)
├── templates/                    ← empty JSON templates
├── docs/                         ← field guide, decisions, diagrams
└── tests/                        ← offline checks: python tests/run_all.py
```

There is no database in the pipeline: these JSON files in git **are** the data. `git pull` gives you everyone's clips. Photos and covers are on Cloudinary; the files keep only their links. (The website repo, TvNa-Prototype, has its own Postgres database; loading our places into it is a later step.)

**When a condition is not met, where does the file go?**
- **Bad link, or a duplicate in stage 1:** no file is made at all.
- **Duplicate found later (5a):** the copy moves to `data/clips/duplicates/`.
- **Everything else stays in `data/clips/`.** The status is written **inside** the file, per place (`rejected`, `needs_review`, `auto_added`, `verified`), because one video can have several places with different statuses. A stage that fails leaves the clip unchanged.
- Nothing is ever deleted (except the old `data/results/places.json`, moved once into `data/places/`). Only `verified` places reach `data/places/` and `final_dataset.json`.
- Full table, case by case: [docs/tvna_pipeline_explained.md, section 7](docs/tvna_pipeline_explained.md#7-folders-and-where-a-file-goes-when-a-condition-is-not-met).

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

**In:** `source.url`. **Out:** `data/audio/PP-002.wav` (16 kHz mono), `source.caption`, `source.cover_url`, `source.posted_at`.

```
PP-002: saved data/audio/PP-002.wav (16 kHz, mono, 73.3 s)
  caption: This yet-to-discover restaurant, has such a dope Tteobokki.  …
  posted_at: 2026-11-11 (from TikTok)
  cover: https://res.cloudinary.com/<cloud name>/image/upload/v…/tvna/covers/PP-002.jpg
Next: python stage3_transcribe.py data/clips/PP-002.json
```

- WAVs are not in git. For a teammate's clip, run stage 2 on it.
- No caption on the video → `source.caption` is `null`.
- **Cover picture:** the video's TikTok cover, made a 720 px wide JPG (no hidden photo data such as GPS) and put on Cloudinary as `tvna/covers/PP-NNN`. The website shows it next to the creator's mention.
- `source.cover_url`: a link = done; `null` = TikTok has no cover; `""` or missing = not saved yet, the next run tries again.
- A clip with a WAV but no caption or no cover gets only those (no video download).
- A cover that can't be saved (no Cloudinary keys, no internet) doesn't stop stage 2: the audio is still made, and the message says why.

| Try this | You should see |
|---|---|
| The same command again | `already has audio … Skipped.` |
| A deleted or private video | `Download failed: …` then `Nothing changed` |
| No Cloudinary keys in `.env` | the WAV is made, then `cover: not saved, the Cloudinary keys are not in .env` |
| Old clips (PP-002 to PP-007) after adding the keys | `reading the cover from TikTok (no download)`, then `cover: https://…` |

---

## Stage 3: get the transcript

**In:** the WAV. **Out:** `stt.transcript`: Khmer in Khmer script, English in English, no translation. Audio only (the caption is not used here, so the name as spoken is kept).

```
PP-002: saved transcript (30 lines, gemini-3.6-flash)
  ហែម ភូក ក៏ ឆ្ងាញ់
  បាទ ថ្ងៃ នេះ ទៅ ទៅ ៗ
  សម្រាប់ អ្នក ដែល ចូលចិត្ត ញ៉ាំ អី នៅ កន្លែង ដែល ជន ជាតិ ដើម គេ បើក ហ្មង ណា
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

**Then the code sets the status.** It counts how many of the 3 key fields are filled: name, district, opinion (`completeness`).

| Stage 4 finds | Status |
|---|---|
| no name, or the "name" is only a #hashtag or @account | `rejected` (kept, not deleted) |
| a name, but only 1 or 2 of the 3 key fields | `needs_review` |
| all 3 key fields | `auto_added` (**not** added anywhere; still waits for a person, [see above](#the-status-of-a-place)) |
| all 3, but the name is only in the caption, not said (could be a sponsor) | `needs_review` |

### `data/gemini_answers/`: Gemini's first answer

One file per clip (`PP-002.json`): the places **exactly as stage 4 made them**, before any person touches them. Nobody ever edits it.

```
data/gemini_answers/PP-002.json   ← what Gemini said (before review)
data/clips/PP-002.json            ← after the team fixed it in 5b
```

- **Why:** after 5b the clip file no longer shows what Gemini got wrong. Comparing the two files does, e.g. "Gemini said `area: null`, the team wrote the district".
- **Used by:** nothing yet. Stages 5–6 don't read it, so it doesn't change the website. It's for the improvement loop (Capstone 2): save the team's fixes, give known names to Gemini as hints, and score Gemini's accuracy.
- **Rules:** never edit it (the "before" copy would be lost). It's in git. Stage 4 `--force` writes a new one, but a clip the team already reviewed is never redone, so its copy stays.

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
python stage5b_validate_clips.py data/clips/*.json
```

It reads every clip and **changes nothing**. You'll see (real run):

```
problems (0):
to review (3):
  PP-002.json  "Hanjan Coffee" (needs_review): fill area, google_maps_url; check flags: name_from_caption
  PP-003.json  "Luv selfie booth" (needs_review): fill area, google_maps_url; check flags: name_from_caption
  PP-004.json  "Wat Botum Park" (needs_review): fill area; check flags: name_from_caption
ready (2): verified, no problems
  PP-005.json  "Beans Barley"
  PP-007.json  "Beans Barley"
rejected (0), not at stage 4 yet (1 clip)
Next: python stage5c_match_places.py data/clips/*.json
```

- **to review:** nobody approved it yet; it says what to fill and which flags to check.
- **ready:** `verified` with no mistakes; 5c will give it a `place_id`.
- **problems:** mistakes to fix (step 4).

### 2. In each place, these fields tell you what to do

| Field | What it tells you |
|---|---|
| `verification_status` | `needs_review`: something is missing or uncertain. `auto_added`: looks complete, but still check it (it is **not** published yet). `rejected`: no name or only a tag; skip unless it's really a place |
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
3. **District:** from the Maps address, write it in `area` as text, spelled exactly as in `data/reference/areas.json`, e.g. `"Chamkar Mon"` (not a list). One district per place for now (branches: Capstone 2). A neighborhood like "BKK1" or "Toul Tompoung" is not a district; it stays in `area_description`.
4. **Other missing fields:** fill only what the video or caption says. Unknown stays `null`.
5. **Sign it:** your name in `cleaned_by`, a short note in `cleaner_note` (e.g. "district from Google Maps").
6. **Status:** `"verified"` (correct, goes to the website) or `"rejected"` (not a place, not in Phnom Penh, or wrong).

**Same place, other names.** Creators often call one place by different names (English or Khmer, other spellings). Gemini doesn't know the names we already have (planned for Capstone 2), so **you** link them:
- **The Maps link links the names.** 5c checks the Google Maps link first. Copy the Share link of the **right** place (for a branch, the branch in the video), and two creators' names for it match even if they look nothing alike, e.g. an English name in one clip and a Khmer name in another. Check the name, photos and address on Maps before you copy: a wrong link joins the clip to the wrong place (if that link is already in a place file) or makes a second, duplicate place.
- **Is it already in `data/places/`?** Search it for the name, the other names and the link, e.g. `grep -il "hanjan" data/places/*.json`. If it's there, check it is the same shop.
- **Keep every other name.** Add each name said, written or shown in this video (Khmer name, English name, the sign, another spelling) to `place_name_alt`. If the video only says the Khmer name but the caption, the sign or Google Maps shows the English one (or the other way round), add that one too. 5c can't match a Khmer name with an English one by letters, so these names and the Maps link are the only way they connect.
- **After 5c:** decide every **unclear** place, and check that each **matched** place really is the same shop (see "What you do" in Stage 5c).

Can't find the place on Maps? Leave `area` and `google_maps_url` as `null`, write what you tried in `cleaner_note`, and **keep the status `needs_review`** (held back, not on the website; someone can try again later).

### 4. Check your work

Run `python stage5b_validate_clips.py data/clips/*.json` again. It catches the easy mistakes of editing by hand:

```
problems (1):
  PP-005.json  "Beans Barley"
    - verification_status "verfied" is not a status (use rejected, needs_review, auto_added, verified). Did you mean "verified"?
    - notes: write null, not "nothing"
    - area "7 Makara" is not one of the 14 districts in data/reference/areas.json. Write it exactly as there. Did you mean "Prampi Makara"?
    - missing_fields [] doesn't match completeness 0.67. Don't edit these two: they record what stage 4 found (see data/gemini_answers/)
```

It also catches: `area` written as a list instead of one district as text, a number where text belongs (`price_range: 5` → write `"5"`), a category not in the list, a link that isn't Google Maps, a `verified` place with no district, Maps link or `cleaned_by`, a held-back place with no `cleaner_note`, and a broken JSON file (a missing comma or quote).

**Done =** `problems (0)`, and every place is `ready` (verified), `rejected`, or held back with a note. Then commit, push, and run 5c.

Example, PP-002: `missing_fields: ["area"]` → find "Hanjan Coffee" on Maps → write its district in `area` and the link in `google_maps_url` → `name_from_caption`: check the video really shows Hanjan Coffee → `cleaned_by`, `"verified"`.

---

## Stage 5c: match places

**In:** `verified` places (one person at a time, see the team rule in [How `place_id` works](#how-place_id-works)). **Out:** a `place_id` for each, and one file per real place in `data/places/`, with all its names in `aliases`.

So two clips about the same café count as **one place**. How it decides, and what to do with **unclear** or a **wrong match**: [How `place_id` works](#how-place_id-works).

```
new (1):
  PP-003.json  "Luv selfie booth" -> tvna_p_…
waiting for review (1):
  PP-002.json  "Hanjan Coffee" (verification_status "needs_review")
```

- **Waiting for review:** not checked in 5b yet. Nothing changes for it.
- When a clip calls a known place something else, 5c says `website name stays "…"` (the name in its place file).

---

## Stage 5d: photos for new places

**In:** places with **0 photos**: new places from 5c, and places made before 5d existed (e.g. Beans Barley). `stage5d_check_photos.py` lists them all. **Out:** 1–5 photos in the place file. Photo 1 is the main one on the website. A place needs at least 1 to be published (stage 6 leaves it out until then).

```sh
python stage5d_check_photos.py        # problems / need photos (with the name and Maps link) / ready
python stage5d_add_photo.py tvna_p_0002 front.jpg "https://lh3.googleusercontent.com/..." --source "Google Maps" --credit "Dara S."
python stage5d_add_photo.py tvna_p_0002 --move 3 --to 1     # make photo 3 the main one
python stage5d_add_photo.py tvna_p_0002 --remove 2          # a wrong photo (asks first; the picture stays on Cloudinary)
```

- **A photo** is a file or an **image link** (on Google Maps: open the photo, right-click → *Copy image address*). A web page link is refused and says this.
- **Each photo is checked:** JPG, PNG, WebP or HEIC; 20 MB at most; at least 600 px on each side; not the same picture twice; 5 at most. Then it becomes a 1200 px JPG **without hidden photo data** (no GPS, no camera info), goes to Cloudinary as `tvna/places/<place_id>-<code>`, and is saved as `{url, source, credit, sha256}`. `sha256` is the picture's fingerprint, used to refuse the same picture twice.
- **`--source`:** `"Google Maps"`, `"Shop's own page"`, `"Own photo"` or `"Other: <where>"`. **`--credit`:** who took or posted it (needed). Google Maps photos belong to the person who posted them, so the source and credit let us find and swap them later.
- Several photos in one command: each is tried, a bad one is said and skipped, the rest are added (exit code 1 if any failed).
- A place file changed by someone else during an upload is refused: `git pull` and add the photo again.
- Commit and push the place files right after.

**Which photos (the photo guide):**

| Photo | What |
|---|---|
| 1 (the main one) | the front, with the shop's sign, so people recognise it from the street |
| 2 | inside: the seats, the room |
| 3 | a dish or drink they are known for (the one in the video, if you can) |
| 4–5 | optional: more food, the menu, the view |

- **Avoid:** blurry or dark photos; screenshots with app buttons or text on top; a person's face as the main subject; a photo of another branch or another shop.
- **From Google Maps:** search the place (or open its Maps link from the checker) → **Photos** → open a photo → right-click it → **Copy image address** → paste that link in the command. The source is `"Google Maps"`, the credit is the name shown on the photo.
- **Your own photo:** add the file; the source is `"Own photo"`, the credit is your name. Phone photos (HEIC) work; the hidden GPS data is removed.

---

## Stage 6: final dataset

**In:** clips + `data/places/` + `areas.json`. **Out:** `data/results/final_dataset.json`, one record per place:

- **one name** (`place_name` from the place file); other names never reach the website
- **one district** in `area` (text, or `null`): the one in the place file, else the first one from the clips. Clips naming other districts → a warning (one district per branch: Capstone 2)
- `category`, `price_range`, `opening_hours`, `menu_items`: every different value from all clips
- `photos`: 1–5 from the place file (`url`, `source`, `credit`; photo 1 is the main one)
- `mentions`: one per clip (`clip_id`, `creator`, `video_url` = the TikTok link, `cover_url` = its cover picture or `null`, `speaker_opinion`)
- `popularity`: number of different creators who posted about it

Only `verified` places with a `place_id` **and at least 1 photo** are published (no photo yet → a warning with the 5d command; a mistake in the photo list → a warning pointing to `stage5d_check_photos.py`). If **every** verified place still needs a photo, it stops and keeps the old file (no empty website file). A video link or cover that isn't an `https://` link is published as `null` with a warning. It warns about the rest, when clips disagree (e.g. two price ranges), and about a value that isn't text (a number typed by hand is published as text, e.g. `"5"`). It rebuilds the file from scratch each time. No place files in `data/places/` yet → it says to run 5c first.

> **Website team:** since 2026-11-18 the file is at **`data/results/final_dataset.json`** (it was `data/final_dataset.json`). It has **no `place_name_alt`** (since 2026-11-17). Use `place_name`. `area` is **one district as text** (e.g. `"Chamkar Mon"`) or `null`, not a list, in every file (since 2026-11-18). New on 2026-11-28: `photos` (`[{url, source, credit}]`, 1–5, the first is the main one) and, in each mention, `video_url` and `cover_url` (or `null`); a place with no photo yet is not in the file. Fields: `templates/tvna_final_dataset_template.json`.

---

## The team's flow

```
4 ─► 5a ─► 5b CLEAN (your clips) ─► push ─► 5c MATCH (one person at a time) ─► push ─► 5d PHOTOS (new places only) ─► push ─► 6
```

1. **Split the clips** in ranges of whole tens, e.g. A: `PP-001`–`PP-039`, B: `PP-040`–`PP-079`. You clean and match only your range, so two people never edit the same clip file. Your range as a command: A = `data/clips/PP-00?.json data/clips/PP-0[1-3]?.json`, B = `data/clips/PP-0[4-7]?.json`.
2. **5b, clean:** review your clips (see [Stage 5b](#stage-5b-team-review)). No photos yet. `stage5b_validate_clips.py` must say `problems (0)`. Commit and push.
3. **5c, match:** say in the team chat that you start, `git pull`, run 5c on **your range only** (`python stage5c_match_places.py data/clips/PP-0[4-7]?.json`), decide every **unclear** place, commit and push. Then the next person. (One at a time, see [How `place_id` works](#how-place_id-works).)
4. **5d, photos:** 5c's report lists your **new** places: those are yours to photograph. `stage5d_check_photos.py` lists every place that still needs photos; older places (e.g. Beans Barley, made before 5d) are there too, so agree in the team chat who takes them. Commit and push the place files.
5. **6, final dataset:** one person runs it after everyone has pushed. A verified place with no photo is left out until it gets one.

---

## Team rules

**Collecting**
- `git pull` before stage 1, and push your new clips soon. Each computer picks the next free `PP-` number, so two people at the same time can get the same number.
- Collect with `--from-file … --check-only` first. Only new videos go on to stages 2–4.

**Data**
- Missing = `null`. Never `""`, "N/A" or "Unknown".
- Districts exactly as in `data/reference/areas.json` ("Boeung Keng Kang" ≠ "Boeng Keng Kang").
- Only a person sets `verified`. Only `verified` places get a `place_id` and reach the website.
- The caption's spelling of a name wins over the spoken one. One name per place on the website; other names are kept for matching only.
- Never edit `data/gemini_answers/`. Clips are never deleted, only moved to `duplicates/` (5a).

**Photos**
- 1 to 5 per place, photo 1 is the main one. Always with `--source` and `--credit`, so a photo can be found and swapped later.
- For places with no photos yet. A wrong photo: `--remove` it, then add the right one. Collecting better photos for a place that already has good ones is for Capstone 2.
- Never put the Cloudinary secret anywhere but `.env`.

**Git and safety**
- Never commit `.env`, videos or WAVs (`.gitignore` blocks them). Never put your API key in code.
- Before every push: `python tests/run_all.py` must say `Total: N/N passed`. The tests use a fake TikTok, Gemini and Cloudinary, cost nothing and never touch `data/`.
- Every "skip if already done" check is tested with a filled value, `null`, `""` and a missing key, and a second run must change nothing and call nothing.

---

## More detail

- [`docs/tvna_pipeline_explained.md`](docs/tvna_pipeline_explained.md): the whole pipeline explained for the supervisor: each stage (input, output, when it continues), statuses, folders, key takeaways, limits.
- [`docs/tvna_field_guide.md`](docs/tvna_field_guide.md): every field, who fills it, value rules, category list.
- [`docs/decisions.md`](docs/decisions.md): key decisions and why.
- [`docs/tvna_data_model.mmd`](docs/tvna_data_model.mmd): how the JSON files connect (the `.png` picture is older: it still shows `places.json`, `place_name_alt` in the final dataset, many districts per place and no photos).
