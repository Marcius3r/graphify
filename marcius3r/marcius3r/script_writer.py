"""PASO 4: guion original con estructura gancho → intro → desarrollo → detalles → final → CTA.

Cada frase ("beat") lleva su propia escena de vídeo (prompt de cámara en movimiento),
texto en pantalla, efectos de sonido y los ids de hechos verificados que la respaldan.
"""
from __future__ import annotations

import json
import re

from .core import StepError, load_secrets, load_settings
from .research import verified_facts

WORDS_PER_SECOND = 2.7  # castellano enérgico de creador gaming

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
    },
    "required": ["role", "narration", "scene_prompt", "camera", "overlay_text", "sfx", "fact_ids", "claim_type"],
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
        "comment_question": {"type": "string"},
    },
    "required": ["title", "title_alternatives", "thumbnail_text", "thumbnail_scene", "music_mood",
                 "beats", "description", "hashtags", "tags", "caption_hook", "comment_question"],
    "additionalProperties": False,
}

SYSTEM = """Eres el guionista de MARCIUS3R, canal de YouTube en español de España sobre GTA 6.
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
- caption_hook: 1-2 líneas en minúscula, cercanas, con 1 emoji (texto del post). comment_question: esa pregunta personal."""


def target_words(fmt: str, settings: dict) -> int:
    return int(settings["formats"][fmt]["target_seconds"] * WORDS_PER_SECOND)


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
        system=SYSTEM,
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
         "camera": "fast drone push-in", "sfx": "deep boom whoosh", "fact_ids": [], "claim_type": "ninguno"},
        {"role": "intro", "narration": f"Hoy te cuento {idea['title'].lower()}, solo con lo que está confirmado.",
         "overlay_text": "SOLO LO CONFIRMADO",
         "scene_prompt": "Sports car speeding along a beachfront boulevard at sunset, camera tracking alongside",
         "camera": "tracking shot", "sfx": "engine rev", "fact_ids": [], "claim_type": "ninguno"},
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
                      "scene_prompt": p, "camera": cam, "sfx": sfx, "fact_ids": [f["id"]], "claim_type": "confirmado"})
    beats.append({"role": "ending", "narration": "Y esto es solo el principio de lo que esconde Leonida.",
                  "overlay_text": "SOLO EL PRINCIPIO",
                  "scene_prompt": "Slow aerial pull-back from a city skyline at blue hour, lights turning on",
                  "camera": "drone pull-back", "sfx": "riser", "fact_ids": [], "claim_type": "opinion"})
    beats.append({"role": "cta", "narration": settings["channel"]["cta"], "overlay_text": "SUSCRÍBETE",
                  "scene_prompt": "Neon purple and electric blue light streaks racing through a dark tunnel",
                  "camera": "fast forward motion", "sfx": "whoosh", "fact_ids": [], "claim_type": "ninguno"})
    return {"title": f"GTA 6: {idea['title']}"[:70], "title_alternatives": [], "thumbnail_text": "NADIE LO VIO",
            "thumbnail_scene": beats[0]["scene_prompt"], "music_mood": "dark synthwave trap",
            "beats": beats, "description": f"{idea['title']}.", "hashtags": ["#GTA6", "#GTAVI", "#Shorts"],
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
    secs = words / WORDS_PER_SECOND
    f = settings["formats"][fmt]
    if not (f["min_seconds"] * 0.8 <= secs <= f["max_seconds"] * 1.05):
        problems.append(f"duración estimada {secs:.0f}s fuera de rango")
    if len(script["title"]) > 100:
        problems.append("título > 100 caracteres (límite YouTube)")
    return problems


def full_narration(script: dict) -> str:
    return " ".join(b["narration"].strip() for b in script["beats"])
