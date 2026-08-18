---
title: "Backup e Ripristino"
description: "Esegui lo snapshot dei repository cifrati verso uno storage a chunk indirizzato per contenuto, dove vengono caricate solo le celle modificate e ogni snapshot si ripristina direttamente. Oppure conserva una copia su un'altra macchina. Ripristina ovunque, e automatizza con strategie denominate e timer systemd."
category: "Guides"
order: 7
language: it
sourceHash: "91f6072e230b059c"
sourceCommit: "79c84ad044d5730b6d0a20aaf7b21f21914b6bda"
---

# Backup e Ripristino

Rediacc esegue il backup dei repository cifrati e li ripristina sulla stessa macchina o su una diversa. I backup sono cifrati perché lo è il repository: ciò che lascia la macchina è il testo cifrato, e per il ripristino è necessaria la credenziale LUKS del tuo repository.

Ci sono due modi per eseguire il backup, e rispondono a domande diverse.

- **Snapshot verso lo storage a chunk** (`rdc backup snapshot`) mantengono uno storico attraverso cui puoi tornare indietro. È il percorso principale.
- **Una copia su un'altra macchina** (`rdc repo push`, `rdc repo pull`) mantiene il repository così com'è ora, su hardware che controlli tu. Nessun account cloud è coinvolto.

Sono indipendenti. Un repository sottoposto a backup in un modo non risulta sottoposto a backup nell'altro.

## Come funzionano gli snapshot

L'immagine del repository viene tagliata in celle di dimensione fissa su una griglia fissa. Ogni cella è un buco, cioè non vi è mai stato scritto nulla, oppure viene memorizzata sotto una chiave che **è** lo SHA-256 del testo cifrato di quella cella.

Da questa unica decisione derivano le proprietà.

**Solo i cambiamenti reali costano qualcosa.** Il primo snapshot carica ogni cella scritta. Ogni esecuzione successiva chiede al file system quali extent sono stati toccati, legge e sottopone a hash solo quelle, e carica solo le celle che lo storage non possiede ancora. Un repository i cui dati si sono a malapena mossi carica quasi nulla, e l'esecuzione richiede minuti anziché un tempo proporzionale alla dimensione dell'immagine.

**I dati identici vengono memorizzati una sola volta.** Poiché la chiave è l'hash del contenuto, due snapshot che condividono una cella condividono lo stesso oggetto, e lo stesso vale per un repository e i suoi [fork](/it/docs/tutorial-forking): una famiglia di fork esegue il backup contro un'unica discendenza anziché duplicare il proprio genitore.

**Ripristinare uno snapshot vecchio non è più lento che ripristinarne uno recente.** Non c'è una catena di incrementi da riprodurre. Il ripristino risolve lo snapshot in un elenco completo di celle e recupera direttamente quelle celle, quindi il tempo di ripristino segue la dimensione dell'immagine e la tua larghezza di banda, non da quanto tempo fai backup. I buchi restano buchi, quindi un'immagine sparse si ripristina sparse, e una cella che compare in più punti dell'immagine viene scaricata una sola volta.

**Ogni snapshot si regge da solo.** Non esiste un "backup completo" che non devi perdere né una finestra in cui un incremento danneggiato invalida quelli successivi. Qualsiasi snapshot dell'elenco è direttamente ripristinabile.

**La verifica è un nuovo hashing, non fiducia.** Poiché la chiave è l'hash del contenuto, controllare un backup significa recuperare le celle e sottoporle a hash. `rdc backup verify` campiona; `rdc backup verify --deep` sottopone di nuovo a hash ogni cella registrata.

**Un'esecuzione interrotta non è sprecata.** Il caricamento riprende senza reinviare le celle già arrivate, e riavviare un ripristino parziale ricalcola l'hash di ciò che è già su disco e lo riutilizza invece di riscaricarlo.

### Cosa ti costa

La quota è conteggiata in **byte fisici unici memorizzati**: ciò che è effettivamente trattenuto dopo la deduplicazione, non la somma di ciò che i tuoi snapshot rappresentano logicamente. Trenta snapshot di un repository che cambia lentamente costano quasi come uno solo. `rdc backup usage` mostra i byte memorizzati rispetto alla tua quota, un numero per abbonamento che parte da 10 GB nel piano Community.

### Cosa serve agli snapshot

Il caricamento di uno snapshot passa attraverso il server dell'account, che autorizza ogni esecuzione rispetto alla licenza installata del repository e consegna alla macchina un permesso di scrittura di breve durata. Questo percorso richiede quindi un server dell'account raggiungibile dalla macchina e un repository con licenza. Senza di essi, lo snapshot viene rifiutato anziché saltato silenziosamente, e `rdc backup manifests`, `rdc backup usage` e `rdc backup retention` non hanno nulla da leggere.

Questo vale anche per `--dry-run`. La licenza viene letta prima che l'esecuzione decida se sta pianificando o caricando, quindi un'esecuzione a vuoto è un'anteprima del lavoro, non un modo per provare il comando senza credenziali.

Il push e il pull da macchina a macchina non necessitano di nessuno dei due. Sono un trasferimento diretto tra due macchine già presenti nella tua configurazione.

### Cosa non promette uno snapshot

- **Uno snapshot copre un repository, non tutta la tua macchina in una volta.** Ogni repository viene catturato nel proprio istante. Se due repository dipendono l'uno dall'altro, i loro snapshot non formano una coppia coordinata.
- **Non è una replica continua.** Uno snapshot è un punto che hai catturato, e puoi perdere tutto ciò che è stato scritto dall'ultimo. Quanto sia dipende dalla frequenza con cui lo esegui.
- **Gli oggetti memorizzati sono write-once, non WORM certificato.** Le celle vengono scritte con una condizione di sola creazione, il permesso ottenuto da una macchina non può eliminare nulla, e le eliminazioni avvengono lato server secondo la politica di conservazione. È una barriera reale contro una macchina compromessa che distrugge i propri backup. Non è una certificazione di conformità, e non viene verificata come tale.

### Il percorso di storage rclone è sparito

`rdc repo push --to <storage>` e i suoi affini un tempo copiavano un intero file di backup su un provider compatibile con rclone che registravi tu stesso. Ora rifiutano una destinazione di storage e indicano il loro sostituto. Il trasferimento da macchina a macchina non è mai passato per rclone e non è interessato. Se hai ancora bisogno di leggere un archivio scritto in quel modo, vedi [Leggere un archivio scritto prima della dismissione](#reading-an-archive-written-before-the-retirement).

### Comandi per lo storage a chunk

```bash
# Carica uno snapshot. La prima esecuzione semina i dati, le successive inviano solo le celle modificate.
rdc backup snapshot my-app

# Pianifica senza caricare: riporta cosa verrebbe spostato.
rdc backup snapshot my-app --dry-run

# Ferma i container, congela, riavvia, poi carica.
rdc backup snapshot my-app --cold

# Non fidarti dell'ancora locale e ricarica l'intero inventario.
# Questo ricarica tutto e riaddebita la quota; usalo solo quando
# l'ancora è nota per essere difettosa.
rdc backup snapshot my-app --reseed

# Controlla l'inventario memorizzato e la tua quota.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

| Opzione | Descrizione |
|--------|-------------|
| `<repo-ref>` (posizionale) | Repository di cui fare lo snapshot |
| `--dry-run` | Solo pianificazione: nessun caricamento. Riporta cosa verrebbe spostato |
| `--cold` | Ferma i container, congela, riavvia, poi carica. Non combinabile con `--dry-run` |
| `--reseed` | Non fidarti dell'ancora locale e carica un inventario completo. Ricarica tutto e riaddebita la quota |
| `--debug` | Abilita l'output dettagliato |

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

## Invia un Backup a un'Altra Macchina

Copia un repository su una seconda macchina via SSH:

```bash
rdc repo push my-app --to server-1
```

`--to <machine>` risolve la destinazione dalla tua configurazione, e `--to-machine <machine>` dice la stessa cosa esplicitamente. Un nome di storage viene rifiutato: quel percorso è dismesso.

L'immagine cifrata viene copiata con lo STESSO GUID, quindi si tratta di un backup o di una migrazione, non di un fork. Per ottenere una copia indipendente, esegui prima `rdc repo fork` e poi invia il fork.

Il primo invio trasporta l'immagine intera. Ogni invio successivo manda solo i blocchi modificati rispetto a un'immagine base immutabile mantenuta su entrambe le macchine, senza flag da impostare. `--delta-base <guid>` nomina quella base tu stesso se ne hai bisogno.

La copia inviata atterra sulla destinazione come artefatto di backup anziché come repository in esecuzione. Trasformala in uno con `rdc backup restore`:

```bash
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

Per un backup puntuale, usa invece lo storage a chunk: `rdc backup snapshot my-app` carica solo le celle modificate, e `rdc backup restore my-app --at <snapshot>` ne riporta indietro una qualsiasi.

| Opzione | Descrizione |
|--------|-------------|
| `<ref>` (posizionale) | Ref del repository da inviare |
| `--to <remote>` | Macchina o cluster di destinazione |
| `--to-machine <machine>` | Macchina di destinazione, indicata esplicitamente |
| `--provision <provider>` | Effettua il provisioning della macchina di destinazione tramite questo provider cloud se non esiste |
| `--checkpoint` | Crea un checkpoint CRIU prima dell'invio (per container con etichetta `rediacc.checkpoint=true`). La destinazione si ripristina automaticamente su `repo up` |
| `--force` | Sovrascrive un backup esistente |
| `--bwlimit <limit>` | Limite di banda per il trasferimento rsync (ad es. `10M`, `500K`) |
| `--delta-base <guid>` | Trasferisce solo i blocchi modificati rispetto a questa GUID di base immutabile. Ometti per la base automatica |
| `--strategy <strategy>` | Strategia di delta dei blocchi quando si usa una base delta: `auto`, `physical` o `shared` |
| `--debug` | Abilita l'output dettagliato |
| `--skip-router-restart` | Salta il riavvio del route server dopo l'operazione |

## Scarica un Backup da un'Altra Macchina

Recupera un repository dalla macchina che lo contiene:

```bash
rdc repo pull my-app --from server-1
```

Aggiungi `--up` per montarlo e distribuirlo nello stesso comando. Per ripristinare invece dallo storage a chunk, usa `rdc backup restore my-app --at <snapshot-id>`.

Il pull rifiuta di sovrascrivere un repository attualmente **montato**. Smontalo prima, esegui il pull e poi riportalo su con `rdc repo up`. I repository basati su directory sono l'eccezione: si sincronizzano sul posto anche mentre sono montati.

| Opzione | Descrizione |
|--------|-------------|
| `<ref>` (posizionale) | Ref del repository da scaricare |
| `--from <remote>` | Macchina o cluster sorgente |
| `--from-machine <machine>` | Macchina sorgente, indicata esplicitamente |
| `--force` | Sovrascrive il backup locale esistente |
| `--up` | Monta e distribuisce il repository dopo lo scaricamento |
| `--bwlimit <limit>` | Limite di banda per il trasferimento rsync (ad es. `10M`, `500K`) |
| `--delta-base <guid>` | Riceve solo i blocchi modificati rispetto a questa GUID di base immutabile |
| `--strategy <strategy>` | Strategia di delta dei blocchi quando si usa una base delta: `auto`, `physical` o `shared` |
| `--debug` | Abilita l'output dettagliato |
| `--skip-router-restart` | Salta il riavvio del route server dopo l'operazione |

## Elenca i Backup

Elenca gli snapshot nello storage a chunk:

```bash
rdc backup manifests my-app
```

Ogni riga è un punto nel tempo memorizzato:

| Colonna | Significato |
|---|---|
| `Repo` | Nome del repository risolto dalla configurazione locale (fallback al GUID per i repository non in configurazione) |
| `Snapshot` | L'id dello snapshot. È ciò che accetta `rdc backup restore --at` |
| `Created` | Ora UTC in cui è stato preso lo snapshot |
| `Total` | Dimensione dell'immagine del repository che questo snapshot rappresenta |
| `Added` | Byte effettivamente caricati da questo snapshot in aggiunta ai precedenti |
| `Chunks` | Quante celle ha aggiunto |

Per vedere cosa ha lasciato sulla destinazione un `rdc repo push --to <machine>`, chiedi a quella macchina cosa sta trattenendo:

```bash
rdc repo list --machine server-1
```

La copia inviata appare con il proprio nome. Una seconda riga con accanto un GUID grezzo è la base delta trattenuta, che è ciò che rende incrementale anziché completo il prossimo invio a quella macchina.

`rdc backup list --machine <machine>` legge le cartelle `hot/` e `cold/` in cui scrivono le esecuzioni pianificate, quindi è lo strumento sbagliato per una copia che un invio ha depositato lì, e non ti mostrerà nulla.

| Colonna | Significato |
|---|---|
| `Mode` | `hot` o `cold`. In quale cartella di backup pianificato si trova questa voce |
| `Name` | Nome del repository risolto dalla configurazione locale (fallback al GUID per i repository non in configurazione) |
| `GUID` | Il GUID del repository su disco |
| `Size` | Dimensione leggibile del file di backup |
| `Modified` | Timestamp UTC del file sulla macchina |

Elencare un backend di storage è stato dismesso insieme al ramo rclone; il comando rifiuta l'esecuzione e indica questi due sostituti.

## Conservazione

Il server applica una politica di conservazione per repository sullo storage a chunk, così gli snapshot vecchi vengono potati senza che tu debba eliminare nulla a mano. Senza una politica dichiarata, ogni snapshot viene conservato.

```bash
# Cosa è applicato in questo momento.
rdc backup retention my-app

# Mantieni una finestra scorrevole: 7 giornalieri, 4 settimanali, 6 mensili.
rdc backup retention set my-app --keep-daily 7 --keep-weekly 4 --keep-monthly 6

# Torna a conservare tutto.
rdc backup retention clear my-app
```

| Opzione | Descrizione |
|--------|-------------|
| `--keep-last <n>` | Conserva questo numero degli snapshot più recenti |
| `--keep-hourly <n>` | Conserva lo snapshot più recente per ciascuna di queste ore |
| `--keep-daily <n>` | Conserva lo snapshot più recente per ciascuno di questi giorni |
| `--keep-weekly <n>` | Conserva lo snapshot più recente per ciascuna di queste settimane |
| `--keep-monthly <n>` | Conserva lo snapshot più recente per ciascuno di questi mesi |
| `--keep-yearly <n>` | Conserva lo snapshot più recente per ciascuno di questi anni |

Fornisci almeno una regola. `set` senza regole viene rifiutato invece di essere trattato come "non conservare nulla", perché svuotare una politica è esattamente lo scopo di `clear`.

## Ripristino

`rdc backup restore` trasforma un backup in un repository live, ed è lo stesso comando per entrambi i percorsi. Ciò che cambia è a cosa lo punti.

```bash
# Un punto nel tempo dallo storage a chunk.
rdc backup restore my-app --as my-app-yesterday --at <snapshot-id> --up

# Un artefatto lasciato da un invio su una macchina.
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

`--at` accetta un id di snapshot da `rdc backup manifests`, oppure un orario RFC 3339 come `2026-08-14T12:00:00Z`, che si risolve nello snapshot più recente preso in quel momento o prima. Un orario senza uno snapshot in quel momento o prima viene rifiutato invece di essere arrotondato in avanti.

Ripristinare con un nuovo nome tramite `--as` non sovrascrive nulla, quindi un'esercitazione di ripristino è sicura da eseguire su una macchina live. Ripristinare su un nome già esistente viene rifiutato.

| Opzione | Descrizione |
|--------|-------------|
| `<artifact-ref>` (posizionale) | Cosa ripristinare. `repo` per uno snapshot dello storage a chunk, `repo@place` per un artefatto su una macchina |
| `--as <name>` | Nome per il repository ripristinato (predefinito: il nome dell'artefatto) |
| `-m, --machine <machine>` | Macchina su cui ripristinare |
| `--datastore <name>` | Ripristina in questo datastore denominato, la cui macchina collegata lo ospita |
| `--at <time>` | Ripristina un punto nel tempo: un id di snapshot o un orario RFC 3339 |
| `--up` | Distribuisce il repository ripristinato dopo il trasferimento |
| `--health-window <seconds>` | Per quanto tempo osservare la salute del repository distribuito |
| `--health-timeout <seconds>` | Per quanto tempo attendere che diventi sano |
| `-y, --yes` | Salta la conferma |
| `--debug` | Abilita l'output dettagliato |

Ripristinare un repository richiede la sua credenziale LUKS, che vive nella tua configurazione. Se hai lo storage della configurazione abilitato, quella credenziale torna insieme alla tua configurazione su una macchina nuova. In caso contrario, conserva una copia della configurazione in un luogo che la macchina guasta non si porta via con sé.

### Dimostra il ripristino su ogni macchina

Una macchina che non ha mai completato il ciclo completo non è protetta da backup, per quanto verdi appaiano i suoi caricamenti. Caricamenti e ripristini falliscono per motivi diversi, e il secondo tipo si manifesta solo quando lo provi.

Fallo una volta per macchina, prima di fare affidamento sui backup:

1. Prendi uno snapshot: `rdc backup snapshot my-app`.
2. Conferma che sia registrato: `rdc backup manifests my-app`.
3. Ripristinalo con un nome usa e getta: `rdc backup restore my-app --as my-app-drill --at <snapshot-id>`.
4. Confronta il repository ripristinato con la sorgente, poi elimina la copia di prova con `rdc repo delete my-app-drill --yes`.

Nulla in questa sequenza tocca il repository live, quindi è sicura su una macchina che sta servendo traffico. Se stai abbandonando un vecchio schema di backup, tienilo attivo finché questo non è passato su quella macchina almeno una volta. Due percorsi di backup costano storage; un percorso non dimostrato costa i dati.

## Sincronizzare un repository alla volta

Push e pull agiscono su un singolo repository, identificato dal ref (`name`, `name:tag` o `name@machine`). Non esiste una forma «tutti i repository in una volta»: esegui il comando una volta per ogni repository.

Un ref che nomina un fork e una macchina funziona come un nome semplice:

```bash
rdc repo push shop:nightly@server-1 --to server-2
rdc repo pull shop:nightly@server-1 --from server-2
```

Gli elenchi completi delle opzioni si trovano sotto [Invia un Backup a un'Altra Macchina](#push-a-backup-to-another-machine) e [Scarica un Backup da un'Altra Macchina](#pull-a-backup-from-another-machine).

## Backup Pianificati

Rediacc usa strategie di backup con nome. Ogni strategia definisce uno schedule, una modalità di backup, un limite di banda opzionale e filtri sui file. Le macchine fanno riferimento alle strategie per nome per determinare quali backup eseguire su di esse.

### Modalità di Backup

| Modalità | Comportamento | Downtime |
|------|----------|----------|
| `hot` | Immagine del repository congelata mentre i servizi restano in esecuzione (crash-consistent) | Nessuno |
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

Il passo di congelamento è un reflink copy-on-write dell'immagine del repository. Tocca solo metadati, quindi impiega lo stesso tempo sia che il repository contenga 1 GB sia che ne contenga 100, e in un'esecuzione misurata non si è vista nemmeno alla risoluzione del millisecondo. Un repository non rimane fermo durante il congelamento degli altri repository. Il caricamento poi gira sulla copia congelata mentre ogni repository è già tornato attivo.

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

Se si gestisce un repository sensibile alla latenza (web app pubblica, mail), il suo downtime è delimitato dal proprio stop+start (tipicamente 30-90 s), non dalla durata totale dell'esecuzione. I repository vengono assegnati agli slot di concorrenza nell'ordine in cui sono stati scoperti; non esiste una coda con priorità. Dai ai repository pesanti una propria strategia con scope `--include` se hai bisogno di una pianificazione più granulare.

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

Questo comportamento predefinito è deliberato. Eseguire due backup cold in parallelo sullo stesso datastore causerebbe contesa sul percorso di congelamento, sul caricamento e sui sidecar per repository in `/var/run/rediacc/cold-backup-<guid>.status.json`. Attendere dietro un'istanza in esecuzione è meglio che stressare gli stessi dati da due direzioni. Il lock del datastore lo impone: una seconda esecuzione a freddo trova il lock occupato ed è rifiutata subito, senza aver fermato nulla.

**Implicazione per il monitoraggio.** Un backup bloccato (ad esempio, un caricamento inceppato su un blackhole di rete) scarta silenziosamente ogni attivazione successiva del timer. Lo scheduler non emette alcun allarme. Controllare `systemctl show <unit> -p ActiveEnterTimestamp`: se il servizio è in `activating` da più tempo del previsto (ad esempio, più di 48 ore su un timer notturno), investigare.

**Se si ha bisogno che ogni attivazione pianificata venga eseguita**, cambiare il timer da `OnCalendar=<cron>` a `OnUnitInactiveSec=<interval>`. Questo si attiva N ore dopo il completamento dell'esecuzione precedente anziché su uno schedule fisso, quindi le esecuzioni lunghe non causano scartamenti. Spostano semplicemente la prossima esecuzione più avanti. Il compromesso è lo slittamento dello schedule: il tuo notturno alle 03:00 diventa "24 ore dopo la fine dell'ultimo".

### Snapshot, Interruzioni e Spazio nel Pool

Ogni push opera da uno snapshot momentaneo del datastore, quindi i dati caricati sono coerenti anche mentre i repository continuano a scrivere. Mentre il backup è in esecuzione, quello snapshot continua a fare riferimento a ogni blocco che condivide con i repository attivi: eliminazioni e [trim](/it/docs/repositories#reclaim-space-trim) liberano meno spazio nel pool finché il ciclo non termina e lo snapshot viene eliminato. Il [report sulla salute dello storage](/it/docs/monitoring#storage-health) mostra quanto spazio gli snapshot di backup stanno attualmente bloccando.

Le interruzioni sono sicure. Fermare il servizio (o riavviare la macchina) fa sì che il backup interrompa il trasferimento ed elimini il suo snapshot prima di uscire; la prossima esecuzione pianificata riprende da dove si era fermata, poiché le celle già memorizzate non vengono ricaricate. Se il processo viene terminato in modo troppo brusco per poter fare pulizia (perdita di alimentazione), lo snapshot orfano viene rilevato e rimosso automaticamente dal gestore dello storage entro pochi minuti.

### Definire una Strategia

Il default canonico è una divisione in due strategie: uno stream hot orario veloce che cattura ogni repository e uno stream cold settimanale più lento che mette in pausa i container per snapshot app-consistent. Entrambi scrivono nello stesso storage a chunk, e i blocchi condivisi vengono memorizzati una sola volta anziché per ogni stream.

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
  --include shop --include mail \
  --enable
```

`--destination <name>` assegna un nome alla destinazione all'interno della strategia; è un'etichetta che scegli tu, e descrive lo storage a chunk. `--include` elenca i repository da sottoporre a backup, e ripeterlo ne aggiunge altri. Omettilo e la strategia copre ogni repository sul datastore. I nomi corrispondono al nome del repository nella configurazione locale (senza `:tag`).

`--exclude` viene rifiutato per una destinazione di storage a chunk anziché scartato silenziosamente, perché il `backup snapshot` sottostante seleziona i repository nominandoli e non ha un proprio meccanismo di esclusione. Rispettarlo significherebbe eseguire il backup di repository che avevi chiesto di lasciare fuori. Delimita invece una strategia con `--include`, così ciò che copre un'esecuzione pianificata è scritto anziché dedotto.

| Opzione | Descrizione |
|--------|-------------|
| `<strategy>` (posizionale) | Nome della strategia (usato per il binding alla macchina) |
| `--destination <name>` | Nome della destinazione all'interno della strategia. Per default, lo storage a chunk |
| `--storage <name>` | Optare per il tipo di destinazione rclone dismesso. Uno schedule che lo usa non può essere distribuito |
| `--cron <expression>` | Espressione cron (ad es. `"0 2 * * *"` per ogni giorno alle 2:00) |
| `--mode <hot\|cold>` | Modalità di backup |
| `--bwlimit <limit>` | Limite di banda per i caricamenti (ad es. `10M`) |
| `--include <repos>` | Repository coperti da questa strategia (ripetibile) |
| `--exclude <repos>` | Repository da saltare (ripetibile). Rifiutato su una destinazione di storage a chunk |
| `--folder <path>` | Sottocartella all'interno di un bucket rclone. Rifiutato su una destinazione di storage a chunk |
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

Una strategia non associata a nessuna macchina non viene mai distribuita. Associane una o più a una macchina:

```bash
rdc backup strategy bind hourly-hot --machine hostinger
rdc backup strategy bind weekly-cold --machine hostinger
rdc backup strategy unbind weekly-cold --machine hostinger
```

L'associazione viene registrata nella tua configurazione come elenco sulla macchina, che è ciò che `rdc backup schedule` legge per decidere quali unit distribuire:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **Il binding è solo configurazione locale.** Definire una strategia e collegarla a una macchina non modifica la macchina. Esegui `rdc backup schedule -m <machine>` (vedi [Distribuisci lo Schedule sulla Macchina](#deploy-schedule-to-machine)) per distribuire i timer systemd, e rilancialo dopo ogni modifica di strategia o binding.

## Scegliere tra Hot e Cold e il filtraggio per repository

### Hot vs cold in sintesi

| | Hot | Cold |
|---|-----|------|
| **Consistenza** | Crash-consistent (immagine congelata durante l'esecuzione) | Application-consistent (stop > snapshot > start) |
| **Downtime** | Nessuno | Finestra di stop+start per repository (tipicamente 5-120 s) |
| **Frequenza adatta** | Alta (ad es. oraria) | Bassa (ad es. giornaliera o settimanale) |
| **Uso tipico** | Rete di sicurezza ad alta frequenza | Backup pianificato con consistenza garantita |

**Hot** è il default corretto per le esecuzioni ad alta frequenza. I servizi continuano a girare mentre lo snapshot viene effettuato, quindi la finestra di backup non interrompe gli utenti. Lo snapshot è crash-consistent: equivale a quello che si otterrebbe dopo uno spegnimento non pulito. Per la maggior parte dei database moderni e delle code di messaggi questo è accettabile.

**Cold** è appropriato quando si ha bisogno di uno snapshot application-consistent garantito e si può accettare un breve riavvio per repository. I servizi vengono fermati prima dello snapshot e riavviati prima che inizi il caricamento, quindi un caricamento lento o fallito non prolunga mai la finestra di downtime. Vedere [Semantica del Backup Cold](#cold-backup-semantics) per il modello di garanzia completo.

Entrambe le modalità scrivono nello stesso storage a chunk, e la modalità riguarda come viene trattato il repository mentre l'immagine è congelata, non dove finiscono i dati. Un repository coperto sia da uno schedule hot orario sia da uno cold settimanale memorizza le celle condivise una sola volta anziché due.

### Delimitare i repository per strategia

Una strategia senza `--include` copre ogni repository sul datastore. Ripetere `--include` la restringe ai repository che nomini, confrontati con il nome del repository nella configurazione locale (senza `:tag`).

```bash
# Strategia hot: backup di tutto ogni ora
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Strategia cold: settimanale, e solo i repository che hanno bisogno di essere messi in pausa
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

### Quando tenere un repository fuori dalla strategia hot frequente

Nomina i repository che vuoi nell'esecuzione ad alta frequenza, invece di lasciare che prenda tutto, quando:

- Un repository è grande e **completamente rigenerabile** dai dati sorgente già presenti nel volume, quindi ogni backup orario spende banda senza aggiungere valore di recupero.
- L'esecuzione del backup supererebbe il proprio intervallo di schedule alla velocità di caricamento disponibile.

**Esempio.** Un repository `analytics-demo` contiene circa 114 GB di tabelle Postgres derivate che possono essere ricostruite dai file di dump CSV grezzi già memorizzati all'interno dello stesso volume. Con un limite di caricamento di 6 MB/s, un primo snapshot di quel repository richiede oltre 5 ore. Eseguirlo ogni ora significa che ogni esecuzione è ancora in corso quando parte quella successiva, il che causa lo scarto silenzioso di ogni attivazione successiva (vedere [Backup di Lunga Durata e Schedule Sovrapposti](#long-running-backups-and-overlapping-schedules)). Elencare gli altri repository in `hourly-hot` e lasciare `analytics-demo` a `weekly-cold` significa che viene eseguito il backup una volta alla settimana invece di mai.

> **Se i dati sono puramente rigenerabili**, considera se è necessario eseguirne il backup. Un'alternativa è eseguire il backup solo degli input sorgente grezzi (i dump CSV, in questo esempio) e saltare la copia derivata del tutto. Un backup cold settimanale degli input sorgente è molto più piccolo e completamente sufficiente per il recupero.

Un repository coperto da entrambe le strategie ottiene snapshot orari crash-consistent e uno settimanale application-consistent. `rdc backup manifests <repo>` li mostra insieme, e le celle che condividono vengono memorizzate una sola volta.

## Operazioni di Backup

### Distribuisci lo Schedule sulla Macchina

Invia le strategie associate a una macchina come timer systemd:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

La distribuzione è un riconciliatore di stato. Legge i file unit correnti e lo stato systemd sulla macchina, li confronta con ciò che la configurazione produrrebbe (SHA-256 per file) e tocca solo le unit il cui contenuto è effettivamente cambiato. La riesecuzione senza modifiche alla configurazione è una no-op: nessuna scrittura, nessun `daemon-reload`, nessun cambio di timer.

`--dry-run` stampa il piano per ogni strategia (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) senza toccare la macchina. Combinare con `--debug` per stampare anche i corpi delle unit generate, con le credenziali oscurate. Una unit di storage a chunk non ne porta nessuna in partenza: la macchina si autentica con la propria licenza di repository firmata, e il server restituisce un permesso di breve durata, quindi nulla di sensibile viene scritto nel file unit.

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
| `--provision <provider>` | Effettua il provisioning automatico della macchina di destinazione tramite questo provider cloud (ad es. `hetzner`, `linode`) |
| `--checkpoint` | Crea un checkpoint CRIU prima della migrazione, così anche la memoria del processo si sposta |
| `--delta-base <guid>` | GUID di base immutabile per il delta del cutover. Per default, la base della prima fase |
| `--strategy <strategy>` | Strategia di delta dei blocchi per il cutover: `auto`, `physical` o `shared` |
| `--skip-dns` | Salta l'aggiornamento dei record DNS dopo la migrazione |
| `--keep-source` | Conserva le immagini sorgente dopo uno spostamento riuscito |
| `--bwlimit <limit>` | Limite di banda per il trasferimento (ad es. `50M`) |

La migrazione trasferisce i dati del repository cifrato tramite rsync in due fasi: un trasferimento in blocco mentre il repository continua a girare, poi un breve stop per il delta. La migrazione **sposta** il repository, quindi le immagini sorgente vengono eliminate una volta riuscito lo spostamento. Passa `--keep-source` per conservarle. Questa è la differenza tra `repo migrate` e `repo push`: push lascia la sorgente in esecuzione e intatta.

## Leggere un Archivio Scritto Prima della Dismissione

`rdc storage` è ciò che resta del ramo rclone, ed è di sola lettura. Non può più essere una destinazione di backup, ma può ancora accedere a un archivio che vi è stato scritto.

```bash
# Registra un remote già configurato per rclone.
rdc storage import rclone.conf
rdc storage list

# Guarda cosa contiene. Questo esegue l'rclone sul tuo PATH.
rdc storage browse my-storage
```

`import` legge un file di configurazione rclone e registra i remote nella tua configurazione; i tipi supportati sono S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob e Swift.

**`browse` richiede `rclone` sul tuo PATH.** Esegue l'rclone installato sulla macchina su cui stai digitando; non esiste più una copia integrata. Senza di esso te lo dice e non fa nient'altro.

Inviare a, scaricare da, elencare e ripristinare un backend di storage sono dismessi; ognuno rifiuta l'esecuzione e indica il comando che lo sostituisce.

## Buone Pratiche

- Pianifica snapshot cold giornalieri per copie app-consistent dei dati critici
- Usa gli snapshot hot per esecuzioni ad alta frequenza dove è richiesto zero downtime
- Testa periodicamente i ripristini. `rdc backup restore --as <new-name>` non sovrascrive nulla, quindi un'esercitazione è sicura su una macchina live
- Imposta una politica di conservazione invece di potare a mano, così la finestra che mantieni è scritta
- Mantieni una copia da macchina a macchina oltre agli snapshot se vuoi una copia su hardware che controlli
- Tieni le credenziali al sicuro; i backup sono cifrati ma la credenziale LUKS è necessaria per il ripristino
