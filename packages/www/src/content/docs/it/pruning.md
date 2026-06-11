---
title: "Pruning"
description: "Rimuovi backup orfani, snapshot obsoleti, immagini di repository e residui di config locali per recuperare spazio su disco e mantenere lo stato coerente."
category: "Guides"
order: 12
language: it
sourceHash: "d2700c2ac4473962"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Pruning

Il pruning elimina lo stato che non corrisponde più a una risorsa attiva. Tre comandi coprono tre ambiti diversi:

| Comando | Cosa pulisce | Dove risiede la fonte di verità |
|---|---|---|
| `rdc storage prune --name <storage> -m <machine>` | Backup orfani nell'archiviazione cloud | Config CLI locale (verificata rispetto alla macchina esecutrice per la sicurezza del mount) |
| `rdc machine prune --name <machine>` | Artefatti del datastore sulla macchina (sempre); immagini di repository orfane o sconosciute (opt-in) | Config CLI locale + lo specchio `.interim/state` della macchina |
| `rdc config prune` | Residui del config locale (cache certificati, archivi scaduti, riferimenti incrociati pendenti) | Solo config CLI locale |

I tre sono indipendenti. Puoi eseguirne uno qualsiasi senza gli altri. Condividono un modello di sicurezza comune descritto in [Sicurezza](#safety-model) di seguito.

Il pruning rimuove lo stato lasciato da risorse eliminate. Per recuperare spazio occupato da repository *attivi* (blocchi che i loro filesystem hanno liberato ma il pool ancora detiene), usa invece [`rdc repo trim`](/it/docs/repositories#recupera-spazio-trim); i due sono complementari.

## Preflight di sicurezza del mount

`storage prune` e `machine prune --prune-unknown` eseguono entrambi un **preflight di sicurezza del mount** prima di eliminare qualsiasi cosa: interrogano la macchina esecutrice per le repository attualmente montate o in esecuzione, le intersecano con i candidati all'eliminazione e **si rifiutano di eliminare un candidato ancora attivo sulla macchina**. Eliminare il backup fuori macchina di una repository montata, o eliminare un'immagine di repository attiva, è un vero e proprio rischio di perdita di dati. Il preflight rende impossibile farlo accidentalmente.

Per ignorare questo controllo (raro; solo quando sai genuinamente che lo stato attivo è errato), passa `--force-delete-mounted`. Questo è un flag separato da `--force` (che controlla il periodo di grazia dell'archivio) in modo che le due valvole di sicurezza rimangano distinte.

## Storage Prune

Scansiona un provider di archiviazione ed elimina i backup i cui GUID non compaiono più in nessun file di config locale.

```bash
# Solo anteprima - mostra cosa verrebbe eliminato
rdc storage prune --name my-s3 -m server-1 --dry-run

# Elimina effettivamente i backup orfani (comportamento predefinito)
rdc storage prune --name my-s3 -m server-1

# Override del periodo di grazia (predefinito 7 giorni)
rdc storage prune --name my-s3 -m server-1 --grace-days 14

# Override del controllo di sicurezza del mount (usare con cautela)
rdc storage prune --name my-s3 -m server-1 --force-delete-mounted
```

`--machine` è richiesto perché le chiamate rclone vengono eseguite sulla macchina esecutrice, non sul tuo laptop. Non si aspetta che i client abbiano rclone installato localmente. Le credenziali di archiviazione provengono comunque dal tuo config locale; la macchina è solo il runner rclone.

### Cosa controlla

1. Elenca tutti i GUID di backup nell'archiviazione nominata (in entrambe le sottodirectory `hot/` e `cold/`. Vedi [Backup & Restore](/it/docs/backup-restore#scheduled-backups)).
2. Scansiona ogni file di config su disco (`~/.config/rediacc/*.json`).
3. Un backup è **orfano** se il suo GUID non è referenziato dalla sezione repositories di nessun config.
4. Le repository archiviate di recente entro il periodo di grazia sono **protette** anche se rimosse dal config attivo.
5. Preflight di sicurezza del mount: i GUID attualmente montati su `--machine` vengono saltati e segnalati, mai eliminati.

### Prestazioni

Le eliminazioni sono raggruppate per sottopercorso di archiviazione: una chiamata rclone per directory `hot/` o `cold/` indipendentemente da quanti GUID vengono rimossi. Un backlog di 11 orfani si riduce da circa 50 secondi di overhead SSH a un singolo round-trip per sottopercorso.

## Machine Prune

Pulisce le risorse sulla macchina in tre fasi. La fase 1 viene sempre eseguita; le fasi 2 e 3 sono opt-in e possono essere combinate.

### Fase 1: Pulizia del datastore (viene sempre eseguita)

Rimuove tutto ciò che viene lasciato indietro quando una repository viene eliminata o quando una convenzione di denominazione viene dismessa. Ogni categoria viene scansionata indipendentemente. Eseguire il pruning ripetutamente è sicuro: è un singolo passaggio idempotente, quindi gli orfani che l'ultima esecuzione ha perso vengono catturati dalla successiva.

| Categoria | Cosa rimuove |
|---------|-----------------|
| Directory di mount vuote | Directory `mounts/<guid>/` senza immagine di repository corrispondente |
| Directory immovable orfane | Directory `immovable/<guid>/` senza immagine di repository corrispondente |
| File di lock obsoleti | `repositories/.lock-<guid>` per le repository eliminate |
| Snapshot di backup obsoleti | `.snapshot-*` e `.backup-*` lasciati da esecuzioni di backup interrotte |
| Directory sandbox VS Code orfane | `.interim/sandbox/<name>` per repository non più attive sulla macchina |
| Chain iptables orfane | Chain `REDIACC_WILDCARD_<N>` e `DOCKER_ISOLATED_NET_<N>` per reti eliminate |
| Voci authorized_keys orfane | Righe `sandbox-gateway <repo> --guid <uuid>` il cui `--guid` non corrisponde più a una directory di mount attiva |

La scansione di authorized_keys controlla `/home/*/.ssh/authorized_keys` e `/root/.ssh/authorized_keys`. Una voce viene mantenuta solo se il suo tag `--guid` mappa a un GUID di directory di mount attiva, quindi le repository attualmente distribuite sulla macchina vengono sempre preserve indipendentemente da dove appare il loro nome sul disco. Le voci legacy scritte prima che renet iniziasse ad aggiungere il tag `--guid` non possono essere validate e vengono sempre segnalate come orfane.

```bash
# Dry-run, mostra cosa verrebbe rimosso (nessuna modifica applicata)
rdc machine prune --name server-1 --dry-run

# Esegui la pulizia
rdc machine prune --name server-1
```

> **Pulizia a cascata.** Alcune categorie dipendono da quelle precedenti. Ad esempio, eliminare le directory di mount vuote potrebbe esporre ulteriori orfani sandbox il cui mount di supporto è appena scomparso. Eseguire `rdc machine prune` una seconda volta coglie la cascata e completa la pulizia. Il dry-run finale termina con `No orphaned resources found. Datastore is clean.` quando non rimane nulla da fare.

### Fase 2: `--orphaned-repos` (approssimativo)

Con `--orphaned-repos`, la CLI elimina anche le immagini di repository sulla macchina che non compaiono in **nessun** file di config locale.

```bash
rdc machine prune --name server-1 --orphaned-repos --dry-run
rdc machine prune --name server-1 --orphaned-repos
```

Questo è **approssimativo**. Elimina tutto ciò che non è nel tuo config locale, inclusi i fork legittimi gestiti da altri strumenti o il checkout CLI di un altro operatore. Se lo specchio `.interim/state` di renet identifica correttamente una repository come fork ma il config locale non l'ha mai vista, questa fase la rimuove comunque. Preferisci la fase 3 (`--prune-unknown`) quando vuoi essere conservativo.

### Fase 3: `--prune-unknown` (chirurgico)

Con `--prune-unknown`, la CLI elimina solo le repository che **entrambi** i segnali non riescono a classificare: non in nessun config locale **e** nessuna voce contrassegnata come fork nello specchio `.interim/state` della macchina (vedi [Repositories. Colonna `Type`](/it/docs/repositories#type-column-and-the-state-mirror)).

```bash
rdc machine prune --name server-1 --prune-unknown --dry-run
rdc machine prune --name server-1 --prune-unknown
```

In pratica `--prune-unknown` è quello che vuoi per la pulizia di routine; `--orphaned-repos` è corretto solo quando sei certo che il tuo config locale sia l'inventario completo e autorevole di ogni repository sulla macchina. Gli orfani legacy pre-specchio e le repository la cui voce di config è stata eliminata per errore rientrano entrambi nel bucket "sconosciuto". Sono genuinamente incerti, e il flag chirurgico chiede all'operatore di riconoscerlo esplicitamente.

Il preflight di sicurezza del mount viene eseguito anche in questa fase: una repository attualmente montata su `--machine` viene segnalata e saltata a meno che non venga passato `--force-delete-mounted`.

```bash
# Combinato: pulizia completa della macchina con il percorso chirurgico consapevole dei fork
rdc machine prune --name server-1 --prune-unknown
```

## Config Prune

Elimina i residui obsoleti **all'interno del file di config locale** in `~/.config/rediacc/<config>.json`. Puramente locale. Nessun SSH, nessuna chiamata renet. Vengono puliti tre bucket:

1. **Voci della cache dei certificati ACME** il cui anchor (GUID, nome repository o nome macchina) non è più nel config attivo. I wildcard del certificato non possono mai instradare da nessuna parte, quindi sono peso morto.
2. **Repository archiviate scadute** in `resources.deletedRepositories[]`. Voci il cui `deletedAt` è più vecchio di `defaults.pruneGraceDays` (predefinito 7 giorni). Le voci entro la grazia vengono segnalate (con i giorni rimanenti) e mantenute.
3. **Riferimenti incrociati pendenti** tra i bucket di config:
   - Voci `resources.machines.<m>.backupStrategies[]` che nominano una strategia non più esistente.
   - Voci `resources.backupStrategies.<s>.exclude[]` e `include[]` che nominano una repository non più esistente.
   - Destinazioni di archiviazione il cui storage target è mancante. Contrassegnate come avvertimento, non rimosse automaticamente (la rimozione automatica cambierebbe la semantica della strategia).

```bash
# Solo anteprima
rdc config prune --dry-run

# Applica (comportamento predefinito)
rdc config prune

# Limita a un bucket
rdc config prune --certs-only
rdc config prune --archives-only
rdc config prune --refs-only

# Elimina TUTTE le repository archiviate indipendentemente dalla grazia
rdc config prune --purge-archived

# Override della finestra di grazia dell'archivio per questa invocazione
rdc config prune --grace-days 30
```

### Cosa NON tocca

- Risorse attive (macchine, archiviazioni, repository, strategie di backup, provider cloud).
- Credenziali, il blocco account, il blocco di cifratura, i valori predefiniti.
- `vaultContent` di archiviazione (incluso il `access_token` OneDrive scaduto. Il refresh_token conia ancora nuovi token; il pruning forcerebbe la ri-autenticazione).
- Voci `knownHosts` (il percorso di aggiornamento automatico è `rdc config machine scan-keys`).
- L'array di blob di certificati compressi (`infra.acmeCertCache.<base>.data[]`) viene ricostruito automaticamente dall'elenco di certificati puliti; non perdi nessuna catena che copra ancora un nome mantenuto.

### Esempio pratico

Output da una vera esecuzione su una macchina con quattro wildcard GUID orfani e due wildcard di nome macchina obsoleti:

```text
Scanning local config for stale leftovers...
6 cert cache entry/entries would be removed:
  *.linode-1.rediacc.io  (unknown machine linode-1)
  *.marketing.linode-1.rediacc.io  (unknown machine linode-1)
  *.5b749533-99be-446c-9fe3-e6d0eec905a6.hostinger.rediacc.io  (unknown GUID 5b749533-…)
  *.5d09f3a6-9558-4df1-8a6e-b63140a6a7a6.hostinger.rediacc.io  (unknown GUID 5d09f3a6-…)
  *.e18d8c0f-367e-43c7-919e-2dbc59db4b5e.hostinger.rediacc.io  (unknown GUID e18d8c0f-…)
  *.9806c9b8-6bfb-4a87-9eaa-4b757ce1daca.hostinger.rediacc.io  (unknown GUID 9806c9b8-…)
Dry run: 6 change(s) would be applied. Re-run without --dry-run to commit.
```

I nomi di certificato il cui anchor è una macchina, repository o GUID attivo vengono lasciati intatti, come pure qualsiasi wildcard a etichetta singola `<service>.<base>` o radice `*.<base>`.

## Migrazione: backfill dello specchio di stato

Lo specchio `.interim/state/<guid>/.rediacc.json` che alimenta `--prune-unknown` e la colonna `Type` in `rdc repo list -m` viene scritto:

- **Al momento del fork** (`rdc repo fork`). Immediatamente, anche prima che il fork venga mai montato.
- **Ad ogni salvataggio di stato** (`rdc repo mount` e qualsiasi operazione che aggiorna lo stato della repository). Per le repository create prima che il codice dello specchio fosse rilasciato.

Le repository create **prima dell'esistenza dello specchio e non ri-montate dall'aggiornamento** non hanno file specchio. Compaiono come `unknown` in `rdc repo list -m` anche se alcune sono legittimamente fork. Per risolvere questo problema per gli orfani legacy, esegui il backfill one-shot sulla macchina:

```bash
sudo /usr/local/bin/renet repository backfill-state-mirror \
    --datastore /mnt/rediacc \
    --mark-as-fork <guid1>,<guid2>,<guid3>
```

Il backfill copia lo stato in-volume attivo sullo specchio per le repository attualmente montate e scrive uno specchio sintetico contrassegnato come fork per i GUID elencati sotto `--mark-as-fork`. Dopo il backfill, i backup pianificati smettono di caricare i fork elencati (la pipeline di caricamento controlla lo specchio per `is_fork: true`).

## Modello di Sicurezza

Tutti e tre i comandi sono sicuri per default in configurazioni multi-config.

### Consapevolezza multi-config

`storage prune` e `machine prune --orphaned-repos` scansionano **tutti** i file di config in `~/.config/rediacc/`, non solo quello attivo. Una repository referenziata da `production.json` non verrà eliminata anche se assente da `staging.json`. Questo previene l'eliminazione accidentale quando i config sono scoped a diversi ambienti.

### Periodo di grazia

Quando una repository viene rimossa da un config con `--archive-config`, la sua voce di credenziali viene spostata in `resources.deletedRepositories[]` con un timestamp `deletedAt`. I comandi di pruning rispettano un periodo di grazia (predefinito 7 giorni) durante il quale le repository archiviate di recente sono protette dall'eliminazione. Questo ti dà tempo di ripristinare una repository (`rdc config repository restore-archived --name <guid>`) se è stata rimossa accidentalmente. Una volta scaduta la grazia, `storage prune`, `machine prune` e `config prune` eliminano automaticamente la voce.

### Preflight di sicurezza del mount

Descritto sopra. `storage prune` e `machine prune --prune-unknown` si rifiutano di eliminare repository attualmente montate o in esecuzione sulla macchina esecutrice. Override solo con `--force-delete-mounted`.

### Applica per default; `--dry-run` per anteprima

Tutti e tre i comandi di pruning applicano le modifiche per **default**. Passa `--dry-run` per visualizzare l'anteprima senza scrivere. Questo corrisponde al verbo: "prune" è distruttivo di per sé, e il flag dry-run è il opt-out esplicito.

## Configurazione

### `pruneGraceDays`

Imposta un periodo di grazia predefinito personalizzato nel tuo file di config in modo da non dover passare `--grace-days` ogni volta:

```bash
# Imposta il periodo di grazia a 14 giorni nel config attivo
rdc config field set --pointer /defaults/pruneGraceDays --new 14
```

Il flag CLI `--grace-days` sovrascrive questo valore quando fornito.

### Precedenza

1. Flag `--grace-days <N>` (priorità più alta)
2. `pruneGraceDays` nel file di config
3. Predefinito incorporato: 7 giorni

## Buone Pratiche

- **Esegui prima il dry-run in produzione.** Visualizza sempre l'anteprima prima di eseguire un pruning distruttivo, specialmente sull'archiviazione di produzione.
- **Mantieni aggiornati i config multipli.** Storage prune e machine prune controllano tutti i config nella directory di config. Se un file di config è obsoleto o eliminato, le sue repository perdono protezione. Mantieni i file di config accurati.
- **Preferisci `--prune-unknown` rispetto a `--orphaned-repos`.** Il flag chirurgico rispetta lo specchio renet; il flag approssimativo eliminerà volentieri i fork creati da altri strumenti.
- **Usa periodi di grazia generosi per la produzione.** Il periodo di grazia predefinito di 7 giorni si adatta alla maggior parte dei workflow. Per ambienti di produzione con finestre di manutenzione poco frequenti, considera 14 o 30 giorni.
- **Pianifica storage prune dopo le esecuzioni di backup.** Abbina `storage prune` al tuo programma di backup per mantenere i costi di archiviazione sotto controllo senza intervento manuale.
- **Combina machine prune con il programma di backup.** Dopo aver distribuito i programmi di backup (`rdc machine backup schedule`), aggiungi un machine prune periodico per pulire snapshot obsoleti e artefatti del datastore orfani.
- **Esegui `config prune` periodicamente.** Il gonfiore del config locale (specialmente la cache dei certificati) si accumula silenziosamente; un `config prune --dry-run` trimestrale è sufficiente per individuarlo.
- **Fai un audit prima di usare `--force` o `--force-delete-mounted`.** Entrambi i flag ignorano i controlli di sicurezza. Usa `--force` solo quando sei certo che nessun altro config referenzia le repository in questione; usa `--force-delete-mounted` solo quando sei certo che lo stato attivo sulla macchina sia errato.
