# TVNA pipeline: decisions

Key choices and why, newest first. Older decisions (before 2026-11-17) are still only in the README and the field guide. TODO: move them here.

---

## 2026-11-28: Stage 6 publishes photos and video links; no photo, not published

**Decision:**
- Each record in `final_dataset.json` gets `photos: [{url, source, credit}]` from its place file (`sha256` stays in the pipeline). Each mention gets `video_url` (the TikTok link) and `cover_url` (from stage 2, or `null`).
- A verified place with no photo yet is left out, with a warning giving the 5d command. A place with a mistake in its photo list is left out too, pointing to `stage5d_check_photos.py`.

**Why:** the website needs at least one picture per place; leaving a place out is safer than showing an empty card, and the warning says what to do.

**Limit:** Beans Barley (`tvna_p_0001`) drops off the website until it gets a photo.

**Note for the website team:** new fields `photos`, `mentions[].video_url`, `mentions[].cover_url`.

---

## 2026-11-28: Photos belong to the place (stage 5d), on Cloudinary

**Decision:**
- Photos are added after 5c, only to **new** places (0 photos); a known place already has them. 1 to 5 per place, photo 1 is the main one.
- `stage5d_add_photo.py` (and later the review page) uses one shared function, `tvna_review.add_photo`. Each photo is checked (20 MB at most, at least 600 px on each side, 5 at most, not the same picture twice), made a 1200 px JPG without EXIF (no GPS), and put on Cloudinary as `tvna/places/<place_id>-<first 10 of sha256>`. Only the link goes in the place file.
- Each entry is `{url, source, credit, sha256}`. `source` is one of a fixed list; `credit` is needed.
- Removing a photo takes it off the place file only; the picture stays on Cloudinary.
- Photos stay in our place files for now. A later step loads them into the website team's database, once the field differences are agreed.

**Why:** the photos show the place, not one video, so they go in the place file. A fixed public_id per picture means a retry replaces the upload instead of making a copy.

**Risk (the user's choice):** Google Maps photos belong to whoever posted them, and Google's terms don't allow re-hosting them. Every photo keeps `source` and `credit`, so these can be found and swapped later.

**Other options:** photos per clip (rejected: the same place would show different photos per video); store the pictures in git (rejected: the repo would grow fast).

---

## 2026-11-28: One file per place; ids stay numbers until the database

**Decision:**
- One file per place, `data/places/<place_id>.json` (place_id, place_name, aliases, area, google_maps_url, photos). The first 5c run moves the old `data/results/places.json` into these files and deletes it, unless it holds a name, district or link a place file lacks. Stage 6 reads the folder.
- New ids stay counted numbers (`tvna_p_0002`, ...). For a short time ids were made from the Google Maps link, so two computers would not clash; the user dropped that because a database will hand out the ids next.
- Until then, one person runs 5c at a time: `git pull` before, push after.

**Why:** the database is the next step and will give out ids safely; until then, numbered ids are simpler to read.

**Limit:** two people running 5c at once would give the same number to two shops.

---

## 2026-11-27: Fixes from a full review of every stage

**Decision:**

- Stage 4 never drops location words. When a long video is read in parts, every part's `area_description` and its other districts are kept ("also: …"). A word counts as already there only as a whole word ("street 5" is not in "street 51").
- 5c fixes a place's district in `places.json` even when nothing else is new: a Khmer name becomes the English name from `areas.json`, extra spaces go, an old list becomes text. A different district from a clip is reported on every run (so stage 6's warning always has an explanation); "website name stays" is said only once.
- Stage 6 publishes a number typed by hand as text (`5` → `"5"`) with a warning, instead of losing it. 5b lists it as a problem, so the team fixes it first.
- Stages 3 and 4 wait and retry only when Gemini is busy, the connection drops or the answer comes cut off. Any other error (a bug, a certificate problem) stops at once with the real cause, instead of 80 s of retries and "Gemini is busy".

**Why:** a review found each of these could lose data or hide a problem without any message.

## 2026-11-18: Different names for one place: the team links them now, Gemini hints in Capstone 2

**Decision:** when creators call one place by different names, the team links them in 5b: the Maps link of the right place (5c matches by link first), a search of `places.json`, every other name in `place_name_alt`, and a decision on every unclear match after 5c. Giving Gemini the known names as hints (with saving the team's fixes and a test score) moves to Capstone 2.

**Why:** 5c already matches different names through the Maps link, the aliases and close spellings, and asks a person when unsure. The hints need many reviewed clips to learn from and to score; only two clips (one café) are verified so far.

**Other options:** build the hints now (rejected: too few reviewed clips to know if it helps).

## 2026-11-18: One district per place, as text, in every file

**Decision:** `area` is one district as text (e.g. `"Chamkar Mon"`), or `null`, never a list, in clip files, `places.json` and `final_dataset.json`.

- Stage 4: if Gemini names more than one district, the first goes in `area` and the others in `area_description` ("also: …"), so nothing is lost. The same happens when a long video's later part names another district. The Gemini prompt is unchanged (still v5).
- 5b: a list is a problem ("write one district as text").
- 5c: a new place takes the clip's district; an empty one is filled later; a different one is only reported (`another district "…", places.json keeps "…"`). An old `places.json` with a list is read and saved back as text, and the report names any district left out. A hand-typed `area` that is not a district (e.g. "BKK1") is kept until a clip brings a real district; the report then says what it replaced.
- Stage 6: the district in `places.json`, else the first one from the clips; other districts give a warning.
- `data/gemini_answers/` keeps its old shape (never edited).

(Earlier the same day only `final_dataset.json` had changed, and clips accepted both shapes. The user asked for text everywhere.)

**Why:** for now the website shows one district per place. Branches (one place, many branches, each with its own district and Maps link) are planned for Capstone 2.

**Other options:** keep the list (rejected: the website wants one value for now); pick the district named by the most clips (rejected: harder to explain; the first one matches how 5c keeps the first Maps link).

**Note for the website team:** `area` in `data/results/final_dataset.json` is now text or `null`, not a list.

## 2026-11-18: data/ is grouped by what the files are

**Decision:** `areas.json` moved to `data/reference/` (fixed lists, set once). `places.json` and `final_dataset.json` moved to `data/results/` (made by stages 5c and 6). `clips/`, `audio/` and `gemini_answers/` stay as they are.

**Why:** the files sat loose in `data/` next to the folders, so it was hard to see which ones are inputs and which ones the scripts make.

**Note for the website team:** read `data/results/final_dataset.json` (was `data/final_dataset.json`).

## 2026-11-18: A checker for the team review (5b)

**Decision:** `stage5b_validate_clips.py` checks the team's hand edits before stage 5c. It only reads the clip files and never changes them. It lists each place as a problem, to review, or ready, and exits with an error when there is a problem.

**Why:** the first real review (PP-005) had 4 easy mistakes: `"verfied"`, `"7 Makara"`, `"nothing"` instead of `null`, and an edited `missing_fields`. Nothing warned about them until 5c and 6, and the typo alone kept the place off the website without any error.

**Other options:** let 5c refuse such files (rejected: 5c writes files, and a check that changes nothing is safer to run any time); fix mistakes automatically (rejected: a person should see and fix their own edits).

## 2026-11-18: A place not found on Google Maps is held back

**Decision:** if the team can't find a place on Google Maps (so no district and no Maps link), they leave `area` and `google_maps_url` as `null`, write what they tried in `cleaner_note`, and keep `verification_status: "needs_review"`. It is not published and not rejected.

**Why:** the website filters places by district, so a place with no district would be hard to find; and a place nobody could confirm may not exist. Holding it back loses nothing: someone can try again later.

**Other options:** publish without a district (rejected: unconfirmed, and missing from district filters); reject (rejected: the place may be real, just hard to find).

## 2026-11-18: Duplicates are removed in stage 1, before any tokens are spent

**Decision:** stage 1 takes a list of links (`--from-file links.txt`, with `--check-only` to look first). It turns every link into its TikTok video number and compares it with every clip in `data/clips/` and `duplicates/`, and with the links above it. Only new videos get a clip file. The video number is also saved as `source.video_id`. Stage 5a stays as a safety net (e.g. a clip file copied by hand).

**Why:** before, a duplicate could go through stages 2–4 (TikTok download, two Gemini calls) and only then be moved by 5a. That wastes tokens.

**Storage:** no database. The clip JSON files in git are the data; `git pull` first so stage 1 sees the team's clips. A database is worth it only with many thousands of clips or many people adding links at the same time.

**Other options:** check duplicates only in 5a (rejected: tokens already spent); a separate "clean the list" script (rejected: one more command to remember; stage 1 already reads every clip).

## 2026-11-17: Only verified places get a place_id and reach the website

**Decision:** stage 5c matches or creates a place only when the team set `"verification_status": "verified"` in 5b. Every other status (`needs_review`, `auto_added`, empty, a typo) is listed as "waiting for review", and nothing changes for it. Stage 6 also publishes only `verified` places; one with a `place_id` that isn't verified is left out with a warning.

**Why:** 5c names a new place after its clip, and that name goes to the website. Before this, 5c also created places from unchecked clips, so a name Gemini got wrong could become the website name.

**Other options:** let stage 6 warn about unchecked names but still publish them (rejected: the wrong name would still be shown).

## 2026-11-17: Stage 4 uses the TikTok caption (prompt v5)

**Decision:** stage 4 reads the transcript and the caption.

- `place_name` = the English name if one is said or written, otherwise the Khmer name. When the caption writes that name, the caption's spelling is used. (Real runs: a first draft of v5 kept PP-002's spoken "Hanjang Coffee & Eatery" as the name when the caption wrote the shorter "Hanjan Coffee". After adding `name_source` (Gemini says where the name came from), the caption's "Hanjan Coffee" became the name and the spoken one went to `place_name_alt`.)
- `place_name_alt` = every other name said or written, including the misheard spelling (e.g. "ALWAYS selfie booth" when the caption says "Luv selfie booth").
- A place named only in the caption counts. It gets the flag `name_from_caption`. A place the transcript doesn't back up is never `auto_added`.
- A "name" that is only @accounts or #hashtags is kept but `rejected` (flag `name_is_tag`). The prompt's example is made up (not one of our clips), so it can't help a clip score well later.
- A `[no speech]` clip with a caption is read from its caption.
- Stage 4 refuses a clip whose caption hasn't been read yet (missing or `""`), so the caption is never skipped by accident.

**Why:** speech-to-text mishears names; the creator types the caption, so its spelling is usually right. Keeping every other name means nothing is lost, and the team picks the final name in 5b.

**Other options:** let stage 3 spell names from the caption (see the next decision); use only the transcript (keeps misheard names).

## 2026-11-17: Stage 3 stays audio only

**Decision:** stage 3 does not get the caption. (Plan step B was built, then undone.)

**Why:** with the caption, stage 3 wrote the caption's spelling, so the heard spelling disappeared from the transcript. Stage 4 then couldn't keep it in `place_name_alt`.

**Lesson:** every plan now follows one real clip through all stages (in "Coming next", Capstone 2).

## 2026-11-17: One name on the website

**Decision:** `final_dataset.json` gets one `place_name` per place, with no `place_name_alt` (plan step D, done). Other names stay as `aliases` in `places.json`, for matching future clips.

**Names compared:** the clip's `place_name` and every `place_name_alt` are compared with each place's `place_name` and every `aliases` entry in places.json.

- The published name is `place_name` in places.json. Stage 5c sets it from the clip that creates the place, so the team picks the right name in 5b before 5c. To change it later, edit places.json; the old name is already in `aliases`.
- An empty name is published as `null` with a warning. Stage 6 never takes an alias instead, because an alias may be a misheard name.
- When a clip calls a known place something else, 5c says once which name the website keeps (`website name stays "…"`). A stage 6 warning on every run was tried first, but it fired for every correct Khmer name or other spelling, so it was dropped.
- 5c creates places only from `verified` clips (decision above), so the name the team approved is the one published.

**Why:** a misheard name like "ALWAYS selfie booth" helps matching but must not be shown to visitors.

**Note for the website team:** the `place_name_alt` field is gone from `final_dataset.json`.

## 2026-11-17: Caption now, counts later

**Decision:** stage 2 saves only the caption for now. View, like, comment and share counts are for Capstone 2.

## 2026-11-17: Checks before every push

**Decision:**

- Every "skip if already done" check is tested with filled, `null`, `""` and a missing key. Running twice must change nothing and make no TikTok or Gemini call.
- `python tests/run_all.py` must pass.
- A code review runs on the changes. The report says what it found and what was fixed.

**Why:** a stage 2 bug (a saved `null` caption asked TikTok again on every run) got past tests that only used filled values.
