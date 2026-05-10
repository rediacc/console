---
title: "Lavorare con il Tuo Repo"
description: "Instrada una porta verso il browser, esegui comandi all'interno della sandbox e sincronizza file tra il tuo laptop e il repo. È più comodo di quanto si pensi: tre comandi coprono tutto ciò di cui hai bisogno."
category: "Tutorials"
subcategory: essentials
order: 6
language: it
sourceHash: "3d56eb69e72c1a5a"
---

# Lavorare con il Tuo Repo

La tua app è in esecuzione, ma finora l'hai vista solo tramite `docker ps`. Tre comandi coprono il flusso di lavoro quotidiano: **tunnel** per vedere l'app nel browser, **term** per eseguire comandi all'interno della sandbox, **sync** per spostare file tra il tuo laptop e il repo.

## Guarda il tutorial

![Tutorial: Lavorare con il tuo repo](/assets/tutorials/tutorial-work-with-repo.cast)

## I tre quotidiani

![Tunnel, term, sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel**: apri la tua app nel browser.
2. **Term**: esegui un comando all'interno della sandbox.
3. **Sync**: sposta file dentro e fuori.

## Tunnel: vedi la tua app nel browser

L'app gira sul server, non sul tuo laptop. Instrada la porta di un container tramite SSH:

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

Apri `localhost` nel tuo browser: la tua app è lì. Premi `Ctrl+C` quando hai finito.

Per un container diverso, cambia `-c` e scegli la porta:

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term: esegui comandi all'interno del repo

Salta VS Code quando hai solo bisogno di una shell:

```bash
rdc term connect -m my-server -r my-app
```

Ora sei all'interno della sandbox del repo. Provalo:

```bash
time docker ps
```

Vedi solo i container di `my-app`: la stessa vista che avresti in VS Code.

Per comandi una tantum, usa `-c` e salta la shell interattiva:

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync: sposta file tra laptop e repo

Carica una cartella dal tuo laptop nel repo:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

Scarica i file indietro:

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

Fai prima un'anteprima se non sei sicuro: `--dry-run` mostra cosa cambierebbe senza copiare nulla effettivamente:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel, term, sync. Tre comandi coprono il ciclo quotidiano.

---

Successivo: [Fork di un Repository](/it/docs/tutorial-forking).
