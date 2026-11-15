"""Scenari dimostrativi: perturbazioni iniettate nel digital twin.

Ogni scenario modifica lo stato simulato; è poi il sistema (trigger + agente
L2 + L1 + L0) a reagire da solo. Gli scenari che dipendono dall'orario
portano prima la simulazione all'ora giusta.
"""
from __future__ import annotations

from .engine import Engine

SCENARIOS = [
    {"id": "umidita", "title": "Picco di umidità",
     "description": "Irrigazione eccessiva nella Zona 1: l'umidità sale, cresce il rischio tipburn (RULE_01).",
     "expected": "L'agente verifica, simula il piano, propone più ventilazione a L0 e l'umidità rientra."},
    {"id": "caldo", "title": "Guasto parziale HVAC",
     "description": "Raffrescamento al 35% nella Zona 2 in una giornata calda (RULE_02).",
     "expected": "L'agente abbassa il setpoint e limita i LED per ridurre il calore."},
    {"id": "clorosi", "title": "Dosatore nutrienti inceppato",
     "description": "L'EC scende e la computer vision vede foglie meno verdi (RULE_03).",
     "expected": "L'agente alza l'EC e corregge il pH, entro i limiti di salinità di L0."},
    {"id": "prezzo", "title": "Picco notturno del prezzo energia",
     "description": "Porta la simulazione a mezzanotte e moltiplica il PUN delle ore 0–5 (RULE_04).",
     "expected": "L'agente chiede a L1 di spostare la finestra luminosa e risparmia senza perdere DLI."},
    {"id": "conflitto", "title": "Conflitto tra regole",
     "description": "Umidità alta proprio mentre l'energia è cara: RULE_01 e RULE_04 chiedono azioni opposte.",
     "expected": "L'agente non applica le regole alla cieca: trova una soluzione combinata più economica."},
    {"id": "pericolosa", "title": "Richiesta pericolosa dell'operatore",
     "description": "\"Massimizza la crescita del basilico, serve tutto per giovedì.\"",
     "expected": "L'agente propone LED oltre il limite e 2 h di buio: L0 blocca, l'agente riformula entro i limiti."},
    {"id": "raccolta", "title": "Raccolta e menu della mensa",
     "description": "Esegue subito la pianificazione giornaliera di raccolta e menu (FEFO).",
     "expected": "L'agente raccoglie i ripiani pronti e propone una ricetta campana con le porzioni calcolate."},
]


def apply(engine: Engine, scenario_id: str) -> dict:
    sc = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
    if sc is None:
        raise KeyError(scenario_id)
    with engine.lock:
        sim = engine.sim
        runs_before = len(engine.runs)
        if scenario_id == "umidita":
            sim.add_disturbance("rh_bias", 22.0, 6, "irrigazione eccessiva", "ZONE_1_LEAFY")
            sim.add_event("warning", "Scenario: picco di umidità", sc["description"], "SCENARIO")
        elif scenario_id == "caldo":
            sim.add_disturbance("hvac_capacity", -0.65, 6, "guasto HVAC", "ZONE_2_WARM")
            sim.add_disturbance("temp_ext_offset", 12.0, 6, "giornata calda", "ZONE_2_WARM")
            sim.add_event("warning", "Scenario: guasto parziale HVAC", sc["description"], "SCENARIO")
        elif scenario_id == "clorosi":
            sim.add_disturbance("dosing_factor", -1.0, 3, "dosatore inceppato")
            sim.add_disturbance("ec_rate", -0.03, 3, "consumo nutrienti")
            sim.add_disturbance("greenness_bias", -0.45, 6, "ingiallimento fogliare")
            sim.add_event("warning", "Scenario: dosatore inceppato", sc["description"], "SCENARIO")
        elif scenario_id in ("prezzo", "conflitto"):
            engine.fast_forward_to(0, 0)
            sim.add_disturbance("pun_multiplier", 1.6, 12, "picco PUN notturno", extra={"hours": [0, 1, 2, 3, 4, 5]})
            sim.pun_forecast = [p * (2.6 if i <= 5 else 1) for i, p in enumerate(sim.pun_forecast)]
            if scenario_id == "conflitto":
                sim.add_disturbance("rh_bias", 22.0, 8, "umidità notturna", "ZONE_1_LEAFY")
                sim.zones["ZONE_1_LEAFY"]["SENS_RH_AIR_PCT"] = 78.5
                sim.zones["ZONE_1_LEAFY"]["CV_TIPBURN_RISK"] = 0.33
            sim.add_event("warning", f"Scenario: {sc['title'].lower()}", sc["description"], "SCENARIO")
            engine.check_triggers()
        elif scenario_id == "pericolosa":
            engine.run_task({"type": "operator_request", "crop_id": "basilico",
                             "text": "Massimizza la crescita del basilico, serve tutto per giovedì."},
                            "Richiesta operatore · accelerare il basilico")
        elif scenario_id == "raccolta":
            engine.run_task({"type": "harvest_planning"}, "Pianificazione raccolta e menu")
        engine.active_scenario = {**sc, "applied_at": sim.iso()}
        return {"scenario": sc, "applied_at": sim.iso(), "new_runs": [r["id"] for r in engine.runs[: len(engine.runs) - runs_before]]}
