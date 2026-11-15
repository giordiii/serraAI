"""Level 1 · Optimizer (versione dimostrativa, euristica senza solver).

Idea: per ogni zona serve una certa quantità di luce al giorno (DLI).
L'optimizer sceglie la finestra luminosa CONTINUA di N ore che costa meno,
dove il costo orario è il PUN pesato per la quota di carico non coperta dal
fotovoltaico. Rispetta le ore di buio obbligatorie e gli override del Level 2.

Versione futura: programmazione lineare / MPC con gli stessi input e output.
"""
from __future__ import annotations

import math

from .config import (CROPS, ESTIMATES, L0_LIMITS, PROFILE, SOLVER_CFG, ZONES,
                     zone_led_max_w)

PUN = PROFILE["gme_pun_eur_kwh"]
PV = PROFILE["pvgis_25kwp_power_w"]
TEXT = PROFILE["temp_ext_era5_c"]
EFFICACY = L0_LIMITS["led_efficacy_umol_j"]
MOL_PER_UMOL_HOUR = 3600 / 1e6
DARK_PENALTY_EUR = 50.0  # penalità per ora accesa in una finestra che L2 vuole buia


def zone_targets(zone_id: str, crops_on_shelves: list[str]) -> dict:
    crops = [CROPS[c] for c in crops_on_shelves] or [CROPS[ZONES[zone_id]["crops_allowed"][0]]]
    p = [c["ideal_params"] for c in crops]
    return {
        "ppfd": sum(x["ppfd_umol_m2_s"] for x in p) / len(p),
        "dli": sum(x["dli_target_mol_m2_d"] for x in p) / len(p),
        "photoperiod": max(x["photoperiod_h"] for x in p),
        "temp_opt": sum(x["temp_opt_c"] for x in p) / len(p),
        "crops": [c["crop_id"] for c in crops],
    }


def effective_price(hour: int, load_w: float, pun: list[float] | None = None) -> float:
    """€/kWh effettivo: il fotovoltaico copre gratis una parte del carico."""
    pun = pun or PUN
    covered = min(1.0, PV[hour] / load_w) if load_w > 0 else 1.0
    return pun[hour] * (1 - covered)


def _best_window(n_hours: int, load_w: float, forbidden: set[int], pun: list[float]) -> tuple[int, float]:
    best_start, best_cost = 0, float("inf")
    for s in range(24):
        hours = [(s + i) % 24 for i in range(n_hours)]
        cost = sum(effective_price(h, load_w, pun) + (DARK_PENALTY_EUR if h in forbidden else 0) for h in hours)
        if cost < best_cost - 1e-9:
            best_start, best_cost = s, cost
    return best_start, best_cost


def plan(overrides: dict, crops_by_zone: dict[str, list[str]], fixed_reference: bool = False,
         pun: list[float] | None = None) -> dict:
    """Restituisce il piano orario a 24 h per tutte le zone.

    fixed_reference=True calcola il piano "a orario fisso" (luci 6-22, nessun
    risparmio notturno): serve solo come riferimento interno per i KPI.
    """
    pun = list(pun or PUN)
    min_dark = L0_LIMITS["mandatory_min_dark_hours"]
    led_scale = float(overrides.get("led_max_power_w", L0_LIMITS["led_max_power_w"])) / L0_LIMITS["led_max_power_w"]
    forbidden = set(overrides.get("prefer_dark_window_hours", []))
    t_offset = float(overrides.get("temp_target_offset_c", 0.0))
    binding: list[str] = []

    zones_out = {}
    total_led_full = 0.0
    prelim = {}
    for zid, z in ZONES.items():
        t = zone_targets(zid, crops_by_zone.get(zid, []))
        led_max = zone_led_max_w(zid) * min(led_scale, 1.0)
        ppfd_max = led_max * EFFICACY / z["area_m2"]
        ppfd = min(t["ppfd"], ppfd_max)
        hours = max(t["photoperiod"], math.ceil(t["dli"] / (ppfd * MOL_PER_UMOL_HOUR) - 0.05))
        if "photoperiod_h" in overrides:
            hours = int(overrides["photoperiod_h"])
        hours = min(hours, 24 - min_dark)
        if ppfd < t["ppfd"]:
            binding.append(f"{zid}: potenza LED limitata, PPFD {ppfd:.0f} invece di {t['ppfd']:.0f} µmol/m²/s → fotoperiodo esteso a {hours} h")
        led_w = ppfd * z["area_m2"] / EFFICACY
        total_led_full += led_w
        prelim[zid] = (t, ppfd, hours, led_w)

    load_estimate = total_led_full + 2500.0
    for zid, (t, ppfd, hours, led_w) in prelim.items():
        fixed = overrides.get("fixed_light_start", {})
        if fixed_reference:
            start = 6
        elif zid in fixed:
            start = int(fixed[zid])
            binding.append(f"{zid}: finestra luminosa mantenuta come nel piano attuale")
        else:
            start, _ = _best_window(hours, load_estimate, forbidden, pun)
        light_hours = {(start + i) % 24 for i in range(hours)}
        overlap = light_hours & forbidden
        if forbidden and not overlap:
            binding.append(f"{zid}: finestra buia richiesta da L2 ({min(forbidden)}–{max(forbidden) + 1}) rispettata")
        elif overlap:
            binding.append(f"{zid}: impossibile tenere spente tutte le ore {sorted(forbidden)} (servono {hours} h di luce)")
        dli = ppfd * hours * MOL_PER_UMOL_HOUR
        hourly = []
        for h in range(24):
            on = h in light_hours
            sp = t["temp_opt"] + t_offset - (0 if on or fixed_reference else ESTIMATES["dark_setback_c"])
            vent = ESTIMATES["base_vent_m3h"]
            if "rh_max_pct" in overrides:
                # Più il limite di umidità è stretto, più si ventila (62% → massimo previsto).
                strict = min(max((70 - float(overrides["rh_max_pct"])) / 8, 0.0), 1.0)
                vent = ESTIMATES["base_vent_m3h"] + (ESTIMATES["high_vent_m3h"] - ESTIMATES["base_vent_m3h"]) * strict
            vent = max(vent, float(overrides.get("vent_min_m3_h", 0)))
            vent = min(max(vent, L0_LIMITS["vent_min_max_m3_h"][0]), L0_LIMITS["vent_min_max_m3_h"][1])
            hourly.append({"hour": h, "led_on": on, "led_w": round(led_w if on else 0.0, 1),
                           "ppfd": round(ppfd if on else 0.0, 1), "t_setpoint_c": round(sp, 2),
                           "vent_m3h": round(vent / len(ZONES), 1)})
        zones_out[zid] = {
            "light_window": {"start_hour": start, "hours": hours,
                             "label": f"{start:02d}:00 → {(start + hours) % 24:02d}:00"},
            "ppfd": round(ppfd, 1), "dli_planned": round(dli, 2), "dli_target": round(t["dli"], 2),
            "dli_met": dli >= 0.99 * t["dli"], "temp_opt_c": round(t["temp_opt"], 2), "crops": t["crops"],
            "hourly": hourly,
        }
        if dli < 0.99 * t["dli"]:
            binding.append(f"{zid}: DLI pianificato {dli:.1f} sotto il target {t['dli']:.1f} mol/m²/d")

    if "rh_max_pct" in overrides:
        v = zones_out[next(iter(zones_out))]["hourly"][0]["vent_m3h"] * len(zones_out)
        binding.append(f"rh_max {float(overrides['rh_max_pct']):.0f}% → ventilazione portata a {v:.0f} m³/h")
    if "vent_min_m3_h" in overrides:
        binding.append(f"ventilazione minima {float(overrides['vent_min_m3_h']):.0f} m³/h")
    binding.append(f"buio minimo obbligatorio {min_dark} h (L0)")

    # Stima energetica del piano.
    energy = {"led_kwh": 0.0, "hvac_kwh": 0.0, "aux_kwh": 0.0, "pv_used_kwh": 0.0, "grid_kwh": 0.0, "cost_eur": 0.0}
    hourly_total = []
    for h in range(24):
        led = sum(zones_out[z]["hourly"][h]["led_w"] for z in zones_out)
        vent = sum(zones_out[z]["hourly"][h]["vent_m3h"] for z in zones_out)
        sp = sum(zones_out[z]["hourly"][h]["t_setpoint_c"] for z in zones_out) / len(zones_out)
        led_heat_c = ESTIMATES["led_heat_c_per_step_full_power"] * led / L0_LIMITS["led_max_power_w"] * 4
        delta = sp - (TEXT[h] + led_heat_c)
        hvac_th = abs(delta) * 900.0
        hvac_el = hvac_th / L0_LIMITS["hvac_cop"]
        aux = vent * ESTIMATES["fan_w_per_m3h"] + ESTIMATES["pumps_base_w"]
        load = led + hvac_el + aux
        pv_used = min(PV[h], load)
        grid = load - pv_used
        cost = grid / 1000 * pun[h]
        energy["led_kwh"] += led / 1000
        energy["hvac_kwh"] += hvac_el / 1000
        energy["aux_kwh"] += aux / 1000
        energy["pv_used_kwh"] += pv_used / 1000
        energy["grid_kwh"] += grid / 1000
        energy["cost_eur"] += cost
        hourly_total.append({"hour": h, "load_w": round(load), "pv_w": PV[h], "grid_w": round(grid),
                             "pun_eur_kwh": pun[h], "led_w": round(led)})
    energy = {k: round(v, 2) for k, v in energy.items()}
    total = energy["led_kwh"] + energy["hvac_kwh"] + energy["aux_kwh"]
    energy["total_kwh"] = round(total, 2)
    energy["pv_share_pct"] = round(100 * energy["pv_used_kwh"] / total, 1) if total else 0.0

    return {"overrides": overrides, "weights": SOLVER_CFG["weights"], "zones": zones_out,
            "hourly_total": hourly_total, "energy": energy, "binding_constraints": binding,
            "method": "euristica: finestra luminosa continua a costo minimo (PUN × quota non coperta da FV)"}


def plan_with_reference(overrides: dict, crops_by_zone: dict[str, list[str]],
                        pun: list[float] | None = None) -> dict:
    p = plan(overrides, crops_by_zone, pun=pun)
    ref = plan(overrides, crops_by_zone, fixed_reference=True, pun=pun)
    saving = ref["energy"]["cost_eur"] - p["energy"]["cost_eur"]
    p["reference_fixed_schedule"] = {"cost_eur": ref["energy"]["cost_eur"], "grid_kwh": ref["energy"]["grid_kwh"]}
    p["saving_vs_fixed_eur"] = round(saving, 2)
    p["saving_vs_fixed_pct"] = round(100 * saving / ref["energy"]["cost_eur"], 1) if ref["energy"]["cost_eur"] else 0.0
    return p
