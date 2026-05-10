---
title: "Aggiungere il Tuo Primo Server"
description: "Registra il tuo primo server con rdc, eseguine il provisioning e comprendi l'architettura rdc + renet. È più rapido di quanto ci si aspetti."
category: "Tutorials"
subcategory: essentials
order: 3
language: it
sourceHash: "2b5de59f61cfb88c"
---

# Aggiungere il Tuo Primo Server

Prima di aggiungere un server, è utile capire come funziona `rdc`. Rediacc ha un'architettura a due strumenti: `rdc` sul tuo laptop, `renet` sul server.

## Guarda il tutorial

![Tutorial: Aggiungere il tuo primo server](/assets/tutorials/tutorial-add-server.cast)

## Perché due strumenti?

![rdc sul laptop, renet sul server, SSH in mezzo](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`** è la CLI sul tuo laptop. Digiti i comandi qui.
- **`renet`** è l'orchestratore sul server. Gestisce crittografia, Docker e isolamento.

Quando esegui un comando localmente, `rdc` si connette tramite SSH ed esegue `renet` sul server. Non hai mai bisogno di fare SSH manualmente sui tuoi server: `rdc` lo fa per te.

## Passo 1: Registra il server

Comunica a `rdc` le informazioni sul server. Sostituisci nome, IP e utente con i tuoi.

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## Passo 2: Esegui il provisioning

La configurazione installa `renet` e crea il datastore cifrato sul server.

```bash
time rdc config machine setup --name my-server
```

Al termine, il tuo server è pronto ad ospitare repository.

## Dove si trova la configurazione

Verifica cosa sa `rdc` della tua configurazione:

```bash
time rdc config show
```

Oppure apri direttamente il file JSON grezzo:

```bash
vim ~/.config/rediacc/rediacc.json
```

Questo singolo file contiene tutto: macchine, repo, chiave SSH, credenziali di crittografia. Copialo su un altro laptop ed è subito pronto all'uso anche da quella macchina.

---

Successivo: [Creare il Tuo Primo Repository](/it/docs/tutorial-create-repo).
