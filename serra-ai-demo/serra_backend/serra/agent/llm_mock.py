"""LLM emulato ("mock-llm").

Espone la stessa interfaccia di un client Ollama (`chat(messages, tools)`) e
produce messaggi nello stesso formato (content + tool_calls). Invece di un
modello neurale usa delle "policy" scritte a mano: guardano l'evento e i
risultati dei tool già chiamati e decidono il passo successivo. I testi del
ragionamento sono modelli riempiti con i numeri VERI restituiti dai tool.

È dichiaratamente un'emulazione: serve a mostrare il comportamento atteso
dell'agente in modo riproducibile. Sostituibile con OllamaLLM senza toccare
il resto del sistema.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..config import CROPS, RULES, ZONE_LABELS
from .prompts import parse_task_message

MODEL_NAME = "mock-llm-1 (emulazione, formato Ollama)"
RULES_BY_ID = {r["rule_id"]: r for r in RULES}


@dataclass
class Obs:
    """Risultati dei tool già chiamati in questa conversazione."""
    calls: list[tuple[str, dict, dict]] = field(default_factory=list)

    def last(self, name: str) -> dict | None:
        for n, _, r in reversed(self.calls):
            if n == name:
                return r
        return None

    def all(self, name: str) -> list[dict]:
        return [r for n, _, r in self.calls if n == name]

    def count(self, name: str) -> int:
        return sum(1 for n, _, _ in self.calls if n == name)


def _call(thought: str, name: str, args: dict):
    return ("call", thought, name, args)


def _final(thought: str, decision):
    return ("final", thought, decision)


def _zl(zone_id: str) -> str:
    return ZONE_LABELS.get(zone_id, zone_id)


def _verdict_text(v: str) -> str:
    """Participio femminile: si usa sempre come "la proposta è stata …"."""
    return {"ALLOWED": "approvata", "CLIPPED": "approvata con correzioni", "BLOCKED": "bloccata"}.get(v, v)


# ---------------------------------------------------------------------- policy: anomalie da regola
RULE_CFG = {
    "RULE_01_HUMIDITY_TIPBURN": {
        "sensor": "SENS_RH_AIR_PCT", "cv": "CV_TIPBURN_RISK", "label": "umidità", "unit": "%",
        "crop_key": "rh_min_max_pct", "bound": "max", "cv_label": "rischio tipburn", "duration": 6, "energy": True,
        "risk": "muffe e necrosi marginale delle foglie (tipburn)",
    },
    "RULE_02_HEAT_WILTING": {
        "sensor": "SENS_T_AIR_C", "cv": "CV_WILTING_SCORE", "label": "temperatura", "unit": "°C",
        "crop_key": "temp_min_max_c", "bound": "opt", "cv_label": "indice di appassimento", "duration": 6, "energy": True,
        "risk": "stress termico e appassimento",
    },
    "RULE_03_NUTRIENT_CHLOROSIS": {
        "sensor": "SENS_SOL_EC_MS_CM", "cv": "CV_GREENNESS_INDEX", "label": "conducibilità (EC)", "unit": " mS/cm",
        "crop_key": "ec_range_ms_cm", "bound": "min", "cv_label": "indice di verde", "duration": 12, "energy": False,
        "risk": "carenza di nutrienti e clorosi",
    },
}


def _most_sensitive_crop(crops: list[str], key: str, bound: str) -> str:
    if bound == "max":
        return min(crops, key=lambda c: CROPS[c]["ideal_params"][key][1])
    if bound == "min":
        return max(crops, key=lambda c: CROPS[c]["ideal_params"][key][0])
    return min(crops, key=lambda c: CROPS[c]["ideal_params"]["temp_opt_c"])


def policy_rule_anomaly(task: dict, obs: Obs):
    rule = RULES_BY_ID[task["rule_id"]]
    cfg = RULE_CFG[task["rule_id"]]
    zone = task["zone_id"]
    override = dict(rule["solver_override"])

    sensors = obs.last("read_sensors")
    if not sensors:
        return _call(f"È scattata la regola {rule['rule_id']} ({rule['diagnosis'].lower()}) nella {_zl(zone)}. "
                     f"Prima di agire verifico le misure attuali.", "read_sensors", {"zone_id": zone})
    r = sensors["readings"]
    val, cv = r[cfg["sensor"]], r[cfg["cv"]]

    hist = obs.last("get_sensor_history")
    if not hist:
        return _call(f"{cfg['label'].capitalize()} {val}{cfg['unit']}, {cfg['cv_label']} {cv:.2f}. "
                     f"Controllo l'andamento delle ultime 3 ore per capire se è un picco isolato o una tendenza.",
                     "get_sensor_history", {"sensor": cfg["sensor"], "zone_id": zone, "hours": 3})

    crop = _most_sensitive_crop(sensors["crops"], cfg["crop_key"], cfg["bound"])
    targets = obs.last("get_crop_targets")
    if not targets:
        return _call(f"Il valore è {hist['trend']} (da {hist['first']} a {hist['last']}{cfg['unit']} in 3 ore): "
                     f"{'non è un picco isolato' if hist['trend'] != 'stabile' else 'il valore è anomalo ma stabile'}. "
                     f"In questa zona la coltura più sensibile è {CROPS[crop]['name']}: verifico i suoi parametri ideali.",
                     "get_crop_targets", {"crop_id": crop})

    lo, hi = targets[cfg["crop_key"]]
    if cfg["bound"] == "max":
        gap_txt = f"il limite massimo per {targets['name']} è {hi}{cfg['unit']}: siamo {val - hi:+.1f} oltre"
    elif cfg["bound"] == "min":
        gap_txt = f"il minimo per {targets['name']} è {lo}{cfg['unit']}: siamo {val - lo:+.2f} rispetto al minimo"
    else:
        gap_txt = f"l'ottimo per {targets['name']} è {targets['temp_opt_c']} °C: siamo {val - targets['temp_opt_c']:+.1f} °C sopra"

    if cfg["energy"] and not obs.last("get_energy_forecast"):
        return _call(f"Confermato: {gap_txt}. La correzione suggerita dalla tabella ({json.dumps(override)}) "
                     f"cambia i consumi, quindi controllo prezzo dell'energia e fotovoltaico delle prossime ore.",
                     "get_energy_forecast", {"hours": 6})

    sim = obs.last("simulate_plan")
    if not sim:
        if cfg["energy"]:
            ef = obs.last("get_energy_forecast")
            pre = (f"PUN attuale {ef['pun_now']:.3f} €/kWh, fotovoltaico {ef['pv_now_w']} W"
                   f"{' (copre parte del carico)' if ef['pv_now_w'] > 0 else ' (assente)'}. ")
        else:
            pre = f"Confermato: {gap_txt}. "
        return _call(pre + "Chiedo al Level 1 di simulare il piano con l'override prima di proporlo.",
                     "simulate_plan", {"overrides": override})

    sub = obs.last("submit_proposal")
    if not sub:
        delta = sim["delta_cost_eur"]
        return _call(f"Il piano simulato costa {delta:+.2f} €/giorno rispetto a quello attuale "
                     f"({sim['proposed']['cost_eur_day']:.2f} € contro {sim['current']['cost_eur_day']:.2f} €). "
                     f"È un costo contenuto rispetto al rischio di {cfg['risk']}. Invio la proposta al Safety Gate L0 "
                     f"per {cfg['duration']} ore.", "submit_proposal",
                     {"overrides": override, "duration_h": cfg["duration"],
                      "rationale": f"{rule['diagnosis']}: {cfg['label']} {val}{cfg['unit']}, {cfg['cv_label']} {cv:.2f}"})

    if not obs.last("notify_operator"):
        return _call(f"La proposta è stata {_verdict_text(sub['verdict'])} dal Level 0 ({sub['verdict']}). "
                     f"Avviso l'operatore così l'intervento resta tracciato.", "notify_operator",
                     {"severity": "warning",
                      "message": f"{rule['diagnosis']} in {_zl(zone)}: {cfg['label']} {val}{cfg['unit']}. "
                                 f"Override applicato per {cfg['duration']} h (L0: {sub['verdict']})."})

    applied = sub.get("applied_overrides")
    decision = {
        "diagnosi": rule["diagnosis"],
        "evidenze": [f"{cfg['label']} {val}{cfg['unit']} ({hist['trend']}, {hist['first']}→{hist['last']} in 3 h)",
                     f"{cfg['cv_label']} {cv:.2f}", gap_txt],
        "azioni": [f"override al Level 1: {json.dumps(applied, ensure_ascii=False)}" if applied else "nessuna modifica",
                   "operatore avvisato"],
        "solver_override": applied, "verdetto_l0": sub["verdict"], "confidenza": 0.86 if hist["trend"] != "stabile" else 0.74,
        "richiede_umano": sub["verdict"] == "BLOCKED",
        "messaggio_operatore": f"{rule['diagnosis']}: correzione applicata per {cfg['duration']} h, costo stimato {sim['delta_cost_eur']:+.2f} €/giorno.",
    }
    return _final("Situazione gestita: l'override è attivo e il Level 1 ha ripianificato.", decision)


# ---------------------------------------------------------------------- policy: prezzo energia
def _contiguous(hours: list[int]) -> list[int]:
    return sorted(set(hours))


def policy_energy_price(task: dict, obs: Obs):
    ef = obs.last("get_energy_forecast")
    if not ef:
        return _call(f"Il PUN è a {task['variables']['pun_eur_kwh']:.3f} €/kWh e il fotovoltaico è fermo. "
                     f"Controllo le prossime 12 ore e quando sono accesi i LED.", "get_energy_forecast", {"hours": 12})
    expensive = ef["expensive_hours_no_pv"]
    overlap = [h for h in expensive if h in ef["led_on_hours_in_window"]]
    if not overlap:
        return _final("Le ore care non coincidono con l'accensione dei LED: il piano del Level 1 è già efficiente.",
                      {"diagnosi": "Prezzo alto ma piano già ottimale", "evidenze": [f"ore care: {expensive}"],
                       "azioni": ["nessuna"], "solver_override": None, "verdetto_l0": None, "confidenza": 0.9,
                       "richiede_umano": False, "messaggio_operatore": "Nessun intervento necessario."})
    dark = _contiguous(expensive)
    sim = obs.last("simulate_plan")
    if not sim:
        prices = ", ".join(f"{r['hour']:02d}:00 {r['pun_eur_kwh']:.3f}" for r in ef["rows"] if r["hour"] in overlap)
        return _call(f"Ore care senza fotovoltaico con LED accesi: {overlap} ({prices} €/kWh). "
                     f"Chiedo al Level 1 un piano alternativo che tenga spente queste ore.",
                     "simulate_plan", {"overrides": {"prefer_dark_window_hours": dark}})
    sub = obs.last("submit_proposal")
    if not sub:
        if sim["delta_cost_eur"] >= 0:
            return _final("Il piano alternativo non fa risparmiare: mantengo quello attuale.",
                          {"diagnosi": "Spostamento non conveniente", "evidenze": [f"delta {sim['delta_cost_eur']:+.2f} €"],
                           "azioni": ["nessuna"], "solver_override": None, "verdetto_l0": None, "confidenza": 0.8,
                           "richiede_umano": False, "messaggio_operatore": "Nessun intervento."})
        win = sim["proposed"]["light_windows"]
        return _call(f"Il piano alternativo sposta la luce a {win['ZONE_1_LEAFY']} (zona 1) e {win['ZONE_2_WARM']} (zona 2), "
                     f"mantiene il DLI ({sim['proposed']['dli']['ZONE_1_LEAFY']} mol/m²/d in zona 1) e risparmia "
                     f"{-sim['delta_cost_eur']:.2f} €/giorno. Invio la proposta al Level 0.",
                     "submit_proposal", {"overrides": {"prefer_dark_window_hours": dark}, "duration_h": 12,
                                         "rationale": f"PUN alto senza FV nelle ore {dark}"})
    decision = {
        "diagnosi": RULES_BY_ID["RULE_04_ENERGY_PRICE_SPIKE"]["diagnosis"],
        "evidenze": [f"ore care con LED accesi: {overlap}", f"risparmio stimato {-sim['delta_cost_eur']:.2f} €/giorno",
                     f"DLI mantenuto: {sim['proposed']['dli']}"],
        "azioni": [f"finestra buia {dark[0]:02d}:00–{dark[-1] + 1:02d}:00 per 12 h"],
        "solver_override": sub.get("applied_overrides"), "verdetto_l0": sub["verdict"], "confidenza": 0.9,
        "richiede_umano": False,
        "messaggio_operatore": f"Illuminazione spostata fuori dalle ore care: risparmio {-sim['delta_cost_eur']:.2f} €/giorno.",
    }
    return _final(f"La proposta è stata {_verdict_text(sub['verdict'])} dal Level 0: nuovo piano attivo.", decision)


# ---------------------------------------------------------------------- policy: conflitto tra regole
def policy_rule_conflict(task: dict, obs: Obs):
    zone = task["zone_id"]
    r01 = RULES_BY_ID["RULE_01_HUMIDITY_TIPBURN"]["solver_override"]
    sensors = obs.last("read_sensors")
    if not sensors:
        return _call(f"Sono attive insieme RULE_01 (umidità) e RULE_04 (energia cara) nella {_zl(zone)}. "
                     f"Leggo i sensori prima di decidere.", "read_sensors", {"zone_id": zone})
    rh = sensors["readings"]["SENS_RH_AIR_PCT"]
    ef = obs.last("get_energy_forecast")
    if not ef:
        return _call(f"Umidità {rh}%, rischio tipburn {sensors['readings']['CV_TIPBURN_RISK']:.2f}. "
                     f"Controllo i prezzi delle prossime ore.", "get_energy_forecast", {"hours": 8})
    dark = [h for h in ef["expensive_hours_no_pv"] if h in ef["led_on_hours_in_window"]] or ef["expensive_hours_no_pv"][:4]
    sims = obs.all("simulate_plan")
    if len(sims) == 0:
        return _call("Le due regole chiedono cose opposte: RULE_01 vuole più ventilazione (1500 m³/h, più consumo), "
                     "RULE_04 vuole ridurre i consumi nelle ore care. Applicarle alla cieca significa ventilare al "
                     "massimo proprio quando l'energia costa di più. Simulo prima la sola RULE_01, lasciando i LED "
                     "accesi come nel piano attuale, come riferimento.",
                     "simulate_plan", {"overrides": {**r01, "keep_current_light_window": True}})
    combined = {"prefer_dark_window_hours": dark, "rh_max_pct": 65.0, "vent_min_m3_h": 1000.0}
    if len(sims) == 1:
        return _call(f"Solo RULE_01 costerebbe {sims[0]['delta_cost_eur']:+.2f} €/giorno. Alternativa: spegnere i LED "
                     f"nelle ore care {dark} riduce anche la traspirazione, quindi produce meno umidità. "
                     f"Così basta un limite di umidità meno stretto (65%) e una ventilazione più moderata. "
                     f"Simulo la soluzione combinata.",
                     "simulate_plan", {"overrides": combined})
    sub = obs.last("submit_proposal")
    if not sub:
        a, b = sims[0]["delta_cost_eur"], sims[1]["delta_cost_eur"]
        return _call(f"La soluzione combinata costa {b:+.2f} €/giorno contro {a:+.2f} € della sola RULE_01: "
                     f"risparmia {a - b:.2f} € e affronta comunque l'umidità. La propongo al Level 0.",
                     "submit_proposal", {"overrides": combined, "duration_h": 8,
                                         "rationale": "Mediazione tra RULE_01 e RULE_04"})
    if not obs.last("notify_operator"):
        return _call("Proposta approvata. Avviso l'operatore che ho mediato tra due regole, così può verificare.",
                     "notify_operator", {"severity": "info",
                                         "message": f"Conflitto RULE_01/RULE_04 in {_zl(zone)} risolto: LED spenti nelle ore {dark}, "
                                                    f"umidità max 65% con ventilazione moderata (L0: {sub['verdict']})."})
    a, b = sims[0]["delta_cost_eur"], sims[1]["delta_cost_eur"]
    decision = {
        "diagnosi": "Umidità alta durante una fascia di prezzo elevato: regole in conflitto",
        "evidenze": [f"umidità {rh}%", f"ore care con LED accesi: {dark}",
                     f"solo RULE_01: {a:+.2f} €/giorno", f"soluzione combinata: {b:+.2f} €/giorno"],
        "azioni": ["LED spenti nelle ore care", "umidità massima 65% con ventilazione moderata", "ventilazione minima 1000 m³/h"],
        "solver_override": sub.get("applied_overrides"), "verdetto_l0": sub["verdict"], "confidenza": 0.78,
        "richiede_umano": False,
        "messaggio_operatore": "Ho combinato le due regole invece di applicarle separatamente: stesso effetto sull'umidità, costo minore.",
    }
    return _final("Decisione presa ragionando oltre la tabella delle regole.", decision)


# ---------------------------------------------------------------------- policy: richiesta operatore (proposta pericolosa)
def policy_operator_request(task: dict, obs: Obs):
    shelves = obs.last("get_shelf_status")
    if not shelves:
        return _call(f"L'operatore chiede: \"{task['text']}\". Controllo lo stato dei ripiani.", "get_shelf_status", {})
    crop = task.get("crop_id", "basilico")
    sh = next(s for s in shelves["shelves"] if s["crop_id"] == crop)
    targets = obs.last("get_crop_targets")
    if not targets:
        return _call(f"{CROPS[crop]['name']} sul ripiano {sh['level']}: giorno {sh['day_of_cycle']}, "
                     f"{sh['days_to_harvest']} giorni alla raccolta, {sh['biomass_kg']} kg. Verifico i parametri di luce.",
                     "get_crop_targets", {"crop_id": crop})
    subs = obs.all("submit_proposal")
    if not subs:
        return _call(f"Il target è {targets['dli_target_mol_m2_d']} mol/m²/d con {targets['photoperiod_h']} h di luce. "
                     f"Per accelerare al massimo porto i LED a 30000 W e il fotoperiodo a 22 ore.",
                     "submit_proposal", {"overrides": {"led_max_power_w": 30000, "photoperiod_h": 22}, "duration_h": 48,
                                         "rationale": "Accelerare la crescita su richiesta dell'operatore"})
    first = subs[0]
    reasons = "; ".join(c["reason"] for c in first["checks"] if c["outcome"] in ("BLOCKED", "CLIPPED"))
    sim = obs.last("simulate_plan")
    if first["verdict"] == "BLOCKED" and not sim:
        return _call(f"Il Level 0 ha BLOCCATO la proposta: {reasons}. Ho sbagliato a ignorare i limiti hardware e il "
                     f"buio obbligatorio. Riformulo: potenza entro il limite e 18 ore di luce (6 di buio). Simulo prima l'effetto.",
                     "simulate_plan", {"overrides": {"photoperiod_h": 18}})
    if len(subs) == 1:
        dli = sim["proposed"]["dli"]["ZONE_2_WARM"]
        planned, target = (float(x) for x in dli.split("/"))
        gain = planned / target
        days = sh["days_to_harvest"]
        new_days = max(0, round(days / gain, 1))
        return _call(f"Con 18 h di luce il DLI del basilico arriva a {planned:.1f} mol/m²/d ({(gain - 1) * 100:+.0f}%): "
                     f"raccolta stimata in {new_days} giorni invece di {days}. Costo {sim['delta_cost_eur']:+.2f} €/giorno. "
                     f"Invio la proposta corretta.", "submit_proposal",
                     {"overrides": {"photoperiod_h": 18}, "duration_h": 48,
                      "rationale": "Accelerazione entro i limiti di sicurezza"})
    second = subs[-1]
    if not obs.last("notify_operator"):
        return _call(f"Seconda proposta {_verdict_text(second['verdict'])}. Informo l'operatore che la richiesta è stata "
                     f"accolta solo in parte.", "notify_operator",
                     {"severity": "info", "message": "Richiesta accolta in parte: fotoperiodo esteso a 18 h per 48 h. "
                                                     "La prima proposta (30 kW, 22 h di luce) è stata bloccata da L0."})
    decision = {
        "diagnosi": "Richiesta di accelerare la crescita del basilico",
        "evidenze": [f"prima proposta bloccata da L0: {reasons}", f"seconda proposta: {second['verdict']}",
                     f"costo aggiuntivo {sim['delta_cost_eur']:+.2f} €/giorno"],
        "azioni": ["fotoperiodo 18 h per 48 h"], "solver_override": second.get("applied_overrides"),
        "verdetto_l0": second["verdict"], "confidenza": 0.7, "richiede_umano": False,
        "messaggio_operatore": "Ho accelerato il basilico entro i limiti di sicurezza; la richiesta originale avrebbe violato il buio obbligatorio.",
    }
    return _final("Il Level 0 ha corretto il mio errore iniziale; la versione finale rispetta tutti i vincoli.", decision)


# ---------------------------------------------------------------------- policy: raccolta e menu
def policy_harvest_planning(task: dict, obs: Obs):
    fc = obs.last("get_harvest_forecast")
    if not fc:
        return _call("Pianificazione giornaliera: controllo i ripiani pronti nei prossimi 2 giorni e la dispensa.",
                     "get_harvest_forecast", {"days": 2})
    harvested_levels = {r["harvested"]["level"] for r in obs.all("schedule_harvest") if "harvested" in r}
    ready = [i for i in fc["items"] if i["days_to_harvest"] == 0 and i["level"] not in harvested_levels]
    if ready:
        it = ready[0]
        return _call(f"Il ripiano {it['level']} ({CROPS[it['crop_id']]['name']}) è pronto: circa {it['edible_kg']} kg "
                     f"commestibili, conservabili {it['max_storage_days']} giorni. Lo faccio raccogliere oggi.",
                     "schedule_harvest", {"level": it["level"]})
    inv = (obs.last("schedule_harvest") or fc)["inventory"]
    if not inv and not obs.last("draft_menu"):
        return _final("Nessun prodotto pronto né in dispensa: nessun menu da proporre oggi.",
                      {"diagnosi": "Nessuna raccolta prevista", "evidenze": [], "azioni": [], "solver_override": None,
                       "verdetto_l0": None, "confidenza": 0.9, "richiede_umano": False,
                       "messaggio_operatore": "Nessuna azione oggi."})
    menu_res = obs.last("draft_menu")
    if not menu_res:
        first = sorted(inv, key=lambda i: i["expiry"])[0]
        stock = ", ".join(f"{i['crop_id']} {i['kg']} kg" for i in inv)
        return _call(f"In dispensa: {stock}. Applico FEFO: {first['crop_id']} scade per primo ({first['expiry']}). "
                     f"Cerco le ricette della mensa che lo usano.", "draft_menu", {"focus_crop": first["crop_id"]})
    menu = menu_res.get("menu")
    if menu and not obs.last("notify_operator"):
        return _call(f"Ricetta scelta: \"{menu['title']}\" per {menu['servings']} porzioni "
                     f"({menu['coverage_pct']}% dei {menu_res['daily_meals_average']} pasti giornalieri). "
                     f"Chiedo l'approvazione alla mensa.", "notify_operator",
                     {"severity": "info", "message": f"Menu proposto per {menu['target_date']}: {menu['title']} "
                                                     f"({menu['servings']} porzioni). In attesa di approvazione."})
    harvested = [r["harvested"] for r in obs.all("schedule_harvest")]
    decision = {
        "diagnosi": "Pianificazione raccolta e menu",
        "evidenze": [f"raccolti oggi: " + (", ".join(f"{h['crop_id']} {h['quantity_kg']} kg" for h in harvested) or "nessuno"),
                     f"dispensa: {menu_res['stock_kg']}"],
        "azioni": [f"menu {menu['id']}: {menu['title']} ({menu['servings']} porzioni)"] if menu else ["nessun menu"],
        "solver_override": None, "verdetto_l0": None, "confidenza": 0.88, "richiede_umano": bool(menu),
        "messaggio_operatore": (f"Proposto \"{menu['title']}\" per {menu['servings']} porzioni, valore {menu['value_eur']} €. "
                                f"Serve l'approvazione della mensa.") if menu else "Nessun menu possibile.",
    }
    return _final("Pianificazione completata.", decision)


# ---------------------------------------------------------------------- policy: chat
def policy_chat(task: dict, obs: Obs):
    q = task["question"].lower()
    if any(k in q for k in ("temperatur", "umid", "ph", "ec ", "clima", "sensor")):
        if obs.count("read_sensors") == 0:
            return _call("Leggo i sensori della zona 1.", "read_sensors", {"zone_id": "ZONE_1_LEAFY"})
        if obs.count("read_sensors") == 1:
            return _call("Leggo anche la zona 2.", "read_sensors", {"zone_id": "ZONE_2_WARM"})
        a, b = obs.all("read_sensors")
        ra, rb = a["readings"], b["readings"]
        return _final("", f"Zona 1 (foglia): {ra['SENS_T_AIR_C']} °C, umidità {ra['SENS_RH_AIR_PCT']}%. "
                          f"Zona 2 (calda): {rb['SENS_T_AIR_C']} °C, umidità {rb['SENS_RH_AIR_PCT']}%. "
                          f"Soluzione nutritiva: pH {ra['SENS_SOL_PH']}, EC {ra['SENS_SOL_EC_MS_CM']} mS/cm.")
    if any(k in q for k in ("energia", "costo", "prezzo", "pun", "fotovolt", "solare")):
        ef = obs.last("get_energy_forecast")
        if not ef:
            return _call("Controllo prezzi e fotovoltaico.", "get_energy_forecast", {"hours": 12})
        cheap = min(ef["rows"], key=lambda r: r["pun_eur_kwh"])
        return _final("", f"Ora il PUN è {ef['pun_now']:.3f} €/kWh e il fotovoltaico produce {ef['pv_now_w']} W. "
                          f"L'ora più economica delle prossime 12 è le {cheap['hour']:02d}:00 ({cheap['pun_eur_kwh']:.3f} €/kWh). "
                          f"I LED sono pianificati nelle ore {ef['led_on_hours_in_window']}.")
    if any(k in q for k in ("raccol", "matur", "pront", "menu", "menù", "dispensa")):
        fc = obs.last("get_harvest_forecast")
        if not fc:
            return _call("Controllo raccolti previsti e dispensa.", "get_harvest_forecast", {"days": 7})
        items = "; ".join(f"ripiano {i['level']} {i['crop_id']} tra {i['days_to_harvest']} gg (~{i['edible_kg']} kg)"
                          for i in fc["items"]) or "nessun raccolto nei prossimi 7 giorni"
        inv = ", ".join(f"{i['crop_id']} {i['kg']} kg" for i in fc["inventory"]) or "vuota"
        return _final("", f"Raccolti previsti: {items}. Dispensa: {inv}.")
    sh = obs.last("get_shelf_status")
    if not sh:
        return _call("Domanda generica: leggo lo stato dei ripiani.", "get_shelf_status", {})
    txt = "; ".join(f"ripiano {s['level']} {s['crop_id']} ({s['status']}, {s['days_to_harvest']} gg)" for s in sh["shelves"])
    return _final("", f"Stato della serra: {txt}. Puoi chiedermi di clima, energia, raccolti o menu.")


POLICIES = {
    "rule_anomaly": policy_rule_anomaly,
    "energy_price": policy_energy_price,
    "rule_conflict": policy_rule_conflict,
    "operator_request": policy_operator_request,
    "harvest_planning": policy_harvest_planning,
    "chat": policy_chat,
}


class MockLLM:
    name = MODEL_NAME

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        task = parse_task_message(next(m["content"] for m in messages if m["role"] == "user"))
        obs = Obs()
        pending: dict[str, tuple[str, dict]] = {}
        for m in messages:
            if m["role"] == "assistant":
                for tc in m.get("tool_calls") or []:
                    pending[tc["id"]] = (tc["function"]["name"], tc["function"]["arguments"])
            elif m["role"] == "tool":
                name, args = pending.get(m.get("tool_call_id"), (m.get("name"), {}))
                obs.calls.append((name, args, json.loads(m["content"])))
        # La policy è senza stato: tutto viene ricostruito dalla conversazione, come per un LLM vero.
        out = POLICIES[task["type"]](task, obs)
        n = len([m for m in messages if m["role"] == "assistant"])
        if out[0] == "call":
            _, thought, name, args = out
            msg = {"role": "assistant", "content": thought,
                   "tool_calls": [{"id": f"call_{n + 1}", "type": "function",
                                   "function": {"name": name, "arguments": args}}]}
        else:
            _, thought, decision = out
            content = decision if isinstance(decision, str) else json.dumps(decision, ensure_ascii=False)
            msg = {"role": "assistant", "content": content, "thinking": thought}
        tokens = max(12, len(json.dumps(msg, ensure_ascii=False)) // 4)
        return {"model": self.name, "message": msg, "done": True,
                "eval_count": tokens, "prompt_eval_count": sum(len(str(m.get("content", ""))) for m in messages) // 4,
                "total_duration_ms": 350 + tokens * 18}
