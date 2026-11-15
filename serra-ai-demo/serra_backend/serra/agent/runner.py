"""Ciclo agentico (identico per LLM emulato e LLM reale) e resa leggibile.

Ogni esecuzione produce:
  - `messages`: la conversazione grezza in formato Ollama/OpenAI (versione tecnica)
  - `steps`:    la stessa conversazione tradotta in passi leggibili (versione umana)
  - `decision`: la decisione finale strutturata
"""
from __future__ import annotations

import json
import os

from ..config import CROPS, ZONE_LABELS
from ..tools import TOOL_SPECS, Toolbox
from .prompts import CHAT_SYSTEM_PROMPT, SYSTEM_PROMPT, build_task_message

MAX_TURNS = 12


def make_llm():
    if os.environ.get("LLM_MODE", "mock").lower() == "ollama":
        from .llm_ollama import OllamaLLM
        return OllamaLLM()
    from .llm_mock import MockLLM
    return MockLLM()


def run_agent(task: dict, toolbox: Toolbox, llm, run_id: str, trigger: dict) -> dict:
    system = CHAT_SYSTEM_PROMPT if task["type"] == "chat" else SYSTEM_PROMPT
    messages = [{"role": "system", "content": system}, {"role": "user", "content": build_task_message(task)}]
    started_at = toolbox.sim.iso()
    tokens = 0
    duration_ms = 0
    error = None
    for _ in range(MAX_TURNS):
        try:
            resp = llm.chat(messages, TOOL_SPECS)
        except Exception as exc:  # es. Ollama non avviato
            error = f"{type(exc).__name__}: {exc}"
            break
        tokens += resp.get("eval_count", 0)
        duration_ms += resp.get("total_duration_ms", 0)
        msg = resp["message"]
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            break
        for tc in calls:
            fn = tc["function"]
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            result = toolbox.call(fn["name"], args)
            messages.append({"role": "tool", "tool_call_id": tc.get("id"), "name": fn["name"],
                             "content": json.dumps(result, ensure_ascii=False)})

    final = messages[-1] if messages[-1]["role"] == "assistant" else None
    decision = None
    if final and not final.get("tool_calls"):
        try:
            decision = json.loads(final["content"])
        except (json.JSONDecodeError, TypeError):
            decision = final.get("content")
    return {
        "id": run_id, "type": task["type"], "trigger": trigger, "started_at": started_at,
        "model": getattr(llm, "name", "llm"), "messages": messages, "steps": humanize(messages),
        "decision": decision, "error": error, "tokens": tokens, "llm_time_ms": duration_ms,
        "tool_calls": sum(len(m.get("tool_calls") or []) for m in messages if m["role"] == "assistant"),
        "data_origin": "SIMULATED",
    }


# ---------------------------------------------------------------------- versione leggibile
TOOL_LABELS = {
    "read_sensors": "Lettura sensori", "get_sensor_history": "Andamento storico",
    "get_crop_targets": "Parametri coltura", "get_energy_forecast": "Previsione energia",
    "get_shelf_status": "Stato ripiani", "simulate_plan": "Simulazione piano L1",
    "submit_proposal": "Proposta al Safety Gate L0", "get_harvest_forecast": "Previsione raccolti",
    "schedule_harvest": "Raccolta", "draft_menu": "Bozza menu", "notify_operator": "Avviso operatore",
}


def _z(zid):
    return ZONE_LABELS.get(zid, zid)


def describe_call(name: str, a: dict) -> str:
    if name == "read_sensors":
        return f"Legge i sensori della {_z(a.get('zone_id'))}"
    if name == "get_sensor_history":
        return f"Controlla l'andamento di {a.get('sensor')} nelle ultime {a.get('hours')} ore"
    if name == "get_crop_targets":
        return f"Consulta i parametri ideali di {CROPS.get(a.get('crop_id'), {}).get('name', a.get('crop_id'))}"
    if name == "get_energy_forecast":
        return f"Chiede prezzi PUN e fotovoltaico delle prossime {a.get('hours')} ore"
    if name == "get_shelf_status":
        return "Controlla lo stato dei 4 ripiani"
    if name == "simulate_plan":
        return f"Chiede al Level 1 un piano di prova con {_fmt_override(a.get('overrides', {}))}"
    if name == "submit_proposal":
        return f"Propone al Level 0: {_fmt_override(a.get('overrides', {}))} per {a.get('duration_h', 8)} h"
    if name == "get_harvest_forecast":
        return f"Controlla i raccolti dei prossimi {a.get('days')} giorni"
    if name == "schedule_harvest":
        return f"Raccoglie il ripiano {a.get('level')}"
    if name == "draft_menu":
        return f"Cerca ricette della mensa" + (f" con {a['focus_crop']}" if a.get("focus_crop") else "")
    if name == "notify_operator":
        return f"Avvisa l'operatore: \"{a.get('message')}\""
    return f"{name}({a})"


def _fmt_override(o: dict) -> str:
    names = {"rh_max_pct": "umidità max {:g}%", "vent_min_m3_h": "ventilazione min {:g} m³/h",
             "led_max_power_w": "LED max {:g} W", "photoperiod_h": "fotoperiodo {:g} h",
             "temp_target_offset_c": "temperatura {:+g} °C", "ph_setpoint": "pH {:g}",
             "ec_setpoint_offset_ms_cm": "EC {:+g} mS/cm", "prefer_dark_window_hours": "LED spenti alle ore {}"}
    parts = []
    for k, v in o.items():
        fmt = names.get(k, k + " {}")
        try:
            parts.append(fmt.format(v))
        except (ValueError, TypeError):
            parts.append(f"{k} {v}")
    return ", ".join(parts) or "nessun override"


def describe_result(name: str, r: dict) -> tuple[str, str | None]:
    """Restituisce (testo, tono). Il tono serve al frontend per i colori."""
    if "error" in r:
        return f"Errore: {r['error']}", "bad"
    if name == "read_sensors":
        x = r["readings"]
        return (f"{x['SENS_T_AIR_C']} °C · umidità {x['SENS_RH_AIR_PCT']}% · CO₂ {x['SENS_CO2_PPM']:.0f} ppm · "
                f"pH {x['SENS_SOL_PH']} · EC {x['SENS_SOL_EC_MS_CM']} · tipburn {x['CV_TIPBURN_RISK']:.2f} · "
                f"verde {x['CV_GREENNESS_INDEX']:.2f}", None)
    if name == "get_sensor_history":
        return f"{r['first']} → {r['last']} ({r['trend']}, min {r['min']}, max {r['max']})", None
    if name == "get_crop_targets":
        return (f"{r['name']}: {r['temp_opt_c']} °C ottimali, umidità {r['rh_min_max_pct'][0]:.0f}–{r['rh_min_max_pct'][1]:.0f}%, "
                f"DLI {r['dli_target_mol_m2_d']} mol/m²/d, EC {r['ec_range_ms_cm'][0]}–{r['ec_range_ms_cm'][1]}", None)
    if name == "get_energy_forecast":
        exp = r["expensive_hours_no_pv"]
        return (f"PUN ora {r['pun_now']:.3f} €/kWh, FV {r['pv_now_w']} W; ore care senza FV: {exp or 'nessuna'}", None)
    if name == "get_shelf_status":
        return "; ".join(f"R{s['level']} {s['crop_id']} {s['biomass_kg']} kg, {s['days_to_harvest']} gg" for s in r["shelves"]), None
    if name == "simulate_plan":
        return (f"Costo {r['proposed']['cost_eur_day']:.2f} €/giorno ({r['delta_cost_eur']:+.2f} €), "
                f"luce zona 1 {r['proposed']['light_windows']['ZONE_1_LEAFY']}, zona 2 {r['proposed']['light_windows']['ZONE_2_WARM']}",
                "good" if r["delta_cost_eur"] <= 0 else None)
    if name == "submit_proposal":
        bad = [c for c in r["checks"] if c["outcome"] in ("BLOCKED", "CLIPPED")]
        detail = "; ".join(f"{c['param']}: {c['reason']}" for c in bad) or "tutti i controlli superati"
        tone = {"ALLOWED": "good", "CLIPPED": "warn", "BLOCKED": "bad"}[r["verdict"]]
        return f"Verdetto L0: {r['verdict']} — {detail}", tone
    if name == "get_harvest_forecast":
        items = "; ".join(f"R{i['level']} {i['crop_id']} tra {i['days_to_harvest']} gg (~{i['edible_kg']} kg)" for i in r["items"])
        return items or "Nessun raccolto nel periodo", None
    if name == "schedule_harvest":
        h = r["harvested"]
        return f"Raccolti {h['quantity_kg']} kg di {h['crop_id']} (valore {h['value_eur']} €), scadenza {h['expiry'][:10]}", "good"
    if name == "draft_menu":
        m = r.get("menu")
        return (f"Menu: {m['title']} — {m['servings']} porzioni ({m['coverage_pct']}% dei pasti)" if m
                else "Nessuna ricetta realizzabile"), "good" if m else "warn"
    if name == "notify_operator":
        return f"Avviso {r['event_id']} inviato", None
    return json.dumps(r, ensure_ascii=False)[:200], None


def humanize(messages: list[dict]) -> list[dict]:
    steps = []
    names = {}
    for m in messages:
        role = m["role"]
        if role == "user":
            text = m["content"].split("```json")[0].strip()
            steps.append({"kind": "trigger", "text": text})
        elif role == "assistant":
            calls = m.get("tool_calls") or []
            if calls:
                if m.get("content"):
                    steps.append({"kind": "thought", "text": m["content"]})
                for tc in calls:
                    fn = tc["function"]
                    args = fn.get("arguments") or {}
                    if isinstance(args, str):
                        args = json.loads(args or "{}")
                    names[tc.get("id")] = fn["name"]
                    steps.append({"kind": "tool_call", "tool": fn["name"], "label": TOOL_LABELS.get(fn["name"], fn["name"]),
                                  "text": describe_call(fn["name"], args), "args": args})
            else:
                if m.get("thinking"):
                    steps.append({"kind": "thought", "text": m["thinking"]})
                content = m.get("content", "")
                try:
                    d = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    d = None
                if isinstance(d, dict):
                    steps.append({"kind": "decision", "text": d.get("messaggio_operatore") or d.get("diagnosi", ""),
                                  "decision": d, "tone": {"BLOCKED": "bad", "CLIPPED": "warn"}.get(d.get("verdetto_l0"), "good")})
                else:
                    steps.append({"kind": "answer", "text": content})
        elif role == "tool":
            name = m.get("name") or names.get(m.get("tool_call_id"))
            r = json.loads(m["content"])
            text, tone = describe_result(name, r)
            steps.append({"kind": "tool_result", "tool": name, "label": TOOL_LABELS.get(name, name), "text": text, "tone": tone})
    return steps


def to_markdown(run: dict) -> str:
    icons = {"trigger": "⚡", "thought": "💭", "tool_call": "🔧", "tool_result": "📥", "decision": "✅", "answer": "💬"}
    lines = [f"# Esecuzione {run['id']} — {run['trigger'].get('title', run['type'])}", "",
             f"- **Ora simulata:** {run['started_at']}", f"- **Modello:** {run['model']}",
             f"- **Chiamate a tool:** {run['tool_calls']} · **token stimati:** {run['tokens']}",
             f"- **Origine dati:** {run['data_origin']}", "", "## Ragionamento", ""]
    for i, s in enumerate(run["steps"], 1):
        label = f"**{s['label']}** — " if s.get("label") else ""
        lines.append(f"{i}. {icons.get(s['kind'], '•')} {label}{s['text']}")
    if isinstance(run.get("decision"), dict):
        d = run["decision"]
        lines += ["", "## Decisione finale", "", f"- **Diagnosi:** {d.get('diagnosi')}",
                  f"- **Verdetto L0:** {d.get('verdetto_l0')}", f"- **Confidenza:** {d.get('confidenza')}",
                  f"- **Richiede intervento umano:** {'sì' if d.get('richiede_umano') else 'no'}",
                  "- **Evidenze:**"] + [f"  - {e}" for e in d.get("evidenze", [])] + \
                 ["- **Azioni:**"] + [f"  - {a}" for a in d.get("azioni", [])]
    return "\n".join(lines) + "\n"
