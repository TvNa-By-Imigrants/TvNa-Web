"""Offline checks for stage6_build_final_dataset.py: every kind of value (filled, null, "", missing), run twice."""
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
import stage6_build_final_dataset as s6  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="tvna-test-"))
CLIPS = WORK / "clips"
CLIPS.mkdir(parents=True)
PLACES, OUT = WORK / "places", WORK / "final_dataset.json"
MISSING = object()

results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     {detail}"))

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def write(p, data):
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

PHOTO = {"url": "https://res.cloudinary.com/t/image/upload/v1/tvna/places/p.jpg", "source": "Google Maps",
         "credit": "Dara S.", "sha256": "a" * 64}

def write_places(entries):
    """One file per place, as stage 5c makes them (with one photo, as 5d adds it, unless photos is given);
    old files are removed first."""
    shutil.rmtree(PLACES, ignore_errors=True)
    PLACES.mkdir()
    for e in entries:
        write(PLACES / f"{e['place_id']}.json", e if "photos" in e else e | {"photos": [PHOTO]})

def drop_missing(d):
    return {k: v for k, v in d.items() if v is not MISSING}

def place(**over):
    return drop_missing(dict(place_id=None, place_name="Tea Kingdom", place_name_alt=[], category="cafe",
                             area=None, speaker_opinion="Good tea", verification_status="verified") | over)

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
                "--places-dir", str(PLACES), "--output", str(OUT)]
    out, code = io.StringIO(), 0
    with contextlib.redirect_stdout(out):
        try:
            s6.main()
        except SystemExit as e:
            if e.code is None or isinstance(e.code, int):
                code = e.code or 0
            else:  # sys.exit("message"): Python prints it and exits with 1
                out.write(str(e.code))
                code = 1
        except Exception:
            code = "crashed"
            out.write(traceback.format_exc())
    return code, out.getvalue()

write_places([
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
check("3 unknown place_id is a warning", "tvna_p_9999 has no place file, so not published" in out, out)

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
check("9 lists: values from every clip, no repeats; area is one real district, null when none",
      r1.get("price_range") == ["$1-3"] and r1.get("category") == ["cafe"] and r1.get("area") == "Tuol Kouk"
      and r2.get("area", "x") is None and r3.get("area", "x") is None
      and "area 'Toul Kork' is not a district" in out and "more than one district" not in out, (r1, r2, r3, out))

# D. one name per place on the website
template = load(PIPE / "templates/tvna_final_dataset_template.json")[0]
check("D1 one name: place_name from places.json, no place_name_alt, aliases not published",
      r1.get("place_name") == "Tea Kingdom" and all("place_name_alt" not in r and "aliases" not in r for r in data)
      and "ធីឃីងដម" not in text, r1)
check("D2 every record has exactly the template's keys, in the same order",
      bool(data) and all(list(r) == list(template) for r in data)
      and all(list(m) == list(template["mentions"][0]) for r in data for m in r["mentions"]),
      (list(template), [list(r) for r in data]))

raw_out = OUT.read_bytes() if OUT.exists() else b""
raw_in = {p: p.read_bytes() for p in [*PLACES.glob("*.json"), *CLIPS.glob("*.json")]}
code2, out2 = run()
check("R 2nd run: same output byte for byte, no clip or places.json changed",
      code2 == 0 and OUT.read_bytes() == raw_out and all(p.read_bytes() == b for p, b in raw_in.items()), out2)
check("R 2nd run: same report", out2 == out, (out, out2))

# S. hand-edited values
write_places([{"place_id": "tvna_p_0001", "place_name": "Tea Kingdom", "aliases": ["", None, "Tea Kingdom", "TK"],
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
check('S1 aliases with "" / null / a typed text: no crash, never published',
      code == 0 and r1.get("place_name") == "Tea Kingdom" and r2.get("place_name") == "Brown Coffee"
      and "place_name_alt" not in r1 and "aliases" not in r1 and "TK" not in OUT.read_text(encoding="utf-8"), (r1, r2))
check("S2 clips with no clip_id stay separate mentions (file name used), popularity counts both creators",
      [m["clip_id"] for m in r1.get("mentions", [])] == ["PP-101", "PP-102", "PP-103"] and r1.get("popularity") == 2,
      r1)
m3 = next((m for m in r1.get("mentions", []) if m["clip_id"] == "PP-103"), {})
check('S3 creator of only spaces -> null, warned, not counted',
      "creator" in m3 and m3["creator"] is None and "PP-103.json: no creator" in out, (r1, out))

# N. place_name in places.json edited by hand: filled with spaces / null / "" / missing / a list / a number
for f in CLIPS.glob("*.json"):
    f.unlink()
names = {"tvna_p_0001": " Tea Kingdom ", "tvna_p_0002": None, "tvna_p_0003": "", "tvna_p_0004": MISSING,
         "tvna_p_0005": ["Wat Botum Park"], "tvna_p_0006": 5}
nameless = ("tvna_p_0002", "tvna_p_0003", "tvna_p_0004", "tvna_p_0005", "tvna_p_0006")
write_places([drop_missing({"place_id": i, "place_name": n, "aliases": ["Old Name"], "area": []}) for i, n in names.items()])
clip("PP-201", [place(place_id=i) for i in names])
code, out = run()
rec = {r["place_id"]: r for r in load(OUT)} if OUT.exists() else {}
check("N1 place_name with spaces is trimmed",
      code == 0 and rec.get("tvna_p_0001", {}).get("place_name") == "Tea Kingdom", (code, out, rec))
check('N2 place_name null / "" / missing / a list / a number: no crash, null (not an alias), warned',
      code == 0 and all(i in rec and rec[i]["place_name"] is None for i in nameless)
      and all(f"{i}: no place_name in its place file" in out for i in nameless)
      and "Old Name" not in OUT.read_text(encoding="utf-8") and "tvna_p_0001: no place_name" not in out, (out, rec))
raw_out = OUT.read_bytes()
code2, out2 = run()
check("N3 2nd run: same output and report", code2 == 0 and OUT.read_bytes() == raw_out and out2 == out, out2)

# W. spaces-only text, repeated opinions, a name the team checked that differs from places.json
for f in CLIPS.glob("*.json"):
    f.unlink()
write_places([{"place_id": "tvna_p_0001", "place_name": "Luv selfie booth", "aliases": ["ALWAYS selfie booth"],
                "area": [], "google_maps_url": "   "},
               {"place_id": "tvna_p_0002", "place_name": "Brown Coffee", "area": [], "google_maps_url": 7}])
clip("PP-301", [place(place_id="tvna_p_0001", speaker_opinion="Good tea"),
                place(place_id="tvna_p_0001", speaker_opinion=" good  TEA "),
                place(place_id="tvna_p_0001", speaker_opinion="Nice staff")], creator=" @a ")
clip("PP-302", [place(place_id="tvna_p_0002", place_name="Brown Coffee", speaker_opinion="   ")], creator=5)
clip("PP-303", [place(place_id="tvna_p_0001", place_name="ALWAYS selfie booth", verification_status="verified"),
                place(place_id="tvna_p_0001", place_name="ALWAYS selfie booth", verification_status="verified")])
clip("PP-304", [place(place_id="tvna_p_0001", place_name="Always Selfie-Booth", verification_status="needs_review")])
clip("PP-305", [place(place_id="tvna_p_0001", place_name="LUV Selfie Booth", verification_status="verified")])
code, out = run()
rec = {r["place_id"]: r for r in load(OUT)} if OUT.exists() else {}
r1, r2 = rec.get("tvna_p_0001", {}), rec.get("tvna_p_0002", {})
m1 = {m["clip_id"]: m for m in r1.get("mentions", [])}
check("W1 Maps link of only spaces, or a number: null",
      code == 0 and r1.get("google_maps_url") is None and r2.get("google_maps_url") is None, (code, out, r1, r2))
check("W2 opinion of only spaces -> null; creator with spaces trimmed; creator typed as a number -> null",
      r2.get("mentions", [{}])[0].get("speaker_opinion", "x") is None and m1.get("PP-301", {}).get("creator") == "@a"
      and r2.get("mentions", [{}])[0].get("creator", "x") is None, (r1, r2))
check("W3 same place twice in one clip: the same opinion is not repeated, a different one is joined",
      m1.get("PP-301", {}).get("speaker_opinion") == "Good tea; Nice staff", m1.get("PP-301"))
check("W4 verified clips with other spellings: published under the places.json name, no warning (5c says it once)",
      r1.get("place_name") == "Luv selfie booth" and "PP-303.json" not in out and "PP-305.json" not in out
      and {"PP-303", "PP-305"} <= set(m1), (out, m1))
check("W5 unchecked clip: left out, warned once with its status",
      out.count('PP-304.json "Always Selfie-Booth": verification_status "needs_review", not verified by the team, '
                'left out') == 1 and "PP-304" not in m1, out)
raw_out = OUT.read_bytes() if OUT.exists() else b""
code2, out2 = run()
check("W6 2nd run: same output and report", code2 == 0 and OUT.read_bytes() == raw_out and out2 == out, out2)

# V. only places the team approved (verified) are published
for f in CLIPS.glob("*.json"):
    f.unlink()
write_places([{"place_id": "tvna_p_0001", "place_name": "Tea Kingdom", "aliases": [], "area": []}])
clip("PP-501", [place(place_id="tvna_p_0001", speaker_opinion="Checked")], creator="@ok")
for i, status in enumerate(["needs_review", "auto_added", None, "", MISSING, "Verified"], start=2):
    clip(f"PP-50{i}", [place(place_id="tvna_p_0001", verification_status=status, speaker_opinion="Not checked")],
         creator=f"@c{i}")
clip("PP-509", [place(place_id=None, verification_status="needs_review")], creator="@n")
code, out = run()
rec = {r["place_id"]: r for r in load(OUT)} if OUT.exists() else {}
r1 = rec.get("tvna_p_0001", {})
shown = ['"needs_review"', '"auto_added"', "null", '""', "null", '"Verified"']
check('V1 status needs_review / auto_added / null / "" / missing / a typo: left out, warned with the status; '
      "verified published",
      code == 0 and [m["clip_id"] for m in r1.get("mentions", [])] == ["PP-501"] and r1.get("popularity") == 1
      and all(f'PP-50{i}.json "Tea Kingdom": verification_status {shown[i - 2]}, not verified by the team, left out'
              in out for i in range(2, 8))
      and "Not checked" not in OUT.read_text(encoding="utf-8"), (out, r1))
check("V2 places with no place_id: counted in one line (5c lists them), not one by one",
      "1 place has no place_id yet, so not published. Stage 5c lists them" in out and "PP-509" not in out, out)
raw_out = OUT.read_bytes()
code2, out2 = run()
check("V3 2nd run: same output and report", code2 == 0 and OUT.read_bytes() == raw_out and out2 == out, out2)

for f in CLIPS.glob("*.json"):
    f.unlink()
clip("PP-601", [place(place_id="tvna_p_0001", verification_status="needs_review"),
                place(place_id="tvna_p_0001", verification_status="needs_review")], creator=None)
clip("PP-602", [place(place_id=None, verification_status="rejected")], creator="")
code, out = run()
check("V4 same unchecked place twice in one clip: warned once",
      out.count('PP-601.json "Tea Kingdom": verification_status "needs_review"') == 1, out)
check("V5 no creator warning for a clip with nothing published; a rejected place is not counted as missing an id",
      "no creator" not in out and "no place_id yet" not in out, out)

# A. area: one district per place (branches: next milestone)
for f in CLIPS.glob("*.json"):
    f.unlink()
write_places([drop_missing(e) for e in [
    {"place_id": "tvna_p_0001", "place_name": "Tea Kingdom", "area": "Chamkar Mon"},
    {"place_id": "tvna_p_0002", "place_name": "Brown Coffee", "area": []},
    {"place_id": "tvna_p_0003", "place_name": "Luv selfie booth", "area": None},
    {"place_id": "tvna_p_0004", "place_name": "Beans Barley", "area": MISSING}]])
clip("PP-701", [place(place_id="tvna_p_0001", area="Daun Penh"),
                place(place_id="tvna_p_0002", place_name="Brown Coffee", area="Sen Sok"),
                place(place_id="tvna_p_0003", place_name="Luv selfie booth", area="Daun Penh"),
                place(place_id="tvna_p_0004", place_name="Beans Barley", area="BKK1")])
clip("PP-702", [place(place_id="tvna_p_0002", place_name="Brown Coffee", area=["Daun Penh", "sen sok"])])
code, out = run()
rec = {r["place_id"]: r for r in load(OUT)} if OUT.exists() else {}
area = {k: r.get("area", "x") for k, r in rec.items()}
check("A1 area is one district (text), never a list",
      code == 0 and all(isinstance(a, str) or a is None for a in area.values()), area)
check("A2 places.json district comes first; a different clip district is warned, not shown",
      area.get("tvna_p_0001") == "Chamkar Mon"
      and "tvna_p_0001: more than one district ['Chamkar Mon', 'Daun Penh'], the website shows 'Chamkar Mon'" in out,
      (area, out))
check("A3 places.json area [] / null: the first clip district; two districts across clips warned once",
      area.get("tvna_p_0002") == "Sen Sok" and area.get("tvna_p_0003") == "Daun Penh"
      and out.count("tvna_p_0002: more than one district ['Sen Sok', 'Daun Penh']") == 1
      and "tvna_p_0003: more than one district" not in out, (area, out))
check("A4 places.json area missing, clip has only a non-district: area null, warned",
      area.get("tvna_p_0004", "x") is None and "tvna_p_0004: area 'BKK1' is not a district" in out, (area, out))
bad = clip("PP-703", [place(place_id="tvna_p_0002", place_name="Brown Coffee", area=["Sen Sok", 7])])
code_bad, out_bad = run()
check("A6 area typed as a number: no crash, warned, left out",
      code_bad == 0 and "tvna_p_0002: area '7' is not a district" in out_bad and "area 7 is not text" not in out_bad, out_bad)
bad.unlink()
bad = clip("PP-704", [place(place_id="tvna_p_0002", place_name="Brown Coffee", area=True),
                      place(place_id="tvna_p_0003", place_name="Luv selfie booth", area={"d": 1})])
code_bad, out_bad = run()
check("A7 area typed as true / {...}: no crash, left out with a warning (not silently)",
      code_bad == 0 and 'PP-704.json "Brown Coffee": area true is not text, left out' in out_bad
      and 'PP-704.json "Luv selfie booth": area {"d": 1} is not text, left out' in out_bad, out_bad)
bad.unlink()
code, out = run()
raw_out = OUT.read_bytes() if OUT.exists() else b""
code2, out2 = run()
check("A5 2nd run: same output and report", code2 == 0 and OUT.read_bytes() == raw_out and out2 == out, out2)

# B. values typed by hand that are not text: never lost or joined without a word
for f in CLIPS.glob("*.json"):
    f.unlink()
write_places([{"place_id": "tvna_p_0001", "place_name": "Tea Kingdom", "area": "Chamkar Mon"}])
clip("PP-801", [place(place_id="tvna_p_0001", price_range=5, menu_items=["milk tea", 2, True, {"x": 1}])])
clip("PP-802", [place(place_id="tvna_p_0001", price_range=10, opening_hours=7.5)], creator="@other")
code, out = run()
r = load(OUT)[0] if OUT.exists() and load(OUT) else {}
check("B1 numbers typed in two clips (5 and 10): both kept as text, not joined into one",
      code == 0 and r.get("price_range") == ["5", "10"] and r.get("opening_hours") == ["7.5"], r)
check("B2 the clips-disagree warning still shows", "clips disagree on price_range: ['5', '10']" in out, out)
check("B3 each value that is not text is warned with its clip",
      'PP-801.json "Tea Kingdom": price_range 5 is not text, published as "5"' in out
      and 'PP-802.json "Tea Kingdom": price_range 10 is not text, published as "10"' in out, out)
check("B4 true / {...} in a list: left out and warned; the number kept as text",
      r.get("menu_items") == ["milk tea", "2"] and "menu_items true is not text, left out" in out
      and 'menu_items {"x": 1} is not text, left out' in out, (r, out))
raw_out = OUT.read_bytes()
code2, out2 = run()
check("B5 2nd run: same output and report", code2 == 0 and OUT.read_bytes() == raw_out and out2 == out, out2)

# P. photos (from stage 5d) and each mention's video and cover links
for f in CLIPS.glob("*.json"):
    f.unlink()
two = [dict(PHOTO, url="https://res.cloudinary.com/t/2.jpg", credit="  Beans Barley page ", source="Shop's own page",
            sha256="b" * 64), PHOTO]
write_places([drop_missing({"place_id": f"tvna_p_000{i}", "place_name": n, "area": "Chamkar Mon", "photos": ph})
              for i, n, ph in [(1, "Two Photos", two), (2, "Empty List", []), (3, "Null Photos", None),
                               (4, "Empty Text", ""), (5, "No Photos Key", MISSING), (6, "Six Photos",
                               [dict(PHOTO, sha256=str(k) * 64, url=f"https://r/{k}.jpg") for k in range(6)]),
                               (7, "Http Photo", [dict(PHOTO, url="http://insecure/x.jpg")]), (8, "Text Photos", "https://x.jpg")]])
write(PLACES / "tvna_p_0005.json", {"place_id": "tvna_p_0005", "place_name": "No Photos Key", "area": "Chamkar Mon"})
covers = {"PP-901": ("https://www.tiktok.com/@a/video/1", "https://res.cloudinary.com/t/tvna/covers/PP-901.jpg"),
          "PP-902": (None, None), "PP-903": ("", ""), "PP-904": (MISSING, MISSING), "PP-905": ("  ", "   ")}
for cid, (url, cover) in covers.items():
    c = clip(cid, [place(place_id=f"tvna_p_000{i}") for i in range(1, 9)], creator=f"@{cid}")
    d = load(c)
    for key, value in (("url", url), ("cover_url", cover)):
        if value is MISSING:
            del d["source"][key]
        else:
            d["source"][key] = value
    write(c, d)
code, out = run()
data = load(OUT) if OUT.exists() else []
rec = {r["place_id"]: r for r in data}
r1 = rec.get("tvna_p_0001", {})
check("P1 photos published in order with url, source and credit only (no sha256); credit trimmed",
      code == 0 and r1.get("photos") == [{"url": "https://res.cloudinary.com/t/2.jpg", "source": "Shop's own page",
                                          "credit": "Beans Barley page"},
                                         {"url": PHOTO["url"], "source": "Google Maps", "credit": "Dara S."}]
      and "sha256" not in OUT.read_text(encoding="utf-8"), (code, out, r1))
check('P2 photos [] / null / "" / missing: left out, warned once each with the 5d command',
      all(f"tvna_p_000{i}" not in rec for i in (2, 3, 4, 5))
      and all(out.count(f'tvna_p_000{i} "{n}": no photo yet, so not published. Add 1 to 5: '
                        f"python stage5d_add_photo.py tvna_p_000{i}") == 1
              for i, n in [(2, "Empty List"), (3, "Null Photos"), (4, "Empty Text"), (5, "No Photos Key")]), (rec, out))
check("P3 a mistake in the photo list (6 photos, an http link, not a list): left out, points to the checker",
      all(f"tvna_p_000{i}" not in rec for i in (6, 7, 8))
      and all(f'tvna_p_000{i} "{n}": 1 photo problem, so not published. See: python stage5d_check_photos.py' in out
              for i, n in [(6, "Six Photos"), (7, "Http Photo"), (8, "Text Photos")])
      and "7 verified places left out for photos (above)" in out, out)
check("P4 only places with photos published; no creator or place_id warning because of the left-out ones",
      sorted(rec) == ["tvna_p_0001"] and "no creator" not in out and "no place_id" not in out, (sorted(rec), out))
m = {x["clip_id"]: x for x in r1.get("mentions", [])}
check("P5 mention video_url and cover_url: filled kept",
      m.get("PP-901", {}).get("video_url") == covers["PP-901"][0] and m.get("PP-901", {}).get("cover_url") == covers["PP-901"][1], m)
check('P6 video_url and cover_url null / "" / missing / only spaces -> null, never ""',
      all(cid in m and m[cid]["video_url"] is None and m[cid]["cover_url"] is None for cid in ("PP-902", "PP-903", "PP-904", "PP-905"))
      and '""' not in OUT.read_text(encoding="utf-8"), m)
check("P7 photo and mention keys match the template, in order",
      all(list(ph) == list(template["photos"][0]) for ph in r1.get("photos", []))
      and all(list(x) == list(template["mentions"][0]) for x in r1.get("mentions", [])), r1)
raw_out = OUT.read_bytes() if OUT.exists() else b""
raw_in = {q: q.read_bytes() for q in [*PLACES.glob("*.json"), *CLIPS.glob("*.json")]}
code2, out2 = run()
check("P8 2nd run: same output and report, no place or clip file changed",
      code2 == 0 and OUT.read_bytes() == raw_out and out2 == out and all(q.read_bytes() == b for q, b in raw_in.items()), out2)

# Q. fixes from the code review
for f in CLIPS.glob("*.json"):
    f.unlink()
write_places([{"place_id": "tvna_p_0001", "place_name": "Has Photo", "area": "Chamkar Mon",
               "photos": [dict(PHOTO, source="Other: Facebook page  ")]},
              {"place_id": "tvna_p_0002", "place_name": "", "area": "Chamkar Mon", "photos": []}])
c = clip("PP-951", [place(place_id="tvna_p_0001"), place(place_id="tvna_p_0002")])
d = load(c)
d["source"]["url"], d["source"]["cover_url"] = "javascript:alert(1)", "http://insecure/cover.jpg"
write(c, d)
code, out = run()
r = (load(OUT) or [{}])[0] if OUT.exists() else {}
mention = (r.get("mentions") or [{}])[0]
check("Q1 video_url / cover_url that are not https:// links: published as null, warned",
      code == 0 and mention.get("video_url", "x") is None and mention.get("cover_url", "x") is None
      and 'PP-951.json: source.url "javascript:alert(1)" is not an https:// link, published as null' in out
      and 'PP-951.json: source.cover_url "http://insecure/cover.jpg" is not an https:// link' in out
      and "javascript" not in OUT.read_text(encoding="utf-8"), (out, r))
check('Q2 photo source trimmed ("Other: Facebook page")', (r.get("photos") or [{}])[0].get("source") == "Other: Facebook page", r)
check('Q3 a place with no name: the photo warning says "(no name)", not "None"',
      "tvna_p_0002 (no name): no photo yet" in out and '"None"' not in out, out)
before = OUT.read_bytes()
write_places([{"place_id": "tvna_p_0001", "place_name": "Beans Barley", "area": "Prampi Makara", "photos": []}])
code, out = run()
check("Q4 every verified place left out for photos: stops (exit 1), final_dataset.json not changed, says why",
      code == 1 and OUT.read_bytes() == before and "Nothing to publish: every verified place still needs a photo" in out
      and 'tvna_p_0001 "Beans Barley": no photo yet' in out and "not changed" in out, out)
code2, out2 = run()
check("Q5 2nd run: same report, file still not changed", (code2, out2) == (code, out) and OUT.read_bytes() == before, out2)

# C. place files missing or broken: a clear message, not a Python error
raw_out = OUT.read_bytes()
shutil.rmtree(PLACES)
code, out = run()
check("C1 no places folder: says run stage 5c first, exit 1, output not written again",
      code == 1 and "No place files in" in out and "Run stage 5c first" in out and "Traceback" not in out
      and OUT.read_bytes() == raw_out, out)
PLACES.mkdir()
code, out = run()
check("C1b empty places folder: says run stage 5c first", code == 1 and "No place files in" in out, out)
(PLACES / "tvna_p_0001.json").write_text('{"place_id": "tvna_p_0001",}', encoding="utf-8")
code, out = run()
check("C2 broken place file: names the file, exit 1, nothing changed",
      code == 1 and "Can't read" in out and "tvna_p_0001.json" in out and "Nothing changed" in out
      and OUT.read_bytes() == raw_out, out)
write_places([])
(PLACES / "tvna_p_0001.json").mkdir()
code, out = run()
check("C4 a place file that is a folder: clear message, no crash", code == 1 and "Can't read" in out and "Traceback" not in out, out)
write_places([])
write(PLACES / "tvna_p_0001.json", {"place_name": "no id"})
code, out = run()
check("C3 place file without place_id: says it must be the file name", code == 1
      and "its place_id must be the file name (tvna_p_0001)" in out, out)
write(PLACES / "tvna_p_0001.json", {"place_id": "tvna_p_0002", "place_name": "Tea Kingdom"})
code, out = run()
check("C5 place file whose place_id differs from its name: refused", code == 1 and "must be the file name" in out, out)
write(PLACES / "tvna_p_0001.json", ["not", "a", "place"])
code, out = run()
check("C6 place file that is a list: refused, no crash", code == 1 and "must be the file name" in out and "Traceback" not in out, out)

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
