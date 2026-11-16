"""Cadena completa: investigar → seleccionar → verificar → guion → voz → escenas → montaje
→ QC → miniatura → metadatos → (aprobación) → programar → analizar → mejorar.

Estados de un vídeo:
  scripted → voiced → scenes_pending (esperando clips del agente) → rendered
  → qc_failed | ready → approved → scheduled → published   (o failed)
Nada se sube a YouTube si el QC tiene un solo bloqueo.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from . import editor, qc, scenes, scheduler, thumbnail, voice
from .core import (DATA_DIR, StepError, add_cost, db, is_stopped, iso, kv_get, load_settings, log_event, now_utc)
from .metadata import build_metadata
from .research import mark_idea, pick_idea, run_research
from .script_writer import write_script, write_template


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower())[:40].strip("-")


def _update(vid: int, **kw) -> None:
    kw["updated_at"] = iso()
    sets = ", ".join(f"{k}=?" for k in kw)
    with db() as con:
        con.execute(f"UPDATE videos SET {sets} WHERE id=?", (*kw.values(), vid))


def get_video(vid: int) -> dict:
    with db() as con:
        r = con.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    if not r:
        raise StepError(f"vídeo {vid} no existe")
    return dict(r)


def credits_this_month() -> float:
    month = now_utc().strftime("%Y-%m")
    with db() as con:
        r = con.execute("SELECT COALESCE(SUM(credits),0) c FROM costs WHERE substr(created_at,1,7)=?", (month,)).fetchone()
    return float(r["c"])


# ---------------------------------------------------------------- producción
def create(fmt: str = "short", idea_id: int | None = None, template: bool = False, settings: dict | None = None) -> int:
    settings = settings or load_settings()
    if idea_id:
        with db() as con:
            idea = dict(con.execute("SELECT * FROM ideas WHERE id=?", (idea_id,)).fetchone())
    else:
        idea = pick_idea(fmt)
    if not idea:
        raise StepError("no hay ideas nuevas: ejecuta `marcius3r research`")
    with db() as con:
        cur = con.execute("INSERT INTO videos(idea_id,format,title,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                          (idea["id"], fmt, idea["title"], "planned", iso(), iso()))
        vid = cur.lastrowid
    workdir = DATA_DIR / "videos" / f"{vid:04d}-{slugify(idea['title'])}"
    workdir.mkdir(parents=True, exist_ok=True)
    _update(vid, workdir=str(workdir))
    mark_idea(idea["id"], "in_production")
    log_event(vid, "info", "select", f"idea #{idea['id']} [{idea['category']}/{idea['tier']}]: {idea['title']}")
    try:
        script = write_template(idea, fmt, settings) if template else write_script(idea, fmt, settings)
    except Exception as e:
        _update(vid, status="failed")
        mark_idea(idea["id"], "new")
        log_event(vid, "error", "script", str(e))
        raise
    (workdir / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2))
    if "_usage" in script:
        u = script["_usage"]
        add_cost(vid, "anthropic", "guion", usd=u["input_tokens"] * 4e-6 + u["output_tokens"] * 20e-6)
    _update(vid, status="scripted", title=script["title"], script_json=json.dumps(script, ensure_ascii=False))
    return vid


def advance(vid: int, allow_test: bool = False, settings: dict | None = None) -> str:
    """Avanza un vídeo todo lo posible. Idempotente: se puede relanzar tras un fallo."""
    settings = settings or load_settings()
    v = get_video(vid)
    fmt, workdir = v["format"], Path(v["workdir"])
    script = json.loads(v["script_json"])
    try:
        if v["status"] in ("scripted", "voiced", "scenes_pending", "rendered", "qc_failed"):
            vo = voice.synthesize(script, workdir, settings, vid)
            (workdir / "voice.json").write_text(json.dumps(vo, indent=2))
            _update(vid, status="voiced")
            shots = scenes.plan_shots(script, vo, fmt, settings)
            scenes.write_manifest(shots, workdir, settings)
            try:
                clips = scenes.gather_clips(script, shots, workdir, fmt, settings, vid, allow_test=allow_test)
            except StepError as e:
                missing = [s["file"] for s in shots if not (workdir / s["file"]).exists()]
                if missing and "higgsfield_agent" in settings["providers"]["video"]["order"]:
                    _update(vid, status="scenes_pending")
                    log_event(vid, "info", "scenes", f"esperando {len(missing)} clips (manifest listo): {e}")
                    return "scenes_pending"
                raise
            info = editor.render(script, vo, clips, workdir, fmt, settings, vid)
            synthetic = any("IA" in l for l in info["labels"])
            frame = thumbnail.best_frame([c["path"] for c in clips], workdir)
            thumb = thumbnail.make_thumbnail(frame, script["thumbnail_text"], workdir / "thumbnail.jpg", settings, synthetic)
            meta = build_metadata(script, fmt, synthetic, settings)
            (workdir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
            report = qc.run_qc(Path(info["output"]), script, info, fmt, settings, meta, vid)
            (workdir / "qc.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            status = "ready" if report["passed"] else "qc_failed"
            _update(vid, status=status, output_path=info["output"], thumbnail_path=str(thumb),
                    metadata_json=json.dumps(meta, ensure_ascii=False), qc_json=json.dumps(report, ensure_ascii=False),
                    synthetic=int(synthetic))
            level = "info" if report["passed"] else "error"
            log_event(vid, level, "qc", "OK" if report["passed"] else "BLOQUEADO: " + "; ".join(report["blockers"]))
            return status
        return v["status"]
    except Exception as e:
        _update(vid, status="failed")
        log_event(vid, "error", "pipeline", f"{type(e).__name__}: {e}")
        raise


def approve(vid: int) -> None:
    v = get_video(vid)
    if v["status"] != "ready":
        raise StepError(f"solo se aprueban vídeos 'ready' (estado actual: {v['status']})")
    _update(vid, status="approved")
    log_event(vid, "info", "approval", "aprobado manualmente")


def publish(vid: int, settings: dict | None = None, publish_now: bool = False) -> str:
    from . import youtube
    settings = settings or load_settings()
    v = get_video(vid)
    allowed = ("approved",) if settings["production"]["require_manual_approval"] else ("approved", "ready")
    if v["status"] not in allowed:
        raise StepError(f"vídeo {vid} en estado {v['status']}: no publicable")
    report = json.loads(v["qc_json"] or "{}")
    if not report.get("passed"):
        raise StepError("QC no superado: no se publica")
    if is_stopped():
        raise StepError("automatización en pausa")
    slot = scheduler.choose_slot(settings)
    when = None if publish_now else scheduler.next_publish_time(slot, settings)
    meta = json.loads(v["metadata_json"])
    yid = youtube.upload(Path(v["output_path"]), meta, when, Path(v["thumbnail_path"]), vid)
    _update(vid, status="scheduled" if when else "published", youtube_id=yid, slot=slot if when else None,
            publish_at=when.isoformat() if when else iso())
    if v["idea_id"]:
        mark_idea(v["idea_id"], "used")
    return yid


# ---------------------------------------------------------------- analítica
def update_analytics() -> int:
    from . import youtube
    n = 0
    with db() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM videos WHERE youtube_id IS NOT NULL")]
    for v in rows:
        pub = datetime.fromisoformat(v["publish_at"])
        hours = (now_utc() - pub).total_seconds() / 3600
        if hours < 0:
            continue
        if v["status"] == "scheduled":
            _update(v["id"], status="published")
        try:
            a = youtube.fetch_analytics(v["youtube_id"], pub)
        except Exception as e:  # noqa: BLE001
            log_event(v["id"], "warn", "analytics", str(e))
            continue
        with db() as con:
            con.execute("""INSERT INTO analytics(video_id,youtube_id,fetched_at,hours_since_publish,views,avg_view_pct,
                           avg_view_sec,likes,comments,subs_gained,ctr) VALUES(?,?,?,?,?,?,?,?,?,?,NULL)""",
                        (v["id"], v["youtube_id"], iso(), hours, a.get("views"), a.get("avg_view_pct"),
                         a.get("avg_view_sec"), a.get("likes"), a.get("comments"), a.get("subs_gained")))
        n += 1
    return n


# ---------------------------------------------------------------- diario
def daily(settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    summary: dict = {"started": iso()}
    if is_stopped():
        log_event(None, "info", "daily", "en pausa: no se hace nada")
        return {"paused": True}
    budget = settings["production"]["monthly_budget_credits"]
    if credits_this_month() + settings["production"]["max_credits_per_short"] > budget:
        log_event(None, "error", "budget", f"presupuesto mensual agotado ({credits_this_month()}/{budget} créditos)")
        return {"budget_exhausted": True}
    # 0) reanudar vídeos pendientes (p.ej. clips que el agente ya entregó)
    with db() as con:
        pending = [r["id"] for r in con.execute("SELECT id FROM videos WHERE status IN ('scenes_pending','voiced','scripted')")]
    for vid in pending:
        try:
            advance(vid, settings=settings)
        except Exception:  # noqa: BLE001 - registrado en events
            pass
    # 1-3) investigación
    try:
        summary["research"] = run_research(settings)
    except Exception as e:  # noqa: BLE001
        log_event(None, "error", "research", str(e))
    # 4-9) producir el Short del día si no hay ya uno listo
    with db() as con:
        ready = con.execute("SELECT COUNT(*) c FROM videos WHERE format='short' AND status IN ('ready','approved','scenes_pending')").fetchone()["c"]
    if ready == 0:
        try:
            vid = create("short", settings=settings)
            summary["produced"] = {vid: advance(vid, settings=settings)}
        except Exception as e:  # noqa: BLE001
            summary["produce_error"] = str(e)
    # 10) publicar lo aprobado (o lo 'ready' si ya no se exige aprobación)
    states = ("approved",) if settings["production"]["require_manual_approval"] else ("approved", "ready")
    with db() as con:
        to_pub = [r["id"] for r in con.execute(
            f"SELECT id FROM videos WHERE status IN ({','.join('?'*len(states))}) ORDER BY id LIMIT 1", states)]
    for vid in to_pub:
        try:
            summary.setdefault("published", []).append(publish(vid, settings))
        except Exception as e:  # noqa: BLE001
            log_event(vid, "error", "publish", str(e))
    # 11-12) analizar y aprender
    try:
        summary["analytics_rows"] = update_analytics()
        summary["learn"] = scheduler.learn()
    except Exception as e:  # noqa: BLE001
        log_event(None, "warn", "analytics", str(e))
    log_event(None, "info", "daily", json.dumps(summary, ensure_ascii=False, default=str)[:1500])
    return summary


def cleanup(keep_days: int = 14) -> int:
    """Borra intermedios pesados (cortes) de vídeos ya publicados."""
    n = 0
    with db() as con:
        rows = con.execute("SELECT workdir FROM videos WHERE status='published'").fetchall()
    for r in rows:
        cuts = Path(r["workdir"]) / "cuts"
        if cuts.exists():
            shutil.rmtree(cuts)
            n += 1
    return n
