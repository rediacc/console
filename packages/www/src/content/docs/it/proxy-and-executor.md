---
title: Proxy ed Executor
description: Come i comandi da browser e da client leggero vengono eseguiti senza che il client detenga mai chiavi SSH o indirizzi macchina
category: Concepts
tags:
  - security
  - networking
order: 4
language: it
sourceHash: "39ec44d8efc3f9b5"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Proxy ed Executor

Normalmente `rdc` gira sulla tua macchina con la tua configurazione e le tue chiavi SSH, e si collega direttamente ai tuoi server. Il modello proxy divide questo flusso in due: un client leggero che non detiene alcun segreto, e un **executor** che li detiene e fa il lavoro. Il pulsante Esegui della [console web](/it/docs/web-console) e il flag `--proxy` della CLI sono entrambi client leggeri, e parlano lo stesso protocollo.

## Intento del comando, non comandi

Un client leggero non detiene mai una chiave SSH, un indirizzo macchina o una configurazione decifrata. Quando vuole eseguire qualcosa, invia solo l'intento del comando: un identificativo per il comando (il suo percorso nel contratto CLI, ad esempio `repo up`) più i parametri. L'executor cerca il comando nello stesso contratto, lo risolve nella funzione lato server sottostante, risolve la macchina di destinazione dalla configurazione decifrata ed esegue tutto sulla propria connessione SSH. L'output torna in streaming al client.

L'executor è la CLI stessa, avviata come server con `rdc serve`. Lo stesso binario che gli operatori usano su un laptop diventa la cosa che esegue i comandi per loro conto. Ha due possibili collocazioni:

- **`--mode daemon`**: gira su un host che controlli tu, iscritto in modo headless come qualsiasi CLI (vedi [Archivio di Configurazione](/it/docs/config-storage)), quindi può derivare da solo la chiave di configurazione e non ha bisogno di alcuna concessione per sessione. Questo è il livello rigoroso: SSH non esce mai dalla tua rete.
- **`--mode container`**: gira in un container ospitato per te, associato alla tua organizzazione. Parte senza alcuna chiave e non può fare nulla finché un client non gliene concede una per la sessione. Questo è il livello di convenienza.

## La concessione della CEK

L'archivio di configurazione è zero-knowledge: il server memorizza solo blob cifrati, e la chiave di cifratura del contenuto (CEK) esiste in chiaro solo su un client che l'ha sbloccata. Un executor in modalità container deve quindi *ricevere in concessione* la chiave, e la concessione non deve esporla al server nel frattempo.

Il flusso è questo: un browser sbloccato apre una sessione con l'executor, riceve la chiave pubblica della sessione e sigilla la CEK per quella sessione usando X25519. Il blob sigillato passa attraverso il server dell'account, ma il server non può aprirlo, quindi la proprietà zero-knowledge si mantiene end-to-end. L'executor decifra la CEK solo in RAM, con una scadenza per inattività di 30 minuti; nulla viene mai scritto su disco. Le richieste di comando successive fanno riferimento alla sessione concessa tramite l'header `X-Config-Session`.

Un dettaglio importante ai fini di audit: la stessa identità utente attraversa tutte e tre le fasi (apertura della sessione, concessione della chiave, esecuzione dei comandi). Il server dell'account non inoltra mai la propria credenziale all'executor. Per ogni fase emette un token a vita breve attribuito all'utente reale, e ricontrolla ogni volta l'appartenenza di quell'utente. L'executor verifica qualsiasi token gli venga presentato prima di agire. Una concessione fatta da un utente non può essere usata da un altro.

La metà `state` di una configurazione (dati di runtime locali all'host) non viaggia mai nel blob di configurazione, quindi non raggiunge mai un executor nemmeno per questa via.

## Cosa può girare tramite un proxy

Non tutti i comandi hanno senso in remoto. Ogni comando nel contratto porta un flag `proxyCapable`, e l'executor lo impone lato server, indipendentemente da qualsiasi configurazione di policy:

- I **comandi del piano macchina, non interattivi** (deploy, backup, status, logs, e così via) sono abilitati al proxy.
- I **comandi del piano configurazione** non lo sono: modificano la configurazione, che su questo percorso è compito del browser (la console web li instrada invece al proprio editor di configurazione).
- I **comandi interattivi** (terminali, sessioni VS Code) non lo sono: non c'è un TTY su questo canale.
- I **comandi di trasferimento lato client** (`rdc repo sync`) non lo sono: spostano dati tra il filesystem del *client* e una macchina, e l'executor non ha i file del client.

La console web legge lo stesso flag per decidere se un comando riceve o meno un pulsante Esegui, ma l'executor rifiuta i comandi non abilitati indipendentemente da ciò che il client invia.

## L'executor fittizio

In sviluppo, quando non è configurato alcun executor reale, il server dell'account risponde da sé alle richieste di comando con stream fittizi e dati chiaramente falsi (nomi di risorse con prefisso `mock-`). Questo rende l'intera console utilizzabile, inclusi form, streaming e rendering dei risultati, senza bisogno di una macchina o di uno sblocco. L'esecuzione reale richiede un executor reale.

## Correlati

- [Console Web](/it/docs/web-console), il client browser costruito su questo modello
- [Archivio di Configurazione](/it/docs/config-storage), l'archivio zero-knowledge che protegge la CEK
