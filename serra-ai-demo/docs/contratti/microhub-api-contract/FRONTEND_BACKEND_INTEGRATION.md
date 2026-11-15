# Micro-Hub CEA – Contratto di integrazione Frontend/Backend

**Versione:** 1.0.0-draft  
**Specifica API:** `openapi.yaml`  
**Stato:** proposta tecnica da validare sul repository React/Vite effettivo.

## 1. Scopo e limiti

Questo documento definisce il contratto che il nuovo backend dovrà esporre per alimentare la dashboard React/Vite Micro-Hub CEA.

La specifica OpenAPI descrive soprattutto le API del backend consumate dal frontend. Non è un reverse engineering del frontend: in questa sessione non sono stati forniti i sorgenti React e quindi non è possibile attestare i nomi reali delle route, dei componenti o degli attuali servizi HTTP. Claude dovrà confrontare questo contratto con il codice presente in `~/Scaricati/serra-autonoma-ai` e aggiornare la mappa senza alterare inutilmente l'interfaccia esistente.

Il backend da generare è nuovo. Non deve riutilizzare il backend precedente. Questo contratto definisce un'interfaccia futura e non dichiara che gli endpoint siano già implementati.

## 2. Principi di integrazione

1. Il backend è la fonte autorevole per dati, KPI, previsioni, eventi e decisioni.
2. Il frontend non deve contenere logiche agronomiche, predittive o di ottimizzazione duplicate.
3. Il frontend non accede direttamente al database, ai modelli ML, ai solver o ai driver hardware.
4. Ogni valore deve rendere distinguibile la provenienza: `OBSERVED`, `PREDICTED`, `SIMULATED` o `EXTERNAL`.
5. Ogni misura deve riportare unità, timestamp e qualità del dato quando applicabile.
6. Tutte le proposte di intervento devono transitare dal Safe Action Gate L0.
7. Questa API draft opera in modalità `SIMULATION`; non espone comandi verso hardware fisico.
8. Il backend deve restituire errori strutturati e non trasformare errori o dati mancanti in valori numerici fittizi.

## 3. Avvio e configurazione lato frontend

Variabile consigliata in Vite:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
VITE_API_TIMEOUT_MS=15000
VITE_ENABLE_LIVE_UPDATES=true
```

Non inserire API key o segreti nel bundle React. Le credenziali del provider LLM rimangono esclusivamente nel backend.

Il frontend deve centralizzare le richieste in un client HTTP unico, per esempio `src/services/apiClient.ts`, configurando:

- base URL;
- timeout;
- serializzazione dei parametri;
- gestione degli errori;
- eventuale token di sessione;
- identificativo di correlazione, se richiesto dal backend.

Non distribuire chiamate `fetch` ad hoc in ogni componente.

## 4. Mappa funzionale: schermata → endpoint

| Sezione UI | Endpoint principali | Uso |
|---|---|---|
| Dashboard generale | `GET /dashboard/overview` | KPI, stato hub, telemetria recente, eventi e stato sottosistemi |
| Selettore Micro-Hub | `GET /hubs` | Elenco dei Micro-Hub disponibili |
| Dettaglio Micro-Hub | `GET /hubs/{hub_id}` | Metadati e stato dell'hub |
| Zone e ripiani | `GET /hubs/{hub_id}/zones`, `GET /zones/{zone_id}` | Stato delle zone |
| Registro piante | `GET /plants`, `GET /plants/{plant_id}` | Anagrafica e stato colturale |
| Metriche delle piante | `GET /plants/{plant_id}/metrics` | Serie di crescita e metriche, filtrabili per origine |
| Telemetria corrente | `GET /telemetry/latest` | Ultime misure per zona |
| Grafici storici | `GET /telemetry/history` | Serie temporali per intervallo, metrica e zona |
| Energia | `GET /energy/overview`, `GET /energy/forecast` | Carico, FV, rete e previsioni |
| Previsioni AI | `GET /predictions/latest`, `GET /predictions/runs` | Output predittivi e stato dei modelli |
| Energy Optimizer | `POST /optimization/energy/runs`, poi `GET /optimization/energy/runs/{run_id}` | Avvio e visualizzazione di LP/MILP/QP/MPC |
| Produzione | `GET /production/overview` | Quantità disponibili e previste |
| Inventario | `GET /production/inventory` | Lotti, quantità, stato e conservabilità |
| Raccolta prevista | `GET /production/harvest-forecasts` | Previsione quantità/date di raccolta |
| Pianificazione produttiva | `POST /optimization/production/runs` | Ottimizzazione allocazione e fabbisogno |
| Menu | `GET /menus`, `POST /menus` | Consultazione e richiesta di bozza menu |
| Orchestratore L1 | `POST /orchestrator/requests`, `GET /orchestrator/runs/{run_id}` | Richiesta cognitiva e stato del processo |
| Eventi e alert | `GET /events`, `POST /events/{event_id}/acknowledgement` | Elenco e presa visione degli eventi |
| Safe Action Gate | `GET /safety/proposals`, `POST /safety/proposals/{proposal_id}/validate` | Stato proposte e verdetti L0 |
| Approvazione umana | `POST /safety/proposals/{proposal_id}/approval` | Registra una decisione umana quando richiesta; non supera un blocco L0 |
| Digital Twin | `GET /simulation/status`, `POST /simulation/start`, `/stop`, `/step` | Controllo del tempo simulato |
| Scenari Digital Twin | `GET /simulation/scenarios`, `POST /simulation/scenarios` | Consultazione e iniezione scenari |
| Modelli e dataset | `GET /models`, `GET /datasets` | Stato di registrazione, validazione e ingestione |
| Stato sensori | `GET /devices/sensors` | Diagnostica in sola lettura |
| Stato attuatori | `GET /devices/actuators` | Stato virtuale in sola lettura |
| Aggiornamenti live | `GET /stream/events` | Stream SSE per aggiornare la UI senza polling continuo |

## 5. Convenzioni dei dati

### 5.1 Provenienza

Ogni record che può essere reale, predetto o simulato deve includere `data_origin`:

- `OBSERVED`: osservazione o misura effettiva, con provenienza tracciabile.
- `PREDICTED`: risultato di un modello, con `model_id`, `model_version` e orizzonte.
- `SIMULATED`: generato dal Digital Twin o da uno scenario dimostrativo.
- `EXTERNAL`: acquisito da un servizio esterno, ad esempio meteo o mercato.

La UI deve mostrare un badge/etichetta di provenienza e non mescolare implicitamente le serie. Un grafico che confronta più origini deve usare legenda e stili distinti.

### 5.2 Qualità

Quando previsto, `quality` può essere:

- `VALID`: valore utilizzabile.
- `SUSPECT`: valore presente ma da trattare con cautela.
- `INVALID`: valore non utilizzabile per decisioni.
- `STALE`: valore troppo vecchio rispetto alla policy del sensore.
- `UNKNOWN`: qualità non determinata.

La UI deve evidenziare `INVALID`, `STALE` e `SUSPECT`; non deve convertire `null` in zero.

### 5.3 Timestamp e unità

- Trasportare timestamp ISO 8601/RFC 3339 con timezone.
- Memorizzare e confrontare i timestamp preferibilmente in UTC.
- Visualizzare nella timezone configurata per il Micro-Hub, inizialmente `Europe/Rome`.
- Non indovinare unità: ogni misura deve avere unità esplicita o un nome di campo con unità documentata.
- Non ricalcolare DLI sul frontend se il backend fornisce già il valore autorevole.

### 5.4 Paginazione

Le liste usano `items` e `page`, con `limit`, `next_cursor` e `has_more`. Il frontend deve supportare caricamento progressivo e non assumere che l'intera cronologia arrivi in una sola risposta.

## 6. Flussi asincroni

Le ottimizzazioni, le richieste dell'orchestratore, le predizioni e la generazione dei menu possono richiedere tempo.

Sequenza raccomandata:

1. Il frontend invia la richiesta `POST`.
2. Il backend risponde `202 Accepted` con `run_id` e `status_url`.
3. Il frontend mostra lo stato `queued` o `running`.
4. Il frontend riceve aggiornamenti SSE oppure interroga il dettaglio del run.
5. Al completamento recupera il risultato completo.
6. In caso di `failed` o `infeasible`, mostra una motivazione e non simula un risultato valido.

Stati consigliati per i run:

- `queued`;
- `running`;
- `completed`;
- `infeasible` (per problemi di ottimizzazione);
- `failed`;
- `needs_human_review` (per flussi che richiedono supervisione).

## 7. Aggiornamenti live SSE

Endpoint: `GET /api/v1/stream/events?hub_id=...`

Eventi raccomandati:

```text
telemetry.updated
 event: telemetry.updated
 data: {"hub_id":"HUB-DEMO-001","zone_id":"Z1","data_origin":"SIMULATED"}

event.created
 data: {"event_id":"EVT-001","severity":"warning"}

optimization.completed
 data: {"run_id":"OPT-001","status":"completed"}

orchestrator.updated
 data: {"run_id":"ORCH-001","status":"running"}

safety.proposal.updated
 data: {"proposal_id":"PROP-001","gate_status":"BLOCKED"}

simulation.updated
 data: {"status":"running","simulated_time":"2026-11-14T10:00:00Z"}
```

Il testo sopra illustra il formato, non dati reali. Il backend deve inviare eventi SSE validi con `event:` e `data:`; il client deve gestire riconnessione, backoff e duplicati. Non aprire una nuova connessione SSE per ogni widget: condividere un servizio/event bus client-side.

## 8. Gestione errori

Le risposte di errore devono seguire un formato coerente `application/problem+json` con almeno:

```json
{
  "title": "Validation error",
  "status": 422,
  "detail": "Il campo horizon_hours deve essere compreso tra 1 e 48.",
  "code": "INVALID_PARAMETER",
  "request_id": "req-example",
  "errors": [
    {"field": "horizon_hours", "message": "Valore fuori intervallo"}
  ]
}
```

Il frontend deve distinguere almeno:

- `400/422`: richiesta o parametri non validi;
- `401/403`: sessione o permessi;
- `404`: risorsa non trovata;
- `409`: conflitto di stato o approvazione non compatibile;
- `429`: limite richieste;
- `500`: errore interno;
- `503`: servizio non disponibile.

Mostrare messaggi comprensibili all'utente e conservare `request_id` per diagnosi. Non mostrare stack trace o segreti.

## 9. Regole di sicurezza per il frontend

- Non esporre API key LLM nel browser.
- Non esporre endpoint che impartiscono comandi diretti a pompe, LED, ventilazione o HVAC.
- Non consentire al frontend di bypassare il Gate L0.
- Una approvazione umana non può trasformare un verdetto L0 `BLOCKED` in `ALLOWED`.
- Mostrare chiaramente quando la piattaforma è in modalità `SIMULATION`.
- Non permettere di selezionare `HARDWARE` finché il relativo adapter, la progettazione di sicurezza e la validazione non siano stati completati.
- Proteggere le route di amministrazione e supervisione con ruoli e autorizzazioni nel backend.

## 10. Organizzazione consigliata del client React

Adattare i nomi alla struttura reale già esistente, senza duplicare componenti:

```text
src/
  services/
    apiClient.ts
    endpoints.ts
    eventStream.ts
  hooks/
    useDashboardOverview.ts
    useTelemetry.ts
    usePlants.ts
    usePredictions.ts
    useEnergyOptimization.ts
    useEvents.ts
    useSimulation.ts
  types/
    api.generated.ts
  features/
    dashboard/
    cultivation/
    predictions/
    energy/
    orchestrator/
    safety/
    production/
    digital-twin/
```

Generare i tipi TypeScript da `openapi.yaml` (ad esempio con `openapi-typescript`) invece di riscrivere manualmente i tipi in più punti. La generazione dei client non deve introdurre URL o schemi diversi da quelli definiti nel contratto.

## 11. Criteri di accettazione dell'integrazione

L'integrazione è accettata quando:

1. Tutte le schermate principali leggono dati dal backend, non da mock statici.
2. Ogni valore visualizzato conserva provenienza, unità e timestamp quando applicabili.
3. Errori e stati vuoti sono gestiti esplicitamente.
4. Grafici storici supportano intervalli e filtri.
5. I run asincroni mostrano stati e risultati reali del backend.
6. Gli aggiornamenti live non generano connessioni duplicate o memory leak.
7. Le proposte sono visibili con il relativo verdetto L0.
8. Nessuna interazione del frontend può comandare hardware fisico o aggirare L0.
9. Le azioni del Digital Twin modificano lo stato simulato persistito nel backend.
10. Test di integrazione verificano il percorso completo: UI → API → servizio → database → risposta/evento → UI.

## 12. Istruzioni per Claude Code

1. Analizza prima il repository React/Vite esistente e crea una mappa delle pagine, componenti e chiamate dati attuali.
2. Confronta la mappa con `openapi.yaml`.
3. Segnala endpoint non necessari, schermate senza endpoint e dati UI non previsti dal contratto.
4. Mantieni questa specifica come contratto comune: genera il backend per rispettarla e adatta il frontend con modifiche minime.
5. Se è necessaria una modifica al contratto, aggiorna prima `openapi.yaml`, documenta il motivo e poi aggiorna backend, tipi TypeScript e frontend.
6. Genera documentazione Swagger/ReDoc dal file OpenAPI.
7. Aggiungi test che verifichino schema delle risposte e comportamento degli endpoint.
8. Non dichiarare l'integrazione completata finché i flussi principali non sono stati provati end-to-end.

## 13. Nota sul carattere draft

Questo contratto definisce una base concreta e coerente per il backend da generare. Per garantire un'integrazione realmente perfetta deve essere verificato sul codice sorgente effettivo del frontend: route, componenti, filtri, interazioni e dati attualmente attesi. I nomi degli endpoint e gli schemi qui definiti diventano il contratto target da implementare, salvo modifiche motivate e versionate.
