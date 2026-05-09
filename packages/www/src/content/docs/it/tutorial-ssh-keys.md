---
title: "Configurazione della Chiave SSH"
description: "Configura la tua chiave SSH affinché rdc possa connettersi ai tuoi server senza password. È un'operazione da fare una volta sola: poi è tutto più comodo."
category: "Tutorials"
subcategory: essentials
order: 2
language: it
sourceHash: "009a1bd345e93413"
---

# Configurazione della Chiave SSH

`rdc` si connette ai tuoi server tramite SSH, quindi ogni server deve fidarsi della tua chiave SSH. Tre passi in totale: due sono una configurazione una tantum, uno si ripete per ogni nuovo server che aggiungi.

## Guarda il tutorial

![Tutorial: Configurazione della chiave SSH](/assets/tutorials/tutorial-ssh-keys.cast)

## I tre passi

![Genera, copia, registra](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. **Genera** una chiave SSH sul tuo laptop. Una volta, per sempre.
2. **Copia** sul tuo server. Ripeti per ogni nuovo server.
3. **Registra** la chiave con `rdc`. Una volta, per sempre.

## Passo 1: Genera una chiave

Se hai già una chiave che vuoi usare, passa al passo successivo. Altrimenti:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519` è il default moderno: piccolo, veloce e ben supportato.

## Passo 2: Copia sul tuo server

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

Sostituisci `user` e `your-server-ip` con l'utente SSH e l'IP del tuo server. Ti verrà chiesta la password del server un'ultima volta. Dopo questo, l'autenticazione con password non sarà più necessaria.

## Passo 3: Registra la chiave con `rdc`

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

Fatto. Da ora in poi, ogni comando `rdc` si autentica con questa chiave. Niente più password, niente più prompt interattivi.

---

Successivo: [Aggiungere il Tuo Primo Server](/it/docs/tutorial-add-server).
