"""Offline checks for the name/Maps helpers, stage 1's short links and stage5c_match_places.py (fake network)."""
import contextlib
import email.message
import io
import json
import shutil
import sys
import tempfile
import urllib.error
from pathlib import Path

PIPE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPE))
import tvna_common as tc  # noqa: E402
import stage1_new_clip as s1  # noqa: E402
import stage5c_match_places as s5c  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="tvna-test-"))
CLIPS = WORK / "clips"
CLIPS.mkdir(parents=True)

# Fake network: ROUTES maps a URL to where it redirects. Anything else = no connection.
ROUTES = {}
class FakeOpener:
    def open(self, request, timeout=None):
        target = ROUTES.get(request.full_url)
        if isinstance(target, BaseException):
            raise target
        if target is None:
            raise urllib.error.URLError("offline")
        headers = email.message.Message()
        headers["Location"] = target
        raise urllib.error.HTTPError(request.full_url, 302, "Found", headers, None)
tc.urllib.request.build_opener = lambda *a: FakeOpener()

results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     {detail}"))

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

# ---------- helpers ----------
k = tc.name_key
check("key: capitals, spaces, punctuation ignored", k("Tea-Kingdom") == k("tea kingdom") == "teakingdom")
check("key: & = and, é = e", k("Coffee & Eatery") == k("Coffee and Eatery") and k("Café Amazon") == k("Cafe Amazon"))
check("key: Khmer vowel signs and coeng kept", k("ហាងម្ហូបកូរ៉េ") != k("ហងមហបករ") and "្" in k("ហាងម្ហូបកូរ៉េ")
      and k("ហាង") != k("ហង"), k("ហាងម្ហូបកូរ៉េ"))
check("key: Khmer zero-width space and space ignored", k("ហាង\u200bម្ហូប") == k("ហាង ម្ហូប") == k("ហាងម្ហូប"))
check("key: ឲ = ឱ", k("ឲ្យ") == k("ឱ្យ"))
check("score: Hanjang vs Han-Jan Coffee & Eatery = 97 (rounded down)",
      tc.name_score("Hanjang Coffee & Eatery", "Han-Jan Coffee & Eatery") == 97)
check("score: 94.7 is not rounded up to 95", tc.name_score("Sunrise Coffee House A", "Sunrise Coffee House B") == 94)
check("has_khmer", tc.has_khmer("ហាង cafe") and not tc.has_khmer("Tea Kingdom"))

FID = "0x3109513dc76a6be3:0xeac5420f72706db0"
LONG = f"https://www.google.com/maps/place/X/@11.55,104.92,17z/data=!3m1!4b1!4m6!3m5!1s{FID}!8m2!3d11.5!4d104.9?entry=ttu"
LONG2 = f"https://www.google.com/maps/place/Y/@11.56,104.93,15z/data=!4m6!3m5!1s{FID}!8m2?entry=ttu&g_ep=abc"
ROUTES["https://maps.app.goo.gl/abc123"] = LONG
ROUTES["https://maps.app.goo.gl/hop1"] = "https://maps.app.goo.gl/hop2"
ROUTES["https://maps.app.goo.gl/hop2"] = LONG2
check("maps_key: two long links to one place (different zoom/tracking) -> same key",
      tc.maps_key(LONG) == tc.maps_key(LONG2) == f"fid:{FID}")
check("maps_key: short Share link followed (also 2 hops)",
      tc.maps_key("https://maps.app.goo.gl/abc123") == tc.maps_key("https://maps.app.goo.gl/hop1") == f"fid:{FID}")
check("maps_key: query_place_id / cid / ftid links",
      tc.maps_key("https://www.google.com/maps/search/?api=1&query=x&query_place_id=ChIJabc") == "query_place_id:ChIJabc"
      and tc.maps_key("https://maps.google.com/?cid=123") == "cid:123"
      and tc.maps_key(f"https://maps.google.com/?ftid={FID}") == f"fid:{FID}")
check("maps_key: no link -> None", tc.maps_key(None) is None and tc.maps_key("  ") is None)
REAL_SHARE_TARGET = ("https://www.google.com/maps/place/STANN/@11.5771044,104.9003707,17z/data=!4m7!3m6!1s0x3109510038c45ec5"
                     ":0x740dc520910498b6!8m2!3d11.577097!4d104.9029129!15sCgVzdGFubloHIgVzdGFubpIBCm5pZ2h0X2NsdWI")
REAL_SEARCH_RESULT = ("https://www.google.com/maps/place/STANN/data=!4m7!3m6!1s0x3109510038c45ec5:0x740dc520910498b6"
                      "!8m2!3d11.577097!4d104.9029129!16s")
check("maps_key: real Share-link target and real search result for STANN -> same key (2026-11-16)",
      tc.maps_key(REAL_SHARE_TARGET) == tc.maps_key(REAL_SEARCH_RESULT) == "fid:0x3109510038c45ec5:0x740dc520910498b6")
for url, want in [("https://maps.app.goo.gl/offline", "no connection"),
                  ("https://www.google.com/maps/@11.55,104.92,15z", "no place code")]:
    try:
        tc.maps_key(url)
        check(f"maps_key error: {want}", False, "no error")
    except ValueError as e:
        check(f"maps_key error: {want}", want in str(e), str(e))

# ---------- stage 1 still expands short TikTok links (same messages) ----------
ROUTES["https://vt.tiktok.com/ZSabc/"] = "https://www.tiktok.com/@tester/video/7651894070515731733?is_from_webapp=1"
check("stage 1 short link: followed to the video", s1.follow_redirects(
      "https://vt.tiktok.com/ZSabc/", s1.TIKTOK_VIDEO_URL, "TikTok", "video").startswith("https://www.tiktok.com/@tester/video/"))
ROUTES["https://vt.tiktok.com/ZSloop/"] = "https://vt.tiktok.com/ZSloop/"
try:
    s1.follow_redirects("https://vt.tiktok.com/ZSloop/", s1.TIKTOK_VIDEO_URL, "TikTok", "video")
    check("stage 1 redirect loop: stops", False)
except ValueError as e:
    check("stage 1 redirect loop: stops with the old message", str(e) == "too many redirects, no video link found", str(e))

# ---------- stage 5c ----------
PLACES = WORK / "places.json"
def clip(name, *places):
    c = json.loads((PIPE / "templates/tvna_clip_template.json").read_text())
    c["clip_id"] = name
    c["fields"] = [dict(place_id=None, place_name=None, place_name_alt=[], area=None, google_maps_url=None,
                        verification_status="verified") | p for p in places]
    p = CLIPS / f"{name}.json"
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

def run(*clips):
    sys.argv = ["stage5c_match_places.py", *map(str, clips), "--places", str(PLACES)]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        s5c.main()
    return out.getvalue()

def pid(p, i=0):
    return load(p)["fields"][i]["place_id"]

def entry(place_id):
    return next(e for e in load(PLACES) if e["place_id"] == place_id)

a = clip("PP-002", dict(place_name="Hanjang Coffee & Eatery", area="Chamkar Mon"))
b = clip("PP-003", dict(place_name="ALWAYS selfie booth"))
out = run(a, b)
check("1 empty places.json: 2 new places, Next stage 6", pid(a) == "tvna_p_0001" and pid(b) == "tvna_p_0002"
      and "new (2):" in out and "Next: python stage6_build_final_dataset.py data/clips/*.json" in out, out)

c = clip("PP-010", dict(place_name="Han-Jan Coffee & Eatery", area="Daun Penh"))
out = run(c)
check("2 fuzzy 97%: matched, new spelling saved as alias; a different district is reported, the first kept",
      pid(c) == "tvna_p_0001"
      and 'fuzzy 97% like "Hanjang Coffee & Eatery"' in out and "Han-Jan Coffee & Eatery" in entry("tvna_p_0001")["aliases"]
      and entry("tvna_p_0001")["area"] == "Chamkar Mon"
      and 'another district "Daun Penh", places.json keeps "Chamkar Mon" (branches: Capstone 2)' in out, out)

c2 = clip("PP-011", dict(place_name="han-jan coffee and eatery"))
out = run(c2)
check("3 same spelling next time: exact match (no fuzzy)", pid(c2) == "tvna_p_0001" and "fuzzy" not in out, out)

d = clip("PP-012", dict(place_name="Luv selfie booth"))
out = run(d)
check("4 'Luv' vs 'ALWAYS' (77%): unclear, place_id null, team told what to do", pid(d) is None
      and 'maybe tvna_p_0002 "ALWAYS selfie booth" (77%)' in out and "(left null)" in out
      and 'or "new" if not' in out, out)

dd = load(d)
dd["fields"][0]["place_id"] = "tvna_p_0002"
d.write_text(json.dumps(dd, ensure_ascii=False, indent=2), encoding="utf-8")
out = run(d)
check("5 team wrote the place_id: name saved as alias", "has a place_id; new aliases: Luv selfie booth" in out
      and "Luv selfie booth" in entry("tvna_p_0002")["aliases"], out)
out = run(d)
check("5 run again: nothing new, just skipped", "skipped (1)" in out and "matched (0)" in out, out)
e = clip("PP-013", dict(place_name="LUV Selfie-Booth"))
out = run(e)
check("5 the next clip with that name: exact match", pid(e) == "tvna_p_0002", out)

brown = clip("PP-014", dict(place_name="Brown Coffee"))
run(brown)
f = clip("PP-015", dict(place_name="Brew Coffee"))
out = run(f)
check("6 'Brew Coffee' vs 'Brown Coffee' (85%): unclear, not joined", pid(f) is None and "(85%)" in out, out)
ff = load(f)
ff["fields"][0]["place_id"] = "new"
f.write_text(json.dumps(ff, ensure_ascii=False, indent=2), encoding="utf-8")
out = run(f)
check('6 team wrote "new": new place made', pid(f) == "tvna_p_0004" and "the team said: a different place" in out
      and entry("tvna_p_0004")["place_name"] == "Brew Coffee", out)

g = clip("PP-016", dict(place_name="Han Jan"))
out = run(g)
check("7 short name inside a long one: unclear", pid(g) is None and "name inside the other" in out, out)

km = clip("PP-017", dict(place_name="ហាងម្ហូបកូរ៉េ"))
run(km)
km_no_coeng = clip("PP-018", dict(place_name="ហាងមហូបកូរ៉េ"))
km_zwsp = clip("PP-019", dict(place_name="ហាង\u200bម្ហូប កូរ៉េ"))
out = run(km_no_coeng, km_zwsp)
check("8 Khmer missing coeng (96%): unclear, not joined automatically", pid(km_no_coeng) is None
      and "Khmer names are always checked by the team" in out, out)
check("8 Khmer with zero-width space: exact match", pid(km_zwsp) == pid(km), out)

mon = clip("PP-020", dict(place_name="Independence Monument", google_maps_url=LONG))
run(mon)
mon_km = clip("PP-021", dict(place_name="វិមានឯករាជ្យ", google_maps_url="https://maps.app.goo.gl/abc123"))
out = run(mon_km)
check("9 Khmer name + Share link to the same place: matched by Maps link", pid(mon_km) == pid(mon)
      and "same Google Maps link" in out and "វិមានឯករាជ្យ" in entry(pid(mon))["aliases"], out)

h = clip("PP-022", dict(place_name="Hanjang Coffee & Eatery", google_maps_url=LONG2.replace(FID, "0x1:0x2")))
out = run(h)
check("10 Maps link added to a place that had none", pid(h) == "tvna_p_0001" and "Maps link added" in out
      and bool(entry("tvna_p_0001")["google_maps_url"]), out)
h2 = clip("PP-023", dict(place_name="Hanjang Coffee & Eatery", google_maps_url=LONG2.replace(FID, "0x3:0x4")))
out = run(h2)
check("10 same name, different Maps link: unclear (another branch or another place?)",
      pid(h2) is None and "another branch (write tvna_p_0001)" in out, out)

off = clip("PP-024", dict(place_name="Brown Coffee", google_maps_url="https://maps.app.goo.gl/offline"))
out = run(off)
check("11 link can't be read: name check used instead (exact name -> Brown Coffee)", pid(off) == "tvna_p_0003", out)
check("11 problem listed", "Maps link problems (1):" in out and "no connection" in out
      and "Checked by name instead" in out, out)

two = [clip("PP-025", dict(place_name="Sunrise Coffee House A")), clip("PP-026", dict(place_name="Sunrise Coffee House B"))]
out = run(*two)
check("12 '...House A' vs '...House B' (94%): B is unclear, not joined", pid(two[1]) is None and "(94%)" in out, out)
bb = load(two[1]); bb["fields"][0]["place_id"] = "new"; two[1].write_text(json.dumps(bb, ensure_ascii=False), encoding="utf-8")
run(two[1])
s = clip("PP-027", dict(place_name="Sunrise Coffee House"))
out = run(s)
check("12 two places 95%+: unclear, both suggested", pid(s) is None and pid(two[0]) != pid(two[1])
      and pid(two[0]) in out and pid(two[1]) in out, out)

rej = clip("PP-028", dict(place_name="Tea Kingdom", verification_status="rejected"), dict(place_name=None),
           dict(place_name="X", place_id="tvna_p_9999"))
out = run(rej)
check("13 rejected / no name skipped, unknown id reported", "skipped (2)" in out
      and "tvna_p_9999 is not in places.json" in out and pid(rej) is None, out)

before = PLACES.read_bytes()
out = run(*CLIPS.glob("*.json"))
check("14 run everything again: places.json unchanged, no new places", PLACES.read_bytes() == before
      and "new (0)" in out, out)

# R. run it twice: every kind of value -> the 2nd run changes nothing
NAMES = ["Alpha Bakery", "Mekong Grill", "Lotus Spa", "Kampot Pepper House", "Riverside Noodles",
         "Golden Tuk Tuk Bar", "Jasmine Tea Room", "Orchid Florist"]
for i, (kind, over, drop) in enumerate([
        ("place_id null", {}, None), ('place_id ""', {"place_id": ""}, None), ("place_id missing", {}, "place_id"),
        ("place_name_alt null", {"place_name_alt": None}, None), ('place_name_alt ""', {"place_name_alt": ""}, None),
        ("place_name_alt missing", {}, "place_name_alt"), ('google_maps_url ""', {"google_maps_url": ""}, None),
        ("google_maps_url missing", {}, "google_maps_url")]):
    p = clip(f"PP-2{i:02d}", dict(place_name=NAMES[i], **over))
    if drop:
        c = load(p)
        del c["fields"][0][drop]
        p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    out1 = run(p)
    raw, places_raw = p.read_bytes(), PLACES.read_bytes()
    out = run(p)
    check(f"R {kind}: 1st run gives a new place_id; 2nd run changes nothing (clip and places.json)",
          (pid(p) or "").startswith("tvna_p_") and p.read_bytes() == raw and PLACES.read_bytes() == places_raw
          and "new (0)" in out and "matched (0)" in out, (out1, out))

# R. Maps links: the 2nd run reads none (every place already has a place_id)
NET = []
_open = FakeOpener.open
def counted_open(self, request, timeout=None):
    NET.append(request.full_url)
    return _open(self, request, timeout)
FakeOpener.open = counted_open
ROUTES["https://maps.app.goo.gl/twice"] = LONG.replace(FID, "0x31095100aaaa:0x1111")
mp = clip("PP-299", dict(place_name="Twice Cafe", google_maps_url="https://maps.app.goo.gl/twice"))
NET.clear()
run(mp)
first, raw, places_raw = len(NET), mp.read_bytes(), PLACES.read_bytes()
NET.clear()
out = run(mp)
check("R short Maps link: 1st run reads it; 2nd run reads no link and changes nothing",
      first >= 1 and not NET and mp.read_bytes() == raw and PLACES.read_bytes() == places_raw, (first, NET, out))
NET.clear()
run(*sorted(CLIPS.glob("*.json")))
raw_all = {q: q.read_bytes() for q in CLIPS.glob("*.json")}
places_raw = PLACES.read_bytes()
NET.clear()
out = run(*sorted(CLIPS.glob("*.json")))
check("R all clips: 2nd run changes no file (unclear places stay unclear)",
      all(q.read_bytes() == b for q, b in raw_all.items()) and PLACES.read_bytes() == places_raw
      and "new (0)" in out and "new aliases" not in out
      and 'PP-010.json  "Han-Jan Coffee & Eatery" -> tvna_p_0001 (has a place_id; another district "Daun Penh"' in out, out)
check("R 2nd run: a different district is reported again (nothing changed, so stage 6's warning is explained)",
      'another district "Daun Penh", places.json keeps "Chamkar Mon"' in out, out)

# S. hand-typed values and broken connections
sp = clip("PP-300", dict(place_name="Saffron Lane", place_name_alt="Saffron", google_maps_url=""))
run(sp)
e = entry(pid(sp)) if pid(sp) else {}
check('S1 place_name_alt typed as one text, not a list: saved as one alias, not letters',
      e.get("aliases") == ["Saffron Lane", "Saffron"], e)
check('S2 google_maps_url "" in a clip -> null in places.json', "google_maps_url" in e and e["google_maps_url"] is None, e)

data = load(PLACES)
data.append({"place_id": "tvna_p_0900", "place_name": "Null Alias Cafe", "aliases": None, "area": None,
             "google_maps_url": None})
data.append({"place_id": "tvna_p_0901", "place_name": "No Alias Key Bar", "area": []})
PLACES.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
na = clip("PP-301", dict(place_name="Null Alias Cafe", place_name_alt=["NA Cafe"]))
nk = clip("PP-302", dict(place_name="No Alias Key Bar"))
try:
    out = run(na, nk)
    crashed = ""
except Exception as ex:  # noqa: BLE001
    out, crashed = "", repr(ex)
check("S3 places.json entry with aliases null or missing: no crash, matched, aliases become a list",
      not crashed and pid(na) == "tvna_p_0900" and pid(nk) == "tvna_p_0901"
      and entry("tvna_p_0900")["aliases"] == ["Null Alias Cafe", "NA Cafe"], crashed or out)

ROUTES["https://maps.app.goo.gl/slow"] = TimeoutError("timed out")
sl = clip("PP-303", dict(place_name="Slow Link Diner", google_maps_url="https://maps.app.goo.gl/slow"))
try:
    out = run(sl)
    crashed = ""
except Exception as ex:  # noqa: BLE001
    out, crashed = "", repr(ex)
check("S4 Maps link times out: no crash, reported, place checked by name",
      not crashed and "maps.app.goo.gl/slow: no connection (TimeoutError)" in out and bool(pid(sl)), crashed or out)

ROUTES["https://maps.app.goo.gl/ctrlc"] = KeyboardInterrupt()
first = clip("PP-304", dict(place_name="Brand New Noodle Bar"))
stop = clip("PP-305", dict(place_name="Stopped Cafe", google_maps_url="https://maps.app.goo.gl/ctrlc"))
raw_first, places_raw = first.read_bytes(), PLACES.read_bytes()
try:
    run(first, stop)
    stopped = False
except KeyboardInterrupt:
    stopped = True
check("S5 Ctrl-C in the middle of a run: nothing written (no clip with a place_id places.json doesn't have)",
      stopped and first.read_bytes() == raw_first and PLACES.read_bytes() == places_raw)

# V. only places the team approved (verified) get a place_id
ROUTES["https://maps.app.goo.gl/waiting"] = LONG.replace(FID, "0x31095100bbbb:0x2222")
STATUSES = [("needs_review", "needs_review"), ("auto_added", "auto_added"), ("null", None), ('""', ""),
            ("missing", MISSING := object()), ('"Verified" (typo)', "Verified")]
waiting = []
for i, (kind, status) in enumerate(STATUSES):
    p = clip(f"PP-40{i}", dict(place_name=f"Waiting Cafe {i}", google_maps_url="https://maps.app.goo.gl/waiting",
                               verification_status=None if status is MISSING else status))
    if status is MISSING:
        c = load(p)
        del c["fields"][0]["verification_status"]
        p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    waiting.append(p)
raw_all, places_raw = {q: q.read_bytes() for q in waiting}, PLACES.read_bytes()
for attempt in ("1st", "2nd"):
    NET.clear()
    out = run(*waiting)
    check(f"V1 {attempt} run, status needs_review / auto_added / null / \"\" / missing / a typo: waiting, "
          "nothing written, no Maps link read",
          "waiting for review (6):" in out and all(q.read_bytes() == b for q, b in raw_all.items())
          and PLACES.read_bytes() == places_raw and not NET and "new (0)" in out and "matched (0)" in out, (NET, out))
check("V2 each waiting place listed with its status, and the team told what to do",
      all(s in out for s in ['"Waiting Cafe 0" (verification_status "needs_review")',
                             '"Waiting Cafe 2" (verification_status null)', '"Waiting Cafe 3" (verification_status "")',
                             '"Waiting Cafe 4" (verification_status null)', '"Waiting Cafe 5" (verification_status "Verified")'])
      and 'writes "verification_status": "verified". Then run this again.' in out, out)

known = entry("tvna_p_0001")
team_id = clip("PP-410", dict(place_name="Hanjan Cafe Unchecked", place_id="tvna_p_0001", area="Sen Sok",
                              verification_status="needs_review"))
team_rej = clip("PP-411", dict(place_name="Hanjan Cafe Rejected", place_id="tvna_p_0001", area="Dangkao",
                               verification_status="rejected"))
places_raw = PLACES.read_bytes()
out = run(team_id, team_rej)
check("V3 team wrote a place_id but the place is not verified (waiting) or rejected (skipped): "
      "no alias, district or link saved",
      PLACES.read_bytes() == places_raw and "waiting for review (1):" in out and "skipped (1)" in out
      and entry("tvna_p_0001") == known
      and '(verification_status "needs_review"; has place_id tvna_p_0001, not published until verified)' in out, out)
cb = clip("PP-413", dict(place_name="Reviewed Cafe", verification_status="auto_added", cleaned_by="Dara"))
out = run(cb)
check("V3b cleaned_by filled but status not verified: waiting, and the team is told to write verified",
      pid(cb) is None and 'cleaned_by is filled: write "verified" if the place is checked' in out, out)

swap = clip("PP-412", dict(place_name="Moonlight Noodle House", place_name_alt=["Moon Night Noodle House"],
                           verification_status="needs_review"))
out = run(swap)
check("V4 before the review: no place made", pid(swap) is None and "new (0)" in out, out)
sw = load(swap)
sw["fields"][0]["verification_status"] = "verified"
swap.write_text(json.dumps(sw, ensure_ascii=False, indent=2), encoding="utf-8")
out = run(swap)
e = entry(pid(swap)) if pid(swap) else {}
check("V5 after the team sets verified: new place, named after the clip's place_name, other name kept as alias",
      "new (1):" in out and e.get("place_name") == "Moonlight Noodle House"
      and e.get("aliases") == ["Moonlight Noodle House", "Moon Night Noodle House"], (out, e))
raw, places_raw = swap.read_bytes(), PLACES.read_bytes()
out = run(swap)
check("V6 2nd run after verified: nothing changes", swap.read_bytes() == raw and PLACES.read_bytes() == places_raw
      and "skipped (1)" in out, out)

# W. a clip calls a known place something else: 5c says once which name the website keeps
data = load(PLACES)
data.append({"place_id": "tvna_p_0950", "place_name": "Old Gemini Name Noodle House",
             "aliases": ["Old Gemini Name Noodle House"], "area": None})
PLACES.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
fixed = clip("PP-420", dict(place_name="Right Name", place_id="tvna_p_0950"))
out = run(fixed)
check("W1 team-set place_id with a new name: alias saved, and the report says the website name stays",
      'has a place_id; new aliases: Right Name; website name stays "Old Gemini Name Noodle House"' in out
      and entry("tvna_p_0950")["place_name"] == "Old Gemini Name Noodle House", out)
out = run(fixed)
check("W2 2nd run: skipped, the note is not repeated", "website name stays" not in out and "skipped (1)" in out, out)
fz = clip("PP-421", dict(place_name="Old Gemini Name Noodle Houze"))
out = run(fz)
check("W3 fuzzy match: the report says the website name stays", pid(fz) == "tvna_p_0950"
      and 'website name stays "Old Gemini Name Noodle House"' in out, out)
same = clip("PP-422", dict(place_name="old gemini name noodle-house"))
out = run(same)
check("W4 same name in other capitals: no note", pid(same) == "tvna_p_0950" and "website name stays" not in out, out)

# Area typed by the team as one district (text), not a list
t1 = clip("PP-430", dict(place_name="Text Area Tea House", area="Sen Sok"))
out = run(t1)
new_id = pid(t1)
check("T1 new place: its district saved as text in places.json", bool(new_id) and entry(new_id)["area"] == "Sen Sok", out)
t2 = clip("PP-431", dict(place_name="Text Area Tea House", area="Daun Penh"))
out = run(t2)
check("T2 match with another district: first kept, reported", pid(t2) == new_id and entry(new_id)["area"] == "Sen Sok"
      and 'another district "Daun Penh", places.json keeps "Sen Sok"' in out, out)
t3 = clip("PP-432", dict(place_name="No District Yet Cafe"))
run(t3)
t3_id = pid(t3)
t4 = clip("PP-433", dict(place_name="No District Yet Cafe", area="Dangkao"))
out = run(t4)
check("T3 place with no district: the next clip's district fills it", entry(t3_id)["area"] == "Dangkao"
      and "district added: Dangkao" in out, out)
data = load(PLACES)
next(e for e in data if e["place_id"] == t3_id)["area"] = ["Dangkao", "Sen Sok"]
PLACES.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
t5 = clip("PP-434", dict(place_name="No District Yet Cafe", area="Dangkao"))
out = run(t5)
check("T4 old places.json with a list: read, saved back as one district (the first)",
      entry(t3_id)["area"] == "Dangkao" and "another district" not in out, out)
check("T5 old list with two districts: the one left out is named", "district saved as text (left out: Sen Sok)" in out, out)

data = load(PLACES)
next(e for e in data if e["place_id"] == t3_id)["area"] = "BKK1"
PLACES.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
t6 = clip("PP-435", dict(place_name="No District Yet Cafe", place_name_alt=["No District Yet Cafe BKK1"]))
out = run(t6)
check("T6 hand-typed area that is not a district, clip with no district: kept, not erased",
      pid(t6) == t3_id and entry(t3_id)["area"] == "BKK1", out)
t7 = clip("PP-436", dict(place_name="No District Yet Cafe", area="Chamkar Mon"))
out = run(t7)
check("T7 hand-typed area that is not a district, clip with a district: replaced, and the report says so",
      entry(t3_id)["area"] == "Chamkar Mon" and 'district added: Chamkar Mon (was "BKK1", not a district)' in out, out)

# A place with a place_id, another name and another district: the district note every run, the name note once
wn = clip("PP-440", dict(place_name="Text Area Tea Shop", place_id=new_id, area="Dangkao"))
out1 = run(wn)
out2 = run(wn)
check("W5 1st run: new alias, other district and website name all said",
      "new aliases: Text Area Tea Shop" in out1 and 'another district "Dangkao"' in out1 and "website name stays" in out1, out1)
check("W5 2nd run: only the district note again, website name not repeated",
      'another district "Dangkao"' in out2 and "website name stays" not in out2, out2)

def set_entry_area(place_id, value):
    data = load(PLACES)
    next(e for e in data if e["place_id"] == place_id)["area"] = value
    PLACES.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

# A clip that already has its place_id and adds nothing new: places.json's area is still put right and saved
set_entry_area(t3_id, "ចំការមន")
out = run(t7)
check("T8 area typed in Khmer in places.json: saved as the English name, and the report says so",
      entry(t3_id)["area"] == "Chamkar Mon" and 'district written as in areas.json: "Chamkar Mon" (was "ចំការមន")' in out, out)
before = PLACES.read_bytes()
out = run(t7)
check("T8 R 2nd run: nothing changes, nothing said", PLACES.read_bytes() == before and "written as in areas.json" not in out, out)
set_entry_area(t3_id, " Chamkar Mon ")
run(t7)
check("T8b district with extra spaces: saved trimmed", entry(t3_id)["area"] == "Chamkar Mon", entry(t3_id))
t9 = clip("PP-437", dict(place_name="No District Yet Cafe"))
for old_area, want in [(["BKK1", "near market"], "BKK1"), ([], None), ([None, " "], None)]:
    set_entry_area(t3_id, old_area)
    out = run(t9)
    check(f"T9 old list with no district {old_area}, clip with none: saved as text {want!r}, not left a list",
          entry(t3_id)["area"] == want and "area saved as text" in out, out)
    before = PLACES.read_bytes()
    run(t9)
    check(f"T9 R {old_area}: 2nd run changes nothing", PLACES.read_bytes() == before)

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
