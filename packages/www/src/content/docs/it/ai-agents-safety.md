---
title: Sicurezza degli AI Agent e Guardrail
description: >-
  Come Rediacc impedisce agli assistenti di programmazione basati su IA di
  divulgare segreti, sovrascrivere credenziali o aumentare i privilegi. Una sola
  decisione per ogni superficie, adesione esplicita E limite della policy,
  knowledge-gate, redazione e un log di audit con hash a catena per organizzazione e per giorno sul server, e in un file locale per la CLI.
category: Concepts
tags:
  - ai-agents
  - security
subcategory: ai-agents
order: 35
language: it
sourceHash: "43350a2e682cebcc"
sourceCommit: "cc655e698ed2c42faef5311e268425c04997f243"
---

Stai indirizzando un assistente di coding AI alla tua infrastruttura. Quando Claude Code, Cursor, Gemini CLI, Copilot CLI o strumenti simili guidano `rdc`, la CLI lo rileva e applica un set di regole diverso da quello di un umano alla tastiera. Questa pagina spiega cosa l'agent può e non può fare, e come i guardrail resistono anche quando tenta di convincerti a lasciargli il controllo.

## Riferimento rapido: cosa gli agent possono e non possono fare

| Operazione | Comportamento predefinito dell'agent | Come sbloccarla per un caso d'uso specifico |
|---|---|---|
| `rdc config show` (redatto) | ✅ consentito |  |
| `rdc config field get --pointer <pointer>` (stub redatto o digest) | ✅ consentito |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ consentito |  |
| `rdc config field set --pointer <pointer>` (campo pubblico) | ✅ consentito |  |
| `rdc config field set --pointer <pointer>` (campo sensibile, **con `--current` corretto**) | ✅ consentito |  |
| `rdc config edit --dump --redacted` (JSONC redatto) | ✅ consentito |  |
| `rdc config audit {log, tail, verify}` | ✅ consentito |  |
| `rdc config field set --pointer <pointer>` (campo sensibile, senza `--current`) | 🔴 rifiutato | Fornisci `--current "<old value>"` |
| `rdc repo secret set <repo> --rotate-secret` (rotazione senza `--current`) | 🔴 rifiutato | Fornire `--current`, oppure un umano esegue la rotazione da un terminale |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 rifiutato | Usa `--digest` invece |
| `rdc config show --reveal` | 🔴 rifiutato | Usa il semplice `rdc config show` |
| `rdc config edit` (editor interattivo) | 🔴 rifiutato, nessun override | Ispezionare con `--dump --redacted`, modificare un solo campo con `config field set --current` |
| `rdc config edit --apply <file>` | 🔴 rifiutato, nessun override | Idem; un umano da un terminale applica le modifiche all'intero documento |
| `rdc config edit --reveal` | 🔴 rifiutato, nessun override | Idem |
| `rdc config field rotate --pointer <pointer>` | 🔴 rifiutato | Un umano lo esegue da un terminale interattivo |
| Modificare un repository grand (produzione) | 🔴 rifiutato | Adesione esplicita di un umano per quel repository, entro una policy che consente modifiche ai repository grand ([sotto](#one-decision-opt-in-and-policy-ceiling)) |
| Operazioni sul ciclo di vita di cluster o datastore | 🔴 rifiutato | Adesione esplicita di un umano per quel cluster, entro una policy che consente le operazioni sui cluster |
| `rdc term connect <machine>` (SSH diretto alla macchina) | 🔴 rifiutato | Fork prima un repo e connettiti al fork |

Ogni rifiuto verso un agent viene scritto nel log di audit con `outcome: refused` e un motivo. La modifica dell'intero documento di configurazione non ha alcun percorso per un agent: la configurazione contiene la credenziale LUKS di ogni repository, e un agent in grado di riscriverla potrebbe anche eliminare una credenziale senza la quale il volume cifrato non si può aprire.

## Come gli agent sono rilevati

La CLI tratta un processo come un agent quando uno di questi è vero:

- Uno di `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` è impostato su `"1"`, oppure `CURSOR_TRACE_ID` è impostato.
- Su Linux: qualsiasi processo parent nella catena di ascendenza ha una di queste variabili nel suo ambiente (tramite `/proc/<pid>/environ`). Anche se l'agent cancella le sue variabili con `env -i` o uno script wrapper, la catena parent comunica sempre alla CLI chi l'ha avviato.

Il rilevamento viene eseguito una volta per processo e salvato in cache. Non può essere disattivato. Una concessione MCP remota contrassegna le sue chiamate come chiamate di agent sull'esecutore, senza bisogno di rilevamento.

## Una sola decisione: adesione esplicita E limite della policy

Ogni superficie che esegue un comando `rdc` (la CLI, il server MCP locale, il server MCP remoto, `rdc --proxy` e la console web) interroga la stessa funzione di decisione, quindi tutte rifiutano e consentono le stesse cose. La funzione applica due condizioni, e un agent agisce solo dove valgono entrambe:

1. **Il limite della policy.** La policy dell'organizzazione, ristretta da quella del team, decide quali comandi, macchine e repository può usare chi chiama, e se le modifiche ai repository grand (`allowGrandRepos`) e le operazioni sui cluster (`allowClusterOps`) sono consentite. Una configurazione senza record di policy ripiega su un valore predefinito per ruolo: i proprietari e gli amministratori possono agire, i membri no. La policy è un record sigillato separato che scrivono solo proprietari e amministratori ([Modello di sicurezza](/it/docs/security-model#policy)); nessun agent e nessun comando della CLI può modificarla.
2. **L'adesione esplicita dell'umano.** All'interno del limite, un agent ha comunque bisogno che un umano indichi il repository grand o il cluster che può modificare:
   - **Agent locali** (CLI e MCP locale): l'umano esporta `REDIACC_ALLOW_GRAND_REPO` (nomi di repository, oppure `*`) o `REDIACC_ALLOW_CLUSTER_OPS` (nomi di cluster, oppure `*`) nel terminale prima di avviare l'agent. La CLI controlla la catena dei processi antenati, quindi una variabile impostata dall'agent a sessione in corso non conta ([come viene verificato su ogni sistema operativo](#how-a-local-opt-in-is-verified-on-each-os)).
   - **Agent remoti** (MCP remoto): le adesioni fanno parte della concessione che l'umano crea nell'interfaccia dell'account ([Server remoto](/it/docs/ai-agents-mcp#remote-server)).

Un'adesione non amplia mai il limite: un repository che la policy chiude resta chiuso, qualunque cosa dicano l'ambiente o la concessione. I fork non richiedono adesione. Un repository che la CLI non riesce a identificare conta come grand.

**Le modifiche distruttive chiedono prima conferma.** Quando un agent è autorizzato a una modifica distruttiva su un repository grand (per esempio `repo delete`), la risposta è `needs_confirmation`. Un client MCP mostra all'utente una richiesta di conferma; un client che non ne ha una riceve un argomento `confirm` da rimandare dopo aver chiesto all'utente. Nella CLI, l'umano riesegue il comando con `--confirm-grand <repo>`.

Ogni risposta porta un codice stabile (`POLICY_DENIED`, `GRAND_REPO_DENIED`, `CLUSTER_OPS_DENIED`, `AGENT_OPT_IN_MISSING`, `FORK_BLOCKED`, `AGENT_BLOCKED`, `CONFIRMATION_REQUIRED`), così uno script o un agent si regola sul codice e non sul messaggio ([Output JSON](/it/docs/ai-agents-json-output)).

## Il modello knowledge-gate

Le mutazioni sensibili seguono la convenzione `passwd(1)`: per cambiare un segreto, prova che lo conoscevi già. **Simmetrico per umani e agent**. Entrambi passano attraverso lo stesso gate. Non esiste il bypass "Sono io alla tastiera".

- Vuoi ruotare un token API memorizzato in `/credentials/cfDnsApiToken`?
- La CLI chiede: "qual è il valore attuale?"
- L'agent (o l'umano) fornisce il plaintext tramite `--current "$OLD"`. La CLI esegue l'hash di `$OLD` con SHA-256 e lo confronta con il digest del valore attualmente memorizzato. Match → la scrittura procede. Mismatch → rifiutato, registrato.
- Per ruotare senza verificare il valore precedente, passa `--rotate-secret` (mutuamente esclusivo con `--current`). Viene registrato in modo evidente come rotazione e vale solo per un umano su un terminale interattivo: un agent, o uno script senza terminale su stdin, ha comunque bisogno di `--current`.

Il modello chiude tre superfici di attacco:

1. **Rotazione silenziosa**: un chiamante (agent o umano) senza accesso precedente a `$OLD` non può sostituirlo con un valore proprio.
2. **Exfiltrazione tramite probing**: la risposta del digest non contiene mai plaintext; anche un log di audit compromesso mostra `expected abc12345…, got deadbeef…`, non i valori sottostanti.
3. **Calpestamento accidentale della configurazione di produzione**: richiede `--current` deliberato ogni volta, anche al TTY. Cattura l'errore "Intendevo impostare STRIPE_TEST ma sono nella shell di produzione".

### Suggerimenti strutturati sulla prossima azione

Quando la precondizione fallisce, l'envelope JSON (`--output json`) contiene un campo `errors[].next` strutturato che dice agli agent esattamente cosa suggerire all'umano:

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "...",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        { "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Gli agent dovrebbero riportare `next.options[].run` testualmente all'umano invece di inventare propri comandi.** Questo evita il caso in cui l'agent inventa un comando che non esiste e lascia all'operatore il controllo dell'azione effettiva. L'opzione di rotazione è pensata per l'umano, da un terminale; all'agent stesso viene rifiutata.

### Esempio pratico

```bash
# Scopri il digest breve dello stub di redazione (sicuro per gli agent).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Prova a sovrascrivere senza prova: rifiutato.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current

# Fornisci il plaintext attuale: consentito.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Se l'agent non ha mai avuto `$OLD_CF_TOKEN`, non può soddisfare la precondizione e la rotazione viene rifiutata. Chi conosce il valore può comunque eseguirla: passando `--current` dalla propria shell, oppure con `rdc config field rotate` su un terminale interattivo.

## Redazione per impostazione predefinita

Ogni comando `rdc` che legge lo stato sensibile, `config show`, `config field get`, `config machine list`, `config edit --dump --redacted`, restituisce **stub di redazione** per i campi segreti, non plaintext:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

Il suffisso hex di 8 caratteri dello stub è il primo 8 caratteri di `sha256(canonicalize(value))`: abbastanza per distinguere a prima vista due valori diversi, non abbastanza per invertire. Un agent può usare uno stub per tracciare se un valore è cambiato senza vederlo mai.

`--reveal` annulla la redazione per gli umani su un TTY interattivo. Gli agent sono rifiutati indipendentemente dallo stato del TTY. Ogni concessione scrive una voce di audit `reveal_granted`; ogni rifiuto scrive una voce `refused` con i segnali dell'agent allegati.

## Come viene verificata un'adesione esplicita locale su ogni sistema operativo

`REDIACC_ALLOW_GRAND_REPO` e `REDIACC_ALLOW_CLUSTER_OPS` si basano entrambe sulla verifica degli antenati per dimostrare che l'adesione è stata impostata dall'umano e non iniettata dall'agent. La verifica funziona su Linux, macOS e Windows, ma il testimone che legge cambia a seconda della piattaforma, e così la solidità della garanzia:

| Piattaforma | Testimone | Livello di certezza |
|---|---|---|
| Linux | `/proc/<pid>/environ` per ogni processo della catena | Snapshot al momento dell'exec, servito dal kernel. Un processo non può modificare retroattivamente cosa è stato avviato con. |
| macOS | `kern.procargs2` sysctl, letto da un piccolo helper che si trova dentro `rdc` | Stessa proprietà dello snapshot al momento dell'exec come Linux. Leggibile per i tuoi stessi processi senza root. |
| Windows | Il blocco di ambiente dal vivo di ogni processo antenato (PEB), letto dallo stesso helper, con guardie di riuso dei PID | Più debole: Windows non conserva uno snapshot al momento dell'exec, quindi il controllo legge la memoria corrente. Gli antenati comunque non possono essere riscritti da nulla che un agent normalmente esegue, ma la testimone non è congelata dal kernel come su Linux e macOS. |

Su macOS e Windows la CLI avvia il binario `renet` incluso per eseguire la lettura; l'helper indica quali delle variabili osservate porta ciascun antenato, e tutta la logica decisionale resta nella CLI. Se l'helper manca, è obsoleto o fallisce per qualsiasi motivo, la CLI non può verificare l'adesione e **fallisce in modo sicuro**: l'adesione viene respinta e l'errore dice che la verifica non era disponibile, non che sia stato fatto qualcosa di sbagliato. Un'installazione funzionante non mostra mai quel messaggio; reinstallare `rdc` ripristina l'helper.

Ciò che resta vero su ogni piattaforma: l'adesione deve essere già presente nell'ambiente del processo dell'agent quando questo parte. Si esporta nel terminale, poi si avvia l'agent. Un agent che imposta la variabile a sessione in corso viene rifiutato.

## Log di audit

Ogni mutazione, ogni rifiuto, ogni concessione `--reveal` scrive una riga JSONL in `~/.config/rediacc/audit.log.jsonl` (modalità `0600`, ruotato a 10 MB). Ogni riga è collegata tramite hash: il campo `prevHash` è `sha256("<riga precedente>")`. La manomissione di qualsiasi riga rompe la catena in tutte le righe successive.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent environment","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### Ispezione

```bash
# Elenca le voci recenti
rdc config audit log --since 24h

# Filtra per glob del puntatore
rdc config audit log --path '/credentials/*'

# Solo voci originate dagli agent
rdc config audit log --actor agent

# Mostra le nuove voci in tempo reale (Ctrl+C per fermare)
rdc config audit tail

# Verifica che la catena hash sia intatta
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   OPPURE
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### Cosa non appare mai nel log di audit

- Valori dei segreti in testo in chiaro
- Passphrase, token, chiavi SSH
- I valori vecchi/nuovi in caso di mancata corrispondenza della precondizione `--current` (solo il prefisso digest a 8 caratteri)

Il log è sicuro da condividere con un revisore della sicurezza o da allegare a un report di bug.

## Limiti del modello comportamentale

I guardrail degli agenti sono **comportamentali, non crittografici**. Un agente determinato o istruito che gira con lo stesso UID del file di configurazione può sempre eseguire `cat ~/.config/rediacc/rediacc.json` e leggere il testo in chiaro, perché il file è leggibile dal processo.

Per un'applicazione crittografica reale, usa l'[archivio di configurazione cifrato](/en/docs/config-storage): i segreti risiedono lato server, ogni campo sensibile porta un commitment HMAC per campo e il worker dell'account rifiuta le scritture la cui precondizione `--current` non corrisponde all'hash memorizzato. Il server non vede mai il testo in chiaro (zero-knowledge), ma applica comunque il gate.

Il percorso locale: la via facile è quella sicura. L'archivio remoto: anche la via alternativa è crittograficamente difficile.

## Cosa Rediacc non isola

I guardrail degli agenti in questa pagina proteggono l'infrastruttura propria di Rediacc: il file di configurazione, il daemon Docker per repository, i dati del repository cifrati con LUKS, la sandbox SSH con scope limitato. Non proteggono i servizi esterni per cui il repository detiene credenziali.

Un fork di un repository è un reflink BTRFS del volume del genitore. Tutto ciò che risiede sul disco nel genitore è byte-identico nel fork: codice, dati e file `.env` compresi. Se il repository contiene un `STRIPE_LIVE_KEY`, un `AWS_ACCESS_KEY_ID`, un token API di Railway o qualsiasi altra credenziale a lunga durata per un servizio di terze parti, il fork la eredita. Un agente che opera nella sandbox del fork può leggere quel file, esfiltrare il valore o usarlo per chiamare l'API di terze parti. Il servizio di terze parti non ha modo di sapere se la chiamata proviene da un fork o dalla produzione.

Questa è la linea di responsabilità condivisa:

| Confine | Proprietario |
|---|---|
| Dati del repository, mount namespace, scope Docker, guardrail degli agenti, log di audit, iniezione dei segreti al momento del deployment | Rediacc |
| Codice applicativo che utilizza quei segreti e le credenziali inserite nell'immagine in fase di build | Sviluppatore del repository |

La mitigazione principale è integrata: i **[segreti per repository](/en/docs/repositories#secrets)** sono memorizzati in un piano separato dall'immagine del repository cifrata e non vengono copiati attraverso il confine del fork. I container di un fork si avviano con una mappa dei segreti vuota e si identificano come un'entità esterna diversa dal genitore. Impostarli con `rdc repo secret set` (modalità env per l'interpolazione in compose, modalità file per i blocchi `secrets:` tmpfs). Il mutation gate è simmetrico: sia gli esseri umani che gli agenti devono fornire `--current` (precondizione stile passwd) per sovrascrivere o eliminare un valore esistente; `--rotate-secret` (rotazione con audit) è l'alternativa per un umano su un terminale.

**L'isolamento tra repository è applicato.** Un file compose malevolo o trascurato nel repository B non può fare riferimento alla directory dei segreti del repository A. Il validatore di compose di renet rifiuta categoricamente qualsiasi percorso `secrets: file:`, `configs: file:` o `env_file:` che punta fuori dalla directory `${REDIACC_NETWORK_ID}` del repository corrente, e il rifiuto NON è annullabile con `--unsafe`. Difesa in profondità: la sandbox Landlock attorno al sottoprocesso bash del Rediaccfile limita le letture del filesystem alla sola directory dei segreti della rete corrente, quindi un `cat /var/run/rediacc/net-<altro>/secrets/X` da un Rediaccfile malevolo fallisce con EACCES a livello kernel. Lo stesso vale per l'API Docker: il socket Docker di ogni repository è servito da un proxy di policy di renet che rifiuta con un `403` `--privileged`, `pid`, `ipc` e `uts` dell'host, le richieste di dispositivi e i bind che raggiungono il runtime o i dati di un altro repository, quindi un container con `${DOCKER_SOCKET}` non può usare l'API per raggiungere un altro repository, e non viene controllato solo un file compose. Solo l'operatore può ampliare la regola dei bind, per directory host con nome, con una concessione di proprietà di root su cui nessun container può scrivere.

Due pattern aggiuntivi chiudono i casi limite:

1. **Non inserire credenziali di produzione nel filesystem del repository.** Un file `.env` incluso nell'immagine, o una credenziale persistita in un volume durante `up()`, viene reflinkata nel fork. La funzionalità dei segreti per repository protegge solo i valori che si mantengono nel piano dei segreti. Non può proteggere retroattivamente i byte che già risiedono nell'immagine LUKS. Per i repository esistenti con file `.env` incorporati, spostali manualmente nei segreti per repository.
2. **Limitare la rete in uscita del fork con il filtraggio egress eBPF** in modo che possa raggiungere solo localhost ed endpoint sandbox espliciti. L'isolamento di rete per repository di Rediacc è la base; le allowlist egress per fork non sono ancora costruite, ma il percorso è aperto.

Rediacc gestisce l'iniezione al momento del deployment, l'isolamento tra fork e l'isolamento tra repository. La parte "non inserirlo nell'immagine" è a carico dell'utente.

## Ricette rapide

### Lasciare che un agent lavori su un repository grand

```bash
# Come umano, prima di avviare l'agent:
export REDIACC_ALLOW_GRAND_REPO='gitlab'
claude              # oppure cursor, gemini, ecc.
```

L'agent può ora modificare `gitlab`, dove la policy consente modifiche ai repository grand, e nessun altro repository grand. Una modifica distruttiva, come `repo delete gitlab`, chiede comunque conferma.

### Ruotare un token cloud senza conoscere il vecchio valore

```bash
# Come umano, su un terminale interattivo:
rdc config field rotate --pointer /credentials/cfDnsApiToken --new "$NEW_CF_TOKEN"
```

La rotazione senza `--current` resta all'umano. Un agent che conosce il valore attuale usa invece `rdc config field set --current`.

### Scoprire quali campi un agente è autorizzato a toccare

```bash
rdc config field list --sensitive --output json
```

Restituisce ogni template di puntatore, il suo tipo (`secret` / `credential` / `pii` / `identifier`) e se è incluso nell'envelope HMAC lato server.

## Vedi anche

- [Panoramica sull'integrazione degli agenti AI](/en/docs/ai-agents-overview): il tour di livello superiore
- [Server MCP](/it/docs/ai-agents-mcp): MCP locale e remoto, concessioni e le loro adesioni esplicite
- [Modello di sicurezza](/it/docs/security-model): il record di policy e chi può scriverlo
- [Configurazione di Claude Code](/en/docs/ai-agents-claude-code): template di integrazione
- [Envelope di output JSON](/en/docs/ai-agents-json-output): risposte leggibili dalla macchina
- [Archivio di configurazione cifrato](/en/docs/config-storage): applicazione crittografica lato server
- [Sicurezza dell'account](/en/docs/account-security): postura di sicurezza dell'operatore
