---
title: "Canali di Rilascio"
description: "Differenze tra Edge e Stable, e perché scegliere l'uno o l'altro canale."
category: "Concepts"
tags:
  - cli
  - operations
subcategory: platform
order: 2
language: it
sourceHash: "29d62173c5cf044a"
sourceCommit: "abc292b1b7ca5096423e098c12a9b23bdabda16b"
---

Rediacc distribuisce gli aggiornamenti della CLI attraverso due canali: **Stable** ed **Edge**. Entrambi si collegano allo stesso prodotto, quindi account, piano e limiti sono identici su ciascuno. I canali differiscono solo per la rapidità con cui una versione ti raggiunge.

## Canale Stable

Stable è il predefinito. Una versione lo raggiunge solo dopo essere rimasta su Edge per 7 giorni senza problemi segnalati.

- Consigliato quando si preferisce una cadenza di aggiornamento conservativa
- Distribuito dopo 7 giorni di test su Edge
- Gli hotfix possono essere distribuiti direttamente quando critico

## Canale Edge

Edge riceve ogni modifica nel momento in cui viene mergiata nel ramo main. È la versione live del software, distribuita continuamente.

- Rilasciato ad ogni merge nel main
- Stessi account, piani e limiti di Stable
- Ideale per provare in anticipo le novità

## Un prodotto, due canali

Il tuo account risiede nella tua regione dei dati, su `eu.rediacc.cloud`, `us.rediacc.cloud` o `asia.rediacc.cloud`, qualunque canale tu usi. Cambiare canale non tocca il tuo account, i tuoi dati né il tuo abbonamento. Per le regioni, vedi [Regioni dei Dati](/it/docs/data-regions).

## Confronto

| | Stable | Edge |
|---|---|---|
| **Cadenza di distribuzione** | Dopo maturazione di 7 giorni | Ad ogni merge nel main |
| **Stabilità** | Testato per 7 giorni | Produzione, distribuito continuamente |
| **Piani e limiti** | Uguali | Uguali |
| **Account e dati** | Condivisi | Condivisi |
| **Ideale per** | Produzione, carichi di lavoro a pagamento | Accesso anticipato, valutazione |

## Come Funzionano le Promozioni

1. Ogni merge nel ramo main viene distribuito su Edge immediatamente.
2. Dopo 7 giorni senza problemi, Edge viene promosso automaticamente a Stable.
3. Gli hotfix critici possono essere distribuiti su entrambi i canali simultaneamente.

Quindi Stable è al massimo 7 giorni indietro rispetto a Edge. La finestra di maturazione intercetta le regressioni su Edge prima che raggiungano mai Stable.

## Quale Canale Scegliere?

**Scegli Stable se:**
- Preferisci una cadenza di aggiornamento conservativa con una finestra di maturazione di 7 giorni
- Preferisci la massima affidabilità rispetto alle ultime funzionalità

**Scegli Edge se:**
- Vuoi provare le nuove funzionalità in anticipo
- Stai valutando la piattaforma
- Sei a tuo agio con codice più recente e meno testato

## Installazione

Vedi [Installation](/it/docs/installation) per i comandi di installazione, la configurazione del gestore di pacchetti e i tag Docker per ciascun canale.

## Gestione del Canale CLI

La CLI usa il canale che hai configurato all'installazione. Per cambiare:

```bash
rdc update --channel edge      # Passa a Edge
rdc update --channel stable    # Passa a Stable
```
