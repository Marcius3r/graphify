import json
import random
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from marcius3r import core, editor, qc, scenes, scheduler, thumbnail
from marcius3r.metadata import build_metadata
from marcius3r.research import guess_category, ingest_items, pick_idea, seed_idea_bank, similarity
from marcius3r.script_writer import validate_script, write_template
from marcius3r.subtitles import word_timings

S = core.load_settings()


def test_similarity_and_category():
    assert similarity("GTA 6 fecha de lanzamiento", "Fecha de lanzamiento de GTA 6 confirmada") > 0.5
    assert similarity("Leonida vs Florida", "Precio de GTA 6 en México") < 0.2
    assert guess_category("GTA 6 vs GTA 5: el mapa") == "D"
    assert guess_category("Rockstar publica un nuevo tráiler") == "E"


def test_leaks_are_never_ingested():
    n = ingest_items([{"title": "GTA 6 leak shows new map", "link": "https://x.com/a", "tier": "prensa", "published": None}], S)
    assert n == 0


def test_seed_and_pick_without_repeats():
    seed_idea_bank()
    idea = pick_idea("short")
    assert idea and idea["status"] == "new"


def test_template_script_is_valid_and_rumor_rules():
    idea = {"title": "Leonida vs Florida real", "needs": json.dumps(["leonida", "regions", "protagonists"]),
            "angle": "", "category": "C", "tier": "oficial", "source_urls": "[]"}
    s = write_template(idea, "short", S)
    assert validate_script(s, "short", S) == []
    s["beats"][2]["claim_type"] = "rumor"  # rumor no anunciado en voz → error
    assert any("rumor" in p for p in validate_script(s, "short", S))
    s["beats"][2]["claim_type"] = "confirmado"
    s["beats"][2]["fact_ids"] = ["inventado"]
    assert any("desconocido" in p for p in validate_script(s, "short", S))


def test_word_timings_cover_duration():
    w = word_timings("Hay un detalle de GTA 6 que casi nadie ha visto.", 1.0, 3.0)
    assert w[0][1] == 1.0 and abs(w[-1][2] - 4.0) < 1e-6


def test_wer():
    assert qc.wer("hola qué tal", "hola qué tal") == 0
    assert qc.wer("hola qué tal", "hola tal") > 0


def test_slot_rotation_and_madrid_time():
    slot = scheduler.choose_slot(S, random.Random(1))
    assert slot in S["schedule"]["slots"]
    t = scheduler.next_publish_time("A", S, after=datetime.fromisoformat("2026-11-20T10:00:00+00:00"))
    assert t.tzinfo.key == "Europe/Madrid" and (t.hour, t.minute) == (20, 0)


def test_metadata_disclosure_and_limits():
    idea = {"title": "Leonida", "needs": json.dumps(["leonida"]), "category": "C"}
    m = build_metadata(write_template(idea, "short", S), "short", True, S)
    assert "RECREACIÓN IA" in m["description"] and m["contains_synthetic_media"] is True
    assert len(m["title"]) <= 100 and sum(len(t) for t in m["tags"]) <= 500
    assert "Fuentes" in m["description"]


@pytest.mark.slow
def test_end_to_end_render_is_blocked_with_test_scenes(tmp_path: Path):
    """Monta un Short real (voz de tono + escenas procedurales). Debe renderizar bien y QC
    debe BLOQUEARLO por contener escenas de prueba."""
    idea = {"title": "Leonida vs Florida real", "needs": json.dumps(["leonida", "regions", "protagonists", "release_date"]),
            "category": "C"}
    script = write_template(idea, "short", S)
    vdir = tmp_path / "voice"
    vdir.mkdir()
    for i, b in enumerate(script["beats"]):  # voz de prueba: tono con duración realista
        d = max(1.2, len(b["narration"].split()) / 2.7)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=f={180+i*20}:d={d}",
                        "-af", "volume=0.3,tremolo=f=6:d=0.7", str(vdir / f"beat_{i:02d}.wav")], check=True)
    from marcius3r import voice
    vo = voice.synthesize(script, tmp_path, S)
    shots = scenes.plan_shots(script, vo, "short", S)
    clips = scenes.gather_clips(script, shots, tmp_path, "short", S, allow_test=True)
    info = editor.render(script, vo, clips, tmp_path, "short", S, final_quality=False)
    out = Path(info["output"])
    assert out.exists() and info["has_audio"]
    meta = build_metadata(script, "short", True, S)
    report = qc.run_qc(out, script, info, "short", S, meta)
    assert (report["metrics"]["width"], report["metrics"]["height"]) == (1080, 1920)
    assert any("PRUEBA" in b for b in report["blockers"]), report
    assert report["metrics"]["freeze_ratio"] < 0.12
    assert abs(report["metrics"]["lufs"] - (-14)) < 2.0
    assert info["audio"]["native_ambience"] is True
    frame = thumbnail.best_frame([c["path"] for c in clips], tmp_path)
    th = thumbnail.make_thumbnail(frame, script["thumbnail_text"], tmp_path / "t.jpg", S, True)
    assert th.stat().st_size < 2_000_000


def test_wan2gp_tasks_follow_open_generative_ai_format():
    from marcius3r import wan2gp
    t = wan2gp.video_task("city at night", 5, "9:16", "ltx2_25_22B_distilled", seed=3)
    assert t["model_type"] == "ltx2_25_22B_distilled" and t["resolution"] == "704x1280"
    assert (t["video_length"] - 1) % 8 == 0 and 110 <= t["video_length"] <= 130
    w = wan2gp.video_task("x", 5, "16:9", "t2v_1.3B", seed=3)
    assert w["resolution"] == "832x480" and (w["video_length"] - 1) % 4 == 0
    v = wan2gp.tts_task("Hola", {"language": "spanish", "voice_tags": "male, young adult"})
    assert v["model_type"] == "omnivoice" and v["model_mode"] == "spanish" and v["audio_prompt_type"] == ""
    m = wan2gp.music_task("synthwave", 40)
    assert m["prompt"] == "[Instrumental]" and m["duration_seconds"] == 42


def test_kaggle_runner_compiles():
    import base64
    from marcius3r.kaggle_gpu import RUNNER, WAN2GP_COMMIT
    code = RUNNER.format(tasks_b64=base64.b64encode(b"[]").decode(), files_b64=base64.b64encode(b"{}").decode(),
                         commit=WAN2GP_COMMIT, profile=4)
    compile(code, "run.py", "exec")


def test_scenes_without_gpu_fall_back_to_pending(tmp_path):
    """Sin Wan2GP ni Kaggle, gather_clips falla con mensaje claro (el pipeline lo deja en scenes_pending)."""
    idea = {"title": "Leonida", "needs": json.dumps(["leonida"]), "category": "C"}
    script = write_template(idea, "short", S)
    vo = [{"duration": 2.0, "pause": 0.1} for _ in script["beats"]]
    shots = scenes.plan_shots(script, vo, "short", S)
    scenes.write_manifest(shots, tmp_path, S)
    assert (tmp_path / "generation_tasks.json").exists()
    with pytest.raises(core.StepError):
        scenes.gather_clips(script, shots, tmp_path, "short", S)


def test_voice_design_tasks_are_original_descriptions():
    from marcius3r import wan2gp
    d = S["providers"]["voice"]["design"]
    t = wan2gp.voice_design_task(d["sample_text"], d["base"], "spanish", 20)
    assert t["model_type"] == "qwen3_tts_voicedesign" and t["model_mode"] == "spanish"
    assert "audio_guide" not in t  # diseño por descripción, sin audio de nadie
    assert len(d["variants"]) >= 3


def test_publishing_guide_title_hashtags_description():
    from marcius3r.metadata import build_metadata
    from marcius3r.script_writer import title_problems
    assert title_problems("GTA 6 SEIS zonas del mapa que casi nadie conoce 🗺️") == []
    assert title_problems("Las zonas de GTA 6 que nadie conoce del mapa 🗺️")  # no empieza por GTA 6
    assert title_problems("GTA 6 seis zonas del mapa que casi nadie conoce 🗺️")  # gancho no en mayúsculas
    assert title_problems("GTA 6 SEIS zonas del mapa que casi nadie conoce")  # sin emoji
    s = json.load(open(Path(__file__).resolve().parent.parent / "samples" / "sample_01_leonida.json"))
    m = build_metadata(s, "short", True, S)
    assert m["hashtags"][:2] == ["#Shorts", "#GTA6"] and 4 <= len(m["hashtags"]) <= 5
    assert "🔎" in m["description"] and "suscr" not in m["description"].lower()
    assert m["description"].strip().endswith(" ".join(m["hashtags"]))
