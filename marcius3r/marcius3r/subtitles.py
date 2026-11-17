"""Subtítulos ASS: palabra a palabra con resaltado neón, textos de impacto, etiqueta de origen
(RECREACIÓN IA / GAMEPLAY), marca de agua y barra de progreso (Shorts).

Tiempos: cada beat tiene su duración exacta (voz sintetizada por frase). Dentro del beat
las palabras se reparten por longitud silábica aproximada; si hay faster-whisper instalado
se refinan con marcas de tiempo reales por palabra.
"""
from __future__ import annotations

import re
from pathlib import Path

from .core import ROOT


def _ass_color(hex_rgb: str, alpha: int = 0) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _t(sec: float) -> str:
    sec = max(0.0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _weight(word: str) -> float:
    vowels = len(re.findall(r"[aeiouáéíóúü]", word.lower()))
    return max(1.0, vowels) + (0.6 if re.search(r"[,.;:!?…]$", word) else 0)


def word_timings(text: str, start: float, dur: float) -> list[tuple[str, float, float]]:
    words = text.split()
    if not words:
        return []
    ws = [_weight(w) for w in words]
    total = sum(ws)
    t, out = start, []
    for w, wt in zip(words, ws):
        d = dur * wt / total
        out.append((w, t, t + d))
        t += d
    return out


def refine_with_whisper(audio: Path, words: list[tuple[str, float, float]], offset: float) -> list[tuple[str, float, float]]:
    try:
        from faster_whisper import WhisperModel  # opcional
    except ImportError:
        return words
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(audio), language="es", word_timestamps=True)
    stamps = [(w.start + offset, w.end + offset) for s in segs for w in (s.words or [])]
    if len(stamps) != len(words):
        return words  # desalineado: mantenemos la estimación
    return [(w, a, b) for (w, _, _), (a, b) in zip(words, stamps)]


def build_ass(script: dict, timeline: list[dict], fmt: str, settings: dict, out: Path,
              total: float) -> Path:
    f = settings["formats"][fmt]
    W, H = f["width"], f["height"]
    c = settings["brand"]["colors"]
    short = fmt == "short"
    font = "Montserrat ExtraBold"
    sub_size = 84 if short else 64
    sub_y = int(H * (0.66 if short else 0.86))
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Sub,{font},{sub_size},{_ass_color(c['white'])},{_ass_color(c['neon_purple'])},{_ass_color(c['black'])},"
        f"{_ass_color(c['black'], 0x60)},-1,0,0,0,100,100,1,0,1,{7 if short else 5},3,5,60,60,0,1",
        f"Style: Punch,{font},{118 if short else 96},{_ass_color(c['white'])},{_ass_color(c['white'])},{_ass_color(c['neon_purple'])},"
        f"{_ass_color(c['black'], 0x40)},-1,0,0,0,100,100,2,0,1,9,0,5,60,60,0,1",
        f"Style: Label,Montserrat Bold,{34 if short else 28},{_ass_color(c['white'])},{_ass_color(c['white'])},{_ass_color(c['black'])},"
        f"{_ass_color(c['black'], 0x50)},-1,0,0,0,100,100,2,0,3,2,0,7,40,40,{150 if short else 40},1",
        f"Style: Mark,Montserrat Bold,{30 if short else 26},{_ass_color(c['white'], 0x55)},{_ass_color(c['white'])},{_ass_color(c['black'], 0x80)},"
        f"{_ass_color(c['black'], 0xFF)},-1,0,0,0,100,100,3,0,1,1,0,9,40,40,{150 if short else 40},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    hl = _ass_color(c["neon_purple"])
    blue = _ass_color(c["electric_blue"])
    # subtítulos palabra a palabra en grupos de 2-4 palabras
    for seg in timeline:
        if seg.get("words") is None:
            continue
        words = seg["words"]
        groups, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) >= (3 if short else 6) or re.search(r"[,.;:!?…]$", w[0]):
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        for g in groups:
            g_start, g_end = g[0][1], g[-1][2]
            for j, (w, ws, we) in enumerate(g):
                parts = []
                for k, (w2, _, _) in enumerate(g):
                    txt = w2.upper() if short else w2
                    if k == j:
                        parts.append(r"{\c" + hl + r"&\fscx108\fscy108}" + txt + r"{\c" + _ass_color(c['white']) + r"&\fscx100\fscy100}")
                    else:
                        parts.append(txt)
                pop = r"{\an5\pos(" + f"{W//2},{sub_y}" + r")" + (r"\fad(40,0)" if j == 0 else "") + "}"
                lines.append(f"Dialogue: 1,{_t(ws)},{_t(we if j < len(g)-1 else g_end)},Sub,,0,0,0,,{pop}{' '.join(parts)}")
    # textos de impacto al inicio de cada beat
    for seg in timeline:
        ov = (seg.get("overlay_text") or "").strip()
        if not ov or seg.get("part", 0) != 0:
            continue
        y = int(H * (0.24 if short else 0.18))
        anim = (r"{\an5\pos(" + f"{W//2},{y}" + r")\fscx40\fscy40\t(0,140,\fscx112\fscy112)\t(140,240,\fscx100\fscy100)\fad(0,180)\bord9\3c"
                + blue + "&}")
        lines.append(f"Dialogue: 2,{_t(seg['start'])},{_t(min(seg['start'] + 1.6, seg['end']))},Punch,,0,0,0,,{anim}{ov.upper()}")
    # etiqueta de origen (siempre visible) y marca
    for seg in timeline:
        lab = seg.get("label")
        if lab:
            color = (c["neon_purple"] if "RECREACIÓN IA" in lab else "#FF3030" if "PRUEBA" in lab else c["electric_blue"])
            lines.append(f"Dialogue: 3,{_t(seg['start'])},{_t(seg['end'])},Label,,0,0,0,,"
                         r"{\3c" + _ass_color(color) + "&}" + f" {lab} ")
    lines.append(f"Dialogue: 3,{_t(0)},{_t(total)},Mark,,0,0,0,,MARCIUS3R")
    if short:  # barra de progreso inferior (retención)
        bar_y = H - 14
        lines.append(f"Dialogue: 4,{_t(0)},{_t(total)},Label,,0,0,0,,"
                     r"{\an7\pos(0," + str(bar_y) + r")\bord0\shad0\1c" + hl + r"&\p1\clip(0,0,0," + str(H) + r")\t(0,"
                     + str(int(total * 1000)) + r",\clip(0,0," + str(W) + "," + str(H) + r"))}m 0 0 l " + f"{W} 0 {W} 14 0 14" + r"{\p0}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def fonts_dir() -> Path:
    return ROOT / "assets" / "fonts"
