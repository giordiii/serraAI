import React, { useEffect, useState } from "react";
import {
  BrainCircuit, CheckCircle2, Code2, Download, Inbox, MessageSquareText, ShieldAlert,
  ShieldCheck, Sparkles, Wrench, Zap
} from "lucide-react";
import { dataProvider } from "../services/dataProvider";
import { simDateTime, simTime } from "../utils/format";

const verdictClass = { ALLOWED: "fresh", CLIPPED: "warning", BLOCKED: "urgent" };
const kindMeta = {
  trigger: { icon: Zap, label: "Evento", cls: "k-trigger" },
  thought: { icon: MessageSquareText, label: "Ragionamento", cls: "k-thought" },
  tool_call: { icon: Wrench, label: "Chiamata tool", cls: "k-call" },
  tool_result: { icon: Inbox, label: "Risultato", cls: "k-result" },
  decision: { icon: CheckCircle2, label: "Decisione", cls: "k-decision" },
  answer: { icon: Sparkles, label: "Risposta", cls: "k-decision" }
};

function Step({ step }) {
  const m = kindMeta[step.kind] || kindMeta.thought;
  let Icon = m.icon;
  if (step.tool === "submit_proposal" && step.kind === "tool_result") Icon = step.tone === "bad" ? ShieldAlert : ShieldCheck;
  return <li className={`r-step ${m.cls} ${step.tone ? `tone-${step.tone}` : ""}`}>
    <div className="r-dot"><Icon size={14}/></div>
    <div className="r-body">
      <div className="r-kind">{step.label ? `${m.label} · ${step.label}` : m.label}</div>
      <p>{step.text}</p>
      {step.kind === "decision" && step.decision && <div className="r-decision">
        <div><span>Diagnosi</span><b>{step.decision.diagnosi}</b></div>
        {step.decision.verdetto_l0 && <div><span>Verdetto L0</span><b className={`status-badge ${verdictClass[step.decision.verdetto_l0]}`}>{step.decision.verdetto_l0}</b></div>}
        <div><span>Confidenza</span><b>{Math.round((step.decision.confidenza || 0) * 100)}%</b></div>
        <div><span>Intervento umano</span><b>{step.decision.richiede_umano ? "Richiesto" : "Non necessario"}</b></div>
        {step.decision.evidenze?.length > 0 && <ul>{step.decision.evidenze.map((e, i) => <li key={i}>{e}</li>)}</ul>}
      </div>}
    </div>
  </li>;
}

export default function ReasoningView({ runs, selectedId, onSelect, model }) {
  const [detail, setDetail] = useState(null);
  const [tab, setTab] = useState("human");
  const current = selectedId || runs[0]?.id;

  useEffect(() => {
    let active = true;
    if (!current) { setDetail(null); return; }
    dataProvider.getRun(current).then((r) => active && setDetail(r)).catch(() => active && setDetail(null));
    return () => { active = false; };
  }, [current]);

  return <div className="view-stack">
    <div className="page-heading"><div><span className="eyebrow">L2 · ORCHESTRATORE LLM · TOOL CALLING</span><h1>Ragionamento dell'agente</h1>
      <p>Ogni decisione mostrata passo per passo: cosa ha letto, quali tool ha usato, cosa ha proposto e cosa ha deciso il Safety Gate L0.</p></div></div>
    <div className="model-note"><BrainCircuit size={16}/><span>Modello: <b>{model}</b>. Le tracce hanno lo stesso formato di un LLM locale con tool calling (Ollama); i tool sono funzioni reali del digital twin.</span></div>
    {runs.length === 0 ? <section className="panel"><p className="empty-note">Ancora nessuna esecuzione. Avvia la simulazione o scegli uno scenario dal menu <b>Scenari</b>.</p></section> :
    <div className="reasoning-layout">
      <section className="panel run-list">
        <div className="panel-head"><div><span className="eyebrow">ESECUZIONI</span><h2>{runs.length} decisioni</h2></div></div>
        {runs.map((r) => <button key={r.id} className={`run-item ${r.id === current ? "active" : ""}`} onClick={() => onSelect(r.id)}>
          <div className="run-top"><b>{r.title}</b>{r.verdict && <span className={`status-badge ${verdictClass[r.verdict]}`}>{r.verdict}</span>}</div>
          <span>{r.id} · {simTime(r.started_at)} · {r.tool_calls} tool</span>
        </button>)}
      </section>
      <section className="panel run-detail">
        {!detail ? <p className="empty-note">Caricamento…</p> : <>
          <div className="panel-head run-head"><div><span className="eyebrow">{detail.id} · {simDateTime(detail.started_at)}</span><h2>{detail.trigger.title}</h2>
            <small className="run-meta">{detail.tool_calls} chiamate a tool · ~{detail.tokens} token · origine dati {detail.data_origin}</small></div>
            <div className="run-actions">
              <div className="tabs"><button className={tab === "human" ? "active" : ""} onClick={() => setTab("human")}>Leggibile</button>
                <button className={tab === "raw" ? "active" : ""} onClick={() => setTab("raw")}><Code2 size={13}/> JSON</button></div>
              <a className="small-button" href={dataProvider.runMarkdownUrl(detail.id)} download={`${detail.id}.md`}><Download size={12}/> .md</a>
            </div>
          </div>
          {detail.error && <p className="error-note">Errore LLM: {detail.error}</p>}
          {tab === "human"
            ? <ol className="r-timeline">{detail.steps.map((s, i) => <Step key={i} step={s}/>)}</ol>
            : <pre className="raw-json">{JSON.stringify(detail.messages, null, 2)}</pre>}
        </>}
      </section>
    </div>}
  </div>;
}
