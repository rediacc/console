---
title: Werkzeuge
description: 'Dateisynchronisation, Terminalzugriff, VS Code-Unterstützung und CLI-Updates.'
category: Guides
order: 9
language: de
sourceHash: "f350872720c99d58"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Werkzeuge

Rediacc bündelt Werkzeuge für die Arbeit mit entfernten Repositories: Dateisynchronisation, SSH-Terminal, VS Code-Integration und CLI-Updates.

## Dateisynchronisation (sync)

Übertragen Sie Dateien zwischen Ihrer Workstation und einem entfernten Repository mittels rsync über SSH.

### Dateien hochladen

```bash
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src
```

### Dateien herunterladen

Verwenden Sie `--remote` für ein Verzeichnis (Standard) oder `--remote-file` für eine einzelne Datei. Die beiden Flags schließen sich gegenseitig aus.

```bash
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data
```

### Synchronisierungsstatus prüfen

```bash
rdc repo sync status -m server-1 -r my-app
```

### Optionen

| Option | Beschreibung |
|--------|-------------|
| `-m, --machine <name>` | Zielmaschine |
| `-r, --repository <name>` | Ziel-Repository |
| `--local <paths...>` | Ein oder mehrere lokale Datei-/Verzeichnispfade (Upload) oder lokales Zielverzeichnis (Download) |
| `--remote <path>` | Entferntes Verzeichnis (relativ zum Repository-Einbindungspunkt) |
| `--remote-file <path>` | Einzelne entfernte Datei (nur Download, Alternative zu `--remote`) |
| `--dry-run` | Änderungen anzeigen, ohne zu übertragen |
| `--mirror` | Quelle auf Ziel spiegeln (zusätzliche Dateien löschen) |
| `--verify` | Prüfsummen nach der Übertragung verifizieren |
| `--confirm` | Interaktive Bestätigung mit Detailansicht |
| `--exclude <patterns...>` | Dateimuster ausschließen |
| `--skip-router-restart` | Neustart des Route-Servers nach der Operation überspringen |

## SSH-Terminal (term)

Öffnen Sie eine interaktive SSH-Sitzung zu einer Maschine oder in die Umgebung eines Repositories.

### Kurzschreibweise

Der schnellste Weg, sich zu verbinden:

```bash
rdc term connect -m server-1                    # Mit einer Maschine verbinden
rdc term connect -m server-1 -r my-app             # Mit einem Repository verbinden
```

### Befehl ausführen

Führen Sie einen Befehl aus, ohne eine interaktive Sitzung zu öffnen:

```bash
rdc term connect -m server-1 -c "uptime"
rdc term connect -m server-1 -r my-app -c "docker ps"
```

Bei der Verbindung zu einem Repository wird `DOCKER_HOST` automatisch auf den isolierten Docker-Socket des Repositories gesetzt, sodass `docker ps` nur die Container dieses Repositories anzeigt.

### Connect-Unterbefehl

Der `connect`-Unterbefehl macht dasselbe mit expliziten Flags:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### Container-Aktionen

Interagieren Sie direkt mit einem laufenden Container:

```bash
# Eine Shell im Container öffnen
rdc term connect -m server-1 -r my-app --container <container-id>

# Container-Logs anzeigen
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs

# Logs in Echtzeit verfolgen
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs --follow

# Container-Statistiken anzeigen
rdc term connect -m server-1 -r my-app --container <container-id> --container-action stats

# Einen Befehl im Container ausführen
rdc term connect -m server-1 -r my-app --container <container-id> --container-action exec -c "ls -la"
```

| Option | Beschreibung |
|--------|-------------|
| `--container <id>` | Ziel-Docker-Container-ID |
| `--container-action <action>` | Aktion: `terminal` (Standard), `logs`, `stats`, `exec` |
| `--log-lines <n>` | Anzahl der anzuzeigenden Log-Zeilen (Standard: 50) |
| `--follow` | Logs kontinuierlich verfolgen |
| `--external` | Externes Terminal anstelle von Inline-SSH verwenden |

## VS Code-Integration (vscode)

Öffnen Sie eine Remote-SSH-Sitzung in VS Code, vorkonfiguriert mit den korrekten SSH-Einstellungen.

### Mit einem Repository verbinden

```bash
rdc vscode connect -r my-app -m server-1
```

Dieser Befehl:
1. Erkennt Ihre VS Code-Installation
2. Konfiguriert die SSH-Verbindung in `~/.ssh/config`
3. Speichert den SSH-Schlüssel für die Sitzung
4. Öffnet VS Code mit einer Remote-SSH-Verbindung zum Repository-Pfad

### Konfigurierte Verbindungen auflisten

```bash
rdc vscode list
```

### Verbindungen bereinigen

```bash
rdc vscode cleanup
```

Entfernt VS Code SSH-Konfigurationen, die nicht mehr benötigt werden.

### Konfiguration überprüfen

```bash
rdc vscode check
```

Überprüft die VS Code-Installation, die Remote-SSH-Erweiterung und aktive Verbindungen.

> **Voraussetzung:** Installieren Sie die [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh)-Erweiterung in VS Code.

## CLI-Updates (update)

Halten Sie die `rdc`-CLI auf dem neuesten Stand.

### Nach Updates suchen

```bash
rdc update --check-only
```

### Update anwenden

```bash
rdc update
```

Updates werden heruntergeladen und direkt angewendet. Die CLI wählt automatisch die richtige Binary für Ihre Plattform (Linux, macOS oder Windows). Die neue Version wird beim nächsten Start wirksam.

### Zurücksetzen

```bash
rdc update --rollback
```

Setzt auf die zuvor installierte Version zurück. Nur verfügbar, nachdem ein Update angewendet wurde.

### Update-Status

```bash
rdc update --status
```

Zeigt die aktuelle Version, den Update-Kanal und die Auto-Update-Konfiguration an.

#### Release-Kanale

```bash
rdc update --channel edge      # Neueste Funktionen, haufig aktualisiert
rdc update --channel stable    # Produktionsreife Versionen (Standard)
rdc update --status            # Aktuellen Kanal und Versionsinformationen anzeigen
```
