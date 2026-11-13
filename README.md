# TvNa

<p align="center">
  <strong>TvNa</strong> is a platform designed to help you discover new hangout spots and food places in your area. Whether you’re looking for a cozy café, a trendy restaurant, or a fun place to chill with friends, <strong>TvNa</strong> makes it easy to find the perfect spot.<br/>
  But <strong>TvNa</strong> is more than just a discovery tool — it’s also a community. Users can share their experiences, post about hidden gems, and recommend places that others may have never known about. Explore, share, and connect with fellow foodies and adventurers on <strong>TvNa</strong>!
</p>

---

## Data pipeline

Turns **TikTok videos about places in Phnom Penh** into `data/final_dataset.json`: one record per place, for the TvNa website.

**Scope:** TikTok videos only. Places in Phnom Penh only.

Each video becomes one clip file (`data/clips/PP-001.json`). Every stage is a small command that fills its own part of the clip file, prints what it did and the next command, and then stops so you can check the result.

---

## Where we are now

_Last updated: 2026-11-12_

| Stage | What it does | Script | Status |
|---|---|---|---|
| 1. Collect | Paste a TikTok link → new clip file | `stage1_new_clip.py` | ✅ Built and tested |
| 2. Video → audio | Download the video → 16 kHz mono WAV | `stage2_get_audio.py` | ✅ Built and tested |
| 3. Audio → transcript | Gemini writes the Khmer + English transcript | `stage3_transcribe.py` | 🔜 **Next, being built** |
| 4. Transcript → places | Gemini finds each place and what was said about it | `stage4_extract_places.py` | ✅ Built (Phnom Penh check planned) |
| 5a. Remove duplicates | Moves clips of the same video to `duplicates/` | `stage5a_dedupe_clips.py` | ✅ Built |
| 5b. Team review | People check and fill missing fields | by hand + `stage5b_validate_clips.py` | ⏳ Validator planned |
| 5c. Match places | Gives each place a `place_id` from `places.json` | `stage5c_match_places.py` | ✅ Built (fuzzy name matching planned) |
| 6. Final dataset | Builds `data/final_dataset.json` | `stage6_build_final_dataset.py` | ✅ Built |

Until stage 3 is built, a new clip stops after stage 2.

**Coming next, in order:**
1. Stage 3: transcript
2. Automatic tests (`python -m unittest`)
3. The clip validator
4. Fuzzy name matching
5. The Phnom Penh check in stage 4

---

## Setup (once per computer)

You need **Python 3.12**, **ffmpeg** and **git**. On a Mac:

```sh
brew install python@3.12 ffmpeg
```

Then:

```sh
git clone https://github.com/VorngViseth/TvNa-Web.git
cd TvNa-Web
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
cp .env.example .env
```

Open `.env` and add your own Gemini API key after `GEMINI_API_KEY=`. You can get a key from Google AI Studio (aistudio.google.com). **Never commit `.env`:** it's already in `.gitignore`.

**Every time** you open a new terminal:

```sh
cd TvNa-Web
source .venv/bin/activate
```

On Windows, create the venv with `py -3.12 -m venv .venv` and activate it with `.venv\Scripts\activate`.

---

## How to run

Each command does one stage, prints what it did and the next command, then stops so you can check.

**Right now a new video can go through stages 1 and 2.** Stage 3 is being built, and stages 4–6 need its transcript.

**For each new video:**

```sh
source .venv/bin/activate                                 # in every new terminal
git pull                                                  # get the team's latest clips first

python stage1_new_clip.py "<TikTok link>"                 # 1. ✅ new clip file: data/clips/PP-NNN.json
python stage2_get_audio.py data/clips/PP-NNN.json         # 2. ✅ audio: data/audio/PP-NNN.wav
# 3. 🔜 transcript: stage3_transcribe.py (being built)
python stage4_extract_places.py data/clips/PP-NNN.json    # 4. ✅ places, from the transcript (--force to redo)
```

Replace `PP-NNN` with the number stage 1 printed.

**Then, for all clips together:**

```sh
python stage5a_dedupe_clips.py data/clips/*.json          # 5a. ✅ move clips of the same video to duplicates/
# 5b. team review: check and fill the clip files by hand (field guide, section 6)
python stage5c_match_places.py data/clips/*.json          # 5c. ✅ give each place a place_id, update places.json
python stage6_build_final_dataset.py data/clips/*.json    # 6.  ✅ build data/final_dataset.json
```

Each stage has its own section below with what it does and a "Test it yourself" table.

---

## Folder layout

```
TvNa-Web/
├── README.md                      ← you are here
├── requirements.txt               ← packages we use (pinned)
├── requirements.lock.txt          ← exact versions of everything; install from this
├── .env.example                   ← copy to .env, add your key
├── tvna_common.py                 ← shared helpers used by all stages
├── stage1_new_clip.py … stage6_build_final_dataset.py   ← one script per stage
├── data/
│   ├── areas.json                 ← the 14 Phnom Penh districts (fixed list)
│   ├── clips/                     ← one file per video: PP-001.json, PP-002.json …
│   │   └── duplicates/            ← clips of a video we already have
│   ├── audio/                     ← WAV files made by stage 2 (not in git)
│   ├── places.json                ← made by stage 5c
│   └── final_dataset.json         ← made by stage 6
├── templates/                     ← empty JSON templates for every file type
├── docs/                          ← field guide and diagrams
└── tests/                         ← automatic tests (coming)
```

---

## Stage 1: add a video

```sh
python stage1_new_clip.py "https://www.tiktok.com/@user/video/7593339174695046416"
```

What it does:
1. **Refuses links that aren't TikTok.**
2. **Expands short links:** a `vt.tiktok.com/...` link from TikTok's Share → Copy link is turned into the full link automatically.
3. **Cleans the link:** the `?_r=...&_t=...` tracking part is removed.
4. **Checks for duplicates:** if the same video is already in `data/clips/` or `data/clips/duplicates/`, it stops and creates nothing.
5. **Makes the clip file:** `data/clips/PP-NNN.json`, with `clip_id`, `url`, `platform`, `creator` (from the link) and `collected_at` (today) filled in.

Add the date the video was posted, if you know it:

```sh
python stage1_new_clip.py "<link>" --posted-at 2026-10-22
```

You'll see:

```
Created data/clips/PP-001.json
  url:       https://www.tiktok.com/@user/video/7593339174695046416
  creator:   @user
  posted_at: null (add it by hand, or use --posted-at)
Next: python stage2_get_audio.py data/clips/PP-001.json
```

**Test it yourself:**

| Try this | You should see |
|---|---|
| A TikTok link of a Phnom Penh place | `Created data/clips/PP-00N.json`. Open the file: `url` has no `?...` part and `creator` matches the video |
| The same video again (full or short link) | `Duplicate: same video as PP-00N … Nothing created.` |
| A YouTube or other link | `Only TikTok links are in scope … Nothing created.` |
| `--posted-at 2026-13-01` | `… is not a date like 2026-10-22` |

---

## Stage 2: get the audio

```sh
python stage2_get_audio.py data/clips/PP-001.json
```

What it does:
1. **Downloads the video** from the clip's TikTok link (with yt-dlp) into a temporary folder.
2. **Makes the WAV:** `data/audio/PP-001.wav`, 16 kHz, mono, 16-bit (with ffmpeg). This is the format stage 3 needs.
3. **Deletes the video.** Only the WAV is kept.
4. **Updates the clip file:** sets `audio_file`. If `posted_at` is empty, it fills it with the date TikTok shows (Phnom Penh time).

You'll see:

```
PP-001: downloading https://www.tiktok.com/@user/video/7593339174695046416 ...
PP-001: saved data/audio/PP-001.wav (16 kHz, mono, 52.4 s)
  posted_at: 2026-01-09 (from TikTok)
Next: python stage3_transcribe.py data/clips/PP-001.json
```

You can give it several clips at once (`data/clips/PP-002.json data/clips/PP-003.json`). If one fails, the others keep going, and a summary is printed at the end.

WAV files are **not in git**. After `git pull`, a teammate's clip has `audio_file` set but no WAV on your computer: just run stage 2 on it, and it downloads the video again.

**Test it yourself:**

| Try this | You should see |
|---|---|
| The clip you made in stage 1 | `saved data/audio/PP-00N.wav (16 kHz, mono, … s)`. Play the WAV: it's the video's sound. The clip file now has `audio_file` (and `posted_at`, if it was empty) |
| The same command again | `already has audio … Skipped.` |
| The same command with `--force` | It downloads the video and makes the WAV again |
| A clip whose video was deleted or made private | `Download failed: …` then `Nothing changed in …`. The clip file isn't touched |

---

## Stages 4–6

Built. They need the transcript from stage 3 first. The commands are in [How to run](#how-to-run).

---

## Team rules

- **Before stage 1, run `git pull`. Share your new clip soon after.** Each computer picks the next free `PP-` number, so two people working at the same time can get the same number.
- **Missing values are always `null`.** Never use `""`, "N/A" or "Unknown".
- **District names must match `data/areas.json` exactly.** "Boeng Keng Kang" and "Boeung Keng Kang" don't match.
- **Never commit `.env`, videos or WAV files.** `.gitignore` already blocks them.

---

## More detail

- [`docs/tvna_field_guide.md`](docs/tvna_field_guide.md) explains every field, who fills it, and the value rules. Note: the guide still uses the old script names (for example `extract_places_gemini.py`, now `stage4_extract_places.py`). It will be updated.
- [`docs/tvna_data_model.png`](docs/tvna_data_model.png) shows how the JSON files connect.
- [`docs/tvna_pipeline_overview.png`](docs/tvna_pipeline_overview.png) shows the stages at a glance.
