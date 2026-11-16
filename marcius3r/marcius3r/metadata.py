"""Título, descripción, hashtags y etiquetas (con fuentes y aviso de recreación IA)."""
from __future__ import annotations

from .research import verified_facts

DISCLOSURE = ("⚠️ Las escenas marcadas como «RECREACIÓN IA» están generadas con inteligencia artificial "
              "con fines ilustrativos: NO son imágenes oficiales de GTA 6 ni gameplay real. "
              "Las escenas marcadas como «GAMEPLAY» son capturas propias del juego.")
LEGAL = ("Canal de fans no afiliado a Rockstar Games ni Take-Two Interactive. "
         "Grand Theft Auto y GTA son marcas de Take-Two Interactive.")


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
    hashtags = list(dict.fromkeys([h if h.startswith("#") else f"#{h}" for h in script.get("hashtags", [])]
                                  + ["#GTA6", "#GTAVI"] + (["#Shorts"] if fmt == "short" else [])))[:6]
    title = script["title"].strip()
    if fmt == "short" and "#shorts" not in title.lower() and len(title) <= 90:
        title = f"{title} #Shorts"
    desc_parts = [script.get("description", "").strip(), "",
                  "🔔 Suscríbete a MARCIUS3R para descubrir cada día un secreto nuevo de GTA 6.", ""]
    if synthetic:
        desc_parts += [DISCLOSURE, ""]
    if used:
        desc_parts += ["📚 Fuentes:"] + [f"• {u}" for u in used] + [""]
    desc_parts += [LEGAL, "", " ".join(hashtags)]
    return {"title": title[:100], "description": "\n".join(desc_parts)[:4900], "tags": tags,
            "hashtags": hashtags, "category_id": "20", "default_language": "es",
            "default_audio_language": "es-ES", "contains_synthetic_media": synthetic}
