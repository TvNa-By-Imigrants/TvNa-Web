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

_Last updated: 2026-11-17_

| Stage | What it does | Script | Status |
|---|---|---|---|
| 1. Collect | Paste a TikTok link → new clip file | `stage1_new_clip.py` | ✅ Built and tested |
| 2. Video → audio | Download the video → 16 kHz mono WAV | `stage2_get_audio.py` | ✅ Built and tested |
| 3. Audio → transcript | Gemini writes the Khmer + English transcript | `stage3_transcribe.py` | ✅ Built and tested |
| 4. Transcript → places | Gemini finds each place and what was said about it | `stage4_extract_places.py` | ✅ Built and tested (Phnom Penh check planned) |
| 5a. Remove duplicates | Moves clips of the same video to `duplicates/` | `stage5a_dedupe_clips.py` | ✅ Built and tested |
| 5b. Team review | People check and fill missing fields | by hand + `stage5b_validate_clips.py` | ⏳ Validator planned |
| 5c. Match places | Gives each place a `place_id` from `places.json` | `stage5c_match_places.py` | ✅ Built and tested |
| 6. Final dataset | Builds `data/final_dataset.json` | `stage6_build_final_dataset.py` | ✅ Built and tested |

**Coming next, in order:**
1. **Now: the improvement loop** (below)
2. The clip validator
3. The Phnom Penh check in stage 4

**Next milestone (noted, not built yet):**
- Save each video's view/like/comment/share counts (stage 2), to help rank places
- Every plan follows one real clip through all stages: what goes in, what comes out, what gets removed
- GitHub runs `python tests/run_all.py` on every push (CI), with no new packages. CI is changed only with the team's OK

**The improvement loop.** Gemini forgets everything after each run, so we save the team's fixes and give them back to it:

> Run stages 1–4 → team fixes mistakes (5b) → fixes are saved → next video gets them as hints → a test score shows if it improved

- Fixes are saved automatically: `known_names.json` (right names + what Gemini misheard) and `mistakes.json` (which field was wrong).
- Stages 3 and 4 get the known names and the TikTok caption as hints.
- The first ~10 clips the team approves become a test set. A change to the prompt or model stays only if the score goes up.

Steps: 1. keep Gemini's first answer ✅ · 2. the TikTok caption (saved by stage 2 ✅ · used by stage 4, which keeps the caption's name and the spoken name · one name on the website) · 3. save the team's fixes · 4. hints for Gemini · 5. test score

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

**Why:** our packages (yt-dlp, Gemini and the rest) are installed only in `.venv/`, the project's own Python 3.12, at the exact versions in `requirements.lock.txt`. `source .venv/bin/activate` makes `python` mean that Python, so everyone on the team runs the same Python with the same packages. It lasts until you close that terminal.

Check it worked: `which python` should end in `.venv/bin/python`.

If you forget it:

| You see | Why |
|---|---|
| `zsh: command not found: python` | Plain `python` only exists when the venv is on. |
| `ModuleNotFoundError: No module named 'yt_dlp'` (or `google`, `dotenv`) | You ran the Mac's own `python3`, which has none of our packages. |

Fix for both: run `source .venv/bin/activate` in the repo folder, then run your command again.

In VS Code you can make new terminals do this for you: press Cmd+Shift+P, choose **Python: Select Interpreter**, and pick the one in `./.venv`.

On Windows, create the venv with `py -3.12 -m venv .venv` and activate it with `.venv\Scripts\activate`.

---

## How to run

Each command does one stage, prints what it did and the next command, then stops so you can check.

**A new video can now go through every stage.**

**For each new video:**

```sh
source .venv/bin/activate                                 # in every new terminal
git pull                                                  # get the team's latest clips first

python stage1_new_clip.py "<TikTok link>"                 # 1. ✅ new clip file: data/clips/PP-NNN.json
python stage2_get_audio.py data/clips/PP-NNN.json         # 2. ✅ audio: data/audio/PP-NNN.wav
python stage3_transcribe.py data/clips/PP-NNN.json        # 3. ✅ transcript, saved in the clip's stt
python stage4_extract_places.py data/clips/PP-NNN.json    # 4. ✅ places, from the transcript
```

Replace `PP-NNN` with the number stage 1 printed. Stages 2–4 also take several clips at once; one failing doesn't stop the others. Add `--force` to redo a clip. Stages 3 and 4 never redo a clip the team already reviewed, even with `--force`.

**Then, for all clips together:**

```sh
python stage5a_dedupe_clips.py data/clips/*.json          # 5a. ✅ move clips of the same video to duplicates/
# 5b. team review: check and fill the clip files by hand (field guide, section 6)
python stage5c_match_places.py data/clips/*.json          # 5c. ✅ give each place a place_id, update places.json
python stage6_build_final_dataset.py data/clips/*.json    # 6.  ✅ build data/final_dataset.json
```

Each stage has its own section below with what it does and a "Test it yourself" table.

**Before every push:** run all offline checks:

```sh
python tests/run_all.py        # Total: N/N passed (stops with an error if any check fails)
```

They use fake Gemini, fake TikTok and fake Maps links, cost nothing and never touch `data/`. One stage only: `python tests/test_stage4.py`. Every stage is also checked to **run twice safely**: the second run changes no file and doesn't call TikTok or Gemini (one exception: stage 1 with a short `vt.tiktok.com` link asks TikTok which video it is, then says `Duplicate`).

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
│   ├── gemini_answers/            ← stage 4's places exactly as Gemini gave them (never edit)
│   ├── places.json                ← made by stage 5c
│   └── final_dataset.json         ← made by stage 6
├── templates/                     ← empty JSON templates for every file type
├── docs/                          ← field guide and diagrams
└── tests/                         ← offline checks: python tests/run_all.py (no Gemini, no internet)
```

---

## Stage 1: add a video

```sh
python stage1_new_clip.py "<TikTok link>"
```

Makes a new clip file from a TikTok link. Short `vt.tiktok.com` links are expanded and the `?...` tracking part is removed. If the video is already in `data/clips/` (or `duplicates/`), nothing is created.

You'll see:

```
Created data/clips/PP-002.json
  url:       https://www.tiktok.com/@motokhiev.bydm/video/7706878472664222982
  creator:   @motokhiev.bydm
  posted_at: null (stage 2 fills it from TikTok)
Next: python stage2_get_audio.py data/clips/PP-002.json
```

**Test it yourself:**

| Try this | You should see |
|---|---|
| A Phnom Penh TikTok link | `Created data/clips/PP-00N.json` |
| The same video again (full or short link) | `Duplicate: same video as PP-00N … Nothing created.` |
| A YouTube or other link | `Only TikTok links are in scope … Nothing created.` |

---

## Stage 2: get the audio

```sh
python stage2_get_audio.py data/clips/PP-002.json
```

Downloads the video, keeps only its sound as `data/audio/PP-002.wav` (the format stage 3 needs), saves the creator's TikTok caption in `source.caption`, and fills `posted_at` if it's empty. WAVs are not in git: for a teammate's clip, just run stage 2 on it.

You'll see:

```
PP-002: downloading https://www.tiktok.com/@motokhiev.bydm/video/7706878472664222982 ...
PP-002: saved data/audio/PP-002.wav (16 kHz, mono, 73.3 s)
  caption: This yet-to-discover restaurant, has such a dope Tteobokki.  …
  posted_at: 2026-11-11 (from TikTok)
Next: python stage3_transcribe.py data/clips/PP-002.json
```

The caption often has the place name written correctly, so stage 4 will use it (stage 3 stays audio only, so the spoken name is kept too). A clip that already has its WAV but no caption (made before captions were added) gets the caption only, with no download:

```
PP-003: already has audio; reading the caption from TikTok (no download) ...
PP-003: saved the caption
  caption: Comfortable and unique, best quality best memories.Welcome t …
```

**Test it yourself:**

| Try this | You should see |
|---|---|
| Your clip from stage 1 | `saved data/audio/PP-00N.wav …`. Play it: it's the video's sound |
| The same command again | `already has audio … Skipped.` |
| A clip whose video was deleted or private | `Download failed: …` then `Nothing changed in …` |
| Open the clip file | `source.caption` has the TikTok caption, or `null` if the video has none |

---

## Stage 3: get the transcript

```sh
python stage3_transcribe.py data/clips/PP-002.json
```

Sends the WAV to Gemini, which writes what is said: Khmer in Khmer script, English in English, no translation. Saved in the clip's `stt`. If `gemini-3.8-flash` is busy, it tries again, then switches to `gemini-3.6-flash`. `stt.model` shows which one did it. When Google is busy, this can take several minutes.

You'll see (here Google was busy):

```
PP-002: transcribing data/audio/PP-002.wav (73.3 s) with gemini-3.8-flash ...
  gemini-3.8-flash is busy (504), trying again in 10 s (2/3)
  gemini-3.8-flash is busy (503), trying again in 30 s (3/3)
  gemini-3.8-flash is still busy (503).
  Trying gemini-3.6-flash instead ...
  gemini-3.6-flash is busy (504), trying again in 10 s (2/3)
PP-002: saved transcript (37 lines, gemini-3.6-flash)
  ហាងម្ហូបកូរ៉េឆ្ងាញ់
  មួយកន្លែងទៀតនៅ Toul Tompoung
  សម្រាប់អ្នកដែលចូលចិត្តញ៉ាំបាយនៅកន្លែងដែលជនជាតិដើមគេបើកហ្មង ហា
  ...
Next: python stage4_extract_places.py data/clips/PP-002.json
```

If it ends with `Gemini is busy … Run the same command again later`, do that. Clips that already have a transcript are skipped.

A video with only music (nobody speaks) gets the transcript `[no speech]`. Song lyrics are not written down.

With `--force`, the clip's old places are cleared too (they point to sentences of the old transcript), so run stage 4 again.

**Test it yourself:**

| Try this | You should see |
|---|---|
| Your clip from stage 2 | `saved transcript (… lines, …)`. Open the clip: `stt.transcript` matches the video |
| The same command again | `already has a transcript. Skipped.` |
| A clip with no WAV | `No audio … Run stage 2 first` |
| `--force` on a clip that has places | `old places cleared … Stage 4 will find them again.` |

---

## Stage 4: find the places

```sh
python stage4_extract_places.py data/clips/PP-002.json
```

Gemini reads the transcript and lists each place with what was said about it (category, menu, opinion …). The code then checks the district against `data/areas.json` and gives each place a status: `auto_added`, `needs_review` or `rejected`. Same busy handling as stage 3 (`gemini-3.6-flash`, backup `gemini-3.8-flash`). A `[no speech]` clip is skipped.

A copy of Gemini's answer is also saved in `data/gemini_answers/PP-002.json`. **Never edit it:** after the team review, it shows what Gemini got wrong (for the improvement loop).

Gemini reads up to 60 sentences at once, so a normal TikTok is read whole. A longer transcript is read in parts, and details about the same place from later parts are added to it.

You'll see:

```
PP-002: finding places in 33 sentences with gemini-3.6-flash ...
PP-002: 1 place found (gemini-3.6-flash)
  - Hanjang Coffee & Eatery (restaurant): needs_review
Next: python stage5a_dedupe_clips.py data/clips/*.json
```

`needs_review` here because no district was named. The team fills it in stage 5b.

A clip the team already reviewed (a name in `cleaned_by`, or status `verified`) is never redone, even with `--force`, so their fixes are kept.

**Test it yourself:**

| Try this | You should see |
|---|---|
| Your clip from stage 3 | `… place(s) found`, one line per place. Open the clip: each place is in `fields` |
| The same command again | `already has places. Skipped.` |
| A clip with no transcript | `No transcript yet. Run stage 3 first` |
| Write your name in a place's `cleaned_by`, then run with `--force` | `1 place was reviewed by the team. Skipped, so their fixes are kept.` |

---

## Stage 5c: match places

```sh
python stage5c_match_places.py data/clips/*.json
```

Run after the team review (5b). Gives each place a `place_id` from `data/places.json`, so clips about the same place count as one. Each place is checked in this order:

| Check | Result |
|---|---|
| Same Google Maps link | matched (even a Khmer and an English name) |
| Same name or alias (capitals, spaces, punctuation, "&"/"and", "é"/"e", "ឲ"/"ឱ" don't matter) | matched |
| Name score 95% or more (not for Khmer names) | matched, new spelling saved as an alias |
| Score 75–94%, one name inside the other, or a close Khmer name | **unclear**: `place_id` stays null |
| Anything else | new place |

**For each unclear place:** write the suggested `place_id` in the clip if it's the same place, or `"new"` if not, then run 5c again. Every name that gets a `place_id` is saved as an alias, so it matches exactly next time.

You'll see (here a second clip spelled the name differently):

```
matched (1):
  PP-099.json  "Han-Jan Coffee & Eatery" -> tvna_p_0001 (fuzzy 97% like "Hanjang Coffee & Eatery"; new aliases: Han-Jan Coffee & Eatery)
new (2):
  PP-002.json  "Hanjang Coffee & Eatery" -> tvna_p_0001
  PP-003.json  "ALWAYS selfie booth" -> tvna_p_0002
unclear (0):
unknown_id (0):
skipped (0): already have a place_id, rejected, or no name
Next: python stage6_build_final_dataset.py data/clips/*.json
```

**Test it yourself:**

| Try this | You should see |
|---|---|
| A clip with a slightly different spelling of a known place | `matched … (fuzzy 9N% like "…")` |
| "Luv selfie booth" when "ALWAYS selfie booth" is known | `unclear … maybe tvna_p_0002 "ALWAYS selfie booth" (77%)` |
| Write that `place_id` in the clip, run again | `set by the team; new aliases: Luv selfie booth` |
| The same command again | nothing new; places with a `place_id` are skipped, and their Maps links aren't read again |

---

## Stages 5a and 6

Built and tested. The commands are in [How to run](#how-to-run).

- **5a** again moves nothing. A clip file that is gone (already moved) is listed under `problems`, not an error.
- **6** rebuilds `data/final_dataset.json` from scratch each time, so the same clips give the same file. Empty text (`""`) is written as `null`.

---

## Team rules

- **Before stage 1, run `git pull`. Share your new clip soon after.** Each computer picks the next free `PP-` number, so two people working at the same time can get the same number.
- **Missing values are always `null`.** Never use `""`, "N/A" or "Unknown".
- **District names must match `data/areas.json` exactly.** "Boeng Keng Kang" and "Boeung Keng Kang" don't match.
- **Never commit `.env`, videos or WAV files.** `.gitignore` already blocks them.

---

## More detail

- [`docs/tvna_field_guide.md`](docs/tvna_field_guide.md) explains every field, who fills it, and the value rules. Note: the guide still uses the old script names (for example `extract_places_gemini.py`, now `stage4_extract_places.py`), and its section 8 still says "exact match only" (see Stage 5c above). It will be updated.
- [`docs/tvna_data_model.png`](docs/tvna_data_model.png) shows how the JSON files connect.
- [`docs/tvna_pipeline_overview.png`](docs/tvna_pipeline_overview.png) shows the stages at a glance.
