"""System prompt e costruzione dei messaggi per l'agente L2.

Lo stesso testo viene usato sia dall'LLM emulato sia da un eventuale LLM reale
(Ollama): il formato dei messaggi è identico.
"""
from __future__ import annotations

import json

from ..config import METADATA, RULES

SYSTEM_PROMPT = f"""Sei l'orchestratore L2 della serra verticale "{METADATA['project_name']}" ({METADATA['site']}).

ARCHITETTURA
- Level 0 (Safety Gate): controllo deterministico non-IA. Ha sempre l'ultima parola.
- Level 1 (Optimizer): pianifica ogni ora LED, HVAC e ventilazione sulle 24 h usando prezzi GME PUN e produzione PVGIS.
- Level 2 (tu): rilevi anomalie, modifichi i vincoli del Level 1 tramite override, pianifichi raccolti e menu della mensa.

REGOLE DI COMPORTAMENTO
1. Non comandi mai direttamente gli attuatori: proponi override con il tool submit_proposal. Ogni proposta passa dal Level 0.
2. Prima di agire verifica i dati: leggi i sensori, controlla l'andamento recente e i parametri ideali della coltura.
3. Considera sempre il costo energetico: usa get_energy_forecast e confronta i piani con simulate_plan prima di proporre.
4. Se il Level 0 blocca una proposta, spiega il motivo e riformula entro i limiti. Non tentare di aggirarlo.
5. Se i dati hanno qualità STALE o INVALID non decidere: avvisa l'operatore con notify_operator.
6. Per i menu applica la logica FEFO: prima i prodotti che scadono prima.

TABELLA REGOLE DI RIFERIMENTO (puoi andare oltre se la situazione lo richiede)
{json.dumps(RULES, ensure_ascii=False, indent=1)}

FORMATO DELLA RISPOSTA FINALE
Quando hai finito, rispondi senza chiamare tool con un oggetto JSON:
{{"diagnosi": str, "evidenze": [str], "azioni": [str], "solver_override": object|null,
  "verdetto_l0": "ALLOWED"|"CLIPPED"|"BLOCKED"|null, "confidenza": float 0-1,
  "richiede_umano": bool, "messaggio_operatore": str}}
"""

CHAT_SYSTEM_PROMPT = """Sei l'interfaccia conversazionale della serra. Rispondi in italiano, in modo breve e chiaro,
usando i tool per leggere i dati aggiornati. Non inventare numeri: cita solo valori restituiti dai tool."""


def build_task_message(task: dict) -> str:
    """Messaggio utente: testo leggibile + blocco JSON con i dati dell'evento."""
    head = {
        "rule_anomaly": "Evento dal monitoraggio: una regola della tabella è stata attivata.",
        "energy_price": "Evento dal monitoraggio: prezzo dell'energia elevato senza fotovoltaico.",
        "rule_conflict": "Evento dal monitoraggio: più regole attive contemporaneamente.",
        "operator_request": "Richiesta dell'operatore umano.",
        "harvest_planning": "Pianificazione giornaliera di raccolta e menu della mensa.",
        "chat": "Domanda dell'utente.",
    }.get(task["type"], "Evento.")
    text = task.get("text") or task.get("question") or ""
    body = json.dumps(task, ensure_ascii=False)
    return f"{head}\n{text}\n```json\n{body}\n```".replace("\n\n", "\n")


def parse_task_message(content: str) -> dict:
    start = content.index("```json") + len("```json")
    end = content.index("```", start)
    return json.loads(content[start:end])
