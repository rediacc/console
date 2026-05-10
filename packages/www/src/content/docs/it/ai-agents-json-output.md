---
title: Riferimento output JSON
description: Riferimento completo per il formato di output JSON della CLI rdc, schema dell'envelope, gestione degli errori e comandi di discovery per agenti. È già disponibile tramite il flag --output json oppure -o json.
category: Reference
order: 51
language: it
---

Tutti i comandi `rdc` supportano l'output JSON strutturato per il consumo programmatico da parte di agenti AI e script.

## Abilitazione dell'output JSON

### Flag esplicito

```bash
rdc machine query --name prod-1 --output json
rdc machine query --name prod-1 -o json
```

### Rilevamento automatico

Quando `rdc` viene eseguito in un ambiente non-TTY (pipe, subshell o avviato da un agente AI), l'output passa automaticamente a JSON. Nessun flag necessario.

```bash
# Questi producono tutti JSON automaticamente
result=$(rdc machine query --name prod-1)
echo '{}' | rdc agent exec "machine query"
```

## Envelope JSON

Ogni risposta JSON utilizza un envelope uniforme:

```json
{
  "success": true,
  "command": "machine query",
  "data": {
    "name": "prod-1",
    "status": "running",
    "repositories": []
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 142
  }
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `success` | `boolean` | Se il comando si è completato con successo |
| `command` | `string` | Il percorso completo del comando (es. `"machine query"`, `"repo up"`) |
| `data` | `object \| array \| null` | Payload specifico del comando in caso di successo, `null` in caso di errore |
| `errors` | `array \| null` | Oggetti errore in caso di fallimento, `null` in caso di successo |
| `warnings` | `string[]` | Avvisi non fatali raccolti durante l'esecuzione |
| `metrics` | `object` | Metadati di esecuzione |

## Risposte di errore

I comandi falliti restituiscono errori strutturati con suggerimenti di ripristino:

```json
{
  "success": false,
  "command": "machine query",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### Campi degli errori

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `code` | `string` | Codice di errore leggibile dalla macchina (vedi le costanti `ERROR_CODES` per l'elenco canonico) |
| `message` | `string` | Descrizione leggibile dall'utente |
| `retryable` | `boolean` | Se riprovare lo stesso comando potrebbe avere successo |
| `guidance` | `string` | Suggerimento in formato libero (legacy. Preferire `next` per dati di azione strutturati) |
| `next` | `object?` | Suggerimento strutturato per l'azione successiva (quando presente). Vedi sotto |

### Suggerimenti di azione strutturati `next`

Per i codici di errore ad alto valore (es. `PRECONDITION_MISMATCH`), gli errori includono un campo `next` strutturato che indica all'agente esattamente quale comando suggerire all'utente. **Gli agenti devono riprodurre `next.options[].run` testualmente all'utente, senza sintetizzare un comando proprio**. Questo evita il problema "l'agente inventa un comando inesistente".

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "--current digest mismatch (expected 3264f8ee…, got 611dfd8a…)",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        {
          "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY"
        },
        {
          "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret"
        }
      ]
    }
  }]
}
```

Schema:

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `next.summary` | `string` | Descrizione in una riga di ciò che l'utente deve decidere |
| `next.options[]` | `array` | Azioni concrete; ognuna è un'alternativa che l'utente può scegliere |
| `next.options[].description` | `string` | Spiegazione leggibile dall'utente di questa opzione |
| `next.options[].run` | `string` | Comando CLI esatto. Riproducilo testualmente all'utente |

### Errori riprovabili

Questi tipi di errore sono contrassegnati come `retryable: true`:

- **NETWORK_ERROR**, connessione SSH o errore di rete
- **RATE_LIMITED**, troppe richieste, attendi e riprova
- **API_ERROR**, errore temporaneo del backend

Gli errori non riprovabili (autenticazione, non trovato, argomenti non validi) richiedono un'azione correttiva prima di riprovare.

## Filtraggio dell'output

Usa `--fields` per limitare l'output a chiavi specifiche. Questo riduce l'utilizzo dei token quando servono solo dati specifici:

```bash
rdc machine containers --name prod-1 -o json --fields name,status,repository
```

## Output in modalità dry-run

I comandi distruttivi supportano `--dry-run` per visualizzare in anteprima cosa succederebbe:

```bash
rdc repo delete --name mail -m prod-1 --dry-run -o json
```

```json
{
  "success": true,
  "command": "repo delete",
  "data": {
    "dryRun": true,
    "repository": "mail",
    "machine": "prod-1",
    "guid": "a1b2c3d4-..."
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 8
  }
}
```

Comandi con supporto `--dry-run`: `repo up`, `repo down`, `repo delete`, `snapshot delete`, `sync upload`, `sync download`.

## Comandi di discovery per agenti

Il sottocomando `rdc agent` fornisce introspezione strutturata agli agenti AI per scoprire le operazioni disponibili in fase di esecuzione.

### Elenca tutti i comandi

```bash
rdc agent capabilities
```

Restituisce l'albero completo dei comandi con argomenti, opzioni e descrizioni:

```json
{
  "success": true,
  "command": "agent capabilities",
  "data": {
    "version": "1.0.0",
    "commands": [
      {
        "name": "machine query",
        "description": "Show machine status",
        "arguments": [
          { "name": "machine", "description": "Machine name", "required": true }
        ],
        "options": [
          { "flags": "-o, --output <format>", "description": "Output format" }
        ]
      }
    ]
  }
}
```

### Ottieni lo schema di un comando

```bash
rdc agent schema --command "machine query"
```

Restituisce lo schema dettagliato per un singolo comando, inclusi tutti gli argomenti e le opzioni con i loro tipi e valori predefiniti.

### Esegui tramite JSON

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine query"
```

Accetta JSON da stdin, mappa le chiavi agli argomenti e alle opzioni del comando, ed esegue con output JSON forzato. Utile per la comunicazione strutturata agente-CLI senza costruire stringhe di comandi shell.

## Esempi di parsing

### Shell (jq)

```bash
status=$(rdc machine query --name prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "query", "--name", "prod-1", "-o", "json"],
    capture_output=True, text=True
)
envelope = json.loads(result.stdout)

if envelope["success"]:
    print(envelope["data"]["status"])
else:
    error = envelope["errors"][0]
    if error["retryable"]:
        # logica di ripetizione
        pass
    else:
        print(f"Error: {error['message']}")
        print(f"Fix: {error['guidance']}")
```

### Node.js

```javascript
import { execFileSync } from 'child_process';

const raw = execFileSync('rdc', ['machine', 'query', '--name', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
