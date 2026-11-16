"""Configuración, rutas, secretos, base de datos e interruptor de parada."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = Path(os.environ.get("MARCIUS3R_SECRETS", Path.home() / ".marcius3r"))
DATA_DIR = Path(os.environ.get("MARCIUS3R_DATA", ROOT / "workspace"))
DB_PATH = DATA_DIR / "marcius3r.db"
STOP_FILE = DATA_DIR / "STOP"


def load_settings(path: Path | None = None) -> dict:
    with open(path or ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_yaml(rel: str) -> dict:
    with open(ROOT / rel, encoding="utf-8") as f:
        return yaml.safe_load(f)


def tz(settings: dict) -> ZoneInfo:
    return ZoneInfo(settings["channel"]["timezone"])


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_secrets() -> dict[str, str]:
    """Lee ~/.marcius3r/secrets.env (KEY=VALUE). Exige permisos 600."""
    out: dict[str, str] = {}
    f = SECRETS_DIR / "secrets.env"
    if f.exists():
        mode = f.stat().st_mode & 0o777
        if mode & 0o077:
            raise PermissionError(f"{f} debe tener permisos 600 (tiene {oct(mode)}). Ejecuta: chmod 600 {f}")
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    for k in ("ANTHROPIC_API_KEY", "MUAPI_API_KEY", "ELEVENLABS_API_KEY", "VOICESTUDIO_API_KEY"):
        if os.environ.get(k):
            out[k] = os.environ[k]
    vs = SECRETS_DIR / "voicestudio.key"
    if "VOICESTUDIO_API_KEY" not in out and vs.exists():
        out["VOICESTUDIO_API_KEY"] = vs.read_text().strip()
    return out


# ---------------------------------------------------------------- base de datos
SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT, angle TEXT,
  needs TEXT, source_urls TEXT, tier TEXT, score REAL DEFAULT 0,
  status TEXT DEFAULT 'new', created_at TEXT, used_at TEXT
);
CREATE TABLE IF NOT EXISTS videos (
  id INTEGER PRIMARY KEY, idea_id INTEGER, format TEXT, title TEXT,
  status TEXT, script_json TEXT, workdir TEXT, output_path TEXT,
  thumbnail_path TEXT, metadata_json TEXT, qc_json TEXT, slot TEXT,
  publish_at TEXT, youtube_id TEXT, cost_credits REAL DEFAULT 0,
  cost_usd REAL DEFAULT 0, synthetic INTEGER DEFAULT 1,
  created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, video_id INTEGER, level TEXT, step TEXT,
  message TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS costs (
  id INTEGER PRIMARY KEY, video_id INTEGER, provider TEXT, item TEXT,
  credits REAL DEFAULT 0, usd REAL DEFAULT 0, created_at TEXT
);
CREATE TABLE IF NOT EXISTS analytics (
  id INTEGER PRIMARY KEY, video_id INTEGER, youtube_id TEXT, fetched_at TEXT,
  hours_since_publish REAL, views INTEGER, avg_view_pct REAL, avg_view_sec REAL,
  likes INTEGER, comments INTEGER, subs_gained INTEGER, ctr REAL
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


@contextmanager
def db(path: Path | None = None):
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def iso(dt: datetime | None = None) -> str:
    return (dt or now_utc()).isoformat(timespec="seconds")


def log_event(video_id: int | None, level: str, step: str, message: str) -> None:
    with db() as con:
        con.execute("INSERT INTO events(video_id,level,step,message,created_at) VALUES(?,?,?,?,?)",
                    (video_id, level, step, message[:4000], iso()))
    print(f"[{level}] {step}: {message[:300]}")


def add_cost(video_id: int | None, provider: str, item: str, credits: float = 0, usd: float = 0) -> None:
    with db() as con:
        con.execute("INSERT INTO costs(video_id,provider,item,credits,usd,created_at) VALUES(?,?,?,?,?,?)",
                    (video_id, provider, item, credits, usd, iso()))
        if video_id:
            con.execute("UPDATE videos SET cost_credits=cost_credits+?, cost_usd=cost_usd+? WHERE id=?",
                        (credits, usd, video_id))


def kv_get(k: str, default: Any = None) -> Any:
    with db() as con:
        r = con.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(r["v"]) if r else default


def kv_set(k: str, v: Any) -> None:
    with db() as con:
        con.execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)", (k, json.dumps(v)))


# ---------------------------------------------------------------- parada
def is_stopped() -> bool:
    return STOP_FILE.exists() or bool(kv_get("paused", False))


def pause(reason: str = "manual") -> None:
    kv_set("paused", True)
    STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOP_FILE.write_text(f"{iso()} {reason}\n")


def resume() -> None:
    kv_set("paused", False)
    STOP_FILE.unlink(missing_ok=True)


class StepError(RuntimeError):
    """Fallo de un paso: se registra y bloquea la publicación del vídeo."""


def retry(fn, attempts: int = 3, delay: float = 5.0, step: str = "", video_id: int | None = None):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - registramos y reintentamos
            last = e
            log_event(video_id, "warn", step, f"intento {i+1}/{attempts} falló: {e!r}")
            time.sleep(delay * (2 ** i))
    log_event(video_id, "error", step, "".join(traceback.format_exception(last))[-3000:])
    raise StepError(f"{step}: {last}") from last
