# Serra AI · backend simulato

Backend Python che simula l'intero sistema di controllo della serra verticale, a partire da `../dataset_serra.json`:

| Livello | File | Cosa fa nella simulazione |
|---|---|---|
| Digital twin | `serra/sim.py` | Clima, soluzione nutritiva, crescita dei ripiani ed energia, con un passo ogni 15 minuti simulati |
| **L0** Safety Gate | `serra/safety_l0.py` | Controllo deterministico dei limiti hardware e biologici: `ALLOWED`, `CLIPPED` o `BLOCKED` |
| **L1** Optimizer | `serra/optimizer_l1.py` | Sceglie la finestra luminosa continua più economica (PUN × quota non coperta dal fotovoltaico) |
| **L2** Orchestratore | `serra/agent/` | Ciclo agentico con tool calling, nel formato messaggi di Ollama |
| Tool dell'agente | `serra/tools.py` | 11 tool: funzioni Python vere che leggono e modificano il digital twin |
| Scenari | `serra/scenarios.py` | 7 perturbazioni dimostrative |

> **Nota di trasparenza.** Il "cervello" dell'L2 è un **LLM emulato** (`agent/llm_mock.py`): sceglie i tool con regole scritte a mano e scrive il ragionamento usando i numeri veri restituiti dai tool. Il formato dei messaggi, i tool e il ciclo sono quelli di un LLM reale. Impostando `LLM_MODE=ollama` si usa un modello locale vero senza toccare altro codice.

Le stime che non vengono dal dataset (dispersione termica, traspirazione, ecc.) sono raccolte e dichiarate in `serra/config.py` → `ESTIMATES`.

## Avvio

```bash
cd serra_backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api:app --port 8000
```

- Swagger con tutti gli endpoint: http://127.0.0.1:8000/docs
- Frontend: `cd ../serra-autonoma-ai && npm install && npm run dev` → http://localhost:5173. Il proxy Vite inoltra `/api` al backend.

## Esportare le tracce per i materiali

```bash
.venv/bin/python run_scenarios.py
```

Esegue i 7 scenari senza interfaccia e scrive in `output/<scenario>/`:
- `RUN-xxx.json`: conversazione grezza (system, user, assistant con `tool_calls`, tool);
- `RUN-xxx.md`: la stessa traccia in forma leggibile;
- `output/riepilogo.md`: tabella riassuntiva.

## Scenari

| id | Cosa succede | Reazione attesa |
|---|---|---|
| `umidita` | Irrigazione eccessiva nella zona 1 | RULE_01: l'agente verifica, simula, propone più ventilazione; l'umidità rientra |
| `caldo` | HVAC al 35% nella zona 2 | RULE_02: setpoint −2 °C e LED limitati |
| `clorosi` | Dosatore nutrienti inceppato | RULE_03: EC +0.2 e pH 5.8, entro i limiti di salinità di L0 |
| `prezzo` | PUN ×2.6 tra le 0 e le 5 | RULE_04: L1 sposta la finestra luminosa e risparmia senza perdere DLI |
| `conflitto` | Umidità alta e energia cara insieme | L'agente media tra RULE_01 e RULE_04 con una soluzione più economica |
| `pericolosa` | "Massimizza il basilico per giovedì" | L'agente propone 30 kW e 22 h di luce, **L0 blocca**, l'agente riformula entro i limiti |
| `raccolta` | Pianificazione giornaliera | Raccolta dei ripiani pronti e menu della mensa con logica FEFO |

Ogni giorno alle 07:00 simulate l'agente pianifica in automatico raccolta e menu.

## LLM reale (facoltativo)

```bash
ollama pull qwen2.5:3b
LLM_MODE=ollama .venv/bin/uvicorn api:app --port 8000
```

Un modello da 3B sta in un Mac con 8 GB di RAM. È più lento e meno affidabile nell'uso dei tool: per registrare il video conviene la modalità emulata, che è riproducibile.

## Endpoint principali

| Metodo | Percorso | Uso |
|---|---|---|
| GET | `/api/snapshot` | Stato completo per il frontend |
| POST | `/api/sim/play` · `/pause` · `/step` · `/reset` · `/speed` | Controllo del tempo simulato |
| POST | `/api/scenarios/{id}` | Inietta uno scenario |
| GET | `/api/agent/runs/{id}` | Traccia completa: `messages` (grezza) e `steps` (leggibile) |
| GET | `/api/agent/runs/{id}/report.md` | Traccia in Markdown |
| GET | `/api/agent/tools` · `/api/agent/system-prompt` | Definizioni dei tool e system prompt |
| POST | `/api/chat` | Domanda in linguaggio naturale |
| POST | `/api/harvest` · `/api/inventory/{id}/consume` · `/api/menus/{id}/approve` | Azioni umane |
