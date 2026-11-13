---
title: "Regioni dei Dati"
description: "Dove vengono archiviati i tuoi dati e come funziona la residenza regionale dei dati."
category: "Concepts"
tags:
  - compliance
  - account
subcategory: platform
order: 3
language: it
sourceHash: "05afa82e66e34693"
sourceCommit: "f9c980842b182e644eb84eb1d37e394baf60f7a5"
---

Quando crei un account Rediacc, scegli una regione dei dati. Tutti i tuoi dati rimangono in quella regione. Questa scelta è permanente e non può essere modificata dopo la registrazione. Non esiste un percorso di migrazione. Scegli in base a dove i tuoi dati devono risiedere legalmente, non dove si trovano i tuoi server oggi.

## Regioni Disponibili

| Regione | Posizione | Dominio |
|---|---|---|
| **Europa (EU)** | Unione Europea | `eu.rediacc.cloud` |
| **Stati Uniti (US)** | Nord America orientale | `us.rediacc.cloud` |
| **Asia Pacifico** | Asia Pacifico | `asia.rediacc.cloud` |

La colonna della posizione indica una regione Cloudflare, non una città con un data center. Cloudflare non promette alcuna città.

Il prodotto funziona su questi domini `rediacc.cloud`. Tutta la documentazione e il sito di marketing si trovano su `www.rediacc.com`, che ti indirizza alla regione giusta dal suo selettore di regione.

Alla registrazione il selettore suggerisce una regione in base alla tua posizione, che puoi confermare o cambiare. Al login ti reindirizza alla tua regione dopo un breve conto alla rovescia che puoi annullare o modificare. Se la tua azienda ha un proprio deployment, l'opzione «Cliente Enterprise?» ti ci porta partendo dalla tua email di lavoro. Per trovare la regione viene inviato solo il dominio; l'email serve solo a precompilare la pagina di accesso.

## Cosa Rimane nella Tua Regione

Questi tipi di dati sono archiviati ed elaborati nella regione scelta (per ciò che è garantito, vedi più sotto l'infrastruttura regionale):

- **Dati dell'account**: email, nome, organizzazione, appartenenza ai team
- **Registrazioni di fatturazione e abbonamento**: piano, attivazioni, emissioni di licenze
- **Blob di configurazione cifrati**: cifrati lato client con crittografia zero-knowledge. Il server non può decifrarli.
- **Email transazionali**: reimpostazione password, magic link, notifiche. Inviate da un endpoint email regionale.

## Cosa È Globale

Questi elementi non sono specifici per regione:

- **Artefatti di rilascio della CLI**: binari pubblici ospitati su una CDN globale
- **Sito web di marketing e documentazione**: `www.rediacc.com`, servito globalmente dai nodi edge
- **Elaborazione dei pagamenti Stripe**: gestita dall'infrastruttura propria di Stripe nell'ambito del loro accordo per il trattamento dei dati

## Infrastruttura Regionale

| Componente | EU | US | Asia |
|---|---|---|---|
| Database (D1) | Suggerimento Europa orientale (EEUR) | Suggerimento Nord America orientale (ENAM) | Suggerimento Asia Pacifico (APAC) |
| Archiviazione config (R2) | Giurisdizione UE (garantita) | Nessuna giurisdizione (al meglio) | Nessuna giurisdizione (al meglio) |
| Email (SES) | Francoforte (eu-central-1) | Virginia (us-east-1) | Francoforte (eu-central-1) |

Solo l'archiviazione della configurazione EU è vincolata a una giurisdizione garantita: Cloudflare mantiene nell'UE gli oggetti R2 sotto la giurisdizione UE. La collocazione del database D1 e l'archiviazione US e Asia Pacifico usano suggerimenti di posizione, applicati al meglio delle possibilità. Cloudflare non garantisce che vengano eseguiti nella regione indicata.

Ogni regione esegue un'infrastruttura indipendente. Non esistono query interregionali né flussi di dati tra regioni.

## Garanzie dei Dati EU

Se sei soggetto a requisiti di residenza dei dati europei, la regione EU offre una garanzia ferma e una collocazione al meglio delle possibilità:

- **Database D1**: collocato con il suggerimento di posizione EEUR (Europa orientale), al meglio delle possibilità e senza garanzia
- **Archiviazione della configurazione R2**: vincolata alla giurisdizione UE, che Cloudflare garantisce (un vincolo rigido, non solo un suggerimento di posizione)
- **Email**: inviate da Francoforte (eu-central-1)

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
- **Archiviazione separata per regione**: ogni regione ha il proprio bucket R2. Solo il bucket EU è vincolato a una giurisdizione; US e Asia Pacifico sono collocati al meglio delle possibilità.
- **Recapito email tramite AWS SES**: le email transazionali vengono inviate tramite AWS SES. EU e US utilizzano endpoint regionali dedicati; l'Asia Pacifico viene instradata attraverso l'endpoint EU (eu-central-1).
- **Un utente, una regione**: un account utente esiste in esattamente una regione. Non può coprire più regioni.
- **Isolamento dei webhook**: gli eventi webhook di Stripe vengono ricevuti da tutti i worker regionali ma elaborati solo dalla regione che possiede il record del cliente.
- **Crittografia config zero-knowledge**: il server non può leggere i dati di configurazione. Le chiavi di crittografia non lasciano mai il dispositivo client.

Per una visione più ampia della conformità alla sovranità dei dati, consulta [Sovranità dei Dati](/en/docs/legal-data-sovereignty).
