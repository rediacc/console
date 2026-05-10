---
title: "Fare il Fork di un Repository"
description: "Clona un intero repository, app, database, file, in pochi secondi. Qualsiasi dimensione. Zero disco aggiuntivo. È una delle funzionalità più utili della piattaforma."
category: "Tutorials"
subcategory: advanced
order: 7
language: it
sourceHash: "9237f00dce2ee5ec"
---

# Fare il Fork di un Repository

Questa è la funzionalità killer: clona un intero ambiente di produzione, l'app, il database, i file di configurazione, in pochi secondi. Qualsiasi dimensione. Zero disco aggiuntivo. Fai il fork tutte le volte che vuoi.

Il motto: **clona la produzione, non rompere nulla.**

## Guarda il tutorial

![Tutorial: Fork di un repository](/assets/tutorials/tutorial-forking.cast)

## Crea qualcosa da perdere

Prima, dai all'app in esecuzione un file per dimostrare l'isolamento del fork. Apri il repo in VS Code:

```bash
rdc vscode connect -m my-server -r my-app
```

All'interno del repo, crea un file marcatore:

```bash
time echo "Hello from production" > index.html
```

Ora fai il fork.

## Fork

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![Il parent si divide in cloni indipendenti](/img/tutorials/tutorial-forking/slide-1.svg)

Un solo comando. Ha clonato tutto, l'app, il database, i file di configurazione, ed è successo in pochi secondi. Eseguilo di nuovo e ottieni un altro clone indipendente.

## Perché è così veloce?

![Condividere un link a una cartella ha la stessa velocita' indipendentemente dalla dimensione della cartella](/img/tutorials/tutorial-forking/slide-2.svg)

Immagina di condividere un link a una cartella. Il link è lo stesso che la cartella sia piccola o enorme: la cartella è pesante, il link è leggero.

![1 GB, 100 GB, 1 TB: stesso tempo, ogni volta](/img/tutorials/tutorial-forking/slide-3.svg)

Il fork funziona allo stesso modo. 1 GB, 100 GB, 1 TB: stesso tempo, ogni volta.

## Cosa è condiviso, cosa è tuo

![Molti specchi, un sole: base condivisa, le tue modifiche sono tue](/img/tutorials/tutorial-forking/slide-4.svg)

Pensa al repo parent come al sole. Non puoi tenere il sole, ma puoi tenere uno specchio che lo cattura, e quello specchio e' il tuo fork. Dipingi sullo specchio e i tuoi disegni sono tuoi. Il sole rimane lo stesso, indipendentemente da quanti specchi gli siano rivolti.

> Non puoi tenere il sole, ma puoi tenerlo in uno specchio.

## E se il parent cambia dopo?


![Un fork e' una fotografia congelata; il parent continua a scorrere come un fiume](/img/tutorials/tutorial-forking/slide-5.svg)

Ora pensa a un fiume. L'acqua continua a scorrere: ogni momento è diverso. Quando fai il fork, scatti una fotografia del fiume, congelata in quel momento. Il fiume continua a scorrere. La tua fotografia no.

Se il repo parent cambia dopo, il tuo fork rimane dov'era.

> Non puoi tenere un fiume, ma puoi tenerlo in una foto.

## L'utilizzo del disco rimane stabile

![Cinque fork di un repo da 100 GB: ancora circa 100 GB in totale](/img/tutorials/tutorial-forking/slide-6.svg)

Ecco perché il tuo disco non esplode. Cinque fork di un repo da 100 GB? Ancora circa 100 GB in totale. Paghi disco solo per ciò che cambi in ogni fork.

> Fai il fork cinque volte se vuoi: il tuo disco non se ne accorgerà nemmeno.

## Cosa i fork *non* ereditano: i segreti

C'è una cosa che il fork deliberatamente non segue: i segreti. Un fork inizia senza chiavi API, senza password del database, senza token Stripe. Ecco perché "clona la produzione, non rompere nulla" funziona davvero: la tua sandbox non può addebitare ai clienti reali perché non può fingersi te. Configuriamo questo correttamente nel tutorial [Gestione dei Segreti](/it/docs/tutorial-managing-secrets).

## Verifica l'isolamento

Elenca entrambi i repo affiancati:

```bash
time rdc repo list -m my-server
```

Vedrai `my-app` e `my-app:experiment` in esecuzione contemporaneamente.

Nel repo originale, controlla cosa sta girando:

```bash
time docker ps
```

Nota il tempo di attività: questi sono i container originali. Ora passa al fork:

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

Stesse immagini, ma il tempo di attività è recente: questi si sono avviati quando è stato creato il fork.

Rendi la differenza ancora più evidente: aggiungi un container solo nel fork:

```bash
time docker run --rm -it -d nginx
time docker ps
```

Nginx e' in esecuzione, ma solo all'interno di questo fork.

Prova qualcosa di distruttivo:

```bash
time rm index.html
```

Sparito qui. Ora torna all'originale:

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

Nessun nginx. I container del fork sono rimasti nel fork. E `index.html` è ancora qui, intatto. L'originale non ha saputo nulla di ciò che è successo. Stesse immagini, daemon Docker separati, filesystem separati.

## Pulizia

Quando hai finito, elimina semplicemente il fork:

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

L'originale rimane esattamente com'era. **Fork, sperimenta, rompi cose, elimina.** Nessun rischio.

---

Successivo: [Gestione dei Segreti](/it/docs/tutorial-managing-secrets).
