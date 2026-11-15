// Adapter dati: i componenti dipendono solo da questo contratto, non dalla sorgente.
// Sorgente attuale: backend simulato (serra_backend, FastAPI) raggiunto via proxy Vite su /api.
// Il vecchio mock statico resta in ../mockData.js solo come riferimento storico.

const API = import.meta.env.VITE_API_BASE_URL || "/api";
const POLL_MS = 800;
const listeners = new Set();
let state = null;
let timer = null;
let lastError = null;

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* risposta non JSON */ }
    throw new Error(`Backend: ${detail}`);
  }
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.text();
}

async function refresh(eventType = "DB_CHANGE") {
  try {
    const next = await request("/snapshot");
    const prevRuns = new Set((state?.agent_runs || []).map((r) => r.id));
    const newRuns = state ? next.agent_runs.filter((r) => !prevRuns.has(r.id)) : [];
    state = next;
    lastError = null;
    listeners.forEach((fn) => fn({ type: eventType, state, newRuns, at: new Date().toISOString() }));
  } catch (e) {
    lastError = e;
    listeners.forEach((fn) => fn({ type: "BACKEND_ERROR", state, error: e.message }));
  }
  return state;
}

function startPolling() {
  if (timer) return;
  timer = setInterval(() => refresh(), POLL_MS);
}

async function action(path, body, eventType) {
  const out = await request(path, { method: "POST", body });
  await refresh(eventType);
  return out;
}

export const dataProvider = {
  async getSnapshot() {
    const s = await refresh();
    startPolling();
    if (!s) throw lastError || new Error("Backend non raggiungibile");
    return s;
  },

  // Observer/Event-Bus alimentato dal polling dello snapshot.
  subscribeToDatabaseChanges(callback) {
    listeners.add(callback);
    startPolling();
    return () => listeners.delete(callback);
  },

  // Controlli del digital twin
  play: (speed) => action("/sim/play", speed ? { speed } : undefined, "SIM_CONTROL"),
  pause: () => action("/sim/pause", undefined, "SIM_CONTROL"),
  setSpeed: (speed) => action("/sim/speed", { speed }, "SIM_CONTROL"),
  step: (n = 4) => action("/sim/step", { n }, "SIM_CONTROL"),
  reset: () => action("/sim/reset", undefined, "SIM_RESET"),
  injectScenario: (id) => action(`/scenarios/${id}`, undefined, "SCENARIO"),

  // Agente L2
  getRun: (id) => request(`/agent/runs/${id}`),
  runMarkdownUrl: (id) => `${API}/agent/runs/${id}/report.md`,

  // Azioni umane (Human-in-the-Loop)
  async registerHarvest(batch) {
    return action("/harvest", { level: batch.level }, "HUMAN_FEEDBACK");
  },
  async consumeInventory(itemId, quantityKg) {
    return action(`/inventory/${itemId}/consume`, { quantity_kg: Number(quantityKg) }, "HUMAN_FEEDBACK");
  },
  async approveMenu(menuId) {
    return action(`/menus/${menuId}/approve`, undefined, "HUMAN_FEEDBACK");
  },
  async askAssistant(question) {
    return request("/chat", { method: "POST", body: { question } });
  }
};
