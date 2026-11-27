---
title: Claude Code Einrichtungsanleitung
description: >-
  Schritt-für-Schritt-Anleitung zur Konfiguration von Claude Code für die
  autonome Verwaltung der Rediacc-Infrastruktur.
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 31
language: de
sourceHash: "81cd5da23b9747e0"
sourceCommit: "29bdc2aca2ed2b968e47005622ff9cfbbb66e56a"
---

Claude Code funktioniert nativ mit Rediacc über die `rdc` CLI. Diese Anleitung behandelt Einrichtung, Berechtigungen und gängige Workflows.

> **Sicherheit zuerst**: Bevor Sie einen Agent mit irgendetwas verbinden, das Geheimnisse berührt, lesen Sie [KI-Agent-Sicherheit & Schutzmaßnahmen](/de/docs/ai-agents-safety). Claude Code, das unter `rdc` läuft, wird als Agent erkannt. Sensible Mutationen erfordern `--current <previous-value>` (passwd-ähnliche Vorbedingung) für Menschen und Agents gleichermaßen; `--rotate-secret` (bestätigte, protokollierte Rotation) zählt nur für einen Menschen an einem Terminal. `rdc config edit` (interaktiv, `--apply`, `--reveal`) wird ohne Überschreibung verweigert, und Grand-Repositories sowie direktes Maschinen-SSH bleiben geschlossen, solange kein Mensch innerhalb dessen zustimmt, was die Richtlinie erlaubt. Schlägt eine Vorbedingung fehl, nennt das Feld `errors[].next.options[].run` des JSON-Envelopes dem Agent den genauen CLI-Befehl, den er dem Benutzer vorschlagen soll. Geben Sie ihn wortwörtlich weiter.

## Schnellstart

1. Installieren Sie die CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Kopieren Sie die [AGENTS.md-Vorlage](/de/docs/agents-md-template) als `CLAUDE.md` in Ihr Projektstammverzeichnis
3. Starten Sie Claude Code im Projektverzeichnis

Claude Code liest `CLAUDE.md` beim Start und verwendet es als dauerhaften Kontext für alle Interaktionen.

## CLAUDE.md-Konfiguration

Platzieren Sie diese Datei in Ihrem Projektstammverzeichnis. Die vollständige Version finden Sie in der [AGENTS.md-Vorlage](/de/docs/agents-md-template). Wichtige Abschnitte:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine status <machine> -o json
- Deploy: rdc repo up <repo>@<machine> --yes
- Containers: rdc machine status <machine> --containers -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term connect <machine|repo-ref>

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Werkzeugberechtigungen

Claude Code fordert die Erlaubnis zum Ausführen von `rdc`-Befehlen an. Sie können gängige Operationen vorab autorisieren, indem Sie diese zu Ihren Claude Code-Einstellungen hinzufügen:

- Erlauben: `rdc machine status *`, Statusabfragen (nur Lesen)
- Erlauben: `rdc machine status * --containers`, Container-Auflistung
- Erlauben: `rdc machine health *`, Gesundheitsprüfungen
- Erlauben: `rdc repo list`, Repository-Auflistung

Für destruktive Operationen (`rdc repo up`, `rdc repo delete`) fragt Claude Code immer nach Bestätigung, es sei denn, Sie autorisieren diese ausdrücklich.

## Beispiel-Workflows

### Infrastrukturstatus prüfen

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine status prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### Ein Repository bereitstellen

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail@prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail@prod-1 --yes
→ Deploys the repository
```

### Container-Probleme diagnostizieren

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine status prod-1 --containers -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc repo logs nextcloud@prod-1 -c nextcloud-app --lines 50
→ Checks recent logs
```

### Dateisynchronisation

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config
→ Syncs the files
```

## Tipps

- Claude Code erkennt automatisch non-TTY-Umgebungen und wechselt zu JSON-Ausgabe, in den meisten Fällen ist `-o json` nicht nötig
- Verwenden Sie `rdc --help-all`, damit Claude Code alle verfügbaren Befehle entdecken kann
- Das `--fields`-Flag hilft, den Kontextfenster-Verbrauch zu reduzieren, wenn Sie nur bestimmte Daten benötigen
