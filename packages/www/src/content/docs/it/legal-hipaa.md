---
title: "Conformità HIPAA"
description: "Come l'architettura di cifratura e isolamento di Rediacc si mappa ai requisiti di salvaguardia HIPAA per la protezione delle informazioni sanitarie."
category: "Legal"
order: 3
language: it
---

L'Health Insurance Portability and Accountability Act (HIPAA) è una legge federale degli Stati Uniti che stabilisce gli standard per la protezione delle informazioni sanitarie sensibili dei pazienti (PHI). Si applica alle entità coperte (fornitori di assistenza sanitaria, piani sanitari, clearinghouse sanitarie) e ai loro associati commerciali.

Testo integrale: [Public Law 104-191](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm)

## Mappatura delle salvaguardie

L'HIPAA richiede salvaguardie amministrative, tecniche e fisiche. La tabella seguente le mappa alle capacità di Rediacc.

### Salvaguardie tecniche

| Requisito | Riferimento HIPAA | Capacità di Rediacc |
|-------------|----------------|-------------------|
| Controllo degli accessi | [45 CFR 164.312(a)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Autenticazione basata su chiave SSH. Token API con vincolo IP e restrizioni di ambito. L'isolamento del daemon Docker per repository impedisce l'accesso tra repository diversi. |
| Controlli di audit | [45 CFR 164.312(b)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Oltre 70 tipologie di eventi che coprono autenticazione, token API, operazioni di configurazione, licenze e operazioni sulle macchine (ciclo di vita dei repository, backup, sincronizzazione, terminale). Traccia per utente e per team. Esportazione tramite dashboard di amministrazione, pagina attività del portale o CLI `rdc audit`. |
| Controlli di integrità | [45 CFR 164.312(c)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Gli snapshot CoW preservano i dati originali prima delle modifiche. `rdc repo validate` verifica l'integrità del repository e lo stato del backup (container LUKS, coerenza del filesystem, configurazione). |
| Cifratura a riposo | [45 CFR 164.312(a)(2)(iv)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Cifratura LUKS2 AES-256 su tutti i volumi dei repository. Le credenziali sono archiviate solo nella configurazione locale dell'operatore, mai sul server. Il config store utilizza la cifratura zero-knowledge AES-256-GCM con derivazione a chiave suddivisa. Nemmeno il server può decifrare le configurazioni archiviate. |
| Sicurezza della trasmissione | [45 CFR 164.312(e)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Tutte le operazioni remote utilizzano SSH. Il trasporto di backup è cifrato end-to-end. Nessun trasferimento di dati non cifrati. |

### Salvaguardie amministrative

| Requisito | Capacità di Rediacc |
|-------------|-------------------|
| Gestione degli accessi del personale | Token API con permessi circoscritti. Controllo degli accessi basato su team. Revoca automatica dei token alla rimozione dal team. |
| Procedure per gli incidenti di sicurezza | I log di audit forniscono una traccia forense di tutte le operazioni. L'isolamento per repository limita il raggio d'impatto. |
| Pianificazione di emergenza | `rdc repo backup push/pull` supporta il backup cifrato verso destinazioni multiple. Gli snapshot CoW consentono il ripristino immediato. |

### Salvaguardie fisiche

| Requisito | Capacità di Rediacc |
|-------------|-------------------|
| Controlli di accesso alle strutture | Self-hosted: la propria organizzazione controlla la sicurezza fisica dei propri server. Nessuna dipendenza da data center di terze parti per le operazioni core. |
| Sicurezza delle postazioni di lavoro | LUKS cifra tutti i dati a riposo. I repository non montati sono blob cifrati su disco, illeggibili senza le credenziali dell'operatore. |

## Business Associate Agreement (BAA)

Poiché Rediacc è un software self-hosted che gira sulla propria infrastruttura, non tratta, archivia né trasmette PHI attraverso i sistemi di Rediacc (l'azienda). Il requisito tipico del BAA si applica al proprio fornitore di infrastruttura (cloud provider o struttura di colocation), non a Rediacc.

Rediacc opera come strumento software sui propri server, in modo analogo a un sistema operativo o a un motore di database. Non ha accesso ai propri dati. Il config store opzionale sincronizza blob cifrati attraverso i server di Rediacc, ma il suo design zero-knowledge implica che il server non possa decifrare il contenuto. Archivia solo testo cifrato opaco.

## Ambienti di sviluppo con PHI

Quando si clonano ambienti di produzione contenenti PHI per scopi di sviluppo, utilizzare il lifecycle hook `up()` del Rediaccfile per eseguire script di sanitizzazione che:

- Rimuovono le PHI dalle tabelle del database
- Sostituiscono gli identificativi dei pazienti con dati sintetici
- Eliminano i token di sessione e le chiavi API

Gli sviluppatori ottengono un'infrastruttura simile a quella di produzione con dati de-identificati, soddisfacendo lo standard HIPAA del minimo necessario.
