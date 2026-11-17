"""PASO 4: guion original con estructura gancho → intro → desarrollo → detalles → final → CTA.

Cada frase ("beat") lleva su propia escena de vídeo (prompt de cámara en movimiento),
texto en pantalla, efectos de sonido y los ids de hechos verificados que la respaldan.
"""
from __future__ import annotations

import json
import re

from .core import StepError, load_secrets, load_settings
from .research import verified_facts

WORDS_PER_SECOND = 2.7  # valor por defecto; se sobreescribe con channel.words_per_second


def wps(settings: dict) -> float:
    return float(settings.get("channel", {}).get("words_per_second", WORDS_PER_SECOND))

BEAT_SCHEMA = {
    "type": "object",
    "properties": {
        "role": {"type": "string", "enum": ["hook", "intro", "body", "detail", "ending", "cta"]},
        "narration": {"type": "string"},
        "scene_prompt": {"type": "string"},
        "camera": {"type": "string"},
        "overlay_text": {"type": "string"},
        "sfx": {"type": "string"},
        "fact_ids": {"type": "array", "items": {"type": "string"}},
        "claim_type": {"type": "string", "enum": ["confirmado", "rumor", "teoria", "opinion", "ninguno"]},
        "footage_tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["role", "narration", "scene_prompt", "camera", "overlay_text", "sfx", "fact_ids", "claim_type",
                 "footage_tags"],
    "additionalProperties": False,
}

SCRIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "title_alternatives": {"type": "array", "items": {"type": "string"}},
        "thumbnail_text": {"type": "string"},
        "thumbnail_scene": {"type": "string"},
        "music_mood": {"type": "string"},
        "beats": {"type": "array", "items": BEAT_SCHEMA},
        "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "caption_hook": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "comment_question": {"type": "string"},
    },
    "required": ["title", "title_alternatives", "thumbnail_text", "thumbnail_scene", "music_mood",
                 "beats", "description", "hashtags", "tags", "caption_hook", "comment_question", "keywords"],
    "additionalProperties": False,
}

SYSTEM_ES = """Eres el guionista de MARCIUS3R, canal de YouTube en español sobre GTA 6 (público España + LATAM).
Voz: chico joven de España, creador gaming, enérgico y cercano, frases cortas, ritmo rápido, cero relleno.
REGLAS INQUEBRANTABLES:
1. Solo puedes afirmar como hecho lo que aparece en HECHOS VERIFICADOS. Cita sus ids en fact_ids.
2. Si mencionas algo no verificado, márcalo como rumor o teoría y dilo en voz alta ("se rumorea", "es una teoría").
3. Nunca inventes mecánicas, precios, fechas ni lugares. Nada de material filtrado.
4. Las escenas son RECREACIONES de IA en movimiento (no capturas del juego): describe planos con
   cámara dinámica, personajes y vehículos en movimiento, ambiente urbano de una ciudad costera tropical
   estilo años 80-actual, neón, palmeras. NO nombres marcas reales, ni logos, ni personajes con su nombre
   en el scene_prompt (descríbelos de forma genérica). Sin texto en la imagen.
5. scene_prompt en INGLÉS, 1-2 frases, cinematográfico, vertical si es Short. camera: tipo de movimiento.
6. overlay_text: 1-4 palabras MAYÚSCULAS. sfx: efecto en inglés (p.ej. "engine rev", "whoosh", "city ambience").
7. Estructura obligatoria de beats: 1 hook (0-3 s, curiosidad máxima), 1 intro, varios body/detail, 1 ending, 1 cta.
8. El cta debe ser exactamente el CTA del canal.
9. Escribe números con letra cuando se lean ("diecinueve de noviembre").
10. Título < 70 caracteres, sin clickbait falso. Descripción con fuentes al final y aviso de recreación IA.
FÓRMULA QUE FUNCIONA (Reels virales de curiosidades en español, p.ej. 45 s y 59K likes):
- Gancho tipo «¿Sabías que…?» o pregunta de emoción («¿Ya estás preparado…?») en la primera frase.
- Una línea emocional que conecte con el jugador (espera, nostalgia, hype del lanzamiento), sin exagerar datos.
- Cierra el ending con una PREGUNTA PERSONAL fácil de responder («¿con quién vas a jugarlo?», «¿cuál vas a
  explorar primero?»), no una pregunta genérica: eso dispara los comentarios.
- caption_hook: 1-2 líneas en minúscula, cercanas, con 1 emoji (texto del post). comment_question: esa pregunta personal.
ESTILO VIRAL DEL CANAL (estilo_viral.md):
- Formato estrella «3 COSAS de GTA 6 que…»: 25-35 s, 6 beats = gancho de 2 s → anuncio («la tercera es una locura»)
  → 1/3 → 2/3 → 3/3 → pregunta. overlay_text con contador («1/3 · 6 ESTRELLAS»). Lo más fuerte al FINAL y anunciado
  al principio. Ritmo: un corte cada 1,5-2,5 s.
- Ganchos que funcionan: contrario a lo esperado/polémico, advertencia («NO compres GTA 6 sin saber esto»), detalle
  oculto («Fíjate BIEN»), número pequeño, «¿Qué pasa si…?», POV («POV: son las 23:59 del 18»), GTA 5 vs GTA 6.
- Pregunta final CERRADA de dos opciones («¿Estándar o Ultimate?»). Nunca pedir suscripción en el ending.
- footage_tags: 2-4 etiquetas en inglés para buscar clips reales en la biblioteca (night, city, police, car…).
- Evita: «80 h de historia» (era una partida de un desarrollador con secundarias), el «truco de Nueva Zelanda» (no
  garantizado) y cualquier clip viral de GTA 6 hecho con IA presentado como real.
GUÍA DE PUBLICACIÓN DEL CANAL (obligatoria):
- title: empieza EXACTAMENTE por «GTA 6» y justo después la palabra GANCHO en MAYÚSCULAS (al hacer scroll solo se
  ven las 2 primeras palabras), 40-60 caracteres, curiosidad sin contarlo todo, termina con UN emoji.
  Ej.: «GTA 6 NADIE vio este detalle del mapa 🤯».
- hashtags: SOLO 2 del tema, sin #Shorts ni #GTA6 (se añaden solos). Ej.: #ViceCity, #JasonYLucia, #GTA6Policia.
- keywords: 6-10 palabras clave de búsqueda (sin #).
- description: resumen breve (2-3 frases). NUNCA escribas «suscríbete» en la descripción."""


SYSTEM_LATAM = SYSTEM_ES.replace(
    "Voz: chico joven de España, creador gaming,",
    "Voz: chico joven latinoamericano, creador gaming, en ESPAÑOL NEUTRO (entendible en España y LATAM): "
    "usa «ustedes», nada de «vosotros», «tío», «mola», «guay» ni modismos locales;")


def system_prompt(settings: dict) -> str:
    return SYSTEM_LATAM if settings["channel"].get("voice_accent") == "latam" else SYSTEM_ES


SYSTEM = SYSTEM_ES  # compatibilidad


def target_words(fmt: str, settings: dict) -> int:
    return int(settings["formats"][fmt]["target_seconds"] * wps(settings))


def build_prompt(idea: dict, fmt: str, settings: dict) -> str:
    needs = json.loads(idea.get("needs") or "[]")
    facts = verified_facts(needs)
    facts_txt = "\n".join(f"- [{f['id']}] ({f['status']}) {f['text']}" for f in facts)
    words = target_words(fmt, settings)
    n_beats = "8-11" if fmt == "short" else "45-70"
    return f"""IDEA: {idea['title']}
ÁNGULO: {idea.get('angle') or '-'}
CATEGORÍA: {idea.get('category')}  (A=qué se puede hacer, B=qué no / mitos, C=curiosidades, D=comparación, E=novedades, F=viral)
FORMATO: {fmt} ({'vertical 9:16, 30-59 s' if fmt == 'short' else 'horizontal 16:9, 5-10 min'})
LONGITUD: ~{words} palabras de narración en total, {n_beats} beats.
CTA DEL CANAL: {settings['channel']['cta']}

HECHOS VERIFICADOS:
{facts_txt}

FUENTES DE LA IDEA: {idea.get('source_urls') or '[]'}  (nivel: {idea.get('tier')})

Escribe el guion completo."""


def write_script(idea: dict, fmt: str = "short", settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    engine = settings["providers"]["script"]["engine"]
    script = _write_anthropic(idea, fmt, settings) if engine == "anthropic" else write_template(idea, fmt, settings)
    problems = validate_script(script, fmt, settings)
    if problems:
        raise StepError("guion inválido: " + "; ".join(problems))
    return script


def _write_anthropic(idea: dict, fmt: str, settings: dict) -> dict:
    import anthropic
    secrets = load_secrets()
    client = anthropic.Anthropic(api_key=secrets.get("ANTHROPIC_API_KEY")) if secrets.get("ANTHROPIC_API_KEY") else anthropic.Anthropic()
    cfg = settings["providers"]["script"]
    kwargs = dict(
        model=cfg["model"],
        max_tokens=16000 if fmt == "short" else 32000,
        system=system_prompt(settings),
        messages=[{"role": "user", "content": build_prompt(idea, fmt, settings)}],
        output_config={"effort": cfg.get("effort", "high"),
                       "format": {"type": "json_schema", "schema": SCRIPT_SCHEMA}},
    )
    with client.messages.stream(**kwargs) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "refusal":
        raise StepError(f"el modelo rechazó la petición: {getattr(resp, 'stop_details', None)}")
    text = next(b.text for b in resp.content if b.type == "text")
    script = json.loads(text)
    script["_usage"] = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    return script


def write_template(idea: dict, fmt: str, settings: dict) -> dict:
    """Guion determinista sin IA (pruebas / respaldo). Solo usa hechos verificados."""
    needs = json.loads(idea.get("needs") or "[]")
    facts = [f for f in verified_facts(needs) if f["id"] in needs] or verified_facts()[:3]
    beats = [
        {"role": "hook", "narration": "Hay un detalle de GTA 6 que casi nadie ha visto.", "overlay_text": "NADIE LO VIO",
         "scene_prompt": "Night aerial shot gliding over a neon-lit tropical coastal city, palm trees, traffic streaks",
         "camera": "fast drone push-in", "sfx": "deep boom whoosh", "fact_ids": [], "claim_type": "ninguno", "footage_tags": []},
        {"role": "intro", "narration": f"Hoy te cuento {idea['title'].lower()}, solo con lo que está confirmado.",
         "overlay_text": "SOLO LO CONFIRMADO",
         "scene_prompt": "Sports car speeding along a beachfront boulevard at sunset, camera tracking alongside",
         "camera": "tracking shot", "sfx": "engine rev", "fact_ids": [], "claim_type": "ninguno", "footage_tags": []},
    ]
    shots = [
        ("Crowded neon street at night, people walking, cars passing, light rain reflections", "steady glide", "city ambience"),
        ("Speedboat cutting through turquoise water near mangroves, spray in slow motion", "low angle follow", "boat engine"),
        ("Police helicopter searchlight sweeping over a highway chase at night", "handheld tilt up", "helicopter"),
        ("Two silhouettes walking out of a convenience store into flashing police lights", "dolly back", "siren"),
    ]
    for i, f in enumerate(facts):
        p, cam, sfx = shots[i % len(shots)]
        beats.append({"role": "body" if i < 2 else "detail", "narration": f["text"], "overlay_text": f["id"].upper()[:18],
                      "scene_prompt": p, "camera": cam, "sfx": sfx, "fact_ids": [f["id"]], "claim_type": "confirmado", "footage_tags": []})
    beats.append({"role": "ending", "narration": "Y esto es solo el principio de lo que esconde Leonida.",
                  "overlay_text": "SOLO EL PRINCIPIO",
                  "scene_prompt": "Slow aerial pull-back from a city skyline at blue hour, lights turning on",
                  "camera": "drone pull-back", "sfx": "riser", "fact_ids": [], "claim_type": "opinion", "footage_tags": []})
    beats.append({"role": "cta", "narration": settings["channel"]["cta"], "overlay_text": "SUSCRÍBETE",
                  "scene_prompt": "Neon purple and electric blue light streaks racing through a dark tunnel",
                  "camera": "fast forward motion", "sfx": "whoosh", "fact_ids": [], "claim_type": "ninguno", "footage_tags": []})
    hook_title = f"GTA 6 NADIE sabe esto: {idea['title']}"
    if len(hook_title) > 57:
        hook_title = hook_title[:56].rsplit(" ", 1)[0]
    hook_title = (hook_title + " del juego" if len(hook_title) < 38 else hook_title) + " 🤯"
    return {"title": hook_title, "title_alternatives": [], "thumbnail_text": "NADIE LO VIO",
            "thumbnail_scene": beats[0]["scene_prompt"], "music_mood": "dark synthwave trap",
            "beats": beats, "description": f"{idea['title']}.", "hashtags": ["#ViceCity", "#Leonida"],
            "keywords": ["GTA 6", "GTA VI", "Leonida", "Vice City", "curiosidades GTA 6", "lanzamiento GTA 6"],
            "tags": ["GTA 6", "GTA VI", "Leonida", "Vice City"],
            "caption_hook": "¿ya estás preparado para GTA 6? 🎮", "comment_question": "¿Con quién vas a jugarlo?"}


def validate_script(script: dict, fmt: str, settings: dict) -> list[str]:
    problems = []
    known = {f["id"]: f for f in verified_facts()}
    roles = [b["role"] for b in script.get("beats", [])]
    if not roles or roles[0] != "hook":
        problems.append("el primer beat debe ser el gancho")
    if roles[-1:] != ["cta"]:
        problems.append("el último beat debe ser la llamada a la acción")
    for b in script["beats"]:
        for fid in b["fact_ids"]:
            if fid not in known:
                problems.append(f"hecho desconocido {fid}")
        if b["claim_type"] == "confirmado" and not b["fact_ids"]:
            problems.append(f"afirmación 'confirmada' sin fuente: {b['narration'][:60]}")
        if b["claim_type"] in ("rumor", "teoria") and not re.search(r"rumor|teor[ií]a|se dice|se especula|no confirmad", b["narration"], re.I):
            problems.append(f"rumor sin avisar en voz: {b['narration'][:60]}")
        if re.search(r"\b(leak|filtrad)", b["narration"], re.I):
            problems.append("menciona material filtrado")
    words = sum(len(b["narration"].split()) for b in script["beats"])
    secs = words / wps(settings)
    f = settings["formats"][fmt]
    if not (f["min_seconds"] * 0.8 <= secs <= f["max_seconds"] * 1.05):
        problems.append(f"duración estimada {secs:.0f}s fuera de rango")
    problems += title_problems(script["title"])
    return problems


EMOJI_END = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF][\uFE0F]?$")


def title_problems(title: str) -> list[str]:
    p = []
    words = title.split()
    if not title.startswith("GTA 6 "):
        p.append("el título debe empezar por «GTA 6»")
    elif len(words) < 3 or not (words[2].isupper() and len(re.sub(r"\W", "", words[2])) >= 2):
        p.append("tras «GTA 6» debe ir la palabra GANCHO en mayúsculas")
    if not (40 <= len(title) <= 60):
        p.append(f"título de {len(title)} caracteres (debe tener 40-60)")
    if not EMOJI_END.search(title.strip()):
        p.append("el título debe terminar con un emoji")
    return p


def full_narration(script: dict) -> str:
    return " ".join(b["narration"].strip() for b in script["beats"])
