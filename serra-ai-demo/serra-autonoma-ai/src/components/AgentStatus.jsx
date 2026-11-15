import React from "react";
import { BrainCircuit, Gauge, ShieldCheck, WifiOff } from "lucide-react";

// Architettura a 3 livelli del dataset: L0 Safety Gate, L1 Optimizer, L2 Orchestratore LLM.
const names = {
  L2_ORCHESTRATOR: ["L2 · Orchestratore LLM", BrainCircuit],
  L1_OPTIMIZER: ["L1 · Optimizer 24 h", Gauge],
  L0_SAFETY: ["L0 · Safety Gate", ShieldCheck]
};
const order = ["L2_ORCHESTRATOR", "L1_OPTIMIZER", "L0_SAFETY"];

export default function AgentStatus({ heartbeats }) {
  const sorted = [...heartbeats].sort((a, b) => order.indexOf(a.agent_layer) - order.indexOf(b.agent_layer));
  return <div className="agent-strip">
    {sorted.map((h) => {
      const [label, Icon] = names[h.agent_layer] || [h.agent_layer, BrainCircuit];
      const offline = h.status === "offline";
      return <div className={`agent-pill ${offline ? "offline" : ""}`} key={h.agent_layer} title={h.agent_name}>
        {offline ? <WifiOff size={15}/> : <Icon size={15}/>}
        <span>{label}</span><i className="dot"/>
        <small>{offline ? "Nodo offline" : "Online"}</small>
      </div>;
    })}
  </div>;
}
