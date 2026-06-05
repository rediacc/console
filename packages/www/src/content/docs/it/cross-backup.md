---
title: Strategia di Backup Incrociato
description: "Il backup fallisce nel momento in cui la macchina si guasta. Rediacc replica gli snapshot su una macchina separata affinché un singolo guasto del disco non comporti la perdita di tutto."
category: Use Cases
order: 5
language: it
sourceHash: "39dbeac1faec121c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Quando Colpisce il Disastro, i Tuoi Dati Sopravviveranno? Con Rediacc, Sempre.**

**Nota:** Questo è un **esempio d'uso** che dimostra come Rediacc può risolvere questo problema. Questi scenari rappresentano applicazioni potenziali, non casi di studio completati.

**Scenario di crisi:** Una chiamata di un cliente rivela l'interruzione del servizio: **guasto al disco**. L'ultimo backup del server di backup remoto risaliva a **3 settimane prima**. Tre settimane di dati, persi.

## Il Problema

Mantenere il backup solo sulla stessa macchina dei dati che protegge non è una strategia. Ecco cosa conferma questo fallimento:
* Guasti hardware
* Attacchi informatici
* Disastri fisici come guerra, terremoto, incendio, alluvione
* Protezione insufficiente contro la perdita di dati

**Ricerca di una Soluzione:**
* Si decide di eseguire il backup di 20 TB di dati su **un server remoto**
* Tuttavia, con i metodi tradizionali, questo backup richiede **2 settimane** e occupa il **99,99% (a seconda del rapporto di aggiornamento dei dati totali tra snapshot)** della banda

## Impatto della Crisi

Dopo una chiamata di un cliente:
* Si nota che **i servizi non funzionano**
* Viene rilevato un **guasto al disco**
* Controllando il server di backup remoto, si scopre che **l'ultimo backup risale a 3 settimane fa**

**Risultati:**
* I tentativi manuali di recupero del disco **falliscono**
* A causa di 3 settimane di perdita di dati, **i contratti con i clienti vengono cancellati**
* La **reputazione dell'organizzazione viene seriamente danneggiata**

## Soluzione Rediacc

![Cross Backup Strategy](/img/cross-backup.svg)

### 1. **Primo Backup**
* La prima volta che 20 TB di dati vengono trasferiti su un server remoto, ci vogliono 2 settimane

### 2. **Backup Intercontinentali Orari**
* Ogni ora viene creata la percezione di un backup completo, ma vengono trasferiti **solo i dati modificati**

### 3. **Preparazione per Scenari di Disastro**
* I dati possono essere sottoposti a backup anche su server **intercontinentali**
* Anche se la macchina principale si blocca, i dati di appena 1 ora prima vengono **attivati in pochi minuti**

## Risultato

**Risparmio di Tempo:**
* Il tempo di backup è stato ridotto da **2 settimane a una media di 4 minuti**
* Il rischio di perdita di dati è stato ridotto a **1 ora**

**Ottimizzazione dei Costi:**
* Il consumo di banda è diminuito del **98%**

**Continuità Aziendale Ininterrotta:**
* Quando il server principale si è bloccato, il backup remoto è stato attivato in **7 minuti**
