---
title: >-
  Il tuo pen test annuale è compliance theatre. L'Article 21(2)(f) di NIS2 ha
  appena reso questo un problema.
description: >-
  La valutazione continua dell'efficacia, il fork a tempo costante che ne
  abbatte i costi, e la scadenza di reporting dell'Article 23 che non è
  rispettabile senza artefatti forensi.
author: Rediacc
publishedDate: 2026-05-09T00:00:00.000Z
category: guide
tags:
  - nis2
  - sre
  - dr-testing
  - effectiveness
  - incident-reporting
featured: false
language: it
sourceHash: 0e471ac41759e4cb
sourceCommit: 8062f196566d6ba5f90b084e5484cf722b4bdf16
translatedFrom: en
---

> **TL;DR.** La maggior parte dei programmi di sicurezza testa il ripristino una volta all'anno, contro un ambiente di staging derivato dalla produzione nel corso dell'estate precedente. Commissionano un pen test su un ambiente che non assomiglia alla produzione, ottengono un report pulito e lo archiviano. L'Article 21(2)(f) di NIS2 ha introdotto una formula che gli auditor inizieranno presto a citare con insistenza: "policies and procedures to assess the effectiveness" delle misure. Una volta all'anno non è continuativo. Lo staging obsoleto non è il sistema sotto test.
>
> - La direttiva dice: Article 21(2)(e) e (f) insieme richiedono che i test di recovery e di sicurezza funzionino davvero, on demand, contro la produzione corrente.
> - Il costo di farlo bene con strumenti Delphix-class, Veeam Instant Recovery o Rubrik Live Mount è ciò che spinge la maggior parte dei team a scegliere silenziosamente lo staging.
> - Quando un fork di produzione richiede sette secondi, l'economia si ribalta. Le esercitazioni settimanali diventano realistiche. La valutazione continua dell'efficacia diventa documentabile.
> - Il reporting previsto dall'Article 23 (early warning a 24 ore, notifica a 72 ore, report finale a un mese) è irraggiungibile senza artefatti di qualità forense. Gli artefatti li forniamo noi; il SOC, il SIEM e il flusso di notifica a ENISA rimangono a carico dell'operatore.

Entra in qualsiasi team SRE di medie dimensioni e fai una domanda: quando è stato eseguito l'ultimo ripristino completo end-to-end, non una verifica del file di backup, ma l'avvio effettivo del sistema recuperato con app, database e configurazioni, e la validazione che funzioni? La risposta onesta, nella maggior parte dei team, è "nell'ultimo tabletop exercise dell'anno scorso." Poi tutti tornano al lavoro.

L'Article 21(2)(f) di NIS2 introduce una formula che gli auditor inizieranno presto a citare con insistenza:

> "strategie e procedure per valutare l'efficacia delle misure di gestione dei rischi di cibersicurezza"

Non dice "annuale." Dice "strategie e procedure." Letto insieme all'Article 21(2)(e), che prescrive:

> "sicurezza dell'acquisizione, dello sviluppo e della manutenzione dei sistemi informatici e di rete, compresa la gestione e la divulgazione delle vulnerabilità"

l'obbligo è continuo, non periodico. Le linee guida di implementazione ENISA del 2024 (Allegato IV del Implementing Regulation (EU) 2024/2690) <!-- nis2-quote-skip: ENISA Implementing Regulation 2024/2690, separate source --> confermano la direzione con espressioni come "ongoing assessment" e "documented evidence of testing covering current production environments, not legacy or staging snapshots."

Se la tua strategia sull'efficacia è "pen test annuale contro staging," il 2026 sarà scomodo.

Questo articolo è rivolto a SRE lead, responsabili operativi e security engineer che gestiscono concretamente le esercitazioni. È anche l'articolo che nomina l'argomento che un operatore consolidato userà in qualsiasi contro-offerta: servizi di reporting gestito e connettori SIEM per le scadenze dell'Article 23. Noi non risolviamo questo. Forniamo gli artefatti. Il flusso di reporting, il SOC, il motore di notifica a ENISA: quelli rimangono a carico dell'operatore.

## Lettura combinata di Article 21(2)(e) e (f)

L'Article 21 elenca dieci misure minime. Due riguardano come si costruisce e come si verifica.

e) **Sicurezza nell'acquisizione, nello sviluppo e nella manutenzione**: è la misura lato supply. Quando si accetta una patch CVE, quando si rilascia un nuovo microservizio, quando si esegue una finestra di manutenzione, la modifica deve essere validata contro l'ambiente reale in cui verrà applicata. Le linee guida ENISA sono esplicite: gli ambienti di staging che differiscono dalla produzione per forma dei dati, scala, segreti o configurazione non soddisfano l'obbligo di test per le modifiche rilevanti dal punto di vista della sicurezza.

f) **Valutazione dell'efficacia**: è la misura di verifica. Qualunque controllo si abbia, occorrono strategie e procedure per confermare che funzionino davvero. La formulazione "efficacia" fa lavoro concreto. È la differenza tra "abbiamo un backup" (il controllo esiste) e "abbiamo dimostrato di poter eseguire il ripristino da esso martedì scorso e il sistema ripristinato ha superato uno smoke test" (il controllo è efficace).

Letti insieme, i due misure richiedono che le modifiche rilevanti per la sicurezza siano testate in ambienti equivalenti all'attuale produzione e che i test producano evidenza che la modifica abbia funzionato. Una volta all'anno è troppo raro. Lo staging obsoleto è il target sbagliato. Un ripristino non validato non è efficace.

La risposta tradizionale a questo obbligo è quella che la maggior parte dei team già adotta: dichiarare che lo staging è simile alla produzione, eseguire esercitazioni annuali contro lo staging, scrivere un runbook che descriva cosa accadrebbe in un incidente reale, e sperare che il regolatore non ponga troppe domande. Funzionava quando il regolatore era il DPA del GDPR e l'incidente era di natura privacy. NIS2 mette un regolatore diverso al posto di guida (il CSIRT nazionale, o BSI in Germania, ANSSI in Francia, ACN in Italia), e quel regolatore fa domande operative.

## La trappola dello staging obsoleto

Tre fattori rendono lo staging non-produzione nel momento in cui la maggior parte dei team lo usa per i test.

**Forma dei dati**: i dati di produzione presentano casi limite nella coda lunga. Il cliente con il campo note da 8.000 caratteri, l'account legacy con un NULL dove ogni altra riga ha un valore, la tabella in join che ha restituito 12 milioni di righe per il tenant che ha importato tutta la cronologia del suo CRM. Lo staging ha il 1% del volume di produzione e la coda lunga non è nel campione.

**Scala**: una query che risponde in 50ms su 10.000 righe in staging risponde in 8 secondi su 12 milioni in produzione. Uno scenario di pen test che non trova una vulnerabilità di esaurimento in staging la trova in produzione immediatamente. La forma delle vulnerabilità dipende dalla scala dei dati.

**Configuration drift**: la produzione ha accumulato variabili d'ambiente, ruoli IAM, policy di rete, segreti ruotati tre volte, un certificato SSL rinnovato la settimana scorsa, un feature flag che avrebbe dovuto essere disattivato a marzo ma è rimasto attivo. Lo staging ha una copia pulita della configurazione dell'estate scorsa più quanto aggiunto per il progetto più recente. I delta sono esattamente dove si nascondono i bug di sicurezza.

Quindi quando la patch supera lo staging, la fiducia del team è mal riposta. Quando il pen test riporta un esito pulito contro lo staging, il report è fuorviante. Quando l'esercitazione di recovery ripristina correttamente lo staging, il team non ha validato il recovery di produzione.

Gli auditor nel 2026 non stanno discutendo se lo staging sia sufficientemente valido. Chiedono evidenza dei test contro la produzione corrente. L'evidenza deve essere con timestamp, deve mostrare che il sistema sotto test assomigliava alla produzione al momento del test, e deve mostrare che il test ha prodotto un risultato.

La maggior parte dei team non è in grado di produrre quella evidenza oggi, perché il costo di eseguire esercitazioni contro la produzione corrente è proibitivo con gli strumenti tradizionali.

## Il costo di farlo bene con gli strumenti tradizionali

Il mercato ha risposte. Le risposte sono costose.

**Veeam Instant Recovery**: avvia una VM direttamente da un backup, montala, puntaci un'interfaccia di rete. Usato per test di recovery application-consistent. Capace di testare il recovery da un backup recente; l'ambiente di staging diventa il backup recuperato. Leggero in termini di capacità perché le letture del disco provengono dal repository di backup. Costo: la licenza Veeam Data Platform Premium scala per numero di VM, e il test di recovery deve comunque essere pianificato e gestito da un ingegnere. La maggior parte dei team lo esegue una volta al trimestre.

**Rubrik Live Mount**: concetto simile, mount istantaneo di uno snapshot di backup per i test. Migliore integrazione con workload cloud-native. Stesso pattern operativo. Stesso overhead di ingegneria per test.

**Delphix (Perforce DevOps Data)**: virtualizza i database sorgente cosi' lo sviluppo ottiene cloni quasi istantanei. Risolve il problema dei dati a forma di produzione in dev. Solo database. Non clona i servizi applicativi, le configurazioni, i segreti o lo stato dei container. La licenza annuale raggiunge cifre a sei zeri per i team mid-market.

**Tonic.ai, Redgate Test Data Manager**: mascherano o sintetizzano dati per dev e test. Buona soluzione per il compromesso privacy-realismo. La forma e la scala dei dati assomigliano alla produzione. Ma questi strumenti clonano i dati, non lo stack applicativo. Usali per il QA, non per le esercitazioni di sicurezza dove la configurazione e' il bug.

**Build personalizzata**: esegui un hot backup, ripristinalo in un ambiente parallelo, esegui il test, smontalo. Concettualmente possibile. Operativamente uno sforzo di ingegneria di più giorni per ogni esercitazione. Il team lo fa una volta perché è stato costretto, poi mai più.

Clonare la produzione completa, incluso lo stato applicativo, ha sempre significato una di tre cose. Copiare ogni byte (lento, costoso su larga scala). Fare lo snapshot della VM (funziona per IaaS, si rompe per container e Kubernetes). Oppure virtualizzare solo il database. Tutti e tre costano di piu' per esercitazione al crescere dell'ambiente.

Quando il costo per test scala con la dimensione, le esercitazioni diventano eventi rari. Gli eventi rari non soddisfano la valutazione continua dell'efficacia.

## Cosa cambia quando un fork di produzione richiede sette secondi

Rediacc utilizza i reflink BTRFS per il forking dei repository. Il meccanismo è copy-on-write a livello di filesystem: il fork condivide blocchi con il padre finché uno dei due non scrive nuovi dati, a quel punto divergono solo i blocchi modificati. L'operazione di fork stessa è a tempo costante indipendentemente dalla dimensione del repository.

Nel nostro [post sul test PocketOS](/it/blog/i-tested-rediacc-against-the-pocketos-incident), abbiamo forkato un repository di produzione da 128 GB in 7,2 secondi end-to-end. Il reflink stesso ha richiesto 2,3 secondi. La maggior parte del resto riguarda il provisioning di un nuovo Docker daemon, il mount del volume cifrato LUKS2, e l'avvio dello stack di servizi su una nuova subnet IP loopback.

La forma del fork conta quanto la velocità. Un fork Rediacc è full-stack. Il repository forkato contiene:

- Il volume cifrato LUKS2 con tutti i file di dati e lo stato del database.
- La configurazione del Docker daemon e lo stato dei container.
- Gli hook del ciclo di vita del Rediaccfile (`up`, `down`, `info`).
- La subnet IP loopback del repository (un nuovo `/26` ritagliato per il fork).
- Il network ID del repository, il socket del daemon e il mount namespace.

Quello che non contiene per default sono i segreti di cui i servizi hanno bisogno per comunicare con SaaS esterni (Stripe, mail relay, chiavi DKIM, chiavi di firma webhook). Per questi, `rdc repo secret` mantiene le credenziali completamente al di fuori dell'immagine del fork in modo che le chiamate SaaS esterne da un fork siano esplicite, non ereditate. Vedi [Repositories](/it/docs/repositories) per il modello dei segreti.

Questa forma, full-stack con gestione esplicita dei segreti, è ciò che rende il fork adatto come target per i test di sicurezza. Il fork è il sistema di produzione, con i dati di produzione correnti, la configurazione di produzione corrente, lo stato corrente dei container, di dieci secondi fa. Questo è il sistema contro cui l'auditor vuole che tu stia testando.

Per i casi d'uso documentati, vedi [Risk-Free Upgrades](/it/docs/risk-free-upgrades) e [Tutorial: Forking](/it/docs/tutorial-forking).

## Una routine di valutazione continua dell'efficacia da eseguire settimanalmente

Ecco una routine concreta che soddisfa Article 21(2)(e) e (f) per un repository di produzione, eseguibile su base settimanale da un singolo SRE.

**Passo 1**: fork della produzione.

```bash
rdc repo fork --parent prod-app --tag effectiveness-2026w19 -m hostinger
```

Il fork e' nominato con la settimana ISO cosi' il log di audit si legge da solo. Il repo si avvia sotto un sottodominio del fork (`<service>-fork-effectiveness-2026w19.prod-app.<machine>.<basedomain>`). Il cert wildcard del parent lo copre. Nessun nuovo handshake TLS.

**Passo 2**: applica la patch sotto test, sul fork.

```bash
rdc repo up --name prod-app:effectiveness-2026w19 -m hostinger
rdc term connect -m hostinger -r prod-app:effectiveness-2026w19 -c "apt-get install -y openssl=3.5.5-1"
```

La sessione term viene eseguita come utente non privilegiato `rediacc` (UID 7111), in un mount namespace separato, con `DOCKER_HOST` delimitato al socket del daemon del fork. L'accesso cross-repo è bloccato a livello kernel (il fork non può raggiungere la subnet loopback della produzione). Vedi [Architecture § Docker Isolation](/it/docs/architecture) per il modello di isolamento.

**Passo 3**: esegui lo smoke test contro il fork.

```bash
curl -fsS https://app-fork-effectiveness-2026w19.prod-app.hostinger.example.com/health
# (qui va il tuo smoke test specifico del progetto)
```

**Passo 4**: esegui l'esercitazione di ripristino. Usa il backup hot più recente della produzione, estratto verso un target allineato al fork.

```bash
rdc repo backup pull --from offsite-b2 --name prod-app:restore-2026w19 -m hostinger
rdc repo up --name prod-app:restore-2026w19 -m hostinger
# verifica che il fork ripristinato risponda allo stesso smoke test
curl -fsS https://app-fork-restore-2026w19.prod-app.hostinger.example.com/health
```

Questo è il test di recovery che Article 21(2)(c) e (f) richiedono: non "l'integrità del file di backup verificata" ma "il sistema recuperato risponde a uno smoke test."

**Passo 5**: registra il risultato nel log di audit, poi smonta.

```bash
rdc audit log --since "1 hour ago" > /tmp/effectiveness-2026w19.json
rdc repo destroy --name prod-app:effectiveness-2026w19 -m hostinger --force
rdc repo destroy --name prod-app:restore-2026w19 -m hostinger --force
```

Il log di audit cattura ogni passo (creazione del fork, repo up, sessioni term, backup pull, repo destroy). È incatenato per hash. `rdc audit verify` sulla workstation dell'operatore conferma che la catena non è stata modificata dalla scrittura degli eventi. Vedi [Account Security § CLI Security Posture for AI Agents](/it/docs/account-security) per il modello di audit.

Il tempo totale di esecuzione per la routine, su un repository da 128 GB, è inferiore a 15 minuti. La maggior parte è lo smoke test e il round-trip di rete per il backup pull. Le operazioni di fork stesse richiedono pochi secondi ciascuna.

Un singolo SRE che esegue questa routine una volta alla settimana produce 52 record di efficacia con timestamp e log di audit all'anno. Questa è la forma dell'evidenza che un auditor richiede.

Vuoi la storia completa del recovery? [Cross Backup Strategy](/it/docs/cross-backup) copre le esercitazioni cross-machine e intercontinentali. [Backup & Restore](/it/docs/backup-restore) e' il punto di partenza. Per un evento di corruzione parziale, vedi [Time Travel Recovery](/it/docs/time-travel-recovery).

## Article 23: la scadenza di reporting che non è rispettabile senza artefatti

L'Article 23 di NIS2 è il cronometro per la segnalazione degli incidenti. Tre scadenze:

- **24 ore** dalla consapevolezza di un incidente significativo: un early warning al CSIRT nazionale o all'autorità competente. Indica che l'incidente è in corso e fornisce informazioni iniziali sull'impatto transfrontaliero.
- **72 ore** dalla consapevolezza: notifica completa dell'incidente. Include la valutazione della gravità, i primi indicatori di compromissione, il tipo di minaccia e l'impatto noto.
- **Un mese** dalla notifica: report finale. Descrizione dettagliata, causa radice, mitigazioni applicate, rischio residuo.

È un cronometro stretto. È anche un cronometro che scorre mentre l'incidente è ancora in corso. La versione più dolorosa dell'Article 23 è quella in cui il team sta ripristinando i servizi, preservando le prove forensi, coordinandosi con le forze dell'ordine, facendo un briefing al team esecutivo e scrivendo l'early warning, tutto nelle prime 24 ore.

Gli strumenti di backup standard impongono un compromesso: ripristina il sistema per recuperare il servizio, oppure preserva il sistema per indagare. Una volta eseguito il ripristino dal backup, le prove live della compromissione sono perse. Una volta congelato il sistema compromesso per indagare, non si stanno servendo i clienti. Entrambe le opzioni sono problematiche in una scadenza Article 23.

Il meccanismo di fork risolve il compromesso. Lo stato compromesso può essere forkato (il repository padre diventa lo snapshot forense) e un fork parallelo può essere avviato dal backup pulito più recente per servire il traffico. Il fork forense è in sola lettura per l'analisi. Il fork di servizio risponde ai clienti. Entrambi esistono simultaneamente sulla stessa macchina, condividendo blocchi tramite reflink, motivo per cui questo è operativamente sostenibile.

In concreto, durante un incidente:

```bash
# Snapshot dello stato compromesso per il forensics. Il fork è lo snapshot.
rdc repo fork --parent prod-app --tag forensic-2026-05-09T14-23Z -m hostinger

# Avvia un fork di servizio dall'ultimo backup pulito. Tag diverso.
rdc repo backup pull --from offsite-b2 --name prod-app:serving-2026-05-09T14-30Z -m hostinger
rdc repo up --name prod-app:serving-2026-05-09T14-30Z -m hostinger
# Reindirizza il traffico al nuovo fork di servizio tramite DNS o il route server.
```

Il fork forense risponde alla domanda del regolatore all'ora 60: "mostraci lo stato esatto dei tuoi sistemi al momento della compromissione." Il fork di servizio risponde alla domanda del cliente. Il log di audit con 70 o più eventi risponde a "chi ha fatto cosa e quando" in modo incatenato per hash e verificabile.

Questo è ciò che Rediacc fornisce all'operatore. Quello che non forniamo:

- **Il SIEM**. Non effettuiamo streaming verso Splunk, Datadog, Sentinel o il tuo stack interno. Il log di audit è JSONL locale sulla workstation dell'operatore; collegarlo a un SIEM è un lavoro di integrazione dell'operatore.
- **Il SOC**. Non gestiamo una capacità di rilevamento 24x7. Non produciamo alert. Non eseguiamo triage.
- **Il reporting gestito**. Non presentiamo il report a ENISA. Non redigiamo l'early warning. Non coordiniamo con il CSIRT nazionale per tuo conto.

Questo è l'argomento che un operatore consolidato userà contro di noi. Veeam Data Platform con integrazioni Coveware, Rubrik con il suo ramo di servizi gestiti, e alcune società specializzate in IR a retainer (Mandiant, Kroll, S-RM in Europa) vendono esattamente lo strato operativo che Rediacc non fornisce. Fingere il contrario è la mossa di marketing che ci mette nei guai. La posizione difendibile è: Rediacc ti fornisce artefatti di qualità forense che quei servizi non possono produrre autonomamente; quei servizi ti forniscono lo strato operativo di reporting che Rediacc non può fornire. Sono complementari. Un programma NIS2 ha bisogno di entrambi.

## Cosa Rediacc non gestisce per te

Due cose che un SRE dovrebbe sapere in anticipo, prima di decidere se il resto di questo articolo è rilevante.

**Rediacc non esegue pen test**. Il fork come target è l'ambiente, non la capacità di test. Un pen test avversariale reale rimane a carico del tuo red team o della tua società di test in contratto (Pentera, Horizon3.ai per i test autonomi; società di consulenza specializzate per quelli human-led). Rediacc elimina l'alibi che l'ambiente di test non era realistico. Non elimina il costo del test.

**Rediacc non scrive i tuoi runbook**. I comandi CLI sopra riportati sono i componenti operativi. Le decisioni su quando forkare, quando eseguire il failover, come comunicare con i clienti, quando coinvolgere le forze dell'ordine, sono decisioni da runbook. Quelle devono ancora essere redatte, esercitate e aggiornate dal tuo team. L'Article 21(2)(b) di NIS2 (incident handling) è un obbligo di processo, non di strumenti, e noi soddisfiamo una parte di esso, non tutto.

Sul lato procurement (certificazioni, GRC, il problema del supplier register), vedi il [post sulla supply chain](/it/blog/nis2-supply-chain-self-hosted). Sul lato costi (cosa rimane nel budget una volta che ti self-hosti), vedi il [post sul conto reale](/it/blog/nis2-the-real-bill).

La lettura corretta di questi post: Rediacc è uno strato di strumenti, non un programma di sicurezza. Elimina gli alibi e produce evidenza. Non gestisce il programma al posto tuo.

## Cosa vuole vedere un auditor nel 2026

Tre artefatti. Producili e la conversazione su Article 21(2)(e) e (f) diventa breve.

**Artefatto 1: la cadenza delle esercitazioni di fork**. Un log con timestamp delle esercitazioni di efficacia eseguite su base settimanale o bisettimanale nell'arco dei dodici mesi precedenti. Ogni voce mostra il repository padre, il tag del fork, la patch o la modifica sotto test, il risultato dello smoke test e il timestamp di smontaggio. Il log di audit prodotto da `rdc audit log --since` cattura tutto questo.

**Artefatto 2: il log di audit di quelle esercitazioni, incatenato per hash**. La catena hash sul log di audit è ciò che trasforma "abbiamo eseguito 47 esercitazioni l'anno scorso" da una dichiarazione in evidenza. `rdc audit verify` valida la catena end-to-end. Il risultato della validazione è un singolo output di comando che un auditor può rieseguire.

**Artefatto 3: la traccia di verifica del backup**. Per ogni strategia di backup pianificata, l'unità systemd produce un file sidecar di stato in `/var/run/rediacc/cold-backup-<guid>.status.json` per repo per esecuzione, e una riga di log finale di riepilogo. `rdc machine backup status` espone entrambi. Combinato con l'esercitazione di ripristino settimanale del Passo 4 della routine sopra, questo fornisce all'auditor una traccia "backup-and-restore-tested," non solo "backup-taken." Vedi [Monitoring](/it/docs/monitoring) per la superficie diagnostica.

Insieme, gli artefatti rispondono alla domanda "i tuoi controlli sono efficaci" con timestamp e una catena di hash. Non attestazione. Evidenza.

## Cosa significa per la prossima riunione di pianificazione trimestrale

Se il tuo team sta entrando nella pianificazione Q3 e Article 21(2)(f) è nel backlog di sicurezza, tre mosse concrete:

1. Verifica la tua attuale strategia di efficacia. Estrai gli ultimi dodici mesi di report di pen test, esercitazioni di recovery e ticket di validazione delle patch. Conta quanti di essi avevano come target la produzione corrente. Il conteggio onesto è di solito inferiore a cinque.
2. Scegli un repository di produzione ed esegui la routine settimanale sopra descritta per un mese. La routine è progettata per essere gestita da un solo SRE senza overhead di pianificazione. Dopo quattro settimane, avrai quattro record di efficacia con timestamp; è più di quanto la maggior parte dei team produce in un anno.
3. Avvia la conversazione su chi copre il SIEM, il SOC e il flusso di reporting dell'Article 23. Se la risposta è "non siamo arrivati a quel punto," il posto giusto da cui partire non è Rediacc, ma una capacità di rilevamento 24x7. Siamo complementari a quella conversazione; non ne siamo il punto di partenza.

Se vuoi vedere il tempo di fork sul tuo repository più grande, l'offerta è semplice. Eseguilo in una chiamata con noi. Se il fork richiede più di dieci secondi, non devi nulla. Se richiede sette, passeremo il resto della chiamata a esaminare la routine sul tuo stack.

La storia dei costi strutturali (cosa viene eliminato nel resto dello stack di sicurezza e cosa rimane nella voce di budget) è nel post complementare sul [conto reale](/it/blog/nis2-the-real-bill). Per l'angolo supplier register e procurement, vedi [Article 21(2)(d) e self-hosting](/it/blog/nis2-supply-chain-self-hosted).

Per la mappa pubblica di cio' che Rediacc fa rispetto a ogni articolo NIS2, vedi [NIS2 and DORA](/it/docs/legal-nis2-dora).
