---
title: "Canali di Rilascio"
description: "Comprensione dei canali di rilascio Edge e Stable, le loro differenze e come scegliere. È possibile cambiare canale in qualsiasi momento."
category: "Concepts"
order: 2
language: it
---

Rediacc pubblica gli aggiornamenti attraverso due canali di rilascio: **Stable** ed **Edge**. Ogni canale si rivolge a un pubblico diverso e comporta compromessi differenti.

## Canale Stable

Stable è il canale predefinito per tutti gli utenti. Le versioni vengono promosse da Edge dopo un periodo di maturazione di 7 giorni senza problemi segnalati.

- Consigliato quando si preferisce una cadenza di aggiornamento conservativa e si desidera accesso ai piani a pagamento
- Distribuito dopo 7 giorni di test su Edge
- Gli hotfix possono essere distribuiti direttamente quando critico
- Domini: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Canale Edge

Edge riceve ogni modifica immediatamente dopo il merge nel ramo main. È la versione più recente del software, distribuita continuamente.

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

Gli utenti Edge con il piano Community ricevono limiti di risorse raddoppiati senza costi aggiuntivi:

| Risorsa | Stable Community | Edge Community |
|---|---|---|
| Dimensione repository | 10 GB | 20 GB |
| Emissioni di licenze al mese | 500 | 1.000 |
| Attivazioni macchina | 2 | 4 |

Se hai bisogno di limiti più alti o funzionalità dei piani a pagamento, crea un account sul canale Stable e aggiorna da lì.

## Account Separati

Edge e Stable funzionano su infrastrutture separate con database separati. Un account creato su Edge non esiste su Stable, e viceversa. Non esiste un percorso di migrazione tra i canali. Se inizi su Edge e poi vuoi un piano a pagamento, dovrai creare un nuovo account su Stable.

## Come Funzionano le Promozioni

1. Ogni merge nel ramo main viene distribuito su Edge immediatamente.
2. Dopo 7 giorni senza problemi, Edge viene promosso automaticamente a Stable.
3. Gli hotfix critici possono essere distribuiti su entrambi i canali simultaneamente.

Questo significa che Stable è sempre al massimo 7 giorni indietro rispetto a Edge. Il periodo di maturazione intercetta le regressioni prima che si propaghino da Edge a Stable.

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

Vedi [Installation](/it/docs/installation) per i comandi per installare da entrambi i canali, inclusa la configurazione del gestore di pacchetti e i tag Docker.

## Gestione del Canale CLI

La CLI usa automaticamente il canale configurato durante l'installazione o il login. Per cambiare canale:

```bash
rdc update --channel edge      # Passa a Edge
rdc update --channel stable    # Passa a Stable
```

Quando esegui `rdc subscription login` e selezioni una regione Edge, la CLI configura automaticamente il canale di aggiornamento Edge. Non è necessario il flag `--channel` manuale.
