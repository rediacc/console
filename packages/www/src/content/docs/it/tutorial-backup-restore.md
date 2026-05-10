---
title: "Backup e Ripristino"
description: "Invia il tuo repository a uno storage esterno e ripristinalo su un nuovo server quando ne hai bisogno. È la soluzione più sicura per proteggere i tuoi dati."
category: "Tutorials"
subcategory: advanced
order: 11
language: it
sourceHash: "8b48f3b19352aebe"
---

# Backup e Ripristino

La tua app è in produzione. Ora assicurati di non perderla mai. `rdc` può inviare l'intero repository, app, database, file e configurazioni, a uno storage esterno e recuperarlo in qualsiasi momento. Sopravvivi a ransomware, guasti hardware, qualsiasi cosa.

## Guarda il tutorial

![Tutorial: Backup e ripristino](/assets/tutorials/tutorial-backup-restore.cast)

## Tre passi

![Configura, invia, ripristina](/img/tutorials/tutorial-backup-restore/slide-1.svg)

1. **Configura** un provider di storage.
2. **Invia** un backup.
3. **Ripristina** quando ne hai bisogno.

## Passo 1: Configura lo storage

Hai bisogno di un file di configurazione `rclone`. Se già usi rclone, importalo direttamente:

```bash
time rdc config storage import --file rclone.conf
```

Questo supporta S3, B2, Google Drive, Dropbox e molti altri. Verifica cosa è configurato:

```bash
time rdc config storage list
```

## Passo 2: Invia un backup

```bash
time rdc repo push --name my-app -m my-server --to my-storage
```

L'intero repository, app, database, file e tutto il resto, è ora nel backup. Poiché il repository è cifrato, anche il backup è cifrato. Nessuna gestione aggiuntiva delle chiavi.

Elenca i tuoi backup in qualsiasi momento:

```bash
time rdc repo backup list --from my-storage -m my-server
```

## Perché nessun downtime?

L'app continua a funzionare mentre il backup viene caricato. Come può essere coerente?

Stessa logica di un [fork](/it/docs/tutorial-forking). `rdc` fa prima il fork, poi carica il fork. Il fork cattura il momento; la tua app live continua a funzionare. Nessun downtime, nessuna incoerenza.

## Passo 3: Ripristina su un nuovo server

Supponiamo che il tuo server si guasti. Configura un nuovo server, aggiungilo a `rdc` e scarica:

```bash
time rdc repo pull --name my-app -m new-server --from my-storage
```

Poi avvialo:

```bash
time rdc repo up --name my-app -m new-server
```

La tua app è tornata. Stessi dati, stessi container, macchina diversa.

## Backup più veloci: da macchina a macchina

Puoi anche inviare direttamente tra macchine, senza storage cloud nel mezzo:

```bash
time rdc repo push --name my-app -m my-server --to-machine backup-server
```

> **Consiglio professionale.** I caricamenti su storage inviano sempre tutto. Da macchina a macchina viene inviata solo la differenza. Il primo invio da macchina a macchina richiede il tempo normale, ma ogni invio successivo è molto più veloce: ottimo per i backup frequenti.

---

Successivo: [Monitoraggio](/it/docs/tutorial-monitoring).
