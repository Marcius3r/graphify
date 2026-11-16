"""PASO 9: miniatura 1280x720 (y portada vertical 1080x1920) con identidad MARCIUS3R.

Elemento principal = el fotograma más nítido/impactante de las escenas, etalonado; texto
breve enorme con contorno y brillo neón; etiqueta 'RECREACIÓN IA' si procede.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat

from .core import ROOT
from .media import extract_frame


def _font(size: int, weight: str = "Black") -> ImageFont.FreeTypeFont:
    p = ROOT / "assets" / "fonts" / f"Montserrat-{weight}.ttf"
    try:
        return ImageFont.truetype(str(p), size)
    except OSError:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def best_frame(clips: list[str], workdir: Path, n_per_clip: int = 3) -> Path:
    """Elige el fotograma con más contraste + nitidez."""
    best, best_s = None, -1
    for ci, clip in enumerate(clips[:8]):
        for k in range(n_per_clip):
            p = workdir / f"cand_{ci}_{k}.png"
            try:
                extract_frame(clip, 0.6 + k * 1.3, p, width=1280)
            except RuntimeError:
                continue
            im = Image.open(p).convert("L")
            sharp = ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES)).mean[0]
            contrast = ImageStat.Stat(im).stddev[0]
            s = sharp * 1.5 + contrast
            if s > best_s:
                best, best_s = p, s
    if best is None:
        raise RuntimeError("no se pudo extraer ningún fotograma")
    return best


def _cover(im: Image.Image, w: int, h: int) -> Image.Image:
    r = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * r) + 1, int(im.height * r) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _wrap(text: str, font, max_w: int, draw) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_thumbnail(frame: Path, text: str, out: Path, settings: dict, synthetic: bool,
                   size: tuple[int, int] = (1280, 720)) -> Path:
    c = settings["brand"]["colors"]
    W, H = size
    base = _cover(Image.open(frame).convert("RGB"), W, H)
    base = ImageEnhance.Contrast(base).enhance(1.25)
    base = ImageEnhance.Color(base).enhance(1.3)
    # degradado lateral negro→transparente para el texto + tinte morado/azul
    grad = Image.new("RGBA", (W, H))
    gd = ImageDraw.Draw(grad)
    for x in range(W):
        a = int(235 * max(0, 1 - x / (W * 0.62)))
        gd.line([(x, 0), (x, H)], fill=(*_hex(c["black"]), a))
    tint = Image.new("RGBA", (W, H), (*_hex(c["neon_purple"]), 38))
    img = Image.alpha_composite(base.convert("RGBA"), tint)
    img = Image.alpha_composite(img, grad)
    draw = ImageDraw.Draw(img)
    # texto grande, máx 3 líneas
    text = text.upper().strip()
    size_px = 150 if W > H else 130
    font = _font(size_px)
    lines = _wrap(text, font, int(W * 0.62), draw)
    while len(lines) > 3 and size_px > 70:
        size_px -= 10
        font = _font(size_px)
        lines = _wrap(text, font, int(W * 0.62), draw)
    lh = int(size_px * 1.02)
    y0 = (H - lh * len(lines)) // 2 if W > H else int(H * 0.12)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for i, line in enumerate(lines):
        gdraw.text((48, y0 + i * lh), line, font=font, fill=(*_hex(c["neon_purple"]), 255))
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        fill = _hex(c["white"]) if i != len(lines) - 1 else _hex(c["electric_blue"])
        draw.text((48, y0 + i * lh), line, font=font, fill=fill, stroke_width=10, stroke_fill=_hex(c["black"]))
    # barra de marca
    draw.rectangle([0, H - 12, W, H], fill=_hex(c["neon_purple"]))
    draw.rectangle([0, H - 12, int(W * 0.35), H], fill=_hex(c["electric_blue"]))
    brand = _font(34, "ExtraBold")
    draw.text((W - 48 - draw.textlength("MARCIUS3R", font=brand), 28), "MARCIUS3R", font=brand,
              fill=_hex(c["white"]), stroke_width=4, stroke_fill=_hex(c["black"]))
    if synthetic:
        tag = _font(26, "Bold")
        label = "RECREACIÓN IA"
        tw = draw.textlength(label, font=tag)
        draw.rounded_rectangle([40, 28, 40 + tw + 28, 28 + 44], radius=8, fill=_hex(c["neon_purple"]))
        draw.text((54, 34), label, font=tag, fill=_hex(c["white"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    if out.stat().st_size > 2_000_000:  # límite de YouTube: 2 MB
        img.convert("RGB").save(out, "JPEG", quality=80, optimize=True)
    return out
