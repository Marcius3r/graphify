"""GPU GRATUITA: ejecuta Wan2GP (motor local de Open-Generative-AI) en un notebook de Kaggle.

Kaggle da GPU gratis (T4/P100, cuota semanal ~30 h) a cuentas verificadas por teléfono.
Flujo: se crea un 'kernel' privado con las tareas → `kaggle kernels push` → se espera →
`kaggle kernels output` descarga los vídeos/audios → se devuelven en el mismo orden.

Requisitos: `pip install kaggle` y ~/.kaggle/kaggle.json (Kaggle → Settings → API → Create New Token).
Wan2GP se fija a un commit revisado (WAN2GP_COMMIT) para no ejecutar código nuevo sin revisar.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import time
from pathlib import Path

from .core import StepError, log_event

WAN2GP_COMMIT = "38758d3c73366422efcf609abb63cab8385f3552"  # revisado el 2026-11-16

RUNNER = r'''
import base64, json, os, re, subprocess, sys, glob, shutil
W = "/kaggle/working"
TASKS = json.loads(base64.b64decode("{tasks_b64}").decode())
FILES = json.loads(base64.b64decode("{files_b64}").decode())
for name, b64 in FILES.items():
    open(os.path.join(W, name), "wb").write(base64.b64decode(b64))
for t in TASKS:
    for k, v in list(t.items()):
        if isinstance(v, str) and v.startswith("@file:"):
            t[k] = os.path.join(W, v[6:])
def sh(c):
    print("+", c, flush=True); r = subprocess.run(c, shell=True); assert r.returncode == 0, c
sh("git clone -q https://github.com/deepbeepmeep/Wan2GP /kaggle/temp/Wan2GP && cd /kaggle/temp/Wan2GP && git checkout -q {commit}")
sh("cd /kaggle/temp/Wan2GP && pip install -q -r requirements.txt 2>&1 | tail -3")
json.dump(TASKS, open(W + "/tasks.json", "w"))
os.makedirs(W + "/out", exist_ok=True)
p = subprocess.run([sys.executable, "wgp.py", "--process", W + "/tasks.json", "--output-dir", W + "/out",
                    "--profile", "{profile}"], cwd="/kaggle/temp/Wan2GP", capture_output=True, text=True)
log = p.stdout + p.stderr
open(W + "/wgp.log", "w").write(log)
saved = re.findall(r"saved to Path:\s*(.+?)\s*$", re.sub(r"\x1b\[[0-9;]*m", "", log), re.M)
for i, s in enumerate(saved):
    shutil.copy(s.strip(), f"{{W}}/result_{{i:03d}}{{os.path.splitext(s.strip())[1]}}")
print("RESULTS", len(saved), "of", len(TASKS))
sys.exit(0 if len(saved) == len(TASKS) else 1)
'''


def _kaggle(*args: str, timeout: int = 600) -> str:
    p = subprocess.run(["kaggle", *args], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise StepError(f"kaggle {' '.join(args[:2])}: {p.stderr[-500:] or p.stdout[-500:]}")
    return p.stdout


def _username() -> str:
    if os.environ.get("KAGGLE_USERNAME"):
        return os.environ["KAGGLE_USERNAME"]
    f = Path.home() / ".kaggle" / "kaggle.json"
    if not f.exists():
        raise StepError("Falta ~/.kaggle/kaggle.json (Kaggle → Settings → API → Create New Token)")
    return json.loads(f.read_text())["username"]


def run_remote(tasks: list[dict], out_dir: Path, settings: dict, label: str, video_id: int | None = None) -> list[Path]:
    cfg = settings["providers"].get("kaggle", {})
    user = _username()
    slug = f"marcius3r-{label}-{int(time.time())}"
    kdir = out_dir / f"kaggle_{label}"
    kdir.mkdir(parents=True, exist_ok=True)
    files, tasks = {}, json.loads(json.dumps(tasks))
    for t in tasks:  # adjuntar archivos locales (p.ej. tu voz de referencia)
        for k, v in list(t.items()):
            if k in ("audio_guide", "image_start") and isinstance(v, str) and Path(v).exists():
                name = f"in_{len(files)}{Path(v).suffix}"
                files[name] = base64.b64encode(Path(v).read_bytes()).decode()
                t[k] = f"@file:{name}"
    code = RUNNER.format(tasks_b64=base64.b64encode(json.dumps(tasks).encode()).decode(),
                         files_b64=base64.b64encode(json.dumps(files).encode()).decode(),
                         commit=WAN2GP_COMMIT, profile=cfg.get("profile", 4))
    (kdir / "run.py").write_text(code)
    (kdir / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{user}/{slug}", "title": slug, "code_file": "run.py", "language": "python",
        "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
        "machine_shape": cfg.get("machine_shape", "NvidiaTeslaT4"),
        "dataset_sources": [], "competition_sources": [], "kernel_sources": []}, indent=2))
    _kaggle("kernels", "push", "-p", str(kdir))
    log_event(video_id, "info", "kaggle", f"{label}: {len(tasks)} tareas enviadas a GPU gratuita ({user}/{slug})")
    deadline = time.time() + cfg.get("timeout_minutes", 170) * 60
    status = ""
    while time.time() < deadline:
        time.sleep(60)
        status = _kaggle("kernels", "status", f"{user}/{slug}").lower()
        if re.search(r"complete|error|cancel", status):
            break
    res_dir = out_dir / f"kaggle_{label}_out"
    res_dir.mkdir(exist_ok=True)
    _kaggle("kernels", "output", f"{user}/{slug}", "-p", str(res_dir), timeout=1800)
    results = sorted(res_dir.glob("result_*.*"))
    if "complete" not in status or len(results) != len(tasks):
        raise StepError(f"Kaggle {label}: estado '{status.strip()}', {len(results)}/{len(tasks)} resultados. "
                        f"Revisa {res_dir}/wgp.log")
    return results
