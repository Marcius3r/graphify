# Investigación y decisiones de arquitectura (16-nov-2026)

## Entorno inspeccionado
- Contenedor en la nube: 4 CPU, 15 GB de RAM, **sin GPU**, FFmpeg 6.1 (libass, freetype, sidechaincompress, freezedetect), Docker 29 y Python 3.13.
- Red restringida: Hugging Face, Google News, `www.googleapis.com`, Instagram y los CDN de Higgsfield **bloqueados** desde esta sesión. No se pudo cambiar la configuración: el servicio de entornos rechazó la petición.
- Conectores disponibles: **Higgsfield** (vídeo, voz, música y SFX con IA, más un sandbox con ffmpeg). Plan Plus con 165 créditos. HyperFrames (HeyGen), Vercel, Supabase, Google Drive, Gmail y Calendar.
- Skills revisadas: `becario-reels` y `cartoon-audio-short` son reels animados con código, no vídeo realista; no encajan como motor principal. `deep-research` cubre la investigación y `claude-api` los guiones.

## Herramientas pedidas

### Open-Generative-AI (Anil-matcha) — MIT
- Es una interfaz Next.js/Electron sobre **MuAPI** (`api.muapi.ai`), un servicio de pago por uso. **No genera nada en local**: cada vídeo se cobra en MuAPI.
- Integración real: `POST https://api.muapi.ai/api/v1/<endpoint>` con cabecera `x-api-key` y después `GET /api/v1/predictions/<id>/result` (comprobado en su código). Implementado en `scenes._muapi`.
- Modelos de vídeo detectados en el código: familias Seedance 2/2.5, Kling, MiniMax Hailuo, Wan, LTX, Grok y Happy Horse.
- No se ha instalado la interfaz completa porque no aporta nada a un pipeline sin interfaz. Solo se usa su API.

### VoiceStudio (debpalash) — AGPL-3.0
- Estudio de voz local con el motor por defecto OmniVoice (k2-fsa). Clonación, diseño de voz, 646 idiomas y API compatible con OpenAI (`POST /v1/audio/speech`, `Authorization: Bearer`).
- **Instalado y arrancado** en Docker: imagen `palashdeb/omnivoice-studio:stable` (el blob de GHCR estaba bloqueado y se usó el espejo de Docker Hub). API en `127.0.0.1:3900` con clave aleatoria en `~/.marcius3r/voicestudio.key`. La migración de la base de datos y la API funcionan, y responde con 401 sin clave.
- **Pendiente**: la primera generación necesita descargar el modelo OmniVoice de Hugging Face y aceptar su licencia, y Hugging Face está bloqueado en esta sesión. En tu PC o VPS se hace desde la interfaz (README §2).
- Licencia AGPL: se usa sin modificar y como servicio separado. Usar sus audios no te obliga a liberar nada. Si lo modificas y lo expones en red, tendrías que publicar esos cambios.
- Funciona en CPU, aunque más lento. Para un Short (unas 100 palabras) es asumible.

### Alternativas evaluadas
| Función | Elegida | Por qué |
|---|---|---|
| Vídeo realista | Higgsfield (Seedance 2.0 mini, Kling 3 turbo, Seedance 2.5) / MuAPI | Calidad cinematográfica con movimiento real. Precio medido: 5 créditos por clip de 5 s. |
| Voz | VoiceStudio local → Higgsfield seed_audio / ElevenLabs | Local y gratuita primero; respaldo de pago. |
| Montaje | FFmpeg propio | Control total, gratis y reproducible. HyperFrames MCP desactiva `compose` para agentes CLI. |
| Subtítulos | ASS (libass) + faster-whisper opcional | Palabra a palabra con estilo de marca. |
| Base de datos | SQLite | Sin servidor y suficiente para un canal. |
| Panel | `http.server` | Sin dependencias, solo local. |
| Programación | systemd timer o cron, `Europe/Madrid` | Lo más simple y robusto. |

## Reel de referencia de Instagram
No se pudo abrir: `www.instagram.com` está bloqueado en la red de esta sesión y, además, Instagram exige iniciar sesión. Para analizarlo:
- Permite `www.instagram.com` en la red del entorno, **o**
- Descarga tú el reel y súbelo al chat. Higgsfield `video_analysis_create` hace el análisis escena a escena: planos, ritmo, cámara y texto.

El estilo implementado sigue los patrones habituales de los Shorts virales de GTA:
- Gancho en menos de 3 s.
- Un cambio de plano cada 2-3 s.
- Subtítulos grandes palabra a palabra.
- Golpes de sonido en cada cambio.
- Música oscura con graves.

Cuando el reel esté accesible, se ajustarán los parámetros (`cuts_per_10s`, estilos ASS, transiciones) para inspirarse en él sin copiarlo.

## Investigación de GTA 6 y competencia (resumen)
- Lanzamiento el **19-nov-2026** (PS5 y Xbox Series), sin versión de PC anunciada y sin fecha para el modo online. Hechos con fuente en `data/facts.yaml`.
- Competencia en español: El canal de X, ZONA GTA 6, Colny, GTA6MomentsES. En inglés: Nought, JoblessGarrett, Saintsfan, Putther, LegacyKillaHD, GTA VI O'Clock.
- Preguntas que más se repiten:
  - Hora de lanzamiento por país.
  - Precio local.
  - PC y GTA Online.
  - Tamaño de descarga.
  - Si merece la pena la edición Ultimate.
  - Si las filtraciones son reales.
  - PS5 frente a PS5 Pro.
- Oportunidad: tras el lanzamiento, el **gameplay propio y legítimo** pasa a ser la mejor fuente de vídeo («cosas que se pueden hacer», mecánicas reales). El sistema ya lo prioriza con `gameplay_library`.

## Políticas aplicadas
- YouTube exige declarar el contenido sintético realista: `status.containsSyntheticMedia` en `videos.insert`. Además: etiqueta en pantalla y aviso en la descripción.
- YouTube «inauthentic content» (desde jul-2025) penaliza la producción en masa con plantilla. Medidas: guion original diario, variedad de categorías y formatos, y análisis propio.
- La API de YouTube deja en **privado** los vídeos de proyectos sin auditar. Hay que solicitar la auditoría (README §3).
- Rockstar tolera el gameplay pero retira el material previo al lanzamiento o filtrado, los finales y las compilaciones de cinemáticas.
- Desde sept-2026, la violencia gráfica en los primeros 7 s deja el vídeo sin anuncios, según la prensa. El gancho se genera sin violencia explícita.
