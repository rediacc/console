---
title: JSON-Ausgabe-Referenz
description: >-
  Vollständige Referenz für das JSON-Ausgabeformat der rdc CLI, Envelope-Schema,
  Fehlerbehandlung und Agenten-Erkennungsbefehle.
category: Reference
order: 51
language: de
sourceHash: "9f8d61df26b59757"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Alle `rdc`-Befehle geben strukturiertes JSON aus. Das Ergebnis lässt sich direkt in ein Skript pipen oder an einen Agenten übergeben.

## JSON-Ausgabe aktivieren

### Explizites Flag

```bash
rdc machine query --name prod-1 --output json
rdc machine query --name prod-1 -o json
```

### Automatische Erkennung

Wenn `rdc` in einer non-TTY-Umgebung läuft (gepipt, Subshell oder von einem KI-Agenten gestartet), wechselt die Ausgabe automatisch zu JSON. Kein Flag erforderlich.

```bash
# These all produce JSON automatically
result=$(rdc machine query --name prod-1)
echo '{}' | rdc agent exec "machine query"
```

## JSON-Envelope

Jede JSON-Antwort verwendet ein einheitliches Envelope-Format:

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

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `success` | `boolean` | Ob der Befehl erfolgreich abgeschlossen wurde |
| `command` | `string` | Der vollständige Befehlspfad (z.B. `"machine query"`, `"repo up"`) |
| `data` | `object \| array \| null` | Befehlsspezifische Nutzlast bei Erfolg, `null` bei Fehler |
| `errors` | `array \| null` | Fehlerobjekte bei Misserfolg, `null` bei Erfolg |
| `warnings` | `string[]` | Nicht-fatale Warnungen, die während der Ausführung gesammelt wurden |
| `metrics` | `object` | Ausführungsmetadaten |

## Fehlerantworten

Fehlgeschlagene Befehle geben strukturierte Fehler mit Wiederherstellungshinweisen zurück:

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

### Fehlerfelder

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `code` | `string` | Maschinenlesbarer Fehlercode (die vollständige Liste steht in den `ERROR_CODES`-Konstanten) |
| `message` | `string` | Menschenlesbare Beschreibung |
| `retryable` | `boolean` | Ob ein erneuter Versuch desselben Befehls erfolgreich sein könnte |
| `guidance` | `string` | Freitexthinweis (veraltet. Bevorzuge `next` für strukturierte Aktionsdaten) |
| `next` | `object?` | Strukturierter Hinweis auf die nächste Aktion (wenn vorhanden). Siehe unten |

### Strukturierte `next`-Aktionshinweise

Bei hochwertigen Fehlercodes wie `PRECONDITION_MISMATCH` enthält der Fehler ein `next`-Feld mit den exakten Befehlen, die dem Benutzer angeboten werden sollen. Nicht jeder Fehlercode trägt dieses Feld, sondern nur solche mit einem definierten Wiederherstellungspfad. **Agenten sollten `next.options[].run` wörtlich an den Menschen weitergeben, anstatt eigene Befehle zu konstruieren.** Das vermeidet den Fehlerfall, bei dem der Agent einen Befehl erfindet, der gar nicht existiert. Es kommt häufiger vor, als man denkt.

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

| Feld | Typ | Beschreibung |
|-------|------|-------------|
| `next.summary` | `string` | Einzeilige Beschreibung, was der Benutzer entscheiden muss |
| `next.options[]` | `array` | Konkrete Aktionen; jede ist eine Alternative, die der Benutzer wählen kann |
| `next.options[].description` | `string` | Menschenlesbare Erklärung dieser Option |
| `next.options[].run` | `string` | Exakter CLI-Befehl. Wörtlich an den Benutzer weitergeben |

### Wiederholbare Fehler

Diese Fehlertypen sind mit `retryable: true` gekennzeichnet:

- **NETWORK_ERROR**, SSH-Verbindungs- oder Netzwerkfehler
- **RATE_LIMITED**, Zu viele Anfragen, warten und erneut versuchen
- **API_ERROR**, Vorübergehender Backend-Fehler

Nicht wiederholbare Fehler (Authentifizierung, nicht gefunden, ungültige Argumente) erfordern eine Korrektur, bevor ein erneuter Versuch sinnvoll ist.

## Ausgabe filtern

Verwende `--fields`, um die Ausgabe auf bestimmte Schlüssel zu beschränken und den Token-Verbrauch zu reduzieren:

```bash
rdc machine containers --name prod-1 -o json --fields name,status,repository
```

## Testlauf-Ausgabe

Destruktive Befehle unterstützen `--dry-run` zur Vorschau der Auswirkungen:

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

Befehle mit `--dry-run`-Unterstützung: `repo up`, `repo down`, `repo delete`, `snapshot delete`, `sync upload`, `sync download`.

## Agenten-Erkennungsbefehle

Der `rdc agent`-Unterbefehl bietet KI-Agenten einen strukturierten Weg, verfügbare Operationen zur Laufzeit zu entdecken.

### Alle Befehle auflisten

```bash
rdc agent capabilities
```

Gibt den vollständigen Befehlsbaum mit Argumenten, Optionen und Beschreibungen zurück:

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

### Befehlsschema abrufen

```bash
rdc agent schema --command "machine query"
```

Gibt das vollständige Schema für einen einzelnen Befehl zurück: alle Argumente und Optionen mit ihren Typen und Standardwerten.

### Ausführung über JSON

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine query"
```

Akzeptiert JSON über stdin, ordnet Schlüssel den Befehlsargumenten und -optionen zu und führt den Befehl mit erzwungener JSON-Ausgabe aus. Nützlich, wenn keine Shell-Befehlszeichenketten für Agent-zu-CLI-Aufrufe konstruiert werden sollen.

## Parsing-Beispiele

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
        # retry logic
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
