---
title: "Monitoraggio"
description: "Controlla la salute dei tuoi server e repo dal tuo laptop con i comandi rdc machine. È possibile visualizzare tutto in tempo reale senza bisogno di accesso diretto al server."
category: "Tutorials"
subcategory: advanced
order: 12
language: it
sourceHash: "e6eaaed180c35e36"
sourceCommit: "be90e8e7896623c088b86360ec29c1baef2e86b4"
---

# Monitoraggio

La tua app è distribuita, online e con backup. Ora assicurati che tutto rimanga in buona salute. `rdc` ti offre un quadro completo di qualsiasi server: salute, container, repo, tutto dal tuo laptop.

## Guarda il tutorial

![Tutorial: Monitoraggio](/assets/tutorials/tutorial-monitoring.cast)

## Tre cose che puoi controllare

![Salute, container, repo](/img/tutorials/tutorial-monitoring/slide-1.svg)

## Salute

Inizia con un controllo dello stato di salute:

```bash
time rdc machine health --name my-server
```

Questo mostra uptime del sistema, utilizzo del disco, salute dei container e stato dello storage. Se qualcosa non va, te lo dice.

## Container

Per vedere tutti i container in esecuzione su ogni repo della macchina:

```bash
time rdc machine containers --name my-server
```

Ottieni nome, stato, salute, CPU e memoria per ogni container, più il repo che lo possiede.

## Repo

Per controllare i tuoi repository:

```bash
time rdc machine repos --name my-server
```

Questo mostra ogni repo con la sua dimensione, stato di mount, stato Docker e utilizzo del disco.

## Tutto in un colpo solo

```bash
time rdc machine query --name my-server
```

Informazioni di sistema, repo, container: tutto in un unico comando.

## Controllo locale di sanità

`rdc doctor` controlla la tua configurazione locale: Node, chiave SSH, `renet`, Docker, indipendentemente da qualsiasi server specifico:

```bash
time rdc doctor
```

## Hai finito

Questa è la serie completa. Ora sai come installare, configurare, distribuire, fare il fork, andare live, configurare l'avvio automatico, fare il backup e monitorare: tutto dal tuo terminale, tutto sui tuoi server.
