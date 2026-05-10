---
title: "Modalità di Produzione"
description: "Esegui la tua app scollegata dal tuo laptop e sopravvivi ai riavvii del server con l'avvio automatico. È più affidabile così: nessuna dipendenza dalla connessione locale."
category: "Tutorials"
subcategory: advanced
order: 10
language: it
sourceHash: "0e070fcd877900ab"
---

# Modalità di Produzione

Finora hai eseguito l'app con `renet dev up` dall'interno del repo. Ottimo per lo sviluppo. Per la produzione, gestisci tutto dal tuo laptop con `rdc`: chiudi il laptop e l'app continua a girare.

## Guarda il tutorial

![Tutorial: Modalità di produzione](/assets/tutorials/tutorial-production-mode.cast)

## Sviluppo vs produzione

La differenza e' semplice:

- `renet dev up` gira **all'interno del repo**. Devi essere connesso.
- `rdc repo up` gira **dal tuo laptop**. Nessuna connessione necessaria dopo.

Tre azioni ti portano da dev a prod:

![Ferma, avvia, avvio automatico](/img/tutorials/tutorial-production-mode/slide-1.svg)

## Passo 1: Ferma la sessione di sviluppo

Connettiti al repo e portalo giu':

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## Passo 2: Avvia in modalita' di produzione

Dal terminale del tuo laptop:

```bash
time rdc repo up --name my-app -m my-server
```

Fatto. La tua app è in esecuzione e puoi chiudere il laptop. Il `Rediaccfile` gestisce tutto: `rdc repo up` chiama la stessa funzione `up` che chiamava `renet dev up`. Stesso `Rediaccfile`, modo diverso di invocarlo.

## Passo 3: Sopravvivi ai riavvii del server

Assicurati che la tua app torni automaticamente quando il server si riavvia:

```bash
time rdc repo autostart enable --name my-app -m my-server
```

Verifica quali repo hanno l'avvio automatico abilitato:

```bash
time rdc repo autostart list -m my-server
```

## Fermare in produzione

Quando hai bisogno di fermare la tua app:

```bash
time rdc repo down --name my-app -m my-server
```

Un comando per avviare, uno per fermare: tutto dal tuo laptop.

---

Successivo: [Backup e Ripristino](/it/docs/tutorial-backup-restore).
