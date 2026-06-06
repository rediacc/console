---
title: "Git-like branching"
description: "Tratta i fork copy-on-write come commit git: congela un fork in uno stato immutabile, assegna nomi ai branch, ripristina i commit in fork scrivibili e unisci le storie senza mai mutare un repository live."
category: Reference
subcategory: advanced
order: 41
language: it
sourceHash: "2448559f0fcfc0e0"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Git-like branching

Ecco il modello concettuale: Rediacc trasforma i fork copy-on-write in una storia di versioni simile a git. Ogni fork immutabile è un **commit**: un'immagine byte-stabile e congelata che rifiuta il mount. I branch sono riferimenti nominati che puntano a un commit. `rdc repo checkout` clona tramite reflink un commit in un fork di lavoro scrivibile, e `rdc repo merge` combina due linee di storia senza mai mutare un repository live in place.

Il modello si mappa su due store. La **macchina è l'object store**: i commit sono immagini di fork immutabili che vivono sul datastore. Il **config CLI è il ref store**: i nomi dei branch, l'`HEAD` corrente e il reflog vivono nella config locale, non sulla macchina. È la stessa divisione che git usa tra `.git/objects` e `.git/refs`.

## Quando usarlo

Usa il branching quando un fork ha guadagnato un nome. Un agente AI ha operato libero in un fork di produzione, il risultato sembra buono, e vuoi un checkpoint congelato e nominato a cui tornare o promuovere in seguito: `rdc repo commit` lo congela, `rdc repo branch` lo nomina. Prima di una migrazione rischiosa, committa il fork di lavoro così hai un punto di rollback esatto che è garantito non cambiare mai (un commit immutabile rifiuta il mount, quindi nulla può scriverci). Per confrontare due checkpoint, `rdc repo diff` funziona tra qualsiasi due commit perché condividono un antenato copy-on-write. Per riportare una linea di lavoro revisionata su un fork target, `rdc repo merge` costruisce il risultato in un clone reflink e lo scambia atomicamente, così un target in esecuzione non viene mai corrotto a metà del merge.

Non usarlo come sostituto di `rdc repo fork` quando hai bisogno solo di una copia usa-e-getta. Un fork semplice è l'unità giusta per l'isolamento effimero per-test. I commit aggiungono valore quando uno stato vale la pena di essere conservato, nominato o distribuito.

## Come commit e fork si relazionano

Un repository è un file immagine LUKS su un pool btrfs. Un fork è un reflink a tempo costante di quella immagine, quindi forkare un repository da 1 GB e uno da 100 GB ha lo stesso costo. Un **commit** è un fork che è stato marcato immutabile: renet rifiuta di montarlo, il che mantiene la sua immagine byte-stabile per sempre. Quella byte-stabilità è ciò che rende un commit un punto di rollback affidabile e una base deterministica per il push delta cross-machine.

`rdc repo commit` registra il messaggio di commit, l'autore, il timestamp e il commit parent **all'interno del volume** (così i metadati viaggiano con l'immagine al push) e li specchia anche fuori dal volume (così `rdc repo log` può percorrere la storia senza sbloccare nulla). Il fork di lavoro che hai committato continua invariato, esattamente come git lascia il tuo working tree intatto dopo un commit.

## Comandi

### rdc repo commit

Congela un fork di lavoro montato in un nuovo commit immutabile.

```bash
rdc repo commit --name <fork> --message "<message>" -m <machine>
```

| Opzione | Descrizione | Default |
|---------|-------------|---------|
| `--name <name>` | Fork di lavoro da committare. Deve essere montato. Obbligatorio. | obbligatorio |
| `--message <msg>` | Messaggio di commit. Obbligatorio. | obbligatorio |
| `--author <author>` | Autore del commit registrato nei metadati. | non impostato |
| `-m, --machine <name>` | Macchina target. Obbligatorio. | obbligatorio |
| `--debug` | Diagnostica verbosa su stderr. | off |

Il nuovo commit viene registrato nel config locale con `immutable: true`, e il `headCommit` del fork di lavoro avanza per puntarvi. Committare un repository immutabile viene rifiutato: prima eseguine il checkout in un fork scrivibile.

### rdc repo branch

Crea un riferimento di branch nominato che punta al commit corrente di un fork di lavoro.

```bash
rdc repo branch --branch <name> --name <fork>
```

| Opzione | Descrizione | Default |
|---------|-------------|---------|
| `--branch <branch>` | Nome del nuovo branch. Obbligatorio. | obbligatorio |
| `--name <name>` | Fork di lavoro il cui commit corrente il branch punta. Obbligatorio. | obbligatorio |

Questa è un'operazione solo sul config. Non viene eseguito nessun lavoro sulla macchina. Il riferimento al branch mappa un nome al `headCommit` del fork di lavoro, quindi il fork deve avere almeno un commit prima.

### rdc repo checkout

Clona tramite reflink un commit immutabile (o la punta di un branch) in un nuovo fork di lavoro scrivibile.

```bash
rdc repo checkout --ref <commit> --tag <newFork> -m <machine>
rdc repo checkout --ref <branchName> --from <fork> --tag <newFork> -m <machine>
```

| Opzione | Descrizione | Default |
|---------|-------------|---------|
| `--ref <commit\|branch>` | GUID del commit da fare checkout, o nome di un branch quando si usa `--from`. Obbligatorio. | obbligatorio |
| `--tag <name>` | Nome per il nuovo fork di lavoro scrivibile. Obbligatorio. | obbligatorio |
| `-m, --machine <name>` | Macchina target. Obbligatorio. | obbligatorio |
| `--from <workingFork>` | Risolve `--ref` come nome di branch su questo fork di lavoro. | commit diretto |
| `--debug` | Diagnostica verbosa su stderr. | off |
| `--skip-router-restart` | Salta il riavvio del router. | off |

Il checkout riusa il percorso reflink del fork, quindi è quasi istantaneo e a tempo costante indipendentemente dalla dimensione del repository. Il `headCommit` del nuovo fork di lavoro viene impostato al commit che hai fatto checkout.

### rdc repo log

Percorre la storia dei commit raggiungibile da un fork di lavoro o da un commit.

```bash
rdc repo log --name <fork> -m <machine>
```

| Opzione | Descrizione | Default |
|---------|-------------|---------|
| `--name <name>` | Fork di lavoro o commit da cui iniziare la percorrenza della storia. Obbligatorio. | obbligatorio |
| `-m, --machine <name>` | Macchina target. Obbligatorio. | obbligatorio |
| `--json` | Output della storia dei commit come JSON. | off |
| `--debug` | Diagnostica verbosa su stderr. | off |

`log` percorre la catena parent registrata da `rdc repo commit`, leggendo il mirror di stato fuori-volume così nessun commit viene sbloccato o montato. È solo lettura.

### rdc repo merge

Fa il merge di un commit sorgente o fork in un fork di lavoro target, senza mutare il target live in place.

```bash
rdc repo merge --name <target> --from <source> -m <machine>
rdc repo merge --name <target> --from <source> --resolve theirs -m <machine>
```

| Opzione | Descrizione | Default |
|---------|-------------|---------|
| `--name <name>` | Fork di lavoro target in cui fare il merge. Obbligatorio. | obbligatorio |
| `--from <source>` | Commit sorgente o fork da cui fare il merge. Obbligatorio. | obbligatorio |
| `-m, --machine <name>` | Macchina target. Obbligatorio. | obbligatorio |
| `--force` | Chiude un target montato o in esecuzione prima del merge. Non muta mai un mount live. | off |
| `--resolve <ours\|theirs>` | Merge three-way per file: applica le modifiche per-file della sorgente sul target, mantenendo (`ours`) o prendendo (`theirs`) la versione della sorgente per i file modificati su entrambi i lati. Ometti per take-theirs dell'intera immagine. | off |
| `--base <guid>` | Commit antenato comune per il merge three-way (usato con `--resolve`). Default al parent del commit sorgente, o al commit corrente del target. | auto |
| `--debug` | Diagnostica verbosa su stderr. | off |

Il risultato viene costruito in un clone reflink e scambiato atomicamente con un marker crash-safe, così un merge interrotto lascia il target originale intatto. Un target montato o in esecuzione viene rifiutato a meno che non si usi `--force`, che chiude il target prima dello scambio.

Senza `--resolve`, il merge è un take-theirs dell'intera immagine (il target diventa la sorgente). Con `--resolve`, è un merge three-way per file contro il parent registrato del commit sorgente: i file cambiati solo su un lato vengono presi da quel lato, e i file cambiati su entrambi i lati vengono risolti dal flag. I percorsi in conflitto vengono segnalati.

### rdc repo gc

Raccoglie i commit object immutabili su una macchina che nessun branch o HEAD raggiunge.

```bash
rdc repo gc -m <machine>            # anteprima dry-run (default)
rdc repo gc --apply -m <machine>    # elimina i commit irraggiungibili
```

| Opzione | Descrizione | Default |
|---------|-------------|---------|
| `-m, --machine <name>` | Macchina su cui raccogliere. Obbligatorio. | obbligatorio |
| `--apply` | Elimina effettivamente i commit irraggiungibili (altrimenti anteprima dry-run). | off |
| `--debug` | Diagnostica verbosa su stderr. | off |

La raggiungibilità viene calcolata dal config locale (il ref store): l'insieme dei commit raggiungibili seguendo ogni punta di branch e HEAD giù per la catena parent. I commit immutabili sulla macchina fuori da quell'insieme sono irraggiungibili. Un object montato o un fork di lavoro non vengono mai raccolti.

### rdc repo fsck

Valida i riferimenti del config contro gli object presenti su una macchina.

```bash
rdc repo fsck -m <machine>
```

| Opzione | Descrizione | Default |
|---------|-------------|---------|
| `-m, --machine <name>` | Macchina da controllare. Obbligatorio. | obbligatorio |

Segnala i riferimenti pendenti (una punta di branch o HEAD che punta a un GUID senza object sulla macchina) e i commit orfani (un commit immutabile sulla macchina che nessun riferimento raggiunge). È solo lettura; recupera gli orfani con `rdc repo gc --apply`.

### Fork immutabili

`rdc repo fork --immutable` marca il nuovo fork in sola lettura alla creazione, producendo una base equivalente a un commit senza un passo `commit` separato.

```bash
rdc repo fork --parent <name> --tag <tag> --immutable -m <machine>
```

Un fork immutabile rifiuta il mount, il che mantiene la sua immagine byte-stabile per sempre. Utile come base congelata per il push delta cross-machine, dove la base deve essere identica su entrambi i lati. Per apportare modifiche, fanne il checkout (o un altro fork) in una copia scrivibile.

## Esempi

### Committa un fork di lavoro

```bash
$ rdc repo commit --name myapp:work --message "schema migration applied" -m server-1
Committed 4f3c2a1b9d8e: schema migration applied
```

### Commit con autore esplicito

```bash
$ rdc repo commit --name myapp:work --message "nightly snapshot" --author ci-bot -m server-1
Committed 7a1b2c3d4e5f: nightly snapshot
```

### Nomina un branch al commit corrente

```bash
$ rdc repo branch --branch staging --name myapp:work
Branch "staging" -> 4f3c2a1b9d8e
```

### Fai checkout di un commit in un nuovo fork scrivibile

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag rollback-test -m server-1
```

### Fai checkout della punta di un branch per nome

Con `--from`, il valore `--ref` viene risolto come nome di branch sul fork di lavoro indicato:

```bash
$ rdc repo checkout --ref staging --from myapp:work --tag staging-copy -m server-1
```

### Percorri la storia

```bash
$ rdc repo log --name myapp:work -m server-1
commit 4f3c2a1b9d8e
  Author: ci-bot  Date: 2026-05-29T10:14:02Z
  schema migration applied
commit 9d8e7a1b2c3d
  Author: ci-bot  Date: 2026-05-28T22:01:55Z
  initial import
```

### Storia come JSON

`--json` emette il walk strutturato, dal più recente al meno recente:

```bash
$ rdc repo log --name myapp:work --json -m server-1
{
  "success": true,
  "start": "4f3c2a1b9d8e",
  "entries": [
    {
      "guid": "4f3c2a1b9d8e",
      "message": "schema migration applied",
      "author": "ci-bot",
      "parent": "9d8e7a1b2c3d",
      "committed_at": "2026-05-29T10:14:02Z",
      "immutable": true
    }
  ]
}
```

### Confronta due commit

`rdc repo diff` funziona tra qualsiasi due commit perché condividono un antenato copy-on-write. Fai checkout di un commit, poi confrontalo con un altro:

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag review -m server-1
$ rdc repo diff --name review --base myapp:work -m server-1
M  db/schema.sql

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Vedi [rdc repo diff](/it/docs/repo-diff) per il riferimento completo al diff.

### Fai merge di una linea revisionata

```bash
$ rdc repo merge --name myapp:main --from myapp:work -m server-1
Merged myapp:work into myapp:main
```

### Fai merge in un target in esecuzione

Un target montato o in esecuzione viene rifiutato a meno che non si usi `--force`, che lo chiude prima:

```bash
$ rdc repo merge --name myapp:main --from myapp:work --force -m server-1
Merged myapp:work into myapp:main
```

### Merge three-way per file

Due fork (`feature` e `hotfix`) fatti checkout dallo stesso commit hanno ciascuno cambiato alcuni file. `--resolve theirs` incorpora la sorgente (`hotfix`) nel target (`feature`): i file cambiati solo da un lato vengono presi da quel lato, e i file cambiati da entrambi i lati vengono risolti alla sorgente. La base viene rilevata automaticamente dall'antenato condiviso (o pinnala con `--base`):

```bash
$ rdc repo merge --name myapp:feature --from myapp:hotfix --resolve theirs -m server-1
Merged myapp:hotfix into myapp:feature (three-way); 1 conflict(s) resolved --theirs: [config/app.yaml]
```

`config/app.yaml` è stato cambiato da entrambi i lati ed è stato risolto alla sorgente; un file aggiunto solo da `hotfix` viene applicato, e un file cambiato solo da `feature` viene mantenuto. I percorsi in conflitto vengono segnalati così puoi rivederli.

### Crea una base immutabile direttamente

```bash
$ rdc repo fork --parent myapp --tag baseline-v1 --immutable -m server-1
```

## Push e pull delta

Un'immagine immutabile e byte-stabile è anche la base per il **trasferimento delta a livello di blocco**. Quando la stessa base immutabile esiste su due macchine, un push o pull può calcolare i blocchi modificati rispetto a quella base e spostare solo quelli, invece di scansionare l'intera immagine cifrata. Un repository da 1 GB con pochi blocchi modificati si trasferisce in megabyte.

Di norma non devi passare una base a mano. Dopo un push completo, la CLI conserva l'immagine pushata come base immutabile su entrambe le macchine e la registra, così il **prossimo** push di quel repository spedisce automaticamente solo il delta, senza nessun flag, anche per un fork che esiste già sul target. (Un re-push *completo* di un fork esistente richiede ancora `--force`, poiché sostituisce l'intera immagine invece di applicare un delta verificato.) Passa `--delta-base <guid>` per pinnare una base specifica, e `--strategy <auto|physical|shared>` per controllare come vengono rilevati i blocchi modificati (`auto` è corretto in quasi tutti i casi).

```bash
# Il primo push è un trasferimento completo; conserva anche una base riutilizzabile su entrambi i lati.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Dopo le modifiche locali, il prossimo push spedisce solo i blocchi modificati, senza flag.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Pinna una base esplicita (un commit immutabile presente su entrambe le macchine).
$ rdc repo push --name myapp:work --to-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Il delta funziona anche al contrario, pullando solo i blocchi modificati da una sorgente macchina.
$ rdc repo pull --name myapp:work --from-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Re-pull di un repository locale esistente (sovrascrivilo) con --force.
$ rdc repo pull --name myapp:work --from-machine backup-1 --force -m server-1
```

Il trasferimento delta si applica solo tra macchine (un remoto con la base FIEMAP). I push verso lo storage cloud object trasferiscono sempre l'immagine completa. La base deve essere byte-identica su entrambi i lati, il che è esattamente ciò che garantisce un commit immutabile o un fork `--immutable`.

## Schema JSON

`rdc repo log --json` avvolge il risultato di renet nell'envelope standard. La storia percorsa si trova in `entries`, dal più recente al meno recente:

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `success` | boolean | Se il walk è stato completato. |
| `start` | string | GUID da cui è partito il walk. |
| `entries` | array | Un oggetto per commit, dal più recente al meno recente. |
| `entries[].guid` | string | GUID del commit. |
| `entries[].message` | string | Messaggio del commit. Omesso quando vuoto. |
| `entries[].author` | string | Autore del commit. Omesso quando vuoto. |
| `entries[].parent` | string | GUID del commit parent. Omesso alla radice. |
| `entries[].committed_at` | string | Timestamp del commit RFC 3339. Omesso quando non impostato. |
| `entries[].immutable` | boolean | Se il commit è marcato in sola lettura (sempre true per un commit vero). |

Per i campi dell'envelope e le regole di rilevamento automatico che emettono JSON in ambienti non-TTY, vedi il [Riferimento Output JSON](/it/docs/ai-agents-json-output).

## Limitazioni

- **I riferimenti sono locali.** I nomi dei branch, `HEAD` e il reflog vivono nel config CLI, non sulla macchina. Pushare un commit su un'altra macchina spedisce l'object del commit e i suoi metadati in-volume, ma il riferimento al branch è un concetto lato config.
- **Un commit rifiuta il mount.** Questo è il punto: l'immutabilità è ciò che rende un commit byte-stabile. Per eseguire o modificare un commit, fanne il checkout in un fork di lavoro scrivibile prima.
- **La risoluzione del merge è a livello di file, non di riga.** Sia il take-theirs dell'intera immagine (senza `--resolve`) che il three-way per file (`--resolve ours|theirs`) sono supportati. Il merge three-way risolve i conflitti un intero file alla volta secondo il flag; non produce hunk a livello di riga o marker di merge all'interno di un file.
- **La storia è una catena parent.** `rdc repo log` percorre il singolo link `parent` registrato al momento del commit. Si ferma quando raggiunge un commit i cui metadati non sono presenti sulla macchina interrogata.

## Vedi anche

- [rdc repo diff](/it/docs/repo-diff). Diff a livello di file tra qualsiasi due commit o fork correlati.
- [Repository](/it/docs/repositories). Crea, forka, monta e opera i repository.
