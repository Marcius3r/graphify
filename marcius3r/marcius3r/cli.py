"""Línea de comandos: `python -m marcius3r <orden>`."""
from __future__ import annotations

import argparse
import json
import sys

from . import core


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="marcius3r", description="Producción automática del canal MARCIUS3R")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("research", help="investigar noticias/tendencias y actualizar ideas")
    p = sub.add_parser("produce", help="crear y montar un vídeo")
    p.add_argument("--format", choices=["short", "long"], default="short")
    p.add_argument("--idea", type=int)
    p.add_argument("--template", action="store_true", help="guion sin IA (plantilla con hechos verificados)")
    p.add_argument("--script", help="usar un guion JSON ya escrito (p.ej. samples/sample_01_leonida.json)")
    p.add_argument("--allow-test-scenes", action="store_true", help="usar escenas procedurales de PRUEBA (nunca publicables)")
    p = sub.add_parser("resume", help="continuar un vídeo (p.ej. tras recibir los clips)")
    p.add_argument("id", type=int)
    p.add_argument("--allow-test-scenes", action="store_true")
    p = sub.add_parser("approve", help="aprobar un vídeo 'ready'")
    p.add_argument("id", type=int)
    p = sub.add_parser("publish", help="subir y programar un vídeo aprobado")
    p.add_argument("id", type=int)
    p.add_argument("--now", action="store_true")
    sub.add_parser("daily", help="ciclo diario completo (lo que ejecuta cron/systemd)")
    sub.add_parser("analytics", help="actualizar métricas y aprender")
    sub.add_parser("auth", help="conectar el canal de YouTube (OAuth)")
    sub.add_parser("channel", help="comprobar la conexión con el canal")
    sub.add_parser("pause", help="detener la automatización")
    sub.add_parser("unpause", help="reanudar la automatización")
    sub.add_parser("status", help="resumen en texto")
    p = sub.add_parser("voice-design", help="crear voces candidatas originales (Qwen3 VoiceDesign)")
    p.add_argument("--kaggle", action="store_true", help="usar la GPU gratuita de Kaggle")
    p = sub.add_parser("voice-pick", help="fijar la candidata N como voz del canal")
    p.add_argument("n", type=int)
    p = sub.add_parser("recap-transcribe", help="transcribir un directo (encargo del streamer)")
    p.add_argument("video")
    p.add_argument("--model", default="medium")
    p = sub.add_parser("recap-render", help="renderizar resumen de directo desde edl.json")
    p.add_argument("video")
    p.add_argument("edl")
    p.add_argument("--vertical", action="store_true")
    p.add_argument("--music")
    p = sub.add_parser("dashboard", help="panel web local")
    p.add_argument("--port", type=int, default=8787)
    p = sub.add_parser("ideas", help="listar ideas")
    p.add_argument("-n", type=int, default=20)
    a = ap.parse_args(argv)

    from . import pipeline
    if a.cmd == "research":
        from .research import run_research
        print(json.dumps(run_research(), ensure_ascii=False, indent=2))
    elif a.cmd == "produce":
        vid = pipeline.create(a.format, a.idea, template=a.template, script_path=a.script)
        print(f"vídeo {vid}: {pipeline.advance(vid, allow_test=a.allow_test_scenes)}")
        print(pipeline.get_video(vid)["workdir"])
    elif a.cmd == "resume":
        print(pipeline.advance(a.id, allow_test=a.allow_test_scenes))
    elif a.cmd == "approve":
        pipeline.approve(a.id)
        print("aprobado")
    elif a.cmd == "publish":
        print(pipeline.publish(a.id, publish_now=a.now))
    elif a.cmd == "daily":
        print(json.dumps(pipeline.daily(), ensure_ascii=False, indent=2, default=str))
    elif a.cmd == "analytics":
        from .scheduler import learn
        print(pipeline.update_analytics(), learn())
    elif a.cmd == "auth":
        from .youtube import authorize, channel_info
        authorize()
        print(channel_info())
    elif a.cmd == "channel":
        from .youtube import channel_info
        print(channel_info())
    elif a.cmd == "pause":
        core.pause("cli")
        print("automatización DETENIDA")
    elif a.cmd == "unpause":
        core.resume()
        print("automatización ACTIVA")
    elif a.cmd == "status":
        with core.db() as con:
            for r in con.execute("SELECT id,format,status,title,publish_at,youtube_id,cost_credits FROM videos ORDER BY id DESC LIMIT 20"):
                print(dict(r))
        print("pausada" if core.is_stopped() else "activa", "| créditos mes:", pipeline.credits_this_month())
    elif a.cmd in ("voice-design", "voice-pick"):
        from . import voice as vmod
        cand = core.ROOT / "library" / "voice" / "candidatas"
        if a.cmd == "voice-design":
            for pth in vmod.design_candidates(core.load_settings(), cand, remote=a.kaggle):
                print("candidata:", pth)
            print("Escúchalas y ejecuta: python -m marcius3r voice-pick <N>")
        else:
            print("voz del canal fijada:", vmod.pick_candidate(a.n, core.load_settings(), cand))
    elif a.cmd == "recap-transcribe":
        from pathlib import Path
        from .stream_recap import transcribe
        v = Path(a.video)
        print(transcribe(v, v.with_suffix(".transcript.json"), a.model))
    elif a.cmd == "recap-render":
        from pathlib import Path
        from .stream_recap import render
        v, e = Path(a.video), Path(a.edl)
        out = render(v, json.loads(e.read_text(encoding="utf-8")), e.parent / "render", core.load_settings(),
                     vertical=a.vertical, music=Path(a.music) if a.music else None, base=e.parent)
        print(out)
    elif a.cmd == "dashboard":
        from .dashboard import serve
        serve(a.port)
    elif a.cmd == "ideas":
        with core.db() as con:
            for r in con.execute("SELECT id,category,tier,score,status,title FROM ideas ORDER BY status, score DESC LIMIT ?", (a.n,)):
                print(dict(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
