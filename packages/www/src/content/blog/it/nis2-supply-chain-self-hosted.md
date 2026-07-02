---
title: "Article 21(2)(d) è una questione di fornitori. Il self-hosting è la risposta che smetti di dover giustificare."
description: "Perché il registro ICT di terze parti si riduce quando il piano dati non lascia mai la tua infrastruttura. Una lettura pratica di NIS2 Article 21(2)(d) per CISO e responsabili degli acquisti che rinegoziano i DPA nel 2026."
author: Rediacc
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - supply-chain
  - self-hosted
  - sovranita
  - conformita
featured: false
language: it
sourceHash: "ffdb86da48dacc58"
sourceCommit: "8062f196566d6ba5f90b084e5484cf722b4bdf16"
translatedFrom: en
---

> **Sintesi.** NIS2 Article 21(2)(d) eleva il rischio della catena di approvvigionamento a questione di competenza del consiglio di amministrazione, non a nota a pie di pagina degli acquisti. La direttiva non impone il self-hosting. Chiede, tuttavia, cosa si trova nel percorso dei dati e cosa accade quando uno di quei fornitori attraversa una brutta giornata. L'infrastruttura self-hosted elimina tre dei quattro livelli presenti nella maggior parte dei percorsi dati SaaS. Non li elimina tutti e quattro: sostenere il contrario è la mossa di marketing che mette un CISO nei guai davanti a un auditor.
>
> - Il testo della direttiva e le linee guida ENISA, in linguaggio diretto.
> - Il percorso dati SaaS a quattro livelli che la maggior parte dei team dimentica di tracciare.
> - Cosa rimuove dal registro fornitori il modello a due strumenti di Rediacc, e cosa vi lascia.
> - Una checklist di sei domande per qualsiasi fornitore che si dichiara "NIS2-ready."

Nel luglio 2020, Blackbaud pagò un riscatto e lo comunicò al mondo in ritardo. Notificò l'accaduto a oltre 13.000 organizzazioni clienti dopo i fatti, affrontò azioni collettive in sette giurisdizioni e si ritrovò a pagare 49,5 milioni di dollari in accordi con i procuratori generali statali e 3 milioni di dollari di multa SEC per comunicazioni fuorvianti. Ciascuna di quelle 13.000 organizzazioni aveva un Data Processing Agreement con Blackbaud. La maggior parte aveva esaminato il rapporto SOC 2 di Blackbaud. Molte avevano Blackbaud nel registro dei rischi fornitori, con una classificazione di livello, una data di rinnovo e un referente nominato.

Nulla di tutto ciò ha fermato il contagio. I dati erano dal lato di Blackbaud del confine. Quando il loro ambiente di backup fu violato, ogni organizzazione cliente fu violata contemporaneamente.

NIS2 Article 21(2)(d) pone una domanda più difficile di "hai verificato il tuo fornitore." Chiede cosa si trova nel percorso dei dati e cosa accade quando quel fornitore attraversa una brutta giornata. La risposta, per la maggior parte dei team, è: "siamo loro, e non ce ne eravamo resi conto."

Questo articolo è rivolto a CISO e responsabili degli acquisti che rinegoziano i DPA nel 2026. Si tratta della lettura del percorso dati di Article 21(2)(d), non della lettura delle certificazioni. È anche onesto su ciò che l'infrastruttura self-hosted non risolve, perché la sezione sulle lacune è quella su cui un auditor si soffermerà e che una brochure di marketing salterà.

## Cosa obbliga effettivamente Article 21(2)(d)

Il testo della direttiva recita, leggermente abbreviato per chiarezza:

> "Gli Stati membri provvedono affinché i soggetti essenziali e importanti adottino misure tecniche, operative e organizzative adeguate e proporzionate per gestire i rischi posti alla sicurezza dei sistemi informatici e di rete [...] e comprendono almeno gli elementi seguenti: [...] d) sicurezza della catena di approvvigionamento, compresi aspetti relativi alla sicurezza riguardanti i rapporti tra ciascun soggetto e i suoi diretti fornitori o fornitori di servizi"

Due aspetti in quel testo sono rilevanti per un acquirente.

Primo, l'obbligo riguarda te, non il fornitore. Le certificazioni del fornitore, il SOC 2 del fornitore, l'ISO 27001 del fornitore sono elementi in ingresso alla tua valutazione del rischio. Non ne sono un sostituto. Se il tuo fornitore ha una postura di conformità perfetta e subisce comunque una violazione, la domanda del regolatore riguarderà la tua gestione del rischio dei fornitori, non la loro.

Secondo, l'obbligo va oltre il contratto. Le linee guida attuative ENISA 2024, Annex IV del Regolamento di esecuzione (UE) 2024/2690 della Commissione, delineano la pratica attesa: mantenere un registro dei fornitori ICT, classificarli per criticità, valutare ciascuno per il rischio alle proprie operazioni e ai dati che trattano, e rinnovare la valutazione con cadenza definita. Annex IV menziona esplicitamente "i fornitori dei fornitori" come in ambito, ed è qui che la maggior parte dei team scopre che il proprio registro fornitori non è davvero un registro, ma un elenco di contratti con un'etichetta appiccicata sopra.

Se stai guardando la situazione dal lato degli acquisti, la traduzione pratica è: ogni fornitore con accesso logico ai tuoi dati di produzione deve essere censito, classificato, monitorato e sostituibile. "Sostituibile" è la parte che rompe la maggior parte degli accordi esistenti.

## Il percorso dati SaaS a quattro livelli che la maggior parte dei team dimentica di tracciare

Siediti con un responsabile degli acquisti e percorri ciò che accade quando il prodotto di un fornitore di backup scrive un singolo record. Il percorso dati reale si presenta così, dall'alto verso il basso:

1. **L'applicazione del fornitore.** Il codice che acquisisce i tuoi dati, prende decisioni di instradamento e applica la logica di business. Gira sull'infrastruttura del fornitore. Manutenuta, aggiornata e monitorata dal fornitore.
2. **Il cloud del fornitore.** La regione dell'hyperscaler o il datacenter proprio del fornitore dove gira l'applicazione. Volumi di storage, rete, IAM. Spesso un hyperscaler con cui il fornitore ha un accordo di sub-responsabile del trattamento.
3. **La custodia delle chiavi del fornitore.** Le chiavi di cifratura che proteggono i dati a riposo nel cloud del fornitore. Nella maggior parte degli accordi SaaS, le detiene il fornitore. Le "chiavi gestite dal cliente" sono talvolta disponibili come opzione di livello superiore; in tali accordi, le chiavi si trovano comunque in un KMS di un hyperscaler che l'IAM del fornitore può richiamare.
4. **I sub-responsabili del fornitore.** I servizi di terze parti utilizzati dal fornitore (CDN, osservabilità, fatturazione, strumenti di supporto clienti) che possono transitare o memorizzare i tuoi dati, o metadati derivati da essi.

Ciascuno di quei quattro livelli è una voce nel tuo registro fornitori ai sensi di Article 21(2)(d). Ciascuno ha la propria storia di incidenti, il proprio raggio d'impatto in caso di violazione, la propria superficie di negoziazione contrattuale. Quando rinnovi con il fornitore SaaS, rinnovi implicitamente tutti e quattro, perché il contratto del fornitore SaaS è l'unico che puoi negoziare.

L'incidente Blackbaud è stata una violazione del livello 2 (cloud del fornitore) che si è propagata attraverso il livello 1 (applicazione del fornitore) ed era visibile a ogni cliente a causa del livello 3 (custodia delle chiavi del fornitore, nel loro caso chiavi lato server senza separazione per tenant nel database colpito). I sub-responsabili di Blackbaud non erano il vettore della violazione, ma i clienti vennero a conoscenza di tre di essi che non avevano censito.

## Blackbaud, la custodia delle chiavi in stile Druva e il pattern del contagio

Tre dettagli dei fascicoli SEC di Blackbaud sono quelli rilevanti per una lettura NIS2.

Primo, Blackbaud deteneva le chiavi di cifratura per i dati dei clienti, incluso l'ambiente di backup che era il bersaglio della violazione. Le chiavi gestite dal cliente non erano disponibili. Nel contenzioso SEC post-incidente, questo fu caratterizzato come una lacuna di controllo, non una violazione, perché i contratti di Blackbaud lo consentivano. La prospettiva di NIS2 sullo stesso accordo, ai sensi di Article 21(2)(d), è più severa, perché il cliente non può valutare in modo significativo il rischio di un controllo di cui non ha visibilità.

Secondo, la violazione ha interessato dati di backup più vecchi del database in produzione. Le organizzazioni clienti i cui dati in produzione erano stati eliminati dai sistemi primari di Blackbaud avevano comunque dati esposti tramite l'ambiente di backup. Questo è il pattern del contagio: una compromissione del fornitore raggiunge dati storici che il cliente riteneva già fuori ambito.

Terzo, oltre 13.000 organizzazioni clienti ricevettero notifiche di violazione. Molte erano piccole organizzazioni non profit e scuole senza capacità operativa di risposta, senza runbook DR, senza un secondo fornitore di backup su cui fare failover. L'incidente del fornitore, in quel senso, divenne il loro incidente.

Per un backup SaaS moderno in stile Druva, l'architettura è migliore in alcuni punti (la separazione delle chiavi per tenant è più comune, il BYOK è disponibile ai livelli superiori) ma il percorso dati a quattro livelli è lo stesso. L'applicazione del fornitore, il cloud del fornitore (tipicamente AWS), la custodia delle chiavi (a volte del fornitore, a volte BYOK nel KMS del cliente, a volte ibrida), i sub-responsabili. Una violazione a qualsiasi livello raggiunge ogni cliente simultaneamente, perché i dati di ogni cliente si trovano sullo stesso lato del confine.

Questo è l'argomento strutturale. Non è un attacco a Druva. Druva gestisce un'operazione più rigorosa di quanto facesse Blackbaud. L'argomento è che la struttura di qualsiasi prodotto di backup progettato come SaaS rende le violazioni di livello 2 e livello 3 un obbligo ai sensi di Article 21(2)(d) che il cliente non può assolvere in modo significativo.

## Il self-hosting elimina tre dei quattro livelli

Rediacc è costruita diversamente. L'architettura completa è documentata nella [pagina Architettura](/it/docs/architecture), ma la forma rilevante per la catena di approvvigionamento è quella di due binari che comunicano tramite SSH:

- `rdc` gira sulla workstation dell'operatore. Legge un file di configurazione JSON flat (sotto `~/.config/rediacc/`), si connette alle macchine proprie dell'operatore tramite SSH e invia i comandi.
- `renet` gira sul server proprio dell'operatore, con privilegi di root, e gestisce immagini disco cifrate con LUKS2, daemon Docker isolati e il reverse proxy.

L'operatore non accede mai all'infrastruttura di Rediacc (l'azienda) per eseguire un backup, un ripristino o un fork. Non esiste un cloud di Rediacc (l'azienda) nel percorso dati. La credenziale LUKS2 del repository è memorizzata nel file di configurazione locale dell'operatore (modalità `0600`), mai sul server, mai inviata a Rediacc. Il percorso dati si presenta così:

1. **Workstation dell'operatore.** Esegue `rdc`. Detiene la credenziale LUKS2.
2. **Server proprio dell'operatore.** Esegue `renet`. Contiene i repository cifrati con LUKS2.
3. **Destinazione di backup propria dell'operatore.** Qualsiasi storage compatibile con rclone (S3, B2, OneDrive, MinIO on-prem). Riceve volumi cifrati.

Non esiste un livello 4. Rediacc (l'azienda) non è un sub-responsabile del trattamento per nessun operatore che non abbia aderito all'[adattatore Cloud](/it/docs/architecture) sperimentale. Per gli operatori self-hosted, il rapporto con Rediacc (l'azienda) è una licenza software, non un accordo di trattamento dei dati.

Questo è l'argomento del percorso dati, ed è l'argomento giusto con cui aprire in una conversazione sul registro fornitori. Un concorrente SaaS può offrire chiavi gestite dal cliente (e la maggior parte di quelli moderni lo fa). Un concorrente SaaS non può offrire "non siamo un sub-responsabile del trattamento."

Il secondo punto, dopo che l'argomento del percorso dati è stato assimilato, riguarda la custodia delle chiavi. Con Rediacc, la credenziale LUKS2 è nel file di configurazione dell'operatore, punto. Non esiste key escrow, nessun servizio di recupero che Rediacc (l'azienda) possa attivare se l'operatore perde la credenziale. Questa è anche l'architettura consigliata per il [config store zero-knowledge](/it/docs/config-storage), dove la chiave di cifratura viene derivata lato client da un'estensione PRF di una passkey e il server memorizza blob opachi. Il server non può leggere le chiavi SSH, le credenziali LUKS2, gli indirizzi IP o qualsiasi configurazione in chiaro. La rotazione del token di accesso non conferisce al server accesso retroattivo in lettura.

Per Article 21(2)(h) (cifratura), questo è rilevante. Per Article 21(2)(d) (catena di approvvigionamento), lo è ancora di più, perché rimuove l'ultimo percorso di accesso logico da Rediacc (l'azienda) ai dati dell'operatore.

## Cosa il self-hosting non elimina

Il self-hosting modifica l'elenco dei fornitori, non lo cancella. Tre aspetti su cui un auditor farà ancora domande:

**1. Hai ancora fornitori, semplicemente diversi.** Il fornitore hardware (Hetzner, Hostinger, OVH, il tuo colo, il tuo bare metal). L'hypervisor (KVM, VMware). Il sistema operativo (Debian, Ubuntu, RHEL). Il container registry (Docker Hub, GHCR, il tuo registry privato). Le immagini base che i tuoi servizi scaricano. Ciascuno di questi è una voce ai sensi di Article 21(2)(d). Il self-hosting modifica l'elenco dei fornitori, non lo cancella.

**2. Rediacc non ha ancora ISO 27001, SOC 2 o BSI C5.** Questi sono nella roadmap, non ancora in mano. Per un team degli acquisti che usa le certificazioni come meccanismo di sbarramento, questa è una reale frizione. Il contropunto difendibile è quello che questo articolo ha argomentato: l'argomento del percorso dati significa che la maggior parte di ciò che quelle certificazioni attestano (controlli di sicurezza del cloud del fornitore, gestione degli accessi del personale del fornitore, gestione dei sub-responsabili del fornitore) non è in ambito, perché Rediacc (l'azienda) non si trova nel percorso dati. Tale argomento deve essere presentato con cura e in modo difendibile, non come sostituto delle certificazioni quando queste sono ciò di cui l'acquirente ha bisogno.

**3. Il livello GRC rimane a tuo carico.** Rediacc fornisce all'operatore un audit log con catena di hash di oltre 70 eventi (`rdc audit verify` valida la catena dall'inizio alla fine). Non fornisce un registro fornitori, un framework di controllo o un flusso di raccolta delle prove. Queste attività rimangono di competenza di Drata, Vanta, OneTrust o di uno dei player europei. Il [post sui costi reali](/it/blog/nis2-the-real-bill) analizza in dettaglio la struttura dei costi di questa complementarità.

## Il DPA che non devi più negoziare

Per rendere tutto questo concreto, ecco una riga "prima vs dopo" del registro da una vera conversazione di procurement, anonimizzata. L'acquirente è un'azienda manifatturiera tedesca con 280 dipendenti, classificata come "soggetto importante" ai sensi di Annex II. La loro voce originale del registro fornitori per il backup era questa:

| Campo | Prima |
|---|---|
| Fornitore | Acme Backup SaaS |
| Livello | Critico |
| Dati trattati | Database di produzione, PII dei clienti, registri finanziari |
| Sub-responsabili | AWS (eu-central-1), Datadog, Stripe, Zendesk |
| Stato contrattuale | DPA firmato 2023, SCCs allegati, piano delle misure rivisto l'ultima volta a gennaio 2025 |
| Custodia chiavi | Gestita dal fornitore (opzione BYOK non inclusa nel livello attuale) |
| Piano di uscita | "Il fornitore si impegna a fornire l'export dei dati in CSV entro 30 giorni dalla risoluzione" |
| Ultima valutazione | 2025-Q1, lacuna rilevata sulla custodia chiavi, rinviata al rinnovo |

Dopo il passaggio a Rediacc su Hetzner:

| Campo | Dopo |
|---|---|
| Fornitori | (1) Rediacc OÜ, licenza software; (2) Hetzner, IaaS |
| Livello | (1) Non critico (nessun piano dati); (2) Critico (piano dati, ma sotto controllo del cliente) |
| Dati trattati | (1) Nessuno; (2) Volumi cifrati, chiavi detenute dal cliente |
| Sub-responsabili | (1) Nessuno per self-hosted; (2) Solo interni a Hetzner, elencati nel loro DPA |
| Stato contrattuale | (1) Licenza software, nessun DPA necessario; (2) DPA Hetzner + SCCs già in vigore |
| Custodia chiavi | Cliente (credenziale LUKS2 nel config dell'operatore, non sul server) |
| Piano di uscita | "`rdc repo backup pull` da qualsiasi destinazione compatibile con rclone. I volumi sono cifrati con LUKS2; l'operatore detiene la credenziale." |
| Ultima valutazione | (2) coperta dalla revisione IaaS esistente |

Due voci nel registro invece di una. La voce di livello critico riguarda il fornitore IaaS, con cui l'acquirente aveva già un DPA in vigore e un piano di uscita testato, perché l'IaaS è un tipo di rapporto che la maggior parte dei team sa gestire. La voce Rediacc è non critica perché si tratta di una licenza software, non di un titolare del trattamento dei dati.

Questo è il motivo strutturale per cui un CISO finisce per voler ridurre le dipendenze SaaS nel piano dati, anche quando il costo di procurement appare simile su un foglio di calcolo. La voce del registro non ha la stessa forma.

## Checklist di procurement

Per qualsiasi fornitore che si dichiara "NIS2-ready" in un ciclo di vendita del 2026, sei domande:

**1. Dove si trova la chiave di cifratura per i nostri dati a riposo?** Se la risposta è "nel nostro HSM" o "nel KMS del cliente che possiamo richiamare tramite IAM," il fornitore si trova nella tua catena di custodia delle chiavi. Se è "nel tuo file di configurazione locale, mai sulla nostra infrastruttura," non vi si trova.

**2. Chi nella vostra azienda può tecnicamente leggere i nostri dati, a prescindere dai termini legali?** Non "chi è autorizzato a farlo" ma "chi potrebbe, se lo volesse e se il log di audit fosse disattivato." Se la risposta è diversa da zero, quella è la tua popolazione per una valutazione del rischio insider.

**3. Il ripristino viene testato su un clone reale della produzione, o su dati di test sintetici?** Article 21(2)(c) e (e) letti congiuntamente richiedono che il backup si ripristini effettivamente. Un fornitore che valida solo su dati sintetici non sta validando il recupero, sta validando l'integrità del file di backup. (Per approfondire, vedi il post complementare sulla [valutazione continuativa dell'efficacia](/it/blog/nis2-effectiveness-without-theatre).)

**4. Il vostro audit trail registra il tipo di attore, umano o agente, dietro ogni azione?** L'attività degli agenti AI è la categoria del log di audit in più rapida crescita. Un log di audit del 2026 che non distingue umano da agente sembrerà una lacuna nel 2027.

**5. Elencate tutti i sub-responsabili con accesso logico ai nostri dati, inclusi i metadati.** "Accesso logico" è la formulazione corretta. "Accesso logico inclusi i metadati" è quella migliore, perché l'accesso ai soli metadati è ciò che hanno tipicamente i sub-responsabili di fatturazione, osservabilità e supporto clienti, ed è sufficiente per far trapelare strutture sensibili anche quando il payload è cifrato.

**6. Qual è il vostro piano di uscita se venite acquisiti da un acquirente extra-UE nel 2027?** Il quadro di adeguatezza del GDPR, il Cloud Act e il FISA 702 sono tutti obiettivi in movimento. L'affermazione di residenza dei dati di un fornitore oggi non è una garanzia tra tre anni. La domanda dell'acquirente riguarda cosa accade al percorso dati se la proprietà del fornitore cambia.

Un fornitore che risponde a tutte e sei le domande in modo netto è insolito. Un fornitore che risponde a quattro su sei e riconosce apertamente le altre due ispira più fiducia di uno che risponde a tutte e sei con sicurezza. Il segnale di credibilità è la disponibilità a nominare ciò che non è risolto.

## Cosa significa per il prossimo ciclo di rinnovo

Se stai per affrontare un rinnovo di backup o DR nei prossimi dodici mesi e Article 21(2)(d) è in valutazione procurement, tre mosse concrete:

1. Disegna su una lavagna il percorso dati a quattro livelli del tuo fornitore attuale. Se non riesci a nominare il terzo sub-responsabile a valle, hai un problema di completezza del registro che precede NIS2, e il rinnovo è il momento giusto per risolverlo.
2. Fai la checklist delle sei domande sopra al tuo fornitore attuale. Invia le risposte al tuo DPO e al tuo auditor e chiedi se le lacune sono accettate. Se le lacune includono il livello 3 (custodia delle chiavi) o il livello 4 (sub-responsabili che non hai censito), quella è la leva.
3. Guarda come sarebbe un registro fornitori alternativo con un piano di controllo self-hosted. Confronta le voci del registro, non i costi di licenza. I costi di licenza sono simili entro un fattore due; le voci del registro hanno forme diverse. (Il post complementare sul [costo strutturale dello stack NIS2](/it/blog/nis2-the-real-bill) illustra in dettaglio cosa viene eliminato e cosa rimane.)

Se siamo noi l'alternativa nella tua shortlist, l'offerta è concreta. Mandaci il tuo questionario fornitori. Lo compileremo su un'istanza deployata, con le nostre risposte reali alle tue domande, lacune incluse. Se vuoi rivedere l'architettura prima di inviare la documentazione, prenoteremo una review architetturale di 30 minuti con il nostro team di ingegneria. Il percorso verso una voce di registro difendibile non è una brochure patinata. Sono le risposte, incluse quelle scomode.

Vuoi la mappa per articolo di Rediacc? Vedi [NIS2 e DORA](/it/docs/legal-nis2-dora). Ti serve il quadro piu' ampio? Leggi [Panoramica sulla conformità](/it/docs/legal-overview). Per la residenza dei dati, vedi [Sovranità dei dati](/it/docs/legal-data-sovereignty). Per capire perche' il self-hosted conta, vedi [On-Premise](/it/docs/on-premise).
