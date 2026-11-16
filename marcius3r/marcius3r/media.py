"""Utilidades FFmpeg/FFprobe."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def run(cmd: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:6])}... → {p.stderr[-1500:]}")
    return p


def probe(path: str | Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]).stdout
    return json.loads(out)


def ffprobe_duration(path: str | Path) -> float:
    return float(probe(path)["format"]["duration"])


def video_stream(path: str | Path) -> dict | None:
    return next((s for s in probe(path)["streams"] if s["codec_type"] == "video"), None)


def has_audio(path: str | Path) -> bool:
    return any(s["codec_type"] == "audio" for s in probe(path)["streams"])


def freeze_seconds(path: str | Path, noise: str = "-60dB", min_d: float = 0.5) -> float:
    """Segundos totales de imagen congelada. Una foto con zoom lento también se detecta
    con un umbral de ruido alto (ver qc)."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", f"freezedetect=n={noise}:d={min_d}",
                          "-map", "0:v:0", "-f", "null", "-"], capture_output=True, text=True).stderr
    return sum(float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", err))


def black_seconds(path: str | Path) -> float:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", "blackdetect=d=0.2:pix_th=0.08",
                          "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    return sum(float(x) for x in re.findall(r"black_duration:([\d.]+)", err))


def scene_changes(path: str | Path, threshold: float = 0.28) -> int:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
                          f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return len(re.findall(r"pts_time:", err))


def motion_score(path: str | Path) -> float:
    """Diferencia media entre fotogramas (0-255). Vídeo real > ~1.5; foto estática ≈ 0."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
                          "scale=160:-2,tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                          "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    vals = [float(x) for x in re.findall(r"YAVG=([\d.]+)", err)]
    return sum(vals) / len(vals) if vals else 0.0


def loudness(path: str | Path) -> dict:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "loudnorm=print_format=json",
                          "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S)
    return json.loads(m.group(0)) if m else {}


def extract_frame(path: str | Path, t: float, out: str | Path, width: int | None = None) -> Path:
    vf = ["-vf", f"scale={width}:-2"] if width else []
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", *vf, str(out)])
    return Path(out)
