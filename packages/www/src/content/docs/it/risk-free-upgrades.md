---
title: Aggiornamenti senza rischi
description: Testa gli aggiornamenti del database senza rischi grazie alla clonazione istantanea e agli snapshot orari. È finalmente possibile aggiornare in tutta tranquillità.
category: Use Cases
order: 4
language: it
---

> **Testa tutto. Nessun rischio. Aggiorna con fiducia.**

**Nota:** Questo è un **esempio di caso d'uso** che illustra come Rediacc può risolvere questo problema. In quanto startup, questi scenari rappresentano applicazioni potenziali piuttosto che casi di studio completati.

**Scenario di crisi:** Durante un aggiornamento del database, si è verificato un **errore inatteso** che ha impedito sia il ripristino della versione precedente sia il passaggio a quella nuova. I clienti non riuscivano ad accedere ai sistemi e oltre 5.000 dipendenti non potevano lavorare.

## Il problema

Mehmet è un esperto amministratore di sistema che gestisce database di grandi dimensioni. Decide di **aggiornare un database PostgreSQL da 100 TB dalla versione 13 alla 14**. Il suo piano:

1. **Eseguire un backup** → Tuttavia, il backup richiede **diversi giorni** a causa delle dimensioni dei dati
2. **Eseguire l'aggiornamento nel weekend** → I reparti vengono informati di un'interruzione **sabato dalle 01:00 alle 05:00**

## Impatto della crisi

* Si verifica un **errore inatteso** durante l'aggiornamento
* Il database **non riesce né a tornare alla versione precedente né ad avanzare a quella nuova**
* Nemmeno i team di supporto esterni riescono a risolvere il problema

**Impatti:**
* I clienti **non riescono ad accedere ai sistemi di pagamento e agli ordini**
* I dipendenti dell'organizzazione (**oltre 5.000 persone**) non riescono a lavorare
* Inizia la **perdita di reputazione** e le lamentele aumentano

**Soluzione temporanea:**
* L'ultimo backup viene caricato su **un nuovo server** → **Il costo hardware raddoppia**
* I dati di giovedì e venerdì sono **solo nell'ambiente live**, causando perdita di dati
* Vengono creati **due database con versioni diverse** → Le incoerenze aumentano

## Soluzione Rediacc

Mehmet risolve il problema alla radice con Rediacc:

![Aggiornamenti senza rischi](/img/risk-free-upgrades.svg)

### 1. **Clonazione istantanea**
* Viene creato **un clone del database da 100 TB in pochi secondi**
* I test di aggiornamento vengono eseguiti **senza impatto sul sistema live**

### 2. **Snapshot orari**
* Viene determinato **da quando e a quale passaggio si verifica il fallimento** durante il processo di aggiornamento
* Le operazioni problematiche vengono **identificate in anticipo** e corrette

### 3. **Aggiornamento senza interruzioni**
* Se l'aggiornamento fallisce, **l'ambiente live non viene influenzato**
* Se l'aggiornamento ha successo, il nuovo ambiente live diventa l'ultimo clone

## Risultato

**Risparmio di tempo e costi:**
* Il tempo di backup si è ridotto da **7 giorni a 10 secondi**

**Aggiornamento senza rischi:**
* Gli errori sono stati rilevati in anticipo nell'ambiente di test → **Nessun problema nel sistema live**

**Zero interruzioni:**
* Clienti e dipendenti **non hanno avvertito alcuna interruzione**
