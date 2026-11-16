"""PASO 5: narración en español de España.

Se sintetiza CADA beat por separado → conocemos su duración exacta y cada escena
se corta a medida de su frase (sincronía perfecta voz-imagen).

Proveedores (en orden de settings.providers.voice.order):
- wan2gp     → OmniVoice dentro de Wan2GP (motor local de Open-Generative-AI). Gratis. Todas las
               frases en un solo lote. Clona tu voz desde una referencia de 3-10 s (castellano).
- kaggle     → lo mismo en la GPU gratuita de Kaggle.
- voicestudio→ VoiceStudio local (mismo modelo OmniVoice, API compatible OpenAI). Gratis, CPU o GPU.
- elevenlabs → API de ElevenLabs (de pago, opcional).
- external   → archivos voice/beat_XX.wav ya presentes (grabados por ti o generados fuera).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import requests

from .core import StepError, add_cost, load_secrets, log_event
from .media import ffprobe_duration

PAUSE_BY_ROLE = {"hook": 0.30, "intro": 0.18, "body": 0.14, "detail": 0.14, "ending": 0.30, "cta": 0.10}


def _voicestudio(text: str, out: Path, cfg: dict, secrets: dict) -> None:
    key = secrets.get("VOICESTUDIO_API_KEY")
    r = requests.post(
        f"{cfg['url'].rstrip('/')}/v1/audio/speech",
        headers={"Authorization": f"Bearer {key}"} if key else {},
        json={"model": cfg.get("model", "omnivoice"), "input": text, "voice": cfg.get("voice", "default"),
              "instructions": cfg.get("instructions"), "response_format": "wav",
              "speed": cfg.get("speed", 1.0), "language": "es"},
        timeout=600,
    )
    if r.status_code != 200:
        raise StepError(f"VoiceStudio {r.status_code}: {r.text[:300]}")
    out.write_bytes(r.content)


def _elevenlabs(text: str, out: Path, cfg: dict, secrets: dict) -> None:
    key = secrets.get("ELEVENLABS_API_KEY")
    if not key or not cfg.get("voice_id"):
        raise StepError("ElevenLabs sin API key o voice_id")
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{cfg['voice_id']}?output_format=mp3_44100_128",
        headers={"xi-api-key": key},
        json={"text": text, "model_id": cfg.get("model_id", "eleven_multilingual_v2"),
              "voice_settings": {"stability": 0.38, "similarity_boost": 0.8, "style": 0.55, "use_speaker_boost": True}},
        timeout=300,
    )
    if r.status_code != 200:
        raise StepError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    mp3 = out.with_suffix(".mp3")
    mp3.write_bytes(r.content)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ar", "48000", str(out)], check=True)


def _agent_file(i: int, voice_dir: Path) -> Path | None:
    for ext in ("wav", "mp3", "m4a", "ogg"):
        p = voice_dir / f"beat_{i:02d}.{ext}"
        if p.exists():
            return p
    return None


def synthesize(script: dict, workdir: Path, settings: dict, video_id: int | None = None) -> list[dict]:
    """Devuelve [{path, duration, pause}] por beat, normalizado a WAV 48 kHz mono."""
    vcfg = settings["providers"]["voice"]
    secrets = load_secrets()
    vdir = workdir / "voice"
    vdir.mkdir(parents=True, exist_ok=True)
    result = []
    # lote Wan2GP/Kaggle para todas las frases que falten
    missing = [i for i in range(len(script["beats"])) if _agent_file(i, vdir) is None]
    for prov in vcfg["order"]:
        if prov == "elevenlabs" and secrets.get("ELEVENLABS_API_KEY") and vcfg["elevenlabs"].get("voice_id"):
            break  # la voz elegida (ElevenLabs) tiene prioridad: no generamos lote local
        if not missing or prov not in ("wan2gp", "kaggle"):
            continue
        try:
            from . import wan2gp
            tasks = [wan2gp.tts_task(script["beats"][i]["narration"], vcfg["wan2gp"], seed=7) for i in missing]
            if prov == "kaggle":
                from .kaggle_gpu import run_remote
                paths = run_remote(tasks, workdir / "tts_out", settings, "tts", video_id)
            else:
                if not wan2gp.available(settings["providers"]["wan2gp"]):
                    continue
                paths = wan2gp.run(tasks, workdir / "tts_out", settings["providers"]["wan2gp"], "tts", video_id)
            for i, src in zip(missing, paths):
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", "48000",
                                str(vdir / f"beat_{i:02d}.wav")], check=True)
            missing = []
        except Exception as e:  # noqa: BLE001
            log_event(video_id, "warn", "voice", f"{prov}: {e}")
    for i, beat in enumerate(script["beats"]):
        final = vdir / f"beat_{i:02d}.clean.wav"
        raw = vdir / f"beat_{i:02d}.raw.wav"
        src = _agent_file(i, vdir)
        errors = []
        if src is None:
            for prov in vcfg["order"]:
                try:
                    if prov == "voicestudio":
                        _voicestudio(beat["narration"], raw, vcfg["voicestudio"], secrets)
                    elif prov == "elevenlabs":
                        _elevenlabs(beat["narration"], raw, vcfg["elevenlabs"], secrets)
                        add_cost(video_id, "elevenlabs", f"beat {i}", usd=len(beat["narration"]) * 0.00018)
                    else:
                        continue
                    src = raw
                    break
                except Exception as e:  # noqa: BLE001 - probamos el siguiente proveedor
                    errors.append(f"{prov}: {e}")
            if src is None:
                raise StepError(f"sin voz para beat {i}: " + " | ".join(errors))
        clean_voice(src, final)
        result.append({"path": str(final), "duration": ffprobe_duration(final),
                       "pause": PAUSE_BY_ROLE.get(beat["role"], 0.15)})
    log_event(video_id, "info", "voice", f"{len(result)} frases, {sum(r['duration'] for r in result):.1f}s")
    return result


def clean_voice(src: Path, out: Path) -> None:
    """Cadena de locución: limpieza, presencia, compresión suave, recorte de silencios."""
    af = ("highpass=f=80,lowpass=f=15000,"
          "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
          "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse,"
          "equalizer=f=200:t=q:w=1.2:g=-2,equalizer=f=3500:t=q:w=1.0:g=2.5,"
          "acompressor=threshold=-20dB:ratio=3:attack=5:release=80:makeup=3,"
          "alimiter=limit=0.95")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", af,
                    "-ar", "48000", "-ac", "1", str(out)], check=True)


def write_voice_manifest(script: dict, workdir: Path, settings: dict) -> None:
    """Tareas OmniVoice (Wan2GP) para generar la voz en otra máquina o en Kaggle/Colab."""
    import json
    from . import wan2gp
    cfg = settings["providers"]["voice"]["wan2gp"]
    tasks = [wan2gp.tts_task(b["narration"], cfg, seed=7) for b in script["beats"]]
    for t in tasks:  # la referencia viaja junto al manifest
        if t.get("audio_guide"):
            t["audio_guide"] = "marcius3r_ref.wav"
    shots = [{"file": f"voice/beat_{i:02d}.wav"} for i in range(len(tasks))]
    (workdir / "generation_tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
    (workdir / "generation_manifest.json").write_text(json.dumps(
        {"engine": "wan2gp", "stage": "voice", "unzip_to": "voice", "shots": shots, "tasks": tasks},
        ensure_ascii=False, indent=2))


def design_candidates(settings: dict, out_dir: Path, remote: bool = False) -> list[Path]:
    """Genera voces candidatas ORIGINALES (Qwen3-TTS VoiceDesign) con el estilo descrito en settings."""
    from . import wan2gp
    d = settings["providers"]["voice"]["design"]
    tasks = [wan2gp.voice_design_task(d["sample_text"], f"{d['base']}. {v}", d.get("language", "spanish"), 20, seed=i + 1)
             for i, v in enumerate(d["variants"])]
    out_dir.mkdir(parents=True, exist_ok=True)
    if remote:
        from .kaggle_gpu import run_remote
        paths = run_remote(tasks, out_dir, settings, "voicedesign")
    else:
        paths = wan2gp.run(tasks, out_dir, settings["providers"]["wan2gp"], "voicedesign")
    result = []
    for i, src in enumerate(paths, 1):
        dest = out_dir / f"candidata_{i}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", "24000", "-ac", "1", str(dest)], check=True)
        result.append(dest)
    return result


def pick_candidate(n: int, settings: dict, cand_dir: Path) -> Path:
    """Fija la candidata N como voz del canal (referencia para OmniVoice) y guarda su transcripción."""
    import yaml as _yaml
    from .core import ROOT
    src = cand_dir / f"candidata_{n}.wav"
    if not src.exists():
        raise StepError(f"no existe {src}")
    cfg = settings["providers"]["voice"]["wan2gp"]
    dest = ROOT / cfg["reference_audio"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    # recorte a ≤10 s (OmniVoice rinde mejor con 3-10 s de referencia)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-t", "10", "-af",
                    "silenceremove=start_periods=1:start_threshold=-45dB,afade=t=out:st=9.7:d=0.3", str(dest)], check=True)
    text = settings["providers"]["voice"]["design"]["sample_text"]
    p = ROOT / "config" / "settings.yaml"
    raw = p.read_text(encoding="utf-8")
    raw = raw.replace('reference_transcript: ""', f'reference_transcript: "{text}"', 1)
    p.write_text(raw, encoding="utf-8")
    _yaml.safe_load(raw)  # sigue siendo YAML válido
    return dest
