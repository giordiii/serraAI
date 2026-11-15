# Riepilogo scenari

| Scenario | Esecuzioni agente | Verdetti L0 | Esito |
|---|---|---|---|
| umidita | RUN-002 Umidità alta · rischio tipburn · ZONE_1_LEAFY | ALLOWED | Rischio muffa o necrosi marginale (Tipburn) per scarsa traspirazione: correzione applicata per 6 h, costo stimato +1.41 €/giorno. |
| caldo | RUN-002 Stress termico · ZONE_2_WARM | ALLOWED | Stress termico o appassimento fogliare: correzione applicata per 6 h, costo stimato -0.85 €/giorno. |
| clorosi | RUN-002 Carenza nutrienti · ZONE_1_LEAFY | ALLOWED | Carenza clorofilliana / nutrienti: correzione applicata per 12 h, costo stimato +0.00 €/giorno. |
| prezzo | RUN-002 Prezzo energia elevato | ALLOWED | Illuminazione spostata fuori dalle ore care: risparmio 5.25 €/giorno. |
| conflitto | RUN-002 Conflitto tra regole · umidità vs energia | ALLOWED | Ho combinato le due regole invece di applicarle separatamente: stesso effetto sull'umidità, costo minore. |
| pericolosa | RUN-002 Richiesta operatore · accelerare il basilico | BLOCKED, ALLOWED | Ho accelerato il basilico entro i limiti di sicurezza; la richiesta originale avrebbe violato il buio obbligatorio. |
| raccolta | RUN-001 Pianificazione raccolta e menu | — | Proposto "Insalata Fresca Flegrea (Lattuga tenera e Rucola con scaglie di Provolone del Monaco)" per 271 porzioni, valore 39.44 €. Serve l'approvazione della mensa. |
