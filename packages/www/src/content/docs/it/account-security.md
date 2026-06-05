---
title: Sicurezza dell'account e API
description: Autenticazione, token API, gestione delle sessioni e modello di permessi. È fondamentale capire come funziona la sicurezza dell'account per proteggere i tuoi dati.
category: Guides
order: 13
language: it
sourceHash: "dcd061b971573573"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

### Autenticazione

Rediacc supporta più metodi di autenticazione:

![Auth Flow](/img/account-auth-flow.svg)

- **Password**: Accesso tradizionale con email e password
- **Magic Link**: Accesso senza password tramite link email (scadenza di 15 minuti)
- **Autenticazione a due fattori (2FA)**: Basata su TOTP con codici di backup

Quando la 2FA è abilitata, l'accesso richiede sia la password (o il magic link) sia un codice TOTP a 6 cifre.

### Token API

I token API autenticano le operazioni machine-to-machine (attivazione licenza CLI, controlli di stato).

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**Scope:**
- `license:read` -- Interrogare lo stato dell'abbonamento e delle licenze
- `license:activate` -- Attivare le macchine e rilasciare licenze repository
- `subscription:read` -- Leggere i dettagli dell'abbonamento

**Funzionalità di sicurezza:**
- Binding IP: la prima richiesta blocca il token su quell'indirizzo IP
- Scope per team: i token possono essere limitati a un team specifico
- Revoca automatica: i token vengono revocati quando il creatore viene rimosso dall'organizzazione

Creazione di un token:
```bash
# Tramite il portale: API Tokens > Create
# Il valore del token viene mostrato una sola volta -- salvalo in modo sicuro
```

### Flusso Device Code

La CLI può autenticarsi su macchine headless tramite il flusso device code:

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# Visualizza: Enter code XXXX-XXXX-XX at https://www.rediacc.com/account/authorize
# Dopo l'approvazione, la CLI riceve le credenziali automaticamente
```

### Archiviazione della configurazione

Per la configurazione cifrata e sincronizzata con il server, consulta [Config Storage](/en/docs/config-storage) per la guida completa. L'archiviazione della configurazione utilizza:
- Cifratura zero-knowledge (il server non vede mai il testo in chiaro)
- Derivazione della chiave basata su passkey (WebAuthn + PRF)
- Token rotanti con rotazione per ogni richiesta

### Sicurezza della sessione

| Tipo di token | Durata | Archiviazione | Aggiornamento |
|---------------|--------|---------------|---------------|
| Access Token (JWT) | 15 minuti | Cookie HttpOnly | Automatico tramite refresh token |
| Refresh Token | 7 giorni | Cookie HttpOnly | Ruotato a ogni utilizzo |
| Sessione elevata | 10 minuti | Lato server | Attivata dalla ri-autenticazione |

Le sessioni elevate sono richieste per le operazioni sensibili: modifiche della password, modifiche dell'email, configurazione della 2FA, trasferimenti di proprietà e azioni amministrative distruttive.

### Modello di permessi

Rediacc utilizza tre livelli di permessi indipendenti:

![Permission Flow](/img/account-permission-flow.svg)

**Livello 1: Ruolo di sistema** -- Determina l'accesso agli endpoint di amministrazione di sistema.

**Livello 2: Ruolo organizzazione** -- Controlla ciò che un utente può fare all'interno della propria organizzazione (owner, admin, member).

**Livello 3: Ruolo team** -- Limita l'accesso alle risorse specifiche del team (team_admin, member). I proprietari e gli amministratori dell'organizzazione bypassano i controlli del ruolo team.

Ogni richiesta API passa attraverso tutti i livelli applicabili in sequenza. Una richiesta a un endpoint con scope team deve soddisfare l'autenticazione della sessione, l'appartenenza all'org e l'accesso al team.

### Canali di aggiornamento

La CLI supporta due canali di rilascio:
- **stable** (predefinito): Promosso da edge dopo un periodo di maturazione di 7 giorni; sceglilo per un ciclo di aggiornamento conservativo
- **edge**: Distribuzione continua in produzione, aggiornato a ogni merge nel main

```bash
rdc update --channel edge      # Passa a edge
rdc update --channel stable    # Torna a stable
rdc update --status            # Mostra il canale corrente
```

### Postura di sicurezza della CLI per gli agenti AI

Gli agenti di programmazione che invocano `rdc` sono una superficie di minaccia reale, quindi li trattiamo come un principal separato. Ogni invocazione di `rdc` viene classificata all'avvio come **human** o **agent** in base ai segnali dell'ambiente (CLAUDECODE, GEMINI_CLI, COPILOT_CLI, CURSOR_TRACE_ID, REDIACC_AGENT) più' un'analisi della catena di antenati Linux `/proc`. Il rilevamento è best-effort. Un wrapper determinato può' falsificare le variabili d'ambiente, ecco perché' la catena di antenati è importante. Gli agenti ricevono un insieme ridotto di permessi: le mutazioni sensibili alla configurazione richiedono il knowledge-gate (`--current <old>`), l'editor interattivo viene rifiutato senza un override `REDIACC_ALLOW_CONFIG_EDIT` verificato tramite antenati, e `--reveal` su qualsiasi comando di visualizzazione è bloccato. Ogni decisione (consenti, rifiuta, o concedi `--reveal`) scrive una riga JSONL con hash in catena in `~/.config/rediacc/audit.log.jsonl`. Esegui `rdc config audit verify` per controllare l'integrita' della catena.

Consulta [Sicurezza e guardrail per agenti AI](/en/docs/ai-agents-safety) per la matrice completa di ciò che gli agenti possono e non possono fare, esempi pratici del knowledge-gate e la meccanica degli scope-override.
