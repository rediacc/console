---
title: Übersicht zur KI-Agenten-Integration
description: "Wie Claude Code, Cursor und Cline die Rediacc-Infrastruktur über rdc verwalten: JSON-Ausgabe, Agenten-Introspektion und Sicherheitsmechanismen."
category: Guides
order: 30
language: de
sourceHash: "0aa0c975030d4856"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Ehrlich gesagt ist `rdc` von Grund auf agentenkompatibel entworfen. Claude Code, Cursor, Cline: Jeder KI-Assistent, der `rdc` in einer Subshell aufruft, erhält strukturierte JSON-Ausgabe, maschinenlesbare Fehlermeldungen und die Sicherheitsmechanismen, die man für die autonome Verwaltung der Rediacc-Infrastruktur erwartet. So funktioniert die Integration.

## Warum Self-Hosted + KI-Agenten

Die Architektur von Rediacc ist von Natur aus agentenfreundlich:

- **CLI-first**: Jede Operation ist ein `rdc`-Befehl, keine GUI erforderlich
- **SSH-basiert**: Das Protokoll, das Agenten aus Trainingsdaten am besten kennen
- **JSON-Ausgabe**: Alle Befehle unterstützen `--output json` mit einheitlichem Envelope
- **Docker-Isolation**: Jedes Repository erhält seinen eigenen Daemon und Netzwerk-Namespace
- **Skriptfähig**: `--yes` überspringt Bestätigungen, `--dry-run` zeigt destruktive Operationen in der Vorschau

## Integrationsansätze

### 1. AGENTS.md / CLAUDE.md-Vorlage

Der schnellste Einstieg. Kopieren Sie unsere [AGENTS.md-Vorlage](/de/docs/agents-md-template) in Ihr Projektstammverzeichnis:

- `CLAUDE.md` für Claude Code
- `.cursorrules` für Cursor
- `.windsurfrules` für Windsurf

Einmal eingefügt, verfügt der Agent über die vollständige Befehlsreferenz, den Architekturkontext und die Konventionen, die er braucht, um ohne Raten zu arbeiten.

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

### 3. Agenten-Fähigkeitserkennung

Der `rdc agent`-Unterbefehl bietet strukturierte Introspektion:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema --command "machine query"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## Wichtige Flags für Agenten

| Flag | Zweck |
|------|---------|
| `--output json` / `-o json` | Maschinenlesbare JSON-Ausgabe |
| `--yes` / `-y` | Interaktive Bestätigungen überspringen |
| `--quiet` / `-q` | Informative stderr-Ausgabe unterdrücken |
| `--fields name,status` | Ausgabe auf bestimmte Felder beschränken |
| `--dry-run` | Destruktive Operationen ohne Ausführung in der Vorschau anzeigen |

## Sicherheit und Schutzmaßnahmen

Die CLI behandelt Agenten nicht gleich wie einen Menschen am Terminal. Sensible Operationen erfordern den Nachweis, dass der aktuelle Zustand bekannt ist (das Flag `--current`), interaktive Editor-Abläufe werden standardmäßig abgelehnt, und jede Ablehnung wird im Audit-Log festgehalten. Die Referenz [KI-Agenten: Sicherheit und Schutzmaßnahmen](/de/docs/ai-agents-safety) enthält die vollständige Firewall-Tabelle, das Knowledge-Gate-Modell, die Scope-Überschreibung `REDIACC_ALLOW_CONFIG_EDIT` und das hash-verkettete Audit-Log.

## Nächste Schritte

- [KI-Agenten: Sicherheit und Schutzmaßnahmen](/de/docs/ai-agents-safety), Was Agenten können und nicht können, Knowledge-Gate, Audit-Log
- [Claude Code Einrichtungsanleitung](/de/docs/ai-agents-claude-code), Schritt-für-Schritt Claude Code-Konfiguration
- [Cursor Einrichtungsanleitung](/de/docs/ai-agents-cursor), Cursor-IDE-Integration
- [JSON-Ausgabe-Referenz](/de/docs/ai-agents-json-output), Vollständige JSON-Ausgabe-Dokumentation
- [AGENTS.md-Vorlage](/de/docs/agents-md-template), Kopierfertige Agenten-Konfigurationsvorlage
