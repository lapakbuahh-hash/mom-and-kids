"""Render slide carousel (1080x1350, rasio 4:5) dengan Pillow.

Font dicari di assets/fonts (Poppins). Kalau tidak ada, dipakai DejaVu agar tetap jalan.
"""
from __future__ import annotations

import pathlib
import re

from PIL import Image, ImageDraw, ImageFont

from .common import FONT_DIR

W, H = 1080, 1350
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


def _font_path(weight: str) -> str:
    local = FONT_DIR / _NAMES[weight]
    if local.exists():
        return str(local)
    for p in _FALLBACKS[weight]:
        if pathlib.Path(p).exists():
            return p
    raise RuntimeError("Font tidak ditemukan. Jalankan scripts/get_fonts.sh atau taruh Poppins di assets/fonts/.")


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_font_path(weight), size)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", _EMOJI.sub("", text or "")).strip()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text, weight, max_w, max_h, start, minimum, spacing=1.25):
    """Cari ukuran font terbesar agar teks muat di kotak max_w x max_h."""
    size = start
    while size >= minimum:
        f = _font(weight, size)
        lines = _wrap(draw, text, f, max_w)
        line_h = int(size * spacing)
        if len(lines) * line_h <= max_h:
            return f, lines, line_h
        size -= 2
    f = _font(weight, minimum)
    lines = _wrap(draw, text, f, max_w)
    return f, lines, int(minimum * spacing)


def _draw_lines(draw, lines, font, x, y, line_h, fill, align="left", box_w=0):
    for ln in lines:
        lx = x
        if align == "center":
            lx = x + (box_w - draw.textlength(ln, font=font)) / 2
        draw.text((lx, y), ln, font=font, fill=fill)
        y += line_h
    return y


def _blobs(draw, colors, variant: int):
    """Hiasan lingkaran lembut di sudut."""
    c1, c2 = colors
    if variant % 2 == 0:
        draw.ellipse((-160, -160, 300, 300), fill=c1)
        draw.ellipse((W - 260, H - 300, W + 160, H + 120), fill=c2)
    else:
        draw.ellipse((W - 300, -160, W + 160, 300), fill=c1)
        draw.ellipse((-160, H - 300, 260, H + 120), fill=c2)


def _footer(draw, brand, idx, total, color):
    f = _font("semibold", 30)
    draw.text((MARGIN, H - 95), brand["handle"], font=f, fill=color)
    label = f"{idx}/{total}"
    tw = draw.textlength(label, font=f)
    draw.text((W - MARGIN - tw, H - 95), label, font=f, fill=color)


def _chip(draw, text, x, y, bg, fg):
    f = _font("semibold", 28)
    tw = draw.textlength(text, font=f)
    draw.rounded_rectangle((x, y, x + tw + 56, y + 62), radius=31, fill=bg)
    draw.text((x + 28, y + 12), text, font=f, fill=fg)


def _cover(post, brand, total) -> Image.Image:
    c = brand["colors"]
    img = Image.new("RGB", (W, H), c["primary"])
    d = ImageDraw.Draw(img)
    d.ellipse((W - 380, -200, W + 200, 380), fill=c["secondary"])
    d.ellipse((-220, H - 420, 340, H + 140), fill=c["cream"])
    _chip(d, clean(post.get("pillar", "")).upper() or "TIPS", MARGIN, 110, c["white"], c["dark"])

    inner_w = W - 2 * MARGIN - 100
    hook = clean(post["hook"])
    f, lines, lh = _fit(d, hook, "bold", inner_w, 440, 84, 44, 1.2)
    sub = clean(post.get("subhook", ""))
    l2, f2, lh2 = [], None, 0
    if sub:
        f2, l2, lh2 = _fit(d, sub, "regular", inner_w, 200, 40, 28, 1.35)
    pad = 60
    content_h = len(lines) * lh + (30 + len(l2) * lh2 if l2 else 0)
    card_h = content_h + 2 * pad
    card_top = int((H - card_h) / 2) - 20
    card = (MARGIN, card_top, W - MARGIN, card_top + card_h)
    d.rounded_rectangle(card, radius=56, fill=c["white"])
    y = _draw_lines(d, lines, f, card[0] + 50, card[1] + pad, lh, c["dark"])
    if l2:
        _draw_lines(d, l2, f2, card[0] + 50, y + 30, lh2, _tint(c["dark"], 0.25))

    sw = _font("semibold", 34)
    d.text((MARGIN, card[3] + 50), "Geser untuk lihat  >>", font=sw, fill=c["dark"])
    _footer(d, brand, 1, total, c["dark"])
    return img


def _content(slide, brand, idx, total, number) -> Image.Image:
    c = brand["colors"]
    img = Image.new("RGB", (W, H), c["cream"])
    d = ImageDraw.Draw(img)
    _blobs(d, (_tint(c["primary"], 0.55), _tint(c["secondary"], 0.55)), idx)

    inner_w = W - 2 * MARGIN
    head = clean(slide["heading"])
    body = clean(slide["body"])
    f, lines, lh = _fit(d, head, "bold", inner_w, 300, 74, 40, 1.2)
    f2, l2, lh2 = _fit(d, body, "regular", inner_w, 560, 50, 28, 1.45)

    badge = 120
    gap_badge, gap_body = 50, 40
    block_h = badge + gap_badge + len(lines) * lh + gap_body + len(l2) * lh2
    top = max(150, int((H - 160 - block_h) / 2))

    d.ellipse((MARGIN, top, MARGIN + badge, top + badge), fill=c["secondary"])
    nf = _font("bold", 64)
    ns = str(number)
    d.text((MARGIN + (badge - d.textlength(ns, font=nf)) / 2, top + 20), ns, font=nf, fill=c["white"])

    y = _draw_lines(d, lines, f, MARGIN, top + badge + gap_badge, lh, c["dark"])
    _draw_lines(d, l2, f2, MARGIN, y + gap_body, lh2, c["dark"])
    _footer(d, brand, idx, total, c["dark"])
    return img


def _cta(post, brand, idx, total) -> Image.Image:
    c = brand["colors"]
    img = Image.new("RGB", (W, H), c["secondary"])
    d = ImageDraw.Draw(img)
    d.ellipse((-200, -200, 380, 380), fill=_tint(c["white"], 0.0, alpha_mix=(c["secondary"], 0.25)))
    d.ellipse((W - 380, H - 420, W + 200, H + 160), fill=c["primary"])

    inner_w = W - 2 * MARGIN
    text = clean(post.get("cta_text") or "Simpan postingan ini untuk nanti")
    f, lines, lh = _fit(d, text, "bold", inner_w, 480, 82, 44, 1.2)
    total_h = len(lines) * lh
    y0 = (H - total_h) / 2 - 90
    y = _draw_lines(d, lines, f, MARGIN, y0, lh, c["white"], "center", inner_w)

    hf = _font("semibold", 42)
    handle = brand["handle"]
    tw = d.textlength(handle, font=hf)
    px0 = (W - tw) / 2 - 40
    d.rounded_rectangle((px0, y + 50, px0 + tw + 80, y + 140), radius=45, fill=c["white"])
    d.text((px0 + 40, y + 70), handle, font=hf, fill=c["dark"])
    _footer(d, brand, idx, total, c["dark"])
    return img


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _tint(color: str, amount: float, alpha_mix: tuple[str, float] | None = None) -> str:
    """Campur warna dengan putih (amount) atau dengan warna lain (alpha_mix)."""
    r, g, b = _hex(color)
    if alpha_mix:
        base, a = alpha_mix
        br, bg_, bb = _hex(base)
        r, g, b = (int(br + (r - br) * a), int(bg_ + (g - bg_) * a), int(bb + (b - bb) * a))
    else:
        r, g, b = (int(v + (255 - v) * amount) for v in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def render_post(post: dict, brand: dict, out_dir: pathlib.Path) -> list[str]:
    """Render semua slide, kembalikan daftar nama file (relatif ke out_dir)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    content = post["slides"]
    total = len(content) + 2
    images = [_cover(post, brand, total)]
    for i, s in enumerate(content, start=1):
        images.append(_content(s, brand, i + 1, total, i))
    images.append(_cta(post, brand, total, total))

    names = []
    for i, im in enumerate(images, start=1):
        name = f"slide_{i:02d}.png"
        im.save(out_dir / name, optimize=True)
        names.append(name)
    return names
