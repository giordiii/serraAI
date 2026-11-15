"""Caricamento del dataset e parametri stimati.

Tutti i dati "veri" arrivano da dataset_serra.json (unica fonte di verità).
I parametri che il dataset non contiene sono raccolti in ESTIMATES e sono
dichiaratamente stime semplificate, scelte per ottenere andamenti plausibili.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = BASE_DIR.parent / "dataset_serra.json"
DATASET_PATH = Path(os.environ.get("SERRA_DATASET", DEFAULT_DATASET))

# Passo di simulazione: 15 minuti simulati per tick.
STEP_MINUTES = 15
STEPS_PER_HOUR = 60 // STEP_MINUTES

# Data di partenza della simulazione (lunedì, autunno: coerente con il profilo
# "typical_24h_naples_autumn_profile").
SIM_START_ISO = "2026-11-16T00:00:00+01:00"

# Stato iniziale dei ripiani: "mode_B_operational_steady_state" è più utile in
# demo (rucola pronta oggi, lattuga e basilico vicini alla raccolta).
INITIAL_SHELVES_MODE = os.environ.get("SERRA_INITIAL_MODE", "mode_B_operational_steady_state")

# Parametri NON presenti nel dataset: stime semplificate e dichiarate.
ESTIMATES = {
    "led_heat_c_per_step_full_power": 0.35,   # °C aggiunti per step a LED pieni
    "envelope_exchange_per_step": 0.04,       # quota di scambio termico con l'esterno
    "hvac_gain": 0.55,                         # quanto l'HVAC corregge per step
    "hvac_w_per_c_step": 9000.0,               # W termici per °C corretto in uno step
    "rh_base_pct": 46.0,                       # umidità di equilibrio senza luce/trasp.
    "rh_transpiration_gain_pct": 22.0,         # contributo traspirazione a LED pieni
    "rh_vent_gain_pct": 14.0,                  # effetto ventilazione (rif. 1500 m3/h)
    "rh_response": 0.15,                       # velocità di risposta dell'umidità
    "fan_w_per_m3h": 0.30,                     # potenza ventilatori
    "pumps_base_w": 300.0,                     # pompe e ausiliari
    "base_vent_m3h": 600.0,                    # ventilazione di base
    "high_vent_m3h": 2800.0,                   # ventilazione quando rh_max è attivo
    "dark_setback_c": 2.0,                     # risparmio notturno sulla temperatura
    "ph_drift_per_step": 0.006,
    "ec_drift_per_step": -0.004,
    "dosing_gain": 0.12,
}


def load_dataset() -> dict:
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


DATASET = load_dataset()

GREENHOUSE = DATASET["1_greenhouse_configuration"]
CROPS = {c["crop_id"]: c for c in DATASET["2_crops_and_storage_catalog"]}
ZONES = {z["zone_id"]: z for z in GREENHOUSE["zones"]}
SENSORS_T0 = DATASET["4_sensors_and_actuators_config"]["initial_sensor_readings_t0"]
L0_LIMITS = DATASET["4_sensors_and_actuators_config"]["actuator_hardware_limits_level0"]
SOLVER_CFG = DATASET["4_sensors_and_actuators_config"]["simple_solver_config"]
RULES = DATASET["5_llm_orchestrator_mapping_table"]
COSTS = DATASET["6_verified_naples_public_datasets_costs_and_climate"]
PROFILE = COSTS["typical_24h_naples_autumn_profile"]
CANTEEN = DATASET["7_canteen_demand_and_campanian_menu"]
METADATA = DATASET["metadata"]

ZONE_LABELS = {
    "ZONE_1_LEAFY": "Zona 1 · Foglia (ripiani 1-3)",
    "ZONE_2_WARM": "Zona 2 · Calda (ripiano 4)",
}


def zone_of_level(level: int) -> str:
    for zid, z in ZONES.items():
        if level in z["levels"]:
            return zid
    raise KeyError(level)


def zone_led_max_w(zone_id: str) -> float:
    """La potenza LED massima è ripartita in proporzione all'area della zona."""
    total = GREENHOUSE["total_cultivated_area_m2"]
    return L0_LIMITS["led_max_power_w"] * ZONES[zone_id]["area_m2"] / total
