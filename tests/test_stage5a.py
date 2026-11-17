"""Offline checks for stage5a_dedupe_clips.py: every kind of source.url (filled, null, "", missing), run twice."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

PIPE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPE))
import stage5a_dedupe_clips as s5a  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="tvna-test-"))
CLIPS = WORK / "clips"
DUPS = CLIPS / "duplicates"
CLIPS.mkdir(parents=True)
MISSING = object()
VIDEO = "https://www.tiktok.com/@tester/video/7000000000000000001"

results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     {detail}"))

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def clip(name, url=MISSING, source=MISSING):
    c = load(PIPE / "templates/tvna_clip_template.json")
    c["clip_id"] = name
    if url is MISSING:
        del c["source"]["url"]
    else:
        c["source"]["url"] = url
    if source is not MISSING:
        c["source"] = source
    if source is None and name == "PP-010":
        del c["source"]
    p = CLIPS / f"{name}.json"
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

def run(*paths):
    sys.argv = ["stage5a_dedupe_clips.py", *map(str, paths or sorted(CLIPS.glob("*.json")))]
    out, code = io.StringIO(), 0
    with contextlib.redirect_stdout(out):
        try:
            s5a.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue()

def snapshot():
    return {p: p.read_bytes() for p in WORK.rglob("*.json")}

clip("PP-001", VIDEO)
clip("PP-002", VIDEO + "?is_from_webapp=1&sender_device=pc")  # same video, tracking parts
clip("PP-003", "https://www.tiktok.com/@other/video/7000000000000000002")
clip("PP-004", None)
clip("PP-005", "")
clip("PP-006")  # url missing
clip("PP-007", source=None)
clip("PP-008", source={})
clip("PP-009", VIDEO.replace("www.", ""))  # same video, no www
clip("PP-010", source=None)  # source missing
first_args = sorted(CLIPS.glob("*.json"))

code, out = run()
moved = sorted(p.name for p in DUPS.glob("*.json"))
check("1 same video (tracking parts, no www) -> moved to duplicates/", code == 0 and moved == ["PP-002.json", "PP-009.json"],
      (moved, out))
check("2 moved clips get duplicate_of = the kept clip",
      all(load(DUPS / n).get("duplicate_of") == "PP-001" for n in moved) and (CLIPS / "PP-001.json").exists(), out)
check('3 url null / "" / missing, source null / {} / missing -> "no url, not checked", not moved',
      "no url, not checked (6)" in out and all((CLIPS / f"PP-00{n}.json").exists() for n in range(4, 9))
      and (CLIPS / "PP-010.json").exists(), out)

before = snapshot()
code, out = run()
check("R 2nd run (same glob): nothing moved, no file changed", code == 0 and "moved (0)" in out and snapshot() == before,
      out)
code, out = run(*first_args)
check("R 2nd run with the same file list (moved files are gone): no crash, nothing changed",
      code == 0 and "moved (0)" in out and snapshot() == before and "PP-002.json: not found" in out, out)

# 4. the same file given twice (e.g. two globs that overlap) is one clip, not a duplicate of itself
before = snapshot()
code, out = run(CLIPS / "PP-001.json", CLIPS / ".." / "clips" / "PP-001.json", *sorted(CLIPS.glob("PP-00*.json")))
check("4 same file given twice: not moved, nothing changed", code == 0 and "moved (0)" in out and snapshot() == before,
      out)

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
