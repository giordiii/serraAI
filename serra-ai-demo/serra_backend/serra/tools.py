"""Tool a disposizione dell'agente L2.

Sono funzioni Python VERE che leggono e modificano il digital twin.
Le definizioni (TOOL_SPECS) sono nel formato JSON-schema usato da Ollama /
OpenAI per il tool calling: lo stesso elenco può essere passato a un LLM reale.
"""
from __future__ import annotations

from datetime import timedelta

from . import optimizer_l1, safety_l0
from .config import CANTEEN, COSTS, CROPS, PROFILE, ZONES
from .sim import Simulation

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "read_sensors", "description": "Legge le misure attuali dei sensori e degli indici di computer vision di una zona.",
        "parameters": {"type": "object", "properties": {"zone_id": {"type": "string", "enum": list(ZONES)}}, "required": ["zone_id"]}}},
    {"type": "function", "function": {
        "name": "get_sensor_history", "description": "Restituisce l'andamento recente di un sensore, per distinguere un picco isolato da una tendenza.",
        "parameters": {"type": "object", "properties": {"sensor": {"type": "string"}, "zone_id": {"type": "string"},
                                                       "hours": {"type": "number"}}, "required": ["sensor", "zone_id", "hours"]}}},
    {"type": "function", "function": {
        "name": "get_crop_targets", "description": "Parametri agronomici ideali di una coltura (temperatura, umidità, luce, pH, EC).",
        "parameters": {"type": "object", "properties": {"crop_id": {"type": "string", "enum": list(CROPS)}}, "required": ["crop_id"]}}},
    {"type": "function", "function": {
        "name": "get_energy_forecast", "description": "Prezzo PUN e produzione fotovoltaica previsti per le prossime ore.",
        "parameters": {"type": "object", "properties": {"hours": {"type": "integer"}}, "required": ["hours"]}}},
    {"type": "function", "function": {
        "name": "get_shelf_status", "description": "Stato dei ripiani: coltura, giorno del ciclo, biomassa, giorni alla raccolta.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "simulate_plan", "description": "Chiede al Level 1 Optimizer un piano di prova con override ipotetici, senza applicarlo.",
        "parameters": {"type": "object", "properties": {"overrides": {"type": "object"}}, "required": ["overrides"]}}},
    {"type": "function", "function": {
        "name": "submit_proposal", "description": "Invia un override al Safety Gate L0. Se approvato (ALLOWED/CLIPPED) viene applicato e il Level 1 ripianifica.",
        "parameters": {"type": "object", "properties": {"overrides": {"type": "object"}, "duration_h": {"type": "number"},
                                                       "rationale": {"type": "string"}}, "required": ["overrides", "rationale"]}}},
    {"type": "function", "function": {
        "name": "get_harvest_forecast", "description": "Ripiani pronti o in maturazione nei prossimi giorni, con kg commestibili stimati.",
        "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}, "required": ["days"]}}},
    {"type": "function", "function": {
        "name": "schedule_harvest", "description": "Registra la raccolta di un ripiano e sposta il prodotto in dispensa.",
        "parameters": {"type": "object", "properties": {"level": {"type": "integer"}}, "required": ["level"]}}},
    {"type": "function", "function": {
        "name": "draft_menu", "description": "Abbina le ricette della mensa ai prodotti disponibili in dispensa e calcola le porzioni.",
        "parameters": {"type": "object", "properties": {"focus_crop": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {
        "name": "notify_operator", "description": "Crea un avviso per l'operatore umano.",
        "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "severity": {"type": "string", "enum": ["info", "warning", "critical"]}},
                       "required": ["message", "severity"]}}},
]


class Toolbox:
    def __init__(self, sim: Simulation):
        self.sim = sim

    def call(self, name: str, args: dict) -> dict:
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_"):
            return {"error": f"tool sconosciuto: {name}"}
        try:
            return fn(**(args or {}))
        except Exception as exc:  # l'LLM deve ricevere l'errore, non far crollare il sistema
            return {"error": f"{type(exc).__name__}: {exc}"}

    # ------------------------------------------------------------------ lettura
    def read_sensors(self, zone_id: str) -> dict:
        return {"zone_id": zone_id, "at": self.sim.iso(), "readings": self.sim.sensors(zone_id),
                "crops": self.sim.crops_by_zone()[zone_id], "quality": "VALID", "data_origin": "SIMULATED"}

    def get_sensor_history(self, sensor: str, zone_id: str, hours: float = 3) -> dict:
        pts = self.sim.sensor_history(sensor, zone_id, hours)
        vals = [p["value"] for p in pts if p["value"] is not None]
        if not vals:
            return {"error": f"nessun dato per {sensor}"}
        trend = vals[-1] - vals[0]
        return {"sensor": sensor, "zone_id": zone_id, "hours": hours, "first": round(vals[0], 2), "last": round(vals[-1], 2),
                "min": round(min(vals), 2), "max": round(max(vals), 2), "delta": round(trend, 2),
                "trend": "in aumento" if trend > 0.5 else "in calo" if trend < -0.5 else "stabile",
                "samples": len(vals)}

    def get_crop_targets(self, crop_id: str) -> dict:
        c = CROPS[crop_id]
        return {"crop_id": crop_id, "name": c["name"], **c["ideal_params"], "cycle_days": c["cycle_days"]}

    def get_energy_forecast(self, hours: int = 6) -> dict:
        h0 = self.sim.hour
        pv = PROFILE["pvgis_25kwp_power_w"]
        rows = [{"hour": (h0 + i) % 24, "pun_eur_kwh": self.sim.pun_forecast[(h0 + i) % 24], "pv_w": pv[(h0 + i) % 24]}
                for i in range(int(hours))]
        expensive = [r["hour"] for r in rows if r["pun_eur_kwh"] > 0.17 and r["pv_w"] == 0]
        led_on = [r["hour"] for r in rows if self.sim.plan["zones"]["ZONE_1_LEAFY"]["hourly"][r["hour"]]["led_on"]]
        return {"from_hour": h0, "rows": rows, "expensive_hours_no_pv": expensive,
                "pun_now": rows[0]["pun_eur_kwh"], "pv_now_w": rows[0]["pv_w"],
                "led_on_hours_in_window": led_on, "data_origin": "EXTERNAL (GME PUN, PVGIS)"}

    def get_shelf_status(self) -> dict:
        return {"shelves": [{"level": s["level"], "zone_id": s["zone_id"], "crop_id": s["crop_id"],
                             "day_of_cycle": round(s["day_of_cycle"], 1), "biomass_kg": round(s["harvestable_biomass_kg"], 1),
                             "days_to_harvest": s["days_to_harvest"], "status": s["status"]} for s in self.sim.shelves]}

    # ------------------------------------------------------------------ L1 / L0
    def simulate_plan(self, overrides: dict) -> dict:
        overrides = dict(overrides)
        if overrides.pop("keep_current_light_window", False):
            overrides["fixed_light_start"] = {z: v["light_window"]["start_hour"] for z, v in self.sim.plan["zones"].items()}
        merged = {**self.sim.overrides, **overrides}
        crops = self.sim.crops_by_zone()
        new = optimizer_l1.plan_with_reference(merged, crops, pun=self.sim.pun_forecast)
        # Il piano attivo viene rivalutato con i prezzi correnti per un confronto equo.
        cur = self.sim.plan
        cur_brief = self._plan_brief(cur)
        cur_brief["cost_eur_day"] = round(sum(h["grid_w"] / 1000 * self.sim.pun_forecast[h["hour"]]
                                              for h in cur["hourly_total"]), 2)
        return {"overrides": merged,
                "current": cur_brief, "proposed": self._plan_brief(new),
                "delta_cost_eur": round(new["energy"]["cost_eur"] - cur_brief["cost_eur_day"], 2),
                "binding_constraints": new["binding_constraints"]}

    def submit_proposal(self, overrides: dict, rationale: str = "", duration_h: float = 8) -> dict:
        result = safety_l0.validate_proposal(overrides, current=self.sim.solution)
        entry = self.sim.log_l0("L2_ORCHESTRATOR", overrides, result)
        out = {"proposal_id": entry["id"], "verdict": result["verdict"], "checks": result["checks"]}
        if result["applied"] is not None:
            new = self.sim.apply_overrides(result["applied"], duration_h, "L2")
            out["applied_overrides"] = result["applied"]
            out["valid_for_h"] = duration_h
            out["new_plan"] = self._plan_brief(new)
        else:
            out["applied_overrides"] = None
            out["note"] = "Proposta rifiutata: nessuna modifica applicata agli attuatori."
        return out

    @staticmethod
    def _plan_brief(p: dict) -> dict:
        return {"light_windows": {z: v["light_window"]["label"] for z, v in p["zones"].items()},
                "dli": {z: f'{v["dli_planned"]}/{v["dli_target"]}' for z, v in p["zones"].items()},
                "cost_eur_day": p["energy"]["cost_eur"], "grid_kwh_day": p["energy"]["grid_kwh"],
                "pv_share_pct": p["energy"]["pv_share_pct"]}

    # ------------------------------------------------------------------ produzione
    def get_harvest_forecast(self, days: int = 3) -> dict:
        rows = []
        for s in self.sim.shelves:
            if s["days_to_harvest"] <= days:
                c = CROPS[s["crop_id"]]
                kg = s["harvestable_biomass_kg"] * c["post_harvest_storage"]["edible_fraction_after_trimming"]
                rows.append({"level": s["level"], "crop_id": s["crop_id"], "days_to_harvest": s["days_to_harvest"],
                             "edible_kg": round(kg, 1), "max_storage_days": c["post_harvest_storage"]["max_storage_days"],
                             "status": s["status"]})
        rows.sort(key=lambda r: (r["days_to_harvest"], r["max_storage_days"]))
        return {"days": days, "items": rows, "inventory": self._inventory_brief()}

    def schedule_harvest(self, level: int) -> dict:
        item = self.sim.harvest(int(level))
        return {"harvested": item, "inventory": self._inventory_brief()}

    def _inventory_brief(self) -> list[dict]:
        return [{"id": i["id"], "crop_id": i["crop_id"], "kg": i["quantity_kg"], "expiry": i["expiry"][:10]}
                for i in self.sim.inventory if i["quantity_kg"] > 0]

    def draft_menu(self, focus_crop: str | None = None) -> dict:
        stock: dict[str, float] = {}
        for i in self.sim.inventory:
            stock[i["crop_id"]] = stock.get(i["crop_id"], 0.0) + i["quantity_kg"]
        meals = CANTEEN["daily_meals_average"]
        candidates = []
        for r in CANTEEN["recipes_catalog"]:
            ing = r["greenhouse_ingredients_g_per_portion"]
            if focus_crop and focus_crop not in ing:
                continue
            covered = [c for c in ing if stock.get(c, 0) > 0]
            if not covered:
                continue
            # Porzioni limitate dagli ingredienti della serra disponibili; quelli mancanti si acquistano.
            portions = min(stock[c] * 1000 / ing[c] for c in covered)
            candidates.append({"recipe_id": r["recipe_id"], "dish_name": r["dish_name"], "course": r["course"],
                               "portions_possible": int(portions), "missing": [c for c in ing if stock.get(c, 0) <= 0],
                               "greenhouse_g_per_portion": ing, "territorial_link": r["territorial_link"]})
        # Priorità: ricette interamente coperte, poi quelle che usano più prodotto della serra.
        meals_cap = CANTEEN["daily_meals_average"]
        candidates.sort(key=lambda c: (len(c["missing"]), -min(c["portions_possible"], meals_cap)
                                       * sum(g for k, g in c["greenhouse_g_per_portion"].items() if k not in c["missing"])))
        chosen = candidates[0] if candidates else None
        menu = None
        if chosen and chosen["portions_possible"] > 0:
            portions = min(chosen["portions_possible"], meals)
            date = (self.sim.now + timedelta(days=1)).date().isoformat()
            used = {c: round(g * portions / 1000, 1) for c, g in chosen["greenhouse_g_per_portion"].items()
                    if c not in chosen["missing"]}
            to_buy = {c: round(g * portions / 1000, 1) for c, g in chosen["greenhouse_g_per_portion"].items()
                      if c in chosen["missing"]}
            prices = COSTS["ismea_campania_market_prices_eur_kg"]
            value = sum(kg * prices[c]["washed_ready_to_eat_canteen_eur_kg"] for c, kg in used.items())
            menu = {"id": f"MENU-{len(self.sim.menus) + 1:03d}", "target_date": date, "recipe_id": chosen["recipe_id"],
                    "title": chosen["dish_name"], "course": chosen["course"], "servings": portions,
                    "coverage_pct": round(100 * portions / meals), "greenhouse_kg": used,
                    "value_eur": round(value, 2), "status": "proposed", "territorial_link": chosen["territorial_link"],
                    "to_buy_kg": to_buy}
            self.sim.menus.insert(0, menu)
        return {"stock_kg": {k: round(v, 1) for k, v in stock.items()}, "daily_meals_average": meals,
                "candidates": candidates[:4], "menu": menu}

    def notify_operator(self, message: str, severity: str = "info") -> dict:
        ev = self.sim.add_event(severity, "Messaggio dell'orchestratore", message, "L2_ORCHESTRATOR")
        return {"event_id": ev["id"], "delivered": True}
