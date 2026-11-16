"""PASOS 10-11: publicación y analítica con las APIs OFICIALES de YouTube (OAuth 2.0).

Credenciales:
- ~/.marcius3r/client_secret.json  (OAuth "Aplicación de escritorio" de tu proyecto Google Cloud)
- ~/.marcius3r/youtube_token.json  (se crea con `marcius3r auth`, permisos 600)
Nunca se usan contraseñas.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from .core import SECRETS_DIR, StepError, log_event

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
TOKEN = SECRETS_DIR / "youtube_token.json"
CLIENT = SECRETS_DIR / "client_secret.json"


def authorize(port: int = 8765) -> None:
    """Abre (o imprime) la URL de consentimiento de Google y guarda el token."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not CLIENT.exists():
        raise StepError(f"Falta {CLIENT}. Descárgalo de Google Cloud Console → Credenciales → ID de cliente OAuth (escritorio).")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
    creds = flow.run_local_server(host="localhost", port=port, open_browser=False,
                                  authorization_prompt_message="Abre esta URL en tu navegador y autoriza el canal MARCIUS3R:\n{url}\n",
                                  success_message="Autorizado. Ya puedes cerrar esta pestaña.")
    _save(creds)
    log_event(None, "info", "auth", "token de YouTube guardado")


def _save(creds) -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    TOKEN.write_text(creds.to_json())
    os.chmod(TOKEN, 0o600)


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not TOKEN.exists():
        raise StepError("No hay token de YouTube. Ejecuta: marcius3r auth")
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        _save(creds)
    return creds


def service(name: str = "youtube", version: str = "v3"):
    from googleapiclient.discovery import build
    return build(name, version, credentials=_creds(), cache_discovery=False)


def channel_info() -> dict:
    r = service().channels().list(part="snippet,statistics,status", mine=True).execute()
    if not r.get("items"):
        raise StepError("La cuenta autorizada no tiene canal de YouTube")
    it = r["items"][0]
    return {"id": it["id"], "title": it["snippet"]["title"], "subscribers": it["statistics"].get("subscriberCount"),
            "long_uploads": it["status"].get("longUploadsStatus")}


def upload(video: Path, meta: dict, publish_at: datetime | None, thumbnail: Path | None,
           video_id: int | None = None) -> str:
    from googleapiclient.http import MediaFileUpload
    yt = service()
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": bool(meta.get("contains_synthetic_media"))}
    if publish_at:
        status["publishAt"] = publish_at.astimezone().isoformat()
    body = {"snippet": {"title": meta["title"], "description": meta["description"], "tags": meta["tags"],
                        "categoryId": meta.get("category_id", "20"), "defaultLanguage": meta.get("default_language", "es"),
                        "defaultAudioLanguage": meta.get("default_audio_language", "es-ES")},
            "status": status}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True,
                                                        mimetype="video/mp4"))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    yid = resp["id"]
    log_event(video_id, "info", "publish", f"subido {yid} (estado {resp['status'].get('uploadStatus')}, "
                                           f"publishAt {status.get('publishAt')})")
    if thumbnail and thumbnail.exists():
        try:
            yt.thumbnails().set(videoId=yid, media_body=MediaFileUpload(str(thumbnail), mimetype="image/jpeg")).execute()
        except Exception as e:  # noqa: BLE001 - el canal puede no estar verificado para miniaturas
            log_event(video_id, "warn", "thumbnail", f"no se pudo poner la miniatura (¿canal verificado?): {e}")
    return yid


def video_status(yid: str) -> dict:
    r = service().videos().list(part="status,statistics", id=yid).execute()
    return r["items"][0] if r.get("items") else {}


def fetch_analytics(yid: str, published: datetime) -> dict:
    """Métricas por vídeo. Nota: el CTR de impresiones NO está disponible en la API pública."""
    ya = service("youtubeAnalytics", "v2")
    start = published.date().isoformat()
    end = (datetime.utcnow().date() + timedelta(days=1)).isoformat()
    r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end,
                           metrics="views,averageViewPercentage,averageViewDuration,likes,comments,subscribersGained",
                           dimensions="video", filters=f"video=={yid}").execute()
    row = (r.get("rows") or [[yid, 0, 0, 0, 0, 0, 0]])[0]
    keys = ["video", "views", "avg_view_pct", "avg_view_sec", "likes", "comments", "subs_gained"]
    out = dict(zip(keys, row))
    if not out.get("views"):  # Analytics tarda ~48 h; usamos estadísticas públicas mientras tanto
        st = video_status(yid).get("statistics", {})
        out.update(views=int(st.get("viewCount", 0)), likes=int(st.get("likeCount", 0)),
                   comments=int(st.get("commentCount", 0)))
    return out


def save_json(p: Path, data: dict) -> None:
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
