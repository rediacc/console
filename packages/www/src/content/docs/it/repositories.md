---
title: "Repository"
description: "Crea, gestisci e opera repository cifrati con LUKS su macchine remote."
category: "Guides"
order: 4
language: it
sourceHash: "0f08c5b75c3588cc"
sourceCommit: "3fb35b9a33c7e8ec6753ecd56231f2018e8f4803"
---

# Repository

Un **repository** è un'immagine di disco cifrata LUKS su un server remoto. Quando montato, fornisce:
- Un filesystem isolato per i tuoi dati applicativi
- Un daemon Docker dedicato (separato da quello dell'host)
- IP loopback unici per ogni servizio all'interno di una subnet /26

## Crea un Repository

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| Opzione | Obbligatorio | Descrizione |
|---------|----------|-------------|
| `-m, --machine <name>` | Sì | La macchina target dove verrà creato il repository |
| `--size <size>` | Sì | Dimensione dell'immagine di disco cifrata (ad es. `5G`, `10G`, `50G`) |
| `--skip-router-restart` | No | Salta il riavvio del route server dopo l'operazione |

L'output mostrerà tre valori generati automaticamente:

- **Repository GUID** -- Un UUID che identifica l'immagine di disco cifrata sul server.
- **Credential** -- Una passphrase casuale usata per cifrare/decifrare il volume LUKS.
- **Network ID** -- Un numero intero (iniziando da 2816, incrementato di 64) che determina la subnet IP per i servizi di questo repository.

> **Memorizza la credential in modo sicuro.** È la chiave di cifratura per il tuo repository. Se persa, i dati non possono essere recuperati. La credential è memorizzata nel tuo `config.json` locale ma non è memorizzata sul server.

## Monta e Smonta

Il montaggio decifra e rende il filesystem del repository accessibile. Lo smontaggio chiude il volume cifrato.

```bash
rdc repo mount --name my-app -m server-1  # Decifra e monta
rdc repo unmount --name my-app -m server-1  # Smonta e ricifra
```

| Opzione | Descrizione |
|--------|-------------|
| `--checkpoint` | Crea un checkpoint CRIU prima di montare/smontare (per container con etichetta `rediacc.checkpoint=true`) |
| `--skip-router-restart` | Salta il riavvio del route server dopo l'operazione |

## Controlla Stato

```bash
rdc repo status --name my-app -m server-1
```

## Elenca Repository

```bash
rdc repo list -m server-1
```

### Colonna Type e lo state mirror

La tabella di output include una colonna `Type` con tre valori:

- **`grand`**. Un repository di primo livello registrato nel tuo config CLI locale senza un genitore. È il caso base.
- **`fork`**. Un fork copy-on-write di un altro repository. Identificato tramite `grandGuid` nel config locale **oppure** tramite lo state mirror `.interim/state` di renet sulla macchina. Entrambe le fonti sono autorevoli; dovrebbero essere d'accordo una volta che lo specchio è popolato.
- **`unknown`**. Nessuno dei due segnali può classificare il repository. Più spesso un fork legacy pre-mirror (creato prima che il codice dello specchio fosse spedito e mai rimontato da allora), o un `grand` stale il cui inserimento nel config locale è stato cancellato per errore. La CLI si rifiuta di indovinare; l'operatore dovrebbe eseguire [il backfill dello specchio](/it/docs/pruning#migration-state-mirror-backfill) o rimuovere la directory se è veramente orfana.

Lo specchio `.interim/state/<guid>/.rediacc.json` è un piccolo file sidecar scritto **al di fuori** del volume cifrato LUKS, quindi gli strumenti di backup e `repo list` possono leggere la lineage del fork senza sbloccare ogni immagine. Ha la stessa forma del `.rediacc.json` in-volume (`is_fork`, `grand_guid`, `name`, ecc.) ed è aggiornato su ogni `Repository.SaveState`. Cioè ogni montaggio e ogni mutazione di stato. È la fonte di verità per il rilevamento del fork nei backup programmati: un fork smontato con uno specchio che dice `is_fork: true` è correttamente saltato dagli upload `cold` e `hot`.

Per la pulizia ordinaria delle voci sconosciute, vedi [`rdc machine prune --prune-unknown`](/it/docs/pruning#phase-3---prune-unknown-surgical).

## Ridimensiona

Imposta il repository a una dimensione esatta o espandi di una quantità data:

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Imposta a dimensione esatta
rdc repo expand --name my-app -m server-1 --size 5G  # Aggiungi 5G alla dimensione attuale
```

> Il repository deve essere smontato prima di ridimensionare. `repo expand` funziona online. Il ridimensionamento modifica la dimensione massima del repository; per restituire al pool i blocchi liberati senza modificare il massimo, usa invece [`repo trim`](#recupera-spazio-trim).

## Recupera Spazio (trim)

Eliminare file all'interno di un repository libera spazio per quel repository, e `repo trim` restituisce quei blocchi liberati al pool condiviso del datastore. Viene eseguito online senza alcun downtime:

```bash
rdc repo trim -m server-1                       # Trim every mounted repository plus the datastore
rdc repo trim -m server-1 --name my-app          # Trim one repository
rdc repo trim -m server-1 --report-only          # Show reclaimable space without trimming
rdc repo trim -m server-1 --docker               # Also clear stopped containers, dangling images, and build cache first
```

Come funziona: le immagini di repository sono file sparsi e il volume cifrato propaga i discard. Un trim dice al filesystem all'interno del repository di rilasciare ogni blocco inutilizzato, il che perfora l'immagine di supporto e riduce immediatamente l'utilizzo del pool.

Note:

- Il trim del filesystem viene saltato e segnalato per i repository con un backup attivo, perché lo snapshot del backup fa ancora riferimento ai blocchi, quindi perforare i fori non libererebbe spazio nel pool. Il recupero `--docker` non è interessato e viene eseguito comunque (vedi sotto).
- Eseguire il trim due volte di seguito riporta 0 byte la seconda volta. Il filesystem ricorda quali gruppi di blocchi sono già stati elaborati; questo è il comportamento atteso, non un errore.
- `--docker` non rimuove mai le immagini con tag, solo quelle dangling, i container fermi e la build cache. Aggiungi `--docker-volumes` per rimuovere anche i volumi inutilizzati (questo elimina dati; solo CLI). A differenza del trim del filesystem, il recupero `--docker` viene eseguito anche mentre un backup è in corso, così puoi svuotare una build cache bloccata senza attendere la finestra di backup.

## Policy di Dimensione Automatica

Invece di ridimensionare manualmente, lascia che la macchina gestisca le dimensioni dei repository. Una policy abilita l'auto-grow online (la dimensione massima del repository aumenta quando si riempie) e i trim pianificati. La macchina applica le policy ogni pochi minuti tramite il timer systemd `rediacc-storage-maintain`.

```bash
# Machine-wide default: trim every repository daily
rdc repo policy set -m server-1 --auto-trim true

# Per-repository: grow my-app automatically, up to a hard ceiling
rdc repo policy set -m server-1 --name my-app --auto-grow true --max-quota 50G

# Inspect the stored and effective policy
rdc repo policy get -m server-1 --name my-app
```

Campi della policy:

| Campo | Significato | Predefinito |
|---|---|---|
| `--auto-grow` | Espandi il repository online quando il suo filesystem supera la soglia | disattivo |
| `--max-quota` | Limite massimo per l'auto-grow. Obbligatorio: impostarlo è il tuo consenso esplicito al sovra-provisioning del pool | nessuno |
| `--grow-threshold` | Percentuale di filesystem usato che attiva un'espansione | 85 |
| `--grow-step` | Quanto aggiungere per ogni espansione: valore assoluto (`10G`) o percentuale della dimensione corrente (`20%`) | 20% |
| `--auto-trim` | Esegui trim pianificati | disattivo |
| `--trim-interval` | Ore minime tra trim automatici | 24 |

Protezioni: l'auto-grow si rifiuta di agire quando lo spazio libero del pool scende sotto una riserva (10 GB o il 5% del pool, il maggiore dei due), attende almeno 30 minuti tra le espansioni dello stesso repository e non supera mai `--max-quota`. Non esiste un restringimento automatico: ridurre la dimensione massima di un repository rimane un'operazione manuale, offline, tramite [`repo resize`](#ridimensiona).

Le impostazioni per-repository hanno la precedenza sul default a livello di macchina. Chiamate successive a `policy set` modificano solo i flag che passi.

## Fork

Crea una copia di un repository esistente al suo stato attuale:

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

I fork usano il modello name:tag: il fork risultante si chiama `my-app:staging`. Questo crea una nuova copia cifrata con il suo proprio GUID e Network ID, mentre condivide il nome del genitore. Il fork condivide la stessa credential LUKS del genitore.

> I fork condividono i dati del genitore tramite reflink BTRFS, incluse eventuali credential memorizzate su disco. Vedi [Cosa Rediacc non isola](/it/docs/ai-agents-safety#what-rediacc-does-not-isolate) per le implicazioni quando quelle credential autorizzano servizi esterni come Stripe, AWS o Railway. Per tenere le credential di deploy-time fuori dalla portata del fork, usa [per-repo secrets](#secrets) al posto di incorporare valori nei file `.env` all'interno del repository.

Alla creazione del fork, `repo fork` scrive il [sidecar dello state mirror](#type-column-and-the-state-mirror) a `<datastore>/.interim/state/<fork-guid>/.rediacc.json` immediatamente. Senza sbloccare il volume. Quindi il nuovo fork è correttamente identificato come `is_fork: true` dal momento della creazione. Questo permette ai backup programmati di saltarlo (i fork sono esclusi dalla pipeline di upload per impostazione predefinita) anche se non è mai stato montato. Quando si fa fork di un fork, `grand_guid` si concatena correttamente: lo specchio del nuovo fork punta al GUID del genitore originale, non al fork intermedio.

### Fork e avvio in un solo passo

`--up` esegue il fork, il montaggio e l'avvio dei servizi in un'unica operazione remota. Aggiungi `--detach` per riprendere il terminale non appena i container sono avviati: i health check terminano in background e il proxy riprova finché ogni servizio non si mette in ascolto:

```bash
rdc repo fork --parent my-app --tag staging -m server-1 --up
rdc repo fork --parent my-app --tag scratch -m server-1 --up --detach
```

Nei nostri test, un repository da 128 GB ha completato il fork e raggiunto i servizi in esecuzione in circa 57 secondi, e circa 31 secondi con `--detach`. Le esecuzioni in modalità distaccata stampano un suggerimento per verificare l'avanzamento: `rdc machine query --containers --name <machine>`.

### Distribuzione del tempo

Le esecuzioni che durano più di qualche secondo si concludono con un riepilogo dei tempi: un dettaglio passo per passo, un waterfall che mostra cosa è andato in parallelo, e una riga di attribuzione che separa la pipeline Rediacc dall'avvio dei tuoi servizi:

```
  Rediacc pipeline 19.2s (61%) · service startup 12.3s (39%)
```

L'avvio dei servizi corrisponde al boot dei container, inclusi immagini, init e health check, secondo quanto definito nel Rediaccfile del repository, e varia quindi da applicazione ad applicazione. I grafici vengono visualizzati sui terminali interattivi; imposta `RDC_TIMING_CHART=1` per forzarne la visualizzazione anche su output reindirizzato.

## Versionamento simile a git

I fork possono fungere da commit git. `rdc repo commit` congela un fork di lavoro in un commit immutabile e byte-stabile; `rdc repo branch` nomina una linea di storia; `rdc repo checkout` clona tramite reflink un commit in un fork scrivibile; `rdc repo log` percorre la catena dei genitori; e `rdc repo merge` combina due linee senza mutare un repository live in place. `rdc repo fork --immutable` produce una base equivalente a un commit in un unico passo.

```bash
rdc repo commit --name my-app:work --message "schema migration applied" -m server-1
rdc repo branch --branch staging --name my-app:work
rdc repo checkout --ref staging --from my-app:work --tag staging-copy -m server-1
```

Vedi il [riferimento al branching simile a git](/it/docs/repo-branching) per il set completo di comandi, opzioni ed esempi pratici.

## Secret

I secret per-repo sono credential di deploy-time iniettate nei container senza essere scritte nell'immagine del repository cifrata. Vengono mantenuti su un piano separato dai dati del repository, quindi `rdc repo fork` non li propaga. Un fork inizia con una mappa di secret vuota e i suoi container si avviano identificandosi come un principal esterno diverso dal genitore.

> Vuoi una procedura passo-passo? Vedi il [tutorial Gestione dei Secret](/it/docs/tutorial-managing-secrets) per il set completo di cicli set/list/deploy/verify/rotate.

**Modello write-only (stile GitHub):** `get` restituisce solo il digest SHA-256. Il valore in plaintext non è mai restituito a nessuno, umano o agente. Se dimentichi cosa sia un valore, cercalo nel tuo password manager e ruota; non puoi leggerlo indietro da Rediacc per design. Questo elimina un'intera classe di leak: registrazioni di terminale, cronologia della shell, reindirizzamento accidentale, shoulder-surfing.

Due modalità di consegna:

- `env`. Il secret è esportato come `REDIACC_SECRET_<KEY>` nella shell di renet sulla macchina target. Fai riferimento da `docker-compose.yml` tramite l'interpolazione `${REDIACC_SECRET_<KEY>}`. Visibile all'interno dell'ambiente del container, quindi usa questo per valori a forma di stringa di connessione che l'applicazione si aspetta già in env.
- `file`. Il secret è scritto su `/var/run/rediacc/secrets/<networkID>/<KEY>` sull'host (tmpfs, mai persistente). Fai riferimento dal tuo file di composizione tramite una dichiarazione `secrets:` di primo livello con la fonte `file:`, più un elenco `secrets:` per servizio. I container leggono da `/run/secrets/<key>`. Preferisci questa modalità per qualsiasi cosa sensibile. Non compare mai in `docker inspect` o `/proc/<pid>/environ`.

```bash
# Set, list, get (digest only), unset
rdc repo secret set --name my-app --key STRIPE_LIVE_KEY --value sk_live_xxx --mode file --current ""
rdc repo secret set --name my-app --key DB_HOST         --value postgres.internal --mode env --current ""
rdc repo secret list --name my-app
rdc repo secret get  --name my-app --key DB_HOST    # → { key, mode, digest } — no value
rdc repo secret unset --name my-app --key STRIPE_LIVE_KEY --current sk_live_xxx
```

**Symmetric mutation gate.** Sia gli umani che gli agenti hanno bisogno di `--current <previous-value>` per sovrascrivere o annullare un secret (precondizione stile passwd). Per la prima scrittura di una nuova chiave, passa `--current ""` (vuoto). Per ruotare senza verificare il valore precedente, passa `--rotate-secret` al contrario. Questo è rumorosamente controllato come una rotazione. `--current` e `--rotate-secret` si escludono a vicenda.

Passa `--value -` per leggere da stdin invece da argv (evita l'esposizione della cronologia della shell per le scritture una tantum).

Nel tuo `docker-compose.yml`:

```yaml
services:
  api:
    image: myapp
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

Il riferimento al servizio in minuscolo (`stripe_live_key`) è il nome file in-container `/run/secrets/<name>`; la coda maiuscola del percorso host (`STRIPE_LIVE_KEY`) corrisponde a quello che hai impostato con `--key`. `${REDIACC_NETWORK_ID}` è interpolato da `renet compose` automaticamente.

> **Isolamento cross-repo applicato**: il validatore di composizione di renet rifiuta i percorsi `secrets: file:` (e `configs: file:`, e `env_file:`) che fanno riferimento a qualsiasi altro Network ID del repository. Il token letterale `${REDIACC_NETWORK_ID}` (o il tuo numero di rete) è l'unica forma accettata per i riferimenti `/var/run/rediacc/secrets/...`. E `--unsafe` NON ignora questo controllo. La sandbox Landlock intorno al subprocess bash di Rediaccfile scopa anche l'accesso al filesystem alla sola directory dei secret della tua rete, quindi un malinteso `cat /var/run/rediacc/secrets/<other>/X` da un Rediaccfile fallisce con EACCES al livello del kernel.

> **Fork**: `rdc repo fork` fa **non** copiare i secret. Per usare i secret in un fork, esegui `rdc repo secret set --name <fork>` sul fork esplicitamente. Questa è la proprietà di sicurezza che regge il carico. I container del fork non dovrebbero essere in grado di agire come il principal di produzione contro i servizi esterni.

> **Agenti** (Claude Code, Cursor, ecc.): `repo secret list` e `repo secret get` sono esposti come strumenti MCP (read-safe. Solo nomi + digest, mai valori). `set` e `unset` sono CLI-only perché la cerimonia `--current`/`--rotate-secret` richiede occhi umani; gli agenti che li chiamano tramite shell ottengono lo stesso gate degli umani. Quando la precondizione fallisce, l'involucro JSON contiene un campo strutturato `errors[].next.options[].run`. Gli agenti dovrebbero trasmettere letteralmente quei comandi all'utente. Vedi [sicurezza degli agenti AI](/it/docs/ai-agents-safety) per il modello completo.

## Valida

Controlla l'integrità del filesystem di un repository:

```bash
rdc repo validate --name my-app -m server-1
```

## Proprietà

Imposta la proprietà del file all'interno di un repository all'utente universale (UID 7111). Questo è tipicamente necessario dopo aver caricato file dalla tua workstation, che arrivano con il tuo UID locale.

```bash
rdc repo ownership --name my-app -m server-1
```

Il comando rileva automaticamente le directory dei dati del container Docker (bind mount scrivibili) e le esclude. Questo previene di rompere i container che gestiscono file con i loro propri UID (ad es. MariaDB=999, www-data=33).

| Opzione | Descrizione |
|--------|-------------|
| `--uid <uid>` | Imposta un UID personalizzato al posto di 7111 |
| `--skip-router-restart` | Salta il riavvio del route server dopo l'operazione |

Per forzare la proprietà su tutti i file, inclusi i dati del container:

```bash
rdc repo ownership --name my-app -m server-1
```

Vedi la [Guida alla migrazione](/it/docs/migration) per una procedura passo-passo completa di quando e come usare la proprietà durante la migrazione del progetto.

## Template

Applica un template per inizializzare un repository con file:

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## Elimina

Distruggi permanentemente un repository e tutti i dati al suo interno:

```bash
rdc repo delete --name my-app -m server-1
```

> Questo distrugge permanentemente l'immagine di disco cifrata. Questa azione non può essere annullata.

## Migra Repository

Migra live un repository da una macchina all'altra. Il downtime è solo la fase di delta-sync finale: tipicamente secondi per bassi minuti a seconda del tasso di scrittura al cutover.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Opzione | Descrizione |
|--------|-------------|
| `--provision` | Provisioning del repository sulla macchina target prima della migrazione (crea l'immagine LUKS e registra il config) |
| `--checkpoint` | Crea un checkpoint CRIU dei container in esecuzione prima del cutover |
| `--bwlimit <kbps>` | Limita la larghezza di banda di rsync in kilobyte al secondo |
| `--skip-dns` | Salta l'aggiornamento dei record DNS dopo il cutover |

**Flusso in tre fasi:**

1. **Hot pre-copy** - rsync trasferisce i dati mentre il repository rimane in esecuzione sulla fonte. I file grandi vengono trasferiti prima di qualsiasi downtime.
2. **Cutover** - il repository viene fermato sulla fonte, un passaggio rsync finale sincronizza i cambiamenti rimanenti, e il repository inizia sulla destinazione.
3. **Start on target** - renet monta e avvia il repository sulla macchina target. DNS viene aggiornato a meno che `--skip-dns` non sia passato.

![Repository Live Migration](/img/repo-migrate-flow.svg)

**Push vs migrate:**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| Operazione | Copia | Sposta |
| Fonte dopo | Invariato | Fermato |
| Downtime | Nessuno (solo copia) | Breve finestra di cutover |
| Aggiornamento DNS | No | Sì (a meno che `--skip-dns`) |
| Caso d'uso | Backup, clone di staging | Sostituzione della macchina, spostamento del server |

## Prune

Dopo aver eliminato i repository o dopo essersi ripreso da operazioni non riuscite, le directory di montaggio orfane, i file di blocco e i marker immovibili possono rimanere. Prune li rimuove in sicurezza:

```bash
# Anteprima di cosa verrebbe rimosso
rdc machine prune --name server-1 --dry-run

# Rimuovi risorse orfane
rdc machine prune --name server-1
```

Solo le risorse senza un'immagine di repository corrispondente sono interessate. Le directory di montaggio non vuote non vengono mai rimosse.
