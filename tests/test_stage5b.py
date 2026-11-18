"""Offline checks for stage5b_validate_clips.py: every mistake it must catch, every kind of value
(filled, null, "", missing), broken files, read-only, run twice."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

PIPE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPE))
import stage5b_validate_clips as s5b  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="tvna-test-"))
MISSING = object()

results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     {detail}"))

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def good_place(**changes):
    """A verified place with no problems; changes set fields (MISSING deletes the key)."""
    p = load(PIPE / "templates/tvna_clip_place_template.json")
    p.update(place_name="Beans Barley", category="cafe", area=["Prampi Makara"], speaker_opinion="Good coffee.",
             google_maps_url="https://maps.app.goo.gl/83k2NQZKFZm3d2Dj8", completeness=1.0, missing_fields=[],
             verification_status="verified", cleaned_by="panha", cleaner_note=None, notes=None)
    for key, value in changes.items():
        if value is MISSING:
            p.pop(key, None)
        else:
            p[key] = value
    return p

def clip_file(name, places=MISSING, raw=None, folder=None):
    folder = folder or WORK / "clips"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
        return path
    c = load(PIPE / "templates/tvna_clip_template.json")
    c["clip_id"] = name
    if places is MISSING:
        del c["fields"]
    else:
        c["fields"] = places
    path.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def run(*paths):
    sys.argv = ["stage5b_validate_clips.py", *map(str, paths)]
    out, code = io.StringIO(), 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            s5b.main()
        except SystemExit as e:
            code = 0 if e.code is None else e.code if isinstance(e.code, int) else 1
            if not isinstance(e.code, int) and e.code is not None:
                out.write(str(e.code))
        except Exception:
            code = "CRASH"
            out.write(traceback.format_exc())
    return code, out.getvalue()

def one(place, name="PP-001"):
    """Run on a single clip with one place; returns (exit code, output)."""
    folder = WORK / f"one-{len(results)}"
    return run(clip_file(name, [place], folder=folder))

# 1. a correct verified place
code, out = one(good_place())
check("1 correct verified place: ready, no problems, exit 0, says the 5c command",
      code == 0 and "problems (0)" in out and "ready (1)" in out and 'PP-001.json  "Beans Barley"' in out
      and "Next: python stage5c_match_places.py" in out, out)
for url in ["https://maps.app.goo.gl/abc", "https://www.google.com/maps/place/Beans/@11.5,104.9",
            "https://google.com/maps?cid=123", "https://maps.google.com/?cid=1", "https://goo.gl/maps/xyz"]:
    code, out = one(good_place(google_maps_url=url))
    check(f"1 Maps link accepted: {url}", code == 0 and "ready (1)" in out, out)
code, out = one(good_place(area=["ប្រាំពីរមករា"]))
check("1 Khmer district name accepted", code == 0 and "ready (1)" in out, out)

# 2. status: typo, null, "", missing, not text
code, out = one(good_place(verification_status="verfied"))
check('2 status "verfied": problem, suggests "verified", exit 1, says nothing was changed',
      code == 1 and 'verification_status "verfied" is not a status' in out and 'Did you mean "verified"?' in out
      and "Nothing was changed" in out and "ready (0)" in out, out)
for kind, value in [("null", None), ('""', ""), ("missing", MISSING), ("a number", 5), ("Verified", "Verified")]:
    code, out = one(good_place(verification_status=value))
    check(f"2 status {kind}: problem, no crash", code == 1 and "is not a status" in out, out)

# 3. text that should be null
for value in ["nothing", "", "N/A", " none ", "Unknown", "null", "-"]:
    code, out = one(good_place(notes=value))
    check(f"3 notes {value!r}: write null", code == 1 and "notes: write null, not" in out, out)
code, out = one(good_place(menu_items=["Latte", ""]))
check('3 "" inside a list (menu_items): write null', code == 1 and "menu_items: write null" in out, out)
code, out = one(good_place(cleaner_note=""))
check('3 cleaner_note "": write null', code == 1 and "cleaner_note: write null" in out, out)
code, out = one(good_place(notes="Opens late on weekends", speaker_opinion="Nothing special, but cheap."))
check("3 real text that starts with 'nothing' or mentions it: fine", code == 0, out)

# 4. area
code, out = one(good_place(area=["7 Makara"]))
check('4 area "7 Makara": not a district, suggests "Prampi Makara"',
      code == 1 and 'area "7 Makara" is not one of the 14 districts' in out and 'Did you mean "Prampi Makara"?' in out, out)
code, out = one(good_place(area="Prampi Makara"))
check('4 area as text, not a list: says write ["…"]',
      code == 1 and 'area must be a list, e.g. ["Prampi Makara"]' in out, out)
code, out = one(good_place(area=["Boeung Keng Kang"]))
check("4 area misspelled district: problem + suggestion",
      code == 1 and 'Did you mean "Boeng Keng Kang"?' in out, out)
code, out = one(good_place(area=["Prampi Makara", "Daun Penh"]))
check("4 two districts (branches): fine", code == 0, out)

# 5. category, Maps link, missing_fields
code, out = one(good_place(category="Cafe"))
check('5 category "Cafe": not in the list, suggests "cafe"', code == 1 and 'Did you mean "cafe"?' in out, out)
code, out = one(good_place(category=None))
check("5 category null: fine", code == 0, out)
for url in ["https://www.youtube.com/watch?v=1", "maps.app.goo.gl/abc", "https://www.google.com/search?q=cafe",
            "https://example.com/maps/place/x", "ftp://maps.app.goo.gl/abc"]:
    code, out = one(good_place(google_maps_url=url))
    check(f"5 not a Maps link ({url}): problem", code == 1 and "is not a Google Maps link" in out, out)
code, out = one(good_place(completeness=0.67, missing_fields=[]))
check("5 missing_fields edited to [] while completeness is 0.67: problem",
      code == 1 and "doesn't match completeness 0.67" in out, out)
code, out = one(good_place(completeness=0.67, missing_fields=["area"]))
check("5 missing_fields matches completeness: fine", code == 0, out)
code, out = one(good_place(completeness=MISSING, missing_fields=MISSING))
check("5 completeness and missing_fields missing: no crash, fine", code == 0, out)

# 6. verified needs name, reviewer, district, Maps link (null, "", missing)
for field, words in [("place_name", "place_name is empty"), ("cleaned_by", "cleaned_by is empty"),
                     ("area", "area is empty"), ("google_maps_url", "google_maps_url is empty")]:
    for kind, value in [("null", None), ("missing", MISSING)] + ([("[]", [])] if field == "area" else []):
        code, out = one(good_place(**{field: value}))
        check(f"6 verified, {field} {kind}: problem", code == 1 and f"verified, but {words}" in out, out)
code, out = one(good_place(area=None))
check("6 verified with no district: says keep needs_review if not found on Maps",
      "Keep needs_review (team rule)" in out, out)

# 7. waiting places: to review, with what is left
code, out = one(good_place(verification_status="needs_review", area=None, google_maps_url=None, cleaned_by=None,
                           completeness=0.67, missing_fields=["area"], flags=["name_from_caption"]))
check("7 needs_review: to review, lists what to fill and the flags, exit 0",
      code == 0 and "to review (1)" in out
      and "(needs_review): fill area, google_maps_url; check flags: name_from_caption" in out, out)
code, out = one(good_place(verification_status="auto_added", flags=[], cleaned_by=None))
check("7 auto_added with district and Maps link: to review, says what to do next",
      code == 0 and '(auto_added): district and Maps link filled: check it, then your name in cleaned_by and "verified"' in out, out)
code, out = one(good_place(verification_status="needs_review", area=None, google_maps_url=None,
                           completeness=0.67, missing_fields=["area"], cleaner_note=None))
check("7 cleaned_by filled, still needs_review, no cleaner_note: problem (held back without a reason?)",
      code == 1 and "say why in cleaner_note" in out, out)
code, out = one(good_place(verification_status="needs_review", area=None, google_maps_url=None,
                           completeness=0.67, missing_fields=["area"], cleaner_note="Not found on Google Maps"))
check("7 held back with a cleaner_note: to review, shows the reason",
      code == 0 and "held back: Not found on Google Maps" in out, out)

# 8. rejected places are counted, not listed
code, out = one(good_place(verification_status="rejected", place_name=None, area=None, google_maps_url=None,
                           cleaned_by=None, completeness=0.0, missing_fields=["place_name", "area", "speaker_opinion"]))
check("8 rejected: counted, not a problem", code == 0 and "rejected (1)" in out and "problems (0)" in out, out)

# 9. files: fields null / missing / [] / not a list, a place not an object, broken JSON, a list file
F = WORK / "files"
paths = [clip_file("PP-001", None, folder=F), clip_file("PP-002", folder=F), clip_file("PP-003", [], folder=F),
         clip_file("PP-004", "x", folder=F), clip_file("PP-005", ["x"], folder=F),
         clip_file("PP-006", raw='{"clip_id": "PP-006", "fields": [ {"place_name": "A",} ]}', folder=F),
         clip_file("PP-007", raw="[]", folder=F), clip_file("PP-008", [good_place()], folder=F)]
before = {p: p.read_bytes() for p in F.glob("*.json")}
code, out = run(*paths)
check("9 fields null or missing: 'not at stage 4 yet (2 clips)'; [] is fine", "not at stage 4 yet (2 clips)" in out, out)
check("9 fields not a list / a place not an object / list file: problems, no crash",
      code == 1 and "PP-004.json\n    - fields must be a list" in out and "PP-005.json\n    - a place in fields is not an object" in out
      and "PP-007.json\n    - not a clip file" in out, out)
check("9 broken JSON: problem names the file and the line, the other files are still checked",
      "PP-006.json\n    - can't read the file:" in out and "line 1" in out and "ready (1)" in out, out)
check("9 read-only: no file changed", {p: p.read_bytes() for p in F.glob("*.json")} == before, out)
code2, out2 = run(*paths)
check("9 run twice: same output, still nothing changed",
      (code2, out2) == (code, out) and {p: p.read_bytes() for p in F.glob("*.json")} == before, out2)
code, out = run(F / "PP-099.json", F / "PP-008.json")
check("9 a file that doesn't exist: problem, the rest still checked",
      code == 1 and "PP-099.json\n    - can't read the file" in out and "ready (1)" in out, out)

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
