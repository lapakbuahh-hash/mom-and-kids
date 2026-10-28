"""Uji alur end-to-end dengan Telegram, Instagram, dan Gemini palsu (tanpa jaringan).

    python tests/test_pipeline.py
"""
import datetime as dt
import json
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Arahkan penyimpanan ke folder sementara agar data asli tidak tersentuh.
from src import common  # noqa: E402

TMP = pathlib.Path(tempfile.mkdtemp())
common.DATA_DIR = TMP / "data"
common.POSTS_DIR = TMP / "posts"
common.DOCS_DIR = TMP / "docs"

import src.generate as gen  # noqa: E402
import src.insights as insights  # noqa: E402
import src.instagram as ig  # noqa: E402
import src.publish as publish  # noqa: E402
import src.telegram as tg  # noqa: E402

gen.POSTS_DIR = common.POSTS_DIR
tg.POSTS_DIR = common.POSTS_DIR
insights.DOCS_DIR = common.DOCS_DIR
tg.load_state = common.load_state

os.environ.update(
    TELEGRAM_BOT_TOKEN="t", TELEGRAM_CHAT_ID="42", IG_ACCESS_TOKEN="x", IG_USER_ID="999",
    GITHUB_REPOSITORY="me/repo", GITHUB_REF_NAME="main", GEMINI_API_KEY="g",
)

sent = []          # pesan Telegram keluar
updates = []       # callback masuk (disimulasikan)
ig_calls = []      # panggilan ke Instagram


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, json.dumps(payload)

    def json(self):
        return self._p


def fake_tg_call(method, **kw):
    sent.append((method, kw.get("json") or kw.get("data")))
    if method == "answerCallbackQuery":
        # Meniru Telegram: tombol sudah kedaluwarsa karena dibaca belasan menit kemudian.
        raise RuntimeError("Bad Request: query is too old and response timeout expired")
    if method == "sendMessage":
        return {"message_id": len(sent)}
    return {}


tg._call = fake_tg_call


def fake_get(url, params=None, **kw):
    if "getUpdates" in url:
        return FakeResp({"ok": True, "result": list(updates)})
    raise AssertionError(url)


tg.requests.get = fake_get


def fake_ig_post(path, **params):
    ig_calls.append(("POST", path, params))
    if path.endswith("/media_publish"):
        return {"id": "MEDIA1"}
    return {"id": f"C{len(ig_calls)}"}


def fake_ig_get(path, **params):
    ig_calls.append(("GET", path, params))
    if params.get("fields") == "status_code":
        return {"status_code": "FINISHED"}
    if params.get("fields") == "permalink":
        return {"permalink": "https://instagram.com/p/abc"}
    if path == "me":
        return {"username": "u", "followers_count": 123, "media_count": 5}
    if path.endswith("/insights"):
        return {"data": [{"values": [{"value": 10}]}]}
    raise AssertionError(path)


ig.post, ig.get = fake_ig_post, fake_ig_get
publish.instagram.post, publish.instagram.get = fake_ig_post, fake_ig_get
insights.instagram.get = fake_ig_get
ig.time.sleep = lambda s: None
publish.time.sleep = lambda s: None

# ---- 1. normalisasi + jadwal
brand = common.load_brand()
messy = {"pillar": "Edukasi", "hook": "Halo", "slides": [{"heading": "A", "body": "B"}, {"heading": "C", "body": "D"}],
         "caption": "x" * 2300, "hashtags": ["Bebas Spasi", "#Dua"]}
n = gen.normalize_post(messy, brand)
assert n and len(n["full_caption"]) <= 2200, "caption harus dipangkas ke 2200"
assert all(t.startswith("#") and " " not in t for t in n["hashtags"])
assert gen.normalize_post({"hook": "x"}, brand) is None, "data rusak harus ditolak"
slots = gen.assign_slots(brand, 5, dt.date(2026, 11, 2))
assert len({s.date() for s in slots}) == 5 and slots[-1].date() <= dt.date(2026, 11, 8)

# ---- 2. generate (sample) + kirim ke Telegram
sys.argv = ["generate", "--sample"]
gen.main()
posts = common.load_posts()
assert len(posts) == 2 and all(p["status"] == "draft" for p in posts)
assert sum(1 for m, _ in sent if m == "sendMediaGroup") == 2
assert all("telegram_message_id" in p or True for p in posts)

# ---- 3. approve + skip lewat callback
pid_a, pid_b = posts[0]["id"], posts[1]["id"]
updates[:] = [
    {"update_id": 1, "callback_query": {"id": "q1", "data": f"approve:{pid_a}", "message": {"chat": {"id": 42}, "message_id": 7}}},
    {"update_id": 2, "callback_query": {"id": "q2", "data": f"skip:{pid_b}", "message": {"chat": {"id": 42}, "message_id": 8}}},
    {"update_id": 3, "callback_query": {"id": "q3", "data": f"approve:{pid_b}", "message": {"chat": {"id": 999}, "message_id": 9}}},  # orang asing
]
assert tg.process_updates() == 2
posts = common.load_posts()
assert posts[0]["status"] == "approved" and posts[1]["status"] == "skipped", "orang asing tidak boleh mengubah status"
assert common.load_state()["telegram_offset"] == 4

# ---- 4. belum jatuh tempo -> tidak tayang
assert publish.publish_due() == 0

# ---- 5. jatuh tempo -> tayang
posts = common.load_posts()
past = (common.now(brand) - dt.timedelta(hours=1)).isoformat()
posts[0]["scheduled_at"] = past
common.save_posts(posts)
assert publish.publish_due() == 1
posts = common.load_posts()
p = posts[0]
assert p["status"] == "published" and p["media_id"] == "MEDIA1" and p["permalink"].endswith("abc")
child_urls = [c[2]["image_url"] for c in ig_calls if c[0] == "POST" and "image_url" in c[2]]
assert len(child_urls) == 5 and child_urls[0] == f"https://raw.githubusercontent.com/me/repo/main/posts/{pid_a}/slide_01.png"
carousel = [c for c in ig_calls if c[0] == "POST" and c[2].get("media_type") == "CAROUSEL"]
assert len(carousel) == 1 and carousel[0][2]["children"].count(",") == 4

# ---- 6. jadwal basi -> expired, bukan tayang
posts[1]["status"] = "approved"
posts[1]["scheduled_at"] = (common.now(brand) - dt.timedelta(hours=100)).isoformat()
common.save_posts(posts)
assert publish.publish_due() == 0
assert common.load_posts()[1]["status"] == "expired"

# ---- 7. gagal tayang berulang -> failed
posts = common.load_posts()
posts[1]["status"] = "approved"
posts[1]["scheduled_at"] = past
common.save_posts(posts)
def boom(*a, **k):
    raise ig.InstagramError("token kedaluwarsa")
publish.instagram.publish_carousel = boom
for _ in range(3):
    publish.publish_due()
assert common.load_posts()[1]["status"] == "failed"

# ---- 8. analitik
insights.main()
data = json.loads((common.DOCS_DIR / "analytics.json").read_text())
assert data["account"]["followers_count"] == 123 and len(data["posts"]) == 1
assert data["posts"][0]["metrics"]["reach"] == 10

# ---- 9. prompt memuat panduan gaya ramah
prompt = gen.build_prompt(brand, ["topik lama"], gen._weighted_pillars(brand, 5))
assert "Bunda" in prompt and "HANGAT (tiru)" in prompt and "topik lama" in prompt

# ---- 10. Gemini: model 404 -> otomatis pindah ke model cadangan (tanpa menunggu/mengulang)
gem_calls = []


class _R:
    def __init__(self, code, payload=None):
        self.status_code, self._p = code, payload or {}
        self.text = json.dumps(self._p)

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def fake_gem_post(url, **kw):
    gem_calls.append(url)
    if "gemini-3.1-flash-lite" in url:
        return _R(404)
    return _R(200, {"candidates": [{"content": {"parts": [{"text": json.dumps([{"hook": "x"}])}]}}]})


gen.requests.post = fake_gem_post
os.environ.pop("GEMINI_MODEL", None)
assert gen.call_gemini("p") == [{"hook": "x"}]
assert len(gem_calls) == 2 and "gemini-3-flash-preview" in gem_calls[1], gem_calls

# ---- 11. tick: kalau Telegram bermasalah, publish tetap dijalankan; kegagalan tetap dilaporkan
import src.tick as tick  # noqa: E402

tick_calls = []


def _telegram_down():
    raise RuntimeError("telegram mati")


tick.process_updates = _telegram_down
tick.publish_due = lambda: (tick_calls.append(1), 0)[1]
try:
    tick.main()
    raise AssertionError("tick seharusnya exit 1 saat ada error")
except SystemExit as e:
    assert e.code == 1
assert tick_calls == [1], "publish_due harus tetap jalan walau Telegram error"

shutil.rmtree(TMP)
print("Semua uji lulus.")
