---
title: Scalabilità dei Database Legacy
description: Scala i database legacy senza migrazione sfruttando la replica dei dati in tempo reale e la distribuzione delle query.
category: Use Cases
order: 3
language: it
---

> **Il Tuo Database Legacy Ti Sta Frenando. Liberati Senza Romperlo.**

**Nota:** Questo è un **esempio d'uso** che dimostra come Rediacc può risolvere questo problema. Essendo una startup, questi scenari rappresentano applicazioni potenziali piuttosto che casi studio completati.

**Scenario di crisi:** Nonostante la scalabilità dei server di 10 volte con Kubernetes, le prestazioni sono migliorate solo di 2 volte. I clienti si lamentavano dei tempi di query lenti, i costi aumentavano senza risultati soddisfacenti e la reputazione era a rischio.

## Il Problema

I servizi dell'organizzazione nell'ambiente cloud **faticavano a rispondere**. Come soluzione, il team software:
* Ha eseguito la **scalabilità orizzontale con Kubernetes** e **ha aumentato il numero di server di 10 volte**
* Tuttavia, le prestazioni sono migliorate **solo di 2 volte**

**Individuazione del Collo di Bottiglia:**
* Si è capito che la fonte del problema era un **database legacy che non può essere scalato**
* Il database non riusciva a funzionare in modo distribuito come nelle architetture moderne

**Il Dilemma:**
* La migrazione a un database moderno **potrebbe richiedere anni** - Richiedeva la riscrittura del codice, la migrazione dei dati e i processi di test
* La perdita di costi e tempo era inaccettabile

## Impatto della Crisi

* I clienti si lamentano a causa dei **tempi di query lenti**
* I costi dei server aumentano, ma le **prestazioni non sono soddisfacenti**
* Il rischio di **perdita di reputazione** aumenta in un mercato competitivo

## Soluzione Rediacc

L'ingegnere di sistema Yüksel, utilizzando la funzionalità di cross-backup di Rediacc:

![Scalabilità DB Legacy](/img/legacy-scaling.svg)

### 1. **Replica dei Dati in Tempo Reale**
* Le modifiche nel database legacy venivano trasferite ad altri server **a intervalli di 10-15 minuti**
* Venivano sincronizzati **solo i dati modificati** - **Il consumo di banda si è ridotto del 95%**

### 2. **Distribuzione delle Query**
* Le query di lettura venivano **distribuite a più macchine**
* Le operazioni di scrittura venivano mantenute **nel database principale** per garantire la coerenza

### 3. **Scalabilità Senza Costi Aggiuntivi**
* Il sistema legacy è stato supportato con server aggiuntivi **senza essere modificato**
* Nessuna necessità di acquistare nuovo hardware - **I server cloud venivano noleggiati su base oraria** per l'ottimizzazione dei costi

## Risultato

**Aumento delle Prestazioni:**
* I tempi di query si sono ridotti da **55 secondi a 7 secondi**
* La capacità del sistema è aumentata di **8 volte**

**Controllo dei Costi:**
* Risparmio dalla riscrittura del sistema legacy - **Le risorse finanziarie sono state preservate**

**Guadagno di Tempo:**
* La soluzione è stata implementata **entro 3 settimane**
* I reclami dei clienti sono stati risolti al **99,99% (a seconda del rapporto di aggiornamento del totale dei dati tra gli snapshot)**
