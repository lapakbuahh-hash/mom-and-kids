"""Bot Telegram: kirim draf untuk direview (tombol Approve/Skip) dan baca jawabannya.

Karena berjalan di GitHub Actions (tidak ada server yang menyala terus), jawaban tombol
diproses secara berkala lewat getUpdates oleh src/tick.py.
"""
from __future__ import annotations

import json

import requests

from .common import POSTS_DIR, env, find_post, load_posts, load_state, parse_iso, save_posts, save_state


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/{method}"


def _call(method: str, **kwargs):
    r = requests.post(_api(method), timeout=60, **kwargs)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} gagal: {data}")
    return data["result"]


def notify(text: str) -> None:
    """Kirim pesan teks biasa ke pemilik. Gagal kirim tidak boleh menghentikan proses."""
    try:
        _call("sendMessage", json={"chat_id": env("TELEGRAM_CHAT_ID"), "text": text[:4000], "disable_web_page_preview": True})
    except Exception as e:  # noqa: BLE001
        print(f"[warn] notifikasi Telegram gagal: {e}")


def send_post_for_review(post: dict, brand: dict) -> None:
    chat_id = env("TELEGRAM_CHAT_ID")
    folder = POSTS_DIR / post["id"]
    files, media = {}, []
    for i, name in enumerate(post["images"][:10]):
        key = f"photo{i}"
        files[key] = (name, open(folder / name, "rb"), "image/png")
        media.append({"type": "photo", "media": f"attach://{key}"})
    _call("sendMediaGroup", data={"chat_id": chat_id, "media": json.dumps(media)}, files=files)

    when = parse_iso(post["scheduled_at"]).strftime("%a %d %b %Y, %H:%M")
    text = (
        f"Draf {post['id']}\n"
        f"Pilar: {post['pillar']}\n"
        f"Jadwal tayang: {when}\n\n"
        f"{post['full_caption']}"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Approve", "callback_data": f"approve:{post['id']}"},
                {"text": "Skip", "callback_data": f"skip:{post['id']}"},
            ]
        ]
    }
    msg = _call("sendMessage", json={"chat_id": chat_id, "text": text[:4000], "reply_markup": keyboard})
    post["telegram_message_id"] = msg["message_id"]


def process_updates() -> int:
    """Baca klik tombol baru dan perbarui status postingan. Mengembalikan jumlah yang diproses."""
    state = load_state()
    offset = state.get("telegram_offset", 0)
    r = requests.get(
        _api("getUpdates"),
        params={"offset": offset, "timeout": 0, "allowed_updates": json.dumps(["callback_query"])},
        timeout=60,
    )
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"getUpdates gagal: {data}")

    owner = str(env("TELEGRAM_CHAT_ID"))
    posts = load_posts()
    handled = 0
    for upd in data["result"]:
        offset = max(offset, upd["update_id"] + 1)
        cq = upd.get("callback_query")
        if not cq:
            continue
        # Hanya pemilik yang boleh menyetujui.
        if str(cq["message"]["chat"]["id"]) != owner:
            continue
        action, _, post_id = cq["data"].partition(":")
        post = find_post(posts, post_id)
        if not post or post["status"] not in ("draft", "approved", "skipped"):
            _call("answerCallbackQuery", json={"callback_query_id": cq["id"], "text": "Postingan tidak bisa diubah lagi."})
            continue

        if action == "approve":
            post["status"] = "approved"
            label = "Disetujui. Tayang " + parse_iso(post["scheduled_at"]).strftime("%a %d %b, %H:%M")
        elif action == "skip":
            post["status"] = "skipped"
            label = "Dilewati."
        else:
            continue
        handled += 1
        _call("answerCallbackQuery", json={"callback_query_id": cq["id"], "text": label})
        try:
            _call(
                "editMessageReplyMarkup",
                json={"chat_id": owner, "message_id": cq["message"]["message_id"], "reply_markup": {"inline_keyboard": []}},
            )
            _call("sendMessage", json={"chat_id": owner, "text": f"{post['id']}: {label}"})
        except Exception as e:  # noqa: BLE001
            print(f"[warn] gagal memperbarui pesan: {e}")

    save_posts(posts)
    state["telegram_offset"] = offset
    save_state(state)
    return handled


if __name__ == "__main__":
    # Bantuan setup: `python -m src.telegram` menampilkan chat id dari pesan terakhir ke bot.
    res = requests.get(_api("getUpdates"), timeout=60).json()
    for u in res.get("result", []):
        msg = u.get("message") or {}
        chat = msg.get("chat")
        if chat:
            print("chat_id:", chat["id"], "| dari:", chat.get("first_name") or chat.get("title"))
