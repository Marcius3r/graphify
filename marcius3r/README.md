# MARCIUS3R — canal de YouTube de GTA 6 automatizado

Sistema que **investiga, escribe, pone voz, genera escenas de vídeo en movimiento, monta, controla la
calidad, crea miniatura y metadatos, programa la publicación en YouTube, mide y aprende** cada día.

> Estado a 16-nov-2026: código completo y probado (9 pruebas, incluida una de montaje real de extremo a
> extremo). Falta conectar tus cuentas (ver «Lo que tienes que hacer tú») y aprobar la primera muestra.
> La publicación automática está **desactivada** hasta que la apruebes (`require_manual_approval: true`).

---

## 1. Cómo funciona

```
 research ─▶ select ─▶ verify ─▶ script ─▶ voice ─▶ scenes ─▶ edit ─▶ QC ─▶ thumbnail ─▶ publish ─▶ analytics ─▶ learn
 (feeds)    (sin       (facts    (Claude,   (por     (vídeo    (FFmpeg (bloquea (Pillow)    (YouTube   (Analytics  (pesos de
            repetir)   .yaml)    JSON)      frase)   real)     cine)   si falla)            Data API)  API)        tema/hora)
```

| Paso | Módulo | Qué hace |
|---|---|---|
| 1-3 Investigar/seleccionar/verificar | `research.py`, `data/facts.yaml` | Google News (ES/MX/EN), Newswire de Rockstar, r/GTA6. Clasifica **oficial / prensa / comunidad / rumor**, descarta filtraciones, evita temas repetidos, rota categorías A-F y pondera por rendimiento. |
| 4 Guion | `script_writer.py` | Claude (`claude-opus-5-5`) con salida JSON estructurada: gancho (0-3 s) → intro → desarrollo → detalles → final → CTA. Cada frase lleva escena, cámara, texto en pantalla, SFX y **ids de hechos verificados**. Un validador rechaza afirmaciones sin fuente, rumores no anunciados y menciones a filtraciones. |
| 5 Voz | `voice.py` | Una síntesis **por frase**: sincronía exacta voz-imagen. Proveedores: VoiceStudio local → Higgsfield (agente) → ElevenLabs. Cadena de locución (EQ, compresión, limitador). |
| 6 Escenas | `scenes.py` | Un clip de **vídeo en movimiento** por frase (dos si es larga). Fuentes: tu biblioteca de gameplay legítimo → MuAPI (backend de Open-Generative-AI) → Higgsfield (Seedance/Kling vía agente). **Rechaza imágenes estáticas** midiendo el movimiento. |
| 7 Montaje | `editor.py`, `subtitles.py` | Cortes a la duración de cada frase, cambio de plano (punch-in) en frases largas, empuje de cámara, etalonaje neón, viñeta y grano, destellos y whoosh en cada cambio. Subtítulos grandes palabra a palabra, textos de impacto, etiqueta **RECREACIÓN IA / GAMEPLAY**, marca y barra de progreso. Música con ducking, SFX y −14 LUFS. |
| 8 Calidad | `qc.py` | Resolución, duración, imagen congelada (fotos), negros, ritmo de planos, sonoridad, voz vs guion (WER con faster-whisper), licencia de la música, duplicados, metadatos y aviso de IA. **Con un solo bloqueo no se publica.** |
| 9 Miniatura | `thumbnail.py` | Fotograma más nítido de las escenas, alto contraste, texto enorme con brillo neón, barra de marca y etiqueta «RECREACIÓN IA» cuando procede. |
| 10 Publicar | `youtube.py`, `metadata.py` | API oficial de YouTube con OAuth. Subida reanudable, `publishAt` (programado), `containsSyntheticMedia`, categoría Gaming, idioma es-ES, miniatura. Descripción con **fuentes**, aviso de IA y aviso legal. |
| 11-12 Analizar/mejorar | `scheduler.py`, `pipeline.py` | Guarda vistas, % visto, duración media, likes, comentarios y suscriptores. Rota franjas A/B/C y después usa epsilon-greedy. Recalcula el peso de cada categoría de tema. |
| Panel | `dashboard.py` | `http://127.0.0.1:8787`: generados, pendientes, programados, publicados, errores, coste, vistas, rendimiento por franja, ideas futuras. Botones **Detener/Reanudar** y **Aprobar**. |

Estados de un vídeo: `scripted → voiced → scenes_pending → ready | qc_failed → approved → scheduled → published` (o `failed`).

## 2. Instalación (tu PC o un VPS Linux)

Requisitos: Ubuntu 22.04+ (o WSL2), Python 3.11+, FFmpeg, Docker. Con GPU NVIDIA la voz local va mucho más rápida, aunque también funciona en CPU.

```bash
git clone <tu repo> && cd graphify/marcius3r
./deploy/setup.sh            # venv, dependencias, VoiceStudio en Docker, pruebas
```

Arranca VoiceStudio y crea la voz de MARCIUS3R. La primera vez descarga el modelo OmniVoice de Hugging Face y te pide aceptar su licencia:
1. Abre `http://127.0.0.1:3900` (clave en `deploy/.env`).
2. **Model Manager** → acepta la licencia de OmniVoice y descárgalo.
3. **Voice Design** → describe: *«Hombre joven, español de España (castellano peninsular), creador de contenido gaming, enérgico, cercano, pausas naturales»*. Genera, escucha y guárdalo como perfil `marcius3r-es`. La alternativa es clonar una voz propia con 30-60 s de audio limpio. **Solo puede ser tu voz o una que tengas derecho a clonar.**
4. Prueba la voz:
   `curl -s -H "Authorization: Bearer $(cut -d= -f2 deploy/.env)" -X POST localhost:3900/v1/audio/speech -H 'Content-Type: application/json' -d '{"input":"Hola, soy MARCIUS3R","voice":"marcius3r-es","response_format":"wav"}' -o prueba.wav`

## 3. Lo que tienes que hacer tú (cuentas y claves)

| Qué | Para qué | Cómo |
|---|---|---|
| **Google Cloud + YouTube** | Publicar y leer Analytics | 1) console.cloud.google.com → crea el proyecto «marcius3r». 2) Habilita **YouTube Data API v3** y **YouTube Analytics API**. 3) Pantalla de consentimiento OAuth (externo, añade tu cuenta como usuario de prueba). 4) Credenciales → ID de cliente OAuth → **Aplicación de escritorio** → descarga el JSON a `~/.marcius3r/client_secret.json` (`chmod 600`). 5) `python -m marcius3r auth`: abre la URL que imprime, elige la cuenta del canal MARCIUS3R y autoriza. Nunca se te pedirá la contraseña. |
| **Auditoría de la API de YouTube** | Que los vídeos subidos por API puedan ser **públicos** | Google bloquea en **privado** los vídeos subidos por proyectos no auditados creados después de julio de 2020. Solicita la *YouTube API Services Audit* (formulario de cumplimiento de YouTube API). Mientras tanto, el sistema sube en privado programado y tú los pasas a público desde YouTube Studio con un clic. |
| **Canal verificado** | Miniaturas personalizadas y vídeos de más de 15 min | YouTube Studio → Configuración → Canal → verificación por teléfono. |
| **Anthropic API** (de pago, céntimos por guion) | Guiones diarios | console.anthropic.com → API Keys → `ANTHROPIC_API_KEY` en `~/.marcius3r/secrets.env`. |
| **Vídeo IA**, elige una | Escenas | **a) Higgsfield** (ya conectado en Claude; tu plan Plus tenía 165 créditos): lo usa el agente Claude, ver `docs/AGENT_RUNBOOK.md`. **b) MuAPI** (backend de Open-Generative-AI, de pago por uso): `MUAPI_API_KEY`. |
| ElevenLabs (opcional) | Voz de respaldo | `ELEVENLABS_API_KEY` y un `voice_id` es-ES en `config/settings.yaml`. |
| Música | Banda sonora | Pistas con licencia en `library/music/` y su licencia en `licenses.yaml`, o música generada con Higgsfield o ElevenLabs Music (≈ 3 créditos). |

## 4. Uso diario

```bash
python -m marcius3r research                 # actualizar ideas
python -m marcius3r produce                  # crear el Short del día
python -m marcius3r status                   # ver estado
python -m marcius3r approve 12               # aprobar (solo mientras require_manual_approval: true)
python -m marcius3r publish 12               # subir y programar en la próxima franja
python -m marcius3r dashboard                # panel en http://127.0.0.1:8787
python -m marcius3r pause | unpause          # DETENER / reanudar toda la automatización
```

Automatización diaria con systemd (recomendado):
```bash
mkdir -p ~/.config/systemd/user && cp deploy/marcius3r-daily.* ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now marcius3r-daily.timer
loginctl enable-linger $USER     # que corra aunque no tengas sesión abierta
```
La alternativa es cron: `deploy/crontab.txt`. El ciclo `daily` hace esto:
1. Respeta la pausa y el presupuesto mensual.
2. Reanuda vídeos pendientes.
3. Investiga.
4. Produce el Short si no hay uno listo.
5. Publica lo aprobado.
6. Mide y aprende.

Cuando apruebes la muestra y quieras que todo vaya solo: `production.require_manual_approval: false` en `config/settings.yaml`.

## 5. Horarios (Europe/Madrid)

No hay una hora mágica. Se prueban tres franjas y decide Analytics:

| Franja | Madrid | México (CDMX) | Colombia | Argentina | Por qué |
|---|---|---|---|---|---|
| A | 20:00 | 13:00 | 14:00 | 16:00 | Prime time en España |
| B | 23:30 | 16:30 | 17:30 | 19:30 | Noche en España, tarde en LATAM |
| C | 03:00 | 20:00 | 21:00 | 23:00 | Prime time en México y Colombia (publicación programada) |

Diferencias en horario de invierno (UTC+1). Con el horario de verano español suman una hora más.

Mínimo 5 vídeos por franja. Después: 75 % en la mejor franja y 25 % de exploración. La recompensa es vistas a 48 h × (1 + % visto).

## 6. Formatos

- **Short**: 1080×1920, 30 fps, 25-59 s, gancho inmediato, subtítulos grandes, unos 3,5 planos cada 10 s. **1 al día.**
- **Largo**: 1920×1080, 5-11 min, subtítulos clásicos. Plan: **1 a la semana** (`long_every_n_days: 7`). Se producen reutilizando los temas de los 7 Shorts de la semana con más investigación. Coste estimado: unos 60-90 clips.

## 7. Normas que el sistema aplica

- Nunca se presenta como confirmado algo que no esté en `data/facts.yaml` con fuente. Los rumores se dicen en voz alta como rumores.
- **Cero material filtrado.** Los titulares con «leak/filtra» se descartan. No se reutilizan vídeos de otros canales.
- Las recreaciones IA llevan siempre la etiqueta en pantalla y el aviso en la descripción, y se declaran con `containsSyntheticMedia=true`. El gameplay propio lleva la etiqueta «GAMEPLAY».
- Sin logos ni personajes de Rockstar generados de forma engañosa. Las escenas IA describen escenarios genéricos.
- Política de Rockstar para tu gameplay: nada de material previo al lanzamiento, finales ni compilaciones de cinemáticas.
- YouTube penaliza el «contenido no auténtico» producido en masa. Por eso el guion es original, la investigación es diaria, la plantilla varía y se aporta análisis propio. Evita publicar más de lo que puedas supervisar al principio.
- Nada de bots, compra de vistas ni cuentas falsas.

## 8. Costes orientativos (medidos el 16-nov-2026)

| Concepto | Coste |
|---|---|
| Clip 5 s 9:16 720p, Higgsfield `seedance_2_0_mini` / `grok_video_v15_lite` | 5 créditos |
| Clip 5 s, `kling3_0_turbo` / `wan2_6` | 7,5 créditos |
| Voz Higgsfield `seed_audio`, por frase | 1 crédito |
| Música 45 s `elevenlabs_music_v2` | 2,9 créditos |
| **Short de ~40 s (12 clips + 10 frases + música)** | **≈ 73 créditos** |
| Short con VoiceStudio local + música de biblioteca | ≈ 60 créditos |
| Guion con Claude Opus 5.5 | ≈ 0,05-0,15 $ |

Un Short diario necesita unos 1.800-2.200 créditos al mes. Ajusta `monthly_budget_credits`. El sistema se detiene solo al alcanzarlo.

## 9. Pruebas

```bash
.venv/bin/python -m pytest -q                 # 9 pruebas (incluye render completo, ~3 min)
.venv/bin/python -m pytest -q -m "not slow"   # rápidas
```

## 10. Estructura

```
marcius3r/
  config/settings.yaml   marca, formatos, proveedores, QC, franjas, presupuesto
  data/facts.yaml        hechos verificados con fuentes (base de lo que se puede afirmar)
  data/idea_bank.yaml    ideas iniciales por categoría A-F
  marcius3r/             código (research, script_writer, voice, scenes, editor, subtitles, qc,
                         thumbnail, metadata, youtube, scheduler, pipeline, dashboard, cli)
  library/               tu gameplay, música y SFX con licencia
  deploy/                docker-compose (VoiceStudio), systemd, cron, setup.sh
  docs/                  ARCHITECTURE.md (investigación y decisiones), AGENT_RUNBOOK.md
  samples/               guion de la primera muestra
  tests/
```
