"""Render slide carousel (1080x1350, rasio 4:5) dengan Pillow.

Tampilan ceria: palet hangat, kartu "stiker" dengan bayangan, hiasan bentuk (hati, bintang,
awan, matahari, bunga), dan font Poppins. Digambar 2x lalu diperkecil agar tepinya halus.
Font dicari di assets/fonts; kalau tidak ada dipakai DejaVu agar tetap jalan.
"""
from __future__ import annotations

import math
import pathlib
import random
import re

from PIL import Image, ImageDraw, ImageFont

from .common import FONT_DIR

W, H = 1080, 1350
S = 2            # faktor supersampling
MARGIN = 90

_FALLBACKS = {
    "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "semibold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "regular": ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}
_NAMES = {"bold": "Poppins-Bold.ttf", "semibold": "Poppins-SemiBold.ttf", "regular": "Poppins-Regular.ttf"}

# Emoji tidak ada di font slide; dibuang dari teks slide (tetap boleh di caption).
_EMOJI = re.compile(
    "[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0000FE0F\U0000200D\U00002B00-\U00002BFF]+"
)

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


# ------------------------------------------------------------------ warna


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb(c: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % c


def _mix(a: str, b: str, t: float) -> str:
    """Campur warna a dengan b; t=0 -> a, t=1 -> b."""
    ra, rb = _hex(a), _hex(b)
    return _rgb(tuple(int(x + (y - x) * t) for x, y in zip(ra, rb)))  # type: ignore[arg-type]


def _tint(color: str, amount: float) -> str:
    return _mix(color, "#FFFFFF", amount)


def _palette(brand: dict) -> dict:
    c = brand.get("colors", {}) or {}
    return {
        "primary": c.get("primary", "#FF8FA3"),     # merah muda
        "secondary": c.get("secondary", "#FFD166"),  # kuning matahari
        "accent": c.get("accent", "#7ED6C1"),        # mint
        "sky": c.get("sky", "#8ECAE6"),              # biru langit
        "cream": c.get("cream", "#FFF7EA"),
        "dark": c.get("dark", "#4B3A3F"),
        "white": c.get("white", "#FFFFFF"),
    }


# ------------------------------------------------------------------ font & teks


def _font_path(weight: str) -> str:
    local = FONT_DIR / _NAMES[weight]
    if local.exists():
        return str(local)
    for p in _FALLBACKS[weight]:
        if pathlib.Path(p).exists():
            return p
    raise RuntimeError("Font tidak ditemukan. Jalankan scripts/get_fonts.sh atau taruh Poppins di assets/fonts/.")


def _font(weight: str, size: float) -> ImageFont.FreeTypeFont:
    key = (weight, int(size * S))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(_font_path(weight), key[1])
    return _font_cache[key]


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", _EMOJI.sub("", text or "")).strip()


# ------------------------------------------------------------------ kanvas 2x


class Canvas:
    """Semua koordinat dalam satuan 1080x1350; digambar di kanvas 2x."""

    def __init__(self, bg: str):
        self.img = Image.new("RGB", (W * S, H * S), bg)
        self.d = ImageDraw.Draw(self.img)

    def rr(self, box, radius, fill):
        x0, y0, x1, y1 = box
        self.d.rounded_rectangle((x0 * S, y0 * S, x1 * S, y1 * S), radius=radius * S, fill=fill)

    def circle(self, cx, cy, r, fill):
        self.d.ellipse(((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S), fill=fill)

    def poly(self, pts, fill):
        self.d.polygon([(x * S, y * S) for x, y in pts], fill=fill)

    def text(self, xy, s, font, fill):
        self.d.text((xy[0] * S, xy[1] * S), s, font=font, fill=fill)

    def width(self, s, font) -> float:
        return self.d.textlength(s, font=font) / S

    def finish(self) -> Image.Image:
        return self.img.resize((W, H), Image.LANCZOS)


def _wrap(cv: Canvas, text: str, font, max_w: float) -> list[str]:
    lines: list[str] = []
    cur = ""
    for w in text.split(" "):
        trial = f"{cur} {w}".strip()
        if cv.width(trial, font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit(cv, text, weight, max_w, max_h, start, minimum, spacing=1.25):
    """Cari ukuran font terbesar agar teks muat di kotak max_w x max_h."""
    size = start
    while size >= minimum:
        f = _font(weight, size)
        lines = _wrap(cv, text, f, max_w)
        if len(lines) * size * spacing <= max_h:
            return f, lines, size * spacing
        size -= 2
    f = _font(weight, minimum)
    return f, _wrap(cv, text, f, max_w), minimum * spacing


def _draw_lines(cv, lines, font, x, y, lh, fill, align="left", box_w=0):
    for ln in lines:
        lx = x if align == "left" else x + (box_w - cv.width(ln, font)) / 2
        cv.text((lx, y), ln, font, fill)
        y += lh
    return y


# ------------------------------------------------------------------ bentuk hiasan


def heart(cv, cx, cy, size, fill):
    pts = []
    for i in range(100):
        t = 2 * math.pi * i / 100
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * size / 34, cy + y * size / 34))
    cv.poly(pts, fill)


def star(cv, cx, cy, r, fill, rot=0.0, points=5, inner=0.48):
    pts = []
    for i in range(points * 2):
        ang = rot + math.pi * i / points - math.pi / 2
        rad = r if i % 2 == 0 else r * inner
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    cv.poly(pts, fill)


def sparkle(cv, cx, cy, r, fill):
    star(cv, cx, cy, r, fill, points=4, inner=0.28)


def cloud(cv, x, y, w, fill):
    h = w * 0.5
    cv.circle(x + w * 0.27, y + h * 0.62, h * 0.38, fill)
    cv.circle(x + w * 0.5, y + h * 0.42, h * 0.5, fill)
    cv.circle(x + w * 0.74, y + h * 0.64, h * 0.36, fill)
    cv.rr((x + w * 0.2, y + h * 0.62, x + w * 0.82, y + h * 1.0), h * 0.2, fill)


def sun(cv, cx, cy, r, fill):
    for i in range(12):
        a = 2 * math.pi * i / 12
        cv.poly(
            [
                (cx + math.cos(a - 0.13) * r * 1.2, cy + math.sin(a - 0.13) * r * 1.2),
                (cx + math.cos(a) * r * 1.6, cy + math.sin(a) * r * 1.6),
                (cx + math.cos(a + 0.13) * r * 1.2, cy + math.sin(a + 0.13) * r * 1.2),
            ],
            fill,
        )
    cv.circle(cx, cy, r, fill)


def flower(cv, cx, cy, r, petal, center, n=8):
    for i in range(n):
        a = 2 * math.pi * i / n
        cv.circle(cx + math.cos(a) * r * 0.6, cy + math.sin(a) * r * 0.6, r * 0.42, petal)
    cv.circle(cx, cy, r * 0.62, center)


def confetti(cv, rng, colors, count, y_max=H - 150, avoid=None):
    """Taburkan hiasan kecil. `avoid` = (x0, y0, x1, y1) area yang harus bebas hiasan (mis. teks)."""
    for _ in range(count):
        for _try in range(20):
            x, y = rng.randint(30, W - 30), rng.randint(30, y_max)
            if not avoid or not (avoid[0] <= x <= avoid[2] and avoid[1] <= y <= avoid[3]):
                break
        else:
            continue
        col = rng.choice(colors)
        kind = rng.choice(["dot", "dot", "star", "heart", "sparkle"])
        size = rng.randint(12, 30)
        if kind == "dot":
            cv.circle(x, y, size * 0.45, col)
        elif kind == "star":
            star(cv, x, y, size, col, rot=rng.random())
        elif kind == "heart":
            heart(cv, x, y, size * 1.5, col)
        else:
            sparkle(cv, x, y, size * 1.1, col)


def sticker_card(cv, box, pal, shadow):
    x0, y0, x1, y1 = box
    cv.rr((x0 + 12, y0 + 16, x1 + 12, y1 + 16), 56, shadow)
    cv.rr(box, 56, pal["white"])


def _footer(cv, brand, pal, idx, total, color=None):
    color = color or pal["dark"]
    f = _font("semibold", 30)
    cv.text((MARGIN, H - 95), brand["handle"], f, color)
    label = f"{idx}/{total}"
    cv.text((W - MARGIN - cv.width(label, f), H - 95), label, f, color)


# ------------------------------------------------------------------ slide


def _cover(post, brand, pal, total, rng) -> Image.Image:
    bg = pal["primary"]
    deep = _mix(bg, pal["dark"], 0.18)
    cv = Canvas(bg)

    # latar: matahari, awan, bukit mint
    sun(cv, W - 230, 160, 64, pal["secondary"])
    cloud(cv, 50, 95, 250, _tint(bg, 0.65))
    cloud(cv, 330, 190, 170, _tint(bg, 0.45))
    confetti(cv, rng, [pal["secondary"], pal["white"], pal["sky"], pal["accent"]], 14, y_max=1050)
    cv.circle(W * 0.5, H + 330, 600, pal["accent"])
    cv.circle(W * 0.1, H + 120, 260, _mix(pal["accent"], pal["sky"], 0.4))

    # kartu judul
    inner_w = W - 2 * MARGIN - 110
    hook = clean(post["hook"])
    f, lines, lh = _fit(cv, hook, "bold", inner_w, 430, 80, 42, 1.22)
    sub = clean(post.get("subhook", ""))
    f2, l2, lh2 = (None, [], 0)
    if sub:
        f2, l2, lh2 = _fit(cv, sub, "regular", inner_w, 190, 38, 26, 1.4)
    pad_top, pad_bot = 95, 70
    card_h = pad_top + len(lines) * lh + (28 + len(l2) * lh2 if l2 else 0) + pad_bot
    top = (H - card_h) / 2 - 40
    box = (MARGIN, top, W - MARGIN, top + card_h)
    sticker_card(cv, box, pal, deep)

    y = _draw_lines(cv, lines, f, MARGIN + 55, top + pad_top, lh, pal["dark"], "center", inner_w)
    if l2:
        _draw_lines(cv, l2, f2, MARGIN + 55, y + 28, lh2, _mix(pal["dark"], "#FFFFFF", 0.3), "center", inner_w)

    # stiker di sudut kartu
    label = clean(post.get("pillar", "")).upper() or "TIPS"
    cf = _font("bold", 28)
    cw = cv.width(label, cf) + 60
    cv.rr((MARGIN + 36, top - 31, MARGIN + 36 + cw, top + 31), 31, pal["secondary"])
    cv.text((MARGIN + 66, top - 18), label, cf, pal["dark"])
    heart(cv, W - MARGIN - 20, top + 5, 96, deep)
    star(cv, MARGIN + 10, top + card_h - 5, 38, pal["secondary"], rot=0.3)
    sparkle(cv, W - MARGIN - 40, top + card_h + 40, 30, pal["white"])

    sw = _font("semibold", 36)
    msg = "Geser ya, Bunda  >>"
    cv.text(((W - cv.width(msg, sw)) / 2, top + card_h + 62), msg, sw, pal["dark"])
    _footer(cv, brand, pal, 1, total)
    return cv.finish()


def _content(slide, brand, pal, idx, total, number, rng) -> Image.Image:
    pastel = [
        pal["cream"],
        _tint(pal["accent"], 0.7),
        _tint(pal["secondary"], 0.62),
        _tint(pal["primary"], 0.68),
        _tint(pal["sky"], 0.7),
    ]
    bg = pastel[(number - 1) % len(pastel)]
    shadow = _mix(bg, pal["dark"], 0.16)
    cv = Canvas(bg)

    cloud(cv, W - 300, 55, 230, _tint(bg, 0.6) if bg != pal["cream"] else _tint(pal["sky"], 0.6))
    cloud(cv, 40, H - 270, 180, _tint(pal["primary"], 0.55))
    confetti(cv, rng, [pal["primary"], pal["secondary"], pal["accent"], pal["sky"]], 16)

    inner_w = W - 2 * MARGIN - 120
    head = clean(slide["heading"])
    body = clean(slide["body"])
    f, lines, lh = _fit(cv, head, "bold", inner_w, 250, 68, 40, 1.2)
    f2, l2, lh2 = _fit(cv, body, "regular", inner_w, 480, 46, 28, 1.5)

    pad_top, gap, pad_bot = 115, 26, 70
    card_h = pad_top + len(lines) * lh + gap + len(l2) * lh2 + pad_bot
    top = 150 + (H - 300 - card_h) / 2
    box = (MARGIN, top, W - MARGIN, top + card_h)
    sticker_card(cv, box, pal, shadow)

    y = _draw_lines(cv, lines, f, MARGIN + 60, top + pad_top, lh, pal["dark"])
    _draw_lines(cv, l2, f2, MARGIN + 60, y + gap, lh2, pal["dark"])

    # lencana nomor berbentuk bunga
    petal = [pal["primary"], pal["secondary"], pal["accent"], pal["sky"]][(number - 1) % 4]
    flower(cv, MARGIN + 100, top, 74, petal, pal["white"])
    nf = _font("bold", 58)
    ns = str(number)
    cv.text((MARGIN + 100 - cv.width(ns, nf) / 2, top - 44), ns, nf, pal["dark"])
    star(cv, W - MARGIN - 10, top + card_h - 8, 36, pal["secondary"], rot=0.4)
    heart(cv, W - MARGIN - 62, top - 10, 62, _mix(pal["primary"], pal["dark"], 0.1))

    _footer(cv, brand, pal, idx, total)
    return cv.finish()


def _cta(post, brand, pal, idx, total, rng) -> Image.Image:
    bg = pal["secondary"]
    cv = Canvas(bg)
    cloud(cv, 50, 90, 240, _tint(bg, 0.6))
    cloud(cv, W - 330, 160, 200, _tint(bg, 0.5))
    confetti(cv, rng, [pal["primary"], pal["white"], pal["accent"], pal["sky"]], 18, y_max=1100,
             avoid=(40, 440, W - 40, 960))
    cv.circle(W * 0.5, H + 360, 640, _mix(pal["accent"], "#FFFFFF", 0.15))

    heart(cv, W / 2, 330, 210, _mix(pal["primary"], pal["dark"], 0.05))
    sparkle(cv, W / 2 + 170, 260, 36, pal["white"])
    sparkle(cv, W / 2 - 180, 380, 28, pal["white"])

    inner_w = W - 2 * MARGIN
    text = clean(post.get("cta_text") or "Simpan dulu ya, Bunda")
    f, lines, lh = _fit(cv, text, "bold", inner_w, 330, 76, 42, 1.22)
    y = _draw_lines(cv, lines, f, MARGIN, 500, lh, pal["dark"], "center", inner_w)

    hf = _font("semibold", 40)
    handle = brand["handle"]
    tw = cv.width(handle, hf)
    px0 = (W - tw) / 2 - 42
    cv.rr((px0 + 8, y + 46, px0 + tw + 92, y + 138), 46, _mix(bg, pal["dark"], 0.2))
    cv.rr((px0, y + 38, px0 + tw + 84, y + 130), 46, pal["white"])
    cv.text((px0 + 42, y + 60), handle, hf, pal["dark"])
    _footer(cv, brand, pal, idx, total)
    return cv.finish()


def render_post(post: dict, brand: dict, out_dir: pathlib.Path) -> list[str]:
    """Render semua slide, kembalikan daftar nama file (relatif ke out_dir)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pal = _palette(brand)
    seed = post.get("id", "x")
    content = post["slides"]
    total = len(content) + 2

    images = [_cover(post, brand, pal, total, random.Random(f"{seed}-0"))]
    for i, s in enumerate(content, start=1):
        images.append(_content(s, brand, pal, i + 1, total, i, random.Random(f"{seed}-{i}")))
    images.append(_cta(post, brand, pal, total, total, random.Random(f"{seed}-cta")))

    names = []
    for i, im in enumerate(images, start=1):
        name = f"slide_{i:02d}.png"
        im.save(out_dir / name, optimize=True)
        names.append(name)
    return names
