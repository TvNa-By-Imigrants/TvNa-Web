# TVNA pipeline: decisions

Key choices and why, newest first. Older decisions (before 2026-11-17) are still only in the README and the field guide. TODO: move them here.

---

## 2026-11-28: Several people can run 5c at once (ids from the Maps link, one file per place)

**Decision:**
- A new place's id comes from the place code in its Google Maps link: `tvna_p_` + 10 letters and numbers (the start of a SHA-256 of `maps_key()`). The same shop gets the same id on every computer. Old ids (`tvna_p_0001`) stay.
- A place with no readable Maps link gets no new id: 5c lists it as unclear ("add the Share link" or "run again online"). 5b already asks for the link on every `verified` place.
- One file per place, `data/places/<place_id>.json` (place_id, place_name, aliases, area, google_maps_url, photos). The first 5c run moves the old `data/results/places.json` into these files and deletes it; git keeps its history. Stage 6 reads the folder.
- Team rule: each person runs 5c on their own clips, right after `git pull`, and pushes right after.

**Why:** with numbered ids, two people running 5c at once both gave `tvna_p_0005` to two different shops, and everyone edited the same `places.json`. Now ids can't clash, and people working on different places never touch the same file.

**Limits:** two people adding a name to the **same** place at the same moment still get a git conflict in that one small file (keep both names). Two different kinds of Maps link for one shop (a `cid=` link and a place link) can give two ids; 5c then sees the same name and asks (unclear).

**Other options:** a database or a server that hands out ids (we have neither: the data is JSON in git); one person runs all matching (a bottleneck for ~100 clips).

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
