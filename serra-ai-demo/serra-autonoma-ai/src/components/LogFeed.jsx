import React, { useState } from "react";
import { BrainCircuit, ChevronRight, Clock3, Gauge, ShieldCheck } from "lucide-react";
import { simTime } from "../utils/format";

const meta = {
  L2_ORCHESTRATOR: { label: "L2 · Orchestratore", icon: BrainCircuit, color: "purple" },
  L1_OPTIMIZER: { label: "L1 · Optimizer", icon: Gauge, color: "blue" },
  L0_SAFETY: { label: "L0 · Safety Gate", icon: ShieldCheck, color: "green" }
};
const verdictClass = { ALLOWED: "fresh", CLIPPED: "warning", BLOCKED: "urgent" };

export default function LogFeed({ logs, onOpenRun }) {
  const [filter, setFilter] = useState("ALL");
  const visible = logs.filter((x) => filter === "ALL" || x.agent_layer === filter);
  return <section className="panel">
    <div className="panel-head"><div><span className="eyebrow">TRASPARENZA · XAI</span><h2>Feed decisionale</h2></div>
      <select value={filter} onChange={(e) => setFilter(e.target.value)}>
        <option value="ALL">Tutti i livelli</option><option value="L2_ORCHESTRATOR">L2 · Orchestratore</option>
        <option value="L1_OPTIMIZER">L1 · Optimizer</option><option value="L0_SAFETY">L0 · Safety Gate</option>
      </select>
    </div>
    {visible.length === 0 && <p className="empty-note">Nessuna decisione ancora: avvia la simulazione o lancia uno scenario.</p>}
    <div className="log-list">{visible.slice(0, 8).map((log) => {
      const m = meta[log.agent_layer] || meta.L2_ORCHESTRATOR; const Icon = m.icon;
      const clickable = Boolean(log.run_id && onOpenRun);
      return <article className={`log-item ${clickable ? "clickable" : ""}`} key={log.id} onClick={() => clickable && onOpenRun(log.run_id)}>
        <div className={`log-icon ${m.color}`}><Icon size={17}/></div>
        <div className="log-copy"><div className="log-title">{log.action_summary}
          {log.verdict && <span className={`status-badge ${verdictClass[log.verdict]}`}>L0 {log.verdict}</span>}</div>
          <p>{log.reasoning}</p><small>{m.label} · {log.agent_name}{clickable && <> · <b className="link-like">vedi ragionamento <ChevronRight size={11}/></b></>}</small></div>
        <time><Clock3 size={12}/>{simTime(log.timestamp)}</time>
      </article>;
    })}</div>
  </section>;
}
