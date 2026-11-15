// Mock relazionale: gli ID sono condivisi tra tabelle per simulare le FK PostgreSQL.
const ago = (minutes) => new Date(Date.now() - minutes * 60000).toISOString();
const day = (offset) => {
  const d = new Date(); d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
};

export const initialState = {
  zones: [
    { id: "zone-a", name: "Vasca A · Foglia" },
    { id: "zone-b", name: "Vasca B · Aromatiche" },
    { id: "zone-c", name: "Vasca C · Frutto" }
  ],
  telemetry_readings: [
    { id: "t-1", zone_id: "zone-a", temp: 22.4, humidity: 68, vpd: 0.82, ph: 6.1, ec: 1.4, light: 620, timestamp: ago(2) },
    { id: "t-2", zone_id: "zone-b", temp: 21.8, humidity: 71, vpd: 0.69, ph: 5.9, ec: 1.2, light: 540, timestamp: ago(3) },
    { id: "t-3", zone_id: "zone-c", temp: 24.1, humidity: 64, vpd: 1.02, ph: 6.3, ec: 1.8, light: 710, timestamp: ago(4) }
  ],
  crop_batches: [
    { id: "batch-1", zone_id: "zone-a", crop_name: "Lattuga romana", health_score: 96, maturity_pct: 91, estimated_yield_kg: 8.4, estimated_harvest_date: day(2), last_vision_check: ago(10) },
    { id: "batch-2", zone_id: "zone-b", crop_name: "Basilico", health_score: 89, maturity_pct: 74, estimated_yield_kg: 3.2, estimated_harvest_date: day(6), last_vision_check: ago(12) },
    { id: "batch-3", zone_id: "zone-c", crop_name: "Pomodorini", health_score: 93, maturity_pct: 58, estimated_yield_kg: 12.6, estimated_harvest_date: day(14), last_vision_check: ago(18) }
  ],
  inventory_items: [
    { id: "inv-1", crop_name: "Rucola", quantity_kg: 2.4, harvested_at: ago(36 * 60), expiry_date: day(1), fefo_status: "urgent", source_batch_id: null },
    { id: "inv-2", crop_name: "Lattuga", quantity_kg: 4.8, harvested_at: ago(18 * 60), expiry_date: day(3), fefo_status: "warning", source_batch_id: "batch-1" },
    { id: "inv-3", crop_name: "Basilico", quantity_kg: 1.6, harvested_at: ago(8 * 60), expiry_date: day(6), fefo_status: "fresh", source_batch_id: "batch-2" }
  ],
  generated_menus: [
    { id: "menu-1", target_date: day(1), title: "Bowl verde della serra", servings: 24, self_sufficiency_pct: 78, serra_ingredients: [{ inventory_item_id: "inv-1", crop_name: "Rucola", quantity_kg: 1.2 }, { inventory_item_id: "inv-2", crop_name: "Lattuga", quantity_kg: 2.0 }], external_shopping_list: [{ name: "Ceci", quantity: "2 kg" }, { name: "Limoni", quantity: "12 pz" }], status: "proposed" },
    { id: "menu-2", target_date: day(2), title: "Pasta al pesto circolare", servings: 18, self_sufficiency_pct: 64, serra_ingredients: [{ inventory_item_id: "inv-3", crop_name: "Basilico", quantity_kg: 0.7 }], external_shopping_list: [{ name: "Pasta", quantity: "3 kg" }, { name: "Pinoli", quantity: "250 g" }], status: "proposed" }
  ],
  agent_logs: [
    { id: "log-1", agent_layer: "L1_REACTIVE", agent_name: "ClimateController", action_summary: "Microclima stabile nella Vasca A", reasoning: "Temperatura e VPD sono nel corridoio operativo; nessuna correzione agli attuatori necessaria.", timestamp: ago(2) },
    { id: "log-2", agent_layer: "L2_TACTICAL", agent_name: "VisionScout", action_summary: "Lattuga romana al 91% di maturazione", reasoning: "La segmentazione delle foglie rileva chiusura del cespo e biomassa compatibili con raccolta entro 48 ore.", timestamp: ago(10) },
    { id: "log-3", agent_layer: "L3_STRATEGIC", agent_name: "ZeroWasteChef", action_summary: "Proposto menù con 78% di autoproduzione", reasoning: "La rucola è in scadenza ravvicinata: viene priorizzata per ridurre il rischio di scarto.", timestamp: ago(16) }
  ],
  agent_heartbeats: [
    { agent_layer: "L1_REACTIVE", agent_name: "Edge Climate Node", last_heartbeat: ago(1), status: "online" },
    { agent_layer: "L2_TACTICAL", agent_name: "Vision & Crop Agent", last_heartbeat: ago(10), status: "online" },
    { agent_layer: "L3_STRATEGIC", agent_name: "Orchestrator / Chef", last_heartbeat: ago(16), status: "online" }
  ],
  human_override_events: []
};
