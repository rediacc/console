---
title: Archivio di Configurazione
description: Sincronizzazione cifrata zero-knowledge della configurazione con sblocco tramite passkey, password principale o codice di recupero
category: Guides
order: 8
language: it
sourceHash: "73c75b1f00630553"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Archivio di Configurazione

L'archivio di configurazione fornisce la sincronizzazione cifrata zero-knowledge della tua configurazione CLI tra dispositivi. Le tue configurazioni sono cifrate lato client con una chiave di cifratura del contenuto (CEK); il server non vede mai i dati in testo in chiaro.

## Metodi di sblocco (slot delle chiavi)

C'è una sola CEK per archivio, avvolta indipendentemente per ciascun metodo di sblocco, in modo simile agli slot delle chiavi di LUKS. Ogni singolo slot apre la stessa chiave, e gli slot possono essere aggiunti o rimossi senza dover ricifrare i dati:

| Metodo | Cos'è | Note |
|--------|-----------|-------|
| **Passkey** | Passkey WebAuthn con estensione PRF | L'opzione più solida; basata su hardware |
| **Password principale** | Una password a tua scelta, rafforzata con PBKDF2-SHA256 (600.000 iterazioni) | Funziona senza hardware compatibile con PRF; abilita anche l'iscrizione CLI headless |
| **Codice di recupero** | Un codice generato nel formato `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` | Mostrato una sola volta alla creazione; conservalo in un posto sicuro |

Ogni metodo alimenta la stessa pipeline: lo slot produce un segreto che si combina con un segreto conservato dal server per sbloccare la CEK. Nessuna delle due metà da sola è sufficiente, quindi la proprietà zero-knowledge vale per tutti e tre i metodi: il segreto dello slot non raggiunge mai il server.

Gli slot si gestiscono dal portale, nella pagina Archivio di Configurazione. Le organizzazioni che vogliono uno sblocco solo hardware possono attivare la policy **richiedi passkey**, che rifiuta e revoca gli slot non-passkey per l'intero archivio.

Lo sblocco è per dispositivo: sblocchi una volta su un nuovo dispositivo, dopodiché le operazioni CLI quotidiane (push/pull) funzionano senza toccare una passkey o digitare una password.

## Prerequisiti

- **Autenticazione a due fattori** abilitata sull'account
- Per il metodo **passkey**: un provider di passkey con supporto PRF, ad esempio una chiave di sicurezza FIDO2 (come YubiKey), iCloud Keychain, Google Password Manager, 1Password o Dashlane
- **Browser**: Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+

Il requisito PRF si applica solo allo slot passkey. I metodi password principale e codice di recupero funzionano con qualsiasi browser supportato.

## Configurazione

1. Vai ad **Archivio di Configurazione** nella barra laterale, poi fai clic su **Configura Archivio di Configurazione**
2. La checklist dei requisiti verifica il browser, il 2FA e lo stato della sessione
3. Fai clic su **Avvia Configurazione**. Per uno slot passkey dovrai toccare la tua chiave di sicurezza due volte:
   - Primo tocco: registra la passkey
   - Secondo tocco: deriva le chiavi di cifratura tramite PRF
4. Configurazione completata; il segreto della passkey è memorizzato nel portachiavi del sistema operativo

Dopo la configurazione, aggiungi uno slot con password principale o codice di recupero dalla pagina Archivio di Configurazione, così un autenticatore perso o non supportato non ti blocca fuori.

## Compatibilità dei Provider PRF

| Provider | Supporto PRF | Piattaforme |
|----------|:-----------:|-----------|
| YubiKey / chiavi di sicurezza FIDO2 | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Multipiattaforma |
| Estensione Bitwarden | ❌ | In sviluppo |
| Windows Hello | ❌ | Non supportato |

## Iscrizione CLI headless

Una macchina senza browser (un server, un runner CI, un daemon executor) può iscriversi a un archivio esistente con il metodo della password principale:

```bash
rdc config remote enable --password
```

Requisiti:

- Uno **slot con password principale** già predisposto tramite il portale (il browser detiene la chiave durante il provisioning, quindi questo passaggio non può essere headless di per sé)
- Un **token API con lo scope `config:enroll`** per autenticare la chiamata

L'iscrizione è una lettura: la CLI recupera i parametri KDF pubblici dello slot e la chiave avvolta, deriva localmente il segreto della password e sblocca la CEK sul dispositivo. Concede al dispositivo la capacità di decifrare e sincronizzare la configurazione; non modifica l'archivio.

## Rotazione delle chiavi

Ruotare la CEK dell'archivio la riavvolge con una nuova generazione:

- I **codici di recupero vengono sempre invalidati** dalla rotazione: generane e salvane uno nuovo subito dopo
- Uno **slot con password principale** sopravvive solo se la password viene reinserita durante la procedura guidata di rotazione
- Uno slot rimasto indietro a una generazione precedente viene segnalato come obsoleto invece di fallire con un errore di decifratura poco chiaro

## Gestione dei Membri

L'archivio di configurazione ha scope per organizzazione. I membri vengono gestiti tramite il portale web:

- **Visualizza i membri**: Archivio di Configurazione > Membri
- **Aggiungi un membro**: attualmente solo tramite CLI (UI web pianificata)
- **Rimuovi un membro**: fai clic sul pulsante di rimozione nella pagina Membri (richiede 2FA + ri-autenticazione)

Le protezioni di sicurezza impediscono di rimuovere l'ultimo membro attivo o di rimuovere se stessi.

## Sicurezza

- **Zero-knowledge**: il server memorizza dati con tripla cifratura che non riesce a decifrare
- **Chiave divisa**: la decifratura richiede sia il segreto dello slot (client) che il segreto del server
- **Token rotanti**: ogni chiamata API usa un token fresco; i vecchi token si autodistruggono
- **Binding IP**: i token sono legati al tuo IP al primo utilizzo
- **Revoca istantanea**: i membri rimossi perdono l'accesso entro 30 secondi

## Risoluzione dei Problemi

| Errore | Causa | Soluzione |
|-------|-------|-----|
| PRF non supportato | L'autenticatore non ha l'estensione PRF | Usare YubiKey, iCloud Keychain, 1Password o Dashlane, oppure aggiungere uno slot con password principale |
| X25519 non supportato | Versione del browser troppo vecchia | Aggiornare a Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+ |
| Già configurato | L'archivio esiste per la tua organizzazione | Visitare /account/config-storage per gestirlo |
| Archivio di configurazione non configurato | Blob storage mancante sul server | Contattare il proprio amministratore per configurare R2/RustFS |
| Token scaduto | Nessuna attività per 24 ore | Eseguire qualsiasi comando dell'archivio di configurazione per aggiornare |
| Impossibile rimuovere l'ultimo membro | Bloccherebbe permanentemente l'archivio | Aggiungere prima un altro membro |
| Slot obsoleto | Lo slot risale a prima dell'ultima rotazione delle chiavi | Aggiungere di nuovo lo slot (i codici di recupero vanno rigenerati dopo ogni rotazione) |

## Correlati

- [Console Web](/it/docs/web-console), sbloccare l'archivio nel browser per eseguire comandi
- [Proxy ed Executor](/it/docs/proxy-and-executor), come la chiave sbloccata viene concessa a un executor
