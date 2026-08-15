---
title: "Backup e Ripristino"
description: "Esegui il backup dei repository cifrati in due modi: storage a chunk indirizzato per contenuto che carica solo le celle modificate, oppure un push completo su qualsiasi storage compatibile con rclone. Ripristina su una macchina qualsiasi e automatizza con strategie denominate e timer systemd."
category: "Guides"
order: 7
language: it
sourceHash: "c02ab3e78c40fa92"
sourceCommit: "522dceadb04b6a3e7f4ea60ac1e47308f6a1a600"
---

# Backup e Ripristino

Rediacc esegue il backup dei repository cifrati su storage esterno e li ripristina sulla stessa o su una macchina diversa. I backup sono cifrati; per il ripristino è necessaria la credenziale LUKS del repository.

## Due percorsi di backup

Rediacc offre due percorsi di backup indipendenti, e questa guida li copre entrambi. Usano storage e comandi diversi, quindi un repository sottoposto a backup con l'uno non risulta sottoposto a backup con l'altro.

**Lo storage a chunk** (`rdc backup snapshot`) carica l'immagine del repository in celle di dimensione fissa indirizzate per contenuto. La prima esecuzione carica l'intero inventario non nullo; ogni esecuzione successiva carica solo le celle modificate, determinate dai metadati di allocazione del file system anziché leggendo l'intera immagine. Le celle identiche sono memorizzate una sola volta tra gli snapshot e tra un'intera famiglia di fork, e l'utilizzo viene conteggiato a fronte della tua quota di storage (`rdc backup usage`).

**Il push su storage è stato dismesso.** `rdc repo push --to <storage>` copiava un intero file di backup su un provider compatibile con rclone che registravi tu stesso. Il ramo rclone è stato rimosso del tutto, e push, pull, list e restore ora rifiutano una destinazione di storage e ti rimandano qui. Il trasferimento da macchina a macchina non è interessato: non è mai passato per rclone.

Il ripristino dallo storage a chunk funziona: `rdc backup restore <repo> --at <snapshot-id>` materializza uno snapshot memorizzato, e `--at` accetta anche un timestamp RFC 3339, che viene risolto rispetto all'inventario degli snapshot. Aggiungi `--as <name>` per ripristinare con un nome diverso e `--up` per riportare il repository su dopo. Lo storage a chunk ti offre anche il caricamento (`rdc backup snapshot`), la verifica (`rdc backup verify`, e `--deep` per ri-hashare ogni cella anziché un campione), l'inventario degli snapshot (`rdc backup manifests`) e la contabilità della quota (`rdc backup usage`).

### Comandi per lo storage a chunk

```bash
# Carica uno snapshot. La prima esecuzione semina i dati, le successive inviano solo le celle modificate.
rdc backup snapshot my-app

# Pianifica senza caricare: riporta cosa verrebbe spostato.
rdc backup snapshot my-app --dry-run

# Non fidarti dell'ancora locale e ricarica l'intero inventario.
# Questo ricarica tutto e riaddebita la quota; usalo solo quando
# l'ancora è nota per essere difettosa.
rdc backup snapshot my-app --reseed

# Controlla l'inventario memorizzato e la tua quota.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

## Snapshot a Freddo (`--cold`)

Uno snapshot a freddo ferma un repository prima di congelarlo, così l'immagine memorizzata è application-consistent e non soltanto crash-consistent. Il comando gira sulla macchina stessa:

```bash
# Ogni repository sul datastore predefinito.
sudo renet backup snapshot --cold

# Solo i repository indicati. --repo prende un GUID di repository ed è ripetibile.
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold` non si può combinare con `--dry-run`. Una prova a vuoto che ferma i container non è una prova a vuoto, e una che non li ferma non è a freddo: renet rifiuta la coppia invece di scegliere un significato al posto tuo.

### Cosa fa un'esecuzione a freddo

Per ogni repository selezionato, in quest'ordine:

1. Fermare i suoi container.
2. Scrivere su disco il mount del repository e il datastore.
3. Verificare che i container si siano davvero fermati.
4. Prendere un reflink copy-on-write dell'immagine del repository.
5. Riavviare i container.

Solo a quel punto parte il caricamento, con tutti i repository già di nuovo attivi.

Il downtime è il congelamento, non il trasferimento. Un reflink tocca solo metadati, quindi impiega lo stesso tempo sia che il repository contenga 1 GB sia che ne contenga 100. Un caricamento no: cresce con i byte cambiati, e il primo snapshot carica l'intero inventario non nullo. Tenere i container fermi fino alla fine del caricamento legherebbe il downtime alla mole dei dati, cioè ore invece di millisecondi alla prima copia.

Tutti i repository selezionati vengono fermati in un'unica finestra, non uno alla volta. Costa un po' più di downtime per repository e in cambio dà un solo punto di consistenza per l'intero insieme.

Un repository senza container in esecuzione è già fermo. Viene catturato senza alcun downtime, ed è un esito normale, non un errore.

### Quanto costa il downtime

Misurato su una macchina reale, il downtime totale è stato di **222 ms**:

| Fase | Misurato | Cosa succede |
|------|----------|--------------|
| `cold_down` | 64 ms | I container si fermano |
| `cold_sync` | 26 ms | Mount del repository e datastore scritti su disco |
| `cold_verify` | 31 ms | Si conferma che i container sono fermi |
| `cold_stage` | 0 ms | Reflink dell'immagine del repository |
| `cold_up` | 99 ms | I container ripartono |

Il riavvio dei container domina, e lo staging è praticamente gratis: il reflink non si vede nemmeno alla risoluzione del millisecondo. Quello zero però va letto accanto ai record dei singoli repository, non da solo. Anche un'esecuzione che ha rifiutato ogni repository riporta `cold_stage=0ms`, e solo i record dicono quale dei due casi hai davanti.

Il dettaglio è la prova, non un ornamento. Nessuna di queste cinque fasi legge o invia dati del repository, quindi nessuna cresce al crescere del backup. La parte che cresce, il caricamento, parte quando il downtime è già finito.

renet stampa gli stessi numeri alla fine di un'esecuzione, così puoi misurare le tue macchine invece di fidarti delle nostre:

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

Il record JSON di ogni repository porta lo stesso downtime e le stesse fasi, così più avanti si distingue uno snapshot a freddo da uno a caldo senza doverlo dedurre dai tempi.

### Quando scegliere il freddo

Il caldo è il comportamento predefinito ed è la scelta giusta per la maggior parte dei repository. Uno snapshot a caldo è crash-consistent, cioè nello stato in cui un repository si troverebbe dopo un blackout, e non costa alcun downtime. Quasi tutti i database e le code si rimettono in sesto da soli.

Scegli il freddo per dati che non si possono catturare in sicurezza mentre vengono scritti. Un database con il proprio write-ahead log e lo stato in memoria è il caso tipico. Stai scambiando un downtime breve e misurato con uno snapshot che l'applicazione può aprire senza doversi prima riparare.

### Cosa rifiuta un'esecuzione a freddo

Il rifiuto è la funzione. Un backup etichettato a freddo che non ha fermato nulla è una bugia che scopriresti solo al ripristino, perciò renet non declassa mai in silenzio un'esecuzione a freddo a una a caldo:

- **Container che non si sono fermati.** Dopo lo stop, renet chiede al socket Docker del repository se qualcosa è ancora in esecuzione. Se sì, quel repository viene rifiutato invece che catturato. Il controllo decide dalla parte sicura: se il socket è irraggiungibile o l'elenco dei container non è leggibile, la quiescenza vale come non verificata, e non verificata significa rifiutata.
- **Una licenza che non si riesce a leggere.** Le licenze si controllano prima del downtime, non dopo, perché un repository con licenza illeggibile non avrebbe comunque potuto caricare niente. Un repository così viene saltato senza essere fermato. Se nessuno dei repository selezionati ha una licenza leggibile, l'intera esecuzione viene rifiutata prima che scenda un solo container.
- **Una seconda esecuzione a freddo sullo stesso datastore.** Il lock copre il datastore, e un lock occupato viene rifiutato subito, senza aver fermato nulla. Due esecuzioni sovrapposte fermerebbero ciascuna container che l'altra crede propri, e la seconda riavvierebbe repository che la prima sta ancora congelando. Saltare l'esecuzione e aspettare la prossima è meglio.

Se un'esecuzione viene interrotta con i container fermi, da un `systemctl stop` o da un riavvio, renet li rimette in moto prima di uscire. Il recupero sulla macchina fa da rete: individua un backup a freddo il cui proprietario è sparito e riporta su quei repository.

## Configurare lo Storage

Prima di inviare i backup, registra un provider di storage. Rediacc supporta qualsiasi storage compatibile con rclone: S3, B2, Google Drive e molti altri.

### Importa da rclone

Se hai già un remote rclone configurato:

```bash
rdc storage import rclone.conf
```

Questo importa le configurazioni di storage da un file di configurazione rclone nella configurazione corrente. Tipi supportati: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob e Swift.

### Visualizza gli Storage

```bash
rdc storage list
```

## Invia un Backup a un'Altra Macchina

Copia un repository su una seconda macchina via SSH:

```bash
rdc repo push my-app --to-machine server-1
```

L'immagine cifrata viene copiata con lo STESSO GUID, quindi si tratta di un backup o di una migrazione, non di un fork. Per ottenere una copia indipendente, esegui prima `rdc repo fork` e poi invia il fork.

Per un backup puntuale, usa invece lo storage a chunk: `rdc backup snapshot my-app` carica solo le celle modificate, e `rdc backup restore my-app --at <snapshot>` ne riporta indietro una qualsiasi.

| Opzione | Descrizione |
|--------|-------------|
| `--to-machine <machine>` | Macchina di destinazione per il backup da macchina a macchina |
| `--dest <filename>` | Nome file di destinazione personalizzato |
| `--checkpoint` | Crea un checkpoint CRIU prima dell'invio (per container con etichetta `rediacc.checkpoint=true`). La destinazione si ripristina automaticamente su `repo up` |
| `--force` | Sovrascrive un backup esistente |
| `--bwlimit <limit>` | Limite di banda per il trasferimento rsync (ad es. `10M`, `500K`) |
| `--tag <tag>` | Etichetta il backup |
| `-w, --watch` | Monitora il progresso dell'operazione |
| `--debug` | Abilita l'output dettagliato |
| `--skip-router-restart` | Salta il riavvio del route server dopo l'operazione |

## Scarica un Backup da un'Altra Macchina

Recupera un repository dalla macchina che lo contiene:

```bash
rdc repo pull my-app --from-machine server-1
```

Per ripristinare invece dallo storage a chunk, usa
`rdc backup restore my-app --at <snapshot-id>`.

Il pull rifiuta di sovrascrivere un repository attualmente **montato**. Smontalo prima, esegui il pull e poi riportalo su con `rdc repo up`. I repository basati su directory sono l'eccezione: si sincronizzano sul posto anche mentre sono montati.

| Opzione | Descrizione |
|--------|-------------|
| `--from-machine <machine>` | Macchina sorgente per il ripristino da macchina a macchina |
| `--force` | Sovrascrive il backup locale esistente |
| `--bwlimit <limit>` | Limite di banda per il trasferimento rsync (ad es. `10M`, `500K`) |
| `-w, --watch` | Monitora il progresso dell'operazione |
| `--debug` | Abilita l'output dettagliato |
| `--skip-router-restart` | Salta il riavvio del route server dopo l'operazione |

## Elenca i Backup

Elenca gli snapshot nello storage a chunk:

```bash
rdc backup snapshot list my-app
```

Per vedere i backup presenti su una macchina:

```bash
rdc backup list -m server-1
```

L'output è una tabella unificata che unisce entrambe le [cartelle dei backup pianificati](#backup-pianificati) (`hot/` e `cold/`) in modo da vedere ogni backup in un'unica vista:

| Colonna | Significato |
|---|---|
| `Mode` | `hot` o `cold`. In quale cartella di backup pianificato si trova questa voce |
| `Name` | Nome del repository risolto dalla configurazione locale (fallback al GUID per i repository non in configurazione) |
| `GUID` | Il GUID del repository su disco |
| `Size` | Dimensione leggibile del file di backup |
| `Modified` | Timestamp UTC dal backend di storage |

Elencare un backend di storage è stato dismesso insieme al ramo rclone; il comando rifiuta l'esecuzione e indica questi due sostituti.

### Layout dello storage

I backup pianificati finiscono in sottocartelle per modalità all'interno della cartella configurata dello storage, in modo che lo stesso storage ospiti in modo ordinato sia lo stream orario che quello settimanale senza mescolarli:

```text
<bucket>/<folder>/
├── hot/
│   ├── <guid-1>
│   ├── <guid-2>
│   └── ...
└── cold/
    ├── <guid-1>
    ├── <guid-3>
    └── ...
```

Un repository può apparire sia in `hot/` che in `cold/` (lo schedule orario ne crea uno snapshot; lo schedule settimanale ne crea un altro). L'elenco unificato mostra entrambe le righe in modo che sia chiaro quali stream coprono quali repository.

## Sincronizzare un repository alla volta

Push e pull agiscono su un singolo repository, identificato dal ref (`name`, `name:tag` o `name@machine`). Non esiste una forma «tutti i repository in una volta»: esegui il comando una volta per ogni repository.

### Invia a un'Altra Macchina

```bash
rdc repo push shop@server-1 --to-machine server-2
```

### Scarica da un'Altra Macchina

```bash
rdc repo pull shop@server-1 --from-machine server-2
```

| Opzione | Descrizione |
|--------|-------------|
| `--to-machine <machine>` | Macchina di destinazione per il push da macchina a macchina |
| `--from-machine <machine>` | Macchina sorgente per il pull da macchina a macchina |
| `--force` | Sovrascrive un backup o repository esistente |
| `--checkpoint` | Crea un checkpoint CRIU prima dell'invio (solo push) |
| `--up` | Monta e distribuisce il repository dopo il pull (solo pull) |
| `--bwlimit <limit>` | Limite di banda per il trasferimento rsync (ad es. `10M`) |
| `--delta-base <guid>` | Trasferisce solo i blocchi modificati rispetto a una GUID di base immutabile |
| `--debug` | Abilita l'output dettagliato |
| `--skip-router-restart` | Salta il riavvio del route server dopo l'operazione |

## Backup Pianificati

Rediacc usa strategie di backup con nome. Ogni strategia definisce uno schedule, una modalità di backup, un limite di banda opzionale e filtri sui file. Le macchine fanno riferimento alle strategie per nome per determinare quali backup eseguire su di esse.

### Modalità di Backup

| Modalità | Comportamento | Downtime |
|------|----------|----------|
| `hot` | Snapshot BTRFS effettuato mentre i servizi sono in esecuzione (crash-consistent) | Nessuno |
| `cold` | Servizi fermati, snapshot effettuato, servizi riavviati, snapshot caricato (app-consistent) | Finestra di stop+start per repository, parallelizzata tra i repository. Vedere "Stima del Downtime del Backup Cold" di seguito. |

Usare `hot` per i servizi che tollerano snapshot crash-consistent. Usare `cold` quando si ha bisogno di consistenza garantita e si può accettare un breve riavvio.

### Semantica del Backup Cold

Un backup cold viene eseguito in tre fasi per ogni repository incluso: **stop > snapshot > start**. Capire dove finiscono le garanzie aiuta gli operatori a individuare precocemente i fallimenti parziali.

**Cosa garantisce il backup cold:**

- Prima dello snapshot, ogni container in esecuzione in ogni repository incluso viene fermato correttamente tramite l'hook `down()` del Rediaccfile e il daemon Docker per repository viene quiescito. Lo snapshot è quindi application-consistent, non meramente crash-consistent.
- L'insieme degli ID container in esecuzione prima dello snapshot viene persistito in un sidecar in `/var/run/rediacc/cold-backup-<guid>.running.json`. Questo è la fonte di verità per "cosa deve essere attivo quando abbiamo finito".
- Dopo lo snapshot, l'hook `up()` del Rediaccfile del repository viene richiamato per ripristinare lo stack compose completo.
- Un sidecar di stato per esecuzione in `/var/run/rediacc/cold-backup-<guid>.status.json` registra la fase, il risultato ed eventuali errori di ogni tentativo.

**Cosa NON garantisce il backup cold:**

- `up()` è best-effort. Può fallire per ragioni al di fuori del controllo del backup cold (una condizione `depends_on: service_healthy` ancora in attesa, un errore di sintassi nel file compose, un errore di rete transitorio durante il pull di un'immagine). Quando fallisce, il backup cold registra l'errore a livello di errore, scrive il sidecar di stato e passa al repository successivo.
- Quando `up()` fallisce, si attiva un **riavvio diretto di fallback**: il sidecar dei container in esecuzione viene letto e ogni ID container registrato viene riavviato tramite l'API Docker diretta (senza compose). Questo riporta i servizi su anche se il flusso compose ha un problema, sebbene senza rieseguire alcun hook del Rediaccfile.
- Se anche il fallback fallisce per alcuni ID container (ad esempio, il daemon Docker stesso è down), il sidecar viene **lasciato in posizione** in modo che il watchdog del router possa continuare a riprovare a ogni tick.

**Recupero del watchdog:** a ogni tick, il watchdog controlla la presenza di un running-sidecar. Qualsiasi ID container elencato che è attualmente fermo viene riavviato, *indipendentemente dalla `restart_policy` salvata del container*. Ciò significa che i servizi con `restart: on-failure` (che Docker NON riavvierebbe dopo uno stop pulito) tornano comunque attivi dopo un backup cold. Una volta che ogni container elencato è in esecuzione, il sidecar viene eliminato.

**Come gli operatori rilevano i fallimenti:**

- `rdc machine status <machine> --containers` mostra lo stato di esecuzione. Confrontare con il set atteso.
- `/var/run/rediacc/cold-backup-<guid>.status.json` sulla macchina. Ispezionare tramite `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` con un `startedAt` obsoleto significa che l'ultimo backup non è stato completato in modo pulito.
- I log dell'esecuzione del backup di renet (`journalctl -u renet-*` o l'invocazione diretta `rdc backup schedule`) emettono una riga di riepilogo finale della forma `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Un `failed_repos` non vuoto è il target di grep.

### Stima del Downtime del Backup Cold

Ogni repository è fermo solo per la propria finestra `down()` + `up()`. Su un host caldo questi sono tipicamente:

| Dimensione repository | Stop+start tipico |
|------------|--------------------|
| Piccolo (1-2 container, nessun DB) | 5-15 s |
| Medio (web app + cache) | 20-45 s |
| Pesante (DB + queues + mail) | 60-120 s |

Il passo di snapshot (`btrfs subvolume snapshot -r`) è O(1) indipendentemente dalla dimensione del repository: 0,1-1 s. Un repository non rimane fermo per gli snapshot degli altri repository. L'uploader poi gira su uno snapshot in sola lettura mentre ogni repository è già tornato attivo.

**Il tempo totale di esecuzione** dipende da quanti repository si riavviano in modo concorrente. Renet lo deriva dall'host:

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Esempi:

| Host | Repository | Concorrenza | Riavvio wall-clock |
|------|-------|-------------|--------------------|
| VM 4 CPU | 5 repository, media 30 s ciascuno | 2 | ~75 s |
| Server 16 CPU | 10 repository, media 40 s ciascuno | 8 | ~80 s |
| Nodo fleet 64 CPU | 50 repository, media 40 s ciascuno | 8 | ~4 min |

**Override tramite env:** impostare `REDIACC_COLD_BACKUP_CONCURRENCY=N` nell'ambiente del servizio di backup (un drop-in systemd è il modo comune) per fissare un valore specifico. `=1` forza riavvii strettamente seriali, utile per il debug di un crashloop nell'hook `up()` di un repository.

Se si gestisce un repository sensibile alla latenza (web app pubblica, mail), il suo downtime è delimitato dal proprio stop+start (tipicamente 30-90 s), non dalla durata totale dell'esecuzione. I repository vengono assegnati agli slot di concorrenza nell'ordine in cui sono stati scoperti; non esiste una coda con priorità. Suddividere i repository pesanti nelle proprie strategie con scope `--exclude` se si ha bisogno di una pianificazione più granulare.

### Backup di Lunga Durata e Schedule Sovrapposti

Un backup cold che richiede più tempo del proprio intervallo di schedule (ad esempio, un primo seed di un repository da 500 GB su un link modesto può legittimamente richiedere più di 24 ore, durante le quali il timer notturno si attiva di nuovo) non mette in coda né avvia una seconda esecuzione. L'unità systemd `Type=oneshot` è a istanza singola: quando il timer si attiva e il servizio è già `activating`, systemd unisce l'avvio nel job esistente. Nessun nuovo processo viene avviato, nessuna esecuzione viene messa in coda per dopo.

In concreto, un'esecuzione che inizia lunedì alle 03:00 UTC e finisce giovedì a mezzogiorno:

| Giorno | Attivazione 03:00 UTC | Risultato |
|------|---------------|--------|
| Lunedì | Prima attivazione | L'esecuzione inizia |
| Martedì | Seconda attivazione | Scartata silenziosamente (l'esecuzione precedente è ancora attiva) |
| Mercoledì | Terza attivazione | Scartata silenziosamente (l'esecuzione precedente è ancora attiva) |
| Giovedì | L'esecuzione finisce a mezzogiorno | Nessun recupero; la prossima esecuzione è venerdì alle 03:00 UTC |

La direttiva `Persistent=true` del timer **non** salva queste attivazioni. `Persistent=true` riproduce le attivazioni mancate perché il timer stesso era inattivo (sistema spento, timer disabilitato). Le attivazioni scartate perché il servizio era occupato sono perdute.

Questo comportamento predefinito è deliberato. Eseguire due backup cold in parallelo sullo stesso datastore causerebbe contesa sul percorso dello snapshot BTRFS, sul remote rclone e sui sidecar per repository in `/var/run/rediacc/cold-backup-<guid>.status.json`. La serializzazione dietro un'istanza a lunga esecuzione è il risultato sicuro.

**Implicazione per il monitoraggio.** Un backup bloccato (ad esempio, rclone inceppato su un blackhole di rete) scarta silenziosamente ogni attivazione successiva del timer. Lo scheduler non emette alcun allarme. Controllare `systemctl show <unit> -p ActiveEnterTimestamp`: se il servizio è in `activating` da più tempo del previsto (ad esempio, più di 48 ore su un timer notturno), investigare.

**Se si ha bisogno che ogni attivazione pianificata venga eseguita**, cambiare il timer da `OnCalendar=<cron>` a `OnUnitInactiveSec=<interval>`. Questo si attiva N ore dopo il completamento dell'esecuzione precedente anziché su uno schedule fisso, quindi le esecuzioni lunghe non causano scartamenti. Spostano semplicemente la prossima esecuzione più avanti. Il compromesso è lo slittamento dello schedule: il tuo notturno alle 03:00 diventa "24 ore dopo la fine dell'ultimo".

### Snapshot, Interruzioni e Spazio nel Pool

Ogni push opera da uno snapshot momentaneo del datastore, quindi i dati caricati sono coerenti anche mentre i repository continuano a scrivere. Mentre il backup è in esecuzione, quello snapshot continua a fare riferimento a ogni blocco che condivide con i repository attivi: eliminazioni e [trim](/it/docs/repositories#recupera-spazio-trim) liberano meno spazio nel pool finché il ciclo non termina e lo snapshot viene eliminato. Il [report sulla salute dello storage](/it/docs/monitoring#salute-dellarchiviazione) mostra quanto spazio gli snapshot di backup stanno attualmente bloccando.

Le interruzioni sono sicure. Fermare il servizio (o riavviare la macchina) fa sì che il backup interrompa il trasferimento ed elimini il suo snapshot prima di uscire; la prossima esecuzione pianificata riprende da dove si era fermata, poiché i file non modificati vengono saltati tramite checksum. Se il processo viene terminato in modo troppo brusco per poter fare pulizia (perdita di alimentazione), lo snapshot orfano viene rilevato e rimosso automaticamente dal gestore dello storage entro pochi minuti.

### Definire una Strategia

Il default canonico è una divisione in due strategie: uno stream hot orario veloce che cattura ogni repository e uno stream cold settimanale più lento che crea snapshot app-consistent. Le due strategie scrivono in sottocartelle di storage diverse (`hot/` e `cold/`) in modo che i backup non si mescolino mai.

```bash
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

Il filtro `--exclude` sulla strategia cold è la via d'uscita consigliata per i repository molto grandi che non rientrano nella finestra di manutenzione settimanale. La strategia hot oraria li copre comunque; cold li salta semplicemente. I nomi dei repository in `--exclude` corrispondono al nome del repository nella configurazione locale (senza `:tag`).

| Opzione | Descrizione |
|--------|-------------|
| `<strategy>` (posizionale) | Nome della strategia (usato per il binding alla macchina) |
| `--destination <storage>` | Provider di storage su cui caricare |
| `--cron <expression>` | Espressione cron (ad es. `"0 2 * * *"` per ogni giorno alle 2:00) |
| `--mode <hot\|cold>` | Modalità di backup |
| `--bwlimit <limit>` | Limite di banda per i caricamenti (ad es. `10M`) |
| `--include <pattern>` | Filtro di inclusione (ripetibile) |
| `--exclude <pattern>` | Filtro di esclusione (ripetibile) |
| `--enable` / `--disable` | Abilita o disabilita la strategia |

### Visualizza le Strategie

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### Rimuovi una Strategia

```bash
rdc backup strategy remove weekly-cold
```

### Associa le Strategie a una Macchina

Nella tua configurazione, associa uno o più nomi di strategia a una macchina:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **Il binding è solo configurazione locale.** Definire una strategia e collegarla a una macchina non modifica la macchina. Esegui `rdc backup schedule -m <machine>` (vedi [Distribuisci lo Schedule sulla Macchina](#distribuisci-lo-schedule-sulla-macchina)) per distribuire i timer systemd, e rilancialo dopo ogni modifica di strategia o binding.

## Scegliere tra Hot e Cold e il filtraggio per repository

### Hot vs cold in sintesi

| | Hot | Cold |
|---|-----|------|
| **Consistenza** | Crash-consistent (snapshot BTRFS durante l'esecuzione) | Application-consistent (stop > snapshot > start) |
| **Downtime** | Nessuno | Finestra di stop+start per repository (tipicamente 5-120 s) |
| **Frequenza adatta** | Alta (ad es. oraria) | Bassa (ad es. giornaliera o settimanale) |
| **Uso tipico** | Rete di sicurezza ad alta frequenza | Backup pianificato con consistenza garantita |

**Hot** è il default corretto per le esecuzioni ad alta frequenza. I servizi continuano a girare mentre lo snapshot viene effettuato, quindi la finestra di backup non interrompe gli utenti. Lo snapshot è crash-consistent: equivale a quello che si otterrebbe dopo uno spegnimento non pulito. Per la maggior parte dei database moderni e delle code di messaggi questo è accettabile.

**Cold** è appropriato quando si ha bisogno di uno snapshot application-consistent garantito e si può accettare un breve riavvio per repository. I servizi vengono fermati prima dello snapshot e riavviati prima che inizi il caricamento, quindi un caricamento lento o fallito non prolunga mai la finestra di downtime. Vedere [Semantica del Backup Cold](#semantica-del-backup-cold) per il modello di garanzia completo.

### Filtraggio dei repository per strategia

Ogni strategia può avere filtri `--include` e `--exclude`. I nomi di repository che corrispondono a un pattern `--exclude` vengono saltati per quella strategia; `--include` limita l'esecuzione solo a quei nomi. I filtri corrispondono al nome del repository nella configurazione locale (senza `:tag`).

```bash
# Strategia hot: backup di tutto ogni ora
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Strategia cold: backup di tutto ogni settimana, escludendo il dataset derivato di grandi dimensioni
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude analytics-demo \
  --enable
```

### Quando escludere un repository dalla strategia hot ad alta frequenza

Escludi un repository dall'esecuzione ad alta frequenza quando:

- Il repository è grande e **completamente rigenerabile** dai dati sorgente già presenti nel volume, quindi ogni backup orario spreca banda significativa senza aggiungere valore di recupero significativo.
- L'esecuzione del backup supererebbe il proprio intervallo di schedule alla velocità di caricamento disponibile.

**Esempio.** Un repository `analytics-demo` contiene circa 114 GB di tabelle Postgres derivate che possono essere completamente ricostruite dai file di dump CSV grezzi già memorizzati all'interno dello stesso volume. Con un limite di caricamento di 6 MB/s, un singolo backup hot di quel repository richiede oltre 5 ore. Eseguirlo ogni ora significa che ogni esecuzione è ancora in corso quando parte quella successiva, il che causa lo scarto silenzioso di ogni esecuzione successiva (vedere [Backup di Lunga Durata e Schedule Sovrapposti](#backup-di-lunga-durata-e-schedule-sovrapposti)). Escluderlo da `hourly-hot` e mantenerlo in `weekly-cold` significa che viene eseguito il backup una volta alla settimana invece di mai.

> **Se i dati sono puramente rigenerabili**, considera se è necessario eseguirne il backup. Un'alternativa è eseguire il backup solo degli input sorgente grezzi (i dump CSV, in questo esempio) e saltare la copia derivata del tutto. Un backup cold settimanale degli input sorgente è molto più piccolo e completamente sufficiente per il recupero.

I repository non esclusi da nessuna delle due strategie appaiono in entrambe le sottocartelle di storage `hot/` e `cold/`. L'output unificato di `rdc backup list` mostra entrambe le righe in modo da poter verificare quali stream coprono quali repository.

## Operazioni di Backup

### Distribuisci lo Schedule sulla Macchina

Invia le strategie associate a una macchina come timer systemd:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

La distribuzione è un riconciliatore di stato. Legge i file unit correnti e lo stato systemd sulla macchina, li confronta con ciò che la configurazione produrrebbe (SHA-256 per file) e tocca solo le unit il cui contenuto è effettivamente cambiato. La riesecuzione senza modifiche alla configurazione è una no-op: nessuna scrittura, nessun `daemon-reload`, nessun cambio di timer.

`--dry-run` stampa il piano per ogni strategia (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) senza toccare la macchina. Combinare con `--debug` per stampare anche i corpi delle unit generate; i token rclone sono redatti.

Se un backup è attualmente in esecuzione per una strategia che si sta per aggiornare o rimuovere, la distribuzione fallisce rapidamente con un suggerimento di annullarlo o di passare `--force`. Con `--force`, l'invocazione in esecuzione mantiene la propria unit in memoria e la nuova configurazione si applica al prossimo tick del timer, quindi il backup in esecuzione non viene mai interrotto.

`--reset-failed` è opt-in. Se passato, cancella lo stato di fallimento di systemd sui servizi toccati dopo una distribuzione riuscita. Disabilitato per impostazione predefinita affinché i segnali di fallimento precedenti rimangono visibili agli alert.

### Esegui un Backup Ora

Attiva un backup immediatamente senza attendere il timer. Funziona anche se non sono stati distribuiti timer, usando `systemd-run` per l'esecuzione ad-hoc:

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### Visualizza lo Stato del Backup

Mostra lo stato corrente dei timer di backup e i risultati dei job recenti:

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### Annulla un Backup in Esecuzione

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## Migrazione del Repository

Sposta un repository da una macchina a un'altra:

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| Opzione | Descrizione |
|--------|-------------|
| `<ref>` (posizionale) | Ref del repository da migrare; il suo `@machine` indica la sorgente |
| `--to <place>` | Macchina o cluster di destinazione |
| `--provision` | Effettua il provisioning del repository sulla destinazione prima del trasferimento |
| `--checkpoint` | Crea un checkpoint CRIU prima della migrazione |
| `--skip-dns` | Salta l'aggiornamento dei record DNS dopo la migrazione |
| `--bwlimit <limit>` | Limite di banda per il trasferimento (ad es. `50M`) |

La migrazione trasferisce i dati del repository cifrato tramite rsync. Il repository sorgente rimane intatto fino a quando non lo si rimuove esplicitamente.

## Sfoglia lo Storage

`rdc storage browse` e `rdc storage import` sono l'eccezione a questa dismissione: avviano il tuo rclone personale dal PATH invece di una copia integrata, e restano il modo per leggere un archivio scritto prima del cambiamento.

```bash
rdc storage browse my-storage
```

Sfogliare è di sola lettura. L'invio a, il download da e l'elenco di un backend di storage sono stati dismessi; ognuno rifiuta l'esecuzione e indica il comando di storage a chunk che lo sostituisce.

## Buone Pratiche

- Pianifica backup cold giornalieri per snapshot app-consistent dei dati critici
- Usa i backup hot per snapshot ad alta frequenza dove è richiesto zero downtime
- Testa periodicamente i ripristini per verificare l'integrità dei backup
- Usa più provider di storage per i dati critici (ad es. S3 + B2)
- Tieni le credenziali al sicuro; i backup sono cifrati ma la credenziale LUKS è necessaria per il ripristino
