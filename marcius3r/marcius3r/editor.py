"""PASO 7: montaje automático cinematográfico con FFmpeg.

- Cada frase del guion = 1 segmento de vídeo cortado a la duración exacta de su voz.
- Frases largas se dividen en dos planos (original + punch-in desde otro momento del clip)
  → cambios de plano constantes, ritmo de Short.
- Empuje de cámara suave, etalonaje neón (negro/morado/azul), viñeta y grano.
- Destellos de transición en cada cambio de frase + whoosh.
- Voz procesada + música con ducking (sidechain) + efectos de sonido + loudnorm -14 LUFS.
- Subtítulos palabra a palabra, textos de impacto, etiqueta de origen y marca.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

from .core import ROOT, log_event
from .media import ffprobe_duration, has_audio, run
from .subtitles import build_ass, fonts_dir, word_timings

GRADE = ("eq=contrast=1.08:saturation=1.16:gamma=0.97,"
         "colorbalance=rs=0.03:bs=0.07:rm=0.02:bm=0.03:rh=0.02:bh=0.04,"
         "vignette=PI/5,noise=alls=5:allf=t")


def _enc(settings: dict, final: bool = False) -> list[str]:
    preset = "medium" if final else "veryfast"
    return ["-c:v", "libx264", "-preset", preset, "-crf", "18" if final else "20", "-pix_fmt", "yuv420p"]


def build_timeline(script: dict, voice: list[dict], clips: list[dict]) -> list[dict]:
    """Calcula los cortes: start/end, clip fuente, offset y tipo de plano."""
    by_beat: dict[int, list[dict]] = {}
    for c in clips:
        by_beat.setdefault(c["beat"], []).append(c)
    rnd = random.Random(42)
    t = 0.0
    timeline = []
    for i, (beat, v) in enumerate(zip(script["beats"], voice)):
        seg = v["duration"] + v["pause"]
        shots = sorted(by_beat[i], key=lambda c: c["part"])
        cuts = []
        if len(shots) == 1 and seg > 2.8:
            s = shots[0]
            a = seg * rnd.uniform(0.5, 0.6)
            cuts = [(s, a, 0.0, "wide"), (s, seg - a, min(s["src_duration"] * 0.45, max(0.0, s["src_duration"] - (seg - a) - 0.05)), "punch")]
        else:
            per = seg / len(shots)
            cuts = [(s, per, 0.0, "wide" if k % 2 == 0 else "punch") for k, s in enumerate(shots)]
        for k, (s, d, off, kind) in enumerate(cuts):
            timeline.append({"beat": i, "part": k, "start": t, "end": t + d, "dur": d, "src": s["path"],
                             "src_duration": s["src_duration"], "offset": off, "kind": kind, "label": s["label"],
                             "overlay_text": beat["overlay_text"] if k == 0 else "",
                             "role": beat["role"], "sfx": beat["sfx"] if k == 0 else ""})
            t += d
        # palabras de este beat (sobre la duración de la voz, no de la pausa)
        beat_start = timeline[-len(cuts)]["start"]
        timeline[-len(cuts)]["words"] = word_timings(beat["narration"], beat_start, v["duration"])
    return timeline


def render_cut(cut: dict, out: Path, fmt: str, settings: dict) -> Path:
    f = settings["formats"][fmt]
    W, H, fps = f["width"], f["height"], f["fps"]
    d = cut["dur"]
    avail = cut["src_duration"] - cut["offset"]
    speed = 1.0
    loop = []
    if avail < d:
        speed = min(1.35, d / max(avail, 0.1))      # cámara lenta suave
        if avail * speed < d:
            loop = ["-stream_loop", "-1"]
    zoom_end = 1.07 if cut["kind"] == "wide" else 1.28
    zoom_start = 1.0 if cut["kind"] == "wide" else 1.18
    frames = max(1, int(d * fps))
    zexpr = f"{zoom_start}+({zoom_end}-{zoom_start})*on/{frames}"
    vf = (f"setpts={speed:.4f}*PTS,fps={fps},scale={int(W*1.15)}:{int(H*1.15)}:force_original_aspect_ratio=increase,"
          f"crop={int(W*1.15)}:{int(H*1.15)},"
          f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps},{GRADE}")
    run(["ffmpeg", "-y", "-loglevel", "error", *loop, "-ss", f"{cut['offset']:.3f}", "-i", cut["src"],
         "-t", f"{d:.3f}", "-vf", vf, "-an", *_enc(settings), "-r", str(fps), str(out)])
    return out


# ---------------------------------------------------------------- audio
def _sfx_file(name: str, settings: dict) -> Path | None:
    lib = ROOT / settings["providers"]["sfx"]["library"]
    if not name or not lib.exists():
        return None
    keys = set(re.findall(r"[a-z]+", name.lower()))
    best, best_s = None, 0
    for p in lib.glob("*.*"):
        s = len(keys & set(re.findall(r"[a-z]+", p.stem.lower())))
        if s > best_s:
            best, best_s = p, s
    return best


def synth_whoosh(out: Path, dur: float = 0.45) -> Path:
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anoisesrc=d={dur}:c=pink:a=0.6",
         "-af", f"highpass=f=300,lowpass=f=6000,afade=t=in:d={dur*0.6},afade=t=out:st={dur*0.6}:d={dur*0.4},"
         "aecho=0.6:0.4:40:0.3", "-ar", "48000", "-ac", "2", str(out)])
    return out


def synth_boom(out: Path) -> Path:
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=48:d=1.2",
         "-f", "lavfi", "-i", "anoisesrc=d=1.2:c=brown:a=0.5",
         "-filter_complex", "[0][1]amix=inputs=2,lowpass=f=180,afade=t=out:st=0.05:d=1.1,volume=4",
         "-ar", "48000", "-ac", "2", str(out)])
    return out


def synth_music_bed(out: Path, dur: float) -> Path:
    """Respaldo: lecho sintético oscuro (pad + pulso). Se avisa en QC; preferible música real."""
    run(["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"sine=f=55:d={dur}", "-f", "lavfi", "-i", f"sine=f=82.4:d={dur}",
         "-f", "lavfi", "-i", f"sine=f=130.8:d={dur}", "-f", "lavfi", "-i", f"anoisesrc=d={dur}:c=pink:a=0.08",
         "-filter_complex",
         "[0]volume=0.5[a];[1]volume=0.3,tremolo=f=2:d=0.6[b];[2]volume=0.12,vibrato=f=0.2:d=0.3[c];"
         "[3]highpass=f=6000,tremolo=f=8:d=0.9,volume=0.6[h];[a][b][c][h]amix=inputs=4:normalize=0,"
         f"lowpass=f=2500,afade=t=in:d=0.5,afade=t=out:st={max(0, dur-1.5)}:d=1.5",
         "-ar", "48000", "-ac", "2", str(out)])
    return out


def pick_music(workdir: Path, settings: dict, dur: float, mood: str) -> tuple[Path, bool]:
    for ext in ("wav", "mp3", "m4a"):
        p = workdir / f"music.{ext}"
        if p.exists():
            return p, True
    lib = ROOT / settings["providers"]["music"]["library"]
    tracks = [p for p in lib.glob("*.*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")] if lib.exists() else []
    if tracks:
        meta = lib / "licenses.yaml"
        return random.Random(mood).choice(tracks), meta.exists()
    return synth_music_bed(workdir / "music_synth.wav", dur), False


def build_audio(voice: list[dict], timeline: list[dict], workdir: Path, settings: dict, total: float,
                mood: str) -> tuple[Path, dict]:
    adir = workdir / "audio"
    adir.mkdir(exist_ok=True)
    # 1) pista de voz con pausas naturales
    parts, ins = [], []
    for i, v in enumerate(voice):
        ins += ["-i", v["path"]]
        parts.append(f"[{i}]apad=pad_dur={v['pause']:.3f},aformat=sample_rates=48000:channel_layouts=mono[v{i}]")
    concat = "".join(f"[v{i}]" for i in range(len(voice)))
    voice_track = adir / "voice.wav"
    run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex",
         ";".join(parts) + f";{concat}concat=n={len(voice)}:v=0:a=1[out]", "-map", "[out]", "-ar", "48000", str(voice_track)])
    # 2) efectos: whoosh en cada cambio de frase + sfx del guion + boom en el gancho
    whoosh = synth_whoosh(adir / "whoosh.wav")
    boom = synth_boom(adir / "boom.wav")
    fx_inputs, fx_filters, n = [], [], 0
    for cut in timeline:
        if cut["part"] != 0:
            continue
        events = []
        if cut["start"] > 0.05:
            events.append((whoosh, max(0, cut["start"] - 0.25), 0.55))
        lib = _sfx_file(cut["sfx"], settings)
        if lib:
            events.append((lib, cut["start"], 0.35))
        if cut["role"] == "hook":
            events.append((boom, 0.0, 0.8))
        for path, at, vol in events:
            fx_inputs += ["-i", str(path)]
            fx_filters.append(f"[{n}]aformat=sample_rates=48000:channel_layouts=stereo,volume={vol},adelay={int(at*1000)}|{int(at*1000)}[f{n}]")
            n += 1
    fx_track = adir / "fx.wav"
    mix = "".join(f"[f{i}]" for i in range(n))
    run(["ffmpeg", "-y", "-loglevel", "error", *fx_inputs, "-filter_complex",
         ";".join(fx_filters) + f";{mix}amix=inputs={n}:normalize=0,apad=whole_dur={total:.3f}[o]",
         "-map", "[o]", "-t", f"{total:.3f}", str(fx_track)])
    # 3) música con ducking bajo la voz
    music, licensed = pick_music(workdir, settings, total, mood)
    final = adir / "mix.wav"
    lufs = settings["qc"]["target_lufs"]
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voice_track), "-stream_loop", "-1", "-i", str(music),
         "-i", str(fx_track), "-filter_complex",
         f"[0]aformat=channel_layouts=stereo,asplit=2[vo][key];"
         f"[1]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.42,atrim=0:{total:.3f},"
         f"afade=t=out:st={max(0, total-1.2):.3f}:d=1.2[mu];"
         f"[mu][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[duck];"
         f"[vo][duck][2]amix=inputs=3:normalize=0:duration=first,"
         f"loudnorm=I={lufs}:TP=-1.5:LRA=11",
         "-ar", "48000", "-t", f"{total:.3f}", str(final)])
    return final, {"music": str(music), "music_licensed": licensed, "music_synth": "music_synth" in music.name,
                   "sfx_events": n}


# ---------------------------------------------------------------- render final
def render(script: dict, voice: list[dict], clips: list[dict], workdir: Path, fmt: str, settings: dict,
           video_id: int | None = None, final_quality: bool = True) -> dict:
    f = settings["formats"][fmt]
    timeline = build_timeline(script, voice, clips)
    total = timeline[-1]["end"]
    cdir = workdir / "cuts"
    cdir.mkdir(exist_ok=True)
    listing = []
    for k, cut in enumerate(timeline):
        p = render_cut(cut, cdir / f"cut_{k:03d}.mp4", fmt, settings)
        listing.append(f"file '{p.as_posix()}'")
    (cdir / "list.txt").write_text("\n".join(listing) + "\n")
    raw = workdir / "video_raw.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(cdir / "list.txt"),
         "-c", "copy", str(raw)])
    audio, audio_info = build_audio(voice, timeline, workdir, settings, total, script.get("music_mood", ""))
    ass = build_ass(script, timeline, fmt, settings, workdir / "subs.ass", total)
    # destellos neón en cada cambio de frase
    flashes = [c["start"] for c in timeline if c["part"] == 0 and c["start"] > 0.05]
    purple = settings["brand"]["colors"]["neon_purple"].replace("#", "0x")
    flash_vf = ",".join(f"drawbox=x=0:y=0:w=iw:h=ih:color={purple}@0.28:t=fill:enable='between(t,{t:.3f},{t+0.07:.3f})'"
                        for t in flashes)
    vf = (flash_vf + "," if flash_vf else "") + f"ass={ass.as_posix()}:fontsdir={fonts_dir().as_posix()}"
    out = workdir / f"final_{fmt}.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-i", str(audio), "-vf", vf,
         "-map", "0:v", "-map", "1:a", *_enc(settings, final_quality), "-r", str(f["fps"]),
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(out)])
    info = {"output": str(out), "duration": ffprobe_duration(out), "cuts": len(timeline), "audio": audio_info,
            "labels": sorted({c["label"] for c in timeline}), "has_audio": has_audio(out),
            "timeline": [{k: v for k, v in c.items() if k != "words"} for c in timeline]}
    (workdir / "render.json").write_text(json.dumps(info, ensure_ascii=False, indent=2))
    log_event(video_id, "info", "edit", f"render {fmt}: {info['duration']:.1f}s, {len(timeline)} planos")
    return info
