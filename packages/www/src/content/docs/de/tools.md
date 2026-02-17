---
title: "Werkzeuge"
description: "Dateisynchronisation, Terminalzugriff, VS Code-Integration, Updates und Diagnose."
category: "Guides"
order: 4
language: de
---

# Werkzeuge

Rediacc enthält mehrere Produktivitätswerkzeuge für die Arbeit mit entfernten Repositories. Diese Werkzeuge bauen auf der SSH-Verbindung auf, die durch Ihre Kontext-Konfiguration hergestellt wird.

## Dateisynchronisation (sync)

Übertragen Sie Dateien zwischen Ihrer Workstation und einem entfernten Repository mittels rsync über SSH.

### Dateien hochladen

```bash
rdc sync upload my-app -m server-1 --local ./src --remote /app/src
```

### Dateien herunterladen

```bash
rdc sync download my-app -m server-1 --remote /app/data --local ./data
```

### Optionen

| Option | Beschreibung |
|--------|-------------|
| `-m, --machine <name>` | Zielmaschine |
| `--local <path>` | Lokaler Verzeichnispfad |
| `--remote <path>` | Entfernter Pfad (relativ zum Repository-Einbindungspunkt) |
| `--dry-run` | Änderungen vorschauen, ohne zu übertragen |
| `--delete` | Dateien am Ziel löschen, die an der Quelle nicht vorhanden sind |

Das `--dry-run`-Flag ist nützlich, um vor der Synchronisation eine Vorschau der zu übertragenden Dateien zu erhalten.

## SSH-Terminal (term)

Öffnen Sie eine interaktive SSH-Sitzung zu einer Maschine oder direkt in den Einbindungspfad eines Repositories.

### Mit einer Maschine verbinden

```bash
rdc term connect server-1
```

### Mit einem Repository verbinden

```bash
rdc term connect my-app -m server-1
```

Bei der Verbindung zu einem Repository startet die Terminal-Sitzung im Einbindungsverzeichnis des Repositories mit dem konfigurierten Docker-Socket des Repositories.

## VS Code-Integration (vscode)

Öffnen Sie eine Remote-SSH-Sitzung in VS Code, vorkonfiguriert mit den richtigen SSH-Einstellungen und der Remote-SSH-Erweiterung.

### Mit einem Repository verbinden

```bash
rdc vscode connect my-app -m server-1
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

Zeigt alle SSH-Verbindungen an, die für VS Code konfiguriert wurden.

### Verbindungen bereinigen

```bash
rdc vscode clean
```

Entfernt VS Code-SSH-Konfigurationen, die nicht mehr benötigt werden.

> **Voraussetzung:** Installieren Sie die [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh)-Erweiterung in VS Code.

## CLI-Updates (update)

Halten Sie die `rdc`-CLI mit den neuesten Funktionen und Fehlerbehebungen auf dem aktuellen Stand.

### Nach Updates suchen

```bash
rdc update --check-only
```

### Update anwenden

```bash
rdc update
```

Updates werden heruntergeladen und direkt angewendet. Die neue Version wird beim nächsten Start wirksam.

### Zurücksetzen

```bash
rdc update rollback
```

Setzt auf die zuvor installierte Version zurück. Nur nach einem angewendeten Update verfügbar.

### Auto-Update-Status

```bash
rdc update status
```

Zeigt die aktuelle Version, den Update-Kanal und die Auto-Update-Konfiguration an.

## Systemdiagnose (doctor)

Führen Sie eine umfassende Diagnoseprüfung Ihrer Rediacc-Umgebung durch.

```bash
rdc doctor
```

Der Doctor-Befehl prüft:

| Kategorie | Prüfungen |
|-----------|-----------|
| **Umgebung** | Node.js-Version, CLI-Version, SEA-Modus |
| **Renet** | Vorhandensein der Binary, Version, eingebettetes CRIU und rsync |
| **Konfiguration** | Aktiver Kontext, Modus, Maschinen, SSH-Schlüssel |
| **Authentifizierung** | Anmeldestatus |

Jede Prüfung meldet **OK**, **Warnung** oder **Fehler** mit einer kurzen Erklärung. Verwenden Sie dies als ersten Schritt bei der Behebung von Problemen.
