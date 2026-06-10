---
title: Configurazione del server MCP
description: Collega gli agenti AI all'infrastruttura Rediacc usando il server Model Context Protocol (MCP).
category: Guides
order: 33
language: it
sourceHash: "4483eb3da34a6c03"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

## Panoramica

Dunque, `rdc mcp serve` avvia un server MCP (Model Context Protocol) locale che gli agenti AI possono usare per gestire la tua infrastruttura. Il server utilizza il trasporto stdio: l'agente lo avvia come sottoprocesso e comunica tramite JSON-RPC.

**Prerequisiti:** `rdc` installato e configurato con almeno una macchina.

## Claude Code

Aggiungi al file `.mcp.json` del tuo progetto:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

Oppure con una configurazione con nome:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

Apri Impostazioni → MCP Servers → Add Server:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

## Strumenti disponibili

### Strumenti di lettura (sicuri, senza effetti collaterali)

| Strumento | Descrizione |
|-----------|-------------|
| `machine_query` | Ottieni informazioni di sistema, container, servizi e utilizzo delle risorse per una macchina |
| `machine_containers` | Elenca i container Docker con stato, salute, utilizzo delle risorse, etichette e dominio auto-route |
| `machine_services` | Elenca i servizi systemd gestiti da Rediacc (nome, stato, sub-stato, conteggio riavvii, memoria, repository proprietario) |
| `machine_repos` | Elenca i repository distribuiti (nome, GUID, dimensione, stato mount, stato Docker, conteggio container, utilizzo disco, data di modifica, presenza Rediaccfile) |
| `machine_health` | Esegui un controllo di salute su una macchina (sistema, container, servizi, storage) |
| `machine_list` | Elenca tutte le macchine configurate |
| `config_repositories` | Elenca i repository configurati con le mappature nome-GUID |
| `config_show_infra` | Mostra la configurazione infrastrutturale per una macchina (dominio base, IP pubblici, TLS, zona Cloudflare) |
| `config_providers` | Elenca i provider cloud configurati per il provisioning delle macchine |
| `agent_capabilities` | Elenca tutti i comandi CLI rdc disponibili con i loro argomenti e opzioni |
| `repo_secret_list` | Elenca i nomi dei segreti e le modalità di consegna per un repository (mai i valori, mai i digest). Sicuro in lettura. |
| `repo_secret_get` | Ottieni il digest SHA-256 e la modalità di consegna di un segreto. Il valore in chiaro non viene mai restituito per design. Usalo per verificare l'esistenza o la rotazione di un segreto. |

### Strumenti di scrittura (distruttivi)

| Strumento | Descrizione |
|-----------|-------------|
| `repo_create` | Crea un nuovo repository cifrato su una macchina |
| `repo_up` | Distribuisci/aggiorna un repository (esegue Rediaccfile up, avvia i container). Usa `mount` per la prima distribuzione o dopo un pull |
| `repo_down` | Arresta i container del repository. NON smonta per impostazione predefinita. Usa `unmount` per chiudere anche il container LUKS |
| `repo_delete` | Elimina un repository (distrugge container, volumi e immagine cifrata). Le credenziali vengono archiviate per il recupero |
| `repo_fork` | Crea un fork CoW con nuovo GUID e networkId (copia completamente indipendente, forking online supportato) |
| `backup_push` | Invia il backup del repository allo storage o a un'altra macchina (stesso GUID -- backup/migrazione, non fork) |
| `backup_pull` | Recupera il backup del repository dallo storage o da una macchina. Dopo il pull, distribuisci con `repo_up` (mount=true) |
| `machine_provision` | Esegui il provisioning di una nuova macchina su un provider cloud usando OpenTofu |
| `machine_deprovision` | Distruggi una macchina di cui è stato eseguito il provisioning nel cloud e rimuovila dalla configurazione |
| `config_add_provider` | Aggiungi una configurazione di provider cloud per il provisioning delle macchine |
| `config_remove_provider` | Rimuovi una configurazione di provider cloud |
| `term_exec` | Esegui un comando su una macchina remota tramite SSH |

## Esempi di flussi di lavoro

**Controlla lo stato della macchina:**
> "Qual è lo stato della mia macchina di produzione?"

L'agente chiama `machine_query` → restituisce informazioni di sistema, container in esecuzione, servizi e utilizzo delle risorse.

**Distribuisci un'applicazione:**
> "Distribuisci gitlab sulla mia macchina di staging"

L'agente chiama `repo_up` con `name: "gitlab"` e `machine: "staging"` → distribuisce il repository, restituisce successo/fallimento.

**Diagnostica un servizio in errore:**
> "Il mio nextcloud è lento, scopri cosa c'è che non va"

L'agente chiama `machine_health` → `machine_containers` → `term_exec` per leggere i log → identifica il problema e suggerisce una soluzione.

## Opzioni di configurazione

| Opzione | Predefinito | Descrizione |
|---------|-------------|-------------|
| `--config <name>` | (config predefinita) | Configurazione con nome da usare per tutti i comandi |
| `--timeout <ms>` | `120000` | Timeout predefinito dei comandi in millisecondi |

## Sicurezza

Il server MCP applica due livelli di protezione:

### Modalità fork-only (predefinita)

Per impostazione predefinita, il server opera in **modalità fork-only**: gli strumenti di scrittura (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) possono operare solo sui repository fork. Gli agenti non possono intervenire sui repository grand (originali). Per design.

> **I segreti per repository sono accessibili solo tramite CLI per design.** `repo_secret_set` e `repo_secret_unset` sono intenzionalmente **non** esposti come strumenti MCP. Le scritture richiedono una precondizione `--current <previous-value>` (oppure `--rotate-secret` per riconoscere una rotazione non verificata), e quella procedura richiede la supervisione umana. Gli agenti che devono suggerire la rotazione di un segreto dovranno chiamare `repo_secret_get` per confermare il digest, quindi trasmettere il comando CLI destinato all'operatore all'utente tramite il campo `next.options[].run` strutturato nell'envelope di errore JSON. Consulta [Sicurezza agenti AI](/en/docs/ai-agents-safety#structured-next-action-hints) per il pattern completo e [Repository - Segreti](/en/docs/repositories#secrets) per le istruzioni rivolte all'utente.

Per consentire a un agente di modificare i repository grand, esporta `REDIACC_ALLOW_GRAND_REPO` nel tuo terminale **prima di avviare l'agente che ospita il server MCP**:

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # un repo
# oppure 'repo1,repo2,repo3' (gli spazi bianchi attorno alle voci vengono ignorati), oppure '*' per tutti i repo
claude   # oppure cursor, gemini, ecc.
```

L'override è verificato rispetto all'ascendenza del processo: conta solo se era già presente nell'ambiente del processo agent stesso, il che significa che l'hai esportato prima che l'agent (e il server MCP che ha generato) si avviasse. Un agent non può concedersi accesso impostando la variabile a metà sessione. Non c'è intenzionalmente nessun flag del server per questo: un flag negli argomenti del server MCP non porta alcuna prova di chi l'ha messo lì, mentre il controllo dell'ascendenza sì. L'accesso a livello di macchina (come `term connect -m <machine>` senza un repo) richiede ancora `*`; un elenco di nomi di repo non lo sblocca.

### Chiavi SSH per repository e sandbox lato server

Ogni repository ha la propria coppia di chiavi SSH. La chiave pubblica viene distribuita in `authorized_keys` con un prefisso `command=` che forza tutte le sessioni SSH attraverso `renet sandbox-gateway <repo-name>`, un ForceCommand lato server che non può essere aggirato da nessun client, incluso VS Code.

**Come funziona:**
1. `rdc repo create` o `rdc repo fork` genera una coppia di chiavi ed25519 unica per repo
2. La chiave pubblica viene distribuita in remoto con `command="renet sandbox-gateway <name>"`
3. Ogni connessione SSH che utilizza quella chiave passa attraverso il gateway, che applica:
   - **Landlock LSM**, restrizioni filesystem a livello kernel al percorso di mount del repo
   - **Overlay home OverlayFS**, scritture in `$HOME` acquisite per repo, letture trasparenti verso la home reale
   - **TMPDIR per repo** in `<datastore>/.interim/sandbox/<name>/tmp/`
   - **Accesso Docker** tramite il socket Docker isolato del repo
   - **Riduzione dei privilegi** all'utente universale (`rediacc`)
4. Il `.envrc` del repo viene caricato automaticamente per la configurazione di Docker e dell'ambiente

**RW consentiti**: percorso di mount del repo, workspace sandbox per repo, home directory (tramite overlay), socket Docker
**RO consentiti**: percorsi di sistema (`/usr`, `/bin`, `/etc`, `/proc`, `/sys`)
**Bloccati**: percorsi di mount di altri repo, file di sistema al di fuori della lista consentita

**Integrazione VS Code**: ogni repo ottiene la propria installazione del server VS Code in `<datastore>/.interim/sandbox/<name>/.vscode-server/`. Più repo possono essere aperti contemporaneamente con ambienti sandbox indipendenti, senza condivisione del server tra repo.

Questo impedisce il movimento laterale: anche se un agente ottiene l'accesso shell a un fork, non può leggere o modificare altri repository sulla stessa macchina. L'SSH a livello di macchina (senza un repository) utilizza la chiave del team e non è in sandbox.

## Architettura

Il server MCP è stateless. Ogni chiamata a uno strumento avvia `rdc` come processo figlio isolato con i flag `--output json --yes --quiet`. Questo significa:

- Nessuna perdita di stato tra le chiamate agli strumenti
- Utilizza la configurazione `rdc` e le chiavi SSH esistenti
- Funziona con entrambi gli adapter: local e cloud
- Gli errori in un comando non influenzano gli altri
