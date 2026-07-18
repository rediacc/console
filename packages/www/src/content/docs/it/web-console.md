---
title: Console Web
description: Esegui l'intera CLI rdc dal tuo browser con form, selettori di risorse e cronologia delle esecuzioni
category: Guides
order: 8
language: it
sourceHash: "b735dd2fd77435c5"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Console Web

La console web è un'interfaccia da browser sull'intera CLI `rdc`. Ogni comando CLI compare nella console con un form, la validazione, i selettori di risorse e un pulsante Esegui. Non esiste un "set di funzionalità web" separato: la console è generata dal contratto della CLI, quindi qualsiasi comando presente nella CLI è presente anche nella console, e i nuovi comandi compaiono automaticamente.

Si trova nel portale web all'indirizzo `/account/console`.

## Disponibilità

La console web è una funzionalità a pagamento. È inclusa nei piani a pagamento ed è nascosta nel piano Community. L'accesso è anche vincolato ai ruoli, quindi un amministratore dell'organizzazione può controllare chi la vede.

## Rapporto con l'archivio di configurazione

La console legge le tue risorse (macchine, repository e così via) dal tuo archivio di configurazione cifrato, e decifra quella configurazione solo nel browser. Questo significa che:

- **Da bloccata**, puoi comunque sfogliare l'intero catalogo dei comandi, aprire il form di qualsiasi comando e leggerne i parametri. Funziona senza alcuna configurazione preliminare.
- **Per eseguire comandi e usare i selettori**, devi prima sbloccare il tuo archivio di configurazione (passkey, password principale o codice di recupero, vedi [Archivio di Configurazione](/it/docs/config-storage)). Pulsanti Esegui, pagine delle risorse e selettori di risorse dipendono tutti dalla sessione sbloccata.

La chiave decifrata resta solo nella memoria del browser. Aggiornare la pagina blocca di nuovo la console, e 30 minuti di inattività la bloccano automaticamente.

## Selettori di risorse

Una volta sbloccati, i form dei comandi sostituiscono i campi di testo libero con selettori alimentati dalla tua configurazione decifrata: macchine, repository, datastore, storage, cluster, provider cloud e strategie di backup. Alcuni selettori vengono invece risolti al volo, eseguendo un comando, ad esempio i container su una macchina o gli snapshot in un datastore.

I selettori filtrano in modo dipendente: scegli una macchina e il selettore dei repository si restringe a quella macchina. Per i riferimenti ai repository, un builder di riferimenti compone la forma completa `name:tag@machine` a partire dalle singole scelte. I selettori sono suggerimenti, non vincoli, e puoi sempre digitare un valore a mano.

## Eseguire comandi

Il browser non detiene mai una chiave SSH o un indirizzo macchina. Quando fai clic su Esegui, la console invia solo l'intento del comando, cioè quale comando e quali parametri, e un executor risolve tutto il resto e lo esegue. Vedi [Proxy ed Executor](/it/docs/proxy-and-executor) per capire come funziona e quali comandi possono girare in questo modo.

I comandi che modificano solo la tua configurazione (ad esempio creare una voce macchina) non vengono eseguiti in remoto. La console li instrada al suo editor di configurazione integrato, dove la modifica viene cifrata e inviata come qualsiasi altra modifica alla configurazione.

Ogni form mostra anche il comando CLI equivalente, così tutto ciò che imposti nella console può essere copiato direttamente in un terminale o in uno script.

## Orientarsi nella console

- **Pagine delle risorse**: macchine, repository e job hanno ciascuno pagine di elenco e di dettaglio, con i comandi pertinenti disponibili come azioni.
- **Palette dei comandi**: premi Cmd-K (Ctrl-K) per saltare direttamente a qualsiasi comando o risorsa per nome.
- **Cronologia delle esecuzioni**: le esecuzioni passate vengono conservate per sessione, così puoi rivedere l'output e rieseguire con gli stessi parametri.

## Correlati

- [Archivio di Configurazione](/it/docs/config-storage), configurare e sbloccare l'archivio di configurazione cifrato
- [Proxy ed Executor](/it/docs/proxy-and-executor), il modello di esecuzione dietro il pulsante Esegui
