"""Offline checks for stage1_new_clip.py (fake network): new clip, duplicates, every kind of value, run twice."""
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

WORK = Path(tempfile.mkdtemp(prefix="tvna-test-"))
CLIPS = WORK / "clips"
MISSING = object()
VIDEO = "https://www.tiktok.com/@tester/video/7000000000000000001"

# Fake network: ROUTES maps a URL to where it redirects. Anything else = no connection. NET counts every call.
ROUTES, NET = {}, []
class FakeOpener:
    def open(self, request, timeout=None):
        NET.append(request.full_url)
        target = ROUTES.get(request.full_url)
        if target is None:
            raise urllib.error.URLError("offline")
        headers = email.message.Message()
        headers["Location"] = target
        raise urllib.error.HTTPError(request.full_url, 302, "Found", headers, None)
tc.urllib.request.build_opener = lambda *a: FakeOpener()
ROUTES["https://vt.tiktok.com/ZSshort1/"] = VIDEO + "?is_from_webapp=1"

results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     {detail}"))

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def run(*args, clips_dir=CLIPS):
    sys.argv = ["stage1_new_clip.py", *map(str, args), "--clips-dir", str(clips_dir)]
    out, code = io.StringIO(), 0
    NET.clear()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            s1.main()
        except SystemExit as e:
            code = 0 if e.code is None else e.code if isinstance(e.code, int) else 1
            if not isinstance(e.code, int) and e.code is not None:
                out.write(str(e.code))
    return code, out.getvalue()

def snapshot(folder=CLIPS):
    return {p: p.read_bytes() for p in Path(folder).rglob("*.json")}

# 1. new clip
code, out = run(VIDEO + "?is_from_webapp=1&lang=en", "--posted-at", "2026-10-22")
p1 = CLIPS / "PP-001.json"
c1 = load(p1) if p1.exists() else {}
check("1 full link -> PP-001, link cleaned, creator and posted_at saved, no network",
      code == 0 and c1.get("clip_id") == "PP-001" and c1["source"]["url"] == VIDEO
      and c1["source"]["creator"] == "@tester" and c1["source"]["posted_at"] == "2026-10-22" and not NET, out)
check('2 new clip has caption null (stage 2 fills it) and the template\'s other fields',
      "caption" in c1.get("source", {}) and c1["source"]["caption"] is None and c1.get("audio_file") is None, c1)

# R. the same video again: refused, nothing created, no network
before = snapshot()
for kind, link in [("same link", VIDEO), ("tracking parts", VIDEO + "?lang=km"), ("no www", VIDEO.replace("www.", ""))]:
    code, out = run(link)
    check(f"R {kind}: duplicate of PP-001, nothing created or changed, no network",
          code == 1 and "Duplicate: same video as PP-001" in out and snapshot() == before and not NET, out)
code, out = run("https://vt.tiktok.com/ZSshort1/")
check("R short link to the same video: expanded (1 call to TikTok, no download), duplicate, nothing created",
      code == 1 and "Duplicate: same video as PP-001" in out and snapshot() == before
      and NET == ["https://vt.tiktok.com/ZSshort1/"], (out, NET))

# 3. other clips with every kind of value: url / source / clip_id filled, null, "" or missing
def other(name, url=MISSING, source=MISSING, clip_id=MISSING, folder=CLIPS):
    c = load(PIPE / "templates/tvna_clip_template.json")
    c["clip_id"] = name if clip_id is MISSING else clip_id
    if clip_id == "drop":
        del c["clip_id"]
    if url is MISSING:
        del c["source"]["url"]
    else:
        c["source"]["url"] = url
    if source == "drop":
        del c["source"]
    elif source is not MISSING:
        c["source"] = source
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")

other("PP-002", None)
other("PP-003", "")
other("PP-004")
other("PP-005", source=None)
other("PP-006", source="drop")
other("PP-007", None, clip_id=None)
other("PP-008", None, clip_id="")
other("PP-009", None, clip_id="drop")
other("PP-012", "https://www.tiktok.com/@other/video/7000000000000000012", folder=CLIPS / "duplicates")
before = snapshot()
code, out = run("https://www.tiktok.com/@new/video/7000000000000000099")
check('3 url / source / clip_id null, "" or missing in other clips: read fine; next id counts duplicates/ too',
      code == 0 and (CLIPS / "PP-013.json").exists() and not NET, out)
check("3b other clips not changed", all(p.read_bytes() == b for p, b in before.items()), out)
code, out = run("https://www.tiktok.com/@other/video/7000000000000000012")
check("3c a video already in duplicates/ is a duplicate too", code == 1 and "same video as PP-012" in out, out)

# 4. refused input: nothing created
before = snapshot()
for kind, args in [("not TikTok", ["https://www.youtube.com/watch?v=abc"]),
                   ("short link offline", ["https://vt.tiktok.com/ZSoffline/"]),
                   ("bad date", [VIDEO.replace("01", "77"), "--posted-at", "22-10-2026"])]:
    code, out = run(*args)
    check(f"4 {kind}: refused, nothing created", code != 0 and snapshot() == before, out)
(CLIPS / "PP-050.json").write_text("{ not json", encoding="utf-8")
before = snapshot()
code, out = run(VIDEO.replace("01", "78"))
check("4 broken clip file in the folder: refused, says which file, nothing created",
      code == 1 and "PP-050.json" in out and snapshot() == before, out)

# 5. single link also saves the video id
check("5 single link: source.video_id saved", c1.get("source", {}).get("video_id") == "7000000000000000001", c1)

# F. --from-file: every link checked before any clip is created
FILES = WORK / "files"
FILES.mkdir()
C2 = WORK / "clips2"
A = "https://www.tiktok.com/@a/video/7100000000000000001"
B = "https://www.tiktok.com/@b/video/7100000000000000002"
OLD = "https://www.tiktok.com/@old/video/7100000000000000003"
DUP = "https://www.tiktok.com/@dup/video/7100000000000000004"
ROUTES["https://vt.tiktok.com/ZSnewB/"] = B + "?is_from_webapp=1"
ROUTES["https://vm.tiktok.com/ZSsameA/"] = A
other("PP-001", OLD, folder=C2)
other("PP-002", None, folder=C2)
other("PP-003", "", folder=C2)
other("PP-004", folder=C2)
other("PP-005", source=None, folder=C2)
other("PP-007", DUP, folder=C2 / "duplicates")

def links_file(name, lines, bom=False, newline="\n"):
    path = FILES / name
    path.write_bytes(("\ufeff" if bom else "").encode() + newline.join(lines).encode("utf-8"))
    return path

LIST = links_file("links.txt", [
    "# links from Sokha, 2026-11-18",          # 1 comment
    "",                                         # 2 blank
    A + "?is_from_webapp=1&lang=en",            # 3 new
    "   ",                                      # 4 spaces only
    A.replace("www.", ""),                      # 5 same as line 3
    "https://vt.tiktok.com/ZSnewB/  cafe in BKK",  # 6 short link -> B, note after it
    "https://vm.tiktok.com/ZSsameA/",           # 7 short link -> A
    OLD + "?lang=km",                           # 8 already PP-001
    DUP,                                        # 9 already in duplicates/
    "https://www.youtube.com/watch?v=abc",      # 10 not TikTok
    "https://vt.tiktok.com/ZSoffline/",         # 11 short link, can't expand
    "PP-009",                                   # 12 not a link
], bom=True, newline="\r\n")

before = snapshot(C2)
code, out = run("--from-file", LIST, "--check-only", clips_dir=C2)
shorts = ["https://vt.tiktok.com/ZSnewB/", "https://vm.tiktok.com/ZSsameA/", "https://vt.tiktok.com/ZSoffline/"]
check("F1 --check-only: nothing created or changed; only short links ask TikTok",
      snapshot(C2) == before and sorted(NET) == sorted(shorts), (out, NET))
check("F1 report: 2 new (lines 3, 6), 4 duplicates, 3 bad; BOM, CRLF, blank, spaces and # lines ignored",
      "12 links" not in out and "9 links" in out and "new videos, to create (2)" in out and "Fix the bad links in the file.\n" in out + "\n"
      and "line 3: " + A in out and "line 6: " + B in out
      and "duplicates, not created (4)" in out and "-> same video as line 3" in out and "line 5: " + A.replace("www.", "") in out
      and "line 7: https://vm.tiktok.com/ZSsameA/ -> same video as line 3" in out and "line 8: " + OLD + "?lang=km -> same video as PP-001\n" in out
      and "line 9: " + DUP + " -> same video as PP-007 (in duplicates/)" in out
      and "bad links, not created (3)" in out and "line 10: https://www.youtube.com/watch?v=abc -> only TikTok" in out
      and "line 11: https://vt.tiktok.com/ZSoffline/ -> couldn't expand" in out and "line 12: PP-009 -> only TikTok" in out
      and "Run again without --check-only" in out and code == 1, out)

code, out = run("--from-file", LIST, clips_dir=C2)
n8, n9 = C2 / "PP-008.json", C2 / "PP-009.json"
c8, c9 = (load(n8) if n8.exists() else {}), (load(n9) if n9.exists() else {})
check("F2 real run: only the 2 new videos created, numbered after duplicates/ (PP-008, PP-009), file order",
      sorted(p.name for p in C2.glob("*.json")) == ["PP-001.json", "PP-002.json", "PP-003.json", "PP-004.json",
                                                     "PP-005.json", "PP-008.json", "PP-009.json"]
      and c8.get("source", {}).get("url") == A and c9.get("source", {}).get("url") == B, out)
check("F2 new clips: clean link, video_id, creator, posted_at null, collected_at today",
      c8["source"]["video_id"] == "7100000000000000001" and c9["source"]["video_id"] == "7100000000000000002"
      and c8["source"]["creator"] == "@a" and c8["source"]["posted_at"] is None
      and c8["source"]["collected_at"] == s1.date.today().isoformat() and c8["clip_id"] == "PP-008", (c8, c9))
check("F2 report names the clips; Next lists both; other clips not changed; exit 1 for the bad links",
      "line 3 -> PP-008: " + A in out and "line 6 -> PP-009: " + B + " (expanded from https://vt.tiktok.com/ZSnewB/)" in out
      and "stage2_get_audio.py " in out and "PP-008.json" in out.split("Next:")[-1]
      and all(p.read_bytes() == b for p, b in before.items()) and code == 1, out)

before = snapshot(C2)
code, out = run("--from-file", LIST, clips_dir=C2)
check("F3 run twice: 0 created, nothing changed, the 2 new ones are now duplicates; only short links ask TikTok",
      snapshot(C2) == before and "new videos, created (0)" in out and "duplicates, not created (6)" in out
      and "line 3: " + A + "?is_from_webapp=1&lang=en -> same video as PP-008" in out and "line 6: https://vt.tiktok.com/ZSnewB/ -> same video as PP-009" in out
      and sorted(NET) == sorted(shorts) and "Next:" not in out, (out, NET))

GOOD = links_file("good.txt", ["https://www.tiktok.com/@c/video/7100000000000000010"])
code, out = run("--from-file", GOOD, clips_dir=C2)
check("F4 all links fine: exit 0, PP-010 created, no network", code == 0 and (C2 / "PP-010.json").exists()
      and not NET and "Next: python stage2_get_audio.py" in out, out)

before = snapshot(C2)
for kind, path in [("empty file", links_file("empty.txt", [])),
                   ("only comments and blanks", links_file("comments.txt", ["# nothing yet", "", "  "])),
                   ("missing file", FILES / "nope.txt")]:
    code, out = run("--from-file", path, clips_dir=C2)
    check(f"F5 {kind}: refused, nothing created", code == 1 and snapshot(C2) == before, out)
bad_bytes = FILES / "latin1.txt"
bad_bytes.write_bytes(b"https://www.tiktok.com/@c/video/7100000000000000011 caf\xe9")
code, out = run("--from-file", bad_bytes, clips_dir=C2)
check("F5 not UTF-8: refused, says the file, nothing created",
      code == 1 and "latin1.txt" in out and snapshot(C2) == before, out)

for kind, args in [("link and --from-file", [A, "--from-file", GOOD]),
                   ("no link", []),
                   ("--posted-at with --from-file", ["--from-file", GOOD, "--posted-at", "2026-10-22"]),
                   ("--check-only with one link", ["https://www.tiktok.com/@c/video/7100000000000000012", "--check-only"])]:
    code, out = run(*args, clips_dir=C2)
    check(f"F6 {kind}: usage error, nothing created", code == 2 and snapshot(C2) == before and not NET, out)

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
