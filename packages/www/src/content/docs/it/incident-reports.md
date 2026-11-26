---
title: "Report di incidente: a fasi, firmati e verificabili"
description: "Generate l'allerta precoce, la notifica e il report finale di un incidente in un repository del cliente come JSON, STIX 2.1 o PDF. Ogni report è firmato con Ed25519, porta un link di verifica con QR code e mappa i propri campi su NIS2, sul formato 2025/302 e sull'art. 33, par. 3 del GDPR."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 11
language: it
sourceHash: "777d8ae1dde17294"
sourceCommit: "0531ce955ea0d1658b8fceefd6aa44e3c270521c"
---

# Report di incidente

Un incidente dichiarato ([risposta agli incidenti](/it/docs/incident-response)) produce tre report a fasi che il cliente presenta a un'autorità di controllo. Rediacc genera i documenti a partire dalle prove. Stabilire se un incidente sia significativo o notificabile resta una valutazione del cliente, e ogni report lo dichiara.

## Fasi

Ogni fase elenca le sezioni che richiede e nessun'altra, quindi una sezione che la fase non richiede viene omessa anziché lasciata vuota.

| Fase | Scadenza | Aggiunge |
|---|---|---|
| Allerta precoce | 24 ore dopo la presa di conoscenza | Intestazione, timeline, indicatori di compromissione, impatto doloso sospetto e transfrontaliero |
| Notifica | 72 ore dopo la presa di conoscenza | Valutazione iniziale, impatto sui dati (categorie, numeri approssimativi, Stati membri) e tecniche ATT&CK |
| Finale | Un mese di calendario dopo la notifica | Causa radice e misure di mitigazione |

Il report finale segue una notifica, quindi la notifica viene generata per prima. Ogni fase include le sezioni della fase precedente.

Ogni fatto di un report indica come è noto: osservato nelle prove, inserito dal cliente o dedotto. Un fatto dedotto porta un livello di confidenza e il motivo del rilevatore. Valutazione, categorie di dati, Stati membri, causa sospetta, azioni intraprese, punto di contatto e tecniche sono dati che il cliente inserisce nella pagina dell'incidente prima della generazione.

## Formati

| Formato | Uso |
|---|---|
| JSON | La forma canonica e verificabile |
| STIX 2.1 | Un bundle di indicatori per gli strumenti di threat intelligence |
| PDF | Un documento leggibile, che rende anche le scritture non latine, con l'avvertenza, un QR code e l'hash del report nel piè di pagina di ogni pagina |

Dalla pagina dell'incidente, ogni fase ha un pulsante di download per formato. Dalla riga di comando:

```bash
rdc incident export <id> --stage early-warning
rdc incident export <id> --stage notification --format stix
rdc incident export <id> --stage final --format pdf --out ./reports
```

Il formato predefinito è JSON. `--format` si applica solo con `--stage`. Il file viene scritto con il proprio identificativo di report.

## Firma e verifica

Ogni report è firmato con una chiave di report Ed25519, e identificativo, fase e hash del report sono su un registro pubblico. La firma copre il contenuto canonico del report, quindi qualsiasi modifica successiva alla firma viene rilevata.

Un report si controlla in tre punti:

- La pagina di verifica a `/account/verify/report/<id>`, che il QR code del PDF apre. Il controllo gira nel browser contro la chiave di report pubblicata e non viene caricato nulla. Un file JSON viene controllato per intero. Un PDF non può essere rihashato nel browser, quindi la pagina conferma che il PDF porta l'hash del report e rimanda al file JSON per un controllo completo.
- La riga di comando, per un report JSON:

```bash
rdc forensics verify --report ./reports/<report-id>.json
```

Il comando termina con codice 1 quando il contenuto o la firma non corrispondono. Un PDF si verifica tramite il report JSON da cui è stato creato.

- Il timbro delle prove dentro il report, che registra il risultato di Verify evidence per la finestra: chi ha verificato, con quale versione e quando.

## Mappa dei campi

Ogni campo del report corrisponde ai regimi sotto cui il cliente notifica, così il contenuto può essere riportato senza doverlo riscrivere. La mappa copre tre regimi: NIS2 art. 23, par. 4, il formato di notifica degli incidenti del regolamento di esecuzione (UE) 2025/302 e il GDPR art. 33, par. 3. Esempi:

| Campo del report | NIS2 | GDPR |
|---|---|---|
| Momento della presa di conoscenza | Art. 23(4)(a) | Art. 33(1) |
| Cronologia | Art. 23(4)(d) | Art. 33(3)(a) |
| Punto di contatto | Art. 23(4) | Art. 33(3)(b) |

Un campo senza corrispondente in un regime ne spiega il motivo anziché essere omesso. La notifica dell'art. 33, par. 3 del GDPR non ha, per esempio, numero di riferimento né ora di chiusura.

## Cosa un report non afferma

In ogni fase vengono stampate due dichiarazioni:

- Un record di flusso prova volume e destinazione, non il contenuto.
- Stabilire se l'incidente sia significativo o notificabile è una valutazione del cliente.

Rediacc non presenta nulla a un'autorità di controllo per conto del cliente.
