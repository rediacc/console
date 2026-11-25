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
sourceHash: "5ffb60357e13aeab"
sourceCommit: "a2b1f5471f48c44fb704157f615369df9c354832"
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
| `config_prune` | no | Rimuove il superfluo dal file di configurazione locale ~/.config/rediacc/<config>.json. |
| `config_reconcile` | no | Ricostruisce il contenitore di stato locale a partire dallo stato reale delle macchine (renet list all). |
| `config_show` | no | Mostra i dettagli della configurazione corrente. |
| `credits` | no | Mostra il saldo dei crediti residuo di questo account. |
| `datastore_list` | no | Elenca i datastore con nome, dove sono collegati e cosa contengono. |
| `datastore_snapshot_list` | no | Elenca gli snapshot di un datastore. |
| `datastore_status` | no | Mostra un datastore: backend, collegamento, utilizzo, repository e snapshot. |
| `feedback_list` | no | Elenca i report di feedback visibili a questa macchina: id, impronta breve, stato e date. |
| `feedback_report` | no | Crea un report dall'ultimo comando fallito (--last), da un comando registrato (--command <n>) o solo da un messaggio, mostra esattamente cosa verrebbe inviato e lo invia dopo la conferma. |
| `feedback_show` | no | Mostra un report di feedback tramite il suo id (o un prefisso univoco), con stato, numero di occorrenze e date. |
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
| `repo_fork` | sì | Crea un fork CoW quasi istantaneo di un repository con un NUOVO GUID e networkId (copia completamente indipendente). |
| `repo_gc` | sì | Garbage collection per raggiungibilità: elimina da una macchina gli oggetti commit immutabili che nessun branch o HEAD raggiunge. |
| `repo_health` | no | Esegue i controlli health() del Rediaccfile di un repository e termina con 0 (ok), 1 (avviso) o 2 (errore). |
| `repo_list` | no | Elenca i repository di una macchina. |
| `repo_log` | no | Stampa la cronologia dei commit raggiungibile dal commit corrente di un fork di lavoro (o da un riferimento di commit), percorrendo la catena dei genitori registrata da 'rdc repo commit'. |
| `repo_logs` | no | Mostra i log applicativi dei container di un repository. |
| `repo_merge` | sì | Unisce, in modo sicuro per il ciclo di vita, un commit o fork di origine in un fork di lavoro di destinazione. |
| `repo_migrate` | sì | Sposta un repository su un'altra macchina con un'interruzione minima: copia in due fasi (sincronizzazione massiva a caldo, poi un breve arresto, sincronizzazione del delta e avvio sulla destinazione) con passaggio del DNS. |
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
| `machine_infra_cert_status` | no | Mostra l'inventario dei certificati in cache. |
| `server_status` | no | Mostra lo stato, il livello, il certificato e l'immagine di un server installato. |
| `version` | no | Stampa la versione della CLI, la piattaforma, il canale di aggiornamento e la licenza attiva: il piano dopo l'accesso, "anonymous (FREE per repository)" senza accesso e "unknown (server unreachable)" quando il server degli account non è raggiungibile. |

<!-- <<< translated-table -->

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

Il server MCP è stateless. Ogni chiamata a uno strumento avvia `rdc` come processo figlio isolato con i flag `--output json --yes --quiet`. Questo significa:

- Nessuna perdita di stato tra le chiamate agli strumenti
- Utilizza la configurazione `rdc` e le chiavi SSH esistenti
- Gli errori in un comando non influenzano gli altri
