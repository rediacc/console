---
title: Cursor Einrichtungsanleitung
description: Konfiguration der Cursor-IDE für die Arbeit mit der Rediacc-Infrastruktur über .cursorrules und Terminal-Integration.
category: Guides
order: 32
language: de
---

Cursor integriert sich mit Rediacc über Terminal-Befehle und die Konfigurationsdatei `.cursorrules`.

## Schnellstart

1. Installieren Sie die CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Kopieren Sie die [AGENTS.md-Vorlage](/de/docs/agents-md-template) als `.cursorrules` in Ihr Projektstammverzeichnis
3. Oeffnen Sie das Projekt in Cursor

Cursor liest `.cursorrules` beim Start und verwendet es als Kontext für die KI-gestuetzte Entwicklung.

## .cursorrules-Konfiguration

Erstellen Sie `.cursorrules` in Ihrem Projektstammverzeichnis mit dem Rediacc-Infrastrukturkontext. Die vollstaendige Version finden Sie in der [AGENTS.md-Vorlage](/de/docs/agents-md-template).

Die wichtigsten Abschnitte, die enthalten sein sollten:

- CLI-Tool-Name (`rdc`) und Installation
- Gaengige Befehle mit dem `--output json`-Flag
- Architekturübersicht (Repository-Isolation, Docker Daemons)
- Terminologieregeln (Adapter, nicht Modi)

## Terminal-Integration

Cursor kann `rdc`-Befehle über sein integriertes Terminal ausführen. Gaengige Muster:

### Status pruefen

Fragen Sie Cursor: *"Pruefe den Status meines Produktionsservers"*

Cursor fuehrt im Terminal aus:
```bash
rdc machine info prod-1 -o json
```

### Aenderungen bereitstellen

Fragen Sie Cursor: *"Stelle die aktualisierte nextcloud-Konfiguration bereit"*

Cursor fuehrt im Terminal aus:
```bash
rdc repo up nextcloud -m prod-1 --yes
```

### Logs anzeigen

Fragen Sie Cursor: *"Zeige mir die letzten mail-Container-Logs"*

Cursor fuehrt im Terminal aus:
```bash
rdc term prod-1 mail -c "docker logs mail-postfix --tail 100"
```

## Arbeitsbereichseinstellungen

Fuer Teamprojekte fuegen Sie Rediacc-spezifische Cursor-Einstellungen zu `.cursor/settings.json` hinzu:

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## Tipps

- Cursors Composer-Modus eignet sich gut für mehrstufige Infrastrukturaufgaben
- Verwenden Sie `@terminal` im Cursor-Chat, um auf aktuelle Terminal-Ausgaben zu verweisen
- Der Befehl `rdc agent capabilities` gibt Cursor eine vollstaendige Befehlsreferenz
- Kombinieren Sie `.cursorrules` mit einer `CLAUDE.md`-Datei für maximale Kompatibilitaet über KI-Tools hinweg
