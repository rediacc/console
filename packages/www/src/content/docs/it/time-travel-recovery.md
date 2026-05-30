---
title: Recupero nel Tempo
description: "Recupera dati eliminati settimane fa tramite snapshot btrfs, anche dopo che i tuoi backup normali li hanno già sovrascritti."
category: Use Cases
order: 2
language: it
sourceHash: "4c1fcb1667a89759"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

> **Quando gli altri perdono i dati per sempre, tu puoi viaggiare indietro nel tempo.**

**Nota:** Questo è un **esempio di caso d'uso** che mostra come Rediacc gestisce questo tipo di problema. Siamo una startup. Questi sono scenari realistici per cui il prodotto è stato costruito, non casi studio di clienti già completati.

**Scenario di crisi:** Un nuovo assunto ha **eliminato accidentalmente** righe critiche dal tuo database di produzione 3 settimane fa. Il tuo sistema di backup conserva solo 2 settimane di storia. Con una configurazione normale, quei dati sono perduti.

## Il Problema

Mehmet gestisce il database di una grande piattaforma e-commerce. Una mattina i clienti iniziano a lamentarsi che alcuni record di ordini precedenti **non sono visibili**. Indaga. Un ingegnere appena assunto aveva **eliminato accidentalmente** righe critiche dal database di produzione 3 settimane fa, **connettendosi al database di produzione invece dell'ambiente di test**. L'errore classico che ogni DBA ha commesso almeno una volta o ha visto fare a un junior.

**Sistema di backup esistente:**
* I backup completi vengono eseguiti una volta alla settimana
* I **backup incrementali** vengono registrati giornalmente

**Il dilemma:** l'eliminazione è avvenuta **prima della data dei backup completi**, quindi i dati persi non si trovano in nessun file di backup. I backup giornalieri **registrano solo i dati più recenti**, quindi **gli elementi eliminati non possono essere recuperati**.

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

Ecco la configurazione a "macchina del tempo" che Mehmet costruisce con Rediacc:

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
