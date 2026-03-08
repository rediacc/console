---
title: Claude Code Einrichtungsanleitung
description: Schritt-für-Schritt-Anleitung zur Konfiguration von Claude Code für die autonome Verwaltung der Rediacc-Infrastruktur.
category: Guides
order: 31
language: de
sourceHash: "90eb12eaaf6806c9"
---

Claude Code funktioniert nativ mit Rediacc über die `rdc` CLI. Diese Anleitung behandelt Einrichtung, Berechtigungen und gaengige Workflows.

## Schnellstart

1. Installieren Sie die CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Kopieren Sie die [AGENTS.md-Vorlage](/de/docs/agents-md-template) als `CLAUDE.md` in Ihr Projektstammverzeichnis
3. Starten Sie Claude Code im Projektverzeichnis

Claude Code liest `CLAUDE.md` beim Start und verwendet es als dauerhaften Kontext für alle Interaktionen.

## CLAUDE.md-Konfiguration

Platzieren Sie diese Datei in Ihrem Projektstammverzeichnis. Die vollstaendige Version finden Sie in der [AGENTS.md-Vorlage](/de/docs/agents-md-template). Wichtige Abschnitte:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine info <machine> -o json
- Deploy: rdc repo up <repo> -m <machine> --yes
- Containers: rdc machine containers <machine> -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term <machine> [repo]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Werkzeugberechtigungen

Claude Code fordert die Erlaubnis zum Ausführen von `rdc`-Befehlen an. Sie können gaengige Operationen vorab autorisieren, indem Sie diese zu Ihren Claude Code-Einstellungen hinzufügen:

- Erlauben: `rdc machine info *` — Statusabfragen (nur Lesen)
- Erlauben: `rdc machine containers *` — Container-Auflistung
- Erlauben: `rdc machine health *` — Gesundheitspruefungen
- Erlauben: `rdc config repositories` — Repository-Auflistung

Fuer destruktive Operationen (`rdc repo up`, `rdc repo delete`) fragt Claude Code immer nach Bestaetigung, es sei denn, Sie autorisieren diese ausdruecklich.

## Beispiel-Workflows

### Infrastrukturstatus pruefen

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine info prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### Ein Repository bereitstellen

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail -m prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail -m prod-1 --yes
→ Deploys the repository
```

### Container-Probleme diagnostizieren

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine containers prod-1 -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc term prod-1 -c "docker logs nextcloud-app --tail 50"
→ Checks recent logs
```

### Dateisynchronisation

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc sync upload -m prod-1 -r mail -l ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc sync upload -m prod-1 -r mail -l ./config
→ Syncs the files
```

## Tipps

- Claude Code erkennt automatisch non-TTY-Umgebungen und wechselt zu JSON-Ausgabe — in den meisten Faellen ist `-o json` nicht noetig
- Verwenden Sie `rdc agent capabilities`, damit Claude Code alle verfügbaren Befehle entdecken kann
- Verwenden Sie `rdc agent schema "command name"` für detaillierte Argument-/Optionsinformationen
- Das `--fields`-Flag hilft, den Kontextfenster-Verbrauch zu reduzieren, wenn Sie nur bestimmte Daten benoetigen
