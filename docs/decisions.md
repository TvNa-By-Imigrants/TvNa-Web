# TVNA pipeline: decisions

Key choices and why, newest first. Older decisions (before 2026-11-17) are still only in the README and the field guide. TODO: move them here.

---

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

**Lesson:** every plan now follows one real clip through all stages (in "Coming next", next milestone).

## 2026-11-17: One name on the website

**Decision:** `final_dataset.json` gets one `place_name` per place, with no `place_name_alt` (plan step D). Other names stay as `aliases` in `places.json`, for matching future clips.

**Why:** a misheard name like "ALWAYS selfie booth" helps matching but must not be shown to visitors.

## 2026-11-17: Caption now, counts later

**Decision:** stage 2 saves only the caption for now. View, like, comment and share counts are for the next milestone.

## 2026-11-17: Checks before every push

**Decision:**

- Every "skip if already done" check is tested with filled, `null`, `""` and a missing key. Running twice must change nothing and make no TikTok or Gemini call.
- `python tests/run_all.py` must pass.
- A code review runs on the changes. The report says what it found and what was fixed.

**Why:** a stage 2 bug (a saved `null` caption asked TikTok again on every run) got past tests that only used filled values.
