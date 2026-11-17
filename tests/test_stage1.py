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

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
