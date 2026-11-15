import React from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function EnergyPanel({ energy }) {
  const p = energy.plan;
  const data = p.hourly.map((h) => ({ hour: `${String(h.hour).padStart(2, "0")}`, led: +(h.led_w / 1000).toFixed(1),
    pv: +(h.pv_w / 1000).toFixed(1), pun: h.pun_eur_kwh }));
  return <section className="panel energy-panel">
    <div className="panel-head"><div><span className="eyebrow">LIVELLO 1 · OPTIMIZER 24 H</span><h2>Piano energetico</h2></div>
      <span className="subtle-tag">aggiornato {p.reason}</span></div>
    <div className="energy-kpis">
      <div><span>Costo previsto</span><b>{p.cost_eur.toFixed(2)} €/giorno</b></div>
      <div><span>Quota fotovoltaico</span><b>{p.pv_share_pct}%</b></div>
      <div><span>Risparmio vs orario fisso</span><b>{p.saving_vs_fixed_pct}%</b></div>
      <div><span>Luce zona 1 / zona 2</span><b>{p.light_windows.ZONE_1_LEAFY} · {p.light_windows.ZONE_2_WARM}</b></div>
    </div>
    <div className="chart-legend"><span><i className="legend-led"/> LED pianificati (kW)</span><span><i className="legend-pv"/> Fotovoltaico (kW)</span><span><i className="legend-pun"/> PUN (€/kWh)</span></div>
    <div className="chart-wrap small"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={data}>
      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e9eee9"/>
      <XAxis dataKey="hour" tick={{ fontSize: 10, fill: "#829087" }} axisLine={false} tickLine={false}/>
      <YAxis yAxisId="kw" tick={{ fontSize: 10, fill: "#829087" }} axisLine={false} tickLine={false}/>
      <YAxis yAxisId="eur" orientation="right" tick={{ fontSize: 10, fill: "#829087" }} axisLine={false} tickLine={false} domain={[0, "auto"]}/>
      <Tooltip/>
      <Bar yAxisId="kw" dataKey="pv" fill="#f2c46b" name="Fotovoltaico kW" radius={[3, 3, 0, 0]}/>
      <Bar yAxisId="kw" dataKey="led" fill="#27875a" name="LED kW" radius={[3, 3, 0, 0]}/>
      <Line yAxisId="eur" type="monotone" dataKey="pun" stroke="#c45d50" strokeWidth={2} dot={false} name="PUN €/kWh"/>
    </ComposedChart></ResponsiveContainer></div>
    <ul className="binding-list">{p.binding_constraints.map((b, i) => <li key={i}>{b}</li>)}</ul>
  </section>;
}
