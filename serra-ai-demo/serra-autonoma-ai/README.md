# Serra Autonoma AI — React + Vite

> **Aggiornamento:** il frontend ora legge i dati dal backend simulato in `../serra_backend` (FastAPI, porta 8000) tramite il proxy Vite su `/api`. Avviare prima il backend (vedi `../serra_backend/README.md`), poi `npm run dev`. Architettura allineata al dataset: 2 zone (`ZONE_1_LEAFY`, `ZONE_2_WARM`), 4 ripiani e livelli L0 Safety Gate / L1 Optimizer / L2 Orchestratore LLM. Nuova pagina **Ragionamento AI** con le tracce dell'agente in forma leggibile o come JSON grezzo. `mockData.js` non è più usato.

Frontend dimostrativo per una serra autonoma governata da H-MAS. Include Dashboard, Dispensa FEFO, Menù Zero-Waste e Chat, con data provider disaccoppiato e simulazione degli agenti.

## Avvio

```bash
npm install
npm run dev
```

Build produzione:

```bash
npm run build
npm run preview
```

## Funzionalità

- `Simula Ciclo Agenti (DB Sync)`: produce nuove letture L1, aggiornamenti agronomici L2, log L3 e heartbeat.
- `Simula Offline L1`: simula la perdita del nodo Edge e mostra lo stato offline.
- Dashboard con KPI, grafico microclimatico, schede colture e feed XAI filtrabile.
- Dispensa ordinata FEFO, registrazione raccolto e scarico consumo.
- Menù generati, percentuale di autoproduzione, approvazione e prenotazione simulata degli ingredienti.
- Chat contestuale interrogabile sui dati correnti.
- Event bus Observer e aggiornamenti ottimistici.
- Manifest PWA base.

## Struttura

```text
src/
  App.jsx
  mockData.js
  styles.css
  main.jsx
  components/
    AgentStatus.jsx
    LogFeed.jsx
  services/
    dataProvider.js
```

## Contratto del Data Provider

I componenti React usano esclusivamente `dataProvider`:

- `getSnapshot()`
- `subscribeToDatabaseChanges(callback)`
- `simulateAgentCycle()`
- `setOfflineL1(value)`
- `registerHarvest(batchId, quantityKg)`
- `consumeInventory(itemId, quantityKg)`
- `approveMenu(menuId)`
- `sendHumanOverride(event)`

### Collegamento REST

In `src/services/dataProvider.js`, sostituire la lettura mock in `getSnapshot()` con:

```js
const response = await fetch("/api/snapshot");
if (!response.ok) throw new Error("Snapshot API non disponibile");
return await response.json();
```

Le azioni umane devono inviare un evento, non aggiornare direttamente le tabelle agentiche:

```js
await fetch("/api/human-overrides", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(event)
});
```

### WebSocket

Nel provider inizializzare una connessione una sola volta e normalizzare gli eventi ricevuti:

```js
const socket = new WebSocket(import.meta.env.VITE_WS_URL);
socket.onmessage = ({ data }) => {
  const event = JSON.parse(data);
  // validate + normalize event, poi update dello snapshot locale
};
```

### SSE

```js
const source = new EventSource("/api/events");
source.onmessage = ({ data }) => {
  const event = JSON.parse(data);
  // applicare l'evento normalizzato allo store
};
```

### Supabase Realtime

Sottoscrivere `postgres_changes` sulle tabelle interessate (`telemetry_readings`, `crop_batches`, `inventory_items`, `generated_menus`, `agent_logs`, `agent_heartbeats`) e convertire ogni payload nel contratto eventi del provider.

## Contratto evento Human-in-the-Loop

Esempio:

```json
{
  "id": "uuid",
  "event_type": "HARVEST_RECORDED",
  "entity_type": "crop_batch",
  "entity_id": "batch-1",
  "payload": {
    "quantity_kg": 4.2,
    "inventory_item_id": "uuid",
    "source": "human_ui"
  },
  "requested_by": "utente-kiosk",
  "created_at": "2026-11-14T12:00:00Z",
  "processing_status": "pending"
}
```

Il backend dovrebbe accodare l'evento, applicare controlli di autorizzazione e idempotenza e notificare L3. L'agente ricalcola lo stato e pubblica una nuova versione autorevole. Per evitare race condition, usare `version`/`updated_at`, transazioni e vincoli DB.

## Note per produzione

1. Le soglie heartbeat (15 minuti nel prototipo) devono essere configurabili per tipo di agente.
2. L'approvazione menù in produzione deve essere atomica: validare disponibilità, creare allocazioni e cambiare status nella stessa transazione.
3. La UI usa quantità sottratte come prenotazione simulata. In produzione separare `on_hand`, `reserved` e `consumed` per non confondere prenotazione e consumo fisico.
4. Validare input, RBAC, audit trail e idempotency key lato server.
5. Il service worker offline e le icone PWA vanno aggiunti prima del deployment kiosk.
6. Le metriche di risparmio idrico/energetico sono illustrative nel mock e devono essere collegate a baseline misurate.
