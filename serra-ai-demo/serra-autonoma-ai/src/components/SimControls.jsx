import React, { useEffect, useRef, useState } from "react";
import { FlaskConical, Pause, Play, RotateCcw, SkipForward, ChevronDown } from "lucide-react";
import { simDateTime } from "../utils/format";

const speeds = [[2, "×1"], [6, "×3"], [16, "×8"]];

export default function SimControls({ sim, scenarios, onPlay, onPause, onStep, onReset, onSpeed, onScenario }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const close = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return <div className="sim-controls">
    <div className="sim-clock"><span className="sim-badge">SIMULAZIONE</span><b>{simDateTime(sim.time)}</b></div>
    <div className="sim-buttons">
      {sim.running
        ? <button className="icon-button sim-btn" title="Pausa" onClick={onPause}><Pause size={16}/></button>
        : <button className="icon-button sim-btn primary" title="Avvia" onClick={onPlay}><Play size={16}/></button>}
      <button className="icon-button sim-btn" title="Avanza di 1 ora" onClick={onStep}><SkipForward size={16}/></button>
      <select className="sim-speed" value={sim.speed} onChange={(e) => onSpeed(Number(e.target.value))} title="Velocità">
        {speeds.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        {!speeds.some(([v]) => v === sim.speed) && <option value={sim.speed}>{sim.speed} step/s</option>}
      </select>
      <button className="icon-button sim-btn" title="Ricomincia" onClick={onReset}><RotateCcw size={16}/></button>
    </div>
    <div className="scenario-menu" ref={ref}>
      <button className="sync-button" onClick={() => setOpen(!open)}><FlaskConical size={15}/><span>Scenari</span><ChevronDown size={13}/></button>
      {open && <div className="scenario-dropdown">
        <div className="eyebrow">INIETTA UNO SCENARIO NEL DIGITAL TWIN</div>
        {scenarios.map((s) => <button key={s.id} onClick={() => { setOpen(false); onScenario(s); }}>
          <b>{s.title}</b><span>{s.description}</span>
        </button>)}
      </div>}
    </div>
  </div>;
}
