---
title: Archivio di Configurazione
description: Sincronizzazione cifrata lato client della configurazione con sblocco tramite passkey, password principale o codice di recupero
category: Guides
tags:
  - account
  - security
subcategory: account
order: 8
language: it
sourceHash: "ccced160d151eeeb"
sourceCommit: "6cfcb0017e6db164abaf81c7e0a10d0d8086370b"
---

# Archivio di Configurazione

L'archivio di configurazione sincronizza una configurazione CLI tra dispositivi. Le configurazioni sono cifrate sul dispositivo con una chiave di cifratura del contenuto (CEK) che il server non possiede mai. La sezione [Sicurezza](#security) indica esattamente da cosa questo protegge e da cosa no.

## Metodi di sblocco (slot delle chiavi)

C'è una sola CEK per archivio, avvolta indipendentemente per ciascun metodo di sblocco, in modo simile agli slot delle chiavi di LUKS. Ogni singolo slot apre la stessa chiave, e gli slot possono essere aggiunti o rimossi senza dover ricifrare i dati:

| Metodo | Cos'è | Note |
|--------|-----------|-------|
| **Passkey** | Passkey WebAuthn con estensione PRF | L'opzione più solida; basata su hardware |
| **Password principale** | Una password a tua scelta, rafforzata con PBKDF2-SHA256 (600.000 iterazioni) | Funziona senza hardware compatibile con PRF; abilita anche l'iscrizione CLI headless |
| **Codice di recupero** | Un codice generato nel formato `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` | Mostrato una sola volta alla creazione; conservalo in un posto sicuro |

Ogni metodo alimenta la stessa pipeline: lo slot produce un segreto che si combina con un segreto conservato dal server per sbloccare la CEK. Nessuna delle due metà da sola è sufficiente, e il segreto dello slot non raggiunge mai il server. Uno slot con password principale è il più debole dei tre: il server dispone di tutto il necessario per testare le password offline, quindi la password deve essere robusta. Gli slot passkey e codice di recupero non hanno questa debolezza.

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
3. Scegli il primo metodo di sblocco, poi fai clic su **Crea archivio di configurazione**:
   - **Passkey**, se il tuo provider supporta PRF: tocchi la chiave di sicurezza due volte, una per registrarla e una per derivare le chiavi di cifratura.
   - **Password principale**, che funziona con qualsiasi browser, anche con i provider di passkey senza PRF come Bitwarden.
   - Facoltativamente un **codice di recupero**, mostrato una sola volta, da salvare prima che l'archivio venga creato.
4. Configurazione completata. La CLI conserva il segreto di sblocco nel portachiavi del sistema operativo.

Puoi aggiungere una passkey in seguito dalla pagina Config Storage. Mantieni almeno due metodi di sblocco, così un autenticatore perso o non supportato non ti lascia fuori.

## Compatibilità dei Provider PRF

| Provider | Supporto PRF | Piattaforme |
|----------|:-----------:|-----------|
| YubiKey / chiavi di sicurezza FIDO2 | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Multipiattaforma |
| Estensione Bitwarden | ❌ | Usa invece una password principale |
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

## Abilitazione e letture offline

`rdc config remote enable` collega la configurazione attiva all'archivio. Quando l'archivio è vuoto, l'abilitazione **lo inizializza a partire dalla configurazione locale corrente**: le risorse locali vengono inviate (push) come prima versione dell'archivio, quindi recuperate (pull) per verificare il ciclo completo. Quando l'archivio contiene già dei dati, l'abilitazione si riconcilia con esso invece di sovrascriverlo (si interrompe in caso di divergenza reale, a meno che non venga passato `--force`).

Una volta abilitata, la configurazione mantiene una **cache di lettura** completa, cifrata a riposo con lo stesso meccanismo di qualsiasi configurazione locale, così l'archivio resta utilizzabile anche quando il server dell'account non è raggiungibile:

- **Le letture funzionano offline.** Il contenuto in cache viene servito con un avviso di obsolescenza su stderr, etichettato con la versione e il timestamp memorizzati in cache (`cachedVersion` / `cachedAt`).
- **Le scritture richiedono il server e falliscono in modo sicuro.** Non esiste una coda di scrittura offline: una scrittura che non riesce a raggiungere il server fallisce indicando il server. Se un comando di scrittura ha avuto successo, la modifica è presente sul server.
- **Le modifiche concorrenti da due macchine** si risolvono tramite pull-replay-repush: il server accetta un push solo sopra la versione che sostituisce, e il push perdente viene rieseguito sulla copia aggiornata, così una modifica simultanea altrove non viene sovrascritta.
- **Una configurazione locale** (senza blocco `remote`) non è interessata da nulla di tutto ciò e funziona interamente offline.

## Cosa viene sincronizzato

Tutto in una configurazione viene sincronizzato, incluso l'ID di rete di ogni repository, tranne questi campi locali del dispositivo: `schemaVersion`, `version`, `remote`, `encryption`, `renetPath`, `credentials.masterPasswordVerifier`, e i campi di accesso `account.accountServer` e `account.e2ePublicKey`. L'accesso e la disconnessione sono per dispositivo.

## Versioni e ripristino

Il server conserva le ultime 50 versioni di ogni configurazione.

```bash
rdc config remote versions
rdc config remote restore <version>
```

Un ripristino pubblica il vecchio contenuto come nuova versione sopra quella corrente; il numero di versione non torna mai indietro. Ogni dispositivo riceve il contenuto ripristinato al pull successivo, e il ripristino viene registrato nel log di audit.

## Rotazione delle chiavi

Ruotare la CEK dell'archivio la riavvolge con una nuova generazione:

- I **codici di recupero vengono sempre invalidati** dalla rotazione: generane e salvane uno nuovo subito dopo
- Uno **slot con password principale** sopravvive solo se la password viene reinserita durante la procedura guidata di rotazione
- Uno slot rimasto indietro a una generazione precedente viene segnalato come obsoleto invece di fallire con un errore di decifratura poco chiaro
- I token di configurazione degli altri membri vengono revocati, e a un dispositivo che detiene ancora la vecchia chiave viene chiesto di riabilitarsi con `rdc config remote enable`

## Gestione dei Membri

L'archivio di configurazione ha scope per organizzazione. I membri vengono gestiti tramite il portale web:

- **Visualizza i membri**: Archivio di Configurazione > Membri
- **Aggiungi un membro**: attualmente solo tramite CLI (UI web pianificata)
- **Rimuovi un membro**: fai clic sul pulsante di rimozione nella pagina Membri (richiede 2FA + ri-autenticazione)

Le protezioni di sicurezza impediscono di rimuovere l'ultimo membro attivo o di rimuovere se stessi.

Le configurazioni nell'archivio sono inoltre delimitate per team, ma questa delimitazione è un **controllo di accesso lato server, non un isolamento crittografico**: un'unica CEK a livello di organizzazione cifra le configurazioni di tutti i team, ed è il server a imporre quali team un membro può leggere.

## Sicurezza

**Cosa è protetto.** Le configurazioni archiviate sono confidenziali rispetto a una compromissione dello storage del server e rispetto a un operatore passivo. Ogni blob è vincolato al proprio archivio, configurazione, team e versione, quindi il server non può scambiare il blob di una configurazione con quello di un'altra né alterarlo senza che venga rilevato.

**Cosa non è protetto.** Un operatore che serve codice malevolo del portale può leggere la chiave nel browser. Un operatore può anche negare la versione più recente a un dispositivo che non l'ha mai vista.

| Il server può | Il server non può |
|---|---|
| Vedere gli id di configurazione, i team, i numeri di versione, i timestamp, le dimensioni dei blob, quanti campi una configurazione impegna e il tipo di ciascuno, e gli indirizzi IP dei client | Vedere i nomi di macchine, repository o archivi (sono offuscati) né alcun valore di configurazione |
| Rifiutare, ritardare o eliminare configurazioni e la loro cronologia | Servire il contenuto di una configurazione come quello di un'altra, o modificarlo, senza che il dispositivo lo rilevi |
| Servire una vecchia versione a un dispositivo che non ne ha mai vista una più recente | Servire alla CLI una versione più vecchia di una già vista: la CLI la rifiuta |
| Testare offline le password principali | Aprire uno slot passkey o codice di recupero |

Altre protezioni:

- **Chiave divisa**: la decifratura richiede sia il segreto dello slot (sul dispositivo) sia il segreto del server
- **L'eliminazione richiede conoscenza**: rimuovere un valore impegnato da una configurazione richiede di dimostrare che il valore era noto, così un attore con accesso parziale non può eliminare campi silenziosamente
- **Token rotanti**: ogni richiesta fa ruotare il token di configurazione; un token è legato all'IP del suo primo utilizzo e scade dopo 7 giorni
- **Revoca**: rimuovere un membro elimina contemporaneamente i suoi slot delle chiavi e i suoi token; ciò che aveva già scaricato resta sul suo dispositivo, e una rotazione della CEK impedisce a una chiave conservata di aprire versioni successive

## Risoluzione dei Problemi

| Errore | Causa | Soluzione |
|-------|-------|-----|
| PRF non supportato | L'autenticatore non ha l'estensione PRF | Usare YubiKey, iCloud Keychain, 1Password o Dashlane, oppure aggiungere uno slot con password principale |
| X25519 non supportato | Versione del browser troppo vecchia | Aggiornare a Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+ |
| Già configurato | L'archivio esiste per la tua organizzazione | Visitare /account/config-storage per gestirlo |
| Archivio di configurazione non configurato | Blob storage mancante sul server | Contattare il proprio amministratore per configurare R2/RustFS |
| Token scaduto | Nessuna attività per 7 giorni, oppure la macchina ha cambiato rete | Rinnovato automaticamente tramite l'accesso; se non c'è alcun accesso salvato, eseguire `rdc subscription login` o `rdc config remote enable` |
| La configurazione è tornata a una versione precedente | Il server ha restituito una copia più vecchia di quella già vista da questo dispositivo | Nulla è cambiato localmente; riprovare, e segnalarlo se persiste |
| Impossibile rimuovere l'ultimo membro | Bloccherebbe permanentemente l'archivio | Aggiungere prima un altro membro |
| Slot obsoleto | Lo slot risale a prima dell'ultima rotazione delle chiavi | Aggiungere di nuovo lo slot (i codici di recupero vanno rigenerati dopo ogni rotazione) |

## Correlati

- [Console Web](/it/docs/web-console), sbloccare l'archivio nel browser per eseguire comandi
- [Proxy ed Executor](/it/docs/proxy-and-executor), come la chiave sbloccata viene concessa a un executor
