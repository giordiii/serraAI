"""Digital twin semplificato della serra.

Fisica volutamente minima: ogni grandezza tende verso un valore di equilibrio
che dipende da attuatori, clima esterno e disturbi degli scenari. Lo scopo è
ottenere andamenti plausibili e coerenti con le decisioni dei livelli L0/L1/L2,
non un modello agronomico validato.
"""
from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta

from . import optimizer_l1, safety_l0
from .config import (COSTS, CROPS, DATASET, ESTIMATES, INITIAL_SHELVES_MODE,
                     L0_LIMITS, PROFILE, SENSORS_T0, SIM_START_ISO,
                     STEP_MINUTES, STEPS_PER_HOUR, ZONES, zone_led_max_w,
                     zone_of_level)

HISTORY_MAX = 4 * 24 * STEPS_PER_HOUR  # 4 giorni simulati


def _interp(series: list[float], hour_float: float) -> float:
    h0 = int(hour_float) % 24
    h1 = (h0 + 1) % 24
    f = hour_float - int(hour_float)
    return series[h0] * (1 - f) + series[h1] * f


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _wiggle(step: int, k: float, amp: float) -> float:
    """Rumore deterministico (riprese sempre identiche)."""
    return amp * math.sin(step * k) * math.cos(step * k * 0.37)


class Simulation:
    def __init__(self):
        self.reset()

    # ------------------------------------------------------------------ setup
    def reset(self):
        self.step_count = 0
        self.start = datetime.fromisoformat(SIM_START_ISO)
        self.zones = {}
        for zid in ZONES:
            s = SENSORS_T0
            self.zones[zid] = {
                "SENS_T_AIR_C": s["SENS_T_AIR_C"] + (2.5 if zid == "ZONE_2_WARM" else 0.0),
                "SENS_RH_AIR_PCT": s["SENS_RH_AIR_PCT"],
                "SENS_CO2_PPM": s["SENS_CO2_PPM"],
                "SENS_PAR_PPFD": 0.0,
                "CV_GREENNESS_INDEX": s["CV_GREENNESS_INDEX"],
                "CV_TIPBURN_RISK": s["CV_TIPBURN_RISK"],
                "CV_WILTING_SCORE": s["CV_WILTING_SCORE"],
                "led_w": 0.0, "vent_m3h": 0.0, "hvac_heat_w": 0.0, "hvac_cool_w": 0.0,
            }
        self.solution = {
            "SENS_SOL_PH": SENSORS_T0["SENS_SOL_PH"],
            "SENS_SOL_EC_MS_CM": SENSORS_T0["SENS_SOL_EC_MS_CM"],
            "SENS_SOL_TEMP_C": SENSORS_T0["SENS_SOL_TEMP_C"],
            "SENS_TANK_LVL_L": SENSORS_T0["SENS_TANK_LVL_L"],
        }
        self.shelves = copy.deepcopy(DATASET["3_shelves_initial_state_options"][INITIAL_SHELVES_MODE])
        for sh in self.shelves:
            sh["zone_id"] = zone_of_level(sh["level"])
            sh["day_of_cycle"] = float(sh["day_of_cycle"])
        self.inventory: list[dict] = []
        self.menus: list[dict] = []
        self.events: list[dict] = []
        self.l0_log: list[dict] = []
        self.overrides: dict = {}            # override attivi (già validati da L0)
        self.override_expiry: dict = {}      # chiave -> step di scadenza
        self.disturbances: list[dict] = []
        self.pun_forecast = list(PROFILE["gme_pun_eur_kwh"])
        self.history: list[dict] = []
        self.energy_today = self._empty_energy()
        self.energy_total = self._empty_energy()
        self.revenue_eur = 0.0
        self.harvested_kg = 0.0
        self.plan = None
        self.plan_reason = "piano iniziale"
        self.replan("piano iniziale del giorno")
        self._record()

    @staticmethod
    def _empty_energy():
        return {"load_kwh": 0.0, "pv_kwh": 0.0, "grid_kwh": 0.0, "cost_eur": 0.0, "led_kwh": 0.0, "hvac_kwh": 0.0}

    # ------------------------------------------------------------------ time
    @property
    def now(self) -> datetime:
        return self.start + timedelta(minutes=STEP_MINUTES * self.step_count)

    @property
    def hour_float(self) -> float:
        n = self.now
        return n.hour + n.minute / 60

    @property
    def hour(self) -> int:
        return self.now.hour

    def iso(self) -> str:
        return self.now.isoformat()

    # ------------------------------------------------------------------ L1
    def crops_by_zone(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {z: [] for z in ZONES}
        for sh in self.shelves:
            out[sh["zone_id"]].append(sh["crop_id"])
        return out

    def replan(self, reason: str) -> dict:
        self.plan = optimizer_l1.plan_with_reference(self.overrides, self.crops_by_zone(), pun=self.pun_forecast)
        self.plan["computed_at"] = self.iso()
        self.plan["reason"] = reason
        self.plan_reason = reason
        return self.plan

    def apply_overrides(self, applied: dict, duration_h: float, source: str) -> dict:
        until = self.step_count + int(duration_h * STEPS_PER_HOUR)
        for k, v in applied.items():
            self.overrides[k] = v
            self.override_expiry[k] = until
        return self.replan(f"override da {source}: {', '.join(applied)}")

    def log_l0(self, source: str, proposal: dict, result: dict):
        entry = {"id": f"L0-{len(self.l0_log) + 1:04d}", "at": self.iso(), "source": source,
                 "proposal": proposal, "verdict": result["verdict"], "checks": result["checks"]}
        self.l0_log.insert(0, entry)
        return entry

    # ------------------------------------------------------------------ events
    def add_event(self, severity: str, title: str, detail: str, source: str):
        ev = {"id": f"EVT-{len(self.events) + 1:04d}", "at": self.iso(), "severity": severity,
              "title": title, "detail": detail, "source": source}
        self.events.insert(0, ev)
        return ev

    def add_disturbance(self, kind: str, value: float, hours: float, label: str, zone_id: str | None = None,
                        extra: dict | None = None):
        d = {"kind": kind, "value": value, "zone_id": zone_id, "until": self.step_count + int(hours * STEPS_PER_HOUR),
             "label": label, **(extra or {})}
        self.disturbances.append(d)
        return d

    def _dist(self, kind: str, zone_id: str | None = None) -> float:
        return sum(d["value"] for d in self.disturbances
                   if d["kind"] == kind and (d["zone_id"] in (None, zone_id)))

    # ------------------------------------------------------------------ harvest
    def harvest(self, level: int) -> dict:
        sh = next(s for s in self.shelves if s["level"] == level)
        crop = CROPS[sh["crop_id"]]
        kg = round(sh["harvestable_biomass_kg"] * crop["post_harvest_storage"]["edible_fraction_after_trimming"], 1)
        price = COSTS["ismea_campania_market_prices_eur_kg"][sh["crop_id"]]["washed_ready_to_eat_canteen_eur_kg"]
        item = {"id": f"INV-{len(self.inventory) + 1:03d}", "crop_id": sh["crop_id"], "crop_name": crop["name"],
                "quantity_kg": kg, "harvested_at": self.iso(), "level": level,
                "expiry": (self.now + timedelta(days=crop["post_harvest_storage"]["max_storage_days"])).isoformat(),
                "value_eur": round(kg * price, 2)}
        self.inventory.insert(0, item)
        self.harvested_kg += kg
        self.revenue_eur += item["value_eur"]
        sh.update({"day_of_cycle": 0.0, "harvestable_biomass_kg": 0.0, "days_to_harvest": crop["cycle_days"],
                   "status": "JUST_TRANSPLANTED"})
        return item

    # ------------------------------------------------------------------ step
    def step(self, n: int = 1):
        for _ in range(n):
            self._step_once()

    def _step_once(self):
        prev_day = self.now.date()
        self.step_count += 1
        k = self.step_count
        h = self.hour
        hf = self.hour_float
        dt_h = STEP_MINUTES / 60

        # Scadenza disturbi e override.
        self.disturbances = [d for d in self.disturbances if d["until"] > k]
        expired = [key for key, until in self.override_expiry.items() if until <= k]
        restore_pun = False
        for key in expired:
            self.overrides.pop(key, None)
            self.override_expiry.pop(key, None)
        base_pun = PROFILE["gme_pun_eur_kwh"]
        pun_now = [base_pun[i] * (1 + sum(d["value"] for d in self.disturbances
                                          if d["kind"] == "pun_multiplier" and i in d.get("hours", [])))
                   for i in range(24)]
        if pun_now != self.pun_forecast:
            self.pun_forecast = pun_now
            restore_pun = True
        if self.now.date() != prev_day:
            self.energy_today = self._empty_energy()
            self.replan("nuovo giorno: ripianificazione delle 24 h")
        elif expired:
            self.replan(f"scadenza override: {', '.join(expired)}")
        elif restore_pun and not self.disturbances_of("pun_multiplier"):
            self.replan("prezzi energia tornati ai valori tipici")

        t_ext = _interp(PROFILE["temp_ext_era5_c"], hf)
        pv_w = _interp(PROFILE["pvgis_25kwp_power_w"], hf)
        total_load = 0.0
        led_total = hvac_total = 0.0

        for zid, z in self.zones.items():
            hp = self.plan["zones"][zid]["hourly"][h]
            zone_max = zone_led_max_w(zid)
            led_w = hp["led_w"]
            led_frac = led_w / zone_max if zone_max else 0.0
            vent_total = hp["vent_m3h"] * len(self.zones)
            cap = 1.0 + self._dist("hvac_capacity", zid)  # es. -0.7 = HVAC al 30%

            # Temperatura
            drift = (ESTIMATES["envelope_exchange_per_step"] * ((t_ext + self._dist("temp_ext_offset", zid)) - z["SENS_T_AIR_C"])
                     + ESTIMATES["led_heat_c_per_step_full_power"] * led_frac)
            corr = ESTIMATES["hvac_gain"] * cap * (hp["t_setpoint_c"] - (z["SENS_T_AIR_C"] + drift))
            heat_w = max(0.0, corr) * ESTIMATES["hvac_w_per_c_step"]
            cool_w = max(0.0, -corr) * ESTIMATES["hvac_w_per_c_step"]
            cmd, _ = safety_l0.clip_actuators({"vent_m3h": vent_total, "hvac_heat_w": heat_w, "hvac_cool_w": cool_w})
            z["SENS_T_AIR_C"] += drift + corr + _wiggle(k, 0.71 + len(zid) * 0.01, 0.05)

            # Umidità
            rh_eq = (ESTIMATES["rh_base_pct"] + ESTIMATES["rh_transpiration_gain_pct"] * led_frac
                     + ESTIMATES["rh_vent_gain_pct"] * (1 - cmd["vent_m3h"] / 1500) + self._dist("rh_bias", zid))
            z["SENS_RH_AIR_PCT"] += (rh_eq - z["SENS_RH_AIR_PCT"]) * ESTIMATES["rh_response"] + _wiggle(k, 0.53, 0.25)
            z["SENS_RH_AIR_PCT"] = _clamp(z["SENS_RH_AIR_PCT"], 30, 98)

            # CO2 e luce
            co2_eq = 900 - (cmd["vent_m3h"] - 600) * 0.06 - 120 * led_frac
            z["SENS_CO2_PPM"] += (co2_eq - z["SENS_CO2_PPM"]) * 0.2
            z["SENS_PAR_PPFD"] = max(0.0, hp["ppfd"] + (_wiggle(k, 0.9, 3.0) if hp["ppfd"] else 0.0))

            # Indici da computer vision
            t_opt = self.plan["zones"][zid]["temp_opt_c"]
            tip_eq = _clamp((z["SENS_RH_AIR_PCT"] - 66) / 28, 0.03, 0.9)
            z["CV_TIPBURN_RISK"] += (tip_eq - z["CV_TIPBURN_RISK"]) * 0.12
            wilt_eq = _clamp((z["SENS_T_AIR_C"] - (t_opt + 3)) / 10, 0.02, 0.9)
            z["CV_WILTING_SCORE"] += (wilt_eq - z["CV_WILTING_SCORE"]) * 0.12
            green_eq = (0.88 - max(0.0, 1.35 - self.solution["SENS_SOL_EC_MS_CM"]) * 0.9
                        + self._dist("greenness_bias", zid))
            z["CV_GREENNESS_INDEX"] += (green_eq - z["CV_GREENNESS_INDEX"]) * 0.08

            z.update({"led_w": led_w, "vent_m3h": cmd["vent_m3h"] / len(self.zones),
                      "hvac_heat_w": cmd["hvac_heat_w"], "hvac_cool_w": cmd["hvac_cool_w"]})
            hvac_el = (cmd["hvac_heat_w"] + cmd["hvac_cool_w"]) / L0_LIMITS["hvac_cop"]
            fans = cmd["vent_m3h"] / len(self.zones) * ESTIMATES["fan_w_per_m3h"]
            total_load += led_w + hvac_el + fans
            led_total += led_w
            hvac_total += hvac_el

            # Crescita dei ripiani della zona
            for sh in (s for s in self.shelves if s["zone_id"] == zid):
                crop = CROPS[sh["crop_id"]]
                light_mol = hp["ppfd"] * dt_h * 3600 / 1e6
                inc = crop["total_shelf_yield_kg"] / crop["cycle_days"] * light_mol / crop["ideal_params"]["dli_target_mol_m2_d"]
                inc *= 1 - 0.5 * max(z["CV_TIPBURN_RISK"] - 0.2, 0) - 0.5 * max(z["CV_WILTING_SCORE"] - 0.2, 0)
                sh["harvestable_biomass_kg"] = round(min(sh["harvestable_biomass_kg"] + inc,
                                                         crop["total_shelf_yield_kg"] * 1.05), 3)
                sh["day_of_cycle"] += dt_h / 24
                left = max(0, math.ceil(crop["cycle_days"] - sh["day_of_cycle"] - 1e-6))
                sh["days_to_harvest"] = left
                sh["status"] = ("READY_TODAY" if left == 0 else "NEAR_HARVEST" if left <= 3
                                else "JUST_TRANSPLANTED" if sh["day_of_cycle"] < 2 else "GROWING")

        # Soluzione nutritiva (condivisa)
        sol = self.solution
        ph_sp = float(self.overrides.get("ph_setpoint", 6.0))
        ec_sp = 1.6 + float(self.overrides.get("ec_setpoint_offset_ms_cm", 0.0))
        sol["SENS_SOL_PH"] += (ESTIMATES["ph_drift_per_step"] + self._dist("ph_rate")
                               + ESTIMATES["dosing_gain"] * (ph_sp - sol["SENS_SOL_PH"]))
        sol["SENS_SOL_EC_MS_CM"] += (ESTIMATES["ec_drift_per_step"] + self._dist("ec_rate")
                                     + ESTIMATES["dosing_gain"] * (ec_sp - sol["SENS_SOL_EC_MS_CM"])
                                     * (1 + self._dist("dosing_factor")))
        sol["SENS_SOL_TEMP_C"] += (self.zones["ZONE_1_LEAFY"]["SENS_T_AIR_C"] - 0.5 - sol["SENS_SOL_TEMP_C"]) * 0.05
        sol["SENS_TANK_LVL_L"] -= 0.9
        if sol["SENS_TANK_LVL_L"] < 600:
            sol["SENS_TANK_LVL_L"] = 950.0

        # Energia
        total_load += ESTIMATES["pumps_base_w"]
        pv_used = min(pv_w, total_load)
        grid = total_load - pv_used
        cost = grid / 1000 * dt_h * self.pun_forecast[h]
        for acc in (self.energy_today, self.energy_total):
            acc["load_kwh"] += total_load / 1000 * dt_h
            acc["pv_kwh"] += pv_used / 1000 * dt_h
            acc["grid_kwh"] += grid / 1000 * dt_h
            acc["cost_eur"] += cost
            acc["led_kwh"] += led_total / 1000 * dt_h
            acc["hvac_kwh"] += hvac_total / 1000 * dt_h
        self._last_power = {"load_w": round(total_load), "pv_w": round(pv_w), "grid_w": round(grid),
                            "pun_eur_kwh": self.pun_forecast[h], "t_ext_c": round(t_ext, 1)}
        self._record()

    def disturbances_of(self, kind: str) -> list[dict]:
        return [d for d in self.disturbances if d["kind"] == kind]

    # ------------------------------------------------------------------ views
    def _record(self):
        if not hasattr(self, "_last_power"):
            hf = self.hour_float
            self._last_power = {"load_w": 0, "pv_w": round(_interp(PROFILE["pvgis_25kwp_power_w"], hf)), "grid_w": 0,
                                "pun_eur_kwh": self.pun_forecast[self.hour],
                                "t_ext_c": round(_interp(PROFILE["temp_ext_era5_c"], hf), 1)}
        rec = {"step": self.step_count, "at": self.iso(), "power": dict(self._last_power),
               "zones": {zid: {k: round(v, 3) for k, v in z.items()} for zid, z in self.zones.items()},
               "solution": {k: round(v, 3) for k, v in self.solution.items()}}
        self.history.append(rec)
        if len(self.history) > HISTORY_MAX:
            self.history.pop(0)

    def sensors(self, zone_id: str) -> dict:
        z = self.zones[zone_id]
        out = {k: round(v, 2) for k, v in z.items() if k.startswith(("SENS_", "CV_"))}
        out.update({k: round(v, 2) for k, v in self.solution.items()})
        return out

    def rule_variables(self, zone_id: str) -> dict:
        v = self.sensors(zone_id)
        v["pun_eur_kwh"] = self.pun_forecast[self.hour]
        v["pvgis_power_w"] = round(_interp(PROFILE["pvgis_25kwp_power_w"], self.hour_float))
        return v

    def sensor_history(self, sensor: str, zone_id: str, hours: float) -> list[dict]:
        n = int(hours * STEPS_PER_HOUR)
        out = []
        for rec in self.history[-n - 1:]:
            val = rec["zones"][zone_id].get(sensor, rec["solution"].get(sensor))
            out.append({"at": rec["at"], "value": val})
        return out
