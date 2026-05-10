---
title: "Installazione"
description: "Installa la CLI rdc sul tuo laptop con un singolo comando e verificala con rdc doctor. È già disponibile per Linux, macOS e Windows."
category: "Tutorials"
subcategory: essentials
order: 1
language: it
sourceHash: "99d4ca1a4f89278e"
---

# Installazione

Installare `rdc` richiede tre passi: apri la pagina di installazione, scegli il tuo sistema operativo, incolla il comando nel terminale. Di solito termina in un minuto o due.

## Guarda il tutorial

![Tutorial: Installazione](/assets/tutorials/tutorial-installation.cast)

## I tre passi

![Panoramica dei tre passi](/img/tutorials/tutorial-installation/slide-1.svg)

1. Apri la [pagina di installazione](/it/install).
2. Scegli il tuo sistema operativo.
3. Copia il comando di installazione e incollalo nel tuo terminale.

## Installa sulla tua piattaforma

La pagina di installazione genera il comando giusto per te, ma ecco i one-liner canonici.

**Linux / macOS:**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> Il prefisso `time` è un trucco della shell che mostra quanto tempo ha impiegato un comando. Lo usiamo in tutta questa serie così puoi vedere la velocità reale di ogni passo. È opzionale: rimuovilo se non lo vuoi.

## Verifica l'installazione

Una volta terminato lo script, controlla che tutto ciò di cui `rdc` ha bisogno sia presente:

```bash
time rdc doctor
```

`rdc doctor` controlla Node, SSH e le restanti dipendenze di `rdc` e segnala eventuali mancanze.

## Perche' `rdc` si trova sul tuo laptop

![rdc sul tuo laptop, renet sul server](/img/tutorials/tutorial-installation/slide-2.svg)

`rdc` è la CLI sul tuo laptop. Il server esegue un componente separato chiamato `renet`, che `rdc` provisiona e gestisce via SSH. Non hai mai bisogno di fare SSH su un server manualmente: `rdc` lo fa per te.

Configureremo tutto correttamente nei prossimi due tutorial.

---

Successivo: [Configurazione della Chiave SSH](/it/docs/tutorial-ssh-keys).
