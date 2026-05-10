---
title: "Regioni dei Dati"
description: "Dove vengono archiviati i tuoi dati e come funziona la residenza regionale dei dati. La scelta è permanente ed è importante farla con cura."
category: "Concepts"
order: 3
language: it
---

Quando crei un account Rediacc, scegli una regione dei dati. Tutti i tuoi dati rimangono in quella regione. Questa scelta è permanente e non può essere modificata dopo la registrazione.

## Regioni Disponibili

| Regione | Posizione | Dominio |
|---|---|---|
| **Europa (EU)** | Francoforte, Germania | `eu.rediacc.com` |
| **Stati Uniti (US)** | Virginia, USA | `us.rediacc.com` |
| **Asia Pacifico** | Tokyo, Giappone | `asia.rediacc.com` |

La tua regione viene rilevata automaticamente dal tuo fuso orario durante la registrazione. Puoi ignorare il suggerimento nel selettore di regione.

## Cosa Rimane nella Tua Regione

Questi tipi di dati vengono archiviati ed elaborati esclusivamente nella regione scelta:

- **Dati dell'account**: email, nome, organizzazione, appartenenza ai team
- **Registrazioni di fatturazione e abbonamento**: piano, attivazioni, emissioni di licenze
- **Blob di configurazione cifrati**: cifrati lato client con crittografia zero-knowledge. Il server non può decifrarli.
- **Email transazionali**: reimpostazione password, magic link, notifiche. Inviate da un endpoint email regionale.

## Cosa È Globale

Questi elementi non sono specifici per regione:

- **Artefatti di rilascio della CLI**: binari pubblici ospitati su una CDN globale
- **Sito web di marketing**: servito globalmente dai nodi edge
- **Elaborazione dei pagamenti Stripe**: gestita dall'infrastruttura propria di Stripe nell'ambito del loro accordo per il trattamento dei dati

## Infrastruttura Regionale

| Componente | EU | US | Asia |
|---|---|---|---|
| Database (D1) | Europa Orientale (EEUR) | Nord America Orientale (ENAM) | Asia Pacifico (APAC) |
| Archiviazione config (R2) | Giurisdizione EU | US | Asia Pacifico |
| Email (SES) | Francoforte (eu-central-1) | Virginia (us-east-1) | Francoforte (eu-central-1) |

Ogni regione esegue un'infrastruttura indipendente. Non esistono query interregionali né flussi di dati tra regioni.

## Garanzie dei Dati EU

La regione EU fornisce garanzie aggiuntive per le organizzazioni con requisiti di residenza dei dati europei:

- **Database D1**: eseguito in Europa Orientale (hint di posizione EEUR)
- **Archiviazione config R2**: utilizza l'applicazione giurisdizionale EU (garanzia contrattuale, non solo un hint di posizione)
- **Email**: inviate da Francoforte (eu-central-1)
- **Decisione di adeguatezza reciproca EU-Giappone (2019)**: abilita flussi di dati conformi per l'infrastruttura della regione Asia

Per la mappatura dettagliata del GDPR, consulta [Conformità GDPR](/en/docs/legal-gdpr).

## Crittografia Zero-Knowledge

I blob di configurazione archiviati in R2 vengono cifrati lato client prima del caricamento utilizzando lo scambio di chiavi X25519 e AES-256-GCM. Il server conserva solo il testo cifrato. Né Rediacc né alcun fornitore di infrastrutture può leggere i tuoi dati di configurazione.

Le chiavi vengono derivate da una passkey con estensione PRF. Il server memorizza un segreto lato server che partecipa alla derivazione della chiave, ma né la passkey da sola né il segreto del server da solo possono decifrare i dati.

Per i dettagli sull'architettura di crittografia, consulta [Archiviazione Config](/en/docs/config-storage).

## Come Scegliere

- **Scegli la regione più vicina a te** per la latenza più bassa.
- **Scegli la regione richiesta dalla tua organizzazione** per la conformità. Se la tua azienda impone la residenza dei dati nell'EU, scegli EU.
- **La scelta è permanente.** Non puoi spostare il tuo account in una regione diversa dopo la registrazione.

## Per i Responsabili della Conformità

Proprietà tecniche dell'architettura regionale:

- **Database separati per regione**: ogni regione ha il proprio database Cloudflare D1. Nessuna query interregionale.
- **Archiviazione separata per regione**: ogni regione ha il proprio bucket R2. L'EU utilizza l'applicazione giurisdizionale.
- **Recapito email tramite AWS SES**: le email transazionali vengono inviate tramite AWS SES. EU e US utilizzano endpoint regionali dedicati; l'Asia Pacifico viene instradata attraverso l'endpoint EU (eu-central-1).
- **Un utente, una regione**: un account utente esiste in esattamente una regione. Non può coprire più regioni.
- **Isolamento dei webhook**: gli eventi webhook di Stripe vengono ricevuti da tutti i worker regionali ma elaborati solo dalla regione che possiede il record del cliente.
- **Crittografia config zero-knowledge**: il server non può leggere i dati di configurazione. Le chiavi di crittografia non lasciano mai il dispositivo client.

Per una visione più ampia della conformità alla sovranità dei dati, consulta [Sovranità dei Dati](/en/docs/legal-data-sovereignty).
