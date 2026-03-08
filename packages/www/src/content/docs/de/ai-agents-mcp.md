---
title: MCP-Server-Einrichtung
description: Verknüpfen Sie KI-Agenten über den Model Context Protocol (MCP) Server mit Ihrer Rediacc-Infrastruktur.
category: Guides
order: 33
language: de
sourceHash: "1b6cd5ba5d8d0ffe"
---

## Überblick

Der Befehl `rdc mcp serve` startet einen lokalen MCP-Server (Model Context Protocol), den KI-Agenten zur Verwaltung Ihrer Infrastruktur nutzen können. Der Server verwendet stdio-Transport — der KI-Agent startet ihn als Unterprozess und kommuniziert über JSON-RPC.

**Voraussetzungen:** `rdc` installiert und mit mindestens einer Maschine konfiguriert.

## Claude Code

Fügen Sie Folgendes zur `.mcp.json` Ihres Projekts hinzu:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

Oder mit einer benannten Konfiguration:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

Öffnen Sie Einstellungen → MCP Servers → Server hinzufügen:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

## Verfügbare Tools

### Lese-Tools (sicher, keine Seiteneffekte)

| Tool | Beschreibung |
|------|-------------|
| `machine_info` | Systeminformationen, Container, Dienste und Ressourcennutzung abrufen |
| `machine_containers` | Docker-Container auflisten, die auf einer Maschine laufen |
| `machine_services` | systemd-Dienste auf einer Maschine auflisten |
| `machine_repos` | Bereitgestellte Repositories auf einer Maschine auflisten |
| `machine_health` | Gesundheitscheck durchführen (System, Container, Dienste, Speicher) |
| `config_repositories` | Konfigurierte Repositories mit Name-zu-GUID-Zuordnungen auflisten |
| `agent_capabilities` | Alle verfügbaren rdc-CLI-Befehle auflisten |

### Schreib-Tools (destruktiv)

| Tool | Beschreibung |
|------|-------------|
| `repo_up` | Ein Repository auf einer Maschine bereitstellen/aktualisieren |
| `repo_down` | Ein Repository auf einer Maschine stoppen |
| `term_exec` | Einen Befehl auf einer entfernten Maschine über SSH ausführen |

## Beispiel-Workflows

**Maschinenstatus prüfen:**
> „Wie ist der Status meiner Produktionsmaschine?"

Der Agent ruft `machine_info` auf → gibt Systeminformationen, laufende Container, Dienste und Ressourcennutzung zurück.

**Eine Anwendung bereitstellen:**
> „Stelle GitLab auf meiner Staging-Maschine bereit"

Der Agent ruft `repo_up` mit `name: "gitlab"` und `machine: "staging"` auf → stellt das Repository bereit, gibt Erfolg/Fehler zurück.

**Einen fehlerhaften Dienst debuggen:**
> „Mein Nextcloud ist langsam, finde heraus, was los ist"

Der Agent ruft `machine_health` → `machine_containers` → `term_exec` auf, um Logs zu lesen → identifiziert das Problem und schlägt eine Lösung vor.

## Konfigurationsoptionen

| Option | Standard | Beschreibung |
|--------|---------|-------------|
| `--config <name>` | (Standardkonfiguration) | Benannte Konfiguration für alle Befehle |
| `--timeout <ms>` | `120000` | Standard-Befehls-Timeout in Millisekunden |

## Architektur

Der MCP-Server ist zustandslos. Jeder Tool-Aufruf startet `rdc` als isolierten Kindprozess mit den Flags `--output json --yes --quiet`. Das bedeutet:

- Kein Zustandsüberlauf zwischen Tool-Aufrufen
- Verwendet Ihre bestehende `rdc`-Konfiguration und SSH-Schlüssel
- Funktioniert sowohl mit dem lokalen als auch dem Cloud-Adapter
- Fehler in einem Befehl beeinflussen andere nicht
