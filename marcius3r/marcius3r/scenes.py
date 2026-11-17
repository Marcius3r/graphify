"""PASO 6: escenas de vídeo con movimiento real, una por frase del guion.

Fuentes (por orden en settings.providers.video.order):
- gameplay_library  → tus capturas legítimas de GTA 6 (etiquetadas). Marca "GAMEPLAY".
- wan2gp            → motor local GRATUITO de Open-Generative-AI (LTX-2.5 con sonido / Wan / Hunyuan),
                      todas las tomas en una sola ejecución. Marca "RECREACIÓN IA".
- kaggle            → el mismo Wan2GP en la GPU gratuita de Kaggle (si no tienes GPU).
- external          → clips ya presentes en workdir/clips/ (generados en otra máquina con el manifest).
- muapi             → nube de Open-Generative-AI (MuAPI, DE PAGO, opcional). Marca "RECREACIÓN IA".
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
from .media import ffprobe_duration, has_audio, motion_score, run, video_stream

AI = "RECREACIÓN IA"
LABEL = {"gameplay_library": "GAMEPLAY", "muapi": AI, "wan2gp": AI, "kaggle": AI, "external": AI,
         "test_motion": "PRUEBA — NO PUBLICAR"}
NEGATIVE = ("static image, slideshow, still photo, text, watermark, logo, subtitles, blurry, deformed hands, "
            "extra limbs, distorted face, low quality, jpeg artifacts")

STYLE_SUFFIX = ("cinematic, photorealistic, dynamic camera movement, natural motion, people and cars moving, "
                "humid tropical air, neon reflections, film grain, shallow depth of field, no text, no logos")


def plan_shots(script: dict, voice: list[dict], fmt: str, settings: dict) -> list[dict]:
    """Una toma por beat (dos si la frase es larga). Devuelve la lista de tomas a generar."""
    clip_len = settings["formats"][fmt]["clip_seconds"]
    aspect = "9:16" if fmt == "short" else "16:9"
    shots = []
    for i, (beat, v) in enumerate(zip(script["beats"], voice)):
        need = v["duration"] + v["pause"]
        if beat.get("footage"):  # clips reales pedidos por nombre en el guion
            for k, fname in enumerate(beat["footage"]):
                shots.append({"beat": i, "part": k, "seconds": need / len(beat["footage"]), "aspect_ratio": aspect,
                              "prompt": beat["scene_prompt"], "library_file": fname,
                              "file": f"clips/beat_{i:02d}_{k}.mp4"})
            continue
        n = max(1, math.ceil(need / (clip_len * 0.95)))
        for k in range(n):
            prompt = beat["scene_prompt"] if k == 0 else f"{beat['scene_prompt']} Different angle, closer shot."
            shots.append({"beat": i, "part": k, "seconds": clip_len, "aspect_ratio": aspect,
                          "prompt": f"{prompt} Camera: {beat['camera']}. {STYLE_SUFFIX}",
                          "file": f"clips/beat_{i:02d}_{k}.mp4"})
    return shots


def wan2gp_tasks(shots: list[dict], settings: dict) -> list[dict]:
    from .wan2gp import video_task
    cfg = settings["providers"]["video"]["wan2gp"]
    return [video_task(sh["prompt"], sh["seconds"], sh["aspect_ratio"], cfg["model"],
                       seed=random.Random(sh["prompt"]).randint(1, 2**31 - 1), negative=NEGATIVE) for sh in shots]


def write_manifest(shots: list[dict], workdir: Path, settings: dict) -> Path:
    """Manifest portable: con él se pueden generar las tomas en cualquier máquina con Wan2GP
    (`python wgp.py --process generation_tasks.json`) y copiarlas a workdir/clips/."""
    tasks = wan2gp_tasks(shots, settings)
    p = workdir / "generation_manifest.json"
    p.write_text(json.dumps({"engine": "wan2gp", "shots": shots, "tasks": tasks}, ensure_ascii=False, indent=2))
    (workdir / "generation_tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
    return p


# ---------------------------------------------------------------- proveedores
def _library(settings: dict) -> tuple[Path, list[dict]]:
    cfg = settings["providers"]["video"]["gameplay_library"]
    lib = ROOT / cfg["path"]
    idx = lib / "index.yaml"
    entries = (yaml.safe_load(idx.read_text()) or []) if idx.exists() else []
    allow_official = bool(cfg.get("allow_official_footage", False))
    ok = [e for e in entries if (lib / e["file"]).exists() and (allow_official or e.get("source") != "official")]
    return lib, ok


def _label_of(entry: dict) -> str:
    return entry.get("label") or ("IMAGEN OFICIAL" if entry.get("source") == "official" else "GAMEPLAY")


def _gameplay(shot: dict, beat: dict, settings: dict, used: set[str]) -> tuple[Path, str] | None:
    lib, entries = _library(settings)
    if not entries:
        return None
    if shot.get("library_file"):
        e = next((e for e in entries if e["file"] == shot["library_file"]), None)
        if e:
            used.add(e["file"])
            return lib / e["file"], _label_of(e)
    tags = {t.lower() for t in beat.get("footage_tags", [])}
    words = set(re.findall(r"[a-z]+", (beat["scene_prompt"] + " " + beat["narration"]).lower())) | tags
    best, best_s = None, 0
    for e in entries:
        if e["file"] in used:
            continue
        et = {t.lower() for t in e.get("tags", [])}
        s = len(words & et) + 2 * len(tags & et)
        if s > best_s:
            best, best_s = e, s
    if best is None or best_s < 2:
        # si el guion pidió clips reales concretos y se agotaron, otro clip real antes que IA
        if shot.get("library_file") or tags:
            best = next((e for e in entries if e["file"] not in used), None)
        if best is None:
            return None
    used.add(best["file"])
    return lib / best["file"], _label_of(best)


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
         "-f", "lavfi", "-i", f"anoisesrc=d={d}:c=brown:a=0.08",
         "-filter_complex",
         f"[1:v]hue=h=t*40,scale={w}:{w}[m];[0:v][m]overlay=y=(H-h)/2+60*sin(t*2):shortest=1,"
         f"drawbox=x='mod(t*{w//2}+{seed},{w})':y=ih*0.72:w=180:h=8:color={c2}@0.9:t=fill,"
         f"drawbox=x='{w}-mod(t*{w//3}+{seed},{w})':y=ih*0.78:w=120:h=6:color=white@0.8:t=fill[v]",
         "-map", "[v]", "-map", "2:a", "-t", str(d), "-c:v", "libx264", "-preset", "veryfast",
         "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)])
    return out


def _batch_wan2gp(pending: list[dict], workdir: Path, settings: dict, video_id: int | None, remote: bool) -> None:
    from . import wan2gp
    tasks = wan2gp_tasks(pending, settings)
    if remote:
        from .kaggle_gpu import run_remote
        paths = run_remote(tasks, workdir / "wan2gp_out", settings, "scenes", video_id)
    else:
        paths = wan2gp.run(tasks, workdir / "wan2gp_out", settings["providers"]["wan2gp"], "scenes", video_id)
    for sh, src in zip(pending, paths):
        dest = workdir / sh["file"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(Path(src).read_bytes())


def gather_clips(script: dict, shots: list[dict], workdir: Path, fmt: str, settings: dict,
                 video_id: int | None = None, allow_test: bool = False) -> list[dict]:
    """Consigue un clip por toma. Devuelve las tomas con 'path' y 'label'."""
    secrets = load_secrets()
    (workdir / "clips").mkdir(parents=True, exist_ok=True)
    order = list(settings["providers"]["video"]["order"]) + (["test_motion"] if allow_test else [])
    used: set[str] = set()
    got: dict[str, tuple[Path, str]] = {}
    errors: list[str] = []
    # 1) clips ya presentes (generados fuera) y gameplay propio, toma a toma
    for sh in shots:
        dest = workdir / sh["file"]
        if dest.exists() and dest.stat().st_size > 10_000:
            got[sh["file"]] = (dest, LABEL["external"])
        elif "gameplay_library" in order:
            g = _gameplay(sh, script["beats"][sh["beat"]], settings, used)
            if g:
                got[sh["file"]] = g
    # 2) proveedores por lotes / por toma para lo que falta
    for prov in order:
        pending = [sh for sh in shots if sh["file"] not in got]
        if not pending:
            break
        try:
            if prov in ("wan2gp", "kaggle"):
                from . import wan2gp
                if prov == "wan2gp" and not wan2gp.available(settings["providers"]["wan2gp"]):
                    errors.append("wan2gp: no instalado en esta máquina")
                    continue
                _batch_wan2gp(pending, workdir, settings, video_id, remote=(prov == "kaggle"))
                for sh in pending:
                    got[sh["file"]] = (workdir / sh["file"], LABEL[prov])
            elif prov == "muapi":
                for sh in pending:
                    got[sh["file"]] = (_muapi(sh, workdir / sh["file"], settings, secrets, video_id), LABEL[prov])
            elif prov == "test_motion":
                for sh in pending:
                    got[sh["file"]] = (_test_motion(sh, workdir / sh["file"], settings, fmt), LABEL[prov])
        except Exception as e:  # noqa: BLE001 - probamos el siguiente proveedor
            errors.append(f"{prov}: {e}")
    missing = [sh["file"] for sh in shots if sh["file"] not in got]
    if missing:
        raise StepError(f"faltan {len(missing)} clips ({missing[0]}…): {' | '.join(errors) or 'sin proveedores'}")
    out = []
    for sh in shots:
        path, label = got[sh["file"]]
        if not video_stream(path):
            raise StepError(f"{path} no contiene vídeo")
        mscore = motion_score(path)
        if mscore < 0.6:
            raise StepError(f"{path} parece una imagen estática (movimiento {mscore:.2f}); se rechaza")
        out.append({**sh, "path": str(path), "label": label, "motion": round(mscore, 2),
                    "src_duration": ffprobe_duration(path), "has_audio": has_audio(path)})
    log_event(video_id, "info", "scenes", f"{len(out)} tomas; fuentes: {', '.join(sorted({o['label'] for o in out}))}")
    return out
