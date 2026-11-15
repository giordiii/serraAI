import React, { useEffect, useState } from "react";
import {
  AlertTriangle, ArrowUpRight, Bot, BrainCircuit, Check, CheckCircle2, ChevronDown, ChevronRight,
  CircleHelp, Clock3, Droplets, Euro, Leaf, Menu, MessageCircle, Package, Plus, Send,
  ShoppingBasket, Sprout, Thermometer, X, Zap, LayoutDashboard, ChefHat
} from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { dataProvider } from "./services/dataProvider";
import AgentStatus from "./components/AgentStatus";
import LogFeed from "./components/LogFeed";
import SimControls from "./components/SimControls";
import ReasoningView from "./components/ReasoningView";
import EnergyPanel from "./components/EnergyPanel";
import { simDate, simTime } from "./utils/format";

const fmt = (n, digits = 1) => Number(n).toFixed(digits);
const nav = [
  ["dashboard", "Dashboard", LayoutDashboard], ["reasoning", "Ragionamento AI", BrainCircuit],
  ["inventory", "Dispensa FEFO", Package], ["menus", "Menù zero-waste", ChefHat], ["chat", "Chat agente", MessageCircle]
];
const statusLabel = { READY_TODAY: "Pronta oggi", NEAR_HARVEST: "Quasi pronta", GROWING: "In crescita", JUST_TRANSPLANTED: "Appena trapiantata" };

function Metric({ label, value, unit, icon: Icon, note, tone = "green" }) {
  return <div className="metric-card"><div className={`metric-icon ${tone}`}><Icon size={18}/></div>
    <div className="metric-label">{label}</div><div className="metric-value">{value}<small>{unit}</small></div>
    <div className="metric-note">{note}</div></div>;
}

function CropCard({ batch, telemetry, zone, onHarvest }) {
  const [expanded, setExpanded] = useState(false);
  const days = batch.days_to_harvest;
  return <article className="crop-card">
    <div className="crop-top"><div className="crop-avatar"><Sprout size={22}/></div>
      <div className="crop-name"><h3>{batch.crop_name}</h3><span>Ripiano {batch.level} · {zone?.name || "Zona non assegnata"}</span></div>
      <span className={`health ${batch.health_score >= 90 ? "good" : "mid"}`}>{batch.health_score}% salute</span>
    </div>
    <div className="crop-stats"><div><span>Ciclo colturale</span><b>{batch.maturity_pct}%</b></div><div><span>Resa stimata</span><b>{fmt(batch.estimated_yield_kg)} kg</b></div></div>
    <div className="progress"><span style={{ width: `${batch.maturity_pct}%` }}/></div>
    <div className="harvest-line"><span><Clock3 size={14}/>{days === 0 ? "Pronta al raccolto" : `Raccolta tra ${days} giorni · ${statusLabel[batch.status]}`}</span>
      <button className="text-button" onClick={() => onHarvest(batch)} disabled={batch.estimated_yield_kg <= 0}>Registra raccolto <ChevronRight size={14}/></button></div>
    <button className="expand-button" onClick={() => setExpanded(!expanded)}>{expanded ? "Nascondi dettagli" : "Dettagli tecnici"} <ChevronDown size={14}/></button>
    {expanded && <div className="technical-grid">
      <div><span>Temperatura</span><b>{telemetry?.temp ?? "—"} °C</b></div>
      <div><span>Umidità</span><b>{telemetry?.humidity ?? "—"}%</b></div>
      <div><span>VPD</span><b>{telemetry?.vpd ?? "—"} kPa</b></div>
      <div><span>pH</span><b>{telemetry?.ph ?? "—"}</b></div>
      <div><span>EC</span><b>{telemetry?.ec ?? "—"} mS/cm</b></div>
      <div><span>Luce (PPFD)</span><b>{telemetry?.light ?? "—"} µmol</b></div>
      <div><span>Rischio tipburn</span><b>{telemetry?.tipburn ?? "—"}</b></div>
      <div><span>Indice di verde</span><b>{telemetry?.greenness ?? "—"}</b></div>
      <div><span>CO₂</span><b>{telemetry?.co2 ?? "—"} ppm</b></div>
    </div>}
  </article>;
}

function Dashboard({ state, onHarvest, onOpenRun }) {
  const [zoneId, setZoneId] = useState("ZONE_1_LEAFY");
  const latest = state.telemetry_readings.find((t) => t.zone_id === zoneId) || state.telemetry_readings[0];
  const ready = state.crop_batches.filter((b) => b.days_to_harvest <= 3).reduce((s, b) => s + b.estimated_yield_kg, 0);
  const chart = (state.telemetry_history[zoneId] || []).filter((_, i, a) => (a.length - 1 - i) % 2 === 0)
    .map((x) => ({ time: simTime(x.timestamp), temp: x.temp, humidity: x.humidity }));
  const zoneName = state.zones.find((z) => z.id === zoneId)?.name;
  return <div className="view-stack">
    <div className="welcome"><div><span className="eyebrow">CENTRO DI CONTROLLO · {state.sim.site.toUpperCase()}</span><h1>La serra, in equilibrio.</h1><p>Digital twin della serra verticale: 4 ripiani, 2 zone climatiche, orchestrati da L0 · L1 · L2.</p></div>
      <div className="live-label"><span className="pulse"/> {state.sim.running ? "SIMULAZIONE IN CORSO" : "SIMULAZIONE IN PAUSA"}</div></div>
    {state.sim.active_scenario && <div className="scenario-banner"><AlertTriangle size={16}/><div><b>Scenario attivo: {state.sim.active_scenario.title}</b>
      <span>{state.sim.active_scenario.expected}</span></div>
      {state.sim.active_overrides.length > 0 && <small>Override attivi: {state.sim.active_overrides.map((o) => o.key).join(", ")}</small>}</div>}
    <div className="metrics-grid">
      <Metric label="Temperatura" value={fmt(latest.temp)} unit="°C" icon={Thermometer} note={zoneName}/>
      <Metric label="Umidità relativa" value={fmt(latest.humidity, 0)} unit="%" icon={Droplets} note={`VPD ${latest.vpd} kPa · tipburn ${latest.tipburn}`} tone="blue"/>
      <Metric label="Pronto entro 3 giorni" value={fmt(ready)} unit="kg" icon={Sprout} note={`${state.crop_batches.length} ripiani monitorati`} tone="orange"/>
      <Metric label="Costo energia oggi" value={fmt(state.kpi.energy_cost_today_eur, 2)} unit="€" icon={Euro} note={`${state.kpi.pv_share_today_pct}% coperto da fotovoltaico`} tone="purple"/>
    </div>
    <AgentStatus heartbeats={state.agent_heartbeats}/>
    <div className="content-grid">
      <section className="panel"><div className="panel-head"><div><span className="eyebrow">COMPUTER VISION · RIPIANI</span><h2>Stato delle colture</h2></div><span className="subtle-tag">{state.crop_batches.length} ripiani attivi</span></div>
        <div className="crop-list">{state.crop_batches.map((b) => <CropCard key={b.id} batch={b} zone={state.zones.find((z) => z.id === b.zone_id)} telemetry={state.telemetry_readings.find((t) => t.zone_id === b.zone_id)} onHarvest={onHarvest}/>)}</div>
      </section>
      <section className="panel chart-panel"><div className="panel-head"><div><span className="eyebrow">TELEMETRIA · ULTIME 12 ORE SIMULATE</span><h2>Microclima</h2></div>
        <select value={zoneId} onChange={(e) => setZoneId(e.target.value)}>{state.zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}</select></div>
        <div className="chart-legend"><span><i className="legend-temp"/> Temperatura °C</span><span><i className="legend-hum"/> Umidità %</span></div>
        <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={chart}>
          <defs><linearGradient id="tempFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#27875a" stopOpacity={0.2}/><stop offset="100%" stopColor="#27875a" stopOpacity={0}/></linearGradient></defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e9eee9"/><XAxis dataKey="time" tick={{ fontSize: 10, fill: "#829087" }} axisLine={false} tickLine={false} minTickGap={24}/><YAxis tick={{ fontSize: 10, fill: "#829087" }} axisLine={false} tickLine={false} domain={[10, 90]}/><Tooltip/>
          <Area type="monotone" dataKey="temp" stroke="#27875a" fill="url(#tempFill)" strokeWidth={2} name="Temperatura" isAnimationActive={false}/>
          <Area type="monotone" dataKey="humidity" stroke="#4b91c8" fill="transparent" strokeWidth={2} name="Umidità" isAnimationActive={false}/>
        </AreaChart></ResponsiveContainer></div>
        <div className="water-card"><div className="water-icon"><Droplets size={19}/></div><div><b>Efficienza risorse</b><p>Acqua <strong>−{state.kpi.water_saving_pct}%</strong> vs pieno campo · Fotovoltaico oggi <strong>{state.kpi.pv_share_today_pct}%</strong></p></div><span className="trend"><ArrowUpRight size={15}/> {fmt(state.kpi.harvested_kg)} kg raccolti</span></div>
      </section>
    </div>
    <EnergyPanel energy={state.energy}/>
    <LogFeed logs={state.agent_logs} onOpenRun={onOpenRun}/>
  </div>;
}

function Inventory({ state, onConsume, onHarvest }) {
  const [selected, setSelected] = useState("");
  const [qty, setQty] = useState("0.5");
  const sorted = [...state.inventory_items].sort((a, b) => a.expiry_date.localeCompare(b.expiry_date));
  const status = { urgent: ["Urgente", "urgent"], warning: ["In scadenza", "warning"], fresh: ["Fresco", "fresh"] };
  return <div className="view-stack"><div className="page-heading"><div><span className="eyebrow">L2 · LOGICA FEFO</span><h1>Dispensa & stoccaggio</h1><p>Prima scade, prima viene utilizzato. La disponibilità viene aggiornata dagli eventi.</p></div></div>
    <div className="inventory-summary"><div><Package/><span>Prodotti in dispensa</span><b>{state.inventory_items.length}</b></div><div><AlertTriangle/><span>Da utilizzare presto</span><b>{state.inventory_items.filter((x) => x.fefo_status !== "fresh").length}</b></div><div><ShoppingBasket/><span>Quantità disponibile</span><b>{fmt(state.inventory_items.reduce((s, x) => s + x.quantity_kg, 0))} kg</b></div></div>
    <section className="panel"><div className="panel-head"><div><span className="eyebrow">INVENTARIO ATTUALE</span><h2>Lotti ordinati per scadenza</h2></div><span className="subtle-tag">FEFO attivo</span></div>
      {sorted.length === 0 && <p className="empty-note">Dispensa vuota: la raccolta viene pianificata dall'agente ogni giorno alle 07:00 (o con lo scenario "Raccolta e menu").</p>}
      {sorted.length > 0 && <div className="table-scroll"><table><thead><tr><th>Prodotto</th><th>Quantità</th><th>Raccolto il</th><th>Scadenza</th><th>Stato FEFO</th><th>Azione</th></tr></thead><tbody>
        {sorted.map((x) => <tr key={x.id}><td><b>{x.crop_name}</b></td><td>{fmt(x.quantity_kg)} kg</td><td>{simDate(x.harvested_at)}</td><td>{simDate(x.expiry_date)}</td><td><span className={`status-badge ${status[x.fefo_status][1]}`}>{status[x.fefo_status][0]}</span></td><td><button className="small-button" onClick={() => { setSelected(x.id); setQty("0.5"); }}>Scarica consumo</button></td></tr>)}
      </tbody></table></div>}
      {selected && <div className="inline-action"><div><b>Scarica {state.inventory_items.find((x) => x.id === selected)?.crop_name}</b><span>Quantità da registrare (kg)</span></div><input type="number" min="0.01" step="0.1" value={qty} onChange={(e) => setQty(e.target.value)}/><button className="primary-button" onClick={() => { onConsume(selected, Number(qty)); setSelected(""); }}>Conferma consumo</button><button className="icon-button" onClick={() => setSelected("")}><X size={17}/></button></div>}
    </section>
    <section className="panel"><div className="panel-head"><div><span className="eyebrow">PREVISIONE · RIPIANI</span><h2>Prossimi raccolti</h2></div></div>
      <div className="harvest-timeline">{[...state.crop_batches].sort((a, b) => a.days_to_harvest - b.days_to_harvest).map((b) => <div className="timeline-row" key={b.id}><div className="timeline-date">{simDate(b.estimated_harvest_date)}</div><div className="timeline-marker"/><div className="timeline-info"><b>{b.crop_name}</b><span>Ripiano {b.level} · {fmt(b.estimated_yield_kg)} kg stimati · ciclo {b.maturity_pct}%</span></div><button className="text-button" onClick={() => onHarvest(b)}>Registra <Plus size={14}/></button></div>)}</div>
    </section>
  </div>;
}

function Menus({ state, onApprove }) {
  return <div className="view-stack"><div className="page-heading"><div><span className="eyebrow">L2 · ORCHESTRATORE · MENU MENSA</span><h1>Menù generati dall'AI</h1><p>Proposte basate su raccolti, scadenze FEFO e ricette campane della mensa ({state.kpi.daily_meals} pasti/giorno).</p></div></div>
    {state.generated_menus.length === 0 && <section className="panel"><p className="empty-note">Nessun menù proposto. L'agente pianifica raccolta e menù ogni giorno alle 07:00, oppure lancia lo scenario "Raccolta e menu".</p></section>}
    {state.generated_menus.map((m) => <section className="menu-card panel" key={m.id}><div className="menu-banner"><div className="menu-art"><ChefHat size={34}/></div><div className="menu-title"><span className="eyebrow">PROPOSTA · {simDate(m.target_date)} · {m.course}</span><h2>{m.title}</h2><span>{m.servings} porzioni · valore prodotto serra {fmt(m.value_eur, 2)} € · {m.status === "approved" ? "Approvato" : "In attesa di approvazione"}</span></div><span className={`status-badge ${m.status === "approved" ? "fresh" : "proposed"}`}>{m.status === "approved" ? "Approvato" : "Proposto"}</span></div>
      <div className="self-sufficiency"><div><span>Ingredienti vegetali dalla serra</span><b>{m.self_sufficiency_pct}%</b></div><div className="progress"><span style={{ width: `${m.self_sufficiency_pct}%` }}/></div><small>{m.territorial_link}</small></div>
      <div className="menu-columns"><div><h3><Leaf size={16}/> Dalla serra</h3>{m.serra_ingredients.map((a) => <div className="ingredient" key={a.crop_id}><span>{a.crop_name}</span><b>{a.quantity_kg} kg</b></div>)}</div>
        <div><h3><ShoppingBasket size={16}/> Spesa integrativa</h3>{m.external_shopping_list.length === 0 ? <div className="ingredient"><span>Nessun ortaggio da acquistare</span></div> : m.external_shopping_list.map((a) => <div className="ingredient" key={a.name}><span>{a.name}</span><b>{a.quantity}</b></div>)}</div></div>
      {m.status === "proposed" ? <div className="menu-footer"><span><CheckCircle2 size={15}/> L'approvazione scarica gli ingredienti dalla dispensa (FEFO) e notifica l'orchestratore.</span><button className="primary-button" onClick={() => onApprove(m.id)}><Check size={16}/> Approva menù</button></div> : <div className="approved-note"><CheckCircle2 size={16}/> Menù approvato. Ingredienti riservati e feedback inviato all'orchestratore.</div>}
    </section>)}
  </div>;
}

function Chat({ state, ask }) {
  const [messages, setMessages] = useState([{ role: "assistant", text: "Ciao! Sono l'interfaccia conversazionale della serra. Uso gli stessi tool dell'orchestratore per leggere clima, energia, raccolti e dispensa. Cosa vuoi sapere?" }]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const suggestions = ["Qual è la temperatura attuale?", "Quanto costa l'energia adesso?", "Quale coltura è pronta al raccolto?"];
  async function send(text = input) {
    if (!text.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", text }]); setInput(""); setBusy(true);
    try {
      const res = await ask(text);
      setMessages((m) => [...m, { role: "assistant", text: res.answer, steps: res.steps.filter((s) => s.kind === "tool_call") }]);
    } catch (e) { setMessages((m) => [...m, { role: "assistant", text: e.message }]); }
    setBusy(false);
  }
  return <div className="chat-layout"><div className="chat-intro"><span className="eyebrow">L2 · INTERFACCIA CONVERSAZIONALE</span><h1>Parla con la serra.</h1><p>Un'interfaccia conversazionale per esplorare i dati del sistema in linguaggio naturale. Ogni risposta mostra i tool usati.</p><div className="chat-context"><Bot size={18}/><div><b>Collegato al digital twin</b><span>{state.crop_batches.length} ripiani · {state.inventory_items.length} lotti in dispensa · {state.agent_runs.length} decisioni</span></div></div></div>
    <section className="chat-window"><div className="chat-header"><div className="bot-avatar"><Bot size={20}/></div><div><b>Agente Serra AI</b><span><i/> {state.sim.llm_model}</span></div></div>
      <div className="chat-messages">{messages.map((m, i) => <div className={`message ${m.role}`} key={i}><div className="message-avatar">{m.role === "assistant" ? <Bot size={15}/> : "U"}</div><div className="bubble">{m.text}
        {m.steps?.length > 0 && <div className="chat-tools">{m.steps.map((s, j) => <span key={j}>🔧 {s.label}</span>)}</div>}</div></div>)}{busy && <div className="typing">L'agente sta elaborando…</div>}</div>
      {messages.length === 1 && <div className="suggestions">{suggestions.map((s) => <button key={s} onClick={() => send(s)}>{s}<ChevronRight size={13}/></button>)}</div>}
      <form className="chat-input" onSubmit={(e) => { e.preventDefault(); send(); }}><input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Chiedi qualcosa alla serra…" /><button className="send-button" disabled={!input.trim() || busy}><Send size={17}/></button></form>
    </section>
  </div>;
}

function HarvestModal({ batch, onClose, onSubmit }) {
  if (!batch) return null;
  return <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}><div className="modal">
    <div className="modal-head"><div><span className="eyebrow">HUMAN-IN-THE-LOOP</span><h2>Registra raccolto</h2></div><button className="icon-button" onClick={onClose}><X/></button></div>
    <p>Il ripiano viene raccolto per intero: la parte commestibile passa in dispensa e il ripiano riparte con un nuovo trapianto.</p>
    <div className="harvest-product"><Sprout/><div><b>{batch.crop_name} · ripiano {batch.level}</b><span>Resa commestibile stimata: {batch.estimated_yield_kg} kg · ciclo {batch.maturity_pct}%</span></div></div>
    <div className="modal-actions"><button className="secondary-button" onClick={onClose}>Annulla</button><button className="primary-button" onClick={onSubmit} disabled={batch.estimated_yield_kg <= 0}>Conferma raccolto</button></div>
  </div></div>;
}

export default function App() {
  const [state, setState] = useState(null);
  const [error, setError] = useState("");
  const [page, setPage] = useState("dashboard");
  const [harvestBatch, setHarvestBatch] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [toast, setToast] = useState("");
  const [mobileNav, setMobileNav] = useState(false);

  useEffect(() => {
    let active = true;
    dataProvider.getSnapshot().then((s) => active && setState(s)).catch((e) => active && setError(e.message));
    const unsubscribe = dataProvider.subscribeToDatabaseChanges(({ state: s, type, newRuns, error: err }) => {
      if (type === "BACKEND_ERROR") { setError(err); return; }
      setError(""); setState(s);
      if (newRuns?.length) notify(`L2 · ${newRuns[0].title}${newRuns[0].verdict ? ` · L0 ${newRuns[0].verdict}` : ""}`);
      if (type === "HUMAN_FEEDBACK") notify("Azione registrata e inviata all'orchestratore");
    });
    return () => { active = false; unsubscribe(); };
  }, []);

  function notify(message) { setToast(message); window.clearTimeout(notify.timer); notify.timer = window.setTimeout(() => setToast(""), 3600); }
  const guard = (fn) => async (...args) => { try { await fn(...args); } catch (e) { notify(e.message); } };
  const harvest = guard(async () => { await dataProvider.registerHarvest(harvestBatch); setHarvestBatch(null); notify("Raccolto trasferito in dispensa"); });
  const consume = guard(async (id, qty) => { await dataProvider.consumeInventory(id, qty); notify("Consumo registrato"); });
  const approve = guard(async (id) => { await dataProvider.approveMenu(id); notify("Menù approvato · ingredienti riservati"); });
  const scenario = guard(async (s) => { await dataProvider.injectScenario(s.id); notify(`Scenario iniettato: ${s.title}`); });
  const openRun = (id) => { setSelectedRun(id); setPage("reasoning"); };

  if (!state) return <div className="loading-screen"><Sprout size={28}/> {error
    ? <span>Backend non raggiungibile ({error}). Avvia <code>serra_backend</code> sulla porta 8000.</span> : "Caricamento serra…"}</div>;

  const titles = { dashboard: "Dashboard", reasoning: "Ragionamento AI", inventory: "Dispensa", menus: "Menù zero-waste", chat: "Agente AI" };
  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? "mobile-open" : ""}`}><div className="brand"><div className="brand-mark"><Sprout size={23}/></div><div><b>serra<span>AI</span></b><small>UNIVERSITY ECOSYSTEM</small></div><button className="mobile-close icon-button" onClick={() => setMobileNav(false)}><X/></button></div>
      <div className="sidebar-label">WORKSPACE</div><nav>{nav.map(([id, label, Icon]) => <button key={id} className={page === id ? "active" : ""} onClick={() => { setPage(id); setMobileNav(false); }}><Icon size={18}/>{label}{page === id && <ChevronRight size={15} className="nav-chevron"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="campus-card"><div className="campus-icon"><Leaf size={18}/></div><b>Campus sostenibile</b><p>{state.sim.canteen}</p><span><i/> Modalità simulazione</span></div><div className="user-mini"><div className="user-avatar">U</div><div><b>Utente serra</b><small>Operatore · Kiosk</small></div><CircleHelp size={17}/></div></div>
    </aside>
    {mobileNav && <div className="mobile-scrim" onClick={() => setMobileNav(false)}/>}
    <main className="main-area"><header className="topbar"><div className="topbar-left"><button className="mobile-menu icon-button" onClick={() => setMobileNav(true)}><Menu/></button><div><span className="breadcrumb">SERRA /</span> {titles[page]}</div></div>
      <div className="topbar-actions"><SimControls sim={state.sim} scenarios={state.scenarios}
        onPlay={guard(() => dataProvider.play())} onPause={guard(() => dataProvider.pause())} onStep={guard(() => dataProvider.step(4))}
        onReset={guard(async () => { await dataProvider.reset(); setSelectedRun(null); notify("Simulazione riportata all'inizio"); })}
        onSpeed={guard((v) => dataProvider.setSpeed(v))} onScenario={scenario}/></div>
    </header>
    {error && <div className="error-banner">Connessione al backend persa: {error}</div>}
    <div className="page-content">{page === "dashboard" && <Dashboard state={state} onHarvest={setHarvestBatch} onOpenRun={openRun}/>}
      {page === "reasoning" && <ReasoningView runs={state.agent_runs} selectedId={selectedRun} onSelect={setSelectedRun} model={state.sim.llm_model}/>}
      {page === "inventory" && <Inventory state={state} onConsume={consume} onHarvest={setHarvestBatch}/>}
      {page === "menus" && <Menus state={state} onApprove={approve}/>}
      {page === "chat" && <Chat state={state} ask={dataProvider.askAssistant}/>}</div>
    <footer className="footer"><span>© Serra AI · L0 Safety · L1 Optimizer · L2 Orchestratore</span><span>Data layer <b>backend simulato (FastAPI)</b> · {state.sim.llm_model}</span></footer></main>
    <HarvestModal batch={harvestBatch} onClose={() => setHarvestBatch(null)} onSubmit={harvest}/>
    {toast && <div className="toast"><Zap size={17}/>{toast}</div>}
  </div>;
}
