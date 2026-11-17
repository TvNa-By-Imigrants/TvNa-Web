"""Offline checks for stage6_build_final_dataset.py: every kind of value (filled, null, "", missing), run twice."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

PIPE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPE))
import stage6_build_final_dataset as s6  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="tvna-test-"))
CLIPS = WORK / "clips"
CLIPS.mkdir(parents=True)
PLACES, OUT = WORK / "places.json", WORK / "final_dataset.json"
MISSING = object()

results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     {detail}"))

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def write(p, data):
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def drop_missing(d):
    return {k: v for k, v in d.items() if v is not MISSING}

def place(**over):
    return drop_missing(dict(place_id=None, place_name="Tea Kingdom", place_name_alt=[], category="cafe",
                             area=None, speaker_opinion="Good tea", verification_status="needs_review") | over)

def clip(name, places, creator="@tester", fields_value=MISSING, source=MISSING):
    c = load(PIPE / "templates/tvna_clip_template.json")
    c["clip_id"] = name
    c["source"]["creator"] = creator
    if creator is MISSING:
        del c["source"]["creator"]
    if source is not MISSING:
        c["source"] = source
    c["fields"] = places if fields_value is MISSING else fields_value
    p = CLIPS / f"{name}.json"
    write(p, c)
    return p

def run():
    sys.argv = ["stage6_build_final_dataset.py", *sorted(map(str, CLIPS.glob("*.json"))),
                "--places", str(PLACES), "--output", str(OUT)]
    out, code = io.StringIO(), 0
    with contextlib.redirect_stdout(out):
        try:
            s6.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue()

write(PLACES, [
    {"place_id": "tvna_p_0001", "place_name": "Tea Kingdom", "aliases": ["Tea Kingdom", "ធីឃីងដម"],
     "area": ["Tuol Kouk"], "google_maps_url": "https://maps.app.goo.gl/abc123"},
    {"place_id": "tvna_p_0002", "place_name": "Brown Coffee", "aliases": None, "area": None, "google_maps_url": ""},
    {"place_id": "tvna_p_0003", "place_name": "Luv selfie booth", "area": []},
])

# place_id: filled / null / "" / missing / unknown; speaker_opinion: filled / null / "" / missing
clip("PP-001", [place(place_id="tvna_p_0001", area=["tuol kouk", "Toul Kork"], price_range="$1-3"),
                place(place_id="tvna_p_0001", speaker_opinion="")])
clip("PP-002", [place(place_id="tvna_p_0001", speaker_opinion=None)], creator="")
clip("PP-003", [place(place_id="tvna_p_0002", place_name="Brown Coffee", speaker_opinion=MISSING)], creator=None)
clip("PP-004", [place(place_id="tvna_p_0003", place_name="Luv selfie booth", speaker_opinion="")], creator=MISSING)
clip("PP-005", [place(place_id=None), place(place_id=""), place(place_id=MISSING), place(place_id="tvna_p_9999"),
                place(place_id="tvna_p_0002", verification_status="rejected")])
# fields and source: null / "" / missing (stage 4 or stage 1 not run yet)
clip("PP-006", None)
clip("PP-007", None, fields_value="")
clip("PP-008", None, fields_value=None)
clip("PP-009", None, source=None)
clip("PP-010", None, source=MISSING)
c = load(CLIPS / "PP-010.json")
del c["fields"], c["source"]
write(CLIPS / "PP-010.json", c)

code, out = run()
check("1 runs on every kind of value without crashing", code == 0 and OUT.exists(), out)
data = load(OUT) if OUT.exists() else []
rec = {r["place_id"]: r for r in data}
check("2 only places with a known place_id, not rejected", sorted(rec) == ["tvna_p_0001", "tvna_p_0002", "tvna_p_0003"],
      sorted(rec))
check("3 unknown place_id is a warning", "tvna_p_9999 is not in places.json" in out, out)

text = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
check('4 no "" in the output: empty values are null', '""' not in text, text)
r1, r2, r3 = rec.get("tvna_p_0001", {}), rec.get("tvna_p_0002", {}), rec.get("tvna_p_0003", {})
check("5 Maps link: filled kept, \"\" -> null, missing -> null",
      r1.get("google_maps_url") == "https://maps.app.goo.gl/abc123" and r2.get("google_maps_url") is None
      and r3.get("google_maps_url") is None, (r1, r2, r3))
m1 = {m["clip_id"]: m for m in r1.get("mentions", [])}
check('6 speaker_opinion: same place twice in one clip -> one mention; "" left out',
      m1.get("PP-001", {}).get("speaker_opinion") == "Good tea", m1)
check('7 speaker_opinion null / "" / missing -> null',
      m1.get("PP-002", {}).get("speaker_opinion") is None
      and r2.get("mentions", [{}])[0].get("speaker_opinion", "x") is None
      and r3.get("mentions", [{}])[0].get("speaker_opinion", "x") is None, (m1, r2, r3))
check('8 creator "" / null / missing -> null, not counted in popularity, warned',
      m1.get("PP-002", {}).get("creator") is None and r1.get("popularity") == 1 and r2.get("popularity") == 0
      and r3.get("popularity") == 0 and r3.get("mentions", [{}])[0].get("creator", "x") is None
      and all(f"PP-00{n}.json: no creator" in out for n in (2, 3, 4)), (r1, out))
check("9 lists: values from every clip, no repeats, areas only real districts",
      r1.get("price_range") == ["$1-3"] and r1.get("category") == ["cafe"] and r1.get("area") == ["Tuol Kouk"]
      and "area 'Toul Kork' is not a district" in out, (r1, out))

raw_out = OUT.read_bytes() if OUT.exists() else b""
raw_in = {p: p.read_bytes() for p in [PLACES, *CLIPS.glob("*.json")]}
code2, out2 = run()
check("R 2nd run: same output byte for byte, no clip or places.json changed",
      code2 == 0 and OUT.read_bytes() == raw_out and all(p.read_bytes() == b for p, b in raw_in.items()), out2)
check("R 2nd run: same report", out2 == out, (out, out2))

# S. hand-edited values
write(PLACES, [{"place_id": "tvna_p_0001", "place_name": "Tea Kingdom", "aliases": ["", None, "Tea Kingdom", "TK"],
                "area": [], "google_maps_url": None},
               {"place_id": "tvna_p_0002", "place_name": "Brown Coffee", "aliases": "Brown", "area": []}])
for f in CLIPS.glob("*.json"):
    f.unlink()
for n, creator in [(1, "@a"), (2, "@b"), (3, "   ")]:
    c = clip(f"PP-1{n:02d}", [place(place_id="tvna_p_0001"), place(place_id="tvna_p_0002", place_name="Brown Coffee")],
             creator=creator)
    d = load(c)
    d["clip_id"] = None if n < 3 else ""  # broken clip files: no clip_id
    write(c, d)
code, out = run()
rec = {r["place_id"]: r for r in load(OUT)} if OUT.exists() else {}
r1, r2 = rec.get("tvna_p_0001", {}), rec.get("tvna_p_0002", {})
check('S1 aliases with "" / null / a typed text: left out, kept whole', r1.get("place_name_alt") == ["TK"]
      and r2.get("place_name_alt") == ["Brown"], (r1, r2))
check("S2 clips with no clip_id stay separate mentions (file name used), popularity counts both creators",
      [m["clip_id"] for m in r1.get("mentions", [])] == ["PP-101", "PP-102", "PP-103"] and r1.get("popularity") == 2,
      r1)
m3 = next((m for m in r1.get("mentions", []) if m["clip_id"] == "PP-103"), {})
check('S3 creator of only spaces -> null, warned, not counted',
      "creator" in m3 and m3["creator"] is None and "PP-103.json: no creator" in out, (r1, out))

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
