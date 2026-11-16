# Runbook del agente (Claude + Higgsfield)

Úsalo cuando las escenas o la voz se generan con **Higgsfield** a través del conector MCP de Claude, que no tiene API key propia en el pipeline. El pipeline deja el vídeo en `scenes_pending` con un `generation_manifest.json`. El agente genera los clips y el sistema continúa.

## Por vídeo

1. `python -m marcius3r produce` deja el vídeo en `scenes_pending` y escribe `workspace/videos/<id>/generation_manifest.json`.
2. Por cada toma del manifest, `mcp__Higgsfield__generate_video_batch` (máximo 12 por lote):
   `{"model": "seedance_2_0_mini", "prompt": <prompt>, "aspect_ratio": "9:16", "duration": 5, "resolution": "720p", "generate_audio": false}`.
   Antes, `get_cost: true` para comprobar que el total cabe en `max_credits_per_short`.
3. Espera con `jobs_wait` y descarga cada resultado a `workspace/videos/<id>/clips/beat_XX_K.mp4`.
4. Voz, si no hay VoiceStudio: `generate_audio_batch` con `seed_audio` (voz `Juan`, preset `6b528d43-c056-4a2f-9d82-1591a7ba13b0`, o la voz clonada del canal), una petición por frase. Guarda en `voice/beat_XX.wav`.
5. Música: `generate_audio` con `elevenlabs_music_v2` (instrumental, duración del vídeo + 3 s). Guarda en `music.mp3` y anótala en `library/music/licenses.yaml` si vas a reutilizarla.
6. `python -m marcius3r resume <id>` monta el vídeo, pasa el QC y lo deja en `ready`.

## Si el contenedor no puede descargar de los CDN de Higgsfield

Ejecuta el montaje dentro de `mcp__Higgsfield__sandbox_exec`. Ese sandbox tiene ffmpeg, Pillow, faster-whisper y las fuentes Montserrat.
1. Empaqueta el código: `tar czf - marcius3r config data samples | base64 -w0`. Descomprímelo en el sandbox.
2. Descarga los clips allí con `curl` desde las URLs de resultado.
3. Ejecuta el render con `MARCIUS3R_DATA=/home/user/work`.
4. Sube el `final_short.mp4` con `media_upload` y el PUT del propio comando.

## Tarea programada diaria (opcional)

Una tarea programada de Claude (sesión nueva cada día) puede ejecutar este runbook. Créala solo cuando la muestra esté aprobada. Necesita:
- El repositorio.
- El conector de Higgsfield.
- Red con acceso a Hugging Face, Google News, `www.googleapis.com` y `oauth2.googleapis.com`.

El token de YouTube debe estar en el entorno de forma segura. Por eso la opción recomendada es ejecutar `daily` en tu PC o VPS con MuAPI o VoiceStudio, y dejar al agente solo para las escenas de Higgsfield.
