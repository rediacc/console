---
title: Scalabilità Dinamica delle Risorse
description: Costruisci un'architettura cloud con flessibilità illimitata per il training AI e i carichi di lavoro dinamici.
category: Use Cases
order: 1
language: it
---

> **La Tua Architettura Cloud È Rigida? Costruisci con Flessibilità Illimitata.**

**Nota:** Questo è un **esempio d'uso** che dimostra come Rediacc può risolvere questo problema. Essendo una startup, questi scenari rappresentano applicazioni potenziali piuttosto che casi studio completati.

**Scenario di crisi:** I tempi di training AI si sono **estesi da 2 a 3 volte**, causando ritardi nei progetti. Gli ingegneri hanno subito una significativa perdita di produttività mentre aspettavano le risorse, mettendo a rischio il vantaggio competitivo dell'organizzazione.

## Il Problema

Gli ingegneri software dell'organizzazione riscontrano problemi di prestazioni con i server **on-premise** utilizzati per il **training dei modelli AI**:
* Durante l'**orario lavorativo** (08:00-17:00), le richieste al server raggiungono il 99% della capacità
* Il training che richiede elevata potenza di elaborazione causa l'**insufficienza dell'hardware**

**Ricerca di una Soluzione:**
* Il costo di aggiornamento del server **non è considerato adeguato** a causa delle **6-7 ore di utilizzo giornaliero**
* Sebbene venga considerata la migrazione al cloud, il **costo di trasferimento dei dati** e le **difficoltà di sincronizzazione** sono ostacoli

## Impatto della Crisi

* I tempi di training AI si **estendono da 2 a 3 volte**, i progetti sono in ritardo
* Gli ingegneri subiscono una **perdita di produttività** mentre aspettano le risorse
* L'organizzazione affronta il rischio di **perdere progressivamente il suo vantaggio competitivo**

## Soluzione Rediacc

L'ingegnere di sistema Yüksel sviluppa **un modello ibrido** con Rediacc:

![Scalabilità Cloud Ibrida](/img/hybrid-cloud-scaling.svg)

### 1. **Migrazione Cloud Istantanea**
* Durante l'orario lavorativo, i servizi on-premise vengono clonati nel cloud **con tutti i dati e le configurazioni**
* 100 TB di dati vengono sincronizzati in 9 minuti trasferendo **solo le parti modificate** grazie a Rediacc

### 2. **Scalabilità Dinamica**
* I server nell'ambiente cloud vengono noleggiati **nella misura necessaria per il training AI**
* La potenza di elaborazione può essere **aumentata di 10 volte** secondo la domanda

### 3. **Sincronizzazione Notturna**
* Al termine della giornata lavorativa, **tutte le modifiche nel cloud** vengono **estratte automaticamente** nell'ambiente on-premise
* Gli ingegneri che lavorano di notte continuano le loro operazioni con **dati aggiornati**

## Risultato

**Vantaggio sui Costi:**
* **Noleggiando le risorse cloud su base oraria**, il costo mensile è stato ridotto del **60%**
* La necessità di aggiornare i server on-premise **è stata eliminata**

**Aumento delle Prestazioni:**
* I tempi di training AI sono stati ridotti da **8 ore a 1,5 ore**
* La produttività degli ingegneri è aumentata del **40%**

**Lavoro Flessibile:**
* La **coerenza dei dati** tra gli ambienti cloud e on-premise è stata garantita senza interruzioni
* I team del turno notturno **avevano accesso immediato ai dati aggiornati**
