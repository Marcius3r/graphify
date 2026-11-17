# Investigación y decisiones (actualizado el 16-nov-2026)

## Decisión: stack 100 % gratuito sobre Open-Generative-AI (modo local)
Por indicación del propietario del canal:
- **No se usa Higgsfield.**
- Se usa **Open-Generative-AI** (Anil-matcha, MIT).
- Se prioriza lo gratuito y de buena calidad que esté en GitHub.

### Open-Generative-AI
Tiene dos modos:
1. **Nube (MuAPI)**. Interfaz sobre `api.muapi.ai` (`x-api-key`, `POST /api/v1/<endpoint>` y después `GET /api/v1/predictions/<id>/result`). **De pago.** Está integrado como opción desactivada (`scenes._muapi`).
2. **Local (gratis)**. Su app de escritorio ejecuta **Wan2GP** con `wgp.py --process settings.json` (`electron/lib/wan2gpProvider.js` y `wan2gpCatalog.js`). Este sistema hace lo mismo desde Python (`marcius3r/wan2gp.py`):
   - Mismos campos: `model_type`, `prompt`, `resolution`, `video_length`, `seed`.
   - Mismo mapa de resoluciones.
   - Mismo análisis de la salida (`saved to Path:`, `Queue completed: N/N`).
   - Mejora: varias tareas en un único JSON, así el modelo se carga una sola vez por vídeo.

La «skill» oficial del ecosistema, **SamurAIGPT/muapi-skills** (MIT), contiene recetas sobre la API de pago de MuAPI (vídeo para redes, drones, historias…). Se revisó, pero no se usa porque cobra por generación. Sus ideas de prompts (planos de dron, tomas de producto) inspiran los `scene_prompt` del guionista.

### Wan2GP (deepbeepmeep/Wan2GP) — WanGP Community License 2.0
- **Uso:** gratis, incluido el comercial. Puedes vender o monetizar lo que generes; solo pide citar WanGP si vendes directamente esas salidas. No permite revender WanGP como servicio.
- **Requisitos:** GPU NVIDIA o AMD; desde 8 GB de VRAM según el modelo.
- **Commit fijado y revisado:** `38758d3c73366422efcf609abb63cab8385f3552`, del 13-nov-2026.
- **Modelos usados:**

| Uso | `model_type` | Notas |
|---|---|---|
| Vídeo principal | `ltx2_25_22B_distilled` | LTX-2.5: vídeo **y sonido sincronizado**, 8 pasos, 704×1280 / 1280×704, 24 fps (8k+1 fotogramas) |
| Vídeo ligero | `t2v_1.3B` | Wan 2.1 1.3B: 480×832, ~8 GB de VRAM, 16 fps (4k+1) |
| Alternativa | `hunyuan_1_5_480_t2v` | Hunyuan Video 1.5, 480p |
| Voz | `omnivoice` | `model_mode: spanish`. Clonación con `audio_prompt_type: "A"` + `audio_guide` (referencia de 3-10 s). Diseño por etiquetas en inglés (acento no garantizado en español). |
| Música | `ace_step_v1_5_turbo_lm_1_7b` | `prompt: "[Instrumental]"`, estilo en `alt_prompt`, `duration_seconds` |

### GPU gratuita
- **Kaggle:** T4 o P100, unas 30 h por semana con teléfono verificado. Se automatiza con la CLI oficial `kaggle` (`kaggle_gpu.py`: push del kernel, estado y descarga de la salida).
- **Colab y Kaggle a mano:** `notebooks/marcius3r_wan2gp_gratis.ipynb`.
- **Sin verificar:** el rendimiento real de LTX-2.5 en una T4 no se ha podido medir (la sesión no tenía GPU ni red hacia Kaggle o Hugging Face). Si no cabe en tiempo, el respaldo es `t2v_1.3B`.

### VoiceStudio (debpalash) — AGPL-3.0
Usa el mismo modelo OmniVoice, ahora disponible dentro de Wan2GP. Queda como alternativa de voz que funciona **sin GPU** (CPU), a través de Docker y su API compatible con OpenAI.

Se probó en esta sesión:
- Se instaló la imagen `palashdeb/omnivoice-studio:stable`.
- Arrancó y su API respondió.
- No se pudo descargar el modelo porque Hugging Face está bloqueado.

### Otras piezas gratuitas
- Fuente **Montserrat** (SIL OFL).
- **FFmpeg** para el montaje.
- **faster-whisper** (MIT), opcional, para el control de pronunciación.
- **Pillow** para las miniaturas.
- Música: solo ACE-Step (original). La guía del canal excluye la biblioteca de audio de YouTube.

## Entorno de la sesión de desarrollo
- 4 CPU, 15 GB de RAM, **sin GPU**, FFmpeg 6.1 y Docker.
- Red restringida: Hugging Face, Kaggle, Colab, Google News, la API de YouTube e **Instagram** bloqueados.
- Intenté ampliar la red del entorno, pero el servicio rechazó el cambio.

## Reels de referencia de Instagram
Están bloqueados: Instagram no es accesible desde esta red y además exige iniciar sesión.
- `instagram.com/reel/Dfu9dpQhSo6`
- `instagram.com/reel/Dfz1kyryxOb`

Para analizarlos escena a escena hay dos opciones:
- Descargar los MP4 y pasarlos a la sesión.
- Permitir `www.instagram.com` en la red.

El estilo implementado sigue los patrones de los Shorts virales de GTA:
- Gancho en menos de 3 s.
- Un plano nuevo cada 2-3 s, con punch-in.
- Subtítulos grandes palabra a palabra.
- Golpes de sonido en cada cambio.
- Ambiente sonoro real gracias a LTX-2.5.
- Música oscura con graves.

## GTA 6, competencia y políticas
- **Lanzamiento:** 19-nov-2026 (PS5 y Xbox Series). Sin versión de PC ni fecha para el modo online. Hechos con fuente en `data/facts.yaml`.
- **Competencia en español:** El canal de X, ZONA GTA 6, Colny, GTA6MomentsES.
- **Competencia en inglés:** Nought, JoblessGarrett, Saintsfan, Putther, LegacyKillaHD, GTA VI O'Clock.
- **Preguntas más repetidas:** hora de lanzamiento por país, precio, PC, GTA Online, tamaño de descarga, si merece la pena la edición Ultimate, si las filtraciones son reales, PS5 frente a PS5 Pro.
- **YouTube:**
  - Hay que declarar el contenido sintético realista (`containsSyntheticMedia`).
  - Los vídeos subidos por API se quedan en privado hasta pasar la auditoría.
  - Las políticas de «inauthentic content» penalizan la producción en serie sin valor propio.
- **Rockstar:** tolera el gameplay, pero no el material filtrado o previo al lanzamiento, los finales ni las compilaciones de cinemáticas.

## Reel de referencia analizado: @lo_sabias_ya · DfTf4NrvDpt (3-nov-2026)
Se analizó a partir del HTML de la página guardado por el usuario. El vídeo y la portada no se pudieron descargar porque el CDN de Instagram está bloqueado en esta red.

### Datos
- **Métricas:** 58.792 «me gusta» y 191 comentarios.
- **Formato:** vertical 720×1280, **45,3 s**, voz original y sin música con licencia.
- **El canal:** de curiosidades en español («¿Lo sabías?»). Sus Reels más vistos llegan a 100-150 K «me gusta». En un post sus seguidores preguntan con qué IA hacen los vídeos, así que producen con IA.
- **Texto del post:**
  - Pregunta de emoción: «¿ya estás preparado para el juego más esperado? 🎮».
  - Línea emocional: «13 años de espera terminan pronto».
  - Pregunta personal: «¿con quién vas a jugarlo?».
- **Momento:** 16 días antes del lanzamiento.

### Qué se ha incorporado
- `target_seconds: 45`.
- En el guionista:
  - Gancho de tipo «¿Sabías que…?» o pregunta de emoción.
  - Una línea emocional.
  - Un **cierre con pregunta personal**.
  - Campos nuevos `caption_hook` y `comment_question`. La descripción del vídeo empieza por ellos.
- Ideas nuevas de cuenta atrás y nostalgia en `data/idea_bank.yaml`, y el hecho verificado `gta5_release`.

### Qué no se pudo analizar
Los planos, el ritmo de corte, el estilo de los subtítulos y la voz. Hace falta el MP4 o capturas de pantalla.
