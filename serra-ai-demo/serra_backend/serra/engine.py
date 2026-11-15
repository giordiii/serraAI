"""Motore: tiene insieme digital twin, trigger dell'agente L2 e storico delle esecuzioni."""
from __future__ import annotations

import threading
import time

from .agent.runner import make_llm, run_agent
from .config import RULES, STEPS_PER_HOUR, ZONES
from .sim import Simulation
from .tools import Toolbox

COOLDOWN_STEPS = {"RULE_01_HUMIDITY_TIPBURN": 6, "RULE_02_HEAT_WILTING": 6,
                  "RULE_03_NUTRIENT_CHLOROSIS": 12, "RULE_04_ENERGY_PRICE_SPIKE": 12}
GLOBAL_RULES = {"RULE_03_NUTRIENT_CHLOROSIS", "RULE_04_ENERGY_PRICE_SPIKE"}
RUN_TITLES = {
    "RULE_01_HUMIDITY_TIPBURN": "Umidità alta · rischio tipburn",
    "RULE_02_HEAT_WILTING": "Stress termico",
    "RULE_03_NUTRIENT_CHLOROSIS": "Carenza nutrienti",
    "RULE_04_ENERGY_PRICE_SPIKE": "Prezzo energia elevato",
}


def eval_condition(expr: str, variables: dict) -> bool:
    py = expr.replace(" AND ", " and ").replace(" OR ", " or ")
    return bool(eval(py, {"__builtins__": {}}, variables))  # espressioni dal nostro dataset


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.llm = make_llm()
        self.running = False
        self.speed = 2  # step simulati al secondo (1 step = 15 min)
        self.reset()

    def reset(self):
        with self.lock:
            self.sim = Simulation()
            self.toolbox = Toolbox(self.sim)
            self.runs: list[dict] = []
            self.last_trigger: dict[tuple, int] = {}
            self.heartbeat = {"L0_SAFETY": time.time(), "L1_OPTIMIZER": time.time(), "L2_ORCHESTRATOR": time.time()}
            self.active_scenario: dict | None = None

    # ------------------------------------------------------------------ agente
    def run_task(self, task: dict, title: str) -> dict:
        run_id = f"RUN-{len(self.runs) + 1:03d}"
        trigger = {"type": task["type"], "title": title, "rule_id": task.get("rule_id"), "zone_id": task.get("zone_id")}
        run = run_agent(task, self.toolbox, self.llm, run_id, trigger)
        if task["type"] != "chat":
            self.runs.insert(0, run)
            del self.runs[60:]
        now = time.time()
        self.heartbeat["L2_ORCHESTRATOR"] = now
        if run["tool_calls"]:
            self.heartbeat["L1_OPTIMIZER"] = now
            self.heartbeat["L0_SAFETY"] = now
        return run

    def _cooling(self, key) -> bool:
        last = self.last_trigger.get(key)
        rule = key[0]
        return last is not None and self.sim.step_count - last < COOLDOWN_STEPS.get(rule, 6) * STEPS_PER_HOUR

    def _leds_on_in_expensive_hours(self) -> bool:
        pv = self.toolbox.get_energy_forecast(12)
        return any(h in pv["led_on_hours_in_window"] for h in pv["expensive_hours_no_pv"])

    def check_triggers(self):
        sim = self.sim
        fired: list[tuple[str, str]] = []
        for zid in ZONES:
            variables = sim.rule_variables(zid)
            for rule in RULES:
                rid = rule["rule_id"]
                key = (rid, "ALL" if rid in GLOBAL_RULES else zid)
                if key in [(r, "ALL" if r in GLOBAL_RULES else z) for r, z in fired]:
                    continue
                if self._cooling(key):
                    continue
                if eval_condition(rule["if_condition"], variables):
                    if rid == "RULE_04_ENERGY_PRICE_SPIKE" and not self._leds_on_in_expensive_hours():
                        continue
                    fired.append((rid, zid))

        ids = {r for r, _ in fired}
        if "RULE_01_HUMIDITY_TIPBURN" in ids and "RULE_04_ENERGY_PRICE_SPIKE" in ids:
            zid = next(z for r, z in fired if r == "RULE_01_HUMIDITY_TIPBURN")
            self.last_trigger[("RULE_01_HUMIDITY_TIPBURN", zid)] = sim.step_count
            self.last_trigger[("RULE_04_ENERGY_PRICE_SPIKE", "ALL")] = sim.step_count
            self.run_task({"type": "rule_conflict", "zone_id": zid, "rule_ids": sorted(ids),
                           "variables": sim.rule_variables(zid)}, "Conflitto tra regole · umidità vs energia")
            fired = [(r, z) for r, z in fired if r not in ("RULE_01_HUMIDITY_TIPBURN", "RULE_04_ENERGY_PRICE_SPIKE")]

        for rid, zid in fired:
            key = (rid, "ALL" if rid in GLOBAL_RULES else zid)
            self.last_trigger[key] = sim.step_count
            if rid == "RULE_04_ENERGY_PRICE_SPIKE":
                self.run_task({"type": "energy_price", "rule_id": rid, "variables": sim.rule_variables(zid)}, RUN_TITLES[rid])
            else:
                self.run_task({"type": "rule_anomaly", "rule_id": rid, "zone_id": zid,
                               "variables": sim.rule_variables(zid)}, f"{RUN_TITLES[rid]} · {zid}")

        # Pianificazione giornaliera di raccolta e menu alle 07:00.
        if sim.now.hour == 7 and sim.now.minute == 0:
            self.run_task({"type": "harvest_planning"}, "Pianificazione raccolta e menu")

    # ------------------------------------------------------------------ tempo
    def step(self, n: int = 1):
        with self.lock:
            for _ in range(n):
                self.sim.step()
                self.heartbeat["L1_OPTIMIZER"] = time.time()
                self.heartbeat["L0_SAFETY"] = time.time()
                self.check_triggers()

    def fast_forward_to(self, hour: int, minute: int = 0):
        with self.lock:
            for _ in range(24 * STEPS_PER_HOUR):
                if self.sim.now.hour == hour and self.sim.now.minute == minute:
                    break
                self.step()

    def chat(self, question: str) -> dict:
        with self.lock:
            return self.run_task({"type": "chat", "question": question}, "Chat")
