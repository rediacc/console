---
title: Recupero nel Tempo
description: Recupera dati eliminati accidentalmente settimane fa grazie al recupero basato su snapshot. È più semplice di qualsiasi soluzione tradizionale.
category: Use Cases
order: 2
language: it
---

> **Quando gli altri perdono i dati per sempre, tu puoi viaggiare indietro nel tempo.**

**Nota:** Questo è un **esempio di caso d'uso** che dimostra come Rediacc può risolvere questo problema. Come startup, questi scenari rappresentano applicazioni potenziali piuttosto che casi studio completati.

**Scenario di crisi:** Un dipendente appena assunto ha **eliminato accidentalmente** dati critici dal database di produzione 3 settimane fa. Il sistema di backup dell'organizzazione conservava i backup solo per 2 settimane, rendendo il recupero dei dati quasi impossibile con i metodi tradizionali.

## Il Problema

Mehmet è un esperto di sistemi responsabile del database di una grande organizzazione di e-commerce. Una mattina, in seguito a reclami dei clienti, nota che alcuni record di ordini precedenti **non sono visibili** nel sistema. L'indagine rivela che un dipendente appena assunto ha **eliminato accidentalmente** alcuni dati critici dal database di produzione 3 settimane fa, **connettendosi al database di produzione invece dell'ambiente di test**.

**Sistema di backup esistente:**
* I backup completi vengono eseguiti una volta alla settimana
* I **backup incrementali** vengono registrati giornalmente

**Il dilemma:** L'eliminazione è avvenuta **prima della data dei backup completi**, quindi i dati persi non si trovano nei backup. I backup giornalieri **registrano solo i dati più recenti**, quindi **gli elementi eliminati non possono essere recuperati**.

## Impatto della Crisi

A causa dei dati persi:
* I clienti **non possono elaborare le richieste di rimborso**
* Si verificano incoerenze nel sistema di pagamento
* Le lamentele si diffondono rapidamente sui social media

**Risultati:**
* Il team di assistenza clienti è sotto **forte pressione**
* La reputazione dell'organizzazione viene **rapidamente danneggiata**
* Gli sforzi manuali di recupero dati ottengono **solo il 15% di successo**

**Ulteriore sfida:**
* Per ridurre i costi di archiviazione, l'organizzazione conserva **solo gli ultimi 2 settimane di backup**
* I dati eliminati non si trovano nei **backup recenti**

## Soluzione Rediacc

Mehmet propone una soluzione simile a una "macchina del tempo" con Rediacc:

![Recupero nel Tempo](/img/time-travel-recovery.svg)

### 1. **Snapshot**
* Rediacc acquisisce automaticamente snapshot del sistema ogni ora
* Questi snapshot coprono anche i momenti immediatamente prima dell'eliminazione dei dati

### 2. **Tornare Indietro nel Tempo**
* Mehmet seleziona la data e l'ora in cui si è verificata l'eliminazione nell'interfaccia Rediacc
* Ripristina uno snapshot del sistema di 3 settimane fa in una nuova istanza in 1 minuto

### 3. **Recupero Completo**
* I dati persi vengono ripristinati in modo completo e coerente

## Risultato

* La reputazione dell'organizzazione è stata ripristinata **entro 24 ore**
* La perdita finanziaria è stata evitata per il **95%**
* Rediacc ha dimostrato che è possibile eseguire backup frequenti **senza aumentare i costi di archiviazione**
