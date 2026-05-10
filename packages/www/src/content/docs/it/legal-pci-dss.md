---
title: "Conformità PCI DSS"
description: "Come Rediacc si allinea ai requisiti PCI DSS per la protezione dei dati delle carte di pagamento tramite crittografia, segmentazione di rete e controllo degli accessi."
category: "Legal"
order: 6
language: it
---

Il Payment Card Industry Data Security Standard (PCI DSS) è obbligatorio per qualsiasi organizzazione che memorizza, elabora o trasmette dati dei titolari di carta. La versione corrente è PCI DSS v4.0.1.

Riferimento: [PCI Security Standards Council](https://www.pcisecuritystandards.org/document_library/)

## Mappatura dei Requisiti

| Requisito PCI DSS | Descrizione | Capacità di Rediacc |
|---------------------|-------------|-------------------|
| **Req 1**, Controlli di sicurezza di rete | Installare e mantenere controlli di sicurezza di rete | Le regole iptables per repository bloccano tutto il traffico tra repository. Ogni repository dispone di una propria sottorete IP di loopback (/26). |
| **Req 2**, Configurazioni sicure | Applicare configurazioni sicure a tutti i componenti di sistema | Gli hook del ciclo di vita del Rediaccfile impongono configurazioni deterministiche e riproducibili. Nessuna credenziale predefinita. Le chiavi LUKS sono generate dall'operatore. |
| **Req 3**, Proteggere i dati dell'account memorizzati | Proteggere i dati dell'account memorizzati con crittografia | Crittografia LUKS2 AES-256 su tutti i volumi dei repository. La crittografia è obbligatoria, non opzionale. Cancellazione crittografica tramite distruzione della chiave LUKS. |
| **Req 4**, Proteggere i dati in transito | Proteggere i dati dei titolari di carta con crittografia robusta durante la trasmissione | Tutte le operazioni remote avvengono tramite SSH. Il trasporto dei backup è cifrato end-to-end. Nessun percorso dati non cifrato. |
| **Req 6**, Sviluppo sicuro | Sviluppare e mantenere sistemi e software sicuri | Il cloning CoW crea ambienti di test isolati senza esporre i dati di produzione dei titolari di carta alle reti di sviluppo. Flusso fork-test-promuovi. |
| **Req 7**, Limitare l'accesso | Limitare l'accesso ai componenti di sistema e ai dati dei titolari di carta in base alla necessità operativa | Socket del daemon Docker per repository. L'accesso a un repository non garantisce l'accesso a un altro. Autenticazione basata su chiave SSH. |
| **Req 8**, Identificare gli utenti e autenticare | Identificare gli utenti e autenticare l'accesso ai componenti di sistema | Autenticazione con chiave SSH. Token API con binding IP e permessi limitati. Autenticazione a due fattori (TOTP). |
| **Req 9**, Limitare l'accesso fisico | Limitare l'accesso fisico ai dati dei titolari di carta | Self-hosted: la sicurezza fisica è sotto il tuo diretto controllo. La crittografia LUKS rende i dischi sottratti illeggibili. |
| **Req 10**, Registrare e monitorare | Registrare e monitorare tutti gli accessi ai componenti di sistema e ai dati dei titolari di carta | Oltre 70 tipi di evento (autenticazione, token API, configurazione, licenze, operazioni macchina). Dashboard amministrativa e portale con filtri per utente, team, tipo e data. CLI `rdc audit` per l'esportazione programmatica. Le operazioni macchina sono registrate anche nei log di sistema per una difesa in profondità. |
| **Req 12**, Politiche organizzative | Supportare la sicurezza delle informazioni con politiche e programmi organizzativi | Il self-hosted elimina l'ambito dei processori di terze parti (Req 12.8). Riduce il perimetro di conformità PCI DSS. |

## Segmentazione di Rete

Il PCI DSS pone grande enfasi sulla segmentazione di rete per isolare il cardholder data environment (CDE). Rediacc la fornisce per architettura:

- Ogni repository opera nel proprio daemon Docker in `/var/run/rediacc/docker-<networkId>.sock`
- I repository dispongono di sottoreti IP di loopback isolate (127.0.x.x/26, 61 IP utilizzabili per rete)
- Le regole iptables imposte da renet bloccano tutto il traffico tra daemon
- I container di repository diversi non possono comunicare a livello di rete

Un repository per l'elaborazione dei pagamenti è isolato a livello di rete da tutte le altre applicazioni sulla stessa macchina. Non è necessaria alcuna configurazione firewall aggiuntiva.

## Riduzione dell'Ambito

Il self-hosted di Rediacc riduce l'ambito di conformità PCI DSS:

- Nessun provider cloud di terze parti nel flusso dei dati dei titolari di carta
- Nessun vendor SaaS da valutare ai sensi del Req 12.8 (fornitori di servizi di terze parti)
- I controlli di sicurezza fisica sono sotto la tua diretta gestione
- Le chiavi di crittografia sono conservate solo nella configurazione locale dell'operatore

## Casi di Applicazione

Una segmentazione di rete inadeguata e la mancanza di crittografia hanno portato a costose azioni di enforcement PCI DSS:

- Heartland Payment Systems (2008): gli aggressori si sono spostati lateralmente su 48 database a causa di una scarsa segmentazione di rete, esponendo 130 milioni di numeri di carte. [Il costo totale ha superato i 200 milioni di dollari.](https://www.philadelphiafed.org/-/media/frbp/assets/consumer-finance/discussion-papers/d-2010-january-heartland-payment-systems.pdf)
- Target (2013): gli aggressori sono passati dall'accesso di rete di un fornitore HVAC ai sistemi punto vendita a causa di un'architettura di rete piatta, acquisendo 40 milioni di carte di pagamento. [Accordo raggiunto per 18,5 milioni di dollari con 47 procuratori generali statali.](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data)
