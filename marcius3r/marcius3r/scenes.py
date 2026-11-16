"""PASO 6: escenas de vídeo con movimiento real, una por frase del guion.

Fuentes (por orden en settings.providers.video.order):
- gameplay_library  → tus capturas legítimas de GTA 6 (etiquetadas). Marca "GAMEPLAY".
- muapi             → API de MuAPI (backend de Open-Generative-AI): Seedance/Kling/Wan. Marca "RECREACIÓN IA".
- higgsfield_agent  → clips generados por el agente Claude con Higgsfield (MCP) y depositados en
                      workdir/clips/beat_XX.mp4 a partir de workdir/generation_manifest.json.
- test_motion       → SOLO PRUEBAS: vídeo procedural con FFmpeg para validar el montaje.
                      Un vídeo con escenas test_motion NUNCA puede publicarse (QC lo bloquea).

Nunca se usan fotografías: el QC mide movimiento por escena y rechaza imágenes estáticas.
"""
from __future__ import annotations

import json
import math
import random
import re
import time
from pathlib import Path

import requests
import yaml

from .core import ROOT, StepError, add_cost, load_secrets, log_event
from .media import ffprobe_duration, motion_score, run, video_stream

LABEL = {"gameplay_library": "GAMEPLAY", "muapi": "RECREACIÓN IA", "higgsfield_agent": "RECREACIÓN IA",
         "test_motion": "PRUEBA — NO PUBLICAR"}

STYLE_SUFFIX = ("cinematic, photorealistic, dynamic camera movement, natural motion, people and cars moving, "
                "humid tropical air, neon reflections, film grain, shallow depth of field, no text, no logos")


def plan_shots(script: dict, voice: list[dict], fmt: str, settings: dict) -> list[dict]:
    """Una toma por beat (dos si la frase es larga). Devuelve la lista de tomas a generar."""
    clip_len = settings["formats"][fmt]["clip_seconds"]
    aspect = "9:16" if fmt == "short" else "16:9"
    shots = []
    for i, (beat, v) in enumerate(zip(script["beats"], voice)):
        need = v["duration"] + v["pause"]
        n = max(1, math.ceil(need / (clip_len * 0.95)))
        for k in range(n):
            prompt = beat["scene_prompt"] if k == 0 else f"{beat['scene_prompt']} Different angle, closer shot."
            shots.append({"beat": i, "part": k, "seconds": clip_len, "aspect_ratio": aspect,
                          "prompt": f"{prompt} Camera: {beat['camera']}. {STYLE_SUFFIX}",
                          "file": f"clips/beat_{i:02d}_{k}.mp4"})
    return shots


def write_manifest(shots: list[dict], workdir: Path, settings: dict) -> Path:
    hcfg = settings["providers"]["video"]["higgsfield"]
    manifest = {"provider": "higgsfield", "model": hcfg["model"], "resolution": hcfg["resolution"],
                "instructions": "Genera cada toma (texto→vídeo, sin audio) y guarda el mp4 en workdir/<file>.",
                "shots": shots}
    p = workdir / "generation_manifest.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return p


# ---------------------------------------------------------------- proveedores
def _gameplay(shot: dict, beat: dict, settings: dict, used: set[str]) -> Path | None:
    lib = ROOT / settings["providers"]["video"]["gameplay_library"]["path"]
    idx = lib / "index.yaml"
    if not idx.exists():
        return None
    entries = yaml.safe_load(idx.read_text()) or []
    words = set(re.findall(r"[a-z]+", (beat["scene_prompt"] + " " + beat["narration"]).lower()))
    best, best_s = None, 0
    for e in entries:
        if e["file"] in used:
            continue
        s = len(words & {t.lower() for t in e.get("tags", [])})
        if s > best_s:
            best, best_s = e, s
    if not best or best_s < 2:
        return None
    used.add(best["file"])
    return lib / best["file"]


def _muapi(shot: dict, out: Path, settings: dict, secrets: dict, video_id: int | None) -> Path:
    cfg = settings["providers"]["video"]["muapi"]
    key = secrets.get("MUAPI_API_KEY")
    if not key:
        raise StepError("MUAPI_API_KEY no configurada")
    base = cfg["base_url"].rstrip("/")
    hdr = {"Content-Type": "application/json", "x-api-key": key}
    r = requests.post(f"{base}/api/v1/{cfg['endpoint']}", headers=hdr, timeout=60,
                      json={"prompt": shot["prompt"], "aspect_ratio": shot["aspect_ratio"],
                            "duration": shot["seconds"], "resolution": cfg.get("resolution", "720p")})
    if r.status_code >= 300:
        raise StepError(f"MuAPI {r.status_code}: {r.text[:300]}")
    rid = r.json().get("request_id") or r.json().get("id")
    for _ in range(180):
        time.sleep(5)
        p = requests.get(f"{base}/api/v1/predictions/{rid}/result", headers=hdr, timeout=30)
        if p.status_code != 200:
            continue
        res = p.json()
        st = str(res.get("status", "")).lower()
        if st in ("completed", "succeeded", "success"):
            url = (res.get("outputs") or [None])[0] or res.get("url") or (res.get("output") or {}).get("url")
            out.write_bytes(requests.get(url, timeout=300).content)
            add_cost(video_id, "muapi", shot["file"], usd=float(res.get("cost", 0) or 0))
            return out
        if st in ("failed", "error"):
            raise StepError(f"MuAPI falló: {res.get('error')}")
    raise StepError("MuAPI: tiempo de espera agotado")


def _test_motion(shot: dict, out: Path, settings: dict, fmt: str) -> Path:
    """Vídeo procedural en movimiento (fractal animado + 'tráfico' de luces). Solo pruebas."""
    f = settings["formats"][fmt]
    w, h, fps, d = f["width"], f["height"], f["fps"], shot["seconds"]
    seed = random.Random(shot["prompt"]).randint(0, 9999)
    c1, c2 = random.Random(seed).choice([("0x1a0033", "0x00b3ff"), ("0x05040a", "0xb026ff"), ("0x001a33", "0xff2bd6")])
    run(["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c={c1}:s={w}x{h}:d={d}:r={fps}",
         "-f", "lavfi", "-i", f"mandelbrot=s=360x360:r={fps}:start_scale={2.0 + seed % 7 / 10}:end_scale=0.3",
         "-filter_complex",
         f"[1:v]hue=h=t*40,scale={w}:{w}[m];[0:v][m]overlay=y=(H-h)/2+60*sin(t*2):shortest=1,"
         f"drawbox=x='mod(t*{w//2}+{seed},{w})':y=ih*0.72:w=180:h=8:color={c2}@0.9:t=fill,"
         f"drawbox=x='{w}-mod(t*{w//3}+{seed},{w})':y=ih*0.78:w=120:h=6:color=white@0.8:t=fill",
         "-t", str(d), "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)])
    return out


def gather_clips(script: dict, shots: list[dict], workdir: Path, fmt: str, settings: dict,
                 video_id: int | None = None, allow_test: bool = False) -> list[dict]:
    """Consigue un clip por toma. Devuelve las tomas con 'path' y 'label'."""
    secrets = load_secrets()
    (workdir / "clips").mkdir(parents=True, exist_ok=True)
    order = list(settings["providers"]["video"]["order"]) + (["test_motion"] if allow_test else [])
    used: set[str] = set()
    out = []
    for shot in shots:
        dest = workdir / shot["file"]
        beat = script["beats"][shot["beat"]]
        got, label, errors = None, None, []
        if dest.exists() and dest.stat().st_size > 10_000:  # depositado por el agente (Higgsfield)
            got, label = dest, LABEL["higgsfield_agent"]
        for prov in order:
            if got:
                break
            try:
                if prov == "gameplay_library":
                    got = _gameplay(shot, beat, settings, used)
                elif prov == "muapi":
                    got = _muapi(shot, dest, settings, secrets, video_id)
                elif prov == "test_motion":
                    got = _test_motion(shot, dest, settings, fmt)
                label = LABEL.get(prov) if got else None
            except Exception as e:  # noqa: BLE001
                errors.append(f"{prov}: {e}")
        if not got:
            raise StepError(f"sin clip para {shot['file']}: {' | '.join(errors) or 'ningún proveedor disponible'}")
        vs = video_stream(got)
        if not vs:
            raise StepError(f"{got} no contiene vídeo")
        mscore = motion_score(got)
        if mscore < 0.6:
            raise StepError(f"{got} parece una imagen estática (movimiento {mscore:.2f}); se rechaza")
        out.append({**shot, "path": str(got), "label": label, "motion": round(mscore, 2),
                    "src_duration": ffprobe_duration(got)})
    labels = {s["label"] for s in out}
    log_event(video_id, "info", "scenes", f"{len(out)} tomas; fuentes: {', '.join(sorted(labels))}")
    return out
