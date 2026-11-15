# serraAI
Progetto Challenge numero 2, MODAL UNINA.


Gruppo Crystal Future.


Vale G.
Giuseppe M.
Giuseppe Z.
Sara R.
Francesca M.



Immaginiamo una piccola serra verticale all'interno del Campus di Monte Sant'Angelo dell'Università Federico II di Napoli: il raccolto non va al mercato, bensì finisce direttamente nella mensa universitaria sotto forma di piatti tipici della terra campana rendendoli più accessibili ed in maniera più indipendente.

Le vertical farm hanno un difetto noto: consumano molta energia, soprattutto per la luce artificiale. Il nostro progetto affida la gestione della serra a un'intelligenza artificiale che decide quando accendere le luci, quanto ventilare e come regolare temperatura e nutrienti. Tiene conto del prezzo orario dell'elettricità, del fotovoltaico e delle esigenze di ogni coltura. In più collega la serra alla cucina: sa cosa sta per maturare, cosa c'è in dispensa e propone i menu di conseguenza.

Il principio guida è la sicurezza. L'intelligenza artificiale suggerisce, ma non comanda mai da sola: ogni decisione passa da un controllo automatico che non può essere aggirato.

I tre livelli di controllo
Il "cervello" della serra è diviso in tre livelli.

L2 · Orchestratore (il direttore). È un modello linguistico open-source eseguito in locale. Sorveglia i sensori, riconosce i problemi (umidità eccessiva, piante che appassiscono, foglie che ingialliscono, energia troppo cara), consulta i dati attraverso degli "strumenti" e propone correzioni. Pianifica anche raccolti e menu e risponde in chat alle domande degli operatori.

L1 · Ottimizzatore (il pianificatore). È un calcolo matematico che organizza le 24 ore successive: sposta l'accensione dei LED nelle fasce in cui l'energia costa meno o il fotovoltaico produce, garantendo comunque a ogni pianta la quantità di luce giornaliera di cui ha bisogno.

L0 · Safety Gate (il responsabile della sicurezza). È un insieme di regole fisse, senza alcuna IA, che conosce i limiti fisici degli impianti e quelli biologici delle piante: almeno 6 ore di buio, CO₂ sotto i 1500 ppm, acidità e salinità entro soglie precise. Ogni comando viene accettato, ridotto entro i limiti oppure bloccato. Il Safety Gate ha sempre l'ultima parola.

Il database: la memoria della serra
Il database descrive tutto ciò che il sistema deve sapere, in un unico archivio strutturato in otto sezioni:
la struttura fisica della serra: superfici, ripiani e zone climatiche (per colture che possono differire;
il catalogo delle colture, con le condizioni ideali di ciascuna (temperatura, umidità, luce, acidità e concentrazione dei nutrienti), i giorni necessari alla crescita, la resa attesa e la durata in frigorifero dopo la raccolta;
lo stato dei ripiani: cosa è stato piantato, da quanti giorni e quanto manca alla raccolta;
i sensori e gli attuatori: letture di temperatura, umidità, CO₂, luce e soluzione nutritiva, indicatori forniti dalle telecamere, insieme ai limiti di potenza di LED, climatizzazione e ventilazione;
le regole di intervento che guidano l'IA, del tipo "se l'umidità supera il 75%, aumenta la ventilazione";
dati pubblici reali su Napoli: prezzo orario dell'energia (GME PUN), produzione solare stimata (PVGIS), tariffe dell'acqua, costi agronomici e prezzi di mercato degli ortaggi in Campania;
la domanda della mensa e un ricettario campano che indica quanti grammi di ciascun ortaggio servono per porzione.

Il backend: dove si prendono le decisioni; riceve i dati dai sensori, esegue i tre livelli di controllo e invia i comandi agli impianti. L'agente L2 lavora in un ciclo di ragionamento: legge la situazione, sceglie uno strumento (per esempio "leggi i sensori della zona 1", "mostrami le previsioni sui prezzi", "simula questo piano prima di applicarlo"), ne valuta il risultato e decide il passo successivo. Quando è pronto invia una proposta, che arriva all'ottimizzatore solo dopo il via libera del Safety Gate. Ogni passaggio viene registrato, così che il ragionamento sia sempre verificabile da una persona.

Il frontend: la finestra sulla serra; è l'applicazione web usata da tecnici e personale della mensa. Comprende:
una dashboard con lo stato in tempo reale di zone e ripiani, i consumi e i costi energetici;
la pagina Ragionamento AI, che mostra passo per passo cosa ha letto l'agente, quali strumenti ha usato, cosa ha proposto e il verdetto del Safety Gate;
la dispensa, gestita secondo il criterio FEFO (First Expiring First Out, prima esce ciò che scade prima);
i menu proposti dall'IA, che il personale approva con un clic;
una chat per fare domande in linguaggio naturale, collegandosi al modello linguistico sottostante.
L'interfaccia non chiede di fidarsi dell'IA: mostra perché ha deciso.

La nostra simulazione
Per la durata dell'hackathon non disponiamo di una serra fisica, quindi abbiamo costruito un gemello digitale: una serra virtuale alimentata dal nostro database (fatto di dati reali, ma ovviamente non specifici della nostra applicazione), che avanza a passi di 15 minuti simulati. Temperatura, umidità, nutrienti, crescita delle piante ed energia reagiscono in modo plausibile ai comandi, anche se la fisica è volutamente semplificata.

Il backend simulato implementa davvero i tre livelli. L'ottimizzatore cerca la finestra di illuminazione più economica, il Safety Gate applica i limiti reali e l'agente usa undici strumenti che leggono e modificano la serra virtuale. Il ragionamento dell'agente è emulato: segue regole scritte da noi ma usa i numeri veri restituiti dalla simulazione e produce messaggi nello stesso formato di un modello linguistico locale, che si può collegare senza cambiare il resto del sistema.

Dall'interfaccia si possono provocare sette situazioni limite: un picco di umidità, un guasto della climatizzazione, un ingiallimento delle foglie, un rincaro dell'energia, un conflitto tra umidità e costi, la pianificazione quotidiana di raccolto e menu e una richiesta pericolosa dell'operatore ("massimizza il basilico per giovedì"). In quest'ultimo caso si vede l'agente proporre luce quasi continua, il Safety Gate bloccarla e l'agente riformulare un piano entro i limiti.
