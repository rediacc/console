---
title: Proxy ed Executor
description: Come i comandi da browser e da client leggero vengono eseguiti senza che il client detenga mai chiavi SSH o indirizzi macchina
category: Concepts
tags:
  - security
  - networking
subcategory: architecture
order: 4
language: it
sourceHash: "7230a907205b8c84"
sourceCommit: "9f58d83e01b4d46f8ce31af467a203b4d195e801"
---

# Proxy ed Executor

Normalmente `rdc` gira sulla tua macchina con la tua configurazione e le tue chiavi SSH, e si collega direttamente ai tuoi server. Il modello proxy divide questo flusso in due: un client leggero che non detiene alcun segreto, e un **executor** che li detiene e fa il lavoro. Il pulsante Esegui della [console web](/it/docs/web-console) e il flag `--proxy` della CLI sono entrambi client leggeri, e parlano lo stesso protocollo.

## Intento del comando, non comandi

Un client leggero non detiene mai una chiave SSH, un indirizzo macchina o una configurazione decifrata. Quando vuole eseguire qualcosa, invia solo l'intento del comando: un identificativo per il comando (il suo percorso nel contratto CLI, ad esempio `repo up`) più i parametri. L'executor cerca il comando nello stesso contratto, lo risolve nella funzione lato server sottostante, risolve la macchina di destinazione dalla configurazione decifrata ed esegue tutto sulla propria connessione SSH. L'output torna in streaming al client.

L'executor è la CLI stessa, avviata come server con `rdc serve`. Lo stesso binario che gli operatori usano su un laptop diventa la cosa che esegue i comandi per loro conto. Ha due possibili collocazioni:

- **`--mode daemon`**: gira su un host che controlli tu, iscritto in modo headless come qualsiasi CLI (vedi [Archivio di Configurazione](/it/docs/config-storage)), quindi può derivare da solo la chiave di configurazione e non ha bisogno di alcuna concessione per sessione. Questo è il livello rigoroso: SSH non esce mai dalla tua rete.
- **`--mode container`**: gira in un container ospitato per te, associato alla tua organizzazione. Parte senza alcuna chiave e non può fare nulla finché un client non gliene concede una per la sessione. Questo è il livello di convenienza.

## La concessione della CEK

L'archivio di configurazione è zero-knowledge: il server memorizza solo blob cifrati, e la chiave di cifratura del contenuto (CEK) esiste in chiaro solo su un client che l'ha sbloccata. Un executor in modalità container deve quindi *ricevere in concessione* la chiave, e la concessione non deve esporla al server nel frattempo.

Il flusso è questo: un browser sbloccato apre una sessione con l'executor, riceve la chiave pubblica della sessione e sigilla la CEK per quella sessione usando X25519. Il blob sigillato passa attraverso il server dell'account, ma il server non può aprirlo, quindi la proprietà zero-knowledge si mantiene end-to-end. L'executor decifra la CEK solo in RAM, con una scadenza per inattività di 30 minuti; nulla viene mai scritto su disco. Le richieste di comando successive fanno riferimento alla sessione concessa tramite l'header `X-Config-Session`.

Un dettaglio importante ai fini di audit: la stessa identità utente attraversa tutte e tre le fasi (apertura della sessione, concessione della chiave, esecuzione dei comandi). Il server dell'account non inoltra mai la propria credenziale all'executor. Per ogni fase emette un token a vita breve attribuito all'utente reale, e ricontrolla ogni volta l'appartenenza di quell'utente. L'executor verifica qualsiasi token gli venga presentato prima di agire. Una concessione fatta da un utente non può essere usata da un altro.

La metà `state` di una configurazione (dati di runtime locali all'host) non viaggia mai nel blob di configurazione, quindi non raggiunge mai un executor nemmeno per questa via.

## Cosa può girare tramite un proxy

Non tutti i comandi hanno senso in remoto. Ogni comando nel contratto porta un flag `proxyCapable`, e l'executor lo impone lato server, indipendentemente da qualsiasi configurazione di policy:

- I **comandi del piano macchina, non interattivi** (deploy, backup, status, logs, e così via) sono abilitati al proxy.
- I **comandi del piano configurazione** non lo sono: modificano la configurazione, che su questo percorso è compito del browser (la console web li instrada invece al proprio editor di configurazione).
- I **comandi interattivi** (terminali, sessioni VS Code) non lo sono: non c'è un TTY su questo canale.
- I **comandi di trasferimento lato client** (`rdc repo sync`) non lo sono: spostano dati tra il filesystem del *client* e una macchina, e l'executor non ha i file del client.

La console web legge lo stesso flag per decidere se un comando riceve o meno un pulsante Esegui, ma l'executor rifiuta i comandi non abilitati indipendentemente da ciò che il client invia.

## L'executor fittizio

In sviluppo, quando non è configurato alcun executor reale, il server dell'account risponde da sé alle richieste di comando con stream fittizi e dati chiaramente falsi (nomi di risorse con prefisso `mock-`). Questo rende l'intera console utilizzabile, inclusi form, streaming e rendering dei risultati, senza bisogno di una macchina o di uno sblocco. L'esecuzione reale richiede un executor reale.

## Limitare da dove si connette l'executor

Il bucket `access` della configurazione contiene gli intervalli di origine IPv4 e IPv6 consentiti per le chiavi SSH. Gli intervalli possono essere impostati per l'intera configurazione, per chiave e per macchina, così una macchina accetta una chiave solo dagli indirizzi da cui si connette il suo executor.

- `rdc config access add <key> --public-key ... --hosted-executor` registra una chiave e associa i due intervalli dell'executor ospitato: `104.28.0.0/16` e `2a09:bac0::/29`. Sono intervalli di uscita di Cloudflare osservati, non un elenco pubblicato da Cloudflare, quindi possono cambiare.
- `rdc machine access set <machine> --key <key>` assegna una chiave a una macchina; `--ipv4`, `--ipv6` e `--clear-ranges` regolano gli intervalli per quella macchina.
- `rdc machine access push <machine>` scrive le righe di accesso sulla macchina, e `--dry-run` mostra il risultato senza modificare nulla.
- `rdc machine access show <machine>` stampa le righe di accesso in vigore.

`machine setup` riapplica le righe di accesso, così una macchina ricostruita riacquista le sue restrizioni.

Un push che escluderebbe la sessione SSH corrente, perché il suo indirizzo è fuori dagli intervalli della chiave in uso, viene rifiutato con `ACCESS_LOCKOUT` e non viene scritto nulla. Un push viene rifiutato con `ACCESS_FILE_CHANGED` quando il file sulla macchina è cambiato nel frattempo; nulla è stato applicato, quindi il push si può ripetere senza rischi.

## Job, ticket e polling

Ogni comando del piano macchina viene eseguito sulla macchina come un job: un'unità systemd gestita da renet, con stato e registro degli eventi conservati in uno spool sulla macchina. Una connessione interrotta non ferma quindi mai il lavoro, e qualsiasi client può riprendere il job tramite il suo ID.

- **La finestra di collegamento.** L'executor trasmette gli eventi di un job per al massimo 20 secondi, con una riga di heartbeat ogni 10 secondi finché il flusso resta silenzioso. Un job che termina entro la finestra restituisce il risultato nella stessa richiesta. Un job più lungo restituisce un risultato con `state: running` e l'ID del job, dopo una riga `job` che riporta la macchina e gli eventuali job sovrapposti.
- **Il polling.** Il client chiede poi a `GET /v1/jobs/<id>/poll` gli eventi successivi all'ultima riga vista, insieme allo stato del job, e dirada le richieste quando le risposte restano vuote. `POST /v1/jobs/<id>/cancel` annulla il job. Entrambe le route applicano la stessa policy del comando che ha avviato il job, e il polling che vede per primo uno stato terminale scrive l'evento di audit una sola volta.
- **I ticket.** Ogni invocazione scrive anche un ticket nella directory di configurazione della CLI (`jobs/<config>.jsonl`). `rdc job wait <id>` attende un job e termina con il suo exit code; `rdc job list`, `status`, `logs`, `cancel` e `gc` gestiscono il resto. Ctrl-C durante un follow si stacca senza annullare ed esce con 130. Un follow la cui connessione non è stata ristabilita esce con 16 e conserva il ticket.
- **I passi.** Il lavoro che segue un job, come registrare un risultato nella configurazione o mostrare un elenco, è un passo annotato nel ticket e nello spool. Un passo viene eseguito una sola volta, nel posto che per primo vede terminare il job: il comando stesso, `rdc job wait`, l'avviso stampato dal comando successivo o il polling dell'executor. La rivendicazione avviene sulla macchina, quindi due osservatori non eseguono mai lo stesso passo.
- **Le sovrapposizioni.** Un avvio che si sovrappone a un job attivo sullo stesso repository o sulla stessa macchina stampa un avviso con il comando che si collega al job attivo. Quando la policy di sovrapposizione rifiuta l'avvio, il comando esce con 15 (`BUSY`), e il rifiuto riporta i job sovrapposti in `overlaps`.
- **I passi mentre il client è assente.** Un passo di successo viene eseguito solo quando il job è `succeeded`, e un passo di fallimento, come un rollback, solo quando è `failed` o annullato. Quando un job termina entro la finestra di collegamento, l'executor mantiene il collegamento anche se il client si disconnette ed esegue i passi, così un comando breve il cui client ha perso la risposta completa comunque i suoi passi. I passi vengono eseguiti solo per un osservatore la cui configurazione coincide con quella che ha avviato il job (l'executor che mantiene il collegamento li esegue con quella configurazione, quindi la condizione è soddisfatta); ogni altra configurazione mostra `N steps pending for config <name>`. L'avviso stampato dal comando successivo esegue i passi in sospeso per al massimo 20 secondi dopo l'output di quel comando, e solo in un'esecuzione testuale interattiva. Con `-o json`, `-q` o MCP non esegue nulla e stampa `steps pending: rdc job wait <id>` su stderr. Finché nessun osservatore ha visto il job terminare, il servizio continua a funzionare, ma i passi attendono: i nomi DNS, la sincronizzazione dei certificati e l'elenco degli URL dopo `repo up`, le pianificazioni di backup di un fork, di una migrazione o di un ripristino, e il record di base che rende il push successivo un delta. `rdc job list` mostra `steps pending` finché non vengono eseguiti.
- **Le eccezioni.** I comandi interattivi (`term connect`, `repo tunnel`, `vscode connect`, `repo exec -i` e `repo logs -f`), i trasferimenti lato client (`repo sync upload`, `download` e `status`, e `backup upload` e `download`), i comandi `job`, `serve`, `vscode serve status` e `stop`, e i comandi che non fanno alcuna chiamata a renet, come `cluster kubeconfig` e `machine access push`, non vengono eseguiti come job. I tratti OpenTofu locali di `machine provision` e `deprovision` girano sul client come prima. Ogni altro comando del piano macchina è un job.
- **La conservazione.** Un job di sola lettura terminato viene conservato per un'ora, ogni altro job terminato per sette giorni. Un job con un passo che nessuno ha rivendicato viene conservato sette giorni qualunque sia la sua classe, e un job in esecuzione non viene mai rimosso. Lo spool contiene al massimo 2000 job terminati e 256 MiB, e i più vecchi escono per primi; i limiti saltano un job con un passo non reclamato finché non sono trascorsi i suoi sette giorni. La pulizia viene eseguita all'avvio di un job, al massimo una volta all'ora. L'unità systemd del job viene fermata alla prima lettura di stato o passata di pulizia che lo vede terminato.

## Correlati

- [Console Web](/it/docs/web-console), il client browser costruito su questo modello
- [Archivio di Configurazione](/it/docs/config-storage), l'archivio zero-knowledge che protegge la CEK
