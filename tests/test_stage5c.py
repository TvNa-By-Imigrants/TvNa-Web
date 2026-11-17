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
                        verification_status="needs_review") | p for p in places]
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

a = clip("PP-002", dict(place_name="Hanjang Coffee & Eatery", area=["Chamkar Mon"]))
b = clip("PP-003", dict(place_name="ALWAYS selfie booth"))
out = run(a, b)
check("1 empty places.json: 2 new places, Next stage 6", pid(a) == "tvna_p_0001" and pid(b) == "tvna_p_0002"
      and "new (2):" in out and "Next: python stage6_build_final_dataset.py data/clips/*.json" in out, out)

c = clip("PP-010", dict(place_name="Han-Jan Coffee & Eatery", area=["Daun Penh"]))
out = run(c)
check("2 fuzzy 97%: matched, new spelling saved as alias, new district added", pid(c) == "tvna_p_0001"
      and 'fuzzy 97% like "Hanjang Coffee & Eatery"' in out and "Han-Jan Coffee & Eatery" in entry("tvna_p_0001")["aliases"]
      and entry("tvna_p_0001")["area"] == ["Chamkar Mon", "Daun Penh"], out)

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
check("5 team wrote the place_id: name saved as alias", "set by the team; new aliases: Luv selfie booth" in out
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

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
