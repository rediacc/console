---
title: "Conformità ISO 27001"
description: "Come Rediacc si mappa ai controlli di sicurezza delle informazioni ISO 27001 per cifratura, gestione degli accessi e sicurezza operativa."
category: "Legal"
order: 5
language: it
---

ISO/IEC 27001 è uno standard internazionale per i sistemi di gestione della sicurezza delle informazioni (ISMS), pubblicato dall'International Organization for Standardization (ISO) e dalla International Electrotechnical Commission (IEC). La versione corrente è ISO/IEC 27001:2022.

Riferimento: [ISO/IEC 27001:2022](https://www.iso.org/standard/27001)

Rediacc è un componente del livello dei controlli tecnici all'interno di un ISMS. La tabella seguente mappa le capacità di Rediacc ai domini di controllo rilevanti dell'Allegato A.

## Mappatura dei controlli dell'Allegato A

| Dominio di controllo | Controllo | Capacità di Rediacc |
|---------------|---------|-------------------|
| **A.8**, Gestione degli asset | A.8.1 Inventario degli asset | Ogni repository è un asset discreto e identificabile con un GUID univoco. `rdc machine query --name <machine> --repositories` elenca tutti i repository con dimensioni, stato di montaggio e conteggio dei container. |
| **A.8**, Gestione degli asset | A.8.24 Uso della crittografia | Cifratura obbligatoria LUKS2 AES-256 su tutti i repository. Gestione delle chiavi: le credenziali sono archiviate solo nella configurazione locale dell'operatore, mai sul server. |
| **A.9**, Controllo degli accessi | A.9.2 Gestione degli accessi degli utenti | Autenticazione con chiave SSH. Token API con vincolo IP, ambito di team e revoca automatica alla rimozione dal team. Supporto all'autenticazione a due fattori (TOTP). |
| **A.10**, Crittografia | A.10.1 Controlli crittografici | LUKS2 con parametri di chiave configurabili. Credenziali di cifratura per repository. Tutto il trasporto remoto tramite SSH. Il config store implementa la cifratura zero-knowledge: AES-256-GCM con derivazione della chiave HKDF, scambio di chiavi membro X25519 e chiavi SDK con finestra temporale per la revoca immediata. |
| **A.12**, Sicurezza operativa | A.12.3 Backup | `rdc repo backup push/pull` con archiviazione offsite cifrata verso destinazioni multiple (SSH, S3, B2, Azure, GDrive). Snapshot CoW per il ripristino a un momento preciso. `rdc repo validate` verifica lo stato del backup e l'integrità del repository. |
| **A.12**, Sicurezza operativa | A.12.4 Registrazione e monitoraggio | Oltre 70 tipologie di eventi (autenticazione, token API, configurazione, licenze, operazioni sulle macchine). Monitoraggio dello stato delle macchine tramite `rdc machine query`. Monitoraggio dello stato dei container e delle risorse. |
| **A.13**, Sicurezza delle comunicazioni | A.13.1 Gestione della sicurezza di rete | Isolamento del daemon Docker per repository. Regole iptables bloccano il traffico tra repository. Sottoreti IP loopback (/26) per repository. Reverse proxy con terminazione TLS per l'accesso esterno. |
| **A.14**, Sviluppo dei sistemi | A.14.2 Sicurezza nello sviluppo | Gli ambienti di sviluppo basati su fork offrono parità con la produzione senza esporre i dati di produzione. I lifecycle hook del Rediaccfile consentono la sanitizzazione automatizzata dei dati negli ambienti clonati. |

## Gestione degli asset

Il modello a repository di Rediacc supporta naturalmente i requisiti di inventario degli asset:

- Ogni repository ha un GUID univoco assegnato alla creazione
- I repository sono enumerabili per macchina (`rdc machine query --repositories`)
- Lo stato di cifratura, lo stato di montaggio, il conteggio dei container e l'utilizzo del disco di ogni repository sono visibili
- Le relazioni di fork tracciano la derivazione degli ambienti clonati

## Gestione delle modifiche

Il flusso di lavoro fork-test-promozione si allinea ai requisiti di gestione delle modifiche di ISO 27001:

1. **Fork**: creare una copia isolata dell'ambiente di produzione
2. **Test**: applicare e validare le modifiche nel fork
3. **Promozione**: utilizzare `rdc repo takeover` per sostituire il fork in produzione
4. **Audit**: tutte le operazioni sono registrate con timestamp e identificazione dell'autore

## Miglioramento continuo

- L'esportazione del log di audit supporta le verifiche periodiche della sicurezza
- I controlli di stato delle macchine (`rdc machine query --system`) supportano il monitoraggio operativo
- `rdc repo validate` verifica lo stato del backup dopo ogni operazione
