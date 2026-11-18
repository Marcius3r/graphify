"""Resumen profesional de un directo (encargo del propio streamer) con subtítulos en castellano.

Flujo:
1) transcribe(video) → transcript.json (segmentos con tiempos, idioma original) con faster-whisper.
2) El editor (persona o Claude) elige los mejores momentos y traduce → edl.json:
   {"title": "...", "streamer": "Nombre", "language": "es-ES",
    "intro_hook": {"start": 3612.0, "end": 3618.5, "text": "¡NO TE LO VAS A CREER!"},   # teaser 0-6 s
    "segments": [{"start": 120.0, "end": 185.0, "chapter": "El primer atraco",
                  "subs": [{"start": 121.2, "end": 124.0, "text": "Tío, mira esto…"}, ...]}, ...]}
   Tiempos de subs en segundos del vídeo ORIGINAL (se recalculan solos).
   Para un resumen CON SENTIDO y TODO traducido (recomendado):
   - "transcript": "transcript.json"      → los cortes se ajustan a frases completas (nunca a mitad de frase).
   - "transcript_es": "transcript_es.json" → misma estructura y tiempos, con el texto traducido al castellano;
                                              se subtitula TODO lo que se oye en el resumen (no hace falta "subs").
   - "bridge" en cada segmento: rótulo de contexto («Tras media hora intentando escapar…») que explica lo
                                 que pasó en la parte que se salta, para que la historia se entienda.
   - "silence_cut": segundos mínimos de silencio que se recortan (por defecto 2.5; 0 = no recortar).
3) render(video, edl) → resumen 16:9 (1920x1080) y, con vertical=True, versión 9:16 para Shorts:
   - teaser inicial del mejor momento, rótulo de capítulo en cada bloque, cortes de silencios largos,
     punch-in alterno (zoom 1.0/1.12) para dinamismo, subtítulos en castellano grandes, crédito al streamer,
     transición con destello, música de fondo opcional con ducking y −14 LUFS.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .core import ROOT
from .media import ffprobe_duration, run
from .subtitles import _ass_color, _t, fonts_dir


def transcribe(video: Path, out: Path, model: str = "medium", language: str | None = None) -> Path:
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device="auto", compute_type="auto")
    segs, info = m.transcribe(str(video), language=language, vad_filter=True, word_timestamps=False)
    data = {"language": info.language, "duration": info.duration,
            "segments": [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs]}
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _load(path: str | None, base: Path) -> dict | None:
    if not path:
        return None
    p = Path(path) if Path(path).is_absolute() else base / path
    return json.loads(p.read_text(encoding="utf-8"))


def snap_to_sentences(start: float, end: float, transcript: dict | None) -> tuple[float, float]:
    """Amplía [start,end] a frases completas de la transcripción (nunca corta a mitad de frase)."""
    if not transcript:
        return start, end
    for s in transcript["segments"]:
        if s["start"] <= start < s["end"]:
            start = s["start"]
        if s["start"] < end <= s["end"]:
            end = s["end"]
    return max(0.0, start - 0.15), end + 0.25


def subtitle_coverage(pieces: list[tuple[float, float]], transcript: dict | None, subs: list[dict]) -> float:
    """% del habla incluida en el resumen que tiene subtítulo en castellano."""
    if not transcript:
        return 1.0
    spoken = covered = 0.0
    for a, b in pieces:
        for s in transcript["segments"]:
            x, y = max(a, s["start"]), min(b, s["end"])
            if y - x <= 0.1:
                continue
            spoken += y - x
            covered += sum(max(0.0, min(y, t["end"]) - max(x, t["start"])) for t in subs)
    return min(1.0, covered / spoken) if spoken else 1.0


def _speech_islands(video: Path, start: float, end: float, min_sil: float = 2.5) -> list[tuple[float, float]]:
    """Partes con sonido dentro de [start,end], quitando silencios > min_sil (jump cuts)."""
    p = run(["ffmpeg", "-hide_banner", "-ss", f"{start:.2f}", "-t", f"{end-start:.2f}", "-i", str(video), "-vn",
             "-af", f"silencedetect=noise=-38dB:d={min_sil}", "-f", "null", "-"])
    err = p.stderr
    sil_s = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    sil_e = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    if min_sil <= 0:
        return [(start, end)]
    keep, cur = [], 0.0
    for s, e in zip(sil_s, sil_e + [end - start] * (len(sil_s) - len(sil_e))):
        if s - cur > 0.3:
            keep.append((start + cur, start + s + 0.35))
        cur = max(cur, e - 0.35)
    if (end - start) - cur > 0.3:
        keep.append((start + cur, end))
    return keep or [(start, end)]


def _style(W: int, H: int, settings: dict, vertical: bool) -> list[str]:
    c = settings["brand"]["colors"]
    size = 78 if vertical else 58
    return ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Sub,Montserrat ExtraBold,{size},{_ass_color(c['white'])},{_ass_color(c['white'])},{_ass_color(c['black'])},"
            f"{_ass_color(c['black'], 0x70)},-1,0,0,0,100,100,0,0,1,6,2,2,80,80,{int(H*0.08) if not vertical else int(H*0.24)},1",
            f"Style: Chapter,Montserrat Black,{96 if vertical else 84},{_ass_color(c['white'])},{_ass_color(c['white'])},{_ass_color(c['neon_purple'])},"
            f"{_ass_color(c['black'], 0x40)},-1,0,0,0,100,100,2,0,1,8,0,5,60,60,0,1",
            f"Style: Bridge,Montserrat Bold,{46 if vertical else 40},{_ass_color(c['white'])},{_ass_color(c['white'])},{_ass_color(c['neon_purple'], 0x20)},"
            f"{_ass_color(c['neon_purple'], 0x30)},-1,0,0,0,100,100,0,0,3,14,0,8,90,90,{int(H*0.30) if vertical else int(H*0.62)},1",
            f"Style: Credit,Montserrat Bold,{34 if vertical else 30},{_ass_color(c['white'])},{_ass_color(c['white'])},{_ass_color(c['black'])},"
            f"{_ass_color(c['black'], 0x60)},-1,0,0,0,100,100,1,0,3,2,0,7,40,40,40,1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]


def render(video: Path, edl: dict, workdir: Path, settings: dict, vertical: bool = False,
           music: Path | None = None, base: Path | None = None) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    base = base or workdir.parent
    transcript = _load(edl.get("transcript"), base)
    transcript_es = _load(edl.get("transcript_es"), base)
    min_sil = float(edl.get("silence_cut", 2.5))
    W, H = (1080, 1920) if vertical else (1920, 1080)
    fps = 30
    blue = _ass_color(settings["brand"]["colors"]["electric_blue"])
    # 1) lista de piezas (teaser + segmentos con jump cuts)
    pieces = []  # (src_start, src_end, chapter|None, is_teaser, bridge|None)
    if edl.get("intro_hook"):
        h = edl["intro_hook"]
        a, b = snap_to_sentences(h["start"], h["end"], transcript)
        pieces.append((a, b, None, True, None))
    for seg in edl["segments"]:
        s0, s1 = snap_to_sentences(seg["start"], seg["end"], transcript)
        for k, (a, b) in enumerate(_speech_islands(video, s0, s1, min_sil)):
            pieces.append((a, b, seg["chapter"] if k == 0 else None, False, seg.get("bridge") if k == 0 else None))
    # 2) render de cada pieza normalizada
    if vertical:  # vídeo horizontal centrado sobre fondo desenfocado
        base = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:3,"
                f"eq=brightness=-0.15[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2-120")
    else:
        base = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"
    listing, timeline, t = [], [], 0.0
    for i, (a, b, chapter, teaser, bridge) in enumerate(pieces):
        d = b - a
        zoom = 1.12 if i % 2 else 1.0
        z = f",scale=iw*{zoom}:ih*{zoom},crop={W}:{H}" if zoom != 1.0 else ""
        out = workdir / f"p_{i:04d}.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-i", str(video), "-t", f"{d:.3f}",
             "-filter_complex", f"[0:v]{base}{z},fps={fps},format=yuv420p[v];[0:a]aresample=48000,"
             f"afade=t=in:d=0.03,afade=t=out:st={max(0, d-0.05):.3f}:d=0.05[a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
             "-c:a", "aac", "-b:a", "192k", "-ac", "2", str(out)])
        listing.append(f"file '{out.as_posix()}'")
        timeline.append({"src_start": a, "src_end": b, "start": t, "end": t + d, "chapter": chapter,
                         "teaser": teaser, "bridge": bridge})
        t += d
    (workdir / "list.txt").write_text("\n".join(listing) + "\n")
    joined = workdir / "joined.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(workdir / "list.txt"),
         "-c", "copy", str(joined)])
    total = ffprobe_duration(joined)
    # 3) subtítulos castellano remapeados + rótulos + crédito
    lines = _style(W, H, settings, vertical)
    if transcript_es:  # TODO traducido: toda la transcripción en castellano
        all_subs = [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in transcript_es["segments"]]
    else:
        all_subs = [s for seg in edl["segments"] for s in seg.get("subs", [])]
        if edl.get("intro_hook"):
            all_subs += edl["intro_hook"].get("subs", [])
    cov = subtitle_coverage([(p["src_start"], p["src_end"]) for p in timeline], transcript, all_subs)
    (workdir / "cobertura_subtitulos.txt").write_text(f"{cov:.1%} del habla del resumen subtitulada\n")
    for p in timeline:
        for s in all_subs:
            a, b = max(s["start"], p["src_start"]), min(s["end"], p["src_end"])
            if b - a > 0.15:
                st, en = p["start"] + (a - p["src_start"]), p["start"] + (b - p["src_start"])
                lines.append(f"Dialogue: 1,{_t(st)},{_t(en)},Sub,,0,0,0,,{s['text']}")
        if p["bridge"]:  # rótulo de contexto: explica lo que pasó en la parte saltada
            lines.append(f"Dialogue: 2,{_t(p['start'] + 0.1)},{_t(min(p['start'] + 3.4, p['end']))},Bridge,,0,0,0,,"
                         r"{\fad(150,250)}" + p["bridge"])
        if p["chapter"]:
            lines.append(f"Dialogue: 2,{_t(p['start'])},{_t(min(p['start']+2.2, p['end']))},Chapter,,0,0,0,,"
                         r"{\fad(120,200)\3c" + blue + "&}" + p["chapter"].upper())
        if p["teaser"] and edl["intro_hook"].get("text"):
            lines.append(f"Dialogue: 2,{_t(p['start'])},{_t(p['end'])},Chapter,,0,0,0,,{edl['intro_hook']['text'].upper()}")
    credit = f"Directo de {edl.get('streamer', '')} · Resumen y subtítulos: MARCIUS3R"
    lines.append(f"Dialogue: 3,{_t(0)},{_t(total)},Credit,,0,0,0,,{credit}")
    ass = workdir / "recap.ass"
    ass.write_text("\n".join(lines) + "\n", encoding="utf-8")
    flashes = [p["start"] for p in timeline if p["chapter"] and p["start"] > 0]
    fx = ",".join(f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.35:t=fill:enable='between(t,{x:.2f},{x+0.06:.2f})'"
                  for x in flashes)
    vf = (fx + "," if fx else "") + f"ass={ass.as_posix()}:fontsdir={fonts_dir().as_posix()}"
    lufs = settings["qc"]["target_lufs"]
    out = workdir / ("resumen_vertical.mp4" if vertical else "resumen_16x9.mp4")
    if music and music.exists():
        af = (f"[1:a]volume=0.18,aloop=loop=-1:size=2e9,atrim=0:{total:.2f}[m];[0:a]asplit[v][k];"
              f"[m][k]sidechaincompress=threshold=0.04:ratio=8[md];[v][md]amix=inputs=2:normalize=0:duration=first,"
              f"loudnorm=I={lufs}:TP=-1.5[a]")
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-i", str(music), "-filter_complex",
             f"[0:v]{vf}[v];{af}", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    else:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-vf", vf, "-af", f"loudnorm=I={lufs}:TP=-1.5",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out)])
    chapters = [(p["start"], p["chapter"]) for p in timeline if p["chapter"]]
    (workdir / "capitulos.txt").write_text(
        "\n".join(f"{int(s//60):02d}:{int(s%60):02d} {c}" for s, c in [(0.0, "Intro")] + chapters if True) + "\n",
        encoding="utf-8")
    return out
