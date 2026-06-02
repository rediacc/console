---
title: "Monitoraggio"
description: "Monitora la salute della macchina, i container, i servizi, i repository ed esegui diagnostiche. È possibile controllare tutto dal tuo laptop senza bisogno di SSH."
category: "Guides"
order: 9
language: it
sourceHash: "1d0af1a74a12d49e"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Monitoraggio

Rediacc fornisce comandi di monitoraggio integrati per ispezionare la salute della macchina, i container in esecuzione, i servizi, lo stato dei repository e le diagnostiche di sistema.

## Salute della Macchina

Ottieni un report sanitario completo di una macchina:

```bash
rdc machine health --name server-1
```

Questo riporta:
- **Sistema**: uptime, utilizzo del disco, utilizzo del datastore
- **Container**: conteggi in esecuzione, sani, non sani
- **Archiviazione**: stato SMART della salute
- **Problemi**: problemi identificati

Usa `--output json` per un output leggibile dalla macchina.

## Elenco dei Container

Visualizza tutti i container in esecuzione su tutti i repository di una macchina:

```bash
rdc machine containers --name server-1
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
rdc machine services --name server-1
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
rdc machine repos --name server-1
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
rdc machine query --name server-1 --storage-health
```

| Colonna | Descrizione |
|--------|-------------|
| Size | Dimensione del file immagine LUKS (come appare il repository) |
| Unique | Dati unici effettivi posseduti solo da questo repository |
| Shared | Blocchi di dati riutilizzati tra repository tramite reflink BTRFS (copie gratuite) |
| Divergence | Percentuale dell'immagine unica in questo repository rispetto a quella condivisa (piu' alta = piu' recuperabile se eliminato) |
| Extents | Numero di estensioni di file nell'immagine copy-on-write (piu' alto = piu' frammentato) |
| Frag | Livello di frammentazione: basso, moderato o alto (solo informativo) |

Il riepilogo mostra i risparmi totali dai reflink BTRFS:

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- La **dimensione virtuale** è la somma di tutte le dimensioni delle immagini dei repository. È come appaiono i repository, ma conta due volte i blocchi condivisi tramite reflink.
- I **dati unici** sono l'archiviazione effettiva consumata dai dati del repository che esistono in un solo repository. Questo è ciò che libereresti eliminando un repository.
- **Shared** è la quantità di dati riutilizzati tra repository tramite reflink BTRFS. Il fork di un repository crea copie tramite reflink che condividono blocchi finché uno dei due lati non scrive nuovi dati, a quel punto i blocchi divergono.
- **Efficiency** è la percentuale di dati riutilizzati tramite reflink. Maggiore è meglio. Una macchina con molti fork dallo stesso genitore mostrerà un'efficienza vicina al 100%.

La colonna Frag e' informativa. Conta le estensioni del file immagine copy-on-write, non i file che la tua applicazione legge al suo interno, quindi risulta alta sotto normali carichi di lavoro con scritture casuali (database, layer container) e non predice le prestazioni di lettura su archiviazione con supporto SSD. Rediacc non offre deliberatamente un comando di deframmentazione: `btrfs filesystem defragment` rimuove la condivisione tramite reflink di fork e snapshot, il che su un pool quasi pieno puo' aumentare drasticamente l'utilizzo dello spazio mentre i benchmark non mostrano alcun guadagno misurabile in lettura. Per le misurazioni complete e il ragionamento, vedi [Il Tuo Indice di Frammentazione Sembra Terrificante. Ho Misurato Quanto Costa.](/it/blog/i-benchmarked-btrfs-fragmentation).

La scansione viene eseguita in parallelo e richiede 5-15 secondi a seconda del numero e della dimensione dei repository. Quando `--storage-health` non è specificato, dopo l'output della query appare un suggerimento di una riga come promemoria.

## Scrub BTRFS

Rediacc pianifica automaticamente uno scrub BTRFS settimanale su ogni macchina. Lo scrub legge ogni blocco di dati nel datastore, verifica i checksum e segnala eventuali corruzioni. Questo rileva la corruzione silente dei dati (bitrot) prima che si propaghi ai backup e ai fork.

Lo scrub viene eseguito ogni domenica alle 02:00 ora locale (fuso orario della macchina) con un ritardo casuale fino a 1 ora. Viene eseguito alla priorità I/O più bassa (`ionice idle`, `nice 19`) in modo da non interferire con i servizi in esecuzione. Sulle macchine con SSD, aspetta circa 8 minuti per 100 GB di datastore.

Il timer dello scrub viene installato automaticamente al primo avvio del daemon dopo un aggiornamento di renet. Quando la politica di scrub cambia in una futura versione di renet, si aggiorna da sola al prossimo avvio del daemon senza alcuna azione da parte dell'utente.

### Stato dello Scrub

Il risultato dell'ultimo scrub viene salvato fuori dal volume BTRFS (in `/var/lib/rediacc/scrub-last-result.json`) in modo che rimanga leggibile anche se il volume ha problemi. L'output di `rdc machine query --system` include un campo `scrub_status`:

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
rdc term connect -m server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

Il risultato viene salvato nello stesso file JSON ed è immediatamente visibile nel successivo `rdc machine query --system`.

## Stato del Vault

Ottieni una panoramica completa di una macchina incluse le informazioni di deployment:

```bash
rdc machine vault-status --name server-1
```

Questo fornisce:
- Hostname e uptime
- Utilizzo di memoria, disco e datastore
- Totale repository, conteggio montati, conteggio Docker in esecuzione
- Informazioni dettagliate per repository

Usa `--output json` per un output leggibile dalla macchina.

## Test della Connessione

> **Solo adapter cloud.** Con l'adapter locale, usa `rdc term connect -m server-1 -c "hostname"` per verificare la connettività.

Verifica la connettività SSH a una macchina:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Riporta:
- Stato della connessione (successo/fallito)
- Metodo di autenticazione utilizzato
- Configurazione della chiave SSH
- Stato del deployment della chiave pubblica
- Voce known hosts

Opzioni:
- `--port <number>`, Porta SSH (predefinito: 22)
- `--save -m server-1`, Salva la chiave host verificata nella configurazione della macchina

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
