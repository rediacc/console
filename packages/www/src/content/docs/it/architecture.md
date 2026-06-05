---
title: Architettura
description: >-
  Come funziona Rediacc: architettura a due strumenti, rilevamento dell'adattatore, modello di sicurezza e
  struttura della configurazione.
category: Concepts
order: 0
language: it
sourceHash: "6763cd925791d474"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Architettura

Quindi: rdc sulla tua workstation, renet sui tuoi server, comunicano tramite SSH. L'intera architettura di Rediacc poggia su questa separazione. Questa pagina spiega come i due strumenti dividono le responsabilità, come il rilevamento dell'adattatore instrada lo stato, come funziona il modello di sicurezza e come è strutturata la configurazione.

## Panoramica dello stack completo

Il traffico fluisce da Internet attraverso un reverse proxy, verso daemon Docker isolati, ognuno supportato da storage cifrato:

![Full Stack Architecture](/img/arch-full-stack.svg)

Ogni repository ha il proprio daemon Docker, subnet IP di loopback (/26 = 64 IP) e volume BTRFS cifrato con LUKS. Il route server scopre i container in esecuzione su tutti i daemon e alimenta la configurazione di routing a Traefik.

## Architettura a due strumenti

Rediacc usa due binari che collaborano tramite SSH:

![Two-Tool Architecture](/img/arch-two-tool.svg)

- **rdc** gira sulla tua workstation (macOS, Linux o Windows). Legge la configurazione locale, si connette alle macchine remote tramite SSH e richiama i comandi di renet.
- **renet** gira sul server remoto con privilegi di root. Gestisce le immagini disco cifrate con LUKS, i daemon Docker isolati, l'orchestrazione dei servizi e la configurazione del reverse proxy.

Ogni comando digitato localmente si traduce in una chiamata SSH che esegue renet sulla macchina remota. Non è mai necessario accedere ai server manualmente tramite SSH.

Per una regola pratica orientata all'operatore, vedere [rdc vs renet](/en/docs/rdc-vs-renet). È possibile usare anche `rdc ops` per eseguire un cluster di VM locale per il testing; vedere [VM sperimentali](/en/docs/experimental-vms).

## Configurazione

Tutto lo stato della CLI è memorizzato in file di configurazione JSON piatti sotto `~/.config/rediacc/`.

### Adattatore locale (predefinito)

Il predefinito per l'uso self-hosted. Tutto lo stato risiede in un file di configurazione sulla workstation (ad es., `~/.config/rediacc/rediacc.json`).

- Connessioni SSH dirette alle macchine
- Nessun servizio esterno richiesto
- Utente singolo, workstation singola
- La configurazione predefinita viene creata automaticamente al primo uso della CLI. Le configurazioni con nome vengono create con `rdc config init --name <nome>`

### Adattatore cloud (sperimentale)

Attivato automaticamente quando una configurazione contiene i campi `apiUrl` e `token`. Usa l'API di Rediacc per la gestione dello stato e la collaborazione in team.

- Stato memorizzato nell'API cloud
- Team multiutente con accesso basato su ruoli
- Console web per la gestione visuale
- Si configura con `rdc auth login`

> **Nota:** I comandi dell'adattatore cloud sono sperimentali. Abilitarli impostando `REDIACC_EXPERIMENTAL=1`.

Entrambi gli adattatori usano gli stessi comandi CLI. L'adattatore influisce solo su dove viene memorizzato lo stato e su come funziona l'autenticazione.

## L'utente rediacc

Quando si esegue `rdc config machine setup`, renet crea un utente di sistema chiamato `rediacc` sul server remoto:

- **UID**: 7111
- **Shell**: `/sbin/nologin` (non può accedere tramite SSH)
- **Scopo**: Possiede i file del repository ed esegue le funzioni del Rediaccfile

L'utente `rediacc` non è accessibile direttamente tramite SSH. Invece, rdc si connette come l'utente SSH configurato (ad es., `deploy`), e renet esegue le operazioni del repository tramite `sudo -u rediacc /bin/sh -c '...'`. Questo significa:

1. L'utente SSH ha bisogno dei privilegi `sudo`
2. Tutti i dati del repository appartengono a `rediacc`, non all'utente SSH
3. Le funzioni del Rediaccfile (`up()`, `down()`) girano come `rediacc`

Questa separazione assicura che i dati del repository abbiano una proprietà coerente indipendentemente da quale utente SSH li gestisce.

## Isolamento Docker

Ogni repository ha il proprio daemon Docker isolato. Quando un repository viene montato, renet avvia un processo `dockerd` dedicato con un socket univoco:

![Docker Isolation](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

Ad esempio, un repository con ID di rete `2816` usa:
```
/var/run/rediacc/docker-2816.sock
```

Questo significa:
- I container di repository diversi non possono vedersi
- Ogni repository ha la propria cache delle immagini, reti e volumi
- Il daemon Docker dell'host (se presente) è completamente separato

Le funzioni del Rediaccfile hanno automaticamente `DOCKER_HOST` impostato al socket corretto.

Quando un agente AI entra in un repository tramite `rdc term connect -r <repo>`, si applica lo stesso isolamento: la sessione gira come l'utente non privilegiato `rediacc` (UID 7111), in un mount namespace distinto, con `DOCKER_HOST` limitato al socket del daemon di quel singolo repository. Il flusso fork-first combina questo isolamento runtime con una primitiva di clone CoW: l'agente opera su un fork per attività, mai sui repository grand (produzione). Vedere [Sicurezza e guardrail degli agenti AI](/en/docs/ai-agents-safety) per il modello completo della sandbox, la semantica degli override e il confine di responsabilità dello sviluppatore per le credenziali dei servizi esterni.

### Layout del percorso del daemon

I dati e la configurazione di Docker sono memorizzati nel mount del repository, mantenendo ogni daemon completamente isolato dall'host e dagli altri repository.

**Layout per repository:**
```
{datastore}/mounts/{guid}/.rediacc/docker/data/    # Docker data root
{datastore}/mounts/{guid}/.rediacc/docker/config/  # Docker config
```

**Layout standalone** (daemon non collegati a un mount di repository):
```
{datastore}/standalone/{N}/.rediacc/docker/data/
{datastore}/standalone/{N}/.rediacc/docker/config/
```

**Percorso runtime condiviso** (invariato):
```
/run/rediacc/docker-{N}.sock
```

Questo layout unificato elimina le collisioni di mount in sola lettura/lettura-scrittura che si verificavano quando i percorsi del daemon erano suddivisi tra il filesystem dell'host e il volume cifrato. Sia i daemon per repository che quelli standalone seguono la stessa struttura di directory, quindi gli strumenti e la diagnostica funzionano in modo identico in entrambi i casi.

## Cifratura LUKS

I repository sono immagini disco cifrate con LUKS memorizzate nel datastore del server (predefinito: `/mnt/rediacc`). Ogni repository:

1. Ha una passphrase di cifratura generata casualmente (la "credenziale")
2. È memorizzato come file: `{datastore}/repos/{guid}.img`
3. Viene montato tramite `cryptsetup` quando vi si accede

La credenziale è memorizzata nel file di configurazione ma **mai** sul server. Senza la credenziale, i dati del repository non possono essere letti. Quando l'avvio automatico è abilitato, un keyfile LUKS secondario viene memorizzato sul server per consentire il montaggio automatico all'avvio.

## Struttura della configurazione

Ogni configurazione è un file JSON memorizzato in `~/.config/rediacc/`. La configurazione predefinita è `rediacc.json`; le configurazioni con nome usano il nome come nome file (ad es., `production.json`). I campi sono raggruppati per scopo: `resources` contiene i deployment, `credentials` i segreti, `account` i valori predefiniti cloud, `infra` TLS/DNS ed `encryption` lo stato a riposo per campo. Il discriminatore di primo livello `schemaVersion: 2` garantisce la compatibilità futura.

```json
{
  "schemaVersion": 2,
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 47,
  "defaults": {
    "language": "en",
    "machine": "prod-1",
    "nextNetworkId": 2880,
    "universalUser": "rediacc"
  },
  "credentials": {
    "ssh": {
      "privateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
      "publicKey": "ssh-ed25519 AAAA...",
      "knownHosts": "..."
    },
    "cfDnsApiToken": "cf-token-xxxxxxxxxxxx"
  },
  "resources": {
    "machines": {
      "prod-1": {
        "ip": "203.0.113.50",
        "user": "deploy",
        "port": 22,
        "datastore": "/mnt/rediacc",
        "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
      }
    },
    "storages": {
      "backblaze": {
        "provider": "b2",
        "vaultContent": { "...": "..." }
      }
    },
    "repositories": {
      "webapp": {
        "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "credential": "base64-encoded-random-passphrase",
        "networkId": 2816
      }
    }
  },
  "infra": {
    "certEmail": "admin@example.com",
    "cfDnsZoneId": "..."
  },
  "encryption": {
    "mode": "plaintext"
  }
}
```

**Bucket principali:**

| Bucket | Contenuto |
|---|---|
| `schemaVersion` | Discriminatore (attualmente `2`). I loader rifiutano le versioni sconosciute. |
| `id` / `version` | UUID immutabile + contatore monotono; usato per il locking ottimistico sull'archivio di configurazione remoto. |
| `defaults.*` | Valori predefiniti di runtime non sensibili (`machine`, `language`, `pruneGraceDays`, `universalUser`, `nextNetworkId`). |
| `credentials.ssh` | Coppia di chiavi SSH inline + `knownHosts`. Sostituisce il legacy `ssh.privateKeyPath` (nessuna indirezione tramite percorso file; il contenuto viene risolto al caricamento e memorizzato inline). |
| `credentials.cfDnsApiToken` | Token ACME DNS-01 di Cloudflare. |
| `credentials.masterPasswordVerifier` | Presente solo quando `encryption.mode === "master-password"`. |
| `resources.machines.*` | Dettagli di connessione SSH per macchina. |
| `resources.storages.*` | Credenziali di backup off-site compatibili con rclone. |
| `resources.repositories.*` | GUID per repository + credenziale LUKS + chiave SSH per l'accesso degli agenti in sandbox isolata. |
| `infra.acmeCertCache.*` | acme.json di Traefik memorizzato nella cache, gzip+base64, indicizzato per dominio. |
| `encryption.mode` | `"plaintext"` (predefinito) o `"master-password"`. |
| `encryption.encryptedFields` | Quando cifrato, una mappa di blob AES-GCM per puntatore (`/resources/repositories/webapp/credential` → `{ciphertext, nonce, tag}`). Un prompt di sblocco per sessione decifra man mano che i campi vengono letti. |
| `remote` | Presente solo quando la configurazione è sincronizzata con l'archivio di configurazione cifrato; vedere [Archivio di configurazione cifrato](/en/docs/config-storage). |

**Modificare in modo sicuro con la CLI, non con `vim`:**

```bash
# Modifiche a singolo campo indirizzate tramite puntatore (con knowledge-gate per percorsi sensibili)
rdc config field set --pointer /resources/machines/prod-1/port --new 2222
rdc config field set --pointer /credentials/cfDnsApiToken --current "$OLD" --new "$NEW"

# Editor completo con proiezione JSONC redatta (solo per esseri umani)
rdc config edit

# Dump JSONC in sola lettura, sicuro per script e agenti
rdc config edit --dump

# Ispeziona ogni mutazione, rifiuto e reveal nel log di audit
rdc config audit log --since 24h
rdc config audit verify
```

> Questo file contiene dati sensibili (chiavi private SSH, credenziali LUKS, token Cloudflare). È memorizzato con permessi `0600` (lettura/scrittura solo per il proprietario). Non condividerlo né includerlo nel controllo di versione. Quando qualsiasi comando `rdc` lo legge, i campi sensibili sono [redatti per impostazione predefinita](/en/docs/ai-agents-safety): il testo in chiaro appare solo con `--reveal` su un TTY interattivo per esseri umani.

### Envelope v2 e applicazione lato server

Quando la configurazione è sincronizzata con l'[archivio di configurazione cifrato](/en/docs/config-storage), la CLI racchiude ogni campo sensibile in un commitment HMAC per campo e trasporta tali commitment nell'envelope in testo in chiaro. Il server vede solo digest esadecimali, mai i valori, eppure può applicare i knowledge-gate su ogni scrittura:

- **Verifica della precondizione**: su `PUT /configs/<id>`, il client invia i digest che dichiara di conoscere per i percorsi che vuole mutare. Il server li confronta con i commitment dell'envelope memorizzato. Mancata corrispondenza: `409 precondition_failed` con `mismatchedPaths`. Zero-knowledge: il server non vede mai il testo in chiaro.
- **Anti-downgrade**: il nuovo envelope deve includere ogni percorso sensibile che il precedente envelope includeva. Un agente non può rimuovere un percorso dai commitment per aggirare una futura precondizione.
- **Pinning della versione dell'envelope**: il server rifiuta gli envelope privi di `envelopeVersion: 2` con `400 unsupported_envelope_version`. Nessuna finestra di doppia accettazione.
- **Cifratura a riposo per campo** (lato CLI): quando `encryption.mode === "master-password"`, ogni segreto diventa un blob AES-GCM individuale con chiave derivata dalla master password. Le letture non generano un prompt a meno che il comando non tocchi effettivamente un segreto (quindi `rdc machine list` rimane senza prompt).

La chiave di commitment (FCK) viene derivata lato client dalla CEK tramite `HKDF-SHA256(ikm=CEK, salt=fckSalt, info="rediacc-config-fck-v1")` con un salt per configurazione. La rotazione di `fckSalt` invalida tutti i commitment precedenti, forzando un ricalcolo completo: utile quando si ruota la CEK.
