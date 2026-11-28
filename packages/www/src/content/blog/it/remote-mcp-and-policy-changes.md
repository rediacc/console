---
title: "MCP remoto: un agente che legge solo ciò che può leggere la sua persona"
description: "L'MCP remoto gira sui tre Worker regionali. Un grant porta la chiave di una config e le chiavi di policy della sua persona, mai la chiave principale, e nessun token sopravvive al grant."
author: Rediacc
publishedDate: 2026-11-25
category: announcement
tags:
  - mcp
  - ai-agents
  - security
  - policy
featured: false
language: it
sourceHash: "ce8dbe4241a2d7ab"
sourceCommit: "dda643f43f9dadc19e08a84858e87f115d428f85"
---

> **In sintesi.** L'MCP remoto dà a un agente AI un URL invece di un terminale. La domanda di progetto non era come collegare l'agente, ma che cosa può vedere una volta collegato. La risposta: esattamente ciò che vede la persona che ha creato il grant, e niente di più.
>
> - Un grant raggiunge **una config** e vive in **una regione**.
> - Token di accesso da **1 ora** al massimo, token di refresh da **30 giorni** al massimo, e mai più a lungo del grant stesso.
> - Il grant porta la chiave di contenuto di una config e due **chiavi di lettura della policy**, mai la chiave principale del config store.
> - Il formato dei record di policy è cambiato. Quelli vecchi vengono rifiutati e non esiste un percorso di migrazione.

## Un URL, non una shell di login

Il server MCP locale (`rdc mcp serve`) gira accanto all'agente ed eredita gli accessi della macchina su cui è in esecuzione. Il server remoto funziona in modo diverso. In ogni regione gira un Worker MCP su `mcp.<region>.rediacc.cloud`, e ogni agente si collega all'URL di un grant: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. Le chiamate agli strumenti vengono eseguite sull'executor dell'organizzazione, non sul portatile di uno sviluppatore.

Client interattivi come claude.ai accedono con OAuth 2.1 e PKCE. Gli agenti headless inviano un bearer `rmcp_<grantId>.<secret>`. Entrambe le forme identificano il grant, mentre l'identificativo nell'URL si limita a nominarlo.

## Il grant è il confine

Un grant è un oggetto piccolo e preciso. Indica una config, una scadenza e un ambito: un flag di sola lettura, una allowlist di strumenti e pattern di nomi per macchine e repository.

Da questa forma discendono tre regole:

- **Una config.** Un `tools/call` che nomina un'altra config viene rifiutato con `REDIACC_GRANT_SCOPE` prima che venga eseguito qualsiasi cosa. Chi ha tre config autorizza tre grant.
- **Una regione.** Gli identificativi dei grant iniziano con la regione. Una richiesta arrivata al Worker sbagliato riceve un HTTP 421 con l'URL corretto e non viene mai inoltrata.
- **Una durata.** Un token di accesso dura il minore tra 1 ora e il tempo residuo del grant. Un token di refresh dura il minore tra 30 giorni e il tempo residuo del grant. Ogni refresh rilegge il grant, quindi un grant revocato smette di funzionare al successivo scambio. Presentare due volte un token di refresh revoca il grant.

L'URL di un grant vale 7 giorni per impostazione predefinita e al massimo 30.

## Giudicato come la sua persona

La parte interessante è il materiale crittografico. Un grant è un segreto diviso in due. Il browser genera un valore casuale e lo mostra una sola volta. Il server degli account conserva solo l'hash di un tag derivato da quel valore, e l'executor deriva la chiave di slot solo finché possiede entrambe le metà. Ciò che quella chiave apre è la chiave di contenuto della config, mai la chiave principale dell'organizzazione.

La stessa chiave di slot apre anche due **chiavi di policy**. La policy, cioè le regole di autorizzazione di una voce di config, vive ora in un record a sé, sigillato con una chiave derivata dalla chiave dello store e dal puntatore del record: store, config, team e generazione della chiave. Il grant porta la chiave della config del proprio team e quella della config a livello di organizzazione. Sono i due record di policy che legge la sua persona, quindi l'executor legge gli stessi.

L'effetto è che un agente viene giudicato come la sua persona. Il tetto è la policy dell'organizzazione, ristretta da quella del team. L'agente agisce solo dove un consenso umano e quel tetto lo permettono entrambi. Non può modificare la policy, leggere i valori dei secret né allargare il proprio grant. Una chiave bloccata dall'organizzazione viene ignorata nella policy di un team, e l'agente si trova davanti quell'esito come la persona.

Legare ogni chiave a un puntatore ha un effetto collaterale da ricordare. Chi possiede una chiave di policy apre i record di quel puntatore sotto quella generazione di chiave e nessun altro. Un blob servito per un altro store, un'altra config o un altro team, o riproposto sotto un'altra versione, non supera il tag di integrità.

## Che cosa cambia per le installazioni esistenti

- **Record di policy alla versione 2.** Un record di versione 1, sigillato con la chiave dello store stessa, non si apre. È una rottura netta, voluta.
- **Le scritture ospitate seguono la stessa policy.** Le scritture di config fatte tramite l'executor ospitato vengono verificate rispetto al tetto della policy prima di essere salvate.
- **Gli agenti locali mantengono lo stesso tetto.** `REDIACC_ALLOW_CONFIG_EDIT` abilita ancora un agente a modificare la config per i puntatori che nomina, ma solo entro ciò che la policy consente.
- **Grant scaduti o ruotati falliscono in modo chiaro.** `initialize` e `tools/list` rispondono ancora, e ogni chiamata restituisce `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` o `REDIACC_KEY_ROTATED` con una `reauthUrl`.

Ogni grant ammette 60 chiamate al minuto e 5 in corso.

## Che cosa ottiene un URL trapelato

Un URL trapelato agisce come quell'utente sulla sua unica config fino alla scadenza o alla revoca. Non apre nessun'altra config dell'organizzazione, né nulla al di fuori dell'executor ospitato della sua regione. L'output degli strumenti arriva invece al provider di modelli che l'utente collega. Rediacc non sceglie quel provider.

La guida all'installazione è [MCP Server Setup](/it/docs/ai-agents-mcp), e la struttura delle chiavi è nel [modello di sicurezza](/it/docs/security-model).
