"""Offline checks for stage2_get_audio.py with a fake yt-dlp (no internet)."""
import contextlib
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path

PIPE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPE))
import yt_dlp  # noqa: E402
import stage2_get_audio as s2  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="tvna-test-"))
CLIPS, AUDIO, MEDIA = WORK / "clips", WORK / "audio", WORK / "media"
for d in (CLIPS, MEDIA):
    d.mkdir(parents=True)

def ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)

ff("-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=3",
   "-c:v", "libx264", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(MEDIA / "sound.mp4"))
ff("-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1", "-c:v", "libx264", str(MEDIA / "nosound.mp4"))

# 2026-10-21 20:00 UTC = 2026-10-22 03:00 in Phnom Penh
TS = int(datetime(2026, 10, 21, 20, 0, tzinfo=timezone.utc).timestamp())

class FakeYDL:
    mode = "sound"
    seen_opts = None
    def __init__(self, opts):
        self.opts = opts
        FakeYDL.seen_opts = opts
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def extract_info(self, url, download):
        if FakeYDL.mode == "fail":
            raise yt_dlp.utils.DownloadError("ERROR: [TikTok] 7000000000000000001: Video not available")
        shutil.copy(MEDIA / f"{FakeYDL.mode}.mp4", self.opts["outtmpl"].replace("%(ext)s", "mp4"))
        return {"timestamp": TS, "upload_date": "20261021"}

s2.yt_dlp.YoutubeDL = FakeYDL

def clip(name, **over):
    c = json.loads((PIPE / "templates/tvna_clip_template.json").read_text())
    c["clip_id"] = name
    c["source"].update(url="https://www.tiktok.com/@tester/video/7000000000000000001", platform="tiktok",
                       creator="@tester", collected_at="2026-11-12")
    for k, v in over.items():
        if k in c["source"]:
            c["source"][k] = v
        else:
            c[k] = v
    p = CLIPS / f"{name}.json"
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

def run(*args):
    sys.argv = ["stage2_get_audio.py", *map(str, args), "--audio-dir", str(AUDIO)]
    out, code = io.StringIO(), 0
    with contextlib.redirect_stdout(out):
        try:
            s2.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (print(e.code) or 1)
    return code, out.getvalue()

results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     {detail}"))

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

before_tmp = set(glob.glob(os.path.join(tempfile.gettempdir(), "tvna-*")))

# 1. normal run
p = clip("PP-002")
code, out = run(p)
c = load(p)
w = AUDIO / "PP-002.wav"
with wave.open(str(w)) as wf:
    shape = (wf.getframerate(), wf.getnchannels(), wf.getsampwidth(), round(wf.getnframes() / 16000, 1))
check("1 normal: WAV made, 16 kHz mono 16-bit ~3 s", code == 0 and shape == (16000, 1, 2, 3.0), (code, shape, out))
check("1 normal: audio_file = PP-002.wav", c["audio_file"] == "PP-002.wav", c["audio_file"])
check("1 normal: posted_at in Cambodia time = 2026-10-22", c["source"]["posted_at"] == "2026-10-22", c["source"])
check("1 normal: other fields unchanged", c["stt"]["transcript"] is None and c["source"]["creator"] == "@tester")
check("1 normal: prints saved + posted_at + Next", "saved" in out and "posted_at: 2026-10-22 (from TikTok)" in out
      and "Next: python stage3_transcribe.py" in out, out)
check("1 normal: yt-dlp asks for the video file ('best', not the separate TikTok sound), quiet logger", FakeYDL.seen_opts["format"] == "best"
      and isinstance(FakeYDL.seen_opts["logger"], s2._QuietLogger))
check("1 normal: no .part file left", not list(AUDIO.glob("*.part")))
print("----- output of a normal run -----\n" + out + "----------------------------------")

# 2. again -> skipped
FakeYDL.seen_opts = None
code, out = run(p)
check("2 again: skipped, no download", code == 0 and "Skipped" in out and FakeYDL.seen_opts is None, out)

# 3. --force -> made again, posted_at kept
w.write_bytes(b"old")
code, out = run(p, "--force")
check("3 --force: WAV made again", code == 0 and w.stat().st_size > 1000, out)

# 4. posted_at already set -> kept
p4 = clip("PP-004", posted_at="2026-01-05")
code, out = run(p4)
check("4 posted_at set by hand is kept", load(p4)["source"]["posted_at"] == "2026-01-05" and "posted_at:" not in out, out)

# 5. download fails -> clip unchanged
p5 = clip("PP-005")
raw = p5.read_bytes()
FakeYDL.mode = "fail"
code, out = run(p5)
FakeYDL.mode = "sound"
check("5 download fails: message + exit 1 + clip unchanged",
      code == 1 and "Download failed: [TikTok] 7000000000000000001: Video not available" in out
      and "deleted or private" in out and "Nothing changed in" in out and p5.read_bytes() == raw
      and not (AUDIO / "PP-005.wav").exists(), out)
print("----- output of a failed download -----\n" + out + "---------------------------------------")

# 6. video with no sound
p6 = clip("PP-006")
FakeYDL.mode = "nosound"
code, out = run(p6)
FakeYDL.mode = "sound"
check("6 no sound: clear message", code == 1 and "The video has no sound" in out and load(p6)["audio_file"] is None, out)

# 7-11. bad clip files
code, out = run(clip("PP-007", url=None))
check("7 no url: says run stage 1", code == 1 and "Run stage 1 first" in out, out)
code, out = run(clip("PP-008", url="https://www.youtube.com/watch?v=abc"))
check("8 not a TikTok link: refused", code == 1 and "not a TikTok video link" in out, out)
bad = CLIPS / "PP-009.json"
bad.write_text("{ not json", encoding="utf-8")
code, out = run(bad)
check("9 broken JSON: can't read", code == 1 and "Can't read the clip file" in out, out)
code, out = run(CLIPS / "PP-404.json")
check("10 missing file: can't read", code == 1 and "Can't read the clip file" in out, out)
code, out = run(clip("../evil"))
check("11 bad clip_id: refused, no file outside audio/", code == 1 and "is not like PP-001" in out
      and not (WORK / "evil.wav").exists(), out)

# 12. several clips, one fails
FakeYDL.mode = "sound"
pa, pb = clip("PP-012"), clip("PP-013", url=None)
code, out = run(pa, pb)
check("12 several: summary, exit 1, Next lists only the OK clip",
      code == 1 and "Done: 1 made, 0 skipped, 1 failed (PP-013)" in out
      and "PP-012.json" in out.split("Next:")[-1] and "PP-013" not in out.split("Next:")[-1], out)
print("----- output of two clips, one failing -----\n" + out + "--------------------------------------------")

# 13. audio_file set but WAV missing (teammate pulled the clip, WAVs are not in git)
p14 = clip("PP-014", audio_file="PP-014.wav")
code, out = run(p14)
check("13 audio_file set, WAV missing: made again", code == 0 and (AUDIO / "PP-014.wav").exists(), out)

# 14. temp folders cleaned up
after_tmp = set(glob.glob(os.path.join(tempfile.gettempdir(), "tvna-*")))
check("14 temp folders deleted", after_tmp == before_tmp, after_tmp - before_tmp)

# 15. ffmpeg missing
old_path = os.environ["PATH"]
os.environ["PATH"] = "/usr/bin:/bin"
code, out = run(clip("PP-015"))
os.environ["PATH"] = old_path
check("15 ffmpeg missing: clear message", code == 1 and "ffmpeg is not installed" in out, out)

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
