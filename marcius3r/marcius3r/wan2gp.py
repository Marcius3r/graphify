"""Motor local GRATUITO de Open-Generative-AI: Wan2GP (deepbeepmeep/Wan2GP).

Open-Generative-AI ejecuta sus modelos locales lanzando `wgp.py --process settings.json`
(electron/lib/wan2gpProvider.js + wan2gpCatalog.js). Aquí hacemos exactamente lo mismo
desde Python, pero con una LISTA de tareas por llamada (el modelo se carga una sola vez).

Modelos usados (pesos abiertos, salidas monetizables; Wan2GP pide citarlo si se venden):
- Vídeo:  ltx2_25_22B_distilled  (LTX-2.5, 8 pasos, vídeo + SONIDO sincronizado)
          t2v_1.3B               (Wan 2.1 1.3B, ~8 GB VRAM, respaldo ligero, 480p)
          hunyuan_1_5_480_t2v    (Hunyuan Video 1.5, 480p)
- Voz:    omnivoice              (100 idiomas, clonación con referencia de 3-10 s)
- Música: ace_step_v1_5_turbo_lm_1_7b (ACE-Step 1.5, Apache-2.0, "[Instrumental]")

Requiere GPU NVIDIA/AMD (≥8 GB VRAM). Sin GPU: ver kaggle_gpu.py (GPU gratis de Kaggle).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

from .core import ROOT, StepError, log_event

RES = {
    "ltx": {"9:16": "704x1280", "16:9": "1280x704"},
    "480": {"9:16": "480x832", "16:9": "832x480"},
}
FPS = {"ltx": 24, "480": 16}


def family(model_type: str) -> str:
    return "ltx" if model_type.startswith("ltx") else "480"


def video_task(prompt: str, seconds: float, aspect: str, model_type: str, seed: int, negative: str = "") -> dict:
    fam = family(model_type)
    frames = int(round(seconds * FPS[fam]))
    if fam == "ltx":
        frames = (frames // 8) * 8 + 1          # LTX necesita 8k+1 fotogramas
    else:
        frames = (frames // 4) * 4 + 1          # Wan necesita 4k+1
    t = {"model_type": model_type, "prompt": prompt, "resolution": RES[fam][aspect],
         "video_length": frames, "seed": seed}
    if negative:
        t["negative_prompt"] = negative
    return t


def tts_task(text: str, cfg: dict, seed: int = 7) -> dict:
    t = {"model_type": "omnivoice", "prompt": text, "model_mode": cfg.get("language", "spanish"),
         "num_inference_steps": cfg.get("steps", 32), "temperature": cfg.get("temperature", 0.1), "seed": seed}
    ref = cfg.get("reference_audio")
    if ref and (ROOT / ref).exists():
        t["audio_prompt_type"] = "A"
        t["audio_guide"] = str((ROOT / ref).resolve())
        t["alt_prompt"] = cfg.get("reference_transcript", "")
    else:
        t["audio_prompt_type"] = ""
        t["alt_prompt"] = cfg.get("voice_tags", "male, young adult, moderate pitch")
    return t


def voice_design_task(text: str, description: str, language: str = "spanish", seconds: int = 20, seed: int = 1) -> dict:
    """Qwen3-TTS VoiceDesign: crea una voz NUEVA a partir de una descripción (no clona a nadie)."""
    return {"model_type": "qwen3_tts_voicedesign", "prompt": text, "alt_prompt": description,
            "model_mode": language, "duration_seconds": seconds, "seed": seed}


def music_task(style: str, seconds: float, seed: int = 11) -> dict:
    return {"model_type": "ace_step_v1_5_turbo_lm_1_7b", "prompt": "[Instrumental]", "alt_prompt": style,
            "duration_seconds": int(seconds) + 2, "num_inference_steps": 8, "seed": seed}


def _cmd(cfg: dict, tasks_file: Path, out_dir: Path) -> list[str]:
    folder = Path(os.path.expanduser(cfg["path"]))
    default = folder / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    py = cfg.get("python") or str(default)
    cmd = [py, "wgp.py", "--process", str(tasks_file), "--output-dir", str(out_dir)]
    if cfg.get("profile") is not None:
        cmd += ["--profile", str(cfg["profile"])]
    if cfg.get("attention"):
        cmd += ["--attention", cfg["attention"]]
    return cmd


def available(cfg: dict) -> bool:
    return bool(cfg.get("path")) and (Path(os.path.expanduser(cfg["path"])) / "wgp.py").exists()


def run(tasks: list[dict], out_dir: Path, cfg: dict, label: str, video_id: int | None = None,
        timeout: int = 4 * 3600) -> list[Path]:
    """Ejecuta las tareas en Wan2GP y devuelve las rutas generadas EN EL MISMO ORDEN."""
    if not available(cfg):
        raise StepError("Wan2GP no instalado: configura providers.wan2gp.path (ver README §2)")
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks_file = out_dir / f"{label}_tasks.json"
    tasks_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
    t0 = time.time()
    p = subprocess.run(_cmd(cfg, tasks_file, out_dir), cwd=os.path.expanduser(cfg["path"]),
                       capture_output=True, text=True, timeout=timeout)
    log_path = out_dir / f"{label}_wgp.log"
    log_path.write_text(p.stdout + "\n--- stderr ---\n" + p.stderr)
    out = re.sub(r"\x1b\[[0-9;]*m", "", p.stdout + p.stderr)
    if "out of memory" in out.lower():
        raise StepError(f"Wan2GP sin VRAM ({label}): usa un modelo más ligero o --profile 4. Log: {log_path}")
    m = re.search(r"Queue completed:\s*(\d+)/(\d+)", out)
    if p.returncode != 0 or not m or m.group(1) != m.group(2):
        raise StepError(f"Wan2GP falló ({label}, código {p.returncode}). Log: {log_path}")
    saved = [Path(s.strip()) for s in re.findall(r"saved to Path:\s*(.+?)\s*$", out, re.M)]
    if len(saved) != len(tasks):  # respaldo: ficheros nuevos por fecha
        media = [f for f in out_dir.iterdir() if f.suffix.lower() in (".mp4", ".wav", ".mp3", ".flac")
                 and f.stat().st_mtime >= t0]
        saved = sorted(media, key=lambda f: f.stat().st_mtime)
    if len(saved) != len(tasks):
        raise StepError(f"Wan2GP devolvió {len(saved)} archivos para {len(tasks)} tareas ({label})")
    log_event(video_id, "info", "wan2gp", f"{label}: {len(tasks)} tareas en {time.time()-t0:.0f}s")
    return saved
