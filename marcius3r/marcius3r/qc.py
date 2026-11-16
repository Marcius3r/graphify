"""PASO 8: control de calidad. Si hay un solo 'blocker', el vídeo NO se publica."""
from __future__ import annotations

import re
from pathlib import Path

from .core import db
from .media import black_seconds, freeze_seconds, loudness, probe, scene_changes
from .research import similarity
from .script_writer import full_narration, validate_script

ALLOWED_CHARS = re.compile(r"^[\wáéíóúüñÁÉÍÓÚÜÑ¿¡?!.,;:'\"()«»\-–—%/&@#+| ]+$")


def wer(ref: str, hyp: str) -> float:
    r = re.findall(r"\w+", ref.lower())
    h = re.findall(r"\w+", hyp.lower())
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / max(1, len(r))


def transcribe(path: Path) -> str | None:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(path), language="es")
    return " ".join(s.text for s in segs)


def run_qc(video_path: Path, script: dict, render_info: dict, fmt: str, settings: dict,
           metadata: dict | None = None, video_id: int | None = None) -> dict:
    q = settings["qc"]
    f = settings["formats"][fmt]
    blockers, warnings, m = [], [], {}
    info = probe(video_path)
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    dur = float(info["format"]["duration"])
    m.update(width=vs["width"], height=vs["height"], duration=round(dur, 2))
    if (vs["width"], vs["height"]) != (f["width"], f["height"]):
        blockers.append(f"resolución {vs['width']}x{vs['height']} ≠ {f['width']}x{f['height']}")
    if not (f["min_seconds"] <= dur <= f["max_seconds"]):
        blockers.append(f"duración {dur:.1f}s fuera de [{f['min_seconds']}, {f['max_seconds']}]")
    if not any(s["codec_type"] == "audio" for s in info["streams"]):
        blockers.append("sin audio")
    # imagen: fotos/congelados, negros, cambios de plano
    frz = freeze_seconds(video_path, noise="-55dB", min_d=0.8)
    m["freeze_ratio"] = round(frz / dur, 3)
    if m["freeze_ratio"] > q["max_freeze_ratio"]:
        blockers.append(f"{m['freeze_ratio']:.0%} del vídeo con imagen congelada (posible foto/estático)")
    blk = black_seconds(video_path)
    m["black_seconds"] = round(blk, 2)
    if blk > q["max_black_seconds"]:
        blockers.append(f"{blk:.1f}s de negro")
    cuts = render_info.get("cuts", 0)
    m["cuts_per_10s"] = round(cuts / dur * 10, 2)
    m["detected_scene_changes"] = scene_changes(video_path)
    if m["cuts_per_10s"] < q["min_scene_changes_per_10s"]:
        warnings.append(f"ritmo lento: {m['cuts_per_10s']} planos/10s")
    low_motion = [c for c in render_info.get("timeline", []) if c.get("motion", 9) < 0.6]
    if low_motion:
        blockers.append(f"{len(low_motion)} planos sin movimiento suficiente")
    # origen de las escenas
    labels = render_info.get("labels", [])
    if any("PRUEBA" in l for l in labels):
        blockers.append("contiene escenas de PRUEBA (test_motion): prohibido publicar")
    m["synthetic"] = any("IA" in l for l in labels)
    # audio
    ld = loudness(video_path)
    if ld:
        m["lufs"] = float(ld["input_i"])
        m["true_peak"] = float(ld["input_tp"])
        if abs(m["lufs"] - q["target_lufs"]) > q["lufs_tolerance"]:
            blockers.append(f"sonoridad {m['lufs']:.1f} LUFS (objetivo {q['target_lufs']})")
        if m["true_peak"] > -0.5:
            warnings.append(f"pico {m['true_peak']} dBTP")
    a = render_info.get("audio", {})
    if a.get("music_synth"):
        warnings.append("música de respaldo sintética: añade música con licencia o generada")
    elif not a.get("music_licensed"):
        blockers.append("música sin licencia documentada (library/music/licenses.yaml)")
    # texto / guion
    problems = validate_script(script, fmt, settings)
    blockers += [f"guion: {p}" for p in problems]
    text = full_narration(script)
    for b in script["beats"]:
        if not ALLOWED_CHARS.match(b["narration"].replace("\n", " ")):
            warnings.append(f"caracteres raros en: {b['narration'][:50]}")
        if "  " in b["narration"] or re.search(r"\b(\w+) \1\b", b["narration"], re.I):
            warnings.append(f"posible errata/duplicado: {b['narration'][:50]}")
    hyp = transcribe(video_path)
    if hyp is not None:
        m["wer"] = round(wer(text, hyp), 3)
        if m["wer"] > q["max_wer"]:
            blockers.append(f"la voz no coincide con el guion (WER {m['wer']:.0%}): posible pronunciación/sincronía mala")
    else:
        warnings.append("WER no medido (instala faster-whisper para verificar pronunciación)")
    # duplicados
    with db() as con:
        prev = [r["title"] for r in con.execute(
            "SELECT title FROM videos WHERE status IN ('published','scheduled','approved') AND id != ?", (video_id or -1,))]
    dup = max((similarity(script["title"], t) for t in prev), default=0)
    m["max_title_similarity"] = round(dup, 2)
    if dup > 0.6:
        blockers.append("tema demasiado parecido a un vídeo ya publicado")
    # metadatos
    if metadata:
        if len(metadata["title"]) > 100:
            blockers.append("título > 100 caracteres")
        if len(metadata["description"]) > 4900:
            blockers.append("descripción demasiado larga")
        if sum(len(t) for t in metadata["tags"]) > 480:
            blockers.append("etiquetas > 500 caracteres")
        if m.get("synthetic") and "recreación" not in metadata["description"].lower():
            blockers.append("falta aviso de recreación IA en la descripción")
    return {"passed": not blockers, "blockers": blockers, "warnings": warnings, "metrics": m}
