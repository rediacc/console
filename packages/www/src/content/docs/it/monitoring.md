---
title: "Monitoraggio"
description: "Monitora la salute della macchina, i container, i servizi, i repository ed esegui diagnostiche."
category: "Guides"
tags:
  - operations
subcategory: operations
order: 9
language: it
sourceHash: "6e4968522e118c98"
sourceCommit: "9b8aa220de6eb4f7c7b7783456af6871202c8305"
---

# Monitoraggio

Rediacc fornisce comandi di monitoraggio per la salute della macchina, i container in esecuzione, i servizi, lo stato dei repository e le diagnostiche di sistema.

## Salute della Macchina

Ottieni un report sanitario completo di una macchina:

```bash
rdc machine health server-1
```

Questo riporta:
- **Sistema**: uptime, memoria (avviso sopra l'80%, errore sopra il 90%), utilizzo del disco e del datastore (avviso sopra l'85%, errore sopra il 95%)
- **Container**: conteggi in esecuzione, sani, non sani; un container in un ciclo `Restarting` è critico
- **Servizi**: unità systemd fallite (un errore) e unità che si riavviano di continuo (critico)
- **Archiviazione**: stato di salute SMART (un disco in avaria è critico) e temperatura del disco
- **Repository**: repository con avvio automatico che non sono montati e utilizzo del filesystem di ogni repository (avviso sopra l'85%, errore sopra il 95%)
- **Backup**: repository senza backup da oltre 10 giorni, in ritardo rispetto alla pianificazione o alla destinazione, oppure la cui ultima verifica è fallita
- **Licenze**: licenze dei repository scadute, mancanti, non corrispondenti o non valide, e licenze da rinnovare
- **Processi renet**: demoni che eseguono ancora un binario renet sostituito
- **Salute dei repository**: il risultato di `health()` di ogni repository montato (vedi sotto)
- **Certificati**: certificati del proxy prossimi alla scadenza e CNAME di sfida ACME condivisi
- **Problemi**: problemi identificati

Il codice di uscita è il verdetto: `0` sano, `1` avviso, `2` errore, `3` critico (un disco in avaria, oppure un container o un servizio in un ciclo di riavvii). Usa `--output json` per un output leggibile dalla macchina; contiene `repo_health` (un report per repository) e `findings`, ciascuno con un codice, una gravità (`info`, `warning`, `error` o `critical`), un soggetto, un dettaglio e, dove esiste una correzione, `fix` (vedi [Riparazione](#repair)).

## Salute del repository

Un Rediaccfile può definire una funzione `health()` che controlla i servizi del repository stesso ([Servizi](/it/docs/services)): uscita `0` ok, `1` avviso, `2` errore. Eseguila per un repository:

```bash
rdc repo health my-app@server-1
```

Il comando termina con il livello peggiore tra i Rediaccfile del repository. Un repository in cui nessun Rediaccfile definisce `health()` stampa **nessun controllo** e termina con `0`; non viene mai segnalato come sano. Un `health()` che va in timeout, viene terminato o esce con qualsiasi altro codice è un errore, così come l'impossibilità di raggiungere la macchina (uscita `2`).

`rdc machine health` esegue il `health()` di ogni repository montato in una sola chiamata e riporta il livello peggiore nel proprio codice di uscita, con un riscontro per repository come avviso (`repo.health.warning`) o errore (`repo.health.error`). I repository senza controllo vengono elencati, non segnalati. Quando il renet della macchina è precedente ai controlli di salute dei repository, il risultato è un avviso, `renet.repo-health.unsupported`, finché `rdc machine setup` non lo aggiorna.

## Scadenza dei certificati e sfide ACME

`rdc machine health` legge i certificati ACME del proxy e segnala `cert.expiry.near` per ciascuno con meno di 21 giorni alla scadenza (un avviso) o meno di 7 giorni (un errore). Il proxy rinnova con 30 giorni di anticipo, quindi un certificato sotto i 21 giorni significa che il suo rinnovo fallisce da almeno nove giorni.

Segnala anche `acme.challenge.cname-shared` quando il record `_acme-challenge.<name>` del nome di un certificato segue un CNAME verso un nome che non è a sua volta un nome `_acme-challenge.`, oppure quando due nomi terminano sullo stesso nome. Un record wildcard che è un CNAME produce questa forma: ogni sfida finisce su un solo nome e i rinnovi collidono. Una delega voluta (per esempio `_acme-challenge.mail.example.com` che punta a `_acme-challenge.mail.example.io`) non viene segnalata; elenca qualsiasi altra delega prevista in `ACME_DELEGATED_NAMES` (un elenco separato da virgole di nomi di certificato) nel `config.env` del proxy. Un nome la cui catena di sfida non ha potuto essere risolta (errore DNS o timeout) viene segnalato come `acme.challenge.unknown`, un avviso, perché il controllo non è stato eseguito per quel nome.

## Riparazione

Ogni riscontro porta un codice e, dove esiste una correzione sicura, un `fix` con `action`, una `class` di sicurezza e `window_only`. `rdc machine health` resta in sola lettura; `rdc machine repair` è il comando che agisce:

```bash
rdc machine repair server-1 --dry-run     # list what would run
rdc machine repair server-1               # run the auto-safe fixes, then re-check
rdc machine repair server-1 --code cert.expiry.near
```

| Classe | Significato |
|---|---|
| `auto-safe` | Viene eseguita per impostazione predefinita: riavviare un container o Traefik, fare trim e pulizia, scrivere l'ancora ACME |
| `auto-with-backup` | Viene eseguita solo con `--with-backup`, dopo uno snapshot riuscito del repository; uno snapshot fallito annulla la correzione |
| `operator-only` | Non viene mai eseguita. Il comando stampa il comando esatto da lanciare a mano. Tutto ciò che cancella dati con nome o spende denaro rientra qui |

`window_only` è una condizione aggiuntiva alla classe: la correzione viene eseguita solo dentro la finestra di manutenzione della macchina, `HH:MM-HH:MM` in UTC (può attraversare la mezzanotte). Una macchina senza finestra non esegue mai queste correzioni da sola; `--window-override` le esegue a mano. Imposta o rimuovi la finestra con:

```bash
rdc machine repair server-1 --set-window 00:00-03:00
rdc machine repair server-1 --set-window off
```

Ogni correzione verifica prima che il suo riscontro sia ancora presente, quindi una seconda esecuzione non ha nulla da fare. Le correzioni che agiscono sulla stessa cosa vengono eseguite una volta (un solo riavvio di Traefik copre tutti i certificati). Ogni correzione viene registrata nel journal della macchina con il tag `rediacc-repair` e nel JSON `actions` (`code`, `subject`, `action`, `class`, `result`, `before`, `after`), e l'esecuzione termina con un controllo completo. Il codice di uscita è `0` quando non resta nulla, `1` quando restano avvisi o elementi operator-only, e `2` quando resta un errore o una correzione è fallita.

| Riscontro | Correzione | Classe |
|---|---|---|
| `datastore.usage.high`, `repo.disk.high` | Trim, poi pulizia di container fermi, volumi anonimi orfani e immagini inutilizzate | auto-safe |
| `container.unhealthy`, `container.restart-loop` | Riavviare il container | auto-safe |
| `renet.binary.replaced` | Riavviare i supervisori dei repository interessati (`rdc machine restart-services --include-docker`, limitato a quelli) | auto-safe, solo in finestra |
| `cert.expiry.near` | Riavviare Traefik perché ritenti il rinnovo | auto-safe |
| `acme.challenge.cname-shared` | Scrivere l'ancora ACME (sotto) | auto-safe |
| `repo.health.warning`, `repo.health.error` | Eseguire il `repair()` del repository ([Servizi](/it/docs/services)) | la classe dichiarata dal Rediaccfile |
| `repo.unmounted`, `service.failed`, `service.restart-loop`, `backup.*`, `license.*`, `renet.repo-health.unsupported` | Stampato come comando da eseguire | operator-only |

I riscontri senza correzione (guasti SMART, temperatura, memoria, disco di sistema, una verifica fallita) vengono segnalati e lasciati all'operatore.

La pulizia non tocca mai l'hub: i container con l'etichetta `rediacc.hub.*` e i volumi con l'etichetta `rediacc.hub.user` o di nome `rediacc-hub-home-*` sono esclusi, così la home di un utente dell'hub sopravvive a ogni recupero di spazio. Un residuo che trim e pulizia non riescono a liberare (volumi con nome, grandi dati applicativi) resta una decisione dell'operatore.

### Riparazione del repository

```bash
rdc repo repair my-app@server-1 --dry-run
rdc repo repair my-app@server-1
```

`rdc repo repair` esegue le funzioni `repair()` del repository con le stesse classi: `auto-safe` viene eseguita, `auto-with-backup` richiede `--with-backup`, e un `repair()` non dichiarato (`operator-only`) viene eseguito solo dopo aver risposto alla conferma o con `--yes`. Poi `health()` viene eseguito di nuovo e il codice di uscita segue il livello in cui termina: `0` ok o nessun controllo, `1` avviso, `2` errore o un `repair()` fallito.

### L'ancora ACME

Un record DNS wildcard che è un CNAME fa sì che ogni nome `_acme-challenge.<host>` lo segua, quindi tutte le sfide finiscono su un solo nome e i rinnovi collidono (`acme.challenge.cname-shared`). La correzione scrive un record TXT con il valore `rediacc-acme-anchor` su ogni `_acme-challenge.<name>` in collisione, tramite il token Cloudflare del proxy, poi riavvia Traefik. Un record esplicito sottrae il nome alla portata del wildcard, così la sfida arriva dove deve. La correzione aggiunge soltanto record, e un'ancora esistente viene lasciata com'è.

I nomi elencati in `ACME_DELEGATED_NAMES` (un elenco separato da virgole di nomi di certificato nel `config.env` del proxy) sono deleghe volute: non vengono mai ancorati né segnalati. Quando il proxy non ha un token Cloudflare utilizzabile, la correzione ripiega su `LEGO_DISABLE_CNAME_SUPPORT=true` in `config.env`, ma solo se non è dichiarato alcun nome delegato, perché quella variabile impedisce di seguire i CNAME per qualsiasi nome; con una delega dichiarata, il riscontro resta operator-only. La stessa correzione viene eseguita a ogni installazione del proxy (`rdc machine infra push`) e da sola con `renet proxy acme-fix` sulla macchina.

## Elenco dei Container

Visualizza tutti i container in esecuzione su tutti i repository di una macchina:

```bash
rdc machine status server-1 --containers
```

| Colonna | Descrizione |
|--------|-------------|
| Name | Nome del container |
| Status | Uptime o motivo di uscita |
| State | In esecuzione, uscito, ecc. |
| Health | Sano, non sano, nessuno |
| CPU | Percentuale di utilizzo CPU |
| Memory | Utilizzo della memoria / limite |
| Repository | Quale repository possiede il container |

Opzioni:
- `--health-check`, Esegui controlli attivi della salute sui container
- `--output json`, Output JSON leggibile dalla macchina

L'output JSON include i dettagli completi del container (`labels`, `port_mappings`, `image`, `id`) più `repository` (nome risolto), `repository_guid` (GUID originale), `domain` e `autoRoute`.

## Elenco dei Servizi

Visualizza i servizi systemd relativi a Rediacc su una macchina:

```bash
rdc machine status server-1 --services
```

| Colonna | Descrizione |
|--------|-------------|
| Name | Nome del servizio |
| State | Attivo, inattivo, fallito |
| Sub-state | In esecuzione, morto, ecc. |
| Restarts | Conteggio riavvii |
| Memory | Utilizzo della memoria del servizio |
| Repository | Repository associato |

Opzioni:
- `--stability-check`, Segnala i servizi instabili (falliti, >3 riavvii, auto-riavvio)
- `--output json`, Output JSON leggibile dalla macchina

L'output JSON include i dettagli completi del servizio con `repository` (nome risolto) e `repository_guid` (GUID originale).

## Elenco dei Repository

Visualizza i repository su una macchina con statistiche dettagliate:

```bash
rdc machine status server-1 --repositories
```

| Colonna | Descrizione |
|--------|-------------|
| Name | Nome del repository |
| Size | Dimensione dell'immagine disco |
| Mount | Montato o smontato |
| Docker | Daemon Docker in esecuzione o fermato |
| Containers | Conteggio dei container |
| Disk Usage | Utilizzo effettivo del disco nel repository |
| Modified | Ora dell'ultima modifica |

Opzioni:
- `--search <text>`, Filtra per nome o percorso di mount
- `--output json`, Output JSON leggibile dalla macchina

L'output JSON include `name` (risolto) e `guid` (GUID originale), e annida i `containers` di ogni repository (con `domain`, `autoRoute`, `repository`/`repository_guid`) e gli array `services`.

## Salute dell'Archiviazione

Ispeziona la frammentazione BTRFS e la condivisione tramite reflink su tutti i repository di una macchina:

```bash
rdc machine status server-1 --storage-health
```

| Colonna | Descrizione |
|--------|-------------|
| Quota | La dimensione massima del repository (il suo tetto di crescita, impostato alla creazione o tramite resize/auto-grow) |
| Allocated | Quanto l'immagine sparsa occupa effettivamente nel pool in questo momento |
| Unique | Dati unici effettivi posseduti solo da questo repository |
| Shared | Blocchi di dati riutilizzati tra repository tramite reflink BTRFS (copie gratuite) |
| Reclaimable | Il divario allocato-vs-usato che [`repo trim`](/it/docs/repositories#reclaim-space-trim) può restituire al pool. Mostra `-` per i repository smontati |
| Discards | Se il volume cifrato propaga i discard (`on` per qualsiasi repository montato da una versione corrente) |
| Divergence | Percentuale dell'immagine unica in questo repository rispetto a quella condivisa (più alta significa più reclaimable se eliminato) |
| Frag | Estensioni per GB nell'immagine copy-on-write (solo informativo) |

Quota e allocazione sono numeri diversi per design: un repository con una quota di 20 GB che memorizza 6 GB di dati costa al pool solo quanto ha allocato. Il pool può quindi promettere una quota totale superiore a quella fisicamente disponibile, e la colonna Reclaimable mostra quanta parte dell'allocazione di ciascun repository non è più utilizzata e può essere recuperata con il trim.

Al di sotto della tabella, un riepilogo del pool riporta il livello di riempimento del datastore e quanto spazio gli snapshot di backup stanno bloccando:

```
Pool: 265.4 GB used, 95.2 GB free (73.6% full)
Backup snapshots pin 2.1 GB (1 active, 0 stale; stale ones are removed by 'rdc machine prune')
```

Mentre un backup è in esecuzione, il suo snapshot continua a fare riferimento a ogni blocco che condivide con i repository attivi: eliminazioni e trim liberano meno spazio nel pool finché quel ciclo di backup non termina e lo snapshot viene eliminato. Gli snapshot obsoleti di backup interrotti vengono rimossi automaticamente dal gestore dello storage entro pochi minuti.

Il riepilogo mostra i risparmi totali dai reflink BTRFS:

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- La **dimensione virtuale** è la somma di tutte le dimensioni delle immagini dei repository. È come appaiono i repository, ma conta due volte i blocchi condivisi tramite reflink.
- I **dati unici** sono l'archiviazione effettiva consumata dai dati del repository che esistono in un solo repository. Questo è ciò che libereresti eliminando un repository.
- **Shared** è la quantità di dati riutilizzati tra repository tramite reflink BTRFS. Il fork di un repository crea copie tramite reflink che condividono blocchi finché uno dei due lati non scrive nuovi dati, a quel punto i blocchi divergono.
- **Efficiency** è la percentuale di dati riutilizzati tramite reflink. Maggiore è meglio. Una macchina con molti fork dallo stesso genitore mostrerà un'efficienza vicina al 100%.

La colonna Frag è informativa. Conta le estensioni del file immagine copy-on-write, non i file che la tua applicazione legge al suo interno, quindi risulta alta sotto normali carichi di lavoro con scritture casuali (database, layer container) e non predice le prestazioni di lettura su archiviazione con supporto SSD. Rediacc non offre deliberatamente un comando di deframmentazione: `btrfs filesystem defragment` rimuove la condivisione tramite reflink di fork e snapshot, il che su un pool quasi pieno può aumentare drasticamente l'utilizzo dello spazio mentre i benchmark non mostrano alcun guadagno misurabile in lettura. Per le misurazioni complete e il ragionamento, vedi [Il Tuo Indice di Frammentazione Sembra Terrificante. Ho Misurato Quanto Costa.](/it/blog/i-benchmarked-btrfs-fragmentation).

La scansione viene eseguita in parallelo e richiede 5-15 secondi a seconda del numero e della dimensione dei repository. Quando `--storage-health` non è specificato, dopo l'output della query appare un suggerimento di una riga come promemoria.

## Scrub BTRFS

Rediacc pianifica automaticamente uno scrub BTRFS settimanale su ogni macchina. Lo scrub legge ogni blocco di dati nel datastore, verifica i checksum e segnala eventuali corruzioni. Questo rileva la corruzione silente dei dati (bitrot) prima che si propaghi ai backup e ai fork.

Lo scrub viene eseguito ogni domenica alle 02:00 ora locale (fuso orario della macchina) con un ritardo casuale fino a 1 ora. Viene eseguito alla priorità I/O più bassa (`ionice idle`, `nice 19`) in modo da non interferire con i servizi in esecuzione. Sulle macchine con SSD, aspetta circa 8 minuti per 100 GB di datastore.

Il timer dello scrub viene installato automaticamente al primo avvio del daemon dopo un aggiornamento di renet. Quando la politica di scrub cambia in una futura versione di renet, si aggiorna da sola al prossimo avvio del daemon senza alcuna azione da parte dell'utente.

### Stato dello Scrub

Il risultato dell'ultimo scrub viene salvato fuori dal volume BTRFS (in `/var/lib/rediacc/scrub-last-result.json`) in modo che rimanga leggibile anche se il volume ha problemi. L'output di `rdc machine status --system` include un campo `scrub_status`:

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| Stato | Significato |
|--------|---------|
| `ok` | L'ultimo scrub è completato senza errori |
| `never_run` | Lo scrub non è ancora stato eseguito (il timer è stato appena installato) |
| `overdue` | L'ultimo scrub è stato eseguito più di 14 giorni fa |
| `errors_found` | Lo scrub ha trovato mancate corrispondenze di checksum (controlla i conteggi `total_errors` e `uncorrectable`) |
| `failed` | Il processo di scrub è uscito con un codice non zero |

Se `uncorrectable` è maggiore di zero, i blocchi interessati non possono essere riparati automaticamente (BTRFS su disco singolo non ha copie ridondanti). Ripristina il repository interessato dal backup più recente.

### Scrub Manuale

Per eseguire uno scrub immediatamente (ad esempio dopo un'interruzione di corrente o una migrazione del disco):

```bash
rdc term connect server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

Il risultato viene salvato nello stesso file JSON ed è immediatamente visibile nel successivo `rdc machine status --system`.

## Panoramica della Macchina

Ottieni una panoramica completa di una macchina incluse le informazioni di deployment:

```bash
rdc machine status server-1
```

Questo fornisce:
- Hostname e uptime
- Utilizzo di memoria, disco e datastore
- Totale repository, conteggio montati, conteggio dei repository il cui daemon Docker risponde
- Informazioni dettagliate per repository

Usa `--output json` per un output leggibile dalla macchina.

## Test della Connessione

Verifica la connettività SSH a una macchina:

```bash
rdc term connect server-1 -c "hostname"
```

Il comando stampa l'hostname remoto in caso di successo e un errore di connessione
in caso contrario, il che verifica DNS, la porta SSH e l'autenticazione con chiave
in un solo passaggio.

## Diagnostiche (doctor)

Esegui un controllo diagnostico completo dell'ambiente Rediacc:

```bash
rdc doctor
```

| Categoria | Controlli |
|----------|--------|
| **Ambiente** | Versione Node.js, versione CLI, modalità SEA, installazione Go, disponibilità Docker |
| **Renet** | Posizione del binario, versione, CRIU, rsync, asset embedded SEA |
| **Configurazione** | Configurazione attiva, adapter, macchine, chiave SSH |
| **Virtualizzazione** | Verifica se il tuo sistema può eseguire macchine virtuali locali (`rdc ops`) |

Ogni controllo riporta **OK**, **Avviso** o **Errore**. Usalo come primo passo nella risoluzione di qualsiasi problema.

Codici di uscita: `0` = tutto superato, `1` = avvisi, `2` = errori.

## Verifica della disponibilità dei servizi

Durante `repo up`, renet attende che i servizi HTTP accettino connessioni prima di dichiararli pronti. L'attesa tiene conto dei health check:

- I container che Docker segnala come **sani** vengono considerati pronti immediatamente, senza alcuna sonda TCP.
- I container ancora nel `start_period` del health check generano una nota informativa, non un avviso; il proxy continua a riprovare finché non si mettono in ascolto.
- I servizi Compose privi di container in esecuzione (ad esempio perché associati a un profilo inattivo) vengono saltati.
- Tutto il resto viene sondato via TCP per un massimo di 15 secondi (modifica questo valore impostando `REDIACC_READINESS_TIMEOUT`, in secondi).

Definire un [Docker health check](https://docs.docker.com/reference/dockerfile/#healthcheck) sui servizi a avvio lento fornisce a renet un segnale di disponibilità autorevole ed elimina il rumore delle sonde dall'output del deploy.
