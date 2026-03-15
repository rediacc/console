---
title: Übersicht zur KI-Agenten-Integration
description: Wie KI-Coding-Assistenten wie Claude Code, Cursor und Cline sich mit der Rediacc-Infrastruktur für autonome Bereitstellung und Verwaltung integrieren.
category: Guides
order: 30
language: de
sourceHash: "2d8ab92216666d0e"
---

KI-Coding-Assistenten können die Rediacc-Infrastruktur über die `rdc` CLI autonom verwalten. Diese Anleitung behandelt die Integrationsansaetze und den Einstieg.

## Warum Self-Hosted + KI-Agenten

Die Architektur von Rediacc ist von Natur aus agentenfreundlich:

- **CLI-first**: Jede Operation ist ein `rdc`-Befehl — keine GUI erforderlich
- **SSH-basiert**: Das Protokoll, das Agenten aus Trainingsdaten am besten kennen
- **JSON-Ausgabe**: Alle Befehle unterstützen `--output json` mit einheitlichem Envelope
- **Docker-Isolation**: Jedes Repository erhaelt seinen eigenen Daemon und Netzwerk-Namespace
- **Skriptfaehig**: `--yes` überspringt Bestaetigungen, `--dry-run` zeigt destruktive Operationen in der Vorschau

## Integrationsansaetze

### 1. AGENTS.md / CLAUDE.md-Vorlage

Der schnellste Einstieg. Kopieren Sie unsere [AGENTS.md-Vorlage](/de/docs/agents-md-template) in Ihr Projektstammverzeichnis:

- `CLAUDE.md` für Claude Code
- `.cursorrules` für Cursor
- `.windsurfrules` für Windsurf

Dies gibt dem Agenten den vollstaendigen Kontext über verfügbare Befehle, Architektur und Konventionen.

### 2. JSON-Ausgabe-Pipeline

Wenn Agenten `rdc` in einer Subshell aufrufen, wechselt die Ausgabe automatisch zu JSON (non-TTY-Erkennung). Jede JSON-Antwort verwendet ein einheitliches Envelope-Format:

```json
{
  "success": true,
  "command": "machine query",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

Fehlerantworten enthalten die Felder `retryable` und `guidance`:

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. Agenten-Faehigkeitserkennung

Der `rdc agent`-Unterbefehl bietet strukturierte Introspektion:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema "machine query"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## Wichtige Flags für Agenten

| Flag | Zweck |
|------|---------|
| `--output json` / `-o json` | Maschinenlesbare JSON-Ausgabe |
| `--yes` / `-y` | Interaktive Bestaetigungen überspringen |
| `--quiet` / `-q` | Informative stderr-Ausgabe unterdruecken |
| `--fields name,status` | Ausgabe auf bestimmte Felder beschraenken |
| `--dry-run` | Destruktive Operationen ohne Ausführung in der Vorschau anzeigen |

## Naechste Schritte

- [Claude Code Einrichtungsanleitung](/de/docs/ai-agents-claude-code) — Schritt-für-Schritt Claude Code-Konfiguration
- [Cursor Einrichtungsanleitung](/de/docs/ai-agents-cursor) — Cursor-IDE-Integration
- [JSON-Ausgabe-Referenz](/de/docs/ai-agents-json-output) — Vollständige JSON-Ausgabe-Dokumentation
- [AGENTS.md-Vorlage](/de/docs/agents-md-template) — Kopierfertige Agenten-Konfigurationsvorlage
