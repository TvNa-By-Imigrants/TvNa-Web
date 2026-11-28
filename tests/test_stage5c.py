"""Offline checks for the name/Maps helpers, stage 1's short links and stage5c_match_places.py (fake network)."""
import contextlib
import email.message
import hashlib
import io
import json
import re
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
PLACES = WORK / "places"
OLD = WORK / "old_places.json"  # the old one-file places.json; only there when a test makes it

def maps(name):
    """A made-up full Google Maps link with its own place code, one per name."""
    code = hashlib.sha256(name.encode()).hexdigest()
    return f"https://www.google.com/maps/place/x/data=!4m6!3m5!1s0x{code[:12]}:0x{code[12:20]}!8m2"

def new_id(link):
    return tc.place_id_from_maps(tc.maps_key(link))

def clip(name, *places, folder=CLIPS):
    c = json.loads((PIPE / "templates/tvna_clip_template.json").read_text())
    c["clip_id"] = name
    c["fields"] = [dict(place_id=None, place_name=None, place_name_alt=[], area=None, google_maps_url=None,
                        verification_status="verified") | p for p in places]
    p = Path(folder) / f"{name}.json"
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

def run(*clips, places=PLACES, old=OLD):
    sys.argv = ["stage5c_match_places.py", *map(str, clips), "--places-dir", str(places), "--old-places", str(old)]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            s5c.main()
        except SystemExit as e:  # sys.exit("message")
            out.write(str(e.code))
    return out.getvalue()

def pid(p, i=0):
    return load(p)["fields"][i]["place_id"]

def entry(place_id, folder=PLACES):
    return load(Path(folder) / f"{place_id}.json")

def put(e, folder=PLACES):
    Path(folder).mkdir(parents=True, exist_ok=True)
    (Path(folder) / f"{e['place_id']}.json").write_text(json.dumps(e, ensure_ascii=False, indent=2), encoding="utf-8")

def snap(folder=PLACES):
    """Every file in the places folder and its bytes (a leftover .part file shows up too)."""
    return {q.name: q.read_bytes() for q in sorted(Path(folder).glob("*"))} if Path(folder).exists() else {}

def set_entry_area(place_id, value):
    e = entry(place_id)
    e["area"] = value
    put(e)

a = clip("PP-002", dict(place_name="Hanjang Coffee & Eatery", area="Chamkar Mon", google_maps_url=maps("Hanjang")))
b = clip("PP-003", dict(place_name="ALWAYS selfie booth", google_maps_url=maps("ALWAYS")))
out = run(a, b)
HJ, AL = pid(a), pid(b)
check("1 no places yet: 2 new places, ids from their Maps links, one file each, Next stage 6",
      HJ == new_id(maps("Hanjang")) and AL == new_id(maps("ALWAYS")) and HJ != AL
      and sorted(snap()) == sorted([f"{HJ}.json", f"{AL}.json"])
      and "new (2):" in out and "python stage6_build_final_dataset.py data/clips/*.json" in out, out)
check("1 the id is tvna_p_ + 10 letters/numbers", re.fullmatch(r"tvna_p_[0-9a-f]{10}", HJ or "") is not None, HJ)
template = json.loads((PIPE / "templates/tvna_places_template.json").read_text())
check("1 a new place file has the template's keys, in order, and photos []",
      list(entry(HJ)) == list(template) and entry(HJ)["photos"] == [], entry(HJ))

c = clip("PP-010", dict(place_name="Han-Jan Coffee & Eatery", area="Daun Penh"))
out = run(c)
check("2 fuzzy 97%: matched, new spelling saved as alias; a different district is reported, the first kept",
      pid(c) == HJ
      and 'fuzzy 97% like "Hanjang Coffee & Eatery"' in out and "Han-Jan Coffee & Eatery" in entry(HJ)["aliases"]
      and entry(HJ)["area"] == "Chamkar Mon"
      and 'another district "Daun Penh", the place file keeps "Chamkar Mon" (branches: Capstone 2)' in out, out)

c2 = clip("PP-011", dict(place_name="han-jan coffee and eatery"))
out = run(c2)
check("3 same spelling next time: exact match (no fuzzy)", pid(c2) == HJ and "fuzzy" not in out, out)

d = clip("PP-012", dict(place_name="Luv selfie booth"))
out = run(d)
check("4 'Luv' vs 'ALWAYS' (77%): unclear, place_id null, team told what to do", pid(d) is None
      and f'maybe {AL} "ALWAYS selfie booth" (77%)' in out and "(left null)" in out
      and 'or "new" if not' in out, out)

dd = load(d)
dd["fields"][0]["place_id"] = AL
d.write_text(json.dumps(dd, ensure_ascii=False, indent=2), encoding="utf-8")
out = run(d)
check("5 team wrote the place_id: name saved as alias", "has a place_id; new aliases: Luv selfie booth" in out
      and "Luv selfie booth" in entry(AL)["aliases"], out)
out = run(d)
check("5 run again: nothing new, just skipped", "skipped (1)" in out and "matched (0)" in out, out)
e = clip("PP-013", dict(place_name="LUV Selfie-Booth"))
out = run(e)
check("5 the next clip with that name: exact match", pid(e) == AL, out)

brown = clip("PP-014", dict(place_name="Brown Coffee", google_maps_url=maps("Brown")))
run(brown)
BR = pid(brown)
f = clip("PP-015", dict(place_name="Brew Coffee", google_maps_url=maps("Brew")))
out = run(f)
check("6 'Brew Coffee' vs 'Brown Coffee' (85%): unclear, not joined", pid(f) is None and "(85%)" in out, out)
ff = load(f)
ff["fields"][0]["place_id"] = "new"
f.write_text(json.dumps(ff, ensure_ascii=False, indent=2), encoding="utf-8")
out = run(f)
check('6 team wrote "new": new place made', pid(f) == new_id(maps("Brew")) and "the team said: a different place" in out
      and entry(pid(f))["place_name"] == "Brew Coffee", out)

g = clip("PP-016", dict(place_name="Han Jan"))
out = run(g)
check("7 short name inside a long one: unclear", pid(g) is None and "name inside the other" in out, out)

km = clip("PP-017", dict(place_name="ហាងម្ហូបកូរ៉េ", google_maps_url=maps("km")))
run(km)
km_no_coeng = clip("PP-018", dict(place_name="ហាងមហូបកូរ៉េ"))
km_zwsp = clip("PP-019", dict(place_name="ហាង​ម្ហូប កូរ៉េ"))
out = run(km_no_coeng, km_zwsp)
check("8 Khmer missing coeng (96%): unclear, not joined automatically", pid(km_no_coeng) is None
      and "Khmer names are always checked by the team" in out, out)
check("8 Khmer with zero-width space: exact match", pid(km_zwsp) == pid(km) is not None, out)

mon = clip("PP-020", dict(place_name="Independence Monument", google_maps_url=LONG))
run(mon)
mon_km = clip("PP-021", dict(place_name="វិមានឯករាជ្យ", google_maps_url="https://maps.app.goo.gl/abc123"))
out = run(mon_km)
check("9 Khmer name + Share link to the same place: matched by Maps link", pid(mon_km) == pid(mon) == new_id(LONG)
      and "same Google Maps link" in out and "វិមានឯករាជ្យ" in entry(pid(mon))["aliases"], out)
check("9 a Share link and a long link to one place give the same new id",
      new_id("https://maps.app.goo.gl/abc123") == new_id(LONG) == new_id(LONG2))

put({"place_id": "tvna_p_0800", "place_name": "No Link Yet Cafe", "aliases": [], "area": None,
     "google_maps_url": None, "photos": []})
h = clip("PP-022", dict(place_name="No Link Yet Cafe", google_maps_url=LONG2.replace(FID, "0x1:0x2")))
out = run(h)
check("10 Maps link added to a place that had none (e.g. moved from the old places.json)",
      pid(h) == "tvna_p_0800" and "Maps link added" in out and bool(entry("tvna_p_0800")["google_maps_url"]), out)
h2 = clip("PP-023", dict(place_name="Hanjang Coffee & Eatery", google_maps_url=LONG2.replace(FID, "0x3:0x4")))
out = run(h2)
check("10 same name, different Maps link: unclear (another branch or another place?)",
      pid(h2) is None and f"another branch (write {HJ})" in out, out)

off = clip("PP-024", dict(place_name="Brown Coffee", google_maps_url="https://maps.app.goo.gl/offline"))
out = run(off)
check("11 link can't be read: name check used instead (exact name -> Brown Coffee)", pid(off) == BR, out)
check("11 problem listed", "Maps link problems (1):" in out and "no connection" in out
      and "Checked by name instead" in out, out)

two = [clip("PP-025", dict(place_name="Sunrise Coffee House A", google_maps_url=maps("SunA"))),
       clip("PP-026", dict(place_name="Sunrise Coffee House B", google_maps_url=maps("SunB")))]
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
      and "tvna_p_9999 has no place file" in out and pid(rej) is None, out)

before = snap()
out = run(*CLIPS.glob("*.json"))
check("14 run everything again: no place file changed, no new places", snap() == before and "new (0)" in out, out)

# R. run it twice: every kind of value -> the 2nd run changes nothing
NAMES = ["Alpha Bakery", "Mekong Grill", "Lotus Spa", "Kampot Pepper House", "Riverside Noodles",
         "Golden Tuk Tuk Bar", "Jasmine Tea Room", "Orchid Florist"]
for i, (kind, over, drop) in enumerate([
        ("place_id null", {}, None), ('place_id ""', {"place_id": ""}, None), ("place_id missing", {}, "place_id"),
        ("place_name_alt null", {"place_name_alt": None}, None), ('place_name_alt ""', {"place_name_alt": ""}, None),
        ("place_name_alt missing", {}, "place_name_alt"), ('google_maps_url ""', {"google_maps_url": ""}, None),
        ("google_maps_url missing", {}, "google_maps_url")]):
    has_link = "google_maps_url" not in over and drop != "google_maps_url"
    p = clip(f"PP-2{i:02d}", dict(place_name=NAMES[i], **({"google_maps_url": maps(NAMES[i])} if has_link else {}), **over))
    if drop:
        c = load(p)
        del c["fields"][0][drop]
        p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    out1 = run(p)
    raw, places_raw = p.read_bytes(), snap()
    out = run(p)
    if has_link:
        first, said = (pid(p) or "").startswith("tvna_p_"), "gives a new place_id"
    else:
        first, said = (pid(p) is None and "no Google Maps link, so no place_id can be made" in out1), "is unclear (no Maps link)"
    check(f"R {kind}: 1st run {said}; 2nd run changes nothing (clip and place files)",
          first and p.read_bytes() == raw and snap() == places_raw
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
first, raw, places_raw = len(NET), mp.read_bytes(), snap()
NET.clear()
out = run(mp)
check("R short Maps link: 1st run reads it; 2nd run reads no link and changes nothing",
      first >= 1 and not NET and mp.read_bytes() == raw and snap() == places_raw and bool(pid(mp)), (first, NET, out))
NET.clear()
run(*sorted(CLIPS.glob("*.json")))
raw_all = {q: q.read_bytes() for q in CLIPS.glob("*.json")}
places_raw = snap()
NET.clear()
out = run(*sorted(CLIPS.glob("*.json")))
check("R all clips: 2nd run changes no file (unclear places stay unclear)",
      all(q.read_bytes() == b for q, b in raw_all.items()) and snap() == places_raw
      and "new (0)" in out and "new aliases" not in out
      and f'PP-010.json  "Han-Jan Coffee & Eatery" -> {HJ} (has a place_id; another district "Daun Penh"' in out, out)
check("R 2nd run: a different district is reported again (nothing changed, so stage 6's warning is explained)",
      'another district "Daun Penh", the place file keeps "Chamkar Mon"' in out, out)

# S. hand-typed values and broken connections
sp = clip("PP-300", dict(place_name="Saffron Lane", place_name_alt="Saffron", google_maps_url=maps("Saffron")))
run(sp)
e = entry(pid(sp)) if pid(sp) else {}
check('S1 place_name_alt typed as one text, not a list: saved as one alias, not letters',
      e.get("aliases") == ["Saffron Lane", "Saffron"], e)
files = snap()
sn = clip("PP-306", dict(place_name="Empty Link Bistro", google_maps_url="  "))
out = run(sn)
check('S2 google_maps_url of only spaces: no place made, the team is told to add the Share link',
      pid(sn) is None and snap() == files and "no Google Maps link, so no place_id can be made" in out, out)

put({"place_id": "tvna_p_0900", "place_name": "Null Alias Cafe", "aliases": None, "area": None, "google_maps_url": None})
put({"place_id": "tvna_p_0901", "place_name": "No Alias Key Bar", "area": []})
na = clip("PP-301", dict(place_name="Null Alias Cafe", place_name_alt=["NA Cafe"]))
nk = clip("PP-302", dict(place_name="No Alias Key Bar"))
try:
    out = run(na, nk)
    crashed = ""
except Exception as ex:  # noqa: BLE001
    out, crashed = "", repr(ex)
check("S3 place file with aliases null or missing: no crash, matched, aliases become a list",
      not crashed and pid(na) == "tvna_p_0900" and pid(nk) == "tvna_p_0901"
      and entry("tvna_p_0900")["aliases"] == ["Null Alias Cafe", "NA Cafe"], crashed or out)

ROUTES["https://maps.app.goo.gl/slow"] = TimeoutError("timed out")
sl = clip("PP-303", dict(place_name="Slow Link Diner", google_maps_url="https://maps.app.goo.gl/slow"))
try:
    out = run(sl)
    crashed = ""
except Exception as ex:  # noqa: BLE001
    out, crashed = "", repr(ex)
check("S4 Maps link times out: no crash, reported, no new place (its id needs the link): run again online",
      not crashed and "maps.app.goo.gl/slow: no connection (TimeoutError)" in out and pid(sl) is None
      and "can't read its Google Maps link (no connection (TimeoutError)), so no place_id can be made. Run again online"
      in out, crashed or out)

ROUTES["https://maps.app.goo.gl/ctrlc"] = KeyboardInterrupt()
first = clip("PP-304", dict(place_name="Brand New Noodle Bar", google_maps_url=maps("Brand New")))
stop = clip("PP-305", dict(place_name="Stopped Cafe", google_maps_url="https://maps.app.goo.gl/ctrlc"))
raw_first, places_raw = first.read_bytes(), snap()
try:
    run(first, stop)
    stopped = False
except KeyboardInterrupt:
    stopped = True
check("S5 Ctrl-C in the middle of a run: nothing written (no clip with a place_id that has no place file)",
      stopped and first.read_bytes() == raw_first and snap() == places_raw)

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
raw_all, places_raw = {q: q.read_bytes() for q in waiting}, snap()
for attempt in ("1st", "2nd"):
    NET.clear()
    out = run(*waiting)
    check(f"V1 {attempt} run, status needs_review / auto_added / null / \"\" / missing / a typo: waiting, "
          "nothing written, no Maps link read",
          "waiting for review (6):" in out and all(q.read_bytes() == b for q, b in raw_all.items())
          and snap() == places_raw and not NET and "new (0)" in out and "matched (0)" in out, (NET, out))
check("V2 each waiting place listed with its status, and the team told what to do",
      all(s in out for s in ['"Waiting Cafe 0" (verification_status "needs_review")',
                             '"Waiting Cafe 2" (verification_status null)', '"Waiting Cafe 3" (verification_status "")',
                             '"Waiting Cafe 4" (verification_status null)', '"Waiting Cafe 5" (verification_status "Verified")'])
      and 'writes "verification_status": "verified". Then run this again.' in out, out)

known = entry(HJ)
team_id = clip("PP-410", dict(place_name="Hanjan Cafe Unchecked", place_id=HJ, area="Sen Sok",
                              verification_status="needs_review"))
team_rej = clip("PP-411", dict(place_name="Hanjan Cafe Rejected", place_id=HJ, area="Dangkao",
                               verification_status="rejected"))
places_raw = snap()
out = run(team_id, team_rej)
check("V3 team wrote a place_id but the place is not verified (waiting) or rejected (skipped): "
      "no alias, district or link saved",
      snap() == places_raw and "waiting for review (1):" in out and "skipped (1)" in out
      and entry(HJ) == known
      and f'(verification_status "needs_review"; has place_id {HJ}, not published until verified)' in out, out)
cb = clip("PP-413", dict(place_name="Reviewed Cafe", verification_status="auto_added", cleaned_by="Dara"))
out = run(cb)
check("V3b cleaned_by filled but status not verified: waiting, and the team is told to write verified",
      pid(cb) is None and 'cleaned_by is filled: write "verified" if the place is checked' in out, out)

swap = clip("PP-412", dict(place_name="Moonlight Noodle House", place_name_alt=["Moon Night Noodle House"],
                           google_maps_url=maps("Moonlight"), verification_status="needs_review"))
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
raw, places_raw = swap.read_bytes(), snap()
out = run(swap)
check("V6 2nd run after verified: nothing changes", swap.read_bytes() == raw and snap() == places_raw
      and "skipped (1)" in out, out)

# W. a clip calls a known place something else: 5c says once which name the website keeps
put({"place_id": "tvna_p_0950", "place_name": "Old Gemini Name Noodle House",
     "aliases": ["Old Gemini Name Noodle House"], "area": None})
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
t1 = clip("PP-430", dict(place_name="Text Area Tea House", area="Sen Sok", google_maps_url=maps("TextArea")))
out = run(t1)
new_place = pid(t1)
check("T1 new place: its district saved as text in its place file", bool(new_place) and entry(new_place)["area"] == "Sen Sok", out)
t2 = clip("PP-431", dict(place_name="Text Area Tea House", area="Daun Penh"))
out = run(t2)
check("T2 match with another district: first kept, reported", pid(t2) == new_place and entry(new_place)["area"] == "Sen Sok"
      and 'another district "Daun Penh", the place file keeps "Sen Sok"' in out, out)
t3 = clip("PP-432", dict(place_name="No District Yet Cafe", google_maps_url=maps("NoDistrict")))
run(t3)
t3_id = pid(t3)
t4 = clip("PP-433", dict(place_name="No District Yet Cafe", area="Dangkao"))
out = run(t4)
check("T3 place with no district: the next clip's district fills it", entry(t3_id)["area"] == "Dangkao"
      and "district added: Dangkao" in out, out)
set_entry_area(t3_id, ["Dangkao", "Sen Sok"])
t5 = clip("PP-434", dict(place_name="No District Yet Cafe", area="Dangkao"))
out = run(t5)
check("T4 old place with a list: read, saved back as one district (the first)",
      entry(t3_id)["area"] == "Dangkao" and "another district" not in out, out)
check("T5 old list with two districts: the one left out is named", "district saved as text (left out: Sen Sok)" in out, out)

set_entry_area(t3_id, "BKK1")
t6 = clip("PP-435", dict(place_name="No District Yet Cafe", place_name_alt=["No District Yet Cafe BKK1"]))
out = run(t6)
check("T6 hand-typed area that is not a district, clip with no district: kept, not erased",
      pid(t6) == t3_id and entry(t3_id)["area"] == "BKK1", out)
t7 = clip("PP-436", dict(place_name="No District Yet Cafe", area="Chamkar Mon"))
out = run(t7)
check("T7 hand-typed area that is not a district, clip with a district: replaced, and the report says so",
      entry(t3_id)["area"] == "Chamkar Mon" and 'district added: Chamkar Mon (was "BKK1", not a district)' in out, out)

# A place with a place_id, another name and another district: the district note every run, the name note once
wn = clip("PP-440", dict(place_name="Text Area Tea Shop", place_id=new_place, area="Dangkao"))
out1 = run(wn)
out2 = run(wn)
check("W5 1st run: new alias, other district and website name all said",
      "new aliases: Text Area Tea Shop" in out1 and 'another district "Dangkao"' in out1 and "website name stays" in out1, out1)
check("W5 2nd run: only the district note again, website name not repeated",
      'another district "Dangkao"' in out2 and "website name stays" not in out2, out2)

# A clip that already has its place_id and adds nothing new: the place file's area is still put right and saved
set_entry_area(t3_id, "ចំការមន")
out = run(t7)
check("T8 area typed in Khmer in the place file: saved as the English name, and the report says so",
      entry(t3_id)["area"] == "Chamkar Mon" and 'district written as in areas.json: "Chamkar Mon" (was "ចំការមន")' in out, out)
before = snap()
out = run(t7)
check("T8 R 2nd run: nothing changes, nothing said", snap() == before and "written as in areas.json" not in out, out)
set_entry_area(t3_id, " Chamkar Mon ")
run(t7)
check("T8b district with extra spaces: saved trimmed", entry(t3_id)["area"] == "Chamkar Mon", entry(t3_id))
t9 = clip("PP-437", dict(place_name="No District Yet Cafe"))
for old_area, want in [(["BKK1", "near market"], "BKK1"), ([], None), ([None, " "], None)]:
    set_entry_area(t3_id, old_area)
    out = run(t9)
    check(f"T9 old list with no district {old_area}, clip with none: saved as text {want!r}, not left a list",
          entry(t3_id)["area"] == want and "area saved as text" in out, out)
    before = snap()
    run(t9)
    check(f"T9 R {old_area}: 2nd run changes nothing", snap() == before)

# M. several people matching at once: ids from the Maps place code, one file per place
dup = clip("PP-450", dict(place_name="Hanjang Copy", place_id="new", google_maps_url=maps("Hanjang")))
before = snap()
out = run(dup)
check('M1 team wrote "new" but a known place has the same Maps link: unclear, says which id to write, "new" kept',
      pid(dup) == "new" and snap() == before
      and f'{HJ} is already used by "Hanjang Coffee & Eatery" (made from this Google Maps link). Same place: write {HJ}'
      in out and "A different place needs its own Maps link" in out, out)

PC1, PC2 = WORK / "pc1", WORK / "pc2"
for pc in (PC1, PC2):
    (pc / "clips").mkdir(parents=True)
x1 = clip("PP-500", dict(place_name="Shared Shop", google_maps_url=maps("Shared")), folder=PC1 / "clips")
y1 = clip("PP-501", dict(place_name="Only On One", google_maps_url=maps("One")), folder=PC1 / "clips")
x2 = clip("PP-600", dict(place_name="Shared Shop Cafe", google_maps_url=maps("Shared")), folder=PC2 / "clips")
y2 = clip("PP-601", dict(place_name="Only On Two", google_maps_url=maps("Two")), folder=PC2 / "clips")
run(x1, y1, places=PC1 / "places")
run(x2, y2, places=PC2 / "places")
check("M2 two computers at once: the same shop gets the same id, different shops different ids",
      pid(x1) == pid(x2) == new_id(maps("Shared")) and len({pid(x1), pid(y1), pid(y2)}) == 3, (pid(x1), pid(x2)))
check("M2 the two place folders share only the same shop's file (the one file git may need joined)",
      set(snap(PC1 / "places")) & set(snap(PC2 / "places")) == {f"{pid(x1)}.json"})

MIG = WORK / "mig"
(MIG / "clips").mkdir(parents=True)
old = MIG / "places.json"
OLD_ENTRY = {"place_id": "tvna_p_0001", "place_name": "Beans Barley", "aliases": ["Beans Barley", "Beans Bali"],
             "area": "Prampi Makara", "google_maps_url": "https://maps.app.goo.gl/83k2"}
OTHER = {"place_id": "tvna_p_0002", "place_name": "Untouched Bakery", "aliases": [], "area": None, "google_maps_url": None}
old.write_text(json.dumps([OLD_ENTRY, OTHER], ensure_ascii=False, indent=2), encoding="utf-8")
bc = clip("PP-700", dict(place_name="Beans and Barley", place_id="tvna_p_0001", area="Prampi Makara"), folder=MIG / "clips")
out = run(bc, places=MIG / "places", old=old)
moved = entry("tvna_p_0001", MIG / "places") if (MIG / "places/tvna_p_0001.json").exists() else {}
check("M3 first run: the old places.json is moved into one file per place, old file deleted, says so",
      not old.exists() and moved.get("place_name") == "Beans Barley" and moved.get("photos") == []
      and moved.get("aliases") == ["Beans Barley", "Beans Bali", "Beans and Barley"]
      and "moved 2 places from" in out and "is deleted: everything in it is in" in out and pid(bc) == "tvna_p_0001"
      and "Next: git add -A data/places data/clips data/results" in out, out)
check("M3 a place no clip touched is moved too (nothing lost when the old file is deleted)",
      (MIG / "places/tvna_p_0002.json").exists() and entry("tvna_p_0002", MIG / "places") == dict(OTHER, photos=[]))
before = snap(MIG / "places")
out = run(bc, places=MIG / "places", old=old)
check("M3 2nd run: nothing moved or changed", snap(MIG / "places") == before and "moved" not in out, out)
old.write_text(json.dumps([OLD_ENTRY, OTHER]), encoding="utf-8")
out = run(bc, places=MIG / "places", old=old)
check("M4 the old places.json comes back (git pull) with nothing new: deleted again, place files unchanged",
      not old.exists() and snap(MIG / "places") == before and "is deleted" in out, out)
LATE = {"place_id": "tvna_p_0005", "place_name": "Added On Old Code", "aliases": [], "area": None, "google_maps_url": None}
old.write_text(json.dumps([OLD_ENTRY, LATE]), encoding="utf-8")
late = clip("PP-702", dict(place_name="Added On Old Code", place_id="tvna_p_0005"), folder=MIG / "clips")
out = run(bc, late, places=MIG / "places", old=old)
check("M4b a teammate added a place to the old file (old code): it is moved in, nothing lost, then the old file goes",
      not old.exists() and entry("tvna_p_0005", MIG / "places")["place_name"] == "Added On Old Code"
      and "moved 1 place from" in out and "unknown_id (0)" in out, out)
old.write_text(json.dumps([{"place_id": "tvna_p_0005"}]), encoding="utf-8")
try:
    out = run(bc, places=MIG / "places", old=old)
    crashed = ""
except Exception as ex:  # noqa: BLE001
    out, crashed = "", repr(ex)
check("M4b an old entry with only a place_id: no crash, nothing lost, old file deleted", not crashed and not old.exists(),
      crashed or out)
before = snap(MIG / "places")
old.write_text(json.dumps([dict(OLD_ENTRY, aliases=["Beans Barley", "Only In The Old File"])]), encoding="utf-8")
out = run(bc, places=MIG / "places", old=old)
check("M4c the old file has a place that differs from its place file: old file kept, the team told what to do",
      old.exists() and snap(MIG / "places") == before and "tvna_p_0001 there differ" in out and "git rm" in out
      and "Next: git add data/places data/clips &&" in out, out)
before = snap(MIG / "places")
old.write_text(json.dumps([dict(OLD_ENTRY, google_maps_url="https://maps.app.goo.gl/other")]), encoding="utf-8")
out = run(bc, places=MIG / "places", old=old)
check("M4d the old file has another Maps link for a place: old file kept, said", old.exists()
      and snap(MIG / "places") == before and "tvna_p_0001 there differ" in out, out)
old.unlink(missing_ok=True)

for label, bad in [("an id that is a path", [dict(OLD_ENTRY, place_id="../evil")]),
                   ("two places with one id", [OLD_ENTRY, OLD_ENTRY]), ("not a list", {"a": 1})]:
    BAD = WORK / f"bad-{len(label)}"
    (BAD / "clips").mkdir(parents=True)
    (BAD / "places.json").write_text(json.dumps(bad), encoding="utf-8")
    bclip = clip("PP-701", dict(place_name="Beans Barley", place_id="tvna_p_0001"), folder=BAD / "clips")
    raw = bclip.read_bytes()
    out = run(bclip, places=BAD / "places", old=BAD / "places.json")
    check(f"M5 old places.json with {label}: refused, nothing written, nothing deleted",
          "Can't read" in out and "Nothing changed" in out and not (BAD / "places").exists()
          and (BAD / "places.json").exists() and bclip.read_bytes() == raw and not (WORK / "evil.json").exists(), out)

(MIG / "places/tvna_p_0003.json").write_text("{ broken", encoding="utf-8")
raw = bc.read_bytes()
out = run(bc, places=MIG / "places", old=old)
check("M6 a broken place file: names it, nothing changed", "Can't read" in out and "tvna_p_0003.json" in out
      and "Nothing changed" in out and bc.read_bytes() == raw, out)
(MIG / "places/tvna_p_0003.json").write_text(json.dumps({"place_id": "tvna_p_0004"}), encoding="utf-8")
out = run(bc, places=MIG / "places", old=old)
check("M6 a place file whose place_id is not its file name: refused", "must be the file name (tvna_p_0003)" in out, out)

(MIG / "places/tvna_p_0003.json").unlink()
(MIG / "places/beans_barley.json").write_text(json.dumps(OLD_ENTRY), encoding="utf-8")
out = run(bc, places=MIG / "places", old=old)
check("M6 a place file with another name (e.g. beans_barley.json): refused, says how to name it",
      "beans_barley.json: a place file is named after its place_id" in out and "Nothing changed" in out, out)
(MIG / "places/beans_barley.json").unlink()

files = snap()
ml = clip("PP-307", dict(place_name="List Link Lounge", google_maps_url=["https://maps.app.goo.gl/x"]))
try:
    out = run(ml)
    crashed = ""
except Exception as ex:  # noqa: BLE001
    out, crashed = "", repr(ex)
check("S2b google_maps_url typed as a list: no crash, no place made, told to add the link",
      not crashed and pid(ml) is None and snap() == files and "no Google Maps link" in out, crashed or out)

target = WORK / "save" / "x.json"
try:
    tc.save_json(target, {"bad": object()})
    raised = False
except TypeError:
    raised = True
check("M7 a save that fails part way leaves no .part file and no half file", raised
      and not target.exists() and not list((WORK / "save").glob("*.part")))
check("M7 no half-written (.part) file left anywhere", not list(WORK.rglob("*.part")), list(WORK.rglob("*.part")))
check("M8 the Next line tells the team to push right after matching", "git push" in run(bc, places=PC1 / "places"))

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
