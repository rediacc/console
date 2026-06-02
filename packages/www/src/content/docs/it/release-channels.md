---
title: "Canali di Rilascio"
description: "Differenze tra Edge e Stable, e perché scegliere l'uno o l'altro canale."
category: "Concepts"
order: 2
language: it
sourceHash: "5fdcb0e8944f5d60"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

Rediacc distribuisce gli aggiornamenti attraverso due canali: **Stable** ed **Edge**. Operano su infrastrutture separate e comportano compromessi diversi.

## Canale Stable

Stable è il predefinito. Una versione lo raggiunge solo dopo essere rimasta su Edge per 7 giorni senza problemi segnalati.

- Consigliato quando si preferisce una cadenza di aggiornamento conservativa e si desidera accesso ai piani a pagamento
- Distribuito dopo 7 giorni di test su Edge
- Gli hotfix possono essere distribuiti direttamente quando critico
- Domini: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Canale Edge

Edge riceve ogni modifica nel momento in cui viene mergiata nel ramo main. È la versione live del software, distribuita continuamente.

- Produzione continuamente distribuita, rilasciata ad ogni merge nel main
- Limiti del piano Community 2X (vedi tabella di seguito)
- Gratuito per sempre. Nessun piano a pagamento disponibile su Edge.
- Account separati da Stable. I dati non si trasferiscono tra i canali.
- Domini: `edge-eu.rediacc.com`, `edge-us.rediacc.com`, `edge-asia.rediacc.com`

## Confronto

| | Stable | Edge |
|---|---|---|
| **Cadenza di distribuzione** | Dopo maturazione di 7 giorni | Ad ogni merge nel main |
| **Stabilità** | Testato per 7 giorni | Produzione, distribuito continuamente |
| **Limiti piano Community** | Repository da 10 GB, 500 emissioni/mese, 2 macchine | Repository da 20 GB, 1.000 emissioni/mese, 4 macchine |
| **Piani a pagamento** | Disponibili (Professional, Business, Enterprise) | Non disponibili |
| **Account** | Indipendenti | Indipendenti (separati da Stable) |
| **Ideale per** | Produzione, carichi di lavoro a pagamento | Produzione, progetti secondari, accesso anticipato |

## Limiti 2X di Edge

Esegui Edge con il piano Community e i tuoi limiti di risorse raddoppiano, senza costi aggiuntivi:

| Risorsa | Stable Community | Edge Community |
|---|---|---|
| Dimensione repository | 10 GB | 20 GB |
| Emissioni di licenze al mese | 500 | 1.000 |
| Attivazioni macchina | 2 | 4 |

Hai bisogno di limiti più alti o funzionalità a pagamento? Crea il tuo account su Stable e aggiorna da lì.

## Account Separati

Edge e Stable operano su infrastrutture separate con database separati. Un account sull'uno non esiste sull'altro, e non c'è percorso di migrazione. Inizia su Edge, poi decidi di volere un piano a pagamento, e dovrai creare un account nuovo su Stable da zero.

## Come Funzionano le Promozioni

1. Ogni merge nel ramo main viene distribuito su Edge immediatamente.
2. Dopo 7 giorni senza problemi, Edge viene promosso automaticamente a Stable.
3. Gli hotfix critici possono essere distribuiti su entrambi i canali simultaneamente.

Quindi Stable è al massimo 7 giorni indietro rispetto a Edge. La finestra di maturazione intercetta le regressioni su Edge prima che raggiungano mai Stable.

## Quale Canale Scegliere?

**Scegli Stable se:**
- Preferisci una cadenza di aggiornamento conservativa con una finestra di maturazione di 7 giorni
- Hai bisogno di piani a pagamento (Professional, Business, Enterprise)
- Preferisci la massima affidabilità rispetto alle ultime funzionalità

**Scegli Edge se:**
- Vuoi provare le nuove funzionalità in anticipo
- Stai valutando la piattaforma
- Vuoi limiti gratuiti generosi per i progetti secondari
- Sei a tuo agio con codice più recente e meno testato

## Installazione

Vedi [Installation](/it/docs/installation) per i comandi di installazione, la configurazione del gestore di pacchetti e i tag Docker per ciascun canale.

## Gestione del Canale CLI

La CLI usa il canale che hai configurato all'installazione o al login. Per cambiare:

```bash
rdc update --channel edge      # Passa a Edge
rdc update --channel stable    # Passa a Stable
```

Esegui `rdc subscription login` e scegli una regione Edge, e la CLI imposta il canale di aggiornamento Edge per te. Nessun flag `--channel` richiesto.
