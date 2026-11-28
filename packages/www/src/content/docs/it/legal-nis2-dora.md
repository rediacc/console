---
title: "NIS2 e DORA"
description: "Come Rediacc risponde alla direttiva UE NIS2 sulla cybersicurezza e ai requisiti di resilienza operativa digitale di DORA."
category: "Legal"
tags:
  - compliance
subcategory: regulations
order: 8
language: it
sourceHash: "e1cdb4848a2124ae"
sourceCommit: "5f4fc4c93d74073e5a9b8f8431444495a7f641b6"
---

NIS2 e DORA sono regolamenti dell'UE che impongono requisiti di cybersicurezza e resilienza operativa alle organizzazioni che operano in infrastrutture critiche e nel settore finanziario. Entrambi sono entrati in vigore nel 2025 e si applicano in modo trasversale ai settori dell'UE.

## Direttiva NIS2

La Network and Information Security Directive 2 (NIS2) stabilisce i requisiti di cybersicurezza per le entità "essenziali" e "importanti" in settori quali energia, trasporti, sanità, infrastrutture digitali e pubblica amministrazione.

Testo integrale: [Direttiva (UE) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)

### Mappatura dei requisiti NIS2

| Requisito NIS2 | Capacità di Rediacc |
|-----------------|-------------------|
| Misure di gestione del rischio (Art. 21) | Cifratura LUKS2 a riposo, isolamento di rete per repository, accesso esclusivo via SSH, log di audit (oltre 70 tipologie di eventi incluse le operazioni sulle macchine) |
| Gestione degli incidenti (Art. 21(2)(b)) | Record di flusso di rete per repository, a un livello scelto dal cliente (destinazione, porta e protocollo; ai livelli superiori processo, nome DNS e aperture di file sensibili), vengono inviati come batch firmati e incatenati per hash a un bucket su cui gli amministratori del cliente non possono scrivere, solo sui piani a pagamento. Una timeline di indagine per repository verifica la catena nel browser, e Declare incident avvia i timer delle scadenze. I record di flusso mostrano volume e destinazione, non il contenuto. I piani Free e Community non registrano nulla. L'isolamento per repository limita il raggio d'impatto. Gli oltre 70 tipi di eventi di audit (autenticazione, token, configurazione, licenze, operazioni sulle macchine) registrano chi ha fatto cosa. |
| Continuità operativa (Art. 21(2)(c)) | `rdc repo push/pull` con backup cifrato verso destinazioni multiple. Snapshot CoW per il rollback immediato. |
| Sicurezza della supply chain (Art. 21(2)(d)) | Il self-hosted elimina il rischio della supply chain SaaS. Nessun cloud provider di terze parti tratta i dati dell'organizzazione. |
| Sicurezza di rete (Art. 21(2)(e)) | Daemon Docker per repository, regole iptables, isolamento IP loopback (/26 subnet). |
| Cifratura (Art. 21(2)(h)) | Cifratura obbligatoria LUKS2 AES-256. Config store zero-knowledge con AES-256-GCM. |
| Controllo degli accessi (Art. 21(2)(i)) | Autenticazione con chiave SSH, token API con ambito limitato e vincolo IP, autenticazione a due fattori (TOTP). |
| Segnalazione degli incidenti, allerta precoce 24h (Art. 23) | Declare incident registra il momento della consapevolezza e avvia da esso tre timer: 24 ore per l'early warning, 72 ore per la notifica dell'incidente e un mese di calendario dopo la notifica per il report finale (Art. 23(4)). Ogni fase è preparata come report firmato in PDF, JSON e STIX 2.1, con una mappa dei campi che collega ogni campo del report alla direttiva. Stabilire se un incidente è significativo, e che cosa inviare al CSIRT o all'autorità competente, resta a valutazione e a carico del cliente. |

### Rischio della supply chain

La sicurezza della supply chain è una preoccupazione centrale della NIS2 (Art. 21(2)(d)). Le organizzazioni devono valutare e gestire i rischi derivanti dai propri fornitori di servizi e prodotti ICT.

Rediacc self-hosted elimina la più grande superficie di attacco della supply chain: nessun SaaS di terze parti gestisce i propri dati, nessun cloud provider ha accesso logico alla propria infrastruttura e nessun ambiente multi-tenant crea esposizione alla postura di sicurezza degli altri clienti. Le violazioni dei vendor SaaS hanno causato danni a cascata in migliaia di organizzazioni. [L'attacco ransomware del 2020 a Blackbaud ha esposto i dati di oltre 13.000 organizzazioni clienti, con un costo di 49,5 milioni di dollari in accordi transattivi.](https://www.sec.gov/newsroom/press-releases/2023-48)

---

## DORA (Digital Operational Resilience Act)

DORA stabilisce i requisiti per la gestione del rischio ICT, la segnalazione degli incidenti, i test di resilienza e la gestione del rischio di terze parti per il settore finanziario dell'UE. Si applica a banche, compagnie assicurative, imprese di investimento, fornitori di servizi su cripto-attività e ai loro fornitori ICT critici.

Testo integrale: [Regolamento (UE) 2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj)

### Mappatura dei requisiti DORA

| Requisito DORA | Capacità di Rediacc |
|-----------------|-------------------|
| Quadro di gestione del rischio ICT (Art. 6) | Cifratura, isolamento, log di audit e backup costituiscono il livello dei controlli tecnici. |
| Protezione e prevenzione (Art. 9) | Cifratura LUKS2 AES-256 a riposo. L'isolamento di rete impedisce i movimenti laterali. Accesso esclusivo via SSH. |
| Rilevamento (Art. 10) | I rilevatori di anomalie girano sulla macchina (anche offline) e sul server sui record di flusso inviati, e generano un avviso di sicurezza per traffico insolito. I rilevatori segnalano scostamenti da una baseline appresa per repository; non provano una violazione e coprono solo i repository con la cattura attiva su un piano a pagamento. Gli oltre 70 tipi di eventi di audit (ciclo di vita dei repository, backup, sincronizzazione, terminale) restano disponibili con filtraggio per utente e per team nella dashboard di amministrazione e nel portale, e nei log di sistema per una difesa in profondità. |
| Risposta e recupero (Art. 11) | Snapshot CoW per il rollback immediato. `rdc repo push/pull` per il ripristino verso destinazioni multiple. Test di disaster recovery basati su fork. |
| Rischio ICT di terze parti (Art. 28-30) | Il self-hosted elimina completamente la classificazione come "fornitore ICT critico di terze parti". |
| Test di resilienza operativa digitale (Art. 24-27) | La clonazione CoW consente test di penetrazione guidati dalla minaccia su ambienti simili a quello di produzione senza esporre i dati. Clone, test, eliminazione. |

### Rischio dei fornitori ICT terzi

I requisiti più onerosi di DORA riguardano la gestione dei fornitori ICT critici di terze parti (Art. 28-30). Gli istituti finanziari devono tenere registri dei fornitori ICT, effettuare valutazioni del rischio, negoziare specifiche clausole contrattuali e pianificare strategie di uscita.

Rediacc self-hosted evita tutto ciò. Nessun fornitore ICT terzo da registrare, valutare o monitorare. L'istituto finanziario controlla direttamente la propria infrastruttura.

### Test di resilienza

DORA impone test di resilienza operativa digitale, inclusi i test di penetrazione guidati dalla minaccia (TLPT) per i grandi istituti (Art. 26). La clonazione CoW gestisce questo aspetto direttamente:

1. Fork dell'ambiente di produzione (istantaneo, sulla stessa macchina, senza trasferimento di dati)
2. Esecuzione dei test di penetrazione sul fork
3. Eliminazione del fork al termine

La produzione non viene mai toccata, eppure l'ambiente di test è una replica esatta. Nessun dato lascia la macchina.
