---
title: "Distribuire la Tua Prima App"
description: "Distribuisci un'app containerizzata da un template integrato usando renet dev up. È già incluso nella CLI: nessuna configurazione aggiuntiva è necessaria."
category: "Tutorials"
subcategory: essentials
order: 5
language: it
sourceHash: "f75b5b6a716e94bf"
---

# Distribuire la Tua Prima App

Hai un repository vuoto. `rdc` include template integrati così puoi avviare app reali senza scrivere un `docker-compose` da zero. Tre passi: scegli un template, applicalo, eseguilo.

## Guarda il tutorial

![Tutorial: Distribuire la tua prima app](/assets/tutorials/tutorial-deploy-app.cast)

## Scegli, Applica, Esegui

![Scegli un template, applicalo, eseguilo](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## Passo 1: Scegli

Sfoglia i template disponibili:

```bash
time rdc repo template list
```

Vedrai configurazioni già pronte per app comuni: Postgres, Redis, web server e altro.

## Passo 2: Applica

Inserisci il template nel tuo repo. Useremo `app-postgres`:

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

Nel repo compaiono due nuovi file: `docker-compose.yml` e `Rediaccfile`. Il file compose descrive i container; il `Rediaccfile` definisce cosa succede quando l'app si avvia e si ferma: i suoi hook di ciclo di vita `up` e `down`.

## Passo 3: Esegui

Sei gia' all'interno della sandbox del repo (tramite la connessione VS Code del tutorial precedente), quindi usa `renet` direttamente:

```bash
time renet dev up
```

Fatto: la tua app è in esecuzione. Verificalo:

```bash
time docker ps
```

`docker ps` qui elenca solo i container di questo repo. Gli altri repo sullo stesso server hanno i propri daemon Docker e sono completamente invisibili da questo.

---

Successivo: [Lavorare con il Tuo Repo](/it/docs/tutorial-work-with-repo).
