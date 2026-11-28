"""Offline checks for stage2_get_audio.py with a fake yt-dlp (no internet)."""
import base64
import contextlib
import glob
import http.server
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
import wave
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path

PIPE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPE))
import yt_dlp  # noqa: E402
import stage2_get_audio as s2  # noqa: E402
import tvna_common as tc  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="tvna-test-"))
CLIPS, AUDIO, MEDIA = WORK / "clips", WORK / "audio", WORK / "media"
for d in (CLIPS, MEDIA):
    d.mkdir(parents=True)

def ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)

ff("-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=3",
   "-c:v", "libx264", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(MEDIA / "sound.mp4"))
ff("-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1", "-c:v", "libx264", str(MEDIA / "nosound.mp4"))
# A 1080x1920 cover with an EXIF block holding a made-up GPS note, to check it is removed
ff("-f", "lavfi", "-i", "color=c=green:s=1080x1920", "-frames:v", "1", str(MEDIA / "plain.jpg"))
plain = (MEDIA / "plain.jpg").read_bytes()
exif = b"Exif\x00\x00MM\x00\x2a\x00\x00\x00\x08\x00\x00TVNA-GPS-11.55N-104.92E"
(MEDIA / "cover.jpg").write_bytes(plain[:2] + b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif + plain[2:])

def width_of(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return int(out.strip() or 0)

# 2026-10-21 20:00 UTC = 2026-10-22 03:00 in Phnom Penh
TS = int(datetime(2026, 10, 21, 20, 0, tzinfo=timezone.utc).timestamp())

CAPTION = "Welcome to Tea Kingdom ☕ 📍 Toul Kork #phnompenh #milktea"

COVER_LINKS = ["https://p16.example/moving-cover.webp", "https://p16.example/cover.jpeg"]  # worst first, as yt-dlp sorts

class FakeYDL:
    mode = "sound"
    seen_opts = None
    caption = CAPTION
    downloads = 0
    cover = "ok"  # ok / none (TikTok has no cover) / fail (download fails) / broken (not a picture)
    cover_asks = []
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
        if download:
            FakeYDL.downloads += 1
            shutil.copy(MEDIA / f"{FakeYDL.mode}.mp4", self.opts["outtmpl"].replace("%(ext)s", "mp4"))
        info = {"timestamp": TS, "upload_date": "20261021", "description": FakeYDL.caption}
        if FakeYDL.cover != "none":
            info["thumbnails"] = [{"id": "dynamicCover", "url": COVER_LINKS[0]},
                                  {"id": "cover", "url": COVER_LINKS[1], "http_headers": {"Referer": "https://www.tiktok.com/"}}]
            info["thumbnail"] = COVER_LINKS[1]
        return info
    def urlopen(self, req):
        FakeYDL.cover_asks.append((req.url, dict(req.headers)))
        if FakeYDL.cover == "fail":
            raise yt_dlp.networking.exceptions.TransportError("timed out")
        if FakeYDL.cover == "broken":
            return io.BytesIO(b"<html>not a picture</html>")
        return open(MEDIA / "cover.jpg", "rb")

s2.yt_dlp.YoutubeDL = FakeYDL

# Fake Cloudinary on this computer; the real .env is never read, so no real key is used.
SECRET = "s3cr3t-never-print"
class FakeCloud(http.server.BaseHTTPRequestHandler):
    mode = "ok"  # ok / refuse
    uploads = []
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        msg = BytesParser(policy=policy.default).parsebytes(
            b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body)
        fields = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
                  for part in msg.iter_parts()}
        FakeCloud.uploads.append({"path": self.path, "auth": self.headers.get("Authorization"), "fields": fields})
        if FakeCloud.mode == "refuse":
            code, answer = 401, {"error": {"message": "Invalid Signature"}}
        elif FakeCloud.mode == "junk":
            code, answer = 200, []
        else:
            code, answer = 200, {"secure_url": "https://res.cloudinary.com/testcloud/image/upload/v1/"
                                               + fields["public_id"].decode() + ".jpg"}
        data = json.dumps(answer).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *a):
        pass

cloud = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeCloud)
threading.Thread(target=cloud.serve_forever, daemon=True).start()
CLOUD_API = f"http://127.0.0.1:{cloud.server_address[1]}/v1_1"
tc.CLOUDINARY_API = CLOUD_API
tc.ENV_FILE = WORK / "no.env"
KEYS = {"CLOUDINARY_CLOUD_NAME": "testcloud", "CLOUDINARY_API_KEY": "123456", "CLOUDINARY_API_SECRET": SECRET}
os.environ.update(KEYS)

def cover_link(name):
    return f"https://res.cloudinary.com/testcloud/image/upload/v1/tvna/covers/{name}.jpg"

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

ALL_OUTPUT = []

def run(*args):
    sys.argv = ["stage2_get_audio.py", *map(str, args), "--audio-dir", str(AUDIO)]
    out, code = io.StringIO(), 0
    with contextlib.redirect_stdout(out):
        try:
            s2.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (print(e.code) or 1)
    ALL_OUTPUT.append(out.getvalue())
    return code, out.getvalue()

results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     {detail}"))

def after_creator(clip):
    keys = list(clip["source"])
    return keys[keys.index("creator") + 1] if "creator" in keys[:-1] else None

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
check("1 normal: caption saved (hashtags kept), printed short", c["source"]["caption"] == CAPTION
      and f"  caption: {CAPTION}\n" in out and after_creator(c) == "caption",
      (c["source"], out))
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
      and "PP-012.json" in out.split("Next:")[-1].splitlines()[0] and "PP-013" not in out.split("Next:")[-1].splitlines()[0], out)
check("12 retry line: only the failed clip", "To try only the failed clip again: python " in out
      and "PP-013.json" in out.split("To try only")[-1] and "PP-012" not in out.split("To try only")[-1], out)
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

# 16. caption for a clip that already has its WAV (an old clip from before captions): no download
p16 = clip("PP-016")
run(p16)
c = load(p16)
del c["source"]["caption"]
p16.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
FakeYDL.downloads = 0
FakeYDL.caption = "ហាងកាហ្វេ  Luv selfie booth   #selfie"
code, out = run(p16)
c = load(p16)
check("16a WAV there, no caption: caption read with no download", code == 0 and FakeYDL.downloads == 0
      and c["source"]["caption"] == "ហាងកាហ្វេ  Luv selfie booth   #selfie" and "saved the caption" in out
      and "no download" in out, (c["source"], out))
check("16a caption key put right after creator", after_creator(c) == "caption",
      list(c["source"]))
check("16a Khmer caption is NFC", c["source"]["caption"] == unicodedata.normalize("NFC", c["source"]["caption"]))
code, out = run(p16)
check("16b caption there: skipped, no TikTok call", "Skipped" in out and FakeYDL.downloads == 0, out)

long = "Best Korean food in town " * 4
FakeYDL.caption = long
p16l = clip("PP-019")
code, out = run(p16l)
check("16 long caption: whole caption saved, printed cut at 60 with …", load(p16l)["source"]["caption"] == long.strip()
      and f"  caption: {long[:60]} …" in out, out)

FakeYDL.caption = "   "
p16c = clip("PP-017")
code, out = run(p16c)
check("16c empty caption saved as null, says so", load(p16c)["source"]["caption"] is None
      and "caption: none (the video has no caption)" in out, out)
FakeYDL.seen_opts = None
code, out = run(p16c)
check("16c video with no caption, run again: skipped, TikTok not asked again", code == 0 and "Skipped" in out
      and FakeYDL.seen_opts is None and "saved the caption" not in out, out)

FakeYDL.caption = None
p16d = clip("PP-018")
run(p16d)
c = load(p16d)
del c["source"]["caption"]  # a clip made before captions existed
p16d.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
FakeYDL.mode = "fail"
raw = p16d.read_bytes()
code, out = run(p16d)
FakeYDL.mode = "sound"
check("16d caption read fails (video gone): message, skipped not failed, clip unchanged, stage 3 still next",
      code == 0 and p16d.read_bytes() == raw and "couldn't read the caption. Download failed" in out
      and "Skipped; nothing changed" in out and f"Next: python stage3_transcribe.py {p16d}" in out, out)
FakeYDL.caption = CAPTION

# R. run it twice: every kind of value -> the 2nd run changes nothing and doesn't ask TikTok
MISSING = object()
FakeYDL.mode, FakeYDL.caption = "sound", CAPTION
n = 0
for audio_kind in ["WAV there", "null", '""', "missing"]:
    for cap_kind, cap in [("filled", "Old caption"), ("null", None), ('""', ""), ("missing", MISSING)]:
        n += 1
        name = f"PP-1{n:02d}"
        p = clip(name)
        c = load(p)
        if audio_kind == "WAV there":
            shutil.copyfile(AUDIO / "PP-002.wav", AUDIO / f"{name}.wav")
            c["audio_file"] = f"{name}.wav"
        elif audio_kind == "missing":
            del c["audio_file"]
        else:
            c["audio_file"] = None if audio_kind == "null" else ""
        if cap is MISSING:
            del c["source"]["caption"]
        else:
            c["source"]["caption"] = cap
        p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
        FakeYDL.seen_opts, downloads = None, FakeYDL.downloads
        run(p)
        asked, downloaded = FakeYDL.seen_opts is not None, FakeYDL.downloads > downloads
        if audio_kind != "WAV there":
            first = asked and downloaded
        elif cap_kind in ("filled", "null"):
            first = not asked and load(p)["source"]["caption"] == cap
        else:
            first = asked and not downloaded and load(p)["source"]["caption"] == CAPTION
        check(f"R audio_file {audio_kind}, caption {cap_kind}: 1st run "
              + ("downloads" if audio_kind != "WAV there" else
                 "skipped" if cap_kind in ("filled", "null") else "reads the caption only (no download)"), first)
        raw = p.read_bytes()
        FakeYDL.seen_opts = None
        code, out = run(p)
        check(f"R audio_file {audio_kind}, caption {cap_kind}: 2nd run skipped, TikTok not asked, file unchanged",
              code == 0 and "Skipped" in out and FakeYDL.seen_opts is None and p.read_bytes() == raw, out)

# C. TikTok cover -> Cloudinary -> source.cover_url
def write(p, c):
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")

def after(clip, key):
    keys = list(clip["source"])
    return keys[keys.index(key) + 1] if key in keys[:-1] else None

FakeYDL.mode, FakeYDL.caption, FakeYDL.cover, FakeCloud.mode = "sound", CAPTION, "ok", "ok"
FakeCloud.uploads.clear()
FakeYDL.cover_asks.clear()
pc = clip("PP-201")
code, out = run(pc)
c = load(pc)
up = FakeCloud.uploads[-1] if FakeCloud.uploads else {"fields": {}}
check("C1 new clip: cover_url = the Cloudinary link, right after caption", code == 0
      and c["source"]["cover_url"] == cover_link("PP-201") and after(c, "caption") == "cover_url"
      and f"  cover: {cover_link('PP-201')}" in out, (c["source"], out))
check("C1 upload: one call to /v1_1/testcloud/image/upload, fixed public_id, overwrite",
      len(FakeCloud.uploads) == 1 and up["path"] == "/v1_1/testcloud/image/upload"
      and up["fields"].get("public_id") == b"tvna/covers/PP-201" and up["fields"].get("overwrite") == b"true", up)
check("C1 upload: Basic login with key:secret", up.get("auth") == "Basic " + base64.b64encode(f"123456:{SECRET}".encode()).decode())
(WORK / "sent.jpg").write_bytes(up["fields"].get("file") or b"")
sent = (WORK / "sent.jpg").read_bytes()
check("C1 the sent picture is a JPG, 720 px wide (from 1080)", sent[:2] == b"\xff\xd8" and width_of(WORK / "sent.jpg") == 720,
      width_of(WORK / "sent.jpg"))
check("C1 EXIF removed (the GPS note is not in the sent picture)", b"Exif" not in sent and b"TVNA-GPS" not in sent
      and b"TVNA-GPS" in (MEDIA / "cover.jpg").read_bytes())
check("C1 TikTok's best cover asked first, with its headers", FakeYDL.cover_asks[:1] == [(COVER_LINKS[1], {"Referer": "https://www.tiktok.com/"})],
      FakeYDL.cover_asks)

raw = pc.read_bytes()
FakeYDL.seen_opts, n_up = None, len(FakeCloud.uploads)
code, out = run(pc)
check("C2 run again: skipped, TikTok and Cloudinary not asked, file unchanged", code == 0 and "Skipped" in out
      and FakeYDL.seen_opts is None and len(FakeCloud.uploads) == n_up and pc.read_bytes() == raw, out)

# C3 an old clip (WAV and caption, no cover_url key): cover only, no download
c = load(pc)
del c["source"]["cover_url"]
c["source"]["caption"] = "Caption saved earlier"  # TikTok's caption differs now; the saved one is kept
write(pc, c)
downloads, n_up = FakeYDL.downloads, len(FakeCloud.uploads)
code, out = run(pc)
c = load(pc)
check("C3 old clip, no cover_url: cover saved with no video download, caption kept", code == 0
      and FakeYDL.downloads == downloads and len(FakeCloud.uploads) == n_up + 1
      and c["source"]["cover_url"] == cover_link("PP-201") and c["source"]["caption"] == "Caption saved earlier"
      and after(c, "caption") == "cover_url" and "reading the cover from TikTok (no download)" in out, (c["source"], out))
raw = pc.read_bytes()
FakeYDL.seen_opts = None
code, out = run(pc)
check("C3 run again: skipped, no TikTok call", "Skipped" in out and FakeYDL.seen_opts is None and pc.read_bytes() == raw, out)

# C4 caption "" and cover missing: one TikTok call reads both
c = load(pc)
c["source"]["caption"] = ""
del c["source"]["cover_url"]
write(pc, c)
downloads = FakeYDL.downloads
code, out = run(pc)
c = load(pc)
check("C4 caption \"\" + no cover: one call reads both, no download", code == 0 and FakeYDL.downloads == downloads
      and c["source"]["caption"] == CAPTION and c["source"]["cover_url"] == cover_link("PP-201")
      and "reading the caption and cover" in out, (c["source"], out))

# C5 TikTok has no cover -> null, done
FakeYDL.cover = "none"
p5c = clip("PP-202")
code, out = run(p5c)
c = load(p5c)
check("C5 no cover on TikTok: cover_url null, says so", code == 0 and c["source"]["cover_url"] is None
      and "cover: none (TikTok has no cover picture" in out, (c["source"], out))
FakeYDL.seen_opts = None
code, out = run(p5c)
check("C5 run again: skipped, TikTok not asked again", "Skipped" in out and FakeYDL.seen_opts is None, out)
FakeYDL.cover = "ok"

# C6 cover download fails on an old clip: skipped, nothing changed; the next run tries again
c = load(pc)
del c["source"]["cover_url"]
write(pc, c)
raw = pc.read_bytes()
FakeYDL.cover = "fail"
code, out = run(pc)
check("C6 cover download fails (old clip): message, skipped, exit 0, file unchanged", code == 0 and pc.read_bytes() == raw
      and "cover: not saved, couldn't download it (TransportError: timed out). The next run tries again." in out
      and "Skipped; nothing changed" in out and "Next: python stage3_transcribe.py" in out, out)
FakeYDL.cover = "ok"
code, out = run(pc)
check("C6 next run (TikTok answers): cover saved", load(pc)["source"]["cover_url"] == cover_link("PP-201"), out)

# C7 cover download fails on a new clip: the WAV is still made, cover_url stays null
FakeYDL.cover = "fail"
p7c = clip("PP-203")
code, out = run(p7c)
c = load(p7c)
FakeYDL.cover = "ok"
check("C7 cover fails on a new clip: WAV made, cover_url \"\" (to try again), exit 0", code == 0
      and c["audio_file"] == "PP-203.wav" and c["source"]["cover_url"] == "" and "cover: not saved" in out, (c, out))
downloads = FakeYDL.downloads
code, out = run(p7c)
check("C7 next run: the cover is tried again and saved, no video download", FakeYDL.downloads == downloads
      and load(p7c)["source"]["cover_url"] == cover_link("PP-203"), out)

# C8-C11 bad answers from Cloudinary or a bad picture: clip unchanged
def cover_fails(name, label, wanted):
    p = clip(name)
    shutil.copyfile(AUDIO / "PP-002.wav", AUDIO / f"{name}.wav")
    c = load(p)
    c["audio_file"] = f"{name}.wav"
    c["source"].update(caption=CAPTION, posted_at="2026-10-22")
    del c["source"]["cover_url"]
    write(p, c)
    raw = p.read_bytes()
    code, out = run(p)
    check(label, code == 0 and p.read_bytes() == raw and wanted in out and "The next run tries again" in out, out)

FakeCloud.mode = "refuse"
cover_fails("PP-204", "C8 Cloudinary refuses (wrong key): its reason shown, clip unchanged", "Cloudinary answered 401: Invalid Signature")
FakeCloud.mode = "ok"
tc.CLOUDINARY_API = "http://127.0.0.1:9/v1_1"
cover_fails("PP-205", "C9 Cloudinary can't be reached: says so, clip unchanged", "no connection to Cloudinary")
tc.CLOUDINARY_API = CLOUD_API
FakeYDL.cover = "broken"
cover_fails("PP-206", "C10 TikTok sends something that is not a picture: says so, clip unchanged", "can't read this picture")
FakeYDL.cover = "ok"
old_max, s2.IMAGE_MAX_BYTES = s2.IMAGE_MAX_BYTES, 100
cover_fails("PP-207", "C11 picture over 20 MB: refused, clip unchanged", "the picture is over 20 MB")
s2.IMAGE_MAX_BYTES = old_max

# C12 no Cloudinary keys: said, never asks TikTok just for the cover
for k in KEYS:
    del os.environ[k]
p12 = clip("PP-208")
code, out = run(p12)
c = load(p12)
check("C12 no keys, new clip: WAV made, cover_url \"\", says the keys are missing", code == 0
      and c["audio_file"] == "PP-208.wav" and c["source"]["cover_url"] == ""
      and "the Cloudinary keys are not in .env" in out, out)
raw = p12.read_bytes()
for i in (1, 2):
    FakeYDL.seen_opts = None
    code, out = run(p12)
    check(f"C12 no keys, run {i} again: skipped, keys note, no TikTok call, file unchanged", code == 0
          and "Skipped" in out and "the Cloudinary keys are not in .env" in out and FakeYDL.seen_opts is None
          and p12.read_bytes() == raw, out)
os.environ.update(KEYS)
code, out = run(p12)
check("C12 keys added: the next run saves the cover", load(p12)["source"]["cover_url"] == cover_link("PP-208"), out)

# C13 --force: the cover is uploaded again under the same name (replaced, not copied)
n_up = len(FakeCloud.uploads)
code, out = run(pc, "--force")
check("C13 --force: cover uploaded again with the same public_id", code == 0 and len(FakeCloud.uploads) == n_up + 1
      and FakeCloud.uploads[-1]["fields"]["public_id"] == b"tvna/covers/PP-201"
      and load(pc)["source"]["cover_url"] == cover_link("PP-201"), out)

# C14 --force without keys: a saved null ("TikTok has no cover") stays null
p14c = clip("PP-209")
FakeYDL.cover = "none"
run(p14c)
FakeYDL.cover = "ok"
for k in KEYS:
    del os.environ[k]
code, out = run(p14c, "--force")
os.environ.update(KEYS)
check("C14 --force, no keys: cover_url null kept (not turned into \"\")", code == 0
      and load(p14c)["source"]["cover_url"] is None, (load(p14c)["source"], out))

# C15 Cloudinary answers 200 but not with a link: message, no crash, clip unchanged
FakeCloud.mode = "junk"
cover_fails("PP-210", "C15 Cloudinary answers [] instead of a link: says so, no crash", "Cloudinary gave no link back")
FakeCloud.mode = "ok"

# R2. run it twice: every kind of cover_url, with and without the WAV
n = 0
for audio_kind in ["WAV there", "no WAV"]:
    for cov_kind, cov in [("link", "https://res.cloudinary.com/x/old.jpg"), ("null", None), ('""', ""), ("missing", MISSING)]:
        n += 1
        name = f"PP-3{n:02d}"
        p = clip(name)
        c = load(p)
        if audio_kind == "WAV there":
            shutil.copyfile(AUDIO / "PP-002.wav", AUDIO / f"{name}.wav")
            c["audio_file"] = f"{name}.wav"
            c["source"]["caption"] = CAPTION
        if cov is MISSING:
            del c["source"]["cover_url"]
        else:
            c["source"]["cover_url"] = cov
        write(p, c)
        FakeYDL.seen_opts, n_up = None, len(FakeCloud.uploads)
        run(p)
        got = load(p)["source"].get("cover_url", MISSING)
        if cov_kind == "link":
            first, said = got == cov and len(FakeCloud.uploads) == n_up, "keeps the link, no upload"
        elif audio_kind == "WAV there" and cov_kind == "null":
            first, said = got is None and FakeYDL.seen_opts is None, "skipped (null = no cover)"
        else:
            first, said = got == cover_link(name) and len(FakeCloud.uploads) == n_up + 1, "saves the cover"
        check(f"R2 {audio_kind}, cover_url {cov_kind}: 1st run {said}", first, (got, n_up, len(FakeCloud.uploads)))
        raw = p.read_bytes()
        FakeYDL.seen_opts, n_up = None, len(FakeCloud.uploads)
        code, out = run(p)
        check(f"R2 {audio_kind}, cover_url {cov_kind}: 2nd run skipped, no TikTok or Cloudinary call, file unchanged",
              code == 0 and "Skipped" in out and FakeYDL.seen_opts is None and len(FakeCloud.uploads) == n_up
              and p.read_bytes() == raw, out)

check("the Cloudinary secret is never printed", not any(SECRET in o for o in ALL_OUTPUT))
check("template: cover_url right after caption, null", after(json.loads((PIPE / "templates/tvna_clip_template.json").read_text()), "caption")
      == "cover_url")

cloud.shutdown()
print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
