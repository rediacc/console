---
title: Sicurezza e guardrail degli agenti AI
description: >-
  Come la CLI di Rediacc impedisce agli assistenti di programmazione AI di far
  trapelare segreti, sovrascrivere credenziali o scalare i privilegi. Knowledge-gate,
  redazione, override con verifica dell'ascendenza e log di audit con hash a catena. È progettato così perché la sicurezza è priorità assoluta.
category: Concepts
order: 35
language: it
---

Quando Claude Code, Cursor, Gemini CLI, Copilot CLI o qualsiasi altro assistente di programmazione AI pilota `rdc`, la CLI lo tratta diversamente da un essere umano alla tastiera. Questa pagina spiega cosa può fare l'agente, cosa non può fare e come i guardrail reggono anche quando l'agente cerca di aggirarli.

## Riferimento rapido: cosa possono e non possono fare gli agenti

| Operazione | Comportamento predefinito | Come sbloccare per un caso d'uso specifico |
|---|---|---|
| `rdc config show` (redatto) | Permesso |  |
| `rdc config field get --pointer <pointer>` (stub redatto o digest) | Permesso |  |
| `rdc config field get --pointer <pointer> --digest` | Permesso |  |
| `rdc config field set --pointer <pointer>` (campo pubblico) | Permesso |  |
| `rdc config field set --pointer <pointer>` (campo sensibile, **con `--current` corretto**) | Permesso |  |
| `rdc config edit --dump` (JSONC redatto) | Permesso |  |
| `rdc config audit {log, tail, verify}` | Permesso |  |
| `rdc config field set --pointer <pointer>` (campo sensibile, senza `--current`) | Rifiutato | Fornire `--current "<vecchio valore>"` |
| `rdc config field get --pointer <pointer> --reveal` | Rifiutato | Usare `--digest` al suo posto |
| `rdc config show --reveal` | Rifiutato | Usare `rdc config show` senza opzioni |
| `rdc config edit` (editor interattivo) | Rifiutato | L'utente imposta `REDIACC_ALLOW_CONFIG_EDIT=*` prima di avviare l'agente |
| `rdc config edit --apply <file>` | Rifiutato | Stesso override |
| `rdc config field rotate --pointer <pointer>` | Rifiutato | Stesso override; richiede conferma interattiva |
| `rdc term connect -m <machine>` (SSH diretto alla macchina) | Rifiutato | Prima eseguire un fork del repository e connettersi al fork |

Tutto ciò che viene rifiutato a un agente viene scritto nel log di audit con `outcome: refused` e una motivazione.

## Come vengono rilevati gli agenti

La CLI tratta un processo come agente quando si verifica almeno una di queste condizioni:

- Una delle variabili `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` è impostata a `"1"`, oppure `CURSOR_TRACE_ID` è impostata.
- Su Linux: qualsiasi processo genitore nella catena di ascendenza possiede una di quelle variabili nel proprio ambiente (tramite `/proc/<pid>/environ`). Anche se l'agente annulla le proprie variabili con `env -i` o uno script wrapper, la catena dei genitori rivela comunque alla CLI chi lo ha avviato.

Il rilevamento viene eseguito una volta per processo e viene memorizzato nella cache. Non può essere disabilitato.

## Il modello knowledge-gate

Le mutazioni sensibili seguono la convenzione `passwd(1)`: per modificare un segreto, dimostra di conoscerlo già. **Simmetrico per esseri umani e agenti**: entrambi passano per lo stesso gate. Non esiste un bypass "sono alla tastiera".

- Si vuole ruotare un token API memorizzato in `/credentials/cfDnsApiToken`?
- La CLI chiede: "qual è il valore attuale?"
- L'agente (o l'utente) fornisce il testo in chiaro tramite `--current "$OLD"`. La CLI calcola l'hash SHA-256 di `$OLD` e lo confronta con il digest del valore attualmente memorizzato. Corrispondenza: la scrittura avviene. Mancata corrispondenza: rifiutato e registrato nel log.
- Per ruotare senza verificare il valore precedente, passare `--rotate-secret` (mutuamente esclusivo con `--current`). Viene registrato esplicitamente come rotazione.

Il modello chiude tre superfici di attacco:

1. **Rotazione silenziosa**: un chiamante (agente o umano) senza accesso precedente a `$OLD` non può sostituirlo con un valore arbitrario.
2. **Esfiltrazione tramite probing**: la risposta con digest non contiene mai testo in chiaro; anche un log di audit compromesso mostra `expected abc12345..., got deadbeef...`, non i valori reali.
3. **Sovrascrittura accidentale della configurazione di produzione**: richiede `--current` deliberato ogni volta, anche su un TTY. Intercetta l'errore "volevo impostare STRIPE_TEST ma sono nella shell di produzione".

### Suggerimenti strutturati per la prossima azione

Quando la precondizione fallisce, l'envelope JSON (`--output json`) include un campo strutturato `errors[].next` che indica agli agenti esattamente cosa suggerire all'utente:

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "...",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        { "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Gli agenti devono trasmettere `next.options[].run` letteralmente all'utente invece di sintetizzare comandi propri.** Questo evita il problema "l'agente inventa un comando inesistente" e mantiene l'operatore in controllo dell'azione reale.

### Esempio pratico

```bash
# Scopri il digest breve dello stub di redazione (sicuro per gli agenti).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Tentativo di sovrascrittura senza prova: rifiutato.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# Fornitura del testo in chiaro attuale: permesso.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Se l'agente non ha mai avuto `$OLD_CF_TOKEN`, non può soddisfare la precondizione e la rotazione viene rifiutata. L'utente che *lo possiede* può ancora farlo tramite l'editor o passando `--current` dalla propria shell.

## Redazione per impostazione predefinita

Ogni comando `rdc` che legge uno stato sensibile (`config show`, `config field get`, `config machine list`, `config edit --dump`) restituisce **stub di redazione** per i campi segreti, non il testo in chiaro:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

Il suffisso esadecimale a 8 caratteri dello stub è i primi 8 caratteri di `sha256(canonicalize(value))`: sufficiente per distinguere due valori diversi a colpo d'occhio, non abbastanza per invertirlo. Un agente può usare uno stub per monitorare se un valore è cambiato senza mai vederlo.

`--reveal` mostra il testo in chiaro agli esseri umani su un TTY interattivo. Gli agenti vengono rifiutati indipendentemente dallo stato del TTY. Ogni concessione scrive una voce di audit `reveal_granted`; ogni rifiuto scrive una voce `refused` con i segnali dell'agente allegati.

## L'override `REDIACC_ALLOW_CONFIG_EDIT`

Alcune operazioni (l'editor interattivo, `--apply`, `field rotate`) esistono per gli esseri umani e non hanno un percorso sicuro per gli agenti. Se si vuole che un agente esegua una di queste operazioni, si imposta:

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # bypass completo
# oppure
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# (glob di scope separati da virgola: wildcard * permesse per segmento)
```

...e l'agente lo eredita.

**Dettaglio cruciale**: l'override deve apparire in un processo **superiore** all'agente nella catena di ascendenza. Se l'agente lo imposta nel proprio ambiente (o in una subshell avviata da lui), la CLI rifiuta e lo comunica:

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

L'effetto: un agente non può aggirare un guardrail eseguendo `export REDIACC_ALLOW_CONFIG_EDIT='*'` a sessione in corso. Solo un processo genitore (l'utente, nel suo terminale, prima di avviare l'agente) può aprire quella porta.

## Supporto piattaforma: solo Linux per gli override

`REDIACC_ALLOW_CONFIG_EDIT` e `REDIACC_ALLOW_GRAND_REPO` si affidano entrambi alla verifica dell'ascendenza per provare che l'override sia stato impostato dall'utente e non iniettato dall'agente. La verifica legge `/proc/<pid>/environ` per ogni processo nella catena. Quel file viene impostato dal kernel al momento dell'esecuzione e non può essere modificato dal processo stesso, quindi l'ambiente della shell genitore è un testimone a prova di manomissione.

Quel file non esiste su macOS o Windows. Senza un modo per verificare la legittimità, la CLI fallisce in modalità chiusa. Anche quando si imposta correttamente l'override nella propria shell prima di avviare l'agente, l'override viene rifiutato. Il messaggio di errore indica esattamente cosa fare:

> The REDIACC_ALLOW_GRAND_REPO override is not supported on darwin. This override only works on Linux. On Windows and macOS, agents must use the fork-first workflow. ... To use the override, run your agent on Linux (directly, WSL, Docker, or a VM).

In pratica, gli utenti non Linux non hanno una via d'uscita dal flusso fork-first. Questo è intenzionale. Gli agenti vengono instradati attraverso una sandbox che non possono eludere, indipendentemente da come sono stati istruiti. Eseguire l'agente dentro WSL, un container Linux o una VM Linux se si ha bisogno dell'override; altrimenti, lavorare su un fork.

## Log di audit

Ogni mutazione, ogni rifiuto, ogni concessione `--reveal` scrive una riga JSONL in `~/.config/rediacc/audit.log.jsonl` (modalità `0600`, rotato a 10 MB). Ogni riga è collegata tramite hash: il campo `prevHash` è `sha256("<riga precedente>")`. La manomissione di qualsiasi riga rompe la catena in tutte le righe successive.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### Ispezione

```bash
# Elenca le voci recenti
rdc config audit log --since 24h

# Filtra per glob del puntatore
rdc config audit log --path '/credentials/*'

# Solo voci originate dagli agenti
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

Per un'applicazione crittografica reale, usare l'[archivio di configurazione cifrato](/en/docs/config-storage): i segreti risiedono lato server, ogni campo sensibile porta un commitment HMAC per campo e il worker dell'account rifiuta le scritture la cui precondizione `--current` non corrisponde all'hash memorizzato. Il server non vede mai il testo in chiaro (zero-knowledge), ma applica comunque il gate.

Il percorso locale è "il percorso facile è sicuro". Il percorso con archivio remoto è "il percorso difficile è difficile anche lui".

## Cosa Rediacc non isola

I guardrail degli agenti in questa pagina proteggono l'infrastruttura propria di Rediacc: il file di configurazione, il daemon Docker per repository, i dati del repository cifrati con LUKS, la sandbox SSH con scope limitato. Non proteggono i servizi esterni per cui il repository detiene credenziali.

Un fork di un repository è un reflink BTRFS del volume del genitore. Tutto ciò che risiede sul disco nel genitore è byte-identico nel fork: codice, dati e file `.env` compresi. Se il repository contiene un `STRIPE_LIVE_KEY`, un `AWS_ACCESS_KEY_ID`, un token API di Railway o qualsiasi altra credenziale a lunga durata per un servizio di terze parti, il fork la eredita. Un agente che opera nella sandbox del fork può leggere quel file, esfiltrare il valore o usarlo per chiamare l'API di terze parti. Il servizio di terze parti non ha modo di sapere se la chiamata proviene da un fork o dalla produzione.

Questa è la linea di responsabilità condivisa:

| Confine | Proprietario |
|---|---|
| Dati del repository, mount namespace, scope Docker, guardrail degli agenti, log di audit, iniezione dei segreti al momento del deployment | Rediacc |
| Codice applicativo che utilizza quei segreti e le credenziali inserite nell'immagine in fase di build | Sviluppatore del repository |

La mitigazione principale è integrata: i **[segreti per repository](/en/docs/repositories#secrets)** sono memorizzati in un piano separato dall'immagine del repository cifrata e non vengono copiati attraverso il confine del fork. I container di un fork si avviano con una mappa dei segreti vuota e si identificano come un'entità esterna diversa dal genitore. Impostarli con `rdc repo secret set` (modalità env per l'interpolazione in compose, modalità file per i blocchi `secrets:` tmpfs). Il mutation gate è simmetrico: sia gli esseri umani che gli agenti devono fornire `--current` (precondizione stile passwd) o `--rotate-secret` (rotazione con audit) per sovrascrivere o eliminare un valore esistente.

**L'isolamento tra repository è applicato.** Un file compose malevolo o trascurato nel repository B non può fare riferimento alla directory dei segreti del repository A. Il validatore di compose di renet rifiuta categoricamente qualsiasi percorso `secrets: file:`, `configs: file:` o `env_file:` che punta fuori dalla directory `${REDIACC_NETWORK_ID}` del repository corrente, e il rifiuto NON è annullabile con `--unsafe`. Difesa in profondità: la sandbox Landlock attorno al sottoprocesso bash del Rediaccfile limita le letture del filesystem alla sola directory dei segreti della rete corrente, quindi un `cat /var/run/rediacc/secrets/<altro>/X` da un Rediaccfile malevolo fallisce con EACCES a livello kernel.

Due pattern aggiuntivi chiudono i casi limite:

1. **Non inserire credenziali di produzione nel filesystem del repository.** Un file `.env` incluso nell'immagine, o una credenziale persistita in un volume durante `up()`, viene reflinkata nel fork. La funzionalità dei segreti per repository protegge solo i valori che si mantengono nel piano dei segreti. Non può proteggere retroattivamente i byte che già risiedono nell'immagine LUKS. Per i repository esistenti con file `.env` incorporati, spostarli manualmente nei segreti per repository.
2. **Limitare la rete in uscita del fork con il filtraggio egress eBPF** in modo che possa raggiungere solo localhost ed endpoint sandbox espliciti. L'isolamento di rete per repository di Rediacc è la base; le allowlist egress per fork non sono ancora costruite, ma il percorso è aperto.

Rediacc gestisce l'iniezione al momento del deployment, l'isolamento tra fork e l'isolamento tra repository. La parte "non inserirlo nell'immagine" è a carico dell'utente.

## Ricette rapide

### Permettere a un agente di ruotare un singolo token cloud

```bash
# Come utente, prima di avviare l'agente:
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # oppure cursor, gemini, ecc.
```

Ora l'agente può eseguire `config field rotate /credentials/cfDnsApiToken --new ...` ma non può ancora modificare `/credentials/ssh/privateKey` né aprire l'editor interattivo.

### Permettere a un agente una sessione di modifica della configurazione ampia

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

L'agente può aprire `rdc config edit`, usare `--reveal` ed eseguire `field rotate`. Ogni azione viene comunque registrata nel log di audit con `actor.kind: agent` e il segnale `CLAUDECODE`.

### Scoprire quali campi un agente è autorizzato a toccare

```bash
rdc config field list --sensitive --output json
```

Restituisce ogni template di puntatore, il suo tipo (`secret` / `credential` / `pii` / `identifier`) e se è incluso nell'envelope HMAC lato server.

## Vedi anche

- [Panoramica sull'integrazione degli agenti AI](/en/docs/ai-agents-overview): il tour di livello superiore
- [Configurazione di Claude Code](/en/docs/ai-agents-claude-code): template di integrazione
- [Envelope di output JSON](/en/docs/ai-agents-json-output): risposte leggibili dalla macchina
- [Archivio di configurazione cifrato](/en/docs/config-storage): applicazione crittografica lato server
- [Sicurezza dell'account](/en/docs/account-security): postura di sicurezza dell'operatore
