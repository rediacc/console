---
title: JSON-Ausgabe-Referenz
description: Vollständige Referenz für das JSON-Ausgabeformat der rdc CLI, Envelope-Schema, Fehlerbehandlung und Agenten-Erkennungsbefehle.
category: Reference
order: 51
language: de
sourceHash: "a516c49fdaf9a901"
---

Alle `rdc`-Befehle unterstützen strukturierte JSON-Ausgabe für die programmatische Nutzung durch KI-Agenten und Skripte.

## JSON-Ausgabe aktivieren

### Explizites Flag

```bash
rdc machine info prod-1 --output json
rdc machine info prod-1 -o json
```

### Automatische Erkennung

Wenn `rdc` in einer non-TTY-Umgebung laeuft (gepipt, Subshell oder von einem KI-Agenten gestartet), wechselt die Ausgabe automatisch zu JSON. Kein Flag erforderlich.

```bash
# These all produce JSON automatically
result=$(rdc machine info prod-1)
echo '{}' | rdc agent exec "machine info"
```

## JSON-Envelope

Jede JSON-Antwort verwendet ein einheitliches Envelope-Format:

```json
{
  "success": true,
  "command": "machine info",
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
| `command` | `string` | Der vollstaendige Befehlspfad (z.B. `"machine info"`, `"repo up"`) |
| `data` | `object \| array \| null` | Befehlsspezifische Nutzlast bei Erfolg, `null` bei Fehler |
| `errors` | `array \| null` | Fehlerobjekte bei Misserfolg, `null` bei Erfolg |
| `warnings` | `string[]` | Nicht-fatale Warnungen, die waehrend der Ausführung gesammelt wurden |
| `metrics` | `object` | Ausführungsmetadaten |

## Fehlerantworten

Fehlgeschlagene Befehle geben strukturierte Fehler mit Wiederherstellungshinweisen zurück:

```json
{
  "success": false,
  "command": "machine info",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
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
| `code` | `string` | Maschinenlesbarer Fehlercode |
| `message` | `string` | Menschenlesbare Beschreibung |
| `retryable` | `boolean` | Ob ein erneuter Versuch desselben Befehls erfolgreich sein koennte |
| `guidance` | `string` | Vorgeschlagene naechste Aktion zur Behebung des Fehlers |

### Wiederholbare Fehler

Diese Fehlertypen sind mit `retryable: true` gekennzeichnet:

- **NETWORK_ERROR** — SSH-Verbindungs- oder Netzwerkfehler
- **RATE_LIMITED** — Zu viele Anfragen, warten und erneut versuchen
- **API_ERROR** — Vorübergehender Backend-Fehler

Nicht wiederholbare Fehler (Authentifizierung, nicht gefunden, ungueltige Argumente) erfordern korrektive Massnahmen vor einem erneuten Versuch.

## Ausgabe filtern

Verwenden Sie `--fields`, um die Ausgabe auf bestimmte Schluessel zu beschraenken. Dies reduziert den Token-Verbrauch, wenn nur bestimmte Daten benoetigt werden:

```bash
rdc machine containers prod-1 -o json --fields name,status,repository
```

## Testlauf-Ausgabe

Destruktive Befehle unterstützen `--dry-run` zur Vorschau der Auswirkungen:

```bash
rdc repo delete mail -m prod-1 --dry-run -o json
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

Befehle mit `--dry-run`-Unterstuetzung: `repo up`, `repo down`, `repo delete`, `snapshot delete`, `sync upload`, `sync download`.

## Agenten-Erkennungsbefehle

Der `rdc agent`-Unterbefehl bietet strukturierte Introspektion, damit KI-Agenten verfügbare Operationen zur Laufzeit entdecken können.

### Alle Befehle auflisten

```bash
rdc agent capabilities
```

Gibt den vollstaendigen Befehlsbaum mit Argumenten, Optionen und Beschreibungen zurück:

```json
{
  "success": true,
  "command": "agent capabilities",
  "data": {
    "version": "1.0.0",
    "commands": [
      {
        "name": "machine info",
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
rdc agent schema "machine info"
```

Gibt das detaillierte Schema für einen einzelnen Befehl zurück, einschliesslich aller Argumente und Optionen mit ihren Typen und Standardwerten.

### Ausführung über JSON

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine info"
```

Akzeptiert JSON über stdin, ordnet Schluessel den Befehlsargumenten und -optionen zu und fuehrt mit erzwungener JSON-Ausgabe aus. Nuetzlich für strukturierte Agent-zu-CLI-Kommunikation ohne Shell-Befehlszeichenfolgen erstellen zu müssen.

## Parsing-Beispiele

### Shell (jq)

```bash
status=$(rdc machine info prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "info", "prod-1", "-o", "json"],
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

const raw = execFileSync('rdc', ['machine', 'info', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
