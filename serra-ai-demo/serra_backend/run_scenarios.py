"""Esegue tutti gli scenari senza frontend ed esporta le tracce dell'agente.

Uso:  .venv/bin/python run_scenarios.py            (tutti gli scenari)
      .venv/bin/python run_scenarios.py umidita    (uno solo)

Output in ./output/<scenario>/: RUN-xxx.json (messaggi grezzi), RUN-xxx.md (versione leggibile)
e riepilogo.md con l'esito di ogni scenario. Utile da allegare ai materiali.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from serra import scenarios
from serra.agent.runner import to_markdown
from serra.engine import Engine

OUT = Path(__file__).parent / "output"
# Ore simulate da far scorrere dopo l'iniezione, per vedere la reazione del sistema.
FOLLOW_UP_H = {"umidita": 4, "caldo": 4, "clorosi": 6, "prezzo": 2, "conflitto": 3, "pericolosa": 1, "raccolta": 1}
WARMUP_STEPS = {"umidita": 40, "caldo": 44, "clorosi": 36, "raccolta": 20}  # 10:00, 11:00, 09:00, 05:00


def run(scenario_id: str) -> dict:
    eng = Engine()
    eng.step(WARMUP_STEPS.get(scenario_id, 30))
    runs_before = {r["id"] for r in eng.runs}
    sensors_before = eng.sim.sensors("ZONE_1_LEAFY"), eng.sim.sensors("ZONE_2_WARM")
    scenarios.apply(eng, scenario_id)
    eng.step(FOLLOW_UP_H[scenario_id] * 4)
    new = [r for r in reversed(eng.runs) if r["id"] not in runs_before]
    folder = OUT / scenario_id
    folder.mkdir(parents=True, exist_ok=True)
    for r in new:
        (folder / f"{r['id']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / f"{r['id']}.md").write_text(to_markdown(r), encoding="utf-8")
    after = eng.sim.sensors("ZONE_1_LEAFY"), eng.sim.sensors("ZONE_2_WARM")
    return {"scenario": scenario_id, "runs": new, "before": sensors_before, "after": after,
            "l0": [e["verdict"] for e in reversed(eng.sim.l0_log)]}


def main():
    ids = sys.argv[1:] or [s["id"] for s in scenarios.SCENARIOS]
    lines = ["# Riepilogo scenari", "", "| Scenario | Esecuzioni agente | Verdetti L0 | Esito |", "|---|---|---|---|"]
    for sid in ids:
        res = run(sid)
        titles = "; ".join(f"{r['id']} {r['trigger']['title']}" for r in res["runs"]) or "nessuna"
        outcome = "; ".join((r["decision"] or {}).get("messaggio_operatore", "") if isinstance(r["decision"], dict)
                            else str(r["decision"]) for r in res["runs"])
        lines.append(f"| {sid} | {titles} | {', '.join(res['l0']) or '—'} | {outcome} |")
        print(f"[{sid}] runs={len(res['runs'])} L0={res['l0']}")
        for r in res["runs"]:
            print("   ", r["id"], r["trigger"]["title"], "| tool:", r["tool_calls"], "|", run_err(r))
    OUT.mkdir(exist_ok=True)
    (OUT / "riepilogo.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Output in {OUT}")


def run_err(r):
    if r.get("error"):
        return "ERRORE " + r["error"]
    d = r["decision"]
    return d.get("messaggio_operatore") if isinstance(d, dict) else d


if __name__ == "__main__":
    main()
