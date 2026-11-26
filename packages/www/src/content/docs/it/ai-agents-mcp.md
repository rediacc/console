---
title: Configurazione del server MCP
description: Collega gli agenti AI all'infrastruttura Rediacc usando il server Model Context Protocol (MCP).
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 33
language: it
sourceHash: "ece2cec7cd2f4bc9"
sourceCommit: "948dc510c78b93b73ea5b1b7b379cdb93141486e"
---

## Panoramica

Due server MCP (Model Context Protocol) attingono i propri strumenti a un unico registro, e il server remoto ne offre un sottoinsieme:

| Server | Trasporto | Esecuzione | Strumenti |
|---|---|---|---|
| Locale | stdio | `rdc mcp serve`, avviato dall'agente | Tutti gli strumenti |
| Remoto | Streamable HTTP | `https://mcp.<region>.rediacc.cloud/g/<grantId>` | Gli strumenti remoti, cioè tutti tranne quelli della tabella dei soli locali |

**Prerequisiti:** `rdc` installato e configurato con almeno una macchina per il server locale. Per il server remoto serve un grant su una configurazione.

## Server locale

`rdc mcp serve` avvia un server MCP su stdio. L'agente lo avvia come sottoprocesso e comunica con esso tramite JSON-RPC.

### Claude Code

Il file `.mcp.json` del progetto contiene la voce:

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

### Cursor

Apri Settings → MCP Servers → Add Server:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

### Opzioni

| Opzione | Predefinito | Descrizione |
|---------|-------------|-------------|
| `--config <name>` | (configurazione predefinita) | Configurazione con nome da usare per tutti i comandi |
| `--timeout <ms>` | `120000` | Timeout predefinito dei comandi in millisecondi |

## Server remoto

In ogni regione gira un Worker MCP su `mcp.<region>.rediacc.cloud`. Ogni agente si collega all'URL di un grant: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. Il grant indica una configurazione, una scadenza e un ambito: un flag di sola lettura, una allowlist di strumenti e pattern (glob) per i nomi di macchine e repository. Le chiamate agli strumenti vengono eseguite sull'executor dell'organizzazione del grant.

### Credenziali

Entrambe le forme identificano il grant; l'id del grant nell'URL serve solo a nominarlo.

| Forma | Uso | Inviata come |
|---|---|---|
| Token di accesso OAuth | Client interattivi come claude.ai | `Authorization: Bearer <token>` |
| Bearer dell'agente `rmcp_<grantId>.<secret>` | Agenti headless | `Authorization: Bearer` oppure `x-api-key` |

Una credenziale nella query string viene rifiutata con 400. Un token OAuth mancante, scaduto o di un altro grant riceve 401 con un'intestazione `WWW-Authenticate: Bearer resource_metadata=...` che punta al documento di risorsa protetta del grant, così il client OAuth rinnova il token o effettua l'accesso. Un grant sconosciuto, un segreto errato e un bearer dell'agente di un altro grant ricevono tutti lo stesso 401 senza altri dettagli.

### OAuth

Il Worker è un server di autorizzazione OAuth 2.1 con PKCE (solo S256). I client si registrano tramite un Client ID Metadata Document oppure con la registrazione dinamica dei client su `/register`.

| Endpoint | Scopo |
|---|---|
| `/.well-known/oauth-authorization-server` | Metadati del server |
| `/.well-known/oauth-protected-resource/g/<grantId>` | Documento di risorsa protetta di un grant |
| `/authorize` | Avvia l'autorizzazione e reindirizza alla pagina account `/account/mcp/authorize` |
| `/oauth/token` | Scambio del codice, rinnovo e revoca |
| `/register` | Registrazione dinamica dei client |

Il client invia `resource=https://mcp.<region>.rediacc.cloud/g/<grantId>`. L'autorizzazione si completa solo per il grant indicato dalla risorsa, e un token funziona solo all'URL del suo grant. Il reindirizzamento da `/authorize` porta un handle firmato monouso e nessun segreto.

### Durata dei token

Un token non sopravvive mai al proprio grant.

| Token | Durata |
|---|---|
| Token di accesso | Il minore tra 1 ora e il tempo residuo del grant |
| Token di rinnovo | Il minore tra 30 giorni e il tempo residuo del grant |

Ogni scambio di codice e ogni rinnovo riconsulta il grant. Un grant scaduto, revocato o con la chiave ruotata risponde `invalid_grant` e revoca la concessione OAuth. I token di rinnovo ruotano, e presentarne uno due volte revoca il grant.

### Una configurazione per grant

Un grant serve solo la configurazione che indica. Un `tools/call` con un argomento che indica un'altra configurazione (`config` o una sua variante di scrittura) viene rifiutato con `REDIACC_GRANT_SCOPE` prima che venga eseguito qualsiasi cosa. Chi ha più configurazioni autorizza un grant per ciascuna. Uno strumento fuori dalla allowlist del grant, o uno strumento di scrittura sotto un grant di sola lettura, non compare in `tools/list` e viene rifiutato se chiamato.

### Regioni

L'id di un grant inizia con la sua regione, per esempio `eu_`. Una richiesta a `/g/<grantId>` sul Worker di un'altra regione riceve 421 con l'URL corretto:

```json
{
  "code": "REDIACC_WRONG_REGION",
  "message": "This grant lives in the us region. Use https://mcp.us.rediacc.cloud/g/us_...",
  "region": "us",
  "mcpUrl": "https://mcp.us.rediacc.cloud/g/us_..."
}
```

Un grant non viene mai accettato come risorsa OAuth, audience del token o destinazione di autorizzazione fuori dalla propria regione.

### Stati del grant e limiti

Un grant scaduto, revocato o che ha perso la chiave per una rotazione delle chiavi dell'archivio di configurazione continua a rispondere a `initialize` e `tools/list`. Ogni `tools/call` restituisce allora `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` oppure `REDIACC_KEY_ROTATED` con una `reauthUrl` che l'utente apre per autorizzare di nuovo.

Ogni grant consente 60 chiamate al minuto e 5 chiamate in corso contemporaneamente. Una chiamata oltre uno dei due limiti restituisce `REDIACC_RATE_LIMITED` con `retryAfterSeconds`.

## Strumenti disponibili

<!-- >>> translated-table: mcp-tools -->

| Strumento | Distruttivo | Descrizione |
|---|---|---|
| `backup_browse` | no | Elenca i file contenuti in un repository. |
| `backup_cancel` | no | Annulla un backup in esecuzione su una macchina remota. |
| `backup_check` | no | Verifica che uno snapshot archiviato si apra con la passphrase, ripristinando un file. |
| `backup_immutability_show` | no | Mostra la finestra di eliminazione ritardata in vigore. |
| `backup_list` | no | Elenca gli artefatti di backup di una macchina. |
| `backup_manifests` | no | Elenca i manifest degli snapshot di backup registrati sul server. |
| `backup_reconcile` | sì | Riporta il registro dei byte archiviati di un repository a ciò che l'archivio contiene davvero (non elimina mai un chunk). |
| `backup_repair` | sì | Ricarica, dall'ancora di questa macchina, i chunk che l'archivio ha perso o conserva in modo errato. |
| `backup_restore` | sì | Trasforma un artefatto di backup in un repository attivo. |
| `backup_retention` | no | Mostra la policy di conservazione degli snapshot applicata dal server. |
| `backup_retention_preview` | no | Mostra quali snapshot eliminerebbe la prossima pulizia e quanto spazio libererebbe. |
| `backup_run` | no | Esegue subito un backup. |
| `backup_snapshot` | no | Carica uno snapshot dell'archivio di chunk: prima l'inventario completo, poi le celle modificate. |
| `backup_status` | no | Mostra lo stato dei backup e del timer su una macchina remota. |
| `backup_strategy_list` | no | Elenca tutte le strategie di backup. |
| `backup_strategy_show` | no | Mostra i dettagli di una strategia di backup. |
| `backup_toc-key_sync` | no | Installa la chiave di elencazione del repository sulla sua macchina, oppure ne sostituisce una diversa. |
| `backup_undelete` | no | Annulla l'eliminazione ritardata di uno snapshot prima che diventi effettiva. |
| `backup_usage` | no | Mostra la quota di archiviazione dei backup, i byte archiviati e l'uso per repository. |
| `backup_verify` | no | Verifica l'ancora di backup di un repository rispetto all'archivio di chunk. |
| `cluster_snapshot_list` | no | Elenca gli snapshot di gruppo del cluster. |
| `cluster_status` | no | Elenca tutti i cluster oppure, passando il nome di un cluster, mostra la sua configurazione completa. |
| `config_access_list` | no | Elenca le chiavi di accesso della configurazione. |
| `config_prune` | no | Rimuove il superfluo dal file di configurazione locale `~/.config/rediacc/<config>.json`. |
| `config_reconcile` | no | Ricostruisce il contenitore di stato locale a partire dallo stato reale delle macchine (renet list all). |
| `config_show` | no | Mostra i dettagli della configurazione corrente. |
| `credits` | no | Mostra il saldo dei crediti residuo di questo account. |
| `datastore_list` | no | Elenca i datastore con nome, dove sono collegati e cosa contengono. |
| `datastore_snapshot_list` | no | Elenca gli snapshot di un datastore. |
| `datastore_status` | no | Mostra un datastore: backend, collegamento, utilizzo, repository e snapshot. |
| `feedback_list` | no | Elenca i report di feedback visibili a questa macchina: id, impronta breve, stato e date. |
| `feedback_report` | no | Crea un report dall'ultimo comando fallito (--last), da un comando registrato (--command <n>) o solo da un messaggio, mostra esattamente cosa verrebbe inviato e lo invia dopo la conferma. |
| `feedback_show` | no | Mostra un report di feedback tramite il suo id (o un prefisso univoco), con stato, numero di occorrenze e date. |
| `incident_status` | no | Elenca gli incidenti dell'organizzazione oppure ne mostra uno con il suo ambito, la finestra, i passaggi per macchina e gli orologi delle scadenze di preallarme, notifica e report finale. |
| `job_cancel` | sì | Annulla un job scollegato in esecuzione. |
| `job_dismiss` | sì | Abbandona in locale i ticket dei job: i passaggi dovuti vengono scartati e il ticket non compare più. |
| `job_gc` | sì | Rimuove i job terminati e i relativi log. |
| `job_list` | no | Elenca i job scollegati di una macchina, dal più recente. |
| `job_logs` | no | Riproduce o segue il log degli eventi di un job scollegato. |
| `job_status` | no | Mostra lo stato di un job scollegato. |
| `job_wait` | no | Attende fino a 50 s che un job termini. |
| `legal` | no | Stampa i link ai documenti legali nella lingua della CLI con i link in inglese vincolanti, la versione corrente dei Termini di servizio con checksum e URL dell'archivio, l'accettazione registrata (dal server degli account dopo l'accesso, da questa configurazione in modalità anonima) e l'entità contraente. |
| `machine_access_show` | no | Mostra le chiavi di accesso associate a una macchina e gli intervalli che ciascuna vi risolve. |
| `machine_add` | no | Registra una macchina esistente raggiungibile via SSH. |
| `machine_containers` | no | Elenca i container Docker di una macchina. |
| `machine_converge` | sì | Riavvia, un repository alla volta, ogni daemon di repository ancora su un vecchio layout del runtime, così che passi a quello attuale. |
| `machine_deprovision` | sì | Distrugge una macchina di cui è stato fatto il provisioning nel cloud e la rimuove dalla configurazione. |
| `machine_gpu_list` | no | Elenca le GPU rilevate su una macchina, i nomi dei dispositivi CDI definiti dalle sue specifiche e i repository a cui ogni dispositivo è assegnato. |
| `machine_health` | no | Controlla lo stato di salute di una macchina per le pipeline CI/CD. |
| `machine_infra_show` | no | Mostra la configurazione dell'infrastruttura di una macchina (dominio base, IP pubblici, porte), le impostazioni TLS condivise (e-mail del certificato, token DNS CF) e l'ID della zona Cloudflare. |
| `machine_list` | no | Elenca le macchine. |
| `machine_provider_add` | no | Aggiunge un provider cloud. |
| `machine_provider_list` | no | Elenca i provider cloud configurati per il provisioning delle macchine. |
| `machine_provider_remove` | sì | Rimuove la configurazione di un provider cloud. |
| `machine_provision` | sì | Esegue il provisioning di una nuova macchina su un provider cloud con OpenTofu. |
| `machine_prune` | sì | Rimuove da una macchina le risorse di datastore orfane e gli snapshot obsoleti. |
| `machine_remove` | sì | Rimuove una macchina dalla configurazione. |
| `machine_repos` | no | Elenca i repository distribuiti su una macchina. |
| `machine_restart-services` | sì | Porta i daemon renet che eseguono ancora un binario sostituito sul binario installato, un'unità alla volta, confermando che ciascuna sia attiva prima di passare alla successiva. |
| `machine_scan-keys` | no | Registra nella configurazione locale le chiavi host SSH della macchina. |
| `machine_services` | no | Elenca i servizi systemd gestiti da Rediacc su una macchina (nome, stato, sotto-stato, numero di riavvii, memoria, repository risolto nel nome con l'originale in repository_guid). |
| `machine_setup` | no | Completa l'onboarding di una macchina: installa renet e la prepara a ospitare repository. |
| `machine_status` | no | Ottiene i dettagli di connessione (IP, utente, porta, datastore), le informazioni di sistema, i container (repository risolto nel nome, originale in repository_guid, dominio, autoRoute), i servizi (repository risolto nel nome), i repository (nome risolto dal GUID, originale in guid) e l'utilizzo delle risorse di una macchina. |
| `repo_admin_fsck` | no | Convalida i riferimenti della configurazione (branch/HEAD) rispetto agli oggetti presenti su una macchina e segnala riferimenti pendenti e commit orfani. |
| `repo_cat` | no | Legge su stdout una finestra limitata di un file di un repository (la diagnostica va su stderr). |
| `repo_checkout` | sì | Clona con reflink un commit immutabile (o la punta di un branch) in un nuovo fork di lavoro scrivibile e punta HEAD su di esso. |
| `repo_commit` | sì | Congela un fork di lavoro montato in un nuovo commit immutabile (come in git). |
| `repo_create` | sì | Crea un nuovo repository. |
| `repo_delete` | sì | Elimina un repository e i suoi dati. |
| `repo_diff` | no | Diff a livello di file in stile git tra due repository fork copy-on-write. |
| `repo_down` | sì | Arresta i container Docker di un repository (esegue Rediaccfile down). |
| `repo_exec` | sì | Esegue un comando all'interno di un container di un repository. |
| `repo_flows` | no | Elenca i flussi di rete registrati per un repository in una finestra temporale: ora, processo, destinazione, byte in uscita e in entrata, più ASN e paese della destinazione quando noti. |
| `repo_fork` | sì | Crea un fork CoW quasi istantaneo di un repository con un NUOVO GUID e networkId (copia completamente indipendente). |
| `repo_gc` | sì | Garbage collection per raggiungibilità: elimina da una macchina gli oggetti commit immutabili che nessun branch o HEAD raggiunge. |
| `repo_health` | no | Esegue i controlli health() del Rediaccfile di un repository e termina con 0 (ok), 1 (avviso) o 2 (errore). |
| `repo_list` | no | Elenca i repository di una macchina. |
| `repo_log` | no | Stampa la cronologia dei commit raggiungibile dal commit corrente di un fork di lavoro (o da un riferimento di commit), percorrendo la catena dei genitori registrata da 'rdc repo commit'. |
| `repo_logs` | no | Mostra i log applicativi dei container di un repository. |
| `repo_merge` | sì | Unisce, in modo sicuro per il ciclo di vita, un commit o fork di origine in un fork di lavoro di destinazione. |
| `repo_migrate` | sì | Sposta un repository su un'altra macchina con un'interruzione minima: copia in due fasi (sincronizzazione massiva a caldo, poi un breve arresto, sincronizzazione del delta e avvio sulla destinazione) con passaggio del DNS. |
| `repo_opens` | no | Elenca le aperture di file registrate per un repository in una finestra temporale: ora, processo e percorso, con i percorsi sensibili contrassegnati. |
| `repo_pull` | sì | Scarica un repository da un'altra macchina. |
| `repo_push` | sì | Invia il backup di un repository all'archiviazione o direttamente a un'altra macchina. |
| `repo_replicate` | no | Esegue il provisioning di repliche in lettura di un repository. |
| `repo_replicate_remove` | sì | Rimuove un set di repliche: elimina i suoi oggetti k8s generati (limitati per etichetta), scarta i suoi datastore fork, elimina il suo snapshot e dimentica lo stato. |
| `repo_replicate_status` | no | Mostra i set di repliche gestiti: repliche, nodi ospitanti, datastore fork, snapshot e orari di aggiornamento. |
| `repo_secret_get` | no | Mostra il digest SHA-256 di un segreto. |
| `repo_secret_list` | no | Elenca chiavi e modalità dei segreti (mai i valori, mai i digest). |
| `repo_status` | no | Ottiene lo stato di un repository (stato del mount, daemon Docker in esecuzione, numero di container, uso del disco). |
| `repo_trim` | no | Recupera spazio dal pool del datastore dai repository montati (online, senza interruzioni). |
| `repo_up` | sì | Distribuisce o aggiorna un repository (esegue Rediaccfile up tramite renet compose, avvia i container). |

<!-- <<< translated-table -->

<!-- >>> translated-table: mcp-tools-local -->

| Strumento | Distruttivo | Descrizione |
|---|---|---|
| `cluster_kubeconfig` | no | Recupera via SSH il kubeconfig dal nodo di controllo del cluster e lo mette in cache locale (0600) per kubectl. |
| `config_audit_log` | no | Legge il log di audit delle modifiche fatte tramite questa configurazione. |
| `config_audit_verify` | no | Verifica che la catena di hash del log di audit non sia stata manomessa. |
| `config_current` | no | Mostra la configurazione attiva: nome, file, server e canale risolti, stato del token. |
| `config_list` | no | Elenca tutti i file di configurazione. |
| `forensics_verify` | no | Ricalcola la catena di hash dei file giornalieri di audit e le catene dei batch forensi firmati di una directory di prove (una directory di esportazione di rdc incident) ed elenca ogni lacuna e ogni modifica. |
| `incident_export` | no | Scrive la finestra dell'incidente in una directory: il record dell'incidente con i suoi orologi, la timeline unificata, gli aggregati dei byte in uscita, il manifest grezzo della catena e i file grezzi che elenca, sotto le chiavi del manifest. |
| `machine_infra_cert_status` | no | Mostra l'inventario dei certificati in cache. |
| `server_status` | no | Mostra lo stato, il livello, il certificato e l'immagine di un server installato. |
| `version` | no | Stampa la versione della CLI, la piattaforma, il canale di aggiornamento e la licenza attiva: il piano dopo l'accesso, "anonymous (FREE per repository)" senza accesso e "unknown (server unreachable)" quando il server degli account non è raggiungibile. |

<!-- <<< translated-table -->

## Esempi di flussi di lavoro

**Controllare lo stato di una macchina:**
> "Qual è lo stato della mia macchina di produzione?"

L'agente chiama `machine_status` e ottiene i dettagli di connessione, le informazioni di sistema, i container, i servizi, i repository e l'uso delle risorse.

**Distribuire un'applicazione:**
> "Distribuisci gitlab sulla mia macchina di staging"

L'agente chiama `repo_up` con `name: "gitlab"` e `machine: "staging"`, che distribuisce il repository e restituisce successo o errore.

**Seguire un job lungo:**
> "Ripristina il backup di ieri sera di nextcloud"

L'agente chiama `backup_restore`. Un comando che supera la propria finestra restituisce un handle del job, e l'agente chiama `job_wait` (fino a 50 s per chiamata) e `job_logs` finché il job non termina.

**Fare il debug di un servizio che non funziona:**
> "Il mio nextcloud è lento, scopri cosa non va"

L'agente chiama `machine_health`, poi `machine_containers` e `repo_logs`, e suggerisce una soluzione.

## Sicurezza

Il server MCP locale applica due livelli di protezione. Per i limiti del server remoto vedi [Server remoto](#remote-server).

### Modalità fork-only (predefinita)

Per impostazione predefinita, il server opera in **modalità fork-only**: gli strumenti di scrittura (`repo_up`, `repo_down`, `repo_delete`, `repo_exec`, `repo_push`, `repo_pull`) possono agire solo su repository fork. Gli agenti non possono toccare i repository grand (originali). Per design.

> **I segreti per repository sono accessibili solo tramite CLI per design.** `repo_secret_set` e `repo_secret_unset` sono intenzionalmente **non** esposti come strumenti MCP. Le scritture richiedono una precondizione `--current <previous-value>` (oppure `--rotate-secret` per riconoscere una rotazione non verificata), e quella procedura richiede la supervisione umana. Gli agenti che devono suggerire la rotazione di un segreto dovranno chiamare `repo_secret_get` per confermare il digest, quindi trasmettere il comando CLI destinato all'operatore all'utente tramite il campo `next.options[].run` strutturato nell'envelope di errore JSON. Consulta [Sicurezza agenti AI](/en/docs/ai-agents-safety#structured-next-action-hints) per il pattern completo e [Repository - Segreti](/en/docs/repositories#secrets) per le istruzioni rivolte all'utente.

Per consentire a un agente di modificare i repository grand, esporta `REDIACC_ALLOW_GRAND_REPO` nel tuo terminale **prima di avviare l'agente che ospita il server MCP**:

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # un repo
# oppure 'repo1,repo2,repo3' (gli spazi bianchi attorno alle voci vengono ignorati), oppure '*' per tutti i repo
claude   # oppure cursor, gemini, ecc.
```

L'override è verificato rispetto all'ascendenza del processo: conta solo se era già presente nell'ambiente del processo agent stesso, il che significa che l'hai esportato prima che l'agent (e il server MCP che ha generato) si avviasse. Un agent non può concedersi accesso impostando la variabile a metà sessione. Non c'è intenzionalmente nessun flag del server per questo: un flag negli argomenti del server MCP non porta alcuna prova di chi l'ha messo lì, mentre il controllo dell'ascendenza sì. L'accesso a livello di macchina (come `term connect <machine>` senza un repo) richiede ancora `*`; un elenco di nomi di repo non lo sblocca.

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

Il server MCP locale è stateless. Ogni chiamata a uno strumento avvia `rdc` come processo figlio isolato con i flag `--output json --yes --quiet`. Questo significa:

- Nessuna perdita di stato tra le chiamate agli strumenti
- Utilizza la configurazione `rdc` e le chiavi SSH esistenti
- Gli errori in un comando non influenzano gli altri
