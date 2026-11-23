---
title: "Politica di divulgazione delle vulnerabilità"
description: "Come segnalare una vulnerabilità di sicurezza in Rediacc: ambito, tutela legale, modalità di segnalazione e tempi di risposta previsti."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 9
language: it
sourceHash: "49a84775c19854ee"
sourceCommit: "72636750e43d473936cbb242ec9c7511fd246f65"
---

Rediacc accoglie con favore le segnalazioni di vulnerabilità di sicurezza nei suoi prodotti e servizi. Questa politica descrive che cosa rientra nell'ambito, come inviare una segnalazione e che cosa può aspettarsi in cambio chi la invia. Il file di contatto leggibile dalle macchine si trova in [`/.well-known/security.txt`](https://www.rediacc.com/.well-known/security.txt) (RFC 9116).

## Ambito

Rientrano nell'ambito:

- la CLI `rdc` e l'orchestratore di macchine `renet`
- il server degli account, il suo portale web e la sua API
- i siti web di Rediacc sotto `rediacc.com` e `rediacc.cloud`
- gli artefatti di rilascio: binari, immagini dei container e programmi di installazione

Non rientrano nell'ambito:

- i riscontri che richiedono l'accesso fisico a una macchina, o un endpoint compromesso che chi segnala controlla già
- il denial of service per volume, lo spam e l'ingegneria sociale ai danni del personale
- i report di scanner automatici senza un impatto dimostrato
- le vulnerabilità di software di terze parti che Rediacc si limita a ridistribuire senza modifiche; vanno segnalate al progetto upstream, e una copia a Rediacc è gradita

## Come segnalare

Inviare la segnalazione a [security@rediacc.com](mailto:security@rediacc.com). Includere:

- il prodotto interessato e la sua versione, oppure l'URL
- i passaggi per riprodurre il problema, oppure una proof of concept
- l'impatto che chi segnala ritiene possibile
- se il problema è già pubblico o sfruttato
- un indirizzo di contatto per il seguito e se si desidera essere citati

Sono preferite le segnalazioni in inglese. Nella segnalazione non vanno inseriti dati reali dei clienti: basta una prova minima dell'accesso.

## Tutela legale (safe harbour)

Rediacc non avvierà né sosterrà azioni legali contro chi segnala in buona fede nel rispetto di questa politica, ossia chi:

- esegue test solo su account, macchine e dati propri, oppure su risorse di proprietà di Rediacc
- si ferma nel momento in cui dimostra il problema e non legge, modifica, copia o elimina dati di altri
- non degrada il servizio per gli altri utenti
- segnala tempestivamente e mantiene riservati i dettagli fino alla data di divulgazione coordinata indicata più avanti

L'attività che resta entro questi limiti è considerata autorizzata, e Rediacc lo confermerà a qualsiasi terza parte che lo chieda.

## Tempi di risposta

| Fase | Obiettivo |
|------|-----------|
| Conferma di ricezione della segnalazione | 2 giorni lavorativi |
| Prima valutazione, con la gravità | 5 giorni lavorativi |
| Aggiornamenti sullo stato finché il caso è aperto | almeno ogni 14 giorni |
| Correzione o mitigazione per un problema critico | 14 giorni dalla valutazione |
| Correzione o mitigazione per gli altri problemi confermati | 90 giorni dalla valutazione |

Gli obiettivi sono traguardi, non garanzie: una segnalazione che richiede più tempo riceve una spiegazione e una nuova data.

## Divulgazione coordinata

Di norma i dettagli vengono pubblicati insieme alla correzione, entro 90 giorni dalla segnalazione. Chi desidera una pubblicazione anticipata o posticipata indica la data nella segnalazione, e le due parti concordano una data. Una vulnerabilità già sfruttata in the wild viene trattata come un incidente, come descritto nella [pagina sulla risposta agli incidenti](/it/docs/security-incident-response).

## Riconoscimento

Una segnalazione confermata viene citata nelle note di rilascio o nell'avviso di sicurezza con il nome o lo pseudonimo scelto da chi l'ha inviata. Rediacc non gestisce un programma di bug bounty a pagamento.

## Vedi anche

- [Risposta agli incidenti](/it/docs/security-incident-response)
- [Sicurezza dell'account e API](/it/docs/account-security)
