"""Offline checks for stage4_extract_places.py with a fake Gemini client (no API calls)."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

PIPE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPE))
from google.genai import errors  # noqa: E402
import tvna_common  # noqa: E402
import stage4_extract_places as s4  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="tvna-test-"))
CLIPS = WORK / "clips"
CLIPS.mkdir(parents=True)
ANSWERS = WORK / "answers"

TRANSCRIPT = ("Today we visit Tea Kingdom in Chamkar Mon.\n"
              "The milk tea is so good and only $2.\n"
              "Follow our channel for more!")

def place(**over):
    p = dict(place_name="Tea Kingdom", category="cafe", area=["Chamkar Mon"],
             speaker_opinion="Very good milk tea at a low price.", price_range="$2",
             confidence=s4.FieldConfidence(place_name="high", category="high", price_range="high", area="high"),
             evidence_text="Tea Kingdom", segment_ids=[0, 1])
    p.update(over)
    return s4.PlaceItem(**p)

def answer(*places):
    return SimpleNamespace(parsed=s4.ExtractionResponse(places=list(places)), text=None)

def api_error(code, status, message):
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, {"error": {"code": code, "message": message, "status": status}})

BUSY = lambda: api_error(503, "UNAVAILABLE", "This model is currently experiencing high demand.")  # noqa: E731

class FakeModels:
    def __init__(self):
        self.calls, self.plan, self.default = [], {}, None
    def generate_content(self, model, contents, config=None):
        self.calls.append((model, contents, config))
        steps = self.plan.get(model) or []
        outcome = steps.pop(0) if steps else self.default
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

FAKE = SimpleNamespace(models=FakeModels())
CLIENT_ARGS = []
def fake_client(**kw):
    CLIENT_ARGS.append(kw)
    return FAKE
s4.gemini_client = fake_client
SLEEPS = []
tvna_common.time.sleep = SLEEPS.append

def reset(plan=None, default=None):
    FAKE.models.calls.clear()
    FAKE.models.plan = plan or {}
    FAKE.models.default = default if default is not None else answer(place())
    SLEEPS.clear()

def clip(name, transcript=TRANSCRIPT, **over):
    c = json.loads((PIPE / "templates/tvna_clip_template.json").read_text())
    c.update(clip_id=name, audio_file=f"{name}.wav")
    c["stt"].update(tool="gemini", model="gemini-3.6-flash", settings="x", transcript=transcript)
    c.update(over)
    p = CLIPS / f"{name}.json"
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

def run(*args):
    sys.argv = ["stage4_extract_places.py", *map(str, args), "--answers-dir", str(ANSWERS)]
    out, code = io.StringIO(), 0
    with contextlib.redirect_stdout(out):
        try:
            s4.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (print(e.code) or 1)
    return code, out.getvalue()

results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     {detail}"))

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

def show(title, out):
    print(f"----- {title} -----\n{out}" + "-" * (len(title) + 12))

# 1. normal run
p = clip("PP-002")
reset()
code, out = run(p)
c = load(p)
model, contents, config = FAKE.models.calls[-1]
check("1 normal: one call to gemini-3.6-flash, SDK retries off", code == 0 and len(FAKE.models.calls) == 1
      and model == "gemini-3.6-flash" and CLIENT_ARGS[-1] == {"attempts": 1}, out)
check("1 normal: same prompt v5 + JSON schema, 3-minute limit",
      config.system_instruction == s4.SYSTEM and config.response_schema is s4.ExtractionResponse
      and config.response_mime_type == "application/json" and config.http_options.timeout == 180000
      and "[0] Today we visit Tea Kingdom in Chamkar Mon." in contents)
check("1 normal: extraction records the real model",
      c["extraction"] == {"method": "llm", "model": "gemini-3.6-flash", "prompt_version": "v5"}, c["extraction"])
f = c["fields"][0] if c["fields"] else {}
check("1 normal: place saved with checks (area, completeness, status)",
      len(c["fields"]) == 1 and f["place_name"] == "Tea Kingdom" and f["area"] == ["Chamkar Mon"]
      and f["completeness"] == 1.0 and f["verification_status"] == "auto_added" and f["place_id"] is None
      and f["flags"] == [], f)
check("1 normal: key order kept (extraction right before fields), stt untouched",
      list(c.keys())[-3:] == ["extraction", "fields", "notes"] and c["stt"]["transcript"] == TRANSCRIPT, list(c.keys()))
check("1 normal: prints places + Next stage 5a on all clips",
      "PP-002: 1 place found (gemini-3.6-flash)" in out and "  - Tea Kingdom (cafe): auto_added" in out
      and "Next: python stage5a_dedupe_clips.py data/clips/*.json" in out, out)
show("normal run", out)

# 2. again -> skipped; --force -> redone
reset()
code, out = run(p)
check("2 again: skipped, no API call", code == 0 and "already has places. Skipped." in out and not FAKE.models.calls, out)
reset(default=answer(place(), place(place_name="Brown Coffee", area=None, evidence_text="Brown Coffee")))
code, out = run(p, "--force")
check("2 --force: found again (2 places)", code == 0 and len(load(p)["fields"]) == 2 and "2 places found" in out, out)

# 3. busy -> backup model, recorded
p3 = clip("PP-003")
reset(plan={"gemini-3.6-flash": [BUSY(), BUSY(), BUSY()]})
code, out = run(p3)
check("3 first model busy: waits shown, gemini-3.8-flash used and recorded",
      code == 0 and SLEEPS == [10, 30] and load(p3)["extraction"]["model"] == "gemini-3.8-flash"
      and "gemini-3.6-flash is busy (503), trying again in 10 s (2/3)" in out
      and "Trying gemini-3.8-flash instead ..." in out, out)
show("first model busy, backup used", out)

# 4. all busy -> unchanged
p4 = clip("PP-004")
raw = p4.read_bytes()
reset(plan={"gemini-3.6-flash": [BUSY()] * 3, "gemini-3.8-flash": [BUSY()] * 3})
code, out = run(p4)
check("4 all busy: clip unchanged, 'run again later'", code == 1 and p4.read_bytes() == raw
      and "Gemini is busy (tried gemini-3.6-flash, gemini-3.8-flash). Try this clip again later." in out, out)

# 5. parts: a normal TikTok (33 sentences, like PP-002) is one part; 80 sentences are 2 parts
reset()
p33 = clip("PP-033", transcript="\n".join(f"Sentence number {i} about Tea Kingdom." for i in range(33)))
code, out = run(p33)
check("5a 33 sentences: one part, one call (Gemini sees the whole video)",
      code == 0 and len(FAKE.models.calls) == 1 and "[32] Sentence number 32" in FAKE.models.calls[0][1], out)

long_text = "\n".join(f"Sentence number {i} about Tea Kingdom." for i in range(80))
p5 = clip("PP-005", transcript=long_text)
raw = p5.read_bytes()
reset(plan={"gemini-3.6-flash": [answer(place(segment_ids=[0])), BUSY(), BUSY(), BUSY()],
            "gemini-3.8-flash": [BUSY()] * 3})
code, out = run(p5)
check("5b 2nd part busy: nothing half-saved", code == 1 and p5.read_bytes() == raw and len(FAKE.models.calls) == 7, out)

part1 = place(area=None, area_description=None, price_range=None, menu_items=["milk tea"], segment_ids=[0, 1],
              confidence=s4.FieldConfidence(place_name="high", category="high"),
              missing_reasons=s4.MissingReasons(area="not mentioned", price_range="not mentioned"))
part2 = place(area=["Chamkar Mon"], area_description="Toul Tompoung", price_range="$2",
              menu_items=["milk tea", "bubble waffle"], speaker_opinion="Another opinion.", category="restaurant",
              evidence_text="Sentence number 55", segment_ids=[55, 999],
              confidence=s4.FieldConfidence(place_name="high", category="high", price_range="high", area="medium"))
reset(plan={"gemini-3.6-flash": [answer(part1), answer(part2)]})
code, out = run(p5)
f = load(p5)["fields"]
m = f[0] if f else {}
check("5c 80 sentences: 2 parts (0-59, 50-79), one place", code == 0 and len(FAKE.models.calls) == 2
      and "[0] Sentence" in FAKE.models.calls[0][1] and "[59] Sentence" in FAKE.models.calls[0][1]
      and "[60] Sentence" not in FAKE.models.calls[0][1]
      and "[50] Sentence" in FAKE.models.calls[1][1] and "[79] Sentence" in FAKE.models.calls[1][1] and len(f) == 1, out)
check("5c merge: empty details filled from part 2 (district, location, price)",
      m.get("area") == ["Chamkar Mon"] and m.get("area_description") == "Toul Tompoung" and m.get("price_range") == "$2"
      and m["confidence"]["area"] == "medium" and m["confidence"]["price_range"] == "high", m)
check("5c merge: lists combined without repeats, filled details kept",
      m.get("menu_items") == ["milk tea", "bubble waffle"] and m.get("speaker_opinion") == "Very good milk tea at a low price."
      and m.get("category") == "cafe" and m.get("evidence_text") == "Tea Kingdom", m)
check("5c merge: sentence ids combined (bad id 999 dropped), 'why missing' notes cleaned",
      m.get("segment_ids") == [0, 1, 55] and m.get("missing_reasons") == {}, m)
check("5c merge: score and status redone (was 0.67 needs_review -> 1.0 auto_added)",
      m.get("completeness") == 1.0 and m.get("missing_fields") == [] and m.get("verification_status") == "auto_added", m)

# 6. no transcript / [no speech]
code, out = run(clip("PP-006", transcript=None))
check("6a no transcript: run stage 3 first", code == 1 and "No transcript yet. Run stage 3 first" in out, out)
reset()
p6 = clip("PP-007", transcript="[no speech]")
code, out = run(p6)
check("6b [no speech], no caption: skipped, no API call, fields stay null",
      code == 0 and "no speech and no caption, so no places to find. Skipped." in out and not FAKE.models.calls
      and load(p6)["fields"] is None, out)

# 7. answer as JSON text / broken answer
reset(default=SimpleNamespace(parsed=None, text=json.dumps({"places": [place().model_dump()]})))
p7 = clip("PP-008")
code, out = run(p7)
check("7a answer only as JSON text: still read", code == 0 and load(p7)["fields"][0]["place_name"] == "Tea Kingdom", out)
p8 = clip("PP-009")
raw = p8.read_bytes()
reset(default=SimpleNamespace(parsed=None, text="sorry, no JSON"))
code, out = run(p8)
check("7b broken answer: clear message, clip unchanged",
      code == 1 and "did not answer in the expected format" in out and p8.read_bytes() == raw, out)

# 8. --model, bad key, missing file
reset(plan={"gemini-3.8-flash": [BUSY()] * 3})
code, out = run(clip("PP-010"), "--model", "gemini-3.8-flash")
check("8a --model gemini-3.8-flash: tried first, 3.6 as backup",
      [m for m, *_ in FAKE.models.calls] == ["gemini-3.8-flash"] * 3 + ["gemini-3.6-flash"], out)
reset(plan={"gemini-3.6-flash": [api_error(400, "INVALID_ARGUMENT", "API key not valid.")]})
code, out = run(clip("PP-011"))
check("8b bad API key: fails at once", code == 1 and len(FAKE.models.calls) == 1
      and "Gemini failed: 400 INVALID_ARGUMENT: API key not valid." in out, out)
code, out = run(CLIPS / "PP-404.json")
check("8c missing clip file: can't read", code == 1 and "Can't read the clip file" in out, out)

# 9. several clips: summary + Next
reset()
code, out = run(clip("PP-012"), clip("PP-013", transcript=None))
check("9 several: summary, exit 1, Next stage 5a", code == 1 and "Done: 1 made, 0 skipped, 1 failed (PP-013)" in out
      and "Next: python stage5a_dedupe_clips.py data/clips/*.json" in out, out)
retry = out.split("To try only the failed clip again: ")[-1].strip()
check("9 retry line: only the failed clip, same options", retry == f"python stage4_extract_places.py "
      f"{CLIPS / 'PP-013.json'} --answers-dir {ANSWERS}", retry)
reset(plan={"gemini-3.6-flash": [answer(place())] + [BUSY()] * 3, "gemini-3.8-flash": [BUSY()] * 3})
done, busy = clip("PP-014"), clip("PP-015")
code, out = run(done, busy, "--force")
retry = out.split("To try only the failed clip again: ")[-1].strip()
check("9 busy with --force: retry line keeps --force and leaves out the clip that worked (so it isn't redone)",
      code == 1 and retry == f"python stage4_extract_places.py {busy} --force --answers-dir {ANSWERS}"
      and "Run the same command again" not in out, out)

# 11. --force guard: places the team reviewed are never redone
def reviewed_clip(name, **place_over):
    p = clip(name)
    reset()
    run(p)
    c = load(p)
    c["fields"][0].update(place_over)
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

p11 = reviewed_clip("PP-030", place_name="Luv selfie booth", cleaned_by="Dara", verification_status="verified")
raw = p11.read_bytes()
reset()
code, out = run(p11, "--force")
check("11a reviewed (cleaned_by + verified) + --force: skipped, no API call, file unchanged",
      code == 0 and not FAKE.models.calls and p11.read_bytes() == raw
      and "PP-030: 1 place was reviewed by the team. Skipped, so their fixes are kept." in out, out)
code, out = run(p11)
check("11b reviewed, no --force: same message (doesn't suggest --force)",
      "reviewed by the team" in out and "Use --force" not in out and not FAKE.models.calls, out)

p11c = reviewed_clip("PP-031", cleaned_by="Dara", verification_status="rejected")
p11d = reviewed_clip("PP-032", verification_status="verified")
reset()
code, out = run(p11c, p11d, "--force")
check("11c team 'rejected' (cleaned_by) and 'verified' without a name: both kept",
      code == 0 and not FAKE.models.calls and out.count("reviewed by the team") == 2
      and "Done: 0 made, 2 skipped, 0 failed" in out, out)

p11e = clip("PP-033b")
reset()
run(p11e)
reset(default=answer(place(place_name="Tea Kingdom 2")))
code, out = run(p11e, "--force")
check("11d not reviewed (needs_review/auto_added) + --force: redone as before",
      code == 0 and len(FAKE.models.calls) == 1 and load(p11e)["fields"][0]["place_name"] == "Tea Kingdom 2", out)

two = clip("PP-034")
reset(default=answer(place(), place(place_name="Other Cafe", evidence_text="Today")))
run(two)
c = load(two)
c["fields"][0]["cleaned_by"] = "Dara"
c["fields"][1]["cleaned_by"] = "Sok"
two.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
reset()
code, out = run(two, "--force")
check("11e two reviewed places: plural message", "PP-034: 2 places were reviewed by the team." in out, out)

# 12. Gemini's first answer is kept in answers/, untouched by the team review
p12 = clip("PP-040")
reset()
run(p12)
ans = ANSWERS / "PP-040.json"
a = load(ans) if ans.exists() else {}
check("12a answer saved: same places and extraction as the clip", a.get("clip_id") == "PP-040"
      and a.get("fields") == load(p12)["fields"] and a.get("extraction") == load(p12)["extraction"], a)
c = load(p12)
c["fields"][0].update(place_name="Tea Kingdom Fixed", cleaned_by="Dara", verification_status="verified")
p12.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
raw = ans.read_bytes()
reset()
run(p12, "--force")
check("12b team fixed the clip: answer keeps Gemini's name, --force doesn't touch it",
      ans.read_bytes() == raw and load(ans)["fields"][0]["place_name"] == "Tea Kingdom")
p12c = clip("PP-041")
reset()
run(p12c)
reset(default=answer(place(place_name="Other Name")))
run(p12c, "--force")
check("12c --force on a clip not reviewed: answer replaced too", load(ANSWERS / "PP-041.json")["fields"][0]["place_name"] == "Other Name")
p12d = clip("PP-042")
reset(plan={"gemini-3.6-flash": [BUSY()] * 3, "gemini-3.8-flash": [BUSY()] * 3})
run(p12d)
p12e = clip("PP-043", transcript="[no speech]")
reset()
run(p12e)
check("12d busy failure / [no speech]: no answer file", not (ANSWERS / "PP-042.json").exists()
      and not (ANSWERS / "PP-043.json").exists())

# 10. no API key
def no_key(**kw):
    raise ValueError("No API key was provided.")
s4.gemini_client = no_key
code, out = run(clip("PP-014"))
check("10 no API key: clear message", code == 1 and "GEMINI_API_KEY is missing" in out, out)

# R. run it twice: every kind of value -> the 2nd run changes nothing and doesn't call Gemini
s4.gemini_client = fake_client  # test 'no API key' above swapped it out
MISSING = object()
for i, (kind, fields, transcript, first_calls) in enumerate([
        ("fields filled", "RUN", TRANSCRIPT, 1),
        ("fields [] (ran, no places)", [], TRANSCRIPT, 0),
        ("fields null", None, TRANSCRIPT, 1),
        ('fields ""', "", TRANSCRIPT, 1),
        ("fields missing", MISSING, TRANSCRIPT, 1),
        ("[no speech]", None, "[no speech]", 0)]):
    name = f"PP-1{i:02d}"
    p = clip(name, transcript=transcript)
    c = load(p)
    if fields is MISSING:
        del c["fields"]
    elif fields != "RUN":
        c["fields"] = fields
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    reset()
    run(p)
    calls = len(FAKE.models.calls)
    ans = ANSWERS / f"{name}.json"
    raw, ans_raw = p.read_bytes(), (ans.read_bytes() if ans.exists() else None)
    reset()
    code, out = run(p)
    check(f"R {kind}: 1st run {first_calls} Gemini call(s); 2nd run skipped, no call, clip and answer unchanged",
          calls == first_calls and code == 0 and "Skipped" in out and not FAKE.models.calls
          and p.read_bytes() == raw and (ans.read_bytes() if ans.exists() else None) == ans_raw, out)

# C. the TikTok caption (prompt v5)
CAPTION = "Comfortable and unique, best quality.Welcome to Luv selfie booth 😉📸 #luvselfiebooth #IFL @sponsor"
HEARD = ("Today we go to ALWAYS selfie booth.\n"
         "You can take many photos here.\n"
         "Follow for more!")

def with_caption(name, caption, transcript=HEARD):
    p = clip(name, transcript=transcript)
    c = load(p)
    if caption is MISSING:
        del c["source"]["caption"]
    else:
        c["source"]["caption"] = caption
    p.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

def luv(**over):
    return place(**dict(dict(place_name="Luv selfie booth", place_name_alt=["ALWAYS selfie booth"],
                             category="entertainment", area=None, price_range=None,
                             evidence_text="Welcome to Luv selfie booth", segment_ids=[0, 1]), **over))

check("C1 prompt v5 says how to use the caption",
      "TIKTOK CAPTION" in s4.SYSTEM and "the caption's spelling" in s4.SYSTEM and "Moon Night Noodle House" in s4.SYSTEM
      and "name_source" in s4.SYSTEM
      and "A hashtag or an @account alone is never a place" in s4.SYSTEM and s4.PROMPT_VERSION == "v5")

pc = with_caption("PP-500", CAPTION)
reset(default=answer(luv()))
code, out = run(pc)
f = (load(pc)["fields"] or [{}])[0]
sent = FAKE.models.calls[-1][1] if FAKE.models.calls else ""
check("C2 caption sent to Gemini after the numbered transcript",
      sent.startswith("Transcript excerpt:\n[0] Today we go to ALWAYS selfie booth.")
      and sent.endswith(f"\n\nTikTok caption (written by the creator; it has no segment ids):\n<caption>\n{CAPTION}\n</caption>"),
      sent)
check("C2 caption spelling is the name, heard spelling kept in place_name_alt",
      f.get("place_name") == "Luv selfie booth" and f.get("place_name_alt") == ["ALWAYS selfie booth"], f)
check("C2 name only in the caption -> flag name_from_caption; evidence found in the caption -> no evidence flag",
      "name_from_caption" in f.get("flags", []) and "evidence_not_found_in_transcript" not in f.get("flags", []), f)
check("C2 printed: name from caption, also called …",
      "Luv selfie booth (entertainment): needs_review, name from caption; also called ALWAYS selfie booth" in out, out)

for i, (kind, cap) in enumerate([("null", None), ("spaces", "   ")]):
    q = with_caption(f"PP-51{i}", cap)
    reset()
    run(q)
    sent = FAKE.models.calls[-1][1] if FAKE.models.calls else ""
    check(f"C3 caption {kind} (video has none): no caption block sent", "TikTok caption" not in sent and "[0] Today" in sent,
          sent)
for i, (kind, cap) in enumerate([('""', ""), ("missing", MISSING)]):
    q = with_caption(f"PP-51{i + 5}", cap)
    raw = q.read_bytes()
    reset()
    code, out = run(q)
    first_calls = len(FAKE.models.calls)
    reset()
    code2, out2 = run(q)
    check(f"C3 caption {kind} (not read yet): refused twice, run stage 2 first, no Gemini call, clip unchanged",
          code == code2 == 1 and "The TikTok caption hasn't been read yet. Run stage 2" in out
          and "write null in source.caption" in out and first_calls == 0 and not FAKE.models.calls
          and q.read_bytes() == raw, out)

q = with_caption("PP-520", "Tea Kingdom 🍵", transcript=TRANSCRIPT)
reset()
run(q)
f = load(q)["fields"][0]
check("C4 name said and in the caption -> no name_from_caption", "name_from_caption" not in f["flags"], f)
q = with_caption("PP-521", CAPTION)
reset(default=answer(luv(evidence_text="Brown Coffee is the best")))
run(q)
f = load(q)["fields"][0]
check("C4 evidence in neither the transcript nor the caption -> evidence_not_found_in_transcript",
      "evidence_not_found_in_transcript" in f["flags"], f)
q = with_caption("PP-522", "Our new spot 📍 Brown Coffee, Toul Kork")
reset(default=answer(place(place_name="Brown Coffee", evidence_text="Brown Coffee, Toul Kork", segment_ids=[])))
run(q)
f = load(q)["fields"][0]
check("C5 speech video, place named only in the caption, no sentence ids -> name_from_caption, no no_valid_segment_ids",
      "name_from_caption" in f["flags"] and "no_valid_segment_ids" not in f["flags"] and f["segment_ids"] == [], f)

# [no speech] + caption: read from the caption only
pn = with_caption("PP-530", CAPTION, transcript="[no speech]")
reset(default=answer(luv(place_name_alt=[], segment_ids=[])))
code, out = run(pn)
c = load(pn)
f = (c["fields"] or [{}])[0]
sent = FAKE.models.calls[-1][1] if FAKE.models.calls else ""
check("C6 [no speech] + caption: one call, Gemini told nobody speaks, caption sent",
      code == 0 and len(FAKE.models.calls) == 1 and sent.startswith("Transcript: [no speech] (nobody speaks")
      and CAPTION in sent and "no speech; finding places in the TikTok caption" in out, out)
check("C6 [no speech] + caption: place saved, name_from_caption, no sentence ids and no no_valid_segment_ids flag",
      f.get("place_name") == "Luv selfie booth" and f.get("segment_ids") == []
      and "name_from_caption" in f.get("flags", []) and "no_valid_segment_ids" not in f.get("flags", [])
      and (ANSWERS / "PP-530.json").exists(), f)
raw = pn.read_bytes()
reset()
code, out = run(pn)
check("C6 R 2nd run: skipped, no call, file unchanged", "Skipped" in out and not FAKE.models.calls and pn.read_bytes() == raw,
      out)
q = with_caption("PP-540", None, transcript="[no speech]")
reset()
code, out = run(q)
check("C6 [no speech], caption null: skipped, no call, fields stay null",
      code == 0 and not FAKE.models.calls and load(q)["fields"] is None and "no speech and no caption" in out, out)
for i, (kind, cap) in enumerate([('""', ""), ("missing", MISSING)]):
    q = with_caption(f"PP-54{i + 1}", cap, transcript="[no speech]")
    reset()
    code, out = run(q)
    check(f"C6 [no speech], caption {kind}: refused (stage 2 first), no call, fields stay null",
          code == 1 and not FAKE.models.calls and load(q)["fields"] is None and "hasn't been read yet" in out, out)

q = with_caption("PP-550", CAPTION)
reset(default=answer(luv(place_name_alt=["ALWAYS selfie booth", "#luvselfiebooth", " @luv ", "  ", "ALWAYS selfie booth"]),
                     place(place_name="@sponsor", evidence_text="@sponsor", area=None)))
code, out = run(q)
fs = load(q)["fields"]
check("C7 tags, blanks and repeats left out of place_name_alt",
      fs[0]["place_name_alt"] == ["ALWAYS selfie booth"], fs[0]["place_name_alt"])
check("C7 a name that is only an @account: kept for the team but rejected, flag name_is_tag, said so",
      len(fs) == 2 and fs[1]["place_name"] == "@sponsor" and fs[1]["verification_status"] == "rejected"
      and "name_is_tag" in fs[1]["flags"] and "@sponsor (cafe): rejected, only a tag, not a place name" in out, (fs, out))
for i, order in enumerate([["real", "tag"], ["tag", "real"]]):
    q = with_caption(f"PP-55{i + 1}", CAPTION)
    items = {"real": luv(), "tag": luv(place_name=" #luvselfiebooth ", place_name_alt=[], menu_items=["photo strip"])}
    reset(default=answer(*(items[k] for k in order)))
    run(q)
    fs = {x["place_name"]: x for x in load(q)["fields"]}
    real, tag = fs.get("Luv selfie booth", {}), fs.get(" #luvselfiebooth ", {})
    check(f"C7 the place's own #hashtag as another record ({' first, '.join(order)} last): never joined, so the real "
          "place keeps its name; the tag record is rejected",
          len(fs) == 2 and real.get("place_name_alt") == ["ALWAYS selfie booth"]
          and real.get("verification_status") == "needs_review" and tag.get("verification_status") == "rejected"
          and "name_is_tag" in tag.get("flags", []), fs)

# a long video in 2 parts: the caption goes with every part; spoken in part 2 -> not "from caption"
LONG = "\n".join([f"Sentence number {i} about the day." for i in range(65)] + ["Luv selfie booth is really fun."])
q = with_caption("PP-560", CAPTION, transcript=LONG)
reset(plan={"gemini-3.6-flash": [answer(luv(place_name_alt=[], segment_ids=[])),
                                  answer(luv(place_name_alt=[], evidence_text="Luv selfie booth is really fun",
                                             segment_ids=[65]))]})
run(q)
c = load(q)
f = (c["fields"] or [{}])[0]
check("C8 2 parts: caption sent with each part", len(FAKE.models.calls) == 2
      and all(CAPTION in call[1] for call in FAKE.models.calls), len(FAKE.models.calls))
check("C8 merged: one place, sentence 65 kept, spoken in part 2 so no name_from_caption",
      len(c["fields"]) == 1 and f.get("segment_ids") == [65] and "name_from_caption" not in f.get("flags", ["x"])
      and "no_valid_segment_ids" not in f.get("flags", ["x"]), f)

# D. review fixes: checks that the caption must not weaken
def one(p_item, transcript=HEARD, caption=CAPTION, name="PP-600"):
    q = with_caption(name, caption, transcript=transcript)
    reset(default=answer(p_item))
    run(q, "--force")
    return (load(q)["fields"] or [{}])[0]

f = one(luv(segment_ids=[7, 9]))
check("D1 name from the caption but made-up sentence numbers -> still no_valid_segment_ids",
      "name_from_caption" in f["flags"] and "no_valid_segment_ids" in f["flags"], f)
f = one(place(place_name="Totally Made Up", evidence_text="", segment_ids=[0]))
check("D2 empty evidence_text -> evidence_not_found_in_transcript", "evidence_not_found_in_transcript" in f["flags"], f)
f = one(luv(place_name="Luv Selfie Booth Phnom Penh", place_name_alt=[], segment_ids=[]), transcript="[no speech]")
check("D3 [no speech]: name_from_caption even when Gemini's name isn't word for word in the caption; no ids flag",
      "name_from_caption" in f["flags"] and "no_valid_segment_ids" not in f["flags"], f)
f = one(place(place_name="Brown Coffee", area=["Tuol Kouk"], evidence_text="Brown Coffee, Tuol Kouk", segment_ids=[]),
        caption="Thanks to our sponsor Brown Coffee, Tuol Kouk, best coffee!")
check("D4 complete place named only in the caption: needs_review, never auto_added",
      f["completeness"] == 1.0 and f["verification_status"] == "needs_review" and "name_from_caption" in f["flags"], f)
for i, bad_field in enumerate([{"place_name_alt": ["Tea King", None, 5]}, {"place_name": ["Luv"]},
                                 {"menu_items": "photo strip"}]):
    q, ok = with_caption(f"PP-60{5 + i}", None, transcript=TRANSCRIPT), with_caption(f"PP-61{5 + i}", None, transcript=TRANSCRIPT)
    raw = q.read_bytes()
    bad = place(segment_ids=[0]).model_dump() | bad_field
    reset(plan={"gemini-3.6-flash": [SimpleNamespace(parsed=None, text=json.dumps({"places": [bad]}))]})
    code, out = run(q, ok)
    check(f"D5 JSON-text answer with a wrong type ({next(iter(bad_field))}): that clip fails cleanly, the next one "
          "still runs", code == 1 and "did not answer in the expected format. Try this clip again." in out
          and q.read_bytes() == raw and load(ok)["fields"] and f"To try only the failed clip again: python stage4_extract_places.py {q}" in out,
          out)
check("D6 prompt prefers the English name, caption's spelling; caption has no segment ids",
      "English name if one is said or written" in s4.SYSTEM and "between <caption> and </caption>" in s4.SYSTEM
      and "Never give an id for something only the caption says" in s4.SYSTEM)
LONG2 = "\n".join([f"Sentence number {i} about the day." for i in range(65)] + ["Luv selfie booth is really fun!"])
q = with_caption("PP-610", CAPTION, transcript=LONG2)
reset(plan={"gemini-3.6-flash": [answer(luv(place_name_alt=[], segment_ids=[])),
                                  answer(luv(place_name="Luv Selfie-Booth!", place_name_alt=[],
                                             evidence_text="Luv selfie booth is really fun", segment_ids=[65]))]})
run(q)
check("D7 parts merged when names differ only in capitals and punctuation", len(load(q)["fields"]) == 1,
      load(q)["fields"])

# E. second review fixes
f = one(luv(place_name="Brown Coffee & Bakery", place_name_alt=[], name_source="caption", area=["Tuol Kouk"],
            evidence_text="Brown Coffee", segment_ids=[0]), caption="Thanks to our sponsor Brown Coffee, Tuol Kouk")
check("E1 Gemini says the name is from the caption (not word for word) -> name_from_caption, not auto_added",
      "name_from_caption" in f["flags"] and f["verification_status"] == "needs_review", f)
f = one(place(place_name="Ice", area=["Tuol Kouk"], evidence_text="Ice, Tuol Kouk", segment_ids=[]),
        transcript="The rice here is so nice and the price is fair.", caption="Sponsored by Ice, Tuol Kouk")
check("E2 complete place but no valid sentence ('ice' inside 'rice'): never auto_added",
      f["completeness"] == 1.0 and f["verification_status"] == "needs_review", f)
f = one(luv(place_name="#luvselfiebooth #IFL", place_name_alt=[]))
check("E3 a name made of several tags -> name_is_tag, rejected",
      "name_is_tag" in f["flags"] and f["verification_status"] == "rejected", f)
f = one(luv(place_name="📍", place_name_alt=[]))
check("E4 a name with no letters (only a symbol) -> no_place_name, rejected",
      "no_place_name" in f["flags"] and f["verification_status"] == "rejected", f)
f = one(luv(place_name_alt=["Luv selfie booth", "ALWAYS selfie booth", "Always Selfie-Booth", "LUV SELFIE BOOTH"]))
check("E5 place_name_alt: the main name and same names in other capitals/punctuation left out",
      f["place_name_alt"] == ["ALWAYS selfie booth"], f["place_name_alt"])
f = one(place(segment_ids=[0, 1]), transcript=TRANSCRIPT, caption="Tea Kingdom 🍵")
check("E6 a normal spoken place, transcript backs it: still auto_added", f["verification_status"] == "auto_added", f)

print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
