"""PASO 1-3: investigar, seleccionar y verificar.

- Lee feeds (Google News, Newswire de Rockstar, Reddit) y los clasifica:
  oficial / prensa / comunidad / rumor.
- Convierte titulares en ideas con categoría A-F y puntuación.
- Evita repetir temas (similitud de tokens contra todo el historial).
- La selección pondera categorías según el rendimiento real (Analytics).
"""
from __future__ import annotations

import html
import json
import math
import re
import unicodedata
from datetime import timedelta
from email.utils import parsedate_to_datetime

import requests

from .core import db, iso, kv_get, load_settings, load_yaml, log_event, now_utc

UA = "marcius3r-research/1.0 (+contenido propio; sin scraping masivo)"
STOP = set("de la el los las un una y o en a que por para con del al se su sus es lo como mas más gta 6 vi grand theft auto the of to in and for on is with".split())

CATEGORY_RULES = [
    ("E", r"rockstar|tr[aá]iler|anuncia|announce|official|oficial|fecha|release|precio|price|parche|patch|update|reserva|pre-?order"),
    ("D", r"\bvs\b|versus|compar|gta 5|gta v\b|diferencia"),
    ("B", r"no (se )?puede|can.?t|cannot|limit|mito|myth|no habr[aá]|missing|falta|no tendr"),
    ("C", r"secret|easter|detalle|detail|referenc|teor[ií]a|theory|oculto|hidden|curios"),
    ("A", r"puedes|can you|actividad|activity|veh[ií]cul|car|animal|explor|personaliz|f[ií]sica|physics|npc|mundo abierto|open world"),
]


def norm_tokens(text: str) -> set[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", t) if w not in STOP and len(w) > 2}


def similarity(a: str, b: str) -> float:
    ta, tb = norm_tokens(a), norm_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def classify_tier(title: str, link: str, default: str, settings: dict) -> str:
    low = f"{title} {link}".lower()
    if any(d in low for d in settings["research"]["official_domains"]):
        return "oficial"
    if any(m in low for m in settings["research"]["rumor_markers"]):
        return "rumor"
    return default


def guess_category(title: str) -> str:
    low = title.lower()
    for cat, pat in CATEGORY_RULES:
        if re.search(pat, low):
            return cat
    return "C"


# ---------------------------------------------------------------- fetchers
def _get(url: str, timeout: int = 20) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r


def fetch_rss(feed: dict) -> list[dict]:
    import feedparser
    parsed = feedparser.parse(_get(feed["url"]).content)
    items = []
    for e in parsed.entries:
        pub = None
        if getattr(e, "published", None):
            try:
                pub = parsedate_to_datetime(e.published)
            except (TypeError, ValueError):
                pub = None
        items.append({"title": html.unescape(e.title), "link": e.link, "published": pub,
                      "source": feed["name"], "tier": feed.get("tier", "prensa")})
    return items


def fetch_reddit(feed: dict) -> list[dict]:
    data = _get(feed["url"]).json()
    out = []
    for c in data.get("data", {}).get("children", []):
        d = c["data"]
        out.append({"title": d["title"], "link": "https://www.reddit.com" + d["permalink"],
                    "published": None, "source": feed["name"], "tier": "comunidad",
                    "engagement": d.get("score", 0) + 3 * d.get("num_comments", 0),
                    "flair": d.get("link_flair_text") or ""})
    return out


def fetch_newswire(feed: dict) -> list[dict]:
    page = _get(feed["url"]).text
    titles = re.findall(r'"title":"([^"]{12,160})"', page)[:20]
    return [{"title": html.unescape(t), "link": feed["url"], "published": None,
             "source": feed["name"], "tier": "oficial"} for t in dict.fromkeys(titles) if "GTA" in t or "Grand Theft" in t]


def run_research(settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    found, errors = [], []
    for feed in settings["research"]["feeds"]:
        kind = feed.get("kind", "rss")
        try:
            items = {"rss": fetch_rss, "reddit": fetch_reddit, "html": fetch_newswire}[kind](feed)
            found.extend(items)
        except Exception as e:  # noqa: BLE001 - un feed caído no para la investigación
            errors.append(f"{feed['name']}: {e}")
            log_event(None, "warn", "research", f"feed {feed['name']} no disponible: {e}")
    added = ingest_items(found, settings)
    seeded = seed_idea_bank()
    return {"fetched": len(found), "new_ideas": added, "seeded": seeded, "errors": errors}


def ingest_items(items: list[dict], settings: dict) -> int:
    max_age = timedelta(hours=settings["research"]["max_age_hours"])
    added = 0
    with db() as con:
        existing = [r["title"] for r in con.execute("SELECT title FROM ideas")]
        for it in items:
            if it.get("published") and now_utc() - it["published"] > max_age:
                continue
            title = re.sub(r"\s+-\s+[^-]+$", "", it["title"]).strip()  # quita " - Medio"
            if any(similarity(title, t) > 0.55 for t in existing):
                continue
            tier = classify_tier(title, it["link"], it["tier"], settings)
            if tier == "rumor" and re.search(r"leak|filtra", title.lower()):
                continue  # política: no producimos sobre material filtrado
            score = {"oficial": 3.0, "prensa": 2.0, "comunidad": 1.2, "rumor": 0.6}[tier]
            score += math.log1p(it.get("engagement", 0)) / 3
            con.execute(
                "INSERT INTO ideas(title,category,angle,needs,source_urls,tier,score,status,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (title, guess_category(title), "", "[]", json.dumps([it["link"]]), tier, score, "new", iso()))
            existing.append(title)
            added += 1
    return added


def seed_idea_bank() -> int:
    bank = load_yaml("data/idea_bank.yaml")["ideas"]
    n = 0
    with db() as con:
        existing = [r["title"] for r in con.execute("SELECT title FROM ideas")]
        for i in bank:
            if any(similarity(i["title"], t) > 0.7 for t in existing):
                continue
            con.execute(
                "INSERT INTO ideas(title,category,angle,needs,source_urls,tier,score,status,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (i["title"], i["category"], i.get("angle", ""), json.dumps(i.get("needs", [])), "[]",
                 "oficial", 2.5 if i.get("evergreen") else 3.0, "new", iso()))
            n += 1
    return n


# ---------------------------------------------------------------- selección
def category_weights() -> dict[str, float]:
    """Peso por categoría = rendimiento medio relativo (aprendido de Analytics)."""
    w = kv_get("category_weights", None)
    return w or {c: 1.0 for c in "ABCDEF"}


def pick_idea(fmt: str = "short") -> dict | None:
    weights = category_weights()
    with db() as con:
        used = [r["title"] for r in con.execute("SELECT title FROM videos")]
        recent_cats = [r["category"] for r in con.execute(
            "SELECT i.category FROM videos v JOIN ideas i ON i.id=v.idea_id ORDER BY v.id DESC LIMIT 3")]
        rows = [dict(r) for r in con.execute("SELECT * FROM ideas WHERE status='new'")]
    best, best_score = None, -1e9
    for r in rows:
        if any(similarity(r["title"], u) > 0.45 for u in used):
            continue
        s = r["score"] * weights.get(r["category"] or "C", 1.0)
        s -= 0.8 * recent_cats.count(r["category"])  # variedad: no repetir categoría
        if r["tier"] == "rumor":
            s -= 1.0
        if s > best_score:
            best, best_score = r, s
    return best


def mark_idea(idea_id: int, status: str) -> None:
    with db() as con:
        con.execute("UPDATE ideas SET status=?, used_at=? WHERE id=?", (status, iso(), idea_id))


def verified_facts(needed: list[str] | None = None) -> list[dict]:
    facts = load_yaml("data/facts.yaml")["facts"]
    if needed:
        prio = [f for f in facts if f["id"] in needed]
        rest = [f for f in facts if f["id"] not in needed]
        return prio + rest
    return facts
