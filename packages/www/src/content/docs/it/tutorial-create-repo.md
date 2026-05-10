---
title: "Creare il Tuo Primo Repository"
description: "Crea un repository cifrato sul tuo server e aprilo in VS Code. È isolato dagli altri repository: la qualità dell'isolamento è garantita."
category: "Tutorials"
subcategory: essentials
order: 4
language: it
sourceHash: "1294b0494f20671b"
---

# Creare il Tuo Primo Repository

Un repository Rediacc è un singolo file cifrato sul tuo server. Quando viene montato, diventa una cartella con il proprio daemon Docker e i propri dati applicativi: completamente isolato, completamente portabile.

Pensalo come una chiavetta USB per la produzione: un file a riposo, un server in esecuzione.

## Guarda il tutorial

![Tutorial: Creare il tuo primo repository](/assets/tutorials/tutorial-create-repo.cast)

## File su disco, ambiente quando montato

![Il file cifrato viene montato come cartella isolata](/img/tutorials/tutorial-create-repo/slide-1.svg)

La forma su disco e' una singola immagine cifrata. Quando viene montata, ottieni:

- Un daemon Docker dedicato (separato da quello dell'host)
- Dati applicativi all'interno del volume cifrato
- IP loopback che non vanno in conflitto con nient'altro sulla macchina

I repository sono portabili. Puoi spostarne uno tra macchine, farne il backup o forkarlo istantaneamente. Ogni repo e' isolato da ogni altro repo sullo stesso server.

## Creane uno

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

Questo crea un repository cifrato da 2 GB su `my-server`. Verificalo:

```bash
time rdc repo list -m my-server
```

## Aprilo in VS Code

```bash
rdc vscode connect -m my-server -r my-app
```

VS Code si apre direttamente all'interno del repository. Nota che lo spazio di lavoro è vuoto: questo è il tuo ambiente isolato. Tutto ciò che crei qui vive all'interno del volume cifrato, invisibile a qualsiasi altro repo sullo stesso server.

---

Successivo: [Distribuire la Tua Prima App](/it/docs/tutorial-deploy-app).
