"""Offline checks for stage3_transcribe.py with a fake Gemini client (no API calls)."""
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from types import SimpleNamespace

PIPE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPE))
from google.genai import errors, types  # noqa: E402
import stage3_transcribe as s3  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="tvna-test-"))
CLIPS, AUDIO = WORK / "clips", WORK / "audio"
CLIPS.mkdir(parents=True)
AUDIO.mkdir()
(WORK / "secret.env").write_text("GEMINI_API_KEY=not-a-real-key\n")

def make_wav(name, secs=2):
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={secs}", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                    str(AUDIO / name)], check=True)

DECOMPOSED = "e\u0301"          # "é" written as two code points, to check NFC
REPLY = f"សួស្តី ថ្ងៃនេះ\nWe go to Tea Kingdom {DECOMPOSED}\nវាឆ្ងាញ់ណាស់\nline four"

def api_error(code, status, message):
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, {"error": {"code": code, "message": message, "status": status}})

BUSY = lambda: api_error(503, "UNAVAILABLE", "This model is currently experiencing high demand.")  # noqa: E731

class ReadTimeout(Exception):
    pass

class FakeModels:
    def __init__(self):
        self.calls, self.plan, self.default = [], {}, REPLY
    def generate_content(self, model, contents, config=None):
        self.calls.append((model, contents, config))
        steps = self.plan.get(model) or []
        outcome = steps.pop(0) if steps else self.default
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)

class FakeFiles:
    def __init__(self):
        self.uploads, self.deletes = [], []
    def upload(self, file, config):
        self.uploads.append((file, config.mime_type))
        return SimpleNamespace(name="files/abc123")
    def delete(self, name):
        self.deletes.append(name)

FAKE = SimpleNamespace(models=FakeModels(), files=FakeFiles())
CLIENT_ARGS = []
def fake_client(**kw):
    CLIENT_ARGS.append(kw)
    return FAKE
s3.gemini_client = fake_client
SLEEPS = []
import tvna_common  # noqa: E402
tvna_common.time.sleep = SLEEPS.append

def clip(name, **over):
    c = json.loads((PIPE / "templates/tvna_clip_template.json").read_text())
    c.update(clip_id=name, audio_file=f"{name}.wav")
    c["source"].update(url="https://www.tiktok.com/@tester/video/1", platform="tiktok", creator="@tester")
    c.update(over)
    p = CLIPS / f"{name}.json"
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

def run(*args):
    sys.argv = ["stage3_transcribe.py", *map(str, args), "--audio-dir", str(AUDIO)]
    out, code = io.StringIO(), 0
    with contextlib.redirect_stdout(out):
        try:
            s3.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (print(e.code) or 1)
    return code, out.getvalue()

def reset(plan=None, default=REPLY):
    FAKE.models.calls.clear()
    FAKE.models.plan = plan or {}
    FAKE.models.default = default
    SLEEPS.clear()

results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     {detail}"))

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def show(title, out):
    print(f"----- {title} -----\n{out}" + "-" * (len(title) + 12))

# 1. normal run
make_wav("PP-002.wav")
p = clip("PP-002")
reset()
code, out = run(p)
c = load(p)
model, contents, config = FAKE.models.calls[-1]
check("1 normal: one call to gemini-3.8-flash, SDK retries off (attempts=1)",
      code == 0 and len(FAKE.models.calls) == 1 and model == "gemini-3.8-flash" and CLIENT_ARGS[-1] == {"attempts": 1}, out)
check("1 normal: 3-minute limit per try", config.http_options.timeout == 180000)
check("1 normal: prompt has the team rules + one sentence per line + no lyrics / [no speech]",
      "Write Khmer words in Khmer script." in contents[0] and "Put each sentence on its own line." in contents[0]
      and "Do not write song lyrics or background music." in contents[0]
      and "If nobody speaks, reply only: [no speech]" in contents[0])
check("1 normal: small WAV sent inline as audio/wav, no upload",
      isinstance(contents[1], types.Part) and contents[1].inline_data.mime_type == "audio/wav" and not FAKE.files.uploads)
check("1 normal: stt filled, transcript NFC",
      c["stt"] == {"tool": "gemini", "model": "gemini-3.8-flash", "settings": "km+en code-switching prompt v1",
                   "transcript": unicodedata.normalize("NFC", REPLY)}, c["stt"])
check("1 normal: nothing else changed", c["fields"] is None and c["audio_file"] == "PP-002.wav"
      and list(c.keys()) == list(json.loads((PIPE / "templates/tvna_clip_template.json").read_text()).keys()))
check("1 normal: preview + model + Next", "saved transcript (4 lines, gemini-3.8-flash)" in out
      and "  សួស្តី ថ្ងៃនេះ" in out and "  ..." in out and "line four" not in out
      and "Next: python stage4_extract_places.py" in out and not SLEEPS, out)
show("normal run", out)

# 2. again -> skipped
reset()
code, out = run(p)
check("2 again: skipped, no API call", code == 0 and "already has a transcript. Skipped." in out and not FAKE.models.calls, out)

# 3. --force --model: chosen model first, the other one as backup
reset(plan={"gemini-3.6-flash": [BUSY(), BUSY(), BUSY()]}, default="from 3.8")
code, out = run(p, "--force", "--model", "gemini-3.6-flash")
c = load(p)
check("3 --model gemini-3.6-flash: tried first, then gemini-3.8-flash as backup",
      code == 0 and [m for m, *_ in FAKE.models.calls] == ["gemini-3.6-flash"] * 3 + ["gemini-3.8-flash"]
      and c["stt"]["model"] == "gemini-3.8-flash" and c["stt"]["transcript"] == "from 3.8", out)

# 4. busy twice, then OK on try 3 (same model)
make_wav("PP-004.wav")
p4 = clip("PP-004")
reset(plan={"gemini-3.8-flash": [BUSY(), BUSY()]})
code, out = run(p4)
check("4 busy twice then OK: waits 10 s, 30 s, says so, keeps gemini-3.8-flash",
      code == 0 and SLEEPS == [10, 30] and load(p4)["stt"]["model"] == "gemini-3.8-flash"
      and "gemini-3.8-flash is busy (503), trying again in 10 s (2/3)" in out
      and "trying again in 30 s (3/3)" in out, out)
show("busy twice, then OK", out)

# 5. first model busy 3 times -> backup model does it
make_wav("PP-005.wav")
p5 = clip("PP-005")
reset(plan={"gemini-3.8-flash": [BUSY(), api_error(429, "RESOURCE_EXHAUSTED", "Quota"), BUSY()]})
code, out = run(p5)
c = load(p5)
check("5 first model stays busy: switches to gemini-3.6-flash, records it",
      code == 0 and c["stt"]["model"] == "gemini-3.6-flash" and SLEEPS == [10, 30]
      and "gemini-3.8-flash is still busy (503)." in out and "Trying gemini-3.6-flash instead ..." in out
      and "saved transcript (4 lines, gemini-3.6-flash)" in out, out)
show("first model busy, backup used", out)

# 6. every model busy -> clip unchanged, 'run again later'
make_wav("PP-006.wav")
p6 = clip("PP-006")
raw = p6.read_bytes()
reset(plan={"gemini-3.8-flash": [BUSY()] * 3, "gemini-3.6-flash": [BUSY()] * 3})
code, out = run(p6)
check("6 all busy: 6 tries, waits 10/30/10/30, clip unchanged, says run again later",
      code == 1 and len(FAKE.models.calls) == 6 and SLEEPS == [10, 30, 10, 30] and p6.read_bytes() == raw
      and "Gemini is busy (tried gemini-3.8-flash, gemini-3.6-flash). Run the same command again later" in out, out)
show("every model busy", out)

# 7. timeout / no answer -> retried like busy
reset(plan={"gemini-3.8-flash": [ReadTimeout("timed out")]})
code, out = run(p6)
check("7 no answer (timeout): retried, then OK", code == 0 and "is not answering (ReadTimeout), trying again in 10 s" in out
      and len(FAKE.models.calls) == 2, out)

# 8. non-busy error (bad key) -> stop at once, no backup
make_wav("PP-008.wav")
p8 = clip("PP-008")
raw = p8.read_bytes()
reset(plan={"gemini-3.8-flash": [api_error(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.")]})
code, out = run(p8)
check("8 bad API key (400): fails at once, no retry, no backup, clip unchanged",
      code == 1 and len(FAKE.models.calls) == 1 and not SLEEPS and p8.read_bytes() == raw
      and "Gemini failed: 400 INVALID_ARGUMENT: API key not valid." in out, out)

# 9. model not found (404) -> straight to the backup, no waiting
reset(plan={"gemini-3.8-flash": [api_error(404, "NOT_FOUND", "models/gemini-3.8-flash is not found")]})
code, out = run(p8)
check("9 model not found (404): straight to backup, no waits",
      code == 0 and not SLEEPS and load(p8)["stt"]["model"] == "gemini-3.6-flash" and "gemini-3.8-flash was not found." in out, out)

# 10. empty reply -> unchanged
make_wav("PP-010.wav")
p10 = clip("PP-010")
raw = p10.read_bytes()
for empty in (None, "   \n "):
    reset(default=empty)
    code, out = run(p10)
    check(f"10 empty reply ({empty!r}): error, clip unchanged",
          code == 1 and "Gemini returned no transcript" in out and p10.read_bytes() == raw, out)

# 10b. music only -> saved as [no speech], skipped next time
for i, reply in enumerate(("[no speech]", "[No speech].")):
    make_wav(f"PP-03{i}.wav")
    pm = clip(f"PP-03{i}")
    reset(default=reply)
    code, out = run(pm)
    check(f"10b music only ({reply!r}): saved as '[no speech]', clear message, Next still shown",
          code == 0 and load(pm)["stt"]["transcript"] == "[no speech]"
          and f"PP-03{i}: no speech (music only). Saved the transcript as [no speech]." in out
          and "Next: python stage4_extract_places.py" in out, out)
reset()
code, out = run(pm)
check("10b music-only clip: skipped next time, no API call", "Skipped" in out and not FAKE.models.calls, out)
make_wav("PP-032.wav")
reset(plan={"gemini-3.8-flash": ["[no speech]"]})
code, out = run(clip("PP-032"))
show("music only", out)

# 11. no audio / bad audio_file / broken WAV -> nothing sent
reset()
code, out = run(clip("PP-011", audio_file=None))
check("11a audio_file null: run stage 2 first", code == 1 and "No audio for this clip. Run stage 2 first" in out, out)
code, out = run(clip("PP-012"))
check("11b WAV missing (teammate's clip): run stage 2 first", code == 1 and "is missing. Run stage 2 first" in out, out)
code, out = run(clip("PP-013", audio_file="../secret.env"))
check("11c audio_file '../secret.env': refused", code == 1 and "should be a file name like PP-002.wav" in out, out)
(AUDIO / "PP-014.wav").write_bytes(b"not a wav")
code, out = run(clip("PP-014"))
check("11d broken WAV: clear message", code == 1 and "is not a valid WAV" in out, out)
check("11 none of these called Gemini", not FAKE.models.calls)

# 12. big WAV -> upload + delete, also when every model is busy
s3.INLINE_LIMIT = 1000
make_wav("PP-015.wav")
reset()
code, out = run(clip("PP-015"))
check("12a big WAV: uploaded as audio/wav, then deleted", code == 0 and FAKE.files.uploads[-1][1] == "audio/wav"
      and FAKE.files.deletes == ["files/abc123"], (out, FAKE.files.uploads, FAKE.files.deletes))
reset(plan={"gemini-3.8-flash": [BUSY()] * 3, "gemini-3.6-flash": [BUSY()] * 3})
code, out = run(clip("PP-016", audio_file="PP-015.wav"))
check("12b big WAV + all busy: uploaded once, still deleted", code == 1 and len(FAKE.files.uploads) == 2
      and FAKE.files.deletes == ["files/abc123", "files/abc123"], out)
s3.INLINE_LIMIT = 15 * 1024 * 1024

# 13. several clips, one fails
make_wav("PP-017.wav")
reset()
code, out = run(clip("PP-017"), clip("PP-018", audio_file=None))
check("13 several: summary, exit 1, Next lists only the OK clip",
      code == 1 and "Done: 1 made, 0 skipped, 1 failed (PP-018)" in out
      and "PP-017.json" in out.split("Next:")[-1] and "PP-018" not in out.split("Next:")[-1], out)

# 14. broken / missing clip file
bad = CLIPS / "PP-019.json"
bad.write_text("{ not json")
code, out = run(bad, CLIPS / "PP-404.json")
check("14 broken and missing clip files", code == 1 and out.count("Can't read the clip file") == 2, out)

# 16. --force guard
def with_places(name, **place_over):
    make_wav(f"{name}.wav")
    place = {"place_name": "Tea Kingdom", "verification_status": "needs_review", "cleaned_by": None,
             "segment_ids": [0, 1]}
    place.update(place_over)
    return clip(name, stt={"tool": "gemini", "model": "old", "settings": "x", "transcript": "old line"},
                extraction={"method": "llm", "model": "gemini-3.6-flash", "prompt_version": "v4"}, fields=[place])

p16 = with_places("PP-021", cleaned_by="Dara", verification_status="verified")
raw = p16.read_bytes()
reset()
code, out = run(p16, "--force")
check("16a reviewed place + --force: skipped, no API call, file unchanged",
      code == 0 and not FAKE.models.calls and p16.read_bytes() == raw
      and "PP-021: 1 place was reviewed by the team. Skipped, so their fixes are kept." in out, out)

p16b = with_places("PP-022")
reset()
code, out = run(p16b, "--force")
c = load(p16b)
check("16b not reviewed + --force: new transcript, old places cleared so stage 4 runs again",
      code == 0 and len(FAKE.models.calls) == 1 and c["stt"]["transcript"] == unicodedata.normalize("NFC", REPLY)
      and c["fields"] is None and c["extraction"] is None
      and "PP-022: old places cleared (they came from the old transcript). Stage 4 will find them again." in out, out)
check("16b key order kept", list(c.keys()) == list(json.loads((PIPE / "templates/tvna_clip_template.json").read_text()).keys()))

reset()
code, out = run(p, "--force")
check("16c no places yet + --force: no 'cleared' message", code == 0 and "cleared" not in out, out)

p16d = with_places("PP-023")
p16e = with_places("PP-024", cleaned_by="Sok", verification_status="rejected")
reset()
code, out = run(p16d, p16e, "--force")
check("16d mixed: one redone, the reviewed one skipped",
      code == 0 and "Done: 1 made, 1 skipped, 0 failed" in out and len(FAKE.models.calls) == 1
      and load(p16e)["fields"][0]["cleaned_by"] == "Sok", out)

# 17. TikTok caption: used only to spell names
CAPTION = "Comfortable and unique, best quality best memories.Welcome to Luv selfie booth 😉📸 #luvselfiebooth #IFL"
SOURCE = {"url": "https://www.tiktok.com/@tester/video/1", "platform": "tiktok", "creator": "@tester",
          "caption": CAPTION, "posted_at": None, "collected_at": None}
make_wav("PP-030.wav")
p17 = clip("PP-030", source=SOURCE)
reset()
code, out = run(p17)
model, contents, config = FAKE.models.calls[-1]
check("17a caption in the prompt, with the spelling-only rule", contents[0].startswith(s3.PROMPT)
      and CAPTION in contents[0] and "only to spell names you actually hear" in contents[0]
      and "Never write caption text that is not spoken" in contents[0], contents[0])
check("17a stt.settings records the caption", load(p17)["stt"]["settings"] == "km+en code-switching prompt v1 + caption",
      load(p17)["stt"])
check("17a says it uses the caption, no warning for a normal transcript",
      "using the caption for names" in out and "check it" not in out, out)

make_wav("PP-031.wav")
p17b = clip("PP-031")
reset()
code, out = run(p17b)
check("17b no caption: prompt and settings exactly as before",
      FAKE.models.calls[-1][1][0] == s3.PROMPT and load(p17b)["stt"]["settings"] == "km+en code-switching prompt v1"
      and "using the caption" not in out, out)

reset(default="Hello guys\nComfortable and unique, best quality, best memories!\nThank you")
code, out = run(p17, "--force")
check("17c caption sentence copied into the transcript: warning (punctuation/case ignored)",
      'check it: the transcript repeats the caption (fine if the speaker read it out): '
      '"Comfortable and unique, best quality best memories"' in out, out)

reset(default="Hello guys\nWelcome to Luv selfie booth\nThank you")
code, out = run(p17, "--force")
check("17d only the name in common: no warning", "check it" not in out, out)

reset(default="សួស្តី\nហាងនេះស្អាតណាស់ ហើយតម្លៃថោកទៀតផង\nបាយ")
km = clip("PP-032", source=dict(SOURCE, caption="ហាងនេះស្អាតណាស់ ហើយតម្លៃថោកទៀតផង 📸"))
make_wav("PP-032.wav")
code, out = run(km)
check("17e Khmer caption sentence copied (no spaces between words): warning too", "check it" in out, out)

# 15. no API key
def no_key(**kw):
    raise ValueError("No API key was provided.")
s3.gemini_client = no_key
code, out = run(clip("PP-020"))
check("15 no API key: clear message", code == 1 and "GEMINI_API_KEY is missing" in out, out)

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
