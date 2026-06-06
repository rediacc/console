---
title: "rdc repo diff"
description: "Mostra un diff a livello di file nello stile di git tra due repository separate tramite copy-on-write confrontando le loro immagini crittate a livello di blocco, senza decrittazione."
category: Reference
subcategory: advanced
order: 40
language: it
sourceHash: "c72fbcc13e7e77ed"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc repo diff

`rdc repo diff` segnala quali file sono cambiati tra due repository correlati: una fork e il suo parent, o qualsiasi due repository che condividono un antenato copy-on-write. Passa `--name <fork>` per confrontare una fork rispetto al parent che la config locale registra per essa, oppure aggiungi `--base <repo>` per confrontare rispetto a un repository correlato arbitrario, dove `--base` è il lato base (vecchio) e `--name` è il lato target (nuovo). Il comando è di sola lettura e non decritta mai le immagini. Confronta i file a livello di blocco sulla macchina remota, quindi il costo è determinato dal numero di blocchi modificati, non dalla dimensione del repository: un repository di 1 GB e uno di 100 GB con le stesse modifiche richiedono lo stesso tempo. Se l'intero repository è cambiato, il numero di blocchi scala con le dimensioni e così anche il costo.

## Quando usarlo

Quindi: usa `repo diff` prima di promuovere una fork. Un agente di AI si è scatenato in una copia fork della produzione e vuoi vedere esattamente quali file ha toccato prima di unire di nuovo la modifica: `repo diff --name <fork> -m <machine>` ti fornisce l'elenco dei file in pochi secondi. Pochi secondi. Dopo un ripristino di disaster recovery, confronta la fork ripristinata rispetto allo snapshot che doveva riprodurre per confermare che il set di file previsto è tornato e nient'altro è andato alla deriva. Per una fork di lunga durata che è stata eseguita insieme al suo parent per settimane, il diff mostra la divergenza accumulata (modifiche di config, accumulo di log, migrazioni dello schema) senza montare ed esplorare manualmente entrambi gli alberi.

Non usarlo tra repository non correlati. I due lati devono condividere un antenato copy-on-write, perché il confronto funziona sulla cronologia dei blocchi condivisi. Non è neanche uno strumento di diff binario: `--content` produce output a livello di riga solo per file di testo, e i binari segnalano `Binary files differ`.

## Riferimento del comando

### Sinossi

```bash
rdc repo diff --name <fork> -m <machine>            # diff a fork rispetto al suo parent
rdc repo diff --name <fork> --base <repo> -m <machine>   # diff rispetto a un repository correlato arbitrario
```

### Opzioni

| Opzione | Descrizione | Predefinito |
|---------|------------|-------------|
| `--name <name>` | Repository da ispezionare (il lato target, nuovo). Obbligatorio. | obbligatorio |
| `--base <name>` | Repository rispetto a cui confrontare (il lato base, vecchio). Per impostazione predefinita, il parent di `--name`, risolto dalla config locale. | parent di `--name` |
| (nessun flag di formato) | Output di stato dei nomi: una lettera A/M/D/R colorata per file modificato più un riepilogo di una riga. | attivo |
| `--name-only` | Un percorso modificato per riga, nessuna lettera di stato. Compatibile con pipe. | disattivo |
| `--stat` | Entità della modifica per file (delta di byte e blocchi) con un riepilogo dei totali. | disattivo |
| `--content <path>` | Diff di testo unificato di un singolo file. Solo testo; i binari segnalano `Binary files differ`. | disattivo |
| `--json` | Output strutturato per agenti e script. | disattivo |
| `--fast` | Salta il passaggio di conferma del content-hash e fidati del filtro dei blocchi. Più veloce, ma potrebbe segnalare eccessivamente i file come Modificati. | disattivo |
| `-m, --machine <name>` | Macchina target. Obbligatorio. | obbligatorio |
| `--debug` | Diagnostica dettagliata su stderr. | disattivo |
| `--skip-router-restart` | Salta il passaggio di riavvio del router. | disattivo |

## Esempi

### Name-status predefinito rispetto al parent

Con solo `--name`, la fork viene confrontata rispetto al parent registrato nella config locale. Qui la fork `test-1gb:fork1` ha un file modificato:

```bash
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Confronto rispetto a una base esplicita

Passa `--base` per confrontare rispetto a un repository correlato arbitrario. `--base` è il lato base (vecchio), `--name` è il lato target (nuovo):

```bash
$ rdc repo diff --name test-1gb:fork1 --base test-1gb:latest -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Entità della modifica con `--stat`

`--stat` aggiunge il delta di byte e blocchi per file e un riepilogo dei totali:

```bash
$ rdc repo diff --name test-1gb:fork1 --stat -m hostinger
 hello.txt | +8 bytes, 1 block

1 file changed, 4096 bytes touched
```

### Solo i percorsi, trasmessi a uno strumento

`--name-only` stampa un percorso per riga senza lettera di stato, pronto per essere trasmesso a un altro comando:

```bash
$ rdc repo diff --name test-1gb:fork1 --name-only -m hostinger | xargs -I{} echo "review: {}"
review: hello.txt
```

### Diff a livello di riga di un file

`--content` produce un diff unificato di un singolo file di testo:

```bash
$ rdc repo diff --name test-1gb:fork1 --content hello.txt -m hostinger
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-the original line of text in the parent
+the original line of text in the parent, now edited
```

### Filtraggio JSON con jq

`--json` emette l'envelope strutturato su stdout, quindi si connette perfettamente a `jq`:

```bash
$ rdc repo diff --name test-1gb:fork1 --json -m hostinger | jq '.data.entries[] | select(.status=="M")'
{
  "status": "M",
  "path": "/hello.txt",
  "type": "file",
  "old_size": 53,
  "size": 61,
  "bytes_changed": 4096,
  "blocks_changed": 1,
  "inode": 13,
  "content_changed": true,
  "mode_changed": false,
  "uid_changed": false,
  "gid_changed": false
}
```

## Formati di output

### Name-status (predefinito)

Ogni file modificato riceve una lettera di stato e il suo percorso. `A` è aggiunto, `M` modificato, `D` eliminato, `R` rinominato (con il percorso vecchio mostrato). Una riga di riepilogo segue con il conteggio per categoria.

### `--name-only`

Un percorso per riga, nessuna lettera di stato, nessun riepilogo. Usalo quando un comando a valle vuole un elenco pulito dei file.

### `--stat`

Ogni riga contiene il delta di byte e il delta di blocchi del file. Un piè di pagina segnala il conteggio totale dei file e il totale dei byte toccati. Questo mostra dove si trova il peso di una modifica, non solo quali file si sono mossi.

### `--content <path>`

Un diff unificato standard (`---`/`+++` intestazioni, `@@` hunk) per un file di testo. I file binari segnalano `Binary files differ` e non producono hunk.

### `--json`

Il risultato strutturato completo. I dati vanno a stdout; l'avanzamento e la diagnostica vanno a stderr, quindi il JSON si connette perfettamente a `jq` o un altro parser anche mentre l'avanzamento viene stampato.

## Schema JSON

La CLI racchiude il risultato di renet nell'envelope standard (`success`, `command`, `data`, `errors`, `warnings`, `metrics`). Il risultato del diff si trova in `data` con campi snake_case:

```json
{
  "success": true,
  "command": "repo diff",
  "data": {
    "base": "<base-guid>",
    "target": "<target-guid>",
    "added": 0,
    "modified": 1,
    "deleted": 0,
    "renamed": 0,
    "strategy": "shared",
    "fast": false,
    "degraded": false,
    "block_size": 4096,
    "total_bytes_changed": 4096,
    "entries": [
      {
        "status": "M",
        "path": "/hello.txt",
        "type": "file",
        "old_size": 53,
        "size": 61,
        "bytes_changed": 4096,
        "blocks_changed": 1,
        "inode": 13,
        "content_changed": true,
        "mode_changed": false,
        "uid_changed": false,
        "gid_changed": false
      }
    ]
  }
}
```

Ogni oggetto in `entries[]` descrive un percorso modificato:

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `status` | `A` \| `M` \| `D` \| `R` | Aggiunto, Modificato, Eliminato o Rinominato. |
| `path` | string | Percorso sul lato target (o lato base per un'eliminazione). |
| `old_path` | string | Percorso precedente. Presente solo nei rinominamenti. |
| `type` | `file` \| `dir` \| `symlink` \| `other` | Tipo di voce. |
| `old_size` | number | Dimensione in byte sul lato base. |
| `size` | number | Dimensione in byte sul lato target. |
| `bytes_changed` | number | Byte che differiscono, arrotondati a blocchi interi. |
| `blocks_changed` | number | Numero di blocchi modificati. |
| `inode` | number | Numero di inode, utilizzato per il rilevamento dei rinominamenti. |
| `content_changed` | boolean | Se il contenuto del file (non solo i metadati) è cambiato. |
| `mode_changed` | boolean | Se la modalità del file è cambiata. `old_mode`/`new_mode` sono presenti quando vero. |
| `uid_changed` | boolean | Se il proprietario è cambiato. `old_uid`/`new_uid` sono presenti quando vero. |
| `gid_changed` | boolean | Se il gruppo è cambiato. `old_gid`/`new_gid` sono presenti quando vero. |
| `old_target` / `new_target` | string | Target dei symlink. Presenti per i symlink modificati. |

Per i campi dell'envelope e le regole di rilevamento automatico che emettono JSON in ambienti non TTY, consulta il [JSON Output Reference](/en/docs/ai-agents-json-output).

## Come funziona

Un repository è un file di immagine LUKS2 su un pool btrfs, e una fork è un reflink a tempo costante di quell'immagine. `repo diff` confronta le due immagini crittate a livello di blocco tramite FIEMAP, leggendo solo i metadati del filesystem e non decriptando mai nulla. Sposta gli offset del testo cifrato modificati dall'offset dei dati LUKS per ottenere gli offset del dispositivo ext4, quindi mappa questi offset di nuovo ai nomi dei file attraverso la mappa estesa ext4 di ogni file. Un'ultima passeggiata di identità dell'inode di entrambi i mount riconcilia il risultato in voci Aggiunto, Modificato, Eliminato e Rinominato. Poiché il lavoro è limitato dal conteggio dei blocchi modificati, il diff è indipendente dalla dimensione del repository, e poiché riutilizza un mount live in posizione, non disturba mai un repository in esecuzione. Il meccanismo completo è descritto in [Git diff for encrypted disk images](/en/blog/git-diff-for-encrypted-disk-images).

## Limitazioni

- **Solo fork correlate.** Entrambi i lati devono condividere un antenato copy-on-write. Non c'è un confronto significativo a livello di blocco tra repository non correlati.
- **Il rilevamento dei rinominamenti è basato su inode.** Un file viene segnalato come rinominato quando lo stesso inode appare in un nuovo percorso. Un delete-then-recreate (un nuovo inode) viene mostrato come una voce Eliminata più una voce Aggiunta, non un rinominamento.
- **`--content` è solo testo.** Produce hunk a livello di riga per file di testo. I binari segnalano `Binary files differ`.
- **`--fast` potrebbe segnalare eccessivamente i file come Modificati.** Si fida del filtro dei blocchi e salta la conferma del content-hash, quindi un file i cui blocchi si sono mossi senza modificare il contenuto può apparire come Modificato.
- **Il tempo di percorrenza dell'estensione scala con la frammentazione, non con le dimensioni.** Un filesystem molto frammentato ha più estensioni da mappare, il che allunga il percorso anche quando il volume di byte delle modifiche è piccolo.

## Vedi anche

- [rdc repo fork](/en/docs/repositories). Crea la fork copy-on-write che questo comando confronta.
- [rdc repo status](/en/docs/repositories). Stato attuale di un singolo repository.
- [rdc repo cat](/en/docs/repositories). Leggi un singolo file da un repository.
