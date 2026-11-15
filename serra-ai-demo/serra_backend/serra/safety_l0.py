"""Level 0 · Safety Gate deterministico (nessuna IA).

Ogni proposta del Level 2 e ogni comando del Level 1 passa da qui.
Verdetti:
  ALLOWED  -> proposta entro i limiti
  CLIPPED  -> proposta corretta riportando i valori entro i limiti
  BLOCKED  -> proposta rifiutata (violazione grave o biologica)
"""
from __future__ import annotations

from .config import CROPS, L0_LIMITS, ZONES

# Oltre questa percentuale sopra il limite la proposta non viene corretta ma bloccata.
BLOCK_MARGIN = 0.20


def _check(param, requested, limit, outcome, reason, applied=None):
    return {"param": param, "requested": requested, "limit": limit,
            "outcome": outcome, "reason": reason, "applied": applied}


def validate_proposal(proposal: dict, current: dict | None = None) -> dict:
    """Valida un override proposto. `current` contiene lo stato utile (es. EC attuale)."""
    current = current or {}
    checks: list[dict] = []
    applied = dict(proposal)

    led_max = L0_LIMITS["led_max_power_w"]
    if "led_max_power_w" in proposal:
        v = float(proposal["led_max_power_w"])
        if v < 0:
            checks.append(_check("led_max_power_w", v, f"0–{led_max:.0f} W", "BLOCKED", "Potenza negativa non valida"))
        elif v > led_max * (1 + BLOCK_MARGIN):
            checks.append(_check("led_max_power_w", v, f"≤ {led_max:.0f} W", "BLOCKED",
                                 f"Potenza LED richiesta oltre il limite hardware di {led_max:.0f} W"))
        elif v > led_max:
            applied["led_max_power_w"] = led_max
            checks.append(_check("led_max_power_w", v, f"≤ {led_max:.0f} W", "CLIPPED",
                                 "Potenza LED ridotta al massimo hardware", led_max))
        else:
            checks.append(_check("led_max_power_w", v, f"≤ {led_max:.0f} W", "OK", "Entro i limiti"))

    min_dark = L0_LIMITS["mandatory_min_dark_hours"]
    if "photoperiod_h" in proposal:
        v = float(proposal["photoperiod_h"])
        dark = 24 - v
        if dark < min_dark:
            checks.append(_check("photoperiod_h", v, f"≤ {24 - min_dark} h di luce", "BLOCKED",
                                 f"Solo {dark:.0f} h di buio: il minimo biologico obbligatorio è {min_dark} h"))
        else:
            checks.append(_check("photoperiod_h", v, f"≤ {24 - min_dark} h di luce", "OK",
                                 f"{dark:.0f} h di buio garantite"))

    vmin, vmax = L0_LIMITS["vent_min_max_m3_h"]
    if "vent_min_m3_h" in proposal:
        v = float(proposal["vent_min_m3_h"])
        if v < vmin or v > vmax:
            clipped = min(max(v, vmin), vmax)
            applied["vent_min_m3_h"] = clipped
            checks.append(_check("vent_min_m3_h", v, f"{vmin:.0f}–{vmax:.0f} m³/h", "CLIPPED",
                                 "Portata riportata nel range dei ventilatori", clipped))
        else:
            checks.append(_check("vent_min_m3_h", v, f"{vmin:.0f}–{vmax:.0f} m³/h", "OK", "Entro i limiti"))

    if "rh_max_pct" in proposal:
        v = float(proposal["rh_max_pct"])
        if v < 45 or v > 85:
            clipped = min(max(v, 45.0), 85.0)
            applied["rh_max_pct"] = clipped
            checks.append(_check("rh_max_pct", v, "45–85 %", "CLIPPED", "Setpoint umidità fuori range sicuro", clipped))
        else:
            checks.append(_check("rh_max_pct", v, "45–85 %", "OK", "Entro i limiti"))

    if "temp_target_offset_c" in proposal:
        v = float(proposal["temp_target_offset_c"])
        # Limite biologico: il nuovo target deve restare nei range di tutte le colture.
        lo, hi = -99.0, 99.0
        for z in ZONES.values():
            for cid in z["crops_allowed"]:
                p = CROPS[cid]["ideal_params"]
                lo = max(lo, p["temp_min_max_c"][0] - p["temp_opt_c"] + 2)
                hi = min(hi, p["temp_min_max_c"][1] - p["temp_opt_c"] - 2)
        if v < lo or v > hi:
            clipped = round(min(max(v, lo), hi), 1)
            applied["temp_target_offset_c"] = clipped
            checks.append(_check("temp_target_offset_c", v, f"{lo:+.1f}…{hi:+.1f} °C", "CLIPPED",
                                 "Offset ridotto per restare nei range biologici delle colture", clipped))
        else:
            checks.append(_check("temp_target_offset_c", v, f"{lo:+.1f}…{hi:+.1f} °C", "OK", "Entro i range colturali"))

    ph_lo, ph_hi = L0_LIMITS["ph_hard_safety_bounds"]
    if "ph_setpoint" in proposal:
        v = float(proposal["ph_setpoint"])
        if v < ph_lo - 0.5 or v > ph_hi + 0.5:
            checks.append(_check("ph_setpoint", v, f"{ph_lo}–{ph_hi}", "BLOCKED", "pH richiesto pericoloso per le radici"))
        elif v < ph_lo or v > ph_hi:
            clipped = min(max(v, ph_lo), ph_hi)
            applied["ph_setpoint"] = clipped
            checks.append(_check("ph_setpoint", v, f"{ph_lo}–{ph_hi}", "CLIPPED", "pH riportato nei limiti", clipped))
        else:
            checks.append(_check("ph_setpoint", v, f"{ph_lo}–{ph_hi}", "OK", "Entro i limiti"))

    ec_max = L0_LIMITS["ec_hard_safety_max_ms_cm"]
    if "ec_setpoint_offset_ms_cm" in proposal:
        v = float(proposal["ec_setpoint_offset_ms_cm"])
        ec_now = float(current.get("SENS_SOL_EC_MS_CM", 1.6))
        if ec_now + v > ec_max:
            clipped = round(ec_max - ec_now, 2)
            applied["ec_setpoint_offset_ms_cm"] = clipped
            checks.append(_check("ec_setpoint_offset_ms_cm", v, f"EC finale ≤ {ec_max}", "CLIPPED",
                                 "Offset EC ridotto per non superare il limite di salinità", clipped))
        else:
            checks.append(_check("ec_setpoint_offset_ms_cm", v, f"EC finale ≤ {ec_max}", "OK",
                                 f"EC risultante {ec_now + v:.2f} mS/cm"))

    if "prefer_dark_window_hours" in proposal:
        hours = proposal["prefer_dark_window_hours"]
        ok = all(isinstance(h, int) and 0 <= h <= 23 for h in hours)
        checks.append(_check("prefer_dark_window_hours", hours, "ore 0–23",
                             "OK" if ok else "BLOCKED", "Finestra oraria valida" if ok else "Ore non valide"))

    outcomes = {c["outcome"] for c in checks}
    verdict = "BLOCKED" if "BLOCKED" in outcomes else "CLIPPED" if "CLIPPED" in outcomes else "ALLOWED"
    return {"verdict": verdict, "checks": checks,
            "applied": applied if verdict != "BLOCKED" else None}


def clip_actuators(cmd: dict) -> tuple[dict, list[str]]:
    """Clipping per-step dei comandi agli attuatori (ultima barriera)."""
    notes = []
    out = dict(cmd)
    vmin, vmax = L0_LIMITS["vent_min_max_m3_h"]
    if out["vent_m3h"] < vmin or out["vent_m3h"] > vmax:
        out["vent_m3h"] = min(max(out["vent_m3h"], vmin), vmax)
        notes.append("vent clipped")
    if out["hvac_heat_w"] > L0_LIMITS["hvac_max_heating_w"]:
        out["hvac_heat_w"] = L0_LIMITS["hvac_max_heating_w"]
        notes.append("heating clipped")
    if out["hvac_cool_w"] > L0_LIMITS["hvac_max_cooling_w"]:
        out["hvac_cool_w"] = L0_LIMITS["hvac_max_cooling_w"]
        notes.append("cooling clipped")
    return out, notes
