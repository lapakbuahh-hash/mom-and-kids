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
        "pillar": "Main Seru",
        "topic": "Kegiatan tenang 10 menit sebelum tidur siang",
        "hook": "Bun, 3 kegiatan tenang 10 menit sebelum si kecil tidur siang",
        "subhook": "Nggak perlu alat mahal, pakai yang ada di rumah aja",
        "slides": [
            {"heading": "Susun balok warna", "body": "Ajak si kecil menyusun balok atau tutup botol dari yang paling terang ke paling gelap. Seru, dan dia jadi lebih tenang."},
            {"heading": "Tebak ceritanya", "body": "Buka buku bergambar, lalu tanya, \"Menurut adek, habis ini apa ya?\" Pelan-pelan aja, biar suasananya adem."},
            {"heading": "Cari benda bulat", "body": "Yuk cari tiga benda bulat di ruang tamu bareng-bareng. Sambil jalan santai, sambil ngobrol."},
        ],
        "cta_text": "Simpan dulu ya, Bunda, buat jadwal tidur siang besok",
        "caption": "Jam menjelang tidur siang kadang bikin Bunda ingin tarik napas panjang, ya kan? Tenang, kita coba pelan-pelan aja. Tiga kegiatan kecil ini bisa bikin suasana jadi lebih adem, dan Bunda bisa ikut ngaso sebentar \U0001F49B Menurut Bunda, yang mana yang paling cocok buat si kecil? Cerita di komentar yuk!",
        "hashtags": ["#aktivitasanak", "#tidursiang", "#mainbareng"],
    },
    {
        "pillar": "Info Produk",
        "topic": "Lembar kerja singkat biar anak betah belajar",
        "hook": "Si kecil cepat bosan belajar? Nggak apa-apa, Bun!",
        "subhook": "Coba ganti caranya, bukan dipaksa",
        "slides": [
            {"heading": "Singkat itu kunci", "body": "Satu lembar, lima menit, selesai. Si kecil merasa berhasil, Bunda juga nggak perlu ngomel."},
            {"heading": "Warna-warni itu menarik", "body": "Gambar yang ceria bikin anak lebih mau duduk dan mencoba. Belajar jadi terasa seperti main."},
            {"heading": "Cetak secukupnya", "body": "Cetak lembar yang dibutuhkan hari itu aja. Rumah nggak penuh tumpukan buku."},
        ],
        "cta_text": "Printable-nya ada di link bio ya, Bunda",
        "caption": "Pernah nggak, Bun, baru lima menit belajar si kecil sudah kabur main? Itu wajar banget kok \U0001F338 Kadang yang perlu diganti bukan anaknya, tapi caranya. Lembar kerja singkat yang berwarna bisa bantu belajar terasa lebih ringan. Link printable ada di bio ya!",
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
    reader = brand.get("reader_nickname", "Bunda")
    kid = brand.get("kid_nickname", "si kecil")

    return f"""Kamu adalah penulis konten Instagram untuk brand "{brand['brand_name']}", yang menulis seperti sahabat sesama ibu.
Niche: {brand['niche']}
Audiens: {brand['audience']}
Karakter suara brand: {brand['tone']}

PANDUAN GAYA BAHASA (sangat penting, ikuti di setiap slide dan caption):
- Sapa pembaca dengan "{reader}" dan sebut anak dengan "{kid}" atau "adek". Pakai "kita" supaya terasa bersama.
- Tulis bahasa Indonesia sehari-hari seperti chat ke teman: boleh "nih", "yuk", "ya", "deh", "lho", "banget", "nggak", "aja".
- Jangan pakai "Anda", kata baku yang kaku, atau istilah akademik. Bayangkan kamu bicara di warung kopi, bukan menulis jurnal.
- Kalimat pendek, 8-14 kata. Satu ide per kalimat.
- Nada hangat, ceria, dan menyemangati. Akui perasaan ibu dulu ("Nggak apa-apa, Bun, itu wajar banget") sebelum memberi tips.
- Hook memancing rasa penasaran dengan gaya ngobrol, misalnya "Bun, pernah nggak..." atau "Yuk coba 3 permainan seru ini".
- Caption dibuka dengan sapaan atau momen yang relatable, memakai 2-4 emoji hangat yang pas (misalnya hati kuning, bunga, bintang, pelangi, beruang), dan ditutup pertanyaan ajakan komentar.
- Hindari: nada menggurui, daftar kaku, kalimat panjang berbelit, dan membuat ibu merasa bersalah.

Contoh perbandingan gaya:
- KAKU (jangan): "Aktivitas sensorik dapat membantu meningkatkan konsentrasi anak."
- HANGAT (tiru): "Main tepung dan air itu seru banget, Bun. Tangan si kecil sibuk, Bunda bisa napas sebentar."
- KAKU (jangan): "Berikut adalah tiga tips efektif untuk mengatasi anak yang rewel."
- HANGAT (tiru): "Si kecil lagi rewel? Tenang, Bun. Coba tiga hal kecil ini dulu yuk."

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
- "hook": judul slide pertama, maksimal 70 karakter, gaya ngobrol, memancing orang berhenti scroll, jujur (bukan clickbait menyesatkan).
- "subhook": satu kalimat pendukung yang menenangkan atau menjanjikan hal mudah, maksimal 70 karakter.
- "slides": tepat 3 sampai 5 slide isi. Tiap slide punya "heading" (maksimal 35 karakter, singkat dan ramah) dan "body" (maksimal 170 karakter, 1-3 kalimat pendek bergaya ngobrol).
- "cta_text": ajakan slide terakhir, maksimal 60 karakter, ramah dan menyapa pembaca.
- "caption": 300-700 karakter, ditulis seperti pesan ke teman, ada pertanyaan pemancing komentar di akhir. Jangan menaruh hashtag di caption.
- "hashtags": 6-10 hashtag relevan huruf kecil, diawali #.
- Postingan pilar "Info Produk" harus soft-sell: mulai dari masalah atau perasaan ibu, baru kaitkan ke produk di atas. Sebut nama produk hanya jika benar-benar relevan.
- Jangan membuat klaim medis, statistik, atau nama penelitian. Teks di slide (hook, subhook, heading, body, cta_text) JANGAN memakai emoji; emoji hanya di caption.
- Semua dalam bahasa Indonesia.

Balas HANYA dengan JSON array valid, tanpa teks lain. Setiap elemen berbentuk:
{{"pillar": "...", "topic": "ringkasan topik 5-10 kata", "hook": "...", "subhook": "...",
  "slides": [{{"heading": "...", "body": "..."}}], "cta_text": "...", "caption": "...", "hashtags": ["#..."]}}"""


# ---------------------------------------------------------------- gemini


def call_gemini(prompt: str) -> list[dict]:
    """Panggil Gemini. Kalau nama model sudah tidak tersedia (404), otomatis coba model cadangan."""
    key = env("GEMINI_API_KEY")
    first = os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite"
    candidates = [first] + [m for m in ("gemini-3-flash-preview", "gemini-flash-latest") if m != first]
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.95, "responseMimeType": "application/json"},
    }
    last_err = None
    for model in candidates:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(3):
            try:
                r = requests.post(url, headers={"x-goog-api-key": key}, json=body, timeout=180)
                if r.status_code == 404:
                    last_err = f"model {model} tidak ditemukan (404)"
                    print(f"[warn] {last_err}, mencoba model berikutnya")
                    break  # langsung ke model cadangan, tidak perlu mengulang
                if r.status_code in (429, 500, 503):
                    raise RuntimeError(f"Gemini sibuk/limit ({r.status_code}): {r.text[:200]}")
                r.raise_for_status()
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                print(f"[ok] model yang dipakai: {model}")
                return _parse_json_list(text)
            except Exception as e:  # noqa: BLE001 - ulang untuk error sementara
                last_err = e
                time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"Gagal memanggil Gemini: {last_err}")


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
