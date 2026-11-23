---
title: "Risposta agli incidenti di sicurezza"
description: "Come Rediacc gestisce i propri incidenti di sicurezza: le comunicazioni ai clienti per fasi, i campi dell'art. 33(3) del GDPR, il percorso di notifica del CRA e che cosa ricevono i clienti."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 10
language: it
sourceHash: "6b9f728f093ecb0c"
sourceCommit: "72636750e43d473936cbb242ec9c7511fd246f65"
---

Questa pagina descrive che cosa accade quando Rediacc stessa subisce un incidente di sicurezza, ad esempio la compromissione dei propri sistemi o una vulnerabilità attivamente sfruttata nei suoi prodotti. Gli incidenti all'interno dei repository di un cliente spettano al cliente, che li indaga e li notifica; Rediacc fornisce a questo scopo gli strumenti per raccogliere le prove. Le segnalazioni di vulnerabilità provenienti dall'esterno sono trattate nella [politica di divulgazione](/it/docs/security-disclosure-policy).

## Fasi

Ogni incidente ha un orologio che parte nel momento in cui Rediacc ne viene a conoscenza. Le informazioni vengono rilasciate per fasi, perché il quadro completo è raramente noto fin dal primo giorno e l'art. 33(4) del GDPR consente di fornire le informazioni in modo graduale.

| Fase | Scadenza | Contenuto |
|------|----------|-----------|
| Preallarme | entro 24 ore | ciò che si sa finora e se si sospettano atti dolosi |
| Notifica | entro 72 ore | la natura dell'incidente, una valutazione iniziale e le misure adottate |
| Relazione finale | entro un mese | una descrizione dettagliata, la causa all'origine e le misure applicate e in corso |

## I campi dell'art. 33(3)

Ogni fase riporta i quattro elementi elencati nell'art. 33(3) del GDPR:

1. la natura della violazione, con le categorie e il numero approssimativo di interessati e di registrazioni di dati personali in questione
2. il nome e i dati di contatto del punto di contatto presso cui ottenere più informazioni
3. le probabili conseguenze
4. le misure adottate o proposte per porre rimedio alla violazione, comprese quelle volte ad attenuarne i possibili effetti negativi

Quando un valore non è ancora noto, la fase lo dichiara e indica la data entro cui lo sarà.

## Che cosa ricevono i clienti

Quando un incidente riguarda un'organizzazione:

- ogni fase viene inviata come avviso nel portale dell'account e come e-mail, ai proprietari e agli amministratori dell'organizzazione e al suo referente per la sicurezza
- l'avviso e l'e-mail vengono inviati indipendentemente dalle preferenze di notifica, perché sono comunicazioni di sicurezza
- un banner nel portale rimanda alla pagina dell'incidente, che mostra ogni fase pubblicata
- ogni fase offre un bundle STIX 2.1 con gli indicatori di compromissione, in un formato leggibile dalle macchine che gli strumenti di sicurezza possono importare

Un'organizzazione non coinvolta non riceve nulla. Nel portale, proprietari e amministratori impostano il referente per la sicurezza dell'organizzazione, in modo che il messaggio arrivi alla persona giusta.

## Notifiche regolamentari

Rediacc notifica i propri incidenti dove la legge lo richiede.

- **GDPR.** Quando Rediacc agisce in qualità di responsabile del trattamento, la comunicazione per fasi informa il titolare senza ingiustificato ritardo (art. 33(2)), e sarà il titolare a decidere sulla notifica alla propria autorità di controllo. Quando Rediacc è il titolare del trattamento, notifica all'autorità di controllo competente entro 72 ore, ove possibile (art. 33(1)).
- **Cyber Resilience Act.** Dall'11 settembre 2026, l'art. 14 del Regolamento (UE) 2024/2847 impone al fabbricante di notificare una vulnerabilità attivamente sfruttata o un incidente grave che incide sulla sicurezza di un prodotto con elementi digitali al CSIRT designato e all'ENISA, tramite la piattaforma unica di segnalazione. Si applicano le stesse fasi di 24 ore, 72 ore e relazione finale, e lo stesso registro dell'incidente alimenta sia la comunicazione ai clienti sia la notifica.

## Segnalare un sospetto incidente

Chiunque sospetti un incidente che riguarda Rediacc, compreso un cliente che osserva un comportamento inatteso in un componente Rediacc, scrive a [security@rediacc.com](mailto:security@rediacc.com). La segnalazione di una vulnerabilità segue la [politica di divulgazione](/it/docs/security-disclosure-policy).
