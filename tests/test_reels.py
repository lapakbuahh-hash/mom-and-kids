"""Uji Reels dan format Jika-Perbanyak (tanpa jaringan, tanpa TTS).

    python tests/test_reels.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import common  # noqa: E402

TMP = pathlib.Path(tempfile.mkdtemp())
common.DATA_DIR, common.POSTS_DIR, common.DOCS_DIR = TMP / "data", TMP / "posts", TMP / "docs"

import src.generate as gen  # noqa: E402
import src.instagram as ig  # noqa: E402
import src.publish as publish  # noqa: E402
import src.reels as reels  # noqa: E402
import src.telegram as tg  # noqa: E402

gen.POSTS_DIR = tg.POSTS_DIR = common.POSTS_DIR
os.environ.update(TELEGRAM_BOT_TOKEN="t", TELEGRAM_CHAT_ID="42", IG_ACCESS_TOKEN="x", GITHUB_REPOSITORY="me/repo",
                  GITHUB_REF_NAME="main")
brand = common.load_brand()
_real_publish_reel = ig.publish_reel

# ---- 1. render tiap gaya -> MP4 valid sesuai syarat Instagram
for style in reels.STYLES:
    out = TMP / f"{style}.mp4"
    info = reels.render_reel(dict(reels._DEMO, style=style), brand, out, use_voice=False)
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(out)],
        capture_output=True, text=True, check=True).stdout)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert (v["codec_name"], v["width"], v["height"], v["pix_fmt"]) == ("h264", 1080, 1920, "yuv420p")
    assert a["codec_name"] == "aac" and int(a["sample_rate"]) <= 48000
    assert 5 <= float(probe["format"]["duration"]) <= 90 and info["size_mb"] < 30, info
    assert info["style"] != "voiceover" and not info["voice"], "tanpa TTS harus turun ke slides_music"

# ---- 2. normalisasi
raw = {"hook": "Halo Bun", "caption": "Cerita", "hashtags": ["a"], "slides": [{"heading": "A", "body": "B"}, {"heading": "C", "body": "D"}]}
assert gen.normalize_reel(raw, brand, "voiceover")["style"] == "slides_music", "voiceover tanpa naskah suara -> turun gaya"
assert gen.normalize_reel(dict(raw, slides=[dict(s, voice="x") for s in raw["slides"]]), brand, "voiceover")["style"] == "voiceover"
assert gen.normalize_reel({"hook": "x"}, brand, "kinetic") is None
j = gen.normalize_jika({**raw, "slides": [{"heading": "Jika anak gampang bosan", "body": "Perbanyak puzzle", "benefit": "Bantu fokus"},
                                          {"heading": "x", "body": "y"}]}, brand)
assert j["layout"] == "jika_perbanyak" and j["slides"][0]["heading"] == "gampang bosan" and j["slides"][0]["body"] == "puzzle"
assert gen.reel_counts({"reels": {"per_week": 2}, "jika_perbanyak": {"per_week": 1}}, 5) == (2, 1, 2)
assert gen.reel_counts({}, 5) == (5, 0, 0)
assert gen.spread_positions(5, 2) == [1, 3] and gen.spread_positions(5, 0) == []
p = gen.build_reels_prompt(brand, ["lama"], ["Main Seru", "Dapur Bunda"], ["kinetic", "voiceover"])
assert "gaya: kinetic" in p and "HANGAT (tiru)" in p and "lama" in p
assert "tanda anak" in gen.build_jika_prompt(brand, [], ["Main Seru"]).lower()  # larangan gaya diagnosis ada di prompt

# ---- 3. minggu campuran (sample): 2 carousel + 1 Jika + 2 Reels, Reels dikirim lewat sendVideo
sent = []
tg._call = lambda m, **kw: (sent.append(m), {"message_id": len(sent)})[1]
gen.time.sleep = lambda s: None
sys.argv = ["generate", "--sample", "--no-voice"]
gen.main()
posts = common.load_posts()
fmts = [p["format"] for p in posts]
assert fmts.count("reels") == 2 and len(posts) == 5 and fmts[0] != "reels", fmts
assert sum(p.get("layout") == "jika_perbanyak" for p in posts) == 1
assert sent.count("sendVideo") == 2 and sent.count("sendMediaGroup") == 3, sent
reel = next(p for p in posts if p["format"] == "reels")
assert (common.POSTS_DIR / reel["id"] / "reel.mp4").exists() and reel["images"] == []

# ---- 4. publish Reels: URL video publik benar, lalu MP4 dihapus supaya repo tidak membengkak
calls = []
publish.instagram.account_id = lambda: "777"
publish.instagram.publish_reel = lambda uid, url, cap: (calls.append((uid, url, cap)), "R1")[1]
publish.instagram.get = lambda *a, **k: {"permalink": "https://instagram.com/reel/abc"}
publish.notify = lambda t: None
publish.time.sleep = lambda s: None
reel["status"] = "approved"
reel["scheduled_at"] = (common.now(brand) - __import__("datetime").timedelta(hours=1)).isoformat()
common.save_posts(posts)
assert publish.publish_due() == 1
assert calls[0][1] == f"https://raw.githubusercontent.com/me/repo/main/posts/{reel['id']}/reel.mp4", calls
done = next(p for p in common.load_posts() if p["id"] == reel["id"])
assert done["status"] == "published" and done["media_id"] == "R1" and done.get("video_removed")
assert not (common.POSTS_DIR / reel["id"] / "reel.mp4").exists()
os.environ["REELS_BASE_URL"] = "https://me.github.io/repo/reels/"
assert publish.video_url("p1", "reel.mp4") == "https://me.github.io/repo/reels/p1/reel.mp4"

# ---- 5. Instagram: container REELS -> tunggu FINISHED -> publish
seq = []
ig.post = lambda path, **kw: (seq.append((path, kw)), {"id": "C1"})[1]
ig.wait_until_ready = lambda cid, timeout=180, interval=4: seq.append(("wait", timeout))
assert _real_publish_reel("777", "https://x/v.mp4", "cap") == "C1"
assert seq[0][1]["media_type"] == "REELS" and seq[0][1]["video_url"] == "https://x/v.mp4" and seq[1][0] == "wait"
assert seq[2][0] == "777/media_publish"

import shutil  # noqa: E402

shutil.rmtree(TMP)
print("Uji Reels lulus.")
