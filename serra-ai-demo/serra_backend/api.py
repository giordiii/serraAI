"""Backend simulato della serra · FastAPI.

Avvio:  .venv/bin/uvicorn api:app --port 8000
Docs:   http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from serra import scenarios
from serra.adapter import run_summary, snapshot
from serra.agent.prompts import SYSTEM_PROMPT
from serra.agent.runner import to_markdown
from serra.engine import Engine
from serra.tools import TOOL_SPECS

engine = Engine()


async def clock():
    while True:
        if engine.running:
            await asyncio.to_thread(engine.step, 1)
            await asyncio.sleep(1 / max(engine.speed, 0.1))
        else:
            await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(clock())
    yield
    task.cancel()


app = FastAPI(title="Serra AI · backend simulato", version="1.0.0", lifespan=lifespan,
              description="Digital twin + Safety Gate L0 + Optimizer L1 + Orchestratore L2 (LLM emulato). Modalità SIMULATION.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class StepBody(BaseModel):
    n: int = 1


class SpeedBody(BaseModel):
    speed: float = 4


class ChatBody(BaseModel):
    question: str


class HarvestBody(BaseModel):
    level: int


class ConsumeBody(BaseModel):
    quantity_kg: float


@app.get("/api/snapshot", tags=["stato"])
def get_snapshot():
    with engine.lock:
        return snapshot(engine)


@app.get("/api/plan", tags=["stato"], summary="Piano completo del Level 1")
def get_plan():
    return engine.sim.plan


@app.get("/api/l0/log", tags=["stato"], summary="Registro delle decisioni del Safety Gate")
def get_l0_log():
    return engine.sim.l0_log


# ---------------------------------------------------------------------- simulazione
@app.post("/api/sim/play", tags=["simulazione"])
def play(body: SpeedBody | None = None):
    if body:
        engine.speed = body.speed
    engine.running = True
    return {"running": True, "speed": engine.speed}


@app.post("/api/sim/pause", tags=["simulazione"])
def pause():
    engine.running = False
    return {"running": False}


@app.post("/api/sim/speed", tags=["simulazione"])
def set_speed(body: SpeedBody):
    engine.speed = max(0.5, min(body.speed, 40))
    return {"speed": engine.speed}


@app.post("/api/sim/step", tags=["simulazione"])
def step(body: StepBody):
    engine.step(max(1, min(body.n, 400)))
    return {"time": engine.sim.iso()}


@app.post("/api/sim/reset", tags=["simulazione"])
def reset():
    engine.running = False
    engine.reset()
    return {"time": engine.sim.iso()}


@app.get("/api/scenarios", tags=["scenari"])
def list_scenarios():
    return scenarios.SCENARIOS


@app.post("/api/scenarios/{scenario_id}", tags=["scenari"])
def inject(scenario_id: str):
    try:
        return scenarios.apply(engine, scenario_id)
    except KeyError:
        raise HTTPException(404, f"Scenario sconosciuto: {scenario_id}")


# ---------------------------------------------------------------------- agente
@app.get("/api/agent/runs", tags=["agente"])
def list_runs():
    return [run_summary(r) for r in engine.runs]


def _find_run(run_id: str) -> dict:
    run = next((r for r in engine.runs if r["id"] == run_id), None)
    if run is None:
        raise HTTPException(404, f"Esecuzione non trovata: {run_id}")
    return run


@app.get("/api/agent/runs/{run_id}", tags=["agente"], summary="Esecuzione completa: messaggi grezzi + passi leggibili")
def get_run(run_id: str):
    return _find_run(run_id)


@app.get("/api/agent/runs/{run_id}/report.md", tags=["agente"], response_class=PlainTextResponse)
def get_run_markdown(run_id: str):
    return to_markdown(_find_run(run_id))


@app.get("/api/agent/tools", tags=["agente"], summary="Definizioni dei tool (formato Ollama/OpenAI)")
def get_tools():
    return TOOL_SPECS


@app.get("/api/agent/system-prompt", tags=["agente"], response_class=PlainTextResponse)
def get_system_prompt():
    return SYSTEM_PROMPT


@app.post("/api/chat", tags=["agente"])
def chat(body: ChatBody):
    run = engine.chat(body.question)
    answer = run["decision"] if isinstance(run["decision"], str) else (run.get("error") or "Nessuna risposta")
    return {"answer": answer, "steps": run["steps"], "model": run["model"]}


# ---------------------------------------------------------------------- azioni umane
@app.post("/api/harvest", tags=["azioni umane"])
def harvest(body: HarvestBody):
    with engine.lock:
        item = engine.sim.harvest(body.level)
        engine.sim.add_event("info", "Raccolto registrato dall'operatore",
                             f"{item['quantity_kg']} kg di {item['crop_name']}", "HUMAN")
        return item


@app.post("/api/inventory/{item_id}/consume", tags=["azioni umane"])
def consume(item_id: str, body: ConsumeBody):
    with engine.lock:
        it = next((i for i in engine.sim.inventory if i["id"] == item_id), None)
        if it is None or body.quantity_kg <= 0 or body.quantity_kg > it["quantity_kg"]:
            raise HTTPException(422, "Quantità non disponibile")
        it["quantity_kg"] = round(it["quantity_kg"] - body.quantity_kg, 2)
        engine.sim.add_event("info", "Consumo registrato", f"{body.quantity_kg} kg di {it['crop_name']}", "HUMAN")
        return it


@app.post("/api/menus/{menu_id}/approve", tags=["azioni umane"])
def approve_menu(menu_id: str):
    with engine.lock:
        m = next((x for x in engine.sim.menus if x["id"] == menu_id), None)
        if m is None:
            raise HTTPException(404, "Menu non trovato")
        if m["status"] != "approved":
            for crop_id, kg in m["greenhouse_kg"].items():
                need = kg
                for it in sorted((i for i in engine.sim.inventory if i["crop_id"] == crop_id), key=lambda i: i["expiry"]):
                    take = min(need, it["quantity_kg"])
                    it["quantity_kg"] = round(it["quantity_kg"] - take, 2)
                    need -= take
            m["status"] = "approved"
            engine.sim.add_event("info", "Menu approvato", f"{m['title']} · {m['servings']} porzioni", "HUMAN")
        return m
