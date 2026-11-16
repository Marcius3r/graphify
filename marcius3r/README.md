# MARCIUS3R — canal de YouTube de GTA 6 automatizado (stack gratuito)

Sistema que cada día **investiga, escribe, pone voz, genera escenas de vídeo en movimiento con sonido,
monta, controla la calidad, crea miniatura y metadatos, programa la publicación en YouTube, mide y aprende**.

**Motor de generación: Open-Generative-AI en modo local (Wan2GP).** Es gratis, de código abierto y sin créditos:
- **Vídeo con sonido sincronizado** (motores, ciudad, pasos): LTX-2.5 22B Distilled, a 720p y en 8 pasos. Alternativas: Wan 2.1/2.2 y Hunyuan Video 1.5.
- **Voz en español de España**: OmniVoice, clonando una referencia tuya de 3-10 s.
- **Música original**: ACE-Step 1.5 (licencia Apache-2.0), instrumental.
- **Dónde corre**: en tu GPU NVIDIA o AMD (≥ 8 GB) o en la **GPU gratuita de Kaggle**.

> Estado (16-nov-2026): código completo; **12 pruebas pasan**, incluido un montaje real de principio a fin.
> No se ha podido generar una muestra con IA en la sesión de desarrollo: no tiene GPU y su red bloquea Kaggle y Hugging Face.
> La publicación automática está **desactivada** hasta que apruebes una muestra (`require_manual_approval: true`).

---

## 1. Cómo funciona

```
research → select → verify → script → voice → scenes → edit → QC → thumbnail → publish → analytics → learn
```

| Paso | Módulo | Qué hace |
|---|---|---|
| Investigar, seleccionar y verificar | `research.py`, `data/facts.yaml` | **Fuentes:** Google News (ES, MX y EN), Newswire de Rockstar y r/GTA6. **Clasificación:** oficial, prensa, comunidad o rumor. **Filtros:** descarta filtraciones y temas repetidos. **Selección:** rota las categorías A-F y aprende cuáles funcionan. |
| Guion | `script_writer.py` | **Modelo:** Claude con salida JSON. **Estructura:** gancho (0-3 s), intro, desarrollo, detalles, final y CTA. **Por frase:** escena, cámara, texto en pantalla, SFX e ids de hechos verificados. **Validador:** bloquea afirmaciones sin fuente y rumores no avisados. |
| Voz | `voice.py`, `wan2gp.py` | **Motor:** OmniVoice en Wan2GP, todas las frases en un lote. **Clonación:** a partir de tu referencia. **Respaldos:** VoiceStudio local o ElevenLabs. **Procesado:** EQ, compresión y limitador. |
| Escenas | `scenes.py`, `wan2gp.py`, `kaggle_gpu.py` | **Un clip por frase:** dos si la frase es larga. **Orden de fuentes:** tu gameplay legítimo, después Wan2GP local, después Kaggle gratis y, por último, clips generados fuera. **Calidad:** rechaza imágenes estáticas. |
| Montaje | `editor.py`, `subtitles.py` | **Cortes:** ajustados a cada frase, con un cambio de plano (punch-in) en las frases largas y empuje de cámara. **Imagen:** etalonaje neón, viñeta y grano. **Transiciones:** destello y whoosh en cada cambio. **Sonido:** sonido nativo de LTX como ambiente, música ACE-Step con ducking y −14 LUFS. **Texto:** subtítulos grandes palabra a palabra, textos de impacto, etiqueta **RECREACIÓN IA / GAMEPLAY** y barra de progreso. |
| Calidad | `qc.py` | **Comprueba:** resolución, duración, imagen congelada (fotos), negros, ritmo, sonoridad, voz frente a guion (WER), licencia de la música, duplicados, metadatos y aviso de IA. **Si hay un solo bloqueo, no se publica.** |
| Miniatura | `thumbnail.py` | Mejor fotograma, alto contraste, texto enorme con brillo neón, marca y etiqueta IA. |
| Publicar | `youtube.py`, `metadata.py` | **Vía:** API oficial con OAuth. **Opciones de subida:** `publishAt`, `containsSyntheticMedia`, categoría Gaming, es-ES y miniatura. **Descripción:** incluye fuentes y avisos. |
| Analizar y mejorar | `scheduler.py` | **Métricas:** vistas, % visto, likes, comentarios y suscriptores. **Horarios:** rota las franjas A/B/C y después usa epsilon-greedy. **Temas:** pesos por categoría según resultados. |
| Panel | `dashboard.py` | Panel en `127.0.0.1:8787`. **Muestra:** generados, pendientes, programados, publicados, errores, coste, vistas, rendimiento e ideas. **Botones:** Detener/Reanudar y Aprobar. |

## 2. Instalación gratuita

### Opción A — Tienes GPU NVIDIA (≥ 8 GB VRAM; 16-24 GB para LTX-2.5 cómodo)
```bash
# 1) Wan2GP (motor local de Open-Generative-AI). Versión revisada:
git clone https://github.com/deepbeepmeep/Wan2GP ~/Wan2GP && cd ~/Wan2GP
git checkout 38758d3c73366422efcf609abb63cab8385f3552
./install.sh                     # crea ~/Wan2GP/venv (Windows: install.bat)
# 2) MARCIUS3R
cd ~/graphify/marcius3r && ./deploy/setup.sh
```
La primera vez, Wan2GP descarga los pesos de los modelos de Hugging Face. Son decenas de GB, pero se descargan una sola vez.

Con 8 GB de VRAM, cambia en `config/settings.yaml` el modelo `ltx2_25_22B_distilled` por `t2v_1.3B`. Es más ligero (480p) y el sistema lo reescala a 1080p.

Si quieres la interfaz gráfica de Open-Generative-AI para probar prompts a mano: instala su app de escritorio (github.com/Anil-matcha/Open-Generative-AI/releases). Después, **Settings → Local Models → Wan2GP**, apunta a `~/Wan2GP` y selecciona **⚡ Local**. Usa el mismo motor que este sistema.

### Opción B — Sin GPU: GPU gratuita de Kaggle
1. Crea una cuenta en kaggle.com y verifica tu teléfono para tener acceso a GPU (~30 h/semana gratis).
2. Kaggle → Settings → API → **Create New Token** → guarda `kaggle.json` en `~/.kaggle/` (`chmod 600`).
3. `pip install kaggle` (dentro de `.venv`).

El sistema envía las tareas a un notebook privado con GPU T4, espera y descarga los resultados (`kaggle_gpu.py`).

Para hacerlo a mano: abre `notebooks/marcius3r_wan2gp_gratis.ipynb` en Kaggle o Colab y sube `generation_tasks.json` y `generation_manifest.json`. Descarga `resultados.zip`, descomprímelo en `workspace/videos/<id>/clips/` y ejecuta `python -m marcius3r resume <id>`.

> En una T4, LTX-2.5 tarda bastante (varios minutos por clip con `--profile 4`). Un Short de unos 12 clips cabe en una sesión, pero **pruébalo primero**: no se ha podido medir sin GPU. Si va justo, usa `t2v_1.3B`.

### La voz del canal (castellano de España)
Las etiquetas de diseño de voz de OmniVoice solo describen acentos del inglés. Para un **acento de España fiable**:
1. Graba **3-10 s de tu voz** con energía de creador gaming, sin ruido ni música.
2. Guárdala como `library/voice/marcius3r_ref.wav`.
3. Si quieres, pon su transcripción en `providers.voice.wan2gp.reference_transcript`.

Usa solo tu voz o una que tengas derecho a clonar. Sin referencia, se usa `voice_tags` y el acento no está garantizado.

## 3. Lo que tienes que hacer tú (cuentas y claves)

| Qué | Para qué | Cómo / coste |
|---|---|---|
| **Google Cloud + YouTube** | Publicar y leer Analytics | Gratis. Pasos: 1) Crea el proyecto en console.cloud.google.com. 2) Habilita **YouTube Data API v3** y **YouTube Analytics API**. 3) Configura la pantalla de consentimiento OAuth y añádete como usuario de prueba. 4) Crea un ID de cliente OAuth de tipo **Aplicación de escritorio** y guárdalo en `~/.marcius3r/client_secret.json`. 5) Ejecuta `python -m marcius3r auth` y autoriza el canal en el navegador. Nunca se pide tu contraseña. |
| **Auditoría de la API de YouTube** | Que los vídeos subidos por API sean públicos | Gratis. Sin auditoría, Google los deja en **privado**. Mientras tanto, los pasas a público con un clic en YouTube Studio. |
| **Verificar el canal** | Miniaturas personalizadas | Gratis. YouTube Studio → verificación por teléfono. |
| **Guiones** | Escribir cada día | **Opción 1:** `ANTHROPIC_API_KEY`, de pago (unos céntimos por guion). **Opción 2:** gratis con `providers.script.engine: template` (plantilla solo con hechos verificados, menos creativa). |
| **GPU** | Generar vídeo, voz y música | Tu GPU o Kaggle, gratis (ver §2). |
| Música propia (opcional) | Banda sonora alternativa | Pistas de la Biblioteca de audio de YouTube (gratis y monetizable) en `library/music/`, con su entrada en `licenses.yaml`. |

La **nube** de Open-Generative-AI (MuAPI) también está integrada (`muapi` en `providers.video.order`), pero **es de pago y está desactivada**.

## 4. Uso

```bash
python -m marcius3r research         # ideas nuevas
python -m marcius3r produce          # Short del día  (muestra: --script samples/sample_01_leonida.json) (en lugar de 'ready' puede quedar en 'scenes_pending' si falta GPU)
python -m marcius3r resume 12        # continuar (p.ej. tras generar los clips en Kaggle a mano)
python -m marcius3r approve 12       # aprobar la muestra
python -m marcius3r publish 12       # subir y programar
python -m marcius3r dashboard        # panel http://127.0.0.1:8787
python -m marcius3r pause|unpause    # DETENER / reanudar toda la automatización
```

Automatización diaria con un timer de systemd:
```bash
mkdir -p ~/.config/systemd/user && cp deploy/marcius3r-daily.* ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now marcius3r-daily.timer
loginctl enable-linger $USER
```
La alternativa es cron (`deploy/crontab.txt`). Cuando apruebes la muestra, pon `production.require_manual_approval: false`.

## 5. Horarios (Europe/Madrid)

No hay una hora mágica: se prueban tres franjas y decide Analytics.

| Franja | Madrid | México | Colombia | Argentina | Por qué |
|---|---|---|---|---|---|
| A | 20:00 | 13:00 | 14:00 | 16:00 | Prime time en España |
| B | 23:30 | 16:30 | 17:30 | 19:30 | Noche en España, tarde en LATAM |
| C | 03:00 | 20:00 | 21:00 | 23:00 | Prime time en México y Colombia (programada) |

Primero se publican al menos 5 vídeos en cada franja. Después, el 75 % va a la mejor y el 25 % sigue explorando. La recompensa es: vistas a las 48 h × (1 + % visto).

## 6. Formatos
- **Short**: 1080×1920, 25-59 s, un cambio de plano cada 2-3 s, subtítulos grandes. **Uno al día.**
- **Largo**: 1920×1080, 5-11 min. **Uno a la semana** (`long_every_n_days: 7`), ampliando los temas de los Shorts de esa semana.

## 7. Normas que aplica el sistema
- Solo se afirma lo que está en `data/facts.yaml` con fuente. Los rumores se dicen en voz alta como rumores.
- **Cero material filtrado.** No se reutilizan vídeos de otros canales.
- **Recreaciones IA:** etiqueta en pantalla, aviso en la descripción y `containsSyntheticMedia=true`.
- **Gameplay propio:** etiqueta «GAMEPLAY». Sin finales ni compilaciones de cinemáticas (política de Rockstar).
- **Escenas IA:** escenarios genéricos (ciudad tropical, coches, personas). Sin logos ni personajes oficiales, para que no se confundan con material de Rockstar.
- **Contenido no auténtico (YouTube):** guion original diario y formatos variados. Al principio, supervisa cada vídeo.
- **Créditos:** WanGP pide citarlo si vendes directamente lo que genera. La descripción incluye una línea de créditos de las herramientas.

## 8. Costes
| Concepto | Coste |
|---|---|
| Vídeo, voz y música con Wan2GP (tu GPU o Kaggle) | **0 €** (más la electricidad, o la cuota semanal de Kaggle) |
| Guion con Claude | ≈ 0,05-0,15 $ por vídeo, o 0 € con plantilla |
| YouTube APIs | 0 € (cuota de 10.000 unidades/día; una subida cuesta 1.600) |

## 9. Pruebas
```bash
.venv/bin/python -m pytest -q                 # 12 pruebas (incluye render completo ~3 min)
.venv/bin/python -m pytest -q -m "not slow"
```

## 10. Estructura
```
marcius3r/
  config/settings.yaml      marca, formatos, motores, QC, franjas, presupuesto
  data/facts.yaml           hechos verificados con fuentes
  data/idea_bank.yaml       ideas iniciales A-F
  marcius3r/                código (research, script_writer, voice, wan2gp, kaggle_gpu, scenes, editor,
                            subtitles, qc, thumbnail, metadata, youtube, scheduler, pipeline, dashboard, cli)
  notebooks/                cuaderno Kaggle/Colab para generar gratis a mano
  library/                  tu gameplay, voz de referencia, música y SFX
  deploy/                   setup.sh, docker-compose (VoiceStudio opcional), systemd, cron
  docs/ARCHITECTURE.md      investigación, herramientas evaluadas y decisiones
  samples/                  guion de la primera muestra
```
