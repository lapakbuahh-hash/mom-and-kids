"""Render Reels vertikal (1080x1920, MP4 H.264 + AAC) dengan Pillow, numpy, dan ffmpeg.

Tiga gaya (lihat `STYLES`):
  - slides_music : kartu bergaya slide carousel yang bergantian, diiringi musik.
  - voiceover    : sama seperti di atas, ditambah narasi suara (TTS gratis lewat edge-tts).
                   Kalau TTS gagal, otomatis turun menjadi slides_music.
  - kinetic      : kalimat besar yang muncul kata demi kata di atas latar warna-warni.

Musik dibuat sendiri lewat sintesis (numpy), jadi bebas masalah hak cipta.
Tidak ada aset eksternal selain font Poppins yang sudah ada di repo.

Uji cepat tanpa Gemini/Instagram:
    python -m src.reels --style kinetic --out /tmp/contoh.mp4
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import random
import subprocess
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .render import (
    MARGIN,
    S,
    Canvas,
    _draw_lines,
    _fit,
    _font_path,
    _mix,
    _palette,
    _tint,
    clean,
    cloud,
    confetti,
    flower,
    heart,
    sparkle,
    star,
    sticker_card,
    sun,
)

W, H = 1080, 1920
FPS = 30
SR = 44100
FADE = 0.45                      # lama transisi antar-adegan (detik)
SAFE_TOP, SAFE_BOTTOM = 260, 400  # area yang tertutup UI Instagram (nama akun, caption, tombol)
STYLES = ("slides_music", "voiceover", "kinetic")
DEFAULT_VOICE = "id-ID-GadisNeural"


class RCanvas(Canvas):
    """Kanvas 2x berukuran 1080x1920 (pakai semua helper gambar dari render.py)."""

    def __init__(self, bg: str):
        self.img = Image.new("RGB", (W * S, H * S), bg)
        self.d = ImageDraw.Draw(self.img)

    def finish(self) -> Image.Image:
        return self.img.resize((W, H), Image.LANCZOS)


# ------------------------------------------------------------------ adegan


def _pastel(pal: dict, number: int) -> str:
    cols = [
        pal["cream"],
        _tint(pal["accent"], 0.7),
        _tint(pal["secondary"], 0.62),
        _tint(pal["primary"], 0.68),
        _tint(pal["sky"], 0.7),
    ]
    return cols[(number - 1) % len(cols)]


def _cover_scene(post: dict, pal: dict, rng: random.Random) -> dict:
    bg = pal["primary"]
    deep = _mix(bg, pal["dark"], 0.18)
    cv = RCanvas(bg)
    sun(cv, W - 220, 250, 72, pal["secondary"])
    cloud(cv, 50, 180, 270, _tint(bg, 0.65))
    cloud(cv, 380, 340, 180, _tint(bg, 0.45))
    confetti(cv, rng, [pal["secondary"], pal["white"], pal["sky"], pal["accent"]], 18, y_max=1500)
    cv.circle(W * 0.5, H + 330, 720, pal["accent"])
    cv.circle(W * 0.1, H + 140, 300, _mix(pal["accent"], pal["sky"], 0.4))

    inner_w = W - 2 * MARGIN - 110
    f, lines, lh = _fit(cv, clean(post["hook"]), "bold", inner_w, 560, 88, 46, 1.22)
    sub = clean(post.get("subhook", ""))
    f2, l2, lh2 = (None, [], 0)
    if sub:
        f2, l2, lh2 = _fit(cv, sub, "regular", inner_w, 220, 40, 28, 1.4)
    pad_top, pad_bot = 100, 80
    card_h = pad_top + len(lines) * lh + (30 + len(l2) * lh2 if l2 else 0) + pad_bot
    top = SAFE_TOP + (H - SAFE_TOP - SAFE_BOTTOM - card_h) / 2
    sticker_card(cv, (MARGIN, top, W - MARGIN, top + card_h), pal, deep)
    y = _draw_lines(cv, lines, f, MARGIN + 55, top + pad_top, lh, pal["dark"], "center", inner_w)
    if l2:
        _draw_lines(cv, l2, f2, MARGIN + 55, y + 30, lh2, _mix(pal["dark"], "#FFFFFF", 0.3), "center", inner_w)

    from .render import _font

    label = clean(post.get("pillar", "")).upper() or "TIPS"
    cf = _font("bold", 30)
    cw = cv.width(label, cf) + 64
    cv.rr((MARGIN + 36, top - 33, MARGIN + 36 + cw, top + 33), 33, pal["secondary"])
    cv.text((MARGIN + 68, top - 19), label, cf, pal["dark"])
    heart(cv, W - MARGIN - 20, top + 5, 100, deep)
    star(cv, MARGIN + 10, top + card_h - 5, 40, pal["secondary"], rot=0.3)
    sparkle(cv, W - MARGIN - 40, top + card_h + 44, 32, pal["white"])
    return {"img": cv.finish(), "kind": "cover"}


def _card_scene(slide: dict, pal: dict, number: int, rng: random.Random) -> dict:
    from .render import _font

    bg = _pastel(pal, number)
    shadow = _mix(bg, pal["dark"], 0.16)
    cv = RCanvas(bg)
    cloud(cv, W - 310, SAFE_TOP - 150, 240, _tint(pal["sky"], 0.6) if bg == pal["cream"] else _tint(bg, 0.6))
    cloud(cv, 40, H - SAFE_BOTTOM - 120, 190, _tint(pal["primary"], 0.55))
    confetti(cv, rng, [pal["primary"], pal["secondary"], pal["accent"], pal["sky"]], 18, y_max=H - 200)

    inner_w = W - 2 * MARGIN - 120
    f, lines, lh = _fit(cv, clean(slide["heading"]), "bold", inner_w, 300, 76, 44, 1.2)
    f2, l2, lh2 = _fit(cv, clean(slide["body"]), "regular", inner_w, 620, 52, 32, 1.5)
    pad_top, gap, pad_bot = 125, 30, 80
    card_h = pad_top + len(lines) * lh + gap + len(l2) * lh2 + pad_bot
    top = SAFE_TOP + (H - SAFE_TOP - SAFE_BOTTOM - card_h) / 2
    sticker_card(cv, (MARGIN, top, W - MARGIN, top + card_h), pal, shadow)
    y = _draw_lines(cv, lines, f, MARGIN + 60, top + pad_top, lh, pal["dark"])
    _draw_lines(cv, l2, f2, MARGIN + 60, y + gap, lh2, pal["dark"])

    petal = [pal["primary"], pal["secondary"], pal["accent"], pal["sky"]][(number - 1) % 4]
    flower(cv, MARGIN + 105, top, 78, petal, pal["white"])
    nf = _font("bold", 62)
    ns = str(number)
    cv.text((MARGIN + 105 - cv.width(ns, nf) / 2, top - 47), ns, nf, pal["dark"])
    star(cv, W - MARGIN - 10, top + card_h - 8, 38, pal["secondary"], rot=0.4)
    heart(cv, W - MARGIN - 62, top - 10, 66, _mix(pal["primary"], pal["dark"], 0.1))
    return {"img": cv.finish(), "kind": "card"}


def _kinetic_scene(slide: dict, pal: dict, number: int, rng: random.Random) -> dict:
    """Latar + daftar kata beserta posisinya; kata digambar bertahap saat render frame."""
    from .render import _font

    bg = _pastel(pal, number)
    shadow = _mix(bg, pal["dark"], 0.16)
    cv = RCanvas(bg)
    box = (MARGIN, 560, W - MARGIN, 1420)
    cloud(cv, W - 320, SAFE_TOP - 130, 240, _tint(pal["sky"], 0.6) if bg == pal["cream"] else _tint(bg, 0.6))
    cloud(cv, 40, 1450, 190, _tint(pal["primary"], 0.55))
    confetti(cv, rng, [pal["primary"], pal["secondary"], pal["accent"], pal["sky"]], 16, y_max=H - 200,
             avoid=(box[0] - 20, box[1] - 60, box[2] + 20, box[3] + 20))
    sticker_card(cv, box, pal, shadow)

    label = clean(slide.get("heading", "")).upper()
    if label:
        lf = _font("bold", 34)
        lw = min(cv.width(label, lf) + 70, W - 2 * MARGIN - 40)
        cx = W / 2
        cv.rr((cx - lw / 2, box[1] - 38, cx + lw / 2, box[1] + 38), 38, [pal["primary"], pal["secondary"], pal["accent"], pal["sky"]][(number - 1) % 4])
        cv.text((cx - cv.width(label, lf) / 2 if cv.width(label, lf) < lw else cx - lw / 2 + 20, box[1] - 22), label, lf, pal["dark"])
    heart(cv, box[2] - 40, box[3] - 10, 80, _mix(pal["primary"], pal["dark"], 0.1))
    star(cv, box[0] + 20, box[3] - 5, 38, pal["secondary"], rot=0.3)

    text = clean(slide["body"])
    inner_w = box[2] - box[0] - 120
    _, lines, lh = _fit(cv, text, "bold", inner_w, box[3] - box[1] - 160, 100, 52, 1.25)
    size = int(round(lh / 1.25))
    font1 = ImageFont.truetype(_font_path("bold"), size)
    total_h = len(lines) * lh
    y = box[1] + (box[3] - box[1] - total_h) / 2
    words = []
    for ln in lines:
        lw = font1.getlength(ln)
        x = (W - lw) / 2
        toks = ln.split(" ")
        for k, tok in enumerate(toks):
            prefix = " ".join(toks[:k]) + (" " if k else "")
            words.append((tok, x + font1.getlength(prefix), y))
        y += lh
    return {"img": cv.finish(), "kind": "kinetic", "words": words, "font": font1, "color": pal["dark"]}


def _cta_scene(post: dict, brand: dict, pal: dict, rng: random.Random) -> dict:
    from .render import _font

    bg = pal["secondary"]
    cv = RCanvas(bg)
    cloud(cv, 50, 200, 250, _tint(bg, 0.6))
    cloud(cv, W - 340, 330, 210, _tint(bg, 0.5))
    confetti(cv, rng, [pal["primary"], pal["white"], pal["accent"], pal["sky"]], 20, y_max=1500,
             avoid=(40, 600, W - 40, 1250))
    cv.circle(W * 0.5, H + 380, 760, _mix(pal["accent"], "#FFFFFF", 0.15))
    heart(cv, W / 2, 640, 250, _mix(pal["primary"], pal["dark"], 0.05))
    sparkle(cv, W / 2 + 200, 540, 40, pal["white"])
    sparkle(cv, W / 2 - 210, 700, 32, pal["white"])

    inner_w = W - 2 * MARGIN
    text = clean(post.get("cta_text") or "Simpan dulu ya, Bunda")
    f, lines, lh = _fit(cv, text, "bold", inner_w, 380, 80, 46, 1.22)
    y = _draw_lines(cv, lines, f, MARGIN, 900, lh, pal["dark"], "center", inner_w)
    hf = _font("semibold", 42)
    handle = brand["handle"]
    tw = cv.width(handle, hf)
    px0 = (W - tw) / 2 - 44
    cv.rr((px0 + 8, y + 50, px0 + tw + 96, y + 146), 48, _mix(bg, pal["dark"], 0.2))
    cv.rr((px0, y + 42, px0 + tw + 88, y + 138), 48, pal["white"])
    cv.text((px0 + 44, y + 64), handle, hf, pal["dark"])
    return {"img": cv.finish(), "kind": "cta"}


def _read_time(text: str, lo: float = 2.8, hi: float = 7.5) -> float:
    return min(hi, max(lo, 1.2 + 0.36 * len(text.split())))


# ------------------------------------------------------------------ musik (sintesis sendiri)


def _midi(n: float) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def _tone(freq: float, dur: float, harmonics=((1, 1.0), (2, 0.3), (3, 0.1))) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    return sum(a * np.sin(2 * np.pi * freq * h * t) for h, a in harmonics)


def _add(out: np.ndarray, seg: np.ndarray, start: int) -> None:
    if start >= len(out):
        return
    end = min(len(out), start + len(seg))
    out[start:end] += seg[: end - start]


def make_music(duration: float, seed: str) -> np.ndarray:
    """Musik latar lembut ala kotak musik: pad akor + bass + denting. Mono float32, panjang = duration."""
    rng = random.Random(seed)
    bpm, transpose = rng.choice([(100, 0), (84, 5), (92, 7)])
    beat = 60 / bpm
    bar = 4 * beat
    prog = [(0, (0, 4, 7)), (9, (0, 3, 7)), (5, (0, 4, 7)), (7, (0, 4, 7))]  # I vi IV V
    base = 48 + transpose
    n = int((duration + 3) * SR)
    out = np.zeros(n)

    for b in range(int(duration / bar) + 2):
        root, ints = prog[b % 4]
        t0 = int(b * bar * SR)
        seg_len = bar + 0.5
        t = np.arange(int(seg_len * SR)) / SR
        env = np.minimum(1, t / 0.35) * np.minimum(1, np.maximum(0, (seg_len - t) / 0.5))
        for iv in ints:
            _add(out, _tone(_midi(base + 12 + root + iv), seg_len) * env * 0.07, t0)
        for beat_i in (0, 2):  # bass di ketukan 1 dan 3
            bt = np.arange(int(beat * 1.8 * SR)) / SR
            bass = _tone(_midi(base + root), beat * 1.8, ((1, 1.0), (2, 0.2))) * np.exp(-bt * 2.2)
            _add(out, bass * 0.16, t0 + int(beat_i * beat * SR))
        for step in range(8):  # denting delapanan
            if rng.random() < 0.72:
                note = base + 24 + root + rng.choice(list(ints) + [12])
                bt = np.arange(int(1.4 * SR)) / SR
                bell = _tone(_midi(note), 1.4, ((1, 1.0), (3, 0.22), (4.2, 0.08))) * np.exp(-bt * 3.2)
                bell[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
                _add(out, bell * 0.10, t0 + int(step * beat / 2 * SR))

    out = out[: int(duration * SR)]
    out = out / (np.max(np.abs(out)) + 1e-9) * 0.55
    fi, fo = int(0.6 * SR), int(1.5 * SR)
    out[:fi] *= np.linspace(0, 1, fi)
    out[-fo:] *= np.linspace(1, 0, fo)
    return out.astype(np.float32)


# ------------------------------------------------------------------ suara (TTS gratis)


def _decode_audio(path: str) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def synth_voice(texts: list[str], voice: str, workdir: pathlib.Path) -> list[np.ndarray] | None:
    """Buat narasi per adegan dengan edge-tts. Mengembalikan None kalau gagal (pemanggil turun ke tanpa suara)."""
    try:
        import edge_tts
    except ImportError:
        print("[warn] edge-tts belum terpasang, Reels dibuat tanpa narasi")
        return None

    async def run() -> list[str]:
        paths = []
        for i, text in enumerate(texts):
            p = str(workdir / f"voice_{i}.mp3")
            await edge_tts.Communicate(text, voice, rate="-4%").save(p)
            paths.append(p)
        return paths

    try:
        paths = asyncio.run(run())
        tracks = [_decode_audio(p) for p in paths]
        if any(len(t) < SR * 0.3 for t in tracks):
            raise RuntimeError("audio narasi kosong")
        return tracks
    except Exception as e:  # noqa: BLE001 - TTS tidak boleh menggagalkan seluruh Reels
        print(f"[warn] TTS gagal ({e}), Reels dibuat tanpa narasi")
        return None


# ------------------------------------------------------------------ frame & video


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _compose(scene: dict, n_words: int, cache: dict) -> Image.Image:
    if scene["kind"] != "kinetic":
        return scene["img"]
    key = (id(scene), n_words)
    if key not in cache:
        im = scene["img"].copy()
        d = ImageDraw.Draw(im)
        for tok, x, y in scene["words"][:n_words]:
            d.text((x, y), tok, font=scene["font"], fill=scene["color"])
        cache.clear() if len(cache) > 40 else None
        cache[key] = im
    return cache[key]


def _zoom(im: Image.Image, z: float) -> Image.Image:
    if z <= 1.0005:
        return im
    cw, ch = W / z, H / z
    x0, y0 = (W - cw) / 2, (H - ch) / 2
    return im.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))


def _frames(scenes: list[dict]):
    cache: dict = {}
    last = None
    for sc in scenes:
        nf = max(1, round(sc["dur"] * FPS))
        words = sc.get("words") or []
        for k in range(nf):
            t = k / FPS
            n_words = 0
            if words:
                n_words = min(len(words), int(max(0.0, t - 0.25) / (sc["dur"] * 0.55) * len(words)) + 1)
            frame = _zoom(_compose(sc, n_words, cache), 1 + 0.035 * k / nf)
            if last is not None and t < FADE:
                frame = Image.blend(last, frame, _ease(t / FADE))
            last = frame
            yield frame


def _write_wav(path: pathlib.Path, data: np.ndarray) -> None:
    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _mix_audio(total: float, starts: list[float], voices: list[np.ndarray] | None, seed: str) -> np.ndarray:
    music = make_music(total, seed)
    if not voices:
        return music * 0.9
    n = len(music)
    voice = np.zeros(n, dtype=np.float32)
    for st, v in zip(starts, voices):
        a = int((st + 0.3) * SR)
        if a < n:
            seg = v[: n - a]
            voice[a : a + len(seg)] += seg
    # musik mengecil saat ada suara (ducking halus)
    active = (np.abs(voice) > 0.02).astype(np.float32)
    win = int(0.35 * SR)
    smooth = np.convolve(active, np.ones(win, dtype=np.float32) / win, mode="same")
    gain = 1.0 - 0.72 * np.clip(smooth * 2.5, 0, 1)
    mixed = music * gain * 0.9 + voice * 1.0
    peak = np.max(np.abs(mixed))
    return (mixed / peak * 0.95).astype(np.float32) if peak > 0.95 else mixed


def render_reel(post: dict, brand: dict, out_path: pathlib.Path, use_voice: bool = True) -> dict:
    """Buat file MP4 Reels. Mengembalikan info: gaya yang akhirnya dipakai, durasi, ukuran (MB), ada suara atau tidak."""
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pal = _palette(brand)
    seed = post.get("id", "x")
    style = post.get("style", "slides_music")
    if style not in STYLES:
        style = "slides_music"
    slides = post["slides"]
    cfg = brand.get("reels", {}) or {}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)

        voices = None
        if style == "voiceover" and use_voice:
            texts = [post["hook"]] + [s.get("voice") or s["body"] for s in slides] + [post.get("cta_text") or ""]
            texts = [clean(t) or "Yuk simak ya, Bunda" for t in texts]
            voices = synth_voice(texts, cfg.get("voice", DEFAULT_VOICE), tmp_dir)
        if style == "voiceover" and not voices:
            style = "slides_music"  # tanpa suara, tampil sebagai Reels slide + musik

        scenes = [_cover_scene(post, pal, random.Random(f"{seed}-0"))]
        for i, s in enumerate(slides, start=1):
            rng = random.Random(f"{seed}-{i}")
            scenes.append(_kinetic_scene(s, pal, i, rng) if style == "kinetic" else _card_scene(s, pal, i, rng))
        scenes.append(_cta_scene(post, brand, pal, random.Random(f"{seed}-cta")))

        scenes[0]["dur"] = _read_time(clean(post["hook"]), 3.0, 4.5)
        for sc, s in zip(scenes[1:-1], slides):
            sc["dur"] = _read_time(clean(s["heading"]) + " " + clean(s["body"]))
            if style == "kinetic":
                sc["dur"] = _read_time(clean(s["body"]), 2.6, 5.5)
        scenes[-1]["dur"] = 3.5
        if voices:
            for sc, v in zip(scenes, voices):
                sc["dur"] = max(2.6, len(v) / SR + 0.8)

        starts, t = [], 0.0
        for sc in scenes:
            starts.append(t)
            t += sc["dur"]
        total = t

        wav = tmp_dir / "audio.wav"
        _write_wav(wav, _mix_audio(total, starts, voices, seed))

        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
            "-i", str(wav),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-r", str(FPS), "-g", str(FPS * 2),
            "-c:a", "aac", "-b:a", "128k", "-ar", str(SR), "-ac", "2",
            "-movflags", "+faststart", "-use_editlist", "0", "-shortest",
            str(out_path),
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for frame in _frames(scenes):
                proc.stdin.write(frame.convert("RGB").tobytes())  # type: ignore[union-attr]
        finally:
            proc.stdin.close()  # type: ignore[union-attr]
            code = proc.wait()
        if code != 0:
            raise RuntimeError(f"ffmpeg gagal (kode {code})")

    size_mb = out_path.stat().st_size / 1_048_576
    return {"style": style, "duration": round(total, 1), "size_mb": round(size_mb, 2), "voice": bool(voices)}


# ------------------------------------------------------------------ uji cepat

_DEMO = {
    "id": "demo",
    "pillar": "Main Seru",
    "hook": "Bun, 3 kegiatan tenang 10 menit sebelum si kecil tidur siang",
    "subhook": "Nggak perlu alat mahal, pakai yang ada di rumah aja",
    "slides": [
        {"heading": "Susun balok warna", "body": "Susun balok atau tutup botol dari yang paling terang ke paling gelap.",
         "voice": "Pertama, ajak si kecil menyusun balok warna dari yang paling terang ke paling gelap."},
        {"heading": "Tebak ceritanya", "body": "Buka buku bergambar, lalu tanya, habis ini apa ya?",
         "voice": "Kedua, buka buku bergambar, lalu tanya pelan-pelan, habis ini apa ya?"},
        {"heading": "Cari benda bulat", "body": "Cari tiga benda bulat di ruang tamu bareng-bareng.",
         "voice": "Ketiga, yuk cari tiga benda bulat di ruang tamu bareng-bareng."},
    ],
    "cta_text": "Simpan dulu ya, Bunda, buat jadwal tidur siang besok",
}


def main() -> None:
    from .common import load_brand

    ap = argparse.ArgumentParser()
    ap.add_argument("--style", choices=STYLES, default="slides_music")
    ap.add_argument("--out", default="contoh_reel.mp4")
    ap.add_argument("--no-voice", action="store_true")
    args = ap.parse_args()
    post = dict(_DEMO, style=args.style)
    print(render_reel(post, load_brand(), pathlib.Path(args.out), use_voice=not args.no_voice))


if __name__ == "__main__":
    main()
