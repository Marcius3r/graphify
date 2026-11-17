"""Título, descripción, hashtags y etiquetas (con fuentes y aviso de recreación IA)."""
from __future__ import annotations

import re

from .research import verified_facts

DISCLOSURE = ("⚠️ Las escenas marcadas como «RECREACIÓN IA» están generadas con inteligencia artificial "
              "con fines ilustrativos: NO son imágenes oficiales de GTA 6 ni gameplay real. "
              "Las escenas marcadas como «GAMEPLAY» son capturas propias del juego.")
CREDITS = "🛠️ Creado con herramientas abiertas: WanGP (Wan2GP), LTX-2, OmniVoice y ACE-Step."
LEGAL = ("Canal de fans no afiliado a Rockstar Games ni Take-Two Interactive. "
         "Grand Theft Auto y GTA son marcas de Take-Two Interactive.")


TOPIC_HASHTAGS = ["#ViceCity", "#Leonida", "#JasonYLucia", "#GTA6Policia", "#GTAVI"]


def normalize_hashtags(script: dict, fmt: str) -> list[str]:
    """#Shorts #GTA6 + 2-3 del tema (máximo 5 en total)."""
    topic = []
    for h in script.get("hashtags", []):
        h = "#" + re.sub(r"[^\wáéíóúñÁÉÍÓÚÑ]", "", h.lstrip("#"))
        if h.lower() not in ("#shorts", "#gta6", "#") and h not in topic:
            topic.append(h)
    for h in TOPIC_HASHTAGS:  # relleno hasta 2 del tema
        if len(topic) >= 2:
            break
        if h not in topic:
            topic.append(h)
    base = (["#Shorts"] if fmt == "short" else []) + ["#GTA6"]
    return (base + topic)[: 5 if fmt == "short" else 4]


def build_metadata(script: dict, fmt: str, synthetic: bool, settings: dict) -> dict:
    facts = {f["id"]: f for f in verified_facts()}
    used = []
    for b in script["beats"]:
        for fid in b["fact_ids"]:
            for url in facts.get(fid, {}).get("sources", []):
                if url not in used:
                    used.append(url)
    tags_base = ["GTA 6", "GTA VI", "Grand Theft Auto VI", "GTA 6 español", "Leonida", "Vice City",
                 "Jason y Lucia", "curiosidades GTA 6", "secretos GTA 6", "MARCIUS3R"]
    tags = list(dict.fromkeys([*script.get("tags", []), *tags_base]))
    while sum(len(t) for t in tags) > 460:
        tags.pop()
    hashtags = normalize_hashtags(script, fmt)
    title = script["title"].strip()  # la guía exige «GTA 6 GANCHO … emoji»: no se añade #Shorts al título
    keywords = list(dict.fromkeys([*script.get("keywords", []), *script.get("tags", [])[:6], "GTA 6", "GTA VI"]))
    lead = [x for x in (script.get("caption_hook", "").strip(), script.get("comment_question", "").strip()) if x]
    desc_parts = [*lead, ""] if lead else []
    desc_parts += [script.get("description", "").strip(), "", "🔎 " + ", ".join(keywords[:12]), ""]
    if synthetic:
        desc_parts += [DISCLOSURE, CREDITS, ""]
    if used:
        desc_parts += ["📚 Fuentes:"] + [f"• {u}" for u in used] + [""]
    desc_parts += [LEGAL, "", " ".join(hashtags)]
    description = "\n".join(desc_parts)
    description = re.sub(r"(?im)^.*suscr[ií]b.*$\n?", "", description)  # guía: NUNCA «suscríbete» en la descripción
    return {"title": title[:100], "description": description[:4900], "tags": tags,
            "hashtags": hashtags, "category_id": "20", "default_language": "es",
            "default_audio_language": "es-ES", "contains_synthetic_media": synthetic}
