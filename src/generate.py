"""Buat rencana konten mingguan dengan Gemini, render slide, lalu kirim ke Telegram untuk direview.

Pemakaian:
    python -m src.generate            # pakai Gemini (butuh GEMINI_API_KEY)
    python -m src.generate --sample   # data contoh, tanpa API, untuk uji render
    python -m src.generate --no-telegram   # jangan kirim ke Telegram
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import time

import requests

from .common import POSTS_DIR, env, get_tz, load_brand, load_posts, now, save_posts
from .render import render_post

MAX_CAPTION = 2200

SAMPLE_POSTS = [
    {
        "pillar": "Edukasi",
        "topic": "Aktivitas 10 menit sebelum tidur siang",
        "hook": "3 kegiatan tenang 10 menit untuk anak sebelum tidur siang",
        "subhook": "Tanpa alat mahal, cukup yang ada di rumah",
        "slides": [
            {"heading": "Susun balok warna", "body": "Minta si kecil mengurutkan balok atau tutup botol dari warna paling terang ke paling gelap. Melatih fokus dan mengenal warna."},
            {"heading": "Cerita dari gambar", "body": "Buka buku bergambar, lalu ajak anak menebak apa yang terjadi di halaman berikutnya. Suara dibuat pelan agar suasana tenang."},
            {"heading": "Cari benda bulat", "body": "Ajak anak mencari tiga benda bulat di ruang tamu dan menyentuhnya satu per satu. Sederhana tapi seru."},
        ],
        "cta_text": "Simpan untuk jadwal tidur siang besok",
        "caption": "Waktu menjelang tidur siang sering jadi momen yang bikin ibu menarik napas panjang. Coba tiga kegiatan tenang ini, pilih yang paling cocok untuk si kecil. Mana yang mau kamu coba duluan?",
        "hashtags": ["#aktivitasanak", "#tidursiang", "#montessoriindonesia", "#mainbareng"],
    },
    {
        "pillar": "Produk",
        "topic": "Printable agar anak betah belajar di rumah",
        "hook": "Anak cepat bosan belajar? Coba ubah caranya, bukan memaksa",
        "subhook": "Lembar kerja singkat yang terasa seperti permainan",
        "slides": [
            {"heading": "Singkat itu kunci", "body": "Satu lembar, lima menit, selesai. Anak merasa berhasil, ibu tidak perlu mengomel."},
            {"heading": "Visual yang ramai", "body": "Gambar dan warna membuat anak lebih mau duduk dan mencoba."},
            {"heading": "Cetak sesuai kebutuhan", "body": "Cukup cetak lembar yang dibutuhkan hari itu, tanpa menumpuk buku di rumah."},
        ],
        "cta_text": "Cek link di bio untuk printable-nya",
        "caption": "Belajar di rumah tidak harus panjang dan melelahkan. Lembar kerja singkat bisa jadi cara yang pas untuk memulai kebiasaan belajar yang menyenangkan. Link ada di bio ya.",
        "hashtags": ["#printableanak", "#lembarkerjaanak", "#belajardirumah"],
    },
]


# ---------------------------------------------------------------- prompt


def _weighted_pillars(brand: dict, n: int) -> list[str]:
    pillars = brand["content_pillars"]
    total = sum(p.get("weight", 1) for p in pillars)
    out: list[str] = []
    for p in pillars:
        out += [p["name"]] * max(1, round(n * p.get("weight", 1) / total))
    random.shuffle(out)
    while len(out) < n:
        out.append(random.choice(pillars)["name"])
    return out[:n]


def build_prompt(brand: dict, history: list[str], pillars: list[str]) -> str:
    products = "\n".join(f"- {p['name']}: {p['description']}" for p in brand["products"])
    pillar_ideas = "\n".join(f"- {p['name']}: {p['idea']}" for p in brand["content_pillars"])
    avoid = "\n".join(f"- {a}" for a in brand.get("avoid", []))
    ctas = "\n".join(f"- {c}" for c in brand.get("cta_options", []))
    past = "\n".join(f"- {t}" for t in history[-25:]) or "(belum ada)"
    plan = "\n".join(f"{i + 1}. pilar: {p}" for i, p in enumerate(pillars))

    return f"""Kamu adalah content strategist Instagram untuk brand "{brand['brand_name']}".
Niche: {brand['niche']}
Audiens: {brand['audience']}
Gaya bahasa: {brand['tone']}

Produk digital brand ini:
{products}

Pilar konten:
{pillar_ideas}

Hindari:
{avoid}

Pilihan ajakan (CTA) yang boleh dipakai atau disesuaikan:
{ctas}

Topik yang SUDAH pernah dibuat (jangan diulang atau dibuat mirip):
{past}

Buat {len(pillars)} postingan carousel Instagram dengan urutan pilar berikut:
{plan}

Aturan tiap postingan:
- "hook": judul slide pertama, maksimal 70 karakter, memancing orang berhenti scroll, jujur (bukan clickbait menyesatkan).
- "subhook": satu kalimat pendukung, maksimal 70 karakter.
- "slides": tepat 3 sampai 5 slide isi. Tiap slide punya "heading" (maksimal 35 karakter) dan "body" (maksimal 170 karakter, 1-3 kalimat pendek).
- "cta_text": ajakan slide terakhir, maksimal 60 karakter.
- "caption": 300-700 karakter, ditulis seperti teman, ada pertanyaan pemancing komentar di akhir. Boleh pakai 1-3 emoji. Jangan menaruh hashtag di caption.
- "hashtags": 6-10 hashtag relevan huruf kecil, diawali #.
- Postingan pilar "Produk" harus soft-sell: mulai dari masalah ibu, baru kaitkan ke produk di atas. Sebut nama produk hanya jika benar-benar relevan.
- Jangan membuat klaim medis, statistik, atau nama penelitian. Jangan teks slide memakai emoji.
- Semua dalam bahasa Indonesia.

Balas HANYA dengan JSON array valid, tanpa teks lain. Setiap elemen berbentuk:
{{"pillar": "...", "topic": "ringkasan topik 5-10 kata", "hook": "...", "subhook": "...",
  "slides": [{{"heading": "...", "body": "..."}}], "cta_text": "...", "caption": "...", "hashtags": ["#..."]}}"""


# ---------------------------------------------------------------- gemini


def call_gemini(prompt: str) -> list[dict]:
    key = env("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "responseMimeType": "application/json"},
    }
    last_err = None
    for attempt in range(4):
        try:
            r = requests.post(url, headers={"x-goog-api-key": key}, json=body, timeout=180)
            if r.status_code in (429, 500, 503):
                raise RuntimeError(f"Gemini sibuk/limit ({r.status_code}): {r.text[:200]}")
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return _parse_json_list(text)
        except Exception as e:  # noqa: BLE001 - kita ulang untuk semua error sementara
            last_err = e
            time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"Gagal memanggil Gemini setelah beberapa percobaan: {last_err}")


def _parse_json_list(text: str) -> list[dict]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("posts") or [data]
    if not isinstance(data, list):
        raise ValueError("Respons Gemini bukan array JSON")
    return data


# ---------------------------------------------------------------- validasi


def normalize_post(raw: dict, brand: dict) -> dict | None:
    try:
        slides = [
            {"heading": str(s["heading"]).strip(), "body": str(s["body"]).strip()}
            for s in raw["slides"]
            if s.get("heading") and s.get("body")
        ][:5]
        if len(slides) < 2:
            return None
        hook = str(raw["hook"]).strip()
        caption = str(raw["caption"]).strip()
        if not hook or not caption:
            return None
    except (KeyError, TypeError):
        return None

    tags: list[str] = []
    for t in list(brand.get("hashtags_base", [])) + list(raw.get("hashtags", [])):
        t = "#" + re.sub(r"[^\w]", "", str(t).lstrip("#")).lower()
        if len(t) > 1 and t not in tags:
            tags.append(t)
    tags = tags[:20]

    full = caption + "\n\n" + " ".join(tags)
    while len(full) > MAX_CAPTION and tags:
        tags.pop()
        full = caption + "\n\n" + " ".join(tags)
    if len(full) > MAX_CAPTION:
        caption = caption[: MAX_CAPTION - 5].rsplit(" ", 1)[0] + "..."
        full = caption

    return {
        "pillar": str(raw.get("pillar", "")).strip(),
        "topic": str(raw.get("topic", hook)).strip(),
        "hook": hook,
        "subhook": str(raw.get("subhook", "")).strip(),
        "slides": slides,
        "cta_text": str(raw.get("cta_text", "")).strip(),
        "caption": caption,
        "hashtags": tags,
        "full_caption": full,
    }


# ---------------------------------------------------------------- jadwal


def assign_slots(brand: dict, count: int, start_date: dt.date) -> list[dt.datetime]:
    tz = get_tz(brand)
    times = brand.get("post_times", ["12:00"])
    slots = []
    for i in range(count):
        day_offset = int(i * 7 / count)
        hh, mm = map(int, times[i % len(times)].split(":"))
        d = start_date + dt.timedelta(days=day_offset)
        slots.append(dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz))
    return slots


# ---------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="pakai data contoh tanpa memanggil Gemini")
    ap.add_argument("--no-telegram", action="store_true", help="jangan kirim ke Telegram")
    args = ap.parse_args()

    brand = load_brand()
    posts = load_posts()
    n = int(brand.get("posts_per_week", 5))

    if args.sample:
        raw_posts = SAMPLE_POSTS
    else:
        history = [p.get("topic", "") for p in posts]
        pillars = _weighted_pillars(brand, n)
        raw_posts = call_gemini(build_prompt(brand, history, pillars))

    clean = [p for p in (normalize_post(r, brand) for r in raw_posts) if p]
    if not clean:
        raise SystemExit("Tidak ada postingan valid dari Gemini. Coba jalankan ulang.")

    tomorrow = (now(brand) + dt.timedelta(days=1)).date()
    slots = assign_slots(brand, len(clean), tomorrow)
    stamp = now(brand).strftime("%Y%m%d-%H%M")

    new_posts = []
    for i, (post, slot) in enumerate(zip(clean, slots), start=1):
        post_id = f"{stamp}-{i:02d}"
        files = render_post(post, brand, POSTS_DIR / post_id)
        post.update(
            {
                "id": post_id,
                "status": "draft",
                "scheduled_at": slot.isoformat(),
                "images": files,
                "created_at": now(brand).isoformat(),
                "attempts": 0,
            }
        )
        new_posts.append(post)
        print(f"[ok] {post_id} | {post['pillar']} | {post['hook']}")

    posts.extend(new_posts)
    save_posts(posts)

    if not args.no_telegram:
        from .telegram import send_post_for_review

        for p in new_posts:
            send_post_for_review(p, brand)
            time.sleep(1.5)
        print(f"{len(new_posts)} draf dikirim ke Telegram.")


if __name__ == "__main__":
    main()
