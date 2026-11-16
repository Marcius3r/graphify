"""Panel de control local (solo 127.0.0.1). Sin dependencias: http.server + SQLite.

Muestra: generados, pendientes, publicados, próximas publicaciones, errores, coste,
visualizaciones, rendimiento por franja/categoría, ideas futuras. Botones: pausar,
reanudar, aprobar, publicar ya.
"""
from __future__ import annotations

import html
import json
import secrets as pysecrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from .core import SECRETS_DIR, db, is_stopped, kv_get, pause, resume
from .pipeline import approve, credits_this_month

CSS = """
:root{--bg:#05040a;--card:#110d1c;--line:#2a2140;--fg:#f4f2ff;--mut:#a39cbf;--pur:#b026ff;--blu:#00b3ff;--red:#ff4d6d;--ok:#22d39b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
header{display:flex;gap:16px;align-items:center;justify-content:space-between;padding:18px 24px;border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{margin:0;font-size:22px;letter-spacing:.06em}h1 b{color:var(--pur)}h2{font-size:15px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em;margin:0 0 10px}
main{padding:20px 24px;display:grid;gap:18px;max-width:1300px;margin:auto}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.k{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}.k .v{font-size:26px;font-weight:800}.k .l{color:var(--mut);font-size:12px}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px}td,th{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600}.pill{padding:2px 8px;border-radius:99px;font-size:12px;font-weight:700;background:#2a2140}
.ready,.approved{background:#0f3d2e;color:var(--ok)}.scheduled,.published{background:#0a2c40;color:var(--blu)}
.failed,.qc_failed{background:#40101c;color:var(--red)}.scenes_pending{background:#33204a;color:#d9a6ff}
button{background:var(--pur);color:#fff;border:0;border-radius:8px;padding:8px 14px;font-weight:700;cursor:pointer}
button.alt{background:transparent;border:1px solid var(--blu);color:var(--blu)}button.stop{background:var(--red)}
.state{font-weight:800}.on{color:var(--ok)}.off{color:var(--red)}form{display:inline}
@media(max-width:600px){header,main{padding:14px 16px}}
"""


def _rows(sql: str, args=()) -> list[dict]:
    with db() as con:
        return [dict(r) for r in con.execute(sql, args)]


def _pill(s: str) -> str:
    return f'<span class="pill {html.escape(s)}">{html.escape(s)}</span>'


def render_page(token: str) -> str:
    vids = _rows("""SELECT v.*, (SELECT views FROM analytics a WHERE a.video_id=v.id ORDER BY id DESC LIMIT 1) views,
                    (SELECT avg_view_pct FROM analytics a WHERE a.video_id=v.id ORDER BY id DESC LIMIT 1) pct
                    FROM videos v ORDER BY v.id DESC LIMIT 60""")
    errors = _rows("SELECT * FROM events WHERE level IN ('error','warn') ORDER BY id DESC LIMIT 25")
    ideas = _rows("SELECT * FROM ideas WHERE status='new' ORDER BY score DESC LIMIT 15")
    slots = _rows("""SELECT v.slot, COUNT(*) n, ROUND(AVG(a.views)) views, ROUND(AVG(a.avg_view_pct),1) pct
                     FROM videos v JOIN analytics a ON a.video_id=v.id WHERE v.slot IS NOT NULL GROUP BY v.slot""")
    cats = kv_get("category_weights", {})
    count = lambda *s: sum(1 for v in vids if v["status"] in s)  # noqa: E731
    total_views = sum(v["views"] or 0 for v in vids)
    paused = is_stopped()
    t = html.escape(token)

    def vrow(v):
        acts = ""
        if v["status"] == "ready":
            acts = f'<form method=post action="/approve"><input type=hidden name=t value="{t}"><input type=hidden name=id value="{v["id"]}"><button>Aprobar</button></form>'
        qc = json.loads(v["qc_json"] or "{}")
        issues = "<br>".join(html.escape(b) for b in qc.get("blockers", [])[:3])
        yt = f'<a href="https://youtu.be/{v["youtube_id"]}" style="color:var(--blu)">{v["youtube_id"]}</a>' if v["youtube_id"] else ""
        return (f"<tr><td>{v['id']}</td><td>{html.escape(v['format'] or '')}</td><td>{html.escape(v['title'] or '')}"
                f"<br><small style='color:var(--red)'>{issues}</small></td><td>{_pill(v['status'])}</td>"
                f"<td>{html.escape((v['publish_at'] or '')[:16])} {html.escape(v['slot'] or '')}</td><td>{yt}</td>"
                f"<td>{v['views'] if v['views'] is not None else '–'}</td><td>{v['pct'] or '–'}</td>"
                f"<td>{v['cost_credits']:.1f} cr / ${v['cost_usd']:.2f}</td><td>{acts}</td></tr>")

    btn = (f'<form method=post action="/resume"><input type=hidden name=t value="{t}"><button class=alt>Reanudar automatización</button></form>'
           if paused else
           f'<form method=post action="/pause"><input type=hidden name=t value="{t}"><button class=stop>Detener automatización</button></form>')
    return f"""<!doctype html><html lang=es><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>MARCIUS3R · Control</title><style>{CSS}</style></head><body>
<header><h1>MARCIUS<b>3</b>R · Control</h1><div>Estado: <span class="state {'off' if paused else 'on'}">{'EN PAUSA' if paused else 'ACTIVA'}</span> {btn}</div></header>
<main>
<div class=kpis>
 <div class=k><div class=v>{len(vids)}</div><div class=l>Vídeos generados</div></div>
 <div class=k><div class=v>{count('ready','scenes_pending','approved','qc_failed')}</div><div class=l>Pendientes</div></div>
 <div class=k><div class=v>{count('scheduled')}</div><div class=l>Programados</div></div>
 <div class=k><div class=v>{count('published')}</div><div class=l>Publicados</div></div>
 <div class=k><div class=v>{total_views:,}</div><div class=l>Visualizaciones</div></div>
 <div class=k><div class=v>{credits_this_month():.0f}</div><div class=l>Créditos este mes</div></div>
 <div class=k><div class=v>{count('failed','qc_failed')}</div><div class=l>Con errores</div></div>
</div>
<section><h2>Vídeos</h2><table><tr><th>#</th><th>Fmt</th><th>Título</th><th>Estado</th><th>Publicación</th><th>YouTube</th><th>Vistas</th><th>% visto</th><th>Coste</th><th></th></tr>
{''.join(vrow(v) for v in vids) or '<tr><td colspan=10>Todavía no hay vídeos.</td></tr>'}</table></section>
<section><h2>Rendimiento por franja (hora Madrid)</h2><table><tr><th>Franja</th><th>Vídeos</th><th>Vistas medias</th><th>% medio visto</th></tr>
{''.join(f"<tr><td>{s['slot']}</td><td>{s['n']}</td><td>{s['views']}</td><td>{s['pct']}</td></tr>" for s in slots) or '<tr><td colspan=4>Sin datos aún (se necesitan ~48 h por vídeo).</td></tr>'}</table>
<p style="color:var(--mut)">Pesos por categoría aprendidos: {html.escape(json.dumps(cats) if cats else 'aún sin datos')}</p></section>
<section><h2>Ideas futuras</h2><table><tr><th>Cat.</th><th>Idea</th><th>Fuente</th><th>Puntuación</th></tr>
{''.join(f"<tr><td>{i['category']}</td><td>{html.escape(i['title'])}</td><td>{i['tier']}</td><td>{i['score']:.1f}</td></tr>" for i in ideas)}</table></section>
<section><h2>Errores y avisos recientes</h2><table><tr><th>Fecha</th><th>Vídeo</th><th>Paso</th><th>Mensaje</th></tr>
{''.join(f"<tr><td>{e['created_at'][:16]}</td><td>{e['video_id'] or ''}</td><td>{e['step']}</td><td>{html.escape(e['message'][:300])}</td></tr>" for e in errors) or '<tr><td colspan=4>Sin errores.</td></tr>'}</table></section>
</main></body></html>"""


def _token() -> str:
    p = SECRETS_DIR / "dashboard.token"
    if not p.exists():
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(pysecrets.token_urlsafe(24))
        p.chmod(0o600)
    return p.read_text().strip()


class Handler(BaseHTTPRequestHandler):
    token = ""

    def _send(self, code: int, body: str, ctype: str = "text/html; charset=utf-8") -> None:
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/state"):
            return self._send(200, json.dumps({"paused": is_stopped(), "credits_month": credits_this_month()}), "application/json")
        self._send(200, render_page(self.token))

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}
        if form.get("t") != self.token:
            return self._send(403, "token inválido")
        try:
            if self.path == "/pause":
                pause("panel")
            elif self.path == "/resume":
                resume()
            elif self.path == "/approve":
                approve(int(form["id"]))
        except Exception as e:  # noqa: BLE001
            return self._send(400, html.escape(str(e)))
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, *a):  # silencio
        pass


def serve(port: int = 8787) -> None:
    Handler.token = _token()
    print(f"Panel en http://127.0.0.1:{port}  (Ctrl+C para salir)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def export_static(out: Path) -> Path:
    out.write_text(render_page("solo-lectura"), encoding="utf-8")
    return out
