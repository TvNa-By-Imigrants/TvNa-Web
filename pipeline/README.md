# TVNA data pipeline

Turns **TikTok videos about places in Phnom Penh** into `data/final_dataset.json`: one record per place, for the TvNa website.

**Scope:** TikTok videos only. Places in Phnom Penh only.

Each video becomes one clip file (`data/clips/PP-001.json`). Every stage is a small command that fills its own part of the clip file, prints what it did and the next command, and then stops so you can check the result.

---

## Where we are now

_Last updated: 2026-11-10_

| Stage | What it does | Script | Status |
|---|---|---|---|
| 1. Collect | Paste a TikTok link → new clip file | `stage1_new_clip.py` | ✅ Built and tested |
| 2. Video → audio | Download the video → 16 kHz mono WAV | `stage2_get_audio.py` | 🔜 **Next, being built** |
| 3. Audio → transcript | Gemini writes the Khmer + English transcript | `stage3_transcribe.py` | ⏳ Planned |
| 4. Transcript → places | Gemini finds each place and what was said about it | `stage4_extract_places.py` | ✅ Built (Phnom Penh check planned) |
| 5a. Remove duplicates | Moves clips of the same video to `duplicates/` | `stage5a_dedupe_clips.py` | ✅ Built |
| 5b. Team review | People check and fill missing fields | by hand + `stage5b_validate_clips.py` | ⏳ Validator planned |
| 5c. Match places | Gives each place a `place_id` from `places.json` | `stage5c_match_places.py` | ✅ Built (fuzzy name matching planned) |
| 6. Final dataset | Builds `data/final_dataset.json` | `stage6_build_final_dataset.py` | ✅ Built |

Until stages 2 and 3 are built, a new clip stops after stage 1.

**Coming next, in order:**
1. Stage 2: download and audio
2. Stage 3: transcript
3. Automatic tests (`python -m unittest`)
4. The clip validator
5. Fuzzy name matching
6. The Phnom Penh check in stage 4

---

## Setup (once per computer)

You need **Python 3.12**, **ffmpeg** and **git**. On a Mac:

```sh
brew install python@3.12 ffmpeg
```

Then:

```sh
git clone https://github.com/VorngViseth/TvNa-Web.git
cd TvNa-Web/pipeline
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
cp .env.example .env
```

Open `.env` and add your own Gemini API key after `GEMINI_API_KEY=`. You can get a key from Google AI Studio (aistudio.google.com). **Never commit `.env`:** it's already in `.gitignore`.

**Every time** you open a new terminal:

```sh
cd TvNa-Web/pipeline
source .venv/bin/activate
```

On Windows, create the venv with `py -3.12 -m venv .venv` and activate it with `.venv\Scripts\activate`.

---

## Folder layout

```
pipeline/
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
│   ├── audio/                     ← WAV files (not in git)
│   ├── videos/                    ← videos saved by hand, as a backup (not in git)
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

## Stages 4–6 (built; they need transcripts from stages 2–3 first)

```sh
python stage4_extract_places.py data/clips/PP-001.json      # add --force to redo a clip
python stage5a_dedupe_clips.py data/clips/*.json
# stage 5b: team review, by editing the clip files (see the field guide, section 6)
python stage5c_match_places.py data/clips/*.json
python stage6_build_final_dataset.py data/clips/*.json      # -> data/final_dataset.json
```

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
