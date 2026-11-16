"""Horarios de publicación (Europe/Madrid) y aprendizaje (PASO 12).

- Franjas de prueba A/B/C rotadas hasta tener min_samples_per_slot vídeos en cada una.
- Después: epsilon-greedy — la mejor franja la mayor parte del tiempo, y exploración.
- Recompensa = visualizaciones a 48 h × (1 + % medio visto) normalizada por la mediana.
- Pesos de categoría (A-F) = rendimiento relativo de cada tipo de tema.
"""
from __future__ import annotations

import random
import statistics
from datetime import datetime, timedelta

from .core import db, kv_set, load_settings, now_utc, tz


def _reward(row) -> float:
    return (row["views"] or 0) * (1 + (row["avg_view_pct"] or 0) / 100)


def slot_stats() -> dict[str, list[float]]:
    stats: dict[str, list[float]] = {}
    with db() as con:
        rows = con.execute("""SELECT v.slot, a.views, a.avg_view_pct FROM videos v JOIN analytics a ON a.video_id=v.id
                              WHERE a.hours_since_publish BETWEEN 40 AND 80 AND v.slot IS NOT NULL""").fetchall()
    for r in rows:
        stats.setdefault(r["slot"], []).append(_reward(r))
    return stats


def choose_slot(settings: dict | None = None, rnd: random.Random | None = None) -> str:
    settings = settings or load_settings()
    rnd = rnd or random.Random()
    slots = list(settings["schedule"]["slots"])
    stats = slot_stats()
    need = settings["schedule"]["min_samples_per_slot"]
    under = [s for s in slots if len(stats.get(s, [])) < need]
    if under:  # fase de prueba: rotación equilibrada
        with db() as con:
            counts = {s: con.execute("SELECT COUNT(*) c FROM videos WHERE slot=?", (s,)).fetchone()["c"] for s in under}
        return min(under, key=lambda s: (counts[s], s))
    if rnd.random() < settings["schedule"]["exploration_rate"]:
        return rnd.choice(slots)
    return max(slots, key=lambda s: statistics.median(stats[s]))


def next_publish_time(slot: str, settings: dict | None = None, after: datetime | None = None) -> datetime:
    """Próxima hora de la franja, ≥2 h desde ahora, en un día sin otro Short programado."""
    settings = settings or load_settings()
    zone = tz(settings)
    hh, mm = map(int, settings["schedule"]["slots"][slot].split(":"))
    base = (after or now_utc()).astimezone(zone) + timedelta(hours=2)
    with db() as con:
        taken = {r["publish_at"][:10] for r in con.execute(
            "SELECT publish_at FROM videos WHERE publish_at IS NOT NULL AND format='short' AND status IN ('scheduled','published')")}
    day = base.date()
    for _ in range(30):
        cand = datetime(day.year, day.month, day.day, hh, mm, tzinfo=zone)
        if cand >= base and cand.date().isoformat() not in taken:
            return cand
        day += timedelta(days=1)
    raise RuntimeError("sin hueco en 30 días")


def learn() -> dict:
    """Recalcula pesos de categoría a partir de Analytics (≥48 h)."""
    with db() as con:
        rows = con.execute("""SELECT i.category, a.views, a.avg_view_pct FROM videos v
                              JOIN ideas i ON i.id=v.idea_id JOIN analytics a ON a.video_id=v.id
                              WHERE a.hours_since_publish BETWEEN 40 AND 80""").fetchall()
    if len(rows) < 6:
        return {"status": "pocos datos", "samples": len(rows)}
    by: dict[str, list[float]] = {}
    for r in rows:
        by.setdefault(r["category"] or "C", []).append(_reward(r))
    med = statistics.median([x for v in by.values() for x in v]) or 1
    weights = {c: 1.0 for c in "ABCDEF"}
    for c, vals in by.items():
        # suavizado bayesiano hacia 1.0 con pocas muestras
        n = len(vals)
        rel = statistics.median(vals) / med
        weights[c] = round((rel * n + 1.0 * 3) / (n + 3), 3)
    kv_set("category_weights", weights)
    return {"status": "ok", "weights": weights, "slots": {k: len(v) for k, v in slot_stats().items()}}
