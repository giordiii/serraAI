"""Traduce lo stato del motore nel formato atteso dal frontend React."""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from .config import (CANTEEN, COSTS, CROPS, METADATA, STEPS_PER_HOUR, ZONE_LABELS, ZONES)
from .engine import Engine
from .scenarios import SCENARIOS

LAYER_NAMES = {"L0_SAFETY": "Safety Gate deterministico", "L1_OPTIMIZER": "Optimizer energetico",
               "L2_ORCHESTRATOR": "Orchestratore LLM"}


def _vpd(t: float, rh: float) -> float:
    es = 0.6108 * 2.71828 ** (17.27 * t / (t + 237.3))
    return round(es * (1 - rh / 100), 2)


def _health(z: dict) -> float:
    h = 100 * z["CV_GREENNESS_INDEX"] / 0.88 - 60 * max(0, z["CV_TIPBURN_RISK"] - 0.05) - 60 * max(0, z["CV_WILTING_SCORE"] - 0.02)
    return round(max(40, min(99, h)), 0)


def run_summary(run: dict) -> dict:
    d = run.get("decision")
    return {"id": run["id"], "title": run["trigger"]["title"], "type": run["type"], "started_at": run["started_at"],
            "model": run["model"], "tool_calls": run["tool_calls"], "tokens": run["tokens"],
            "verdict": d.get("verdetto_l0") if isinstance(d, dict) else None,
            "summary": (d.get("messaggio_operatore") if isinstance(d, dict) else d) or run.get("error"),
            "diagnosis": d.get("diagnosi") if isinstance(d, dict) else None, "error": run.get("error")}


def snapshot(engine: Engine) -> dict:
    sim = engine.sim
    now = sim.now

    zones = [{"id": zid, "name": ZONE_LABELS[zid], "levels": z["levels"], "area_m2": z["area_m2"],
              "crops": sim.crops_by_zone()[zid]} for zid, z in ZONES.items()]

    def reading(rec, zid, i):
        z = rec["zones"][zid]
        return {"id": f"t-{rec['step']}-{zid}", "zone_id": zid, "temp": round(z["SENS_T_AIR_C"], 1),
                "humidity": round(z["SENS_RH_AIR_PCT"], 1), "vpd": _vpd(z["SENS_T_AIR_C"], z["SENS_RH_AIR_PCT"]),
                "ph": round(rec["solution"]["SENS_SOL_PH"], 2), "ec": round(rec["solution"]["SENS_SOL_EC_MS_CM"], 2),
                "light": round(z["SENS_PAR_PPFD"]), "co2": round(z["SENS_CO2_PPM"]),
                "tipburn": round(z["CV_TIPBURN_RISK"], 2), "wilting": round(z["CV_WILTING_SCORE"], 2),
                "greenness": round(z["CV_GREENNESS_INDEX"], 2), "led_w": round(z["led_w"]),
                "vent_m3h": round(z["vent_m3h"] * len(ZONES)), "timestamp": rec["at"], "data_origin": "SIMULATED"}

    latest = sim.history[-1]
    telemetry = [reading(latest, zid, 0) for zid in ZONES]
    hist = sim.history[-12 * STEPS_PER_HOUR:]
    history = {zid: [reading(r, zid, i) for i, r in enumerate(hist)] for zid in ZONES}
    power_hist = [{"timestamp": r["at"], **r["power"]} for r in hist]

    batches = []
    for sh in sim.shelves:
        crop = CROPS[sh["crop_id"]]
        z = latest["zones"][sh["zone_id"]]
        batches.append({
            "id": f"shelf-{sh['level']}", "level": sh["level"], "zone_id": sh["zone_id"], "crop_id": sh["crop_id"],
            "crop_name": crop["name"], "health_score": _health(z),
            "maturity_pct": round(min(100, 100 * sh["day_of_cycle"] / crop["cycle_days"]), 1),
            "estimated_yield_kg": round(sh["harvestable_biomass_kg"] * crop["post_harvest_storage"]["edible_fraction_after_trimming"], 1),
            "estimated_harvest_date": (now + timedelta(days=sh["days_to_harvest"])).date().isoformat(),
            "days_to_harvest": sh["days_to_harvest"], "status": sh["status"], "last_vision_check": latest["at"],
        })

    inventory = []
    for it in sim.inventory:
        if it["quantity_kg"] <= 0:
            continue
        days_left = (datetime.fromisoformat(it["expiry"]) - now).total_seconds() / 86400
        inventory.append({"id": it["id"], "crop_name": it["crop_name"], "crop_id": it["crop_id"],
                          "quantity_kg": it["quantity_kg"], "harvested_at": it["harvested_at"],
                          "expiry_date": it["expiry"][:10],
                          "fefo_status": "urgent" if days_left <= 1 else "warning" if days_left <= 2 else "fresh",
                          "source_batch_id": f"shelf-{it['level']}", "value_eur": it["value_eur"]})

    menus = []
    for m in sim.menus:
        ingredients = []
        for crop_id, kg in m["greenhouse_kg"].items():
            inv = next((i for i in sim.inventory if i["crop_id"] == crop_id and i["quantity_kg"] > 0), None)
            ingredients.append({"inventory_item_id": inv["id"] if inv else None, "crop_name": CROPS[crop_id]["name"],
                                "crop_id": crop_id, "quantity_kg": kg})
        menus.append({"id": m["id"], "target_date": m["target_date"], "title": m["title"], "course": m["course"],
                      "servings": m["servings"], "coverage_pct": m["coverage_pct"],
                      "self_sufficiency_pct": round(100 * sum(m["greenhouse_kg"].values())
                                                    / max(0.1, sum(m["greenhouse_kg"].values()) + sum(m.get("to_buy_kg", {}).values()))),
                      "serra_ingredients": ingredients,
                      "external_shopping_list": [{"name": f"{CROPS[c]['name']} (non disponibile in serra)", "quantity": f"{kg} kg"}
                                                 for c, kg in m.get("to_buy_kg", {}).items()], "status": m["status"],
                      "value_eur": m["value_eur"], "territorial_link": m["territorial_link"]})

    logs = []
    for run in engine.runs[:30]:
        s = run_summary(run)
        logs.append({"id": f"log-{run['id']}", "run_id": run["id"], "agent_layer": "L2_ORCHESTRATOR",
                     "agent_name": run["model"], "action_summary": s["title"], "reasoning": s["summary"] or "",
                     "timestamp": run["started_at"], "verdict": s["verdict"]})
    for e in sim.l0_log[:20]:
        bad = [c["reason"] for c in e["checks"] if c["outcome"] in ("BLOCKED", "CLIPPED")]
        logs.append({"id": f"log-{e['id']}", "agent_layer": "L0_SAFETY", "agent_name": "Safe Action Gate",
                     "action_summary": f"Proposta {e['id']}: {e['verdict']}",
                     "reasoning": "; ".join(bad) or "Tutti i controlli sui limiti fisici e biologici superati.",
                     "timestamp": e["at"], "verdict": e["verdict"]})
    p = sim.plan
    logs.append({"id": f"log-plan-{p['computed_at']}", "agent_layer": "L1_OPTIMIZER", "agent_name": "Optimizer 24 h",
                 "action_summary": f"Piano aggiornato: {p['reason']}",
                 "reasoning": f"Luce zona 1 {p['zones']['ZONE_1_LEAFY']['light_window']['label']}, zona 2 "
                              f"{p['zones']['ZONE_2_WARM']['light_window']['label']}. Costo previsto {p['energy']['cost_eur']:.2f} €/giorno, "
                              f"{p['energy']['pv_share_pct']}% da fotovoltaico.", "timestamp": p["computed_at"]})
    logs.sort(key=lambda x: x["timestamp"], reverse=True)

    wall = time.time()
    heartbeats = [{"agent_layer": k, "agent_name": LAYER_NAMES[k],
                   "last_heartbeat": datetime.fromtimestamp(v if engine.running else wall).astimezone().isoformat(),
                   "status": "online"} for k, v in engine.heartbeat.items()]

    water = COSTS["water_tariff_abc_napoli"]
    e_today = {k: round(v, 2) for k, v in sim.energy_today.items()}
    pv_share = round(100 * e_today["pv_kwh"] / e_today["load_kwh"], 1) if e_today["load_kwh"] else 0.0

    return {
        "sim": {"time": sim.iso(), "step": sim.step_count, "running": engine.running, "speed": engine.speed,
                "mode": "SIMULATION", "llm_model": engine.llm.name, "project": METADATA["project_name"],
                "site": METADATA["site"], "canteen": CANTEEN["canteen_name"],
                "active_scenario": engine.active_scenario,
                "active_overrides": [{"key": k, "value": v, "expires_step": sim.override_expiry.get(k)}
                                     for k, v in sim.overrides.items()],
                "disturbances": [d["label"] for d in sim.disturbances]},
        "zones": zones, "telemetry_readings": telemetry, "telemetry_history": history, "power_history": power_hist,
        "crop_batches": batches, "inventory_items": inventory, "generated_menus": menus, "agent_logs": logs,
        "agent_heartbeats": heartbeats, "agent_runs": [run_summary(r) for r in engine.runs[:30]],
        "events": sim.events[:15], "l0_log": sim.l0_log[:15],
        "energy": {"today": e_today, "total": {k: round(v, 2) for k, v in sim.energy_total.items()},
                   "now": latest["power"], "pv_share_today_pct": pv_share,
                   "plan": {"computed_at": p["computed_at"], "reason": p["reason"],
                            "light_windows": {z: v["light_window"]["label"] for z, v in p["zones"].items()},
                            "dli": {z: {"planned": v["dli_planned"], "target": v["dli_target"]} for z, v in p["zones"].items()},
                            "hourly": p["hourly_total"], "cost_eur": p["energy"]["cost_eur"],
                            "pv_share_pct": p["energy"]["pv_share_pct"], "saving_vs_fixed_pct": p["saving_vs_fixed_pct"],
                            "binding_constraints": p["binding_constraints"], "method": p["method"]}},
        "kpi": {"water_saving_pct": round(100 * (1 - water["cea_water_use_l_per_kg_yield"] / water["open_field_campania_benchmark_l_per_kg"]), 1),
                "harvested_kg": round(sim.harvested_kg, 1), "harvest_value_eur": round(sim.revenue_eur, 2),
                "energy_cost_today_eur": e_today["cost_eur"], "pv_share_today_pct": pv_share,
                "daily_meals": CANTEEN["daily_meals_average"]},
        "scenarios": SCENARIOS,
        "human_override_events": [],
    }
