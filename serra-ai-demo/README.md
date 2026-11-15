# Serra AI · demo simulata

Demo della serra verticale automatizzata del Campus di Monte Sant'Angelo (Big Hack 2026). Il sistema è orchestrato da un LLM centrale con tool esterni e ha un'architettura di controllo a tre livelli:

- **L0 · Safety Gate**: controllo deterministico, senza IA. Applica i limiti fisici e biologici inviolabili e ha sempre l'ultima parola.
- **L1 · Optimizer**: pianifica sulle 24 ore LED, climatizzazione e ventilazione, usando i prezzi dell'energia (GME PUN) e la produzione fotovoltaica (PVGIS).
- **L2 · Orchestratore LLM**: rileva anomalie, usa i tool, propone override a L1 passando sempre da L0, pianifica raccolti e menu della mensa.

> **Modalità SIMULATION.** Tutto gira su un *digital twin* alimentato da `dataset_serra.json`: nessun hardware reale. L'agente L2 è un **LLM emulato**: produce messaggi e chiamate ai tool nello stesso formato di un LLM locale (Ollama), mentre i tool sono funzioni reali del simulatore. Si può collegare un LLM open source vero con `LLM_MODE=ollama` (vedi `serra_backend/README.md`).

## Avvio rapido

Requisiti: **Python 3.10+** e **Node.js 18+**.

**1. Backend** (terminale 1):

```bash
cd serra_backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api:app --port 8000
```

Su Windows usare `.venv\Scripts\pip` e `.venv\Scripts\uvicorn`.

**2. Frontend** (terminale 2):

```bash
cd serra-autonoma-ai
npm install
npm run dev
```

**3. Aprire** http://localhost:5173

- Premere ▶ in alto per far scorrere il tempo simulato.
- Dal menu **Scenari** iniettare un evento: picco di umidità, guasto della climatizzazione, prezzo dell'energia alto, richiesta pericolosa dell'operatore, ecc.
- Nella pagina **Ragionamento AI** si vede, passo per passo, cosa ha letto l'agente, quali tool ha usato, cosa ha proposto e il verdetto del Safety Gate. Si può passare al JSON grezzo o scaricare la traccia in Markdown.

Documentazione interattiva delle API: http://127.0.0.1:8000/docs

## Senza avviare nulla

Le tracce di ragionamento dei 7 scenari sono già esportate in [`serra_backend/output/`](serra_backend/output/riepilogo.md): ogni esecuzione è disponibile in JSON e in Markdown leggibile. Per rigenerarle:

```bash
cd serra_backend && .venv/bin/python run_scenarios.py
```

## Struttura

```text
dataset_serra.json      dati della serra: configurazione, colture, limiti L0, regole, costi, clima, mensa
serra_backend/          backend Python (FastAPI): digital twin, L0, L1, agente L2, scenari
serra-autonoma-ai/      frontend React + Vite (dashboard, ragionamento AI, dispensa, menu, chat)
docs/contratti/         contratto dati del database e bozza OpenAPI del backend
```

I dettagli su backend, scenari ed endpoint sono in [`serra_backend/README.md`](serra_backend/README.md).

## Limiti dichiarati

- La fisica della serra è volutamente semplificata. Le grandezze reagiscono in modo plausibile agli attuatori, ma non si tratta di un modello agronomico validato. I parametri stimati sono elencati in `serra_backend/serra/config.py` (`ESTIMATES`).
- L'optimizer L1 è un'euristica, cioè la ricerca della finestra luminosa più economica; nella versione futura sarà un programma lineare / MPC.
- Il ragionamento dell'agente L2 è emulato e riproducibile. L'architettura (tool, formato dei messaggi, Safety Gate) è la stessa che userebbe un LLM reale.
