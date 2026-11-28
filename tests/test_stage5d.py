"""Offline checks for stage 5d (tvna_review.py, stage5d_add_photo.py, stage5d_check_photos.py):
a fake Cloudinary and a fake photo website on this computer, temp place files; data/ is never touched."""
import base64
import builtins
import contextlib
import http.server
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
from email import policy
from email.parser import BytesParser
from pathlib import Path

PIPE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPE))
import tvna_common as tc  # noqa: E402
import tvna_review as tr  # noqa: E402
import stage5d_add_photo as add  # noqa: E402
import stage5d_check_photos as checker  # noqa: E402

WORK = Path(tempfile.mkdtemp(prefix="tvna-test-"))
PLACES, MEDIA = WORK / "places", WORK / "media"
PLACES.mkdir()
MEDIA.mkdir()
DATA_BEFORE = {p: p.stat().st_mtime_ns for p in (PIPE / "data").rglob("*") if p.is_file()}

results = []
def check(name, cond, detail=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"\n     {detail}"))

def ff(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)

def picture(name, size, color):
    ff("-f", "lavfi", "-i", f"color=c={color}:s={size}", "-frames:v", "1", str(MEDIA / name))
    return MEDIA / name

def with_exif(src, dst, tiff):
    raw = src.read_bytes()
    app1 = b"Exif\x00\x00" + tiff
    dst.write_bytes(raw[:2] + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + raw[2:])
    return dst

def size_of(path):
    return tc.picture_size(path)

BIG = with_exif(picture("plain.jpg", "1600x1200", "green"), MEDIA / "big.jpg",
                b"MM\x00\x2a\x00\x00\x00\x08\x00\x00TVNA-GPS-11.55N-104.92E")
ROT = with_exif(picture("rot.jpg", "1600x1200", "navy"), MEDIA / "rot6.jpg",
                b"MM\x00\x2a" + struct.pack(">IH", 8, 1) + struct.pack(">HHIHH", 0x0112, 3, 1, 6, 0) + struct.pack(">I", 0))
OTHERS = [picture(f"other{i}.png", "800x800", c) for i, c in enumerate(["red", "blue", "yellow", "purple", "orange", "pink"])]
SMALL = picture("small.jpg", "500x400", "gray")
WIDE = picture("wide.jpg", "1600x500", "teal")
NOT_IMAGE = MEDIA / "notes.txt"
NOT_IMAGE.write_text("not a picture")
HEIC = MEDIA / "phone.heic"
subprocess.run(["sips", "-s", "format", "heic", str(BIG), "--out", str(HEIC)], capture_output=True)

# Fake photo website: /photo.jpg = a picture, /page.html = a web page, anything else = 404
class FakeWeb(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/photo.jpg":
            body, kind = OTHERS[5].read_bytes(), "image/png"
        elif self.path == "/bare.jpg":
            body, kind = OTHERS[4].read_bytes(), None
        elif self.path in ("/cut.jpg", "/cut-chunked.jpg"):
            body = OTHERS[3].read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            if self.path == "/cut.jpg":
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body[: len(body) // 2])
            else:
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.write(b"%x\r\n" % len(body) + body[:100])
            return
        elif self.path == "/page.html":
            body, kind = b"<html>a photo page</html>", "text/html; charset=utf-8"
        else:
            self.send_error(404, "Not Found")
            return
        self.send_response(200)
        if kind:
            self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass

SECRET = "s3cr3t-never-print"
class FakeCloud(http.server.BaseHTTPRequestHandler):
    mode = "ok"  # ok / refuse / change (someone saves the place file during the upload)
    uploads = []
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        msg = BytesParser(policy=policy.default).parsebytes(
            b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body)
        fields = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True) for p in msg.iter_parts()}
        FakeCloud.uploads.append({"auth": self.headers.get("Authorization"), "fields": fields})
        if FakeCloud.mode == "change":
            p = PLACES / "tvna_p_0001.json"
            p.write_text(p.read_text() + " ", encoding="utf-8")
        if FakeCloud.mode == "refuse":
            code, answer = 401, {"error": {"message": "Invalid Signature"}}
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

servers = []
for handler in (FakeWeb, FakeCloud):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    servers.append(server)
WEB = f"http://127.0.0.1:{servers[0].server_address[1]}"
tc.CLOUDINARY_API = f"http://127.0.0.1:{servers[1].server_address[1]}/v1_1"
tc.ENV_FILE = WORK / "no.env"
KEYS = {"CLOUDINARY_CLOUD_NAME": "testcloud", "CLOUDINARY_API_KEY": "123456", "CLOUDINARY_API_SECRET": SECRET}
os.environ.update(KEYS)

def place(place_id="tvna_p_0001", **over):
    e = {"place_id": place_id, "place_name": "Beans Barley", "aliases": [], "area": "Prampi Makara",
         "google_maps_url": "https://maps.app.goo.gl/x", "photos": []} | over
    (PLACES / f"{place_id}.json").write_text(json.dumps(e, ensure_ascii=False, indent=2), encoding="utf-8")
    return PLACES / f"{place_id}.json"

def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

ALL_OUTPUT = []
def run(module, *args, answer=None):
    sys.argv = ["stage5d.py", *map(str, args), "--places-dir", str(PLACES)]
    out, code = io.StringIO(), 0
    old_input = builtins.input
    def fake_input(prompt=""):
        out.write(prompt)
        if answer is EOFError:
            raise EOFError
        return answer
    builtins.input = fake_input
    with contextlib.redirect_stdout(out):
        try:
            module.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (out.write(str(e.code)) and 1)
        finally:
            builtins.input = old_input
    ALL_OUTPUT.append(out.getvalue())
    return code, out.getvalue()

def tries(fn, *args):
    """The PhotoError message, or "" when it worked."""
    try:
        fn(*args)
        return ""
    except tr.PhotoError as e:
        ALL_OUTPUT.append(str(e))
        return str(e)

def add_one(image, source="Google Maps", credit="Dara S.", place_id="tvna_p_0001"):
    return tries(tr.add_photo, place_id, str(image), source, credit, PLACES)

def link(i):
    return f"https://res.cloudinary.com/testcloud/image/upload/v1/tvna/places/tvna_p_0001-{i}.jpg"

# 1. a photo file
p = place()
n_up = len(FakeCloud.uploads)
err = add_one(BIG)
e = load(p)
photo = (e["photos"] or [{}])[0]
up = FakeCloud.uploads[-1] if len(FakeCloud.uploads) > n_up else {"fields": {}}
check("1 photo file: added with url, source, credit and its picture code", not err and len(e["photos"]) == 1
      and photo.get("source") == "Google Maps" and photo.get("credit") == "Dara S."
      and len(photo.get("sha256", "")) == 64 and photo.get("url") == link(photo.get("sha256", "")[:10]), (err, e))
check("1 photo file: one upload, public_id tvna/places/<place_id>-<code>, overwrite, Basic login",
      len(FakeCloud.uploads) == n_up + 1 and up["fields"].get("public_id") == f"tvna/places/tvna_p_0001-{photo.get('sha256', '')[:10]}".encode()
      and up["fields"].get("overwrite") == b"true"
      and up.get("auth") == "Basic " + base64.b64encode(f"123456:{SECRET}".encode()).decode(), up)
(WORK / "sent.jpg").write_bytes(up["fields"].get("file") or b"")
sent = (WORK / "sent.jpg").read_bytes()
check("1 the sent picture: a JPG, 1200 px wide (from 1600), EXIF gone (no GPS note)",
      sent[:2] == b"\xff\xd8" and size_of(WORK / "sent.jpg") == (1200, 900) and b"Exif" not in sent
      and b"TVNA-GPS" not in sent and b"TVNA-GPS" in BIG.read_bytes(), size_of(WORK / "sent.jpg"))
check("1 the other place fields are unchanged", {k: v for k, v in e.items() if k != "photos"}
      == {k: v for k, v in json.loads(json.dumps(load(p))).items() if k != "photos"} and e["place_name"] == "Beans Barley")

# 2. the same picture again: refused, nothing uploaded or changed
raw, n_up = p.read_bytes(), len(FakeCloud.uploads)
err = add_one(BIG)
check("2 same picture twice: refused (photo 1), no upload, file unchanged",
      "This photo is already on this place (photo 1)" in err and len(FakeCloud.uploads) == n_up and p.read_bytes() == raw, err)

# 3-5. links
err = add_one(f"{WEB}/photo.jpg", "Shop's own page", "Beans Barley page")
check("3 image link: downloaded and added", not err and len(load(p)["photos"]) == 2
      and load(p)["photos"][1]["source"] == "Shop's own page", err)
raw = p.read_bytes()
err = add_one(f"{WEB}/page.html")
check("4 web page link: says to copy the image address, file unchanged",
      "This is a web page link" in err and "Copy image address" in err and p.read_bytes() == raw, err)
err = add_one(f"{WEB}/gone.jpg")
check("5 link that doesn't download (404): says so, file unchanged", "Couldn't download this link (404" in err
      and p.read_bytes() == raw, err)
err = add_one("http://127.0.0.1:9/x.jpg")
check("5 no connection: says so", "Couldn't download this link (no connection" in err, err)

# 6-9. bad pictures
old_max = tr.IMAGE_MAX_BYTES
tr.IMAGE_MAX_BYTES = 1000
err_file, err_link = add_one(OTHERS[0]), add_one(f"{WEB}/photo.jpg")
tr.IMAGE_MAX_BYTES = old_max
check("6 over 20 MB (file and link): too big, file unchanged", "Too big" in err_file and "Too big" in err_link
      and p.read_bytes() == raw, (err_file, err_link))
err = add_one(NOT_IMAGE)
check("7 not a picture: can't read it, says which kinds work", "Can't read this image" in err and "JPG, PNG, WebP or HEIC" in err
      and p.read_bytes() == raw, err)
err = add_one(MEDIA / "nowhere.jpg")
check("7 a file that isn't there: says so", "Can't find the file" in err, err)
n_up = len(FakeCloud.uploads)
err = add_one(SMALL)
check("8 under 600 px: too small (shows the size), no upload", "Too small (500×400 px)" in err
      and len(FakeCloud.uploads) == n_up and p.read_bytes() == raw, err)

n_up = len(FakeCloud.uploads)
err = add_one(WIDE)
check("8 wide but short (1600×500): too small, no upload", "Too small (1600×500 px)" in err
      and len(FakeCloud.uploads) == n_up and p.read_bytes() == raw, err)
(WORK / "small-sent.jpg").write_bytes(FakeCloud.uploads[-1]["fields"]["file"])
check("8 a photo under 1200 px (the 800 px link photo) is not made bigger", size_of(WORK / "small-sent.jpg") == (800, 800),
      size_of(WORK / "small-sent.jpg"))

# 9. phone photos
err = add_one(ROT, "Own photo", "Sovan")
(WORK / "rot.jpg").write_bytes(FakeCloud.uploads[-1]["fields"]["file"])
check("9 phone photo with a 'turn it' note in EXIF: turned the right way up (portrait), then EXIF removed",
      not err and size_of(WORK / "rot.jpg") == (1200, 1600) and b"Exif" not in (WORK / "rot.jpg").read_bytes(), err)
if HEIC.exists():
    err = add_one(HEIC, "Other: the shop's Instagram", "@beansbarley")
    (WORK / "heic.jpg").write_bytes(FakeCloud.uploads[-1]["fields"]["file"])
    check("9 iPhone HEIC photo: read and made a 1200 px JPG", not err and size_of(WORK / "heic.jpg") == (1200, 900)
          and load(p)["photos"][-1]["source"] == "Other: the shop's Instagram", err)
else:
    check("9 iPhone HEIC photo (skipped: no sips on this computer to make one)", True)

# 10. full: the 6th photo is refused before any download
while len(load(p)["photos"]) < 5:
    add_one(OTHERS[len(load(p)["photos"])])
raw, n_up = p.read_bytes(), len(FakeCloud.uploads)
err = add_one(OTHERS[5])
check("10 6th photo: refused (5 at most), no upload, file unchanged", len(load(p)["photos"]) == 5
      and "already has 5 photos" in err and len(FakeCloud.uploads) == n_up and p.read_bytes() == raw, err)

# 11-13. refused before downloading
p2 = place("tvna_p_0002")
raw2 = p2.read_bytes()
for label, source, credit, wanted in [("source not in the list", "google", "Dara", "source must be one of"),
                                      ('source "Other:" with nothing after', "Other: ", "Dara", "source must be one of"),
                                      ("no credit", "Google Maps", "  ", "credit is needed"),
                                      ("credit null", "Google Maps", None, "credit is needed")]:
    err = add_one(BIG, source, credit, "tvna_p_0002")
    check(f"11 {label}: refused, file unchanged", wanted in err and p2.read_bytes() == raw2, err)
for bad in ["tvna_p_9999", "../evil", "", None]:
    err = add_one(BIG, place_id=bad)
    check(f"12 place id {bad!r}: no such place, says so", "There is no place" in err, err)

for k in KEYS:
    del os.environ[k]
n_up = len(FakeCloud.uploads)
err = add_one(BIG, place_id="tvna_p_0002")
os.environ.update(KEYS)
check("13 no Cloudinary keys: says so, nothing uploaded or changed", "Cloudinary keys are not in .env" in err
      and len(FakeCloud.uploads) == n_up and p2.read_bytes() == raw2, err)

# 14-15. upload problems
FakeCloud.mode = "refuse"
err = add_one(BIG, place_id="tvna_p_0002")
FakeCloud.mode = "ok"
check("14 Cloudinary refuses: its reason shown, file unchanged", "Upload failed (Cloudinary answered 401: Invalid Signature)" in err
      and p2.read_bytes() == raw2, err)
p1 = place(photos=[])
FakeCloud.mode = "change"
err = add_one(BIG)
FakeCloud.mode = "ok"
check("15 someone saved the place file during the upload: refused, their save kept", "changed while the photo was uploading" in err
      and load(p1)["photos"] == [] and p1.read_text().endswith(" "), err)

# R. photos filled / null / [] / missing: add works; the same picture twice keeps one
for kind, value in [("[]", []), ("null", None), ("missing", tr.MAX_PHOTOS), ("one photo", "one")]:
    pid = {"[]": "tvna_p_0101", "null": "tvna_p_0102", "missing": "tvna_p_0103", "one photo": "tvna_p_0104"}[kind]
    q = place(pid)
    e = load(q)
    if kind == "missing":
        del e["photos"]
    elif kind == "one photo":
        e["photos"] = [{"url": "https://res.cloudinary.com/x/a.jpg", "source": "Google Maps", "credit": "A", "sha256": "0" * 64}]
    else:
        e["photos"] = value
    q.write_text(json.dumps(e), encoding="utf-8")
    before = len(tr.photos_of(e))
    err1 = add_one(OTHERS[0], place_id=pid)
    raw = q.read_bytes()
    err2 = add_one(OTHERS[0], place_id=pid)
    check(f"R photos {kind}: 1st add works; 2nd add of the same picture refused, file unchanged",
          not err1 and len(load(q)["photos"]) == before + 1 and "already on this place" in err2 and q.read_bytes() == raw,
          (err1, err2, load(q)))

# F. fixes from the code review
p = place("tvna_p_0201", photos=[])
err = add_one(f"{WEB}/bare.jpg", place_id="tvna_p_0201")
check("F1 image link with no Content-Type: added (not called a web page)", not err and len(load(p)["photos"]) == 1, err)
raw = p.read_bytes()
for path in ("/cut.jpg", "/cut-chunked.jpg"):
    err = add_one(f"{WEB}{path}", place_id="tvna_p_0201")
    check(f"F2 download cut off ({path}): says couldn't download, no crash, file unchanged",
          "Couldn't download this link" in err and p.read_bytes() == raw, err)
err = add_one(NOT_IMAGE, place_id="tvna_p_0201")
check("F3 unreadable message has one pair of brackets", "Can't read this image (" in err and "((" not in err, err)
old_path = os.environ["PATH"]
os.environ["PATH"] = str(WORK / "empty-bin")
err = add_one(OTHERS[1], place_id="tvna_p_0201")
try:
    tc.picture_size(OTHERS[1])
    probe = ""
except ValueError as e:
    probe = str(e)
os.environ["PATH"] = old_path
check("F4 ffmpeg / ffprobe not installed: a clear message, no crash, file unchanged",
      "ffmpeg is not installed" in err and "ffprobe is not installed" in probe and p.read_bytes() == raw, (err, probe))
real_run, calls = tc.run_ffmpeg, []
def first_only(*args):
    calls.append(args)
    if len(calls) == 1:
        real_run(*args)
tc.run_ffmpeg = first_only
err = add_one(OTHERS[1], place_id="tvna_p_0201")
tc.run_ffmpeg = real_run
check("F5 ffmpeg says OK but makes no picture: can't read it, no upload, file unchanged",
      "ffmpeg made no picture" in err and p.read_bytes() == raw, err)

q = place("tvna_p_0202", photos="")
err = add_one(OTHERS[0], place_id="tvna_p_0202")
check('F6 photos "": counts as none; the add saves a real list', not err and isinstance(load(q)["photos"], list)
      and len(load(q)["photos"]) == 1, (err, load(q)))
q = place("tvna_p_0203", photos="https://res.cloudinary.com/x/one.jpg")
raw = q.read_bytes()
errs = [add_one(OTHERS[0], place_id="tvna_p_0203"), tries(tr.remove_photo, "tvna_p_0203", 1, PLACES),
        tries(tr.move_photo, "tvna_p_0203", 1, 1, PLACES)]
check("F7 photos is text, not a list: add, remove and move all refuse with the checker's message, file unchanged",
      all("photos must be a list" in e for e in errs) and q.read_bytes() == raw, errs)

p = place("tvna_p_0204", photos=[])
add_one(OTHERS[0], place_id="tvna_p_0204")
raw = p.read_bytes()
code, out = run(add, "tvna_p_0204", "--remove", "1", answer=EOFError)
check("F8 --remove with no keyboard (stdin closed): not removed, no crash", code == 0 and "Not removed" in out
      and p.read_bytes() == raw and "Traceback" not in out, out)
add_one(OTHERS[1], place_id="tvna_p_0204")
first = load(p)["photos"][0]["url"]
code, out = run(add, "tvna_p_0204", "--move", "2", "--to", "1")
check("F9 after --move the new order is printed, so nobody runs it again to check",
      f"  2. {first}" in out and "  1. " in out, out)

# C. the command
p = place(photos=[])
code, out = run(add, "tvna_p_0001", BIG, f"{WEB}/page.html", OTHERS[1], "--source", "Google Maps", "--credit", "Dara S.")
check("C1 several photos: each tried, the bad one said, the rest added, summary, exit 1", code == 1
      and len(load(p)["photos"]) == 2 and "photo not added" in out and "This is a web page link" in out
      and "Done: 2 added, 1 not added." in out and "photos 2 of 5" in out, out)
code, out = run(add, "tvna_p_0001", "--remove", "1", answer="no")
check("C2 --remove asks first; 'no' keeps it", code == 0 and len(load(p)["photos"]) == 2 and "Type yes" in out
      and "Not removed" in out, out)
second = load(p)["photos"][1]["url"]
code, out = run(add, "tvna_p_0001", "--move", "2", "--to", "1")
check("C3 --move 2 --to 1: photo 2 becomes the main one", code == 0 and load(p)["photos"][0]["url"] == second
      and "is now photo 1" in out, out)
code, out = run(add, "tvna_p_0001", "--remove", "1", answer="yes")
check("C4 --remove 1, 'yes': removed, says the picture stays on Cloudinary", code == 0 and len(load(p)["photos"]) == 1
      and load(p)["photos"][0]["url"] != second and "stays on Cloudinary" in out, out)
raw = p.read_bytes()
for args, wanted in [(["--remove", "7", "--yes"], "There is no photo 7 (this place has 1)"),
                     (["--move", "1", "--to", "3"], "There is no photo 3"), (["--remove", "0", "--yes"], "There is no photo 0")]:
    code, out = run(add, "tvna_p_0001", *args)
    check(f"C5 {' '.join(args)}: says there is no such photo, exit 1, nothing changed", code == 1 and wanted in out
          and "Nothing changed" in out and p.read_bytes() == raw, out)
code, out = run(add, "tvna_p_0404", BIG, "--source", "Google Maps", "--credit", "D")
check("C6 unknown place: stops before any download, exit 1", code == 1 and "There is no place" in out, out)
code, out = run(add, "tvna_p_0001")
check("C7 nothing to do: usage error", code == 2, out)

# K. the checker (read-only)
for f in PLACES.glob("*.json"):
    f.unlink()
good = {"url": "https://res.cloudinary.com/x/1.jpg", "source": "Google Maps", "credit": "A", "sha256": "1" * 64}
place("tvna_p_0001", photos=[good])
place("tvna_p_0002", place_name="New Noodle Bar", photos=[])
place("tvna_p_0003", place_name="No Photos Key")
e = load(PLACES / "tvna_p_0003.json"); del e["photos"]; (PLACES / "tvna_p_0003.json").write_text(json.dumps(e))
place("tvna_p_0004", place_name="Too Many", photos=[dict(good, sha256=str(i) * 64, url=f"https://r/{i}.jpg") for i in range(6)])
place("tvna_p_0005", place_name="Bad Entries", photos=[dict(good, url="http://insecure/x.jpg"), dict(good, source="google", sha256="2" * 64),
                                                        dict(good, credit="", sha256="3" * 64), "https://just-a-link.jpg", dict(good)])
place("tvna_p_0006", place_name="Not A List", photos="https://x.jpg")
place("tvna_p_0007", place_name="Null Photos", photos=None)
place("tvna_p_0009", place_name=None, photos="")
before = {f: f.read_bytes() for f in PLACES.glob("*.json")}
code, out = run(checker)
check("K1 problems: more than 5, http link, bad source, empty credit, not an object, same picture twice, not a list; exit 1",
      code == 1 and "problems (3):" in out and "6 photos: the most is 5" in out and "url must be an https:// link" in out
      and 'source must be one of' in out and "credit is empty" in out and "must be {\"url\", \"source\", \"credit\"}" in out
      and "photo 5 is the same picture as photo 1" in out and "photos must be a list" in out, out)
check("K2 need photos: [] / missing / null, with the name and Maps link to find them",
      "need photos (4):" in out and 'tvna_p_0002  "New Noodle Bar"  https://maps.app.goo.gl/x' in out
      and "tvna_p_0003" in out and "tvna_p_0007" in out and "python stage5d_add_photo.py <place_id>" in out, out)
check("K2 a place with no name says so (not \"None\"); photos \"\" counts as none",
      'tvna_p_0009  "(no name: add place_name)"' in out and "None" not in out and "need photos (4):" in out, out)
check("K3 ready: 1 to 5 good photos", "ready (1):" in out and 'tvna_p_0001  "Beans Barley"' in out, out)
code2, out2 = run(checker)
check("K4 read-only: no file changed; run twice: same output", {f: f.read_bytes() for f in PLACES.glob("*.json")} == before
      and (code2, out2) == (code, out))
(PLACES / "tvna_p_0008.json").write_text("{ broken")
code, out = run(checker)
check("K5 a broken place file: names it, exit 1, no crash", code == 1 and "tvna_p_0008.json" in out and "Traceback" not in out, out)

check("the Cloudinary secret is never printed", not any(SECRET in o for o in ALL_OUTPUT))
check("no half-written (.part) file left", not list(WORK.rglob("*.part")))
check("data/ not touched", {p: p.stat().st_mtime_ns for p in (PIPE / "data").rglob("*") if p.is_file()} == DATA_BEFORE)
check("every message key used exists in review/texts_en.json",
      all(k in tr._texts() for k in ["photo.no_place", "photo.full", "photo.no_file", "photo.too_big", "photo.download_failed",
                                     "photo.web_page", "photo.unreadable", "photo.too_small", "photo.duplicate",
                                     "photo.upload_failed", "photo.no_keys", "photo.bad_source", "photo.no_credit",
                                     "photo.changed", "photo.bad_number"]))

for server in servers:
    server.shutdown()
print(f"\n{sum(results)}/{len(results)} passed")
shutil.rmtree(WORK, ignore_errors=True)
sys.exit(0 if all(results) else 1)
