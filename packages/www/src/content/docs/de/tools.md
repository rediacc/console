---
title: Werkzeuge
description: Dateisynchronisation, Terminalzugriff, VS Code-Unterstützung und CLI-Updates.
category: Guides
order: 9
language: de
sourceHash: "59abc2faa1157369"
sourceCommit: "3fb35b9a33c7e8ec6753ecd56231f2018e8f4803"
---

# Werkzeuge

Rediacc bündelt vier Werkzeuge für die tägliche Arbeit an Ihren Maschinen und Repositories: Dateisynchronisation über SSH, ein SSH-Terminal, VS Code-Integration und CLI-Updates. Alle vier Tools arbeiten über SSH. Auf der Fernseite ist kein Agent oder Daemon erforderlich. Wenn Sie für diese Aufgaben ein GUI benötigen, sind Sie auf dieser Seite falsch.

## Dateisynchronisation (sync)

Übertragen Sie Dateien zwischen Ihrer Workstation und einem entfernten Repository mittels rsync über SSH.

### Dateien hochladen

`--local` akzeptiert einen oder mehrere Pfade. Jeder Pfad kann eine Datei oder ein Verzeichnis sein. Dateien landen bei `<remote>/<basename>`; Verzeichnisinhalte werden in `<remote>/` zusammengeführt. Für eine einzelne Datei verwenden Sie vorzugsweise `--remote-file`, um dem Ziel explizit den Dateipfad zu geben.

```bash
# Verzeichnis (Inhalt in Fernverzeichnis zusammengeführt)
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src

# Einzelne Datei in ein Fernverzeichnis (Basename erhalten)
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote /app/conf

# Einzelne Datei mit explizitem Zielpfad
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote-file /app/conf/config.yml

# Mehrere Quellen in einem Aufruf
rdc repo sync upload -m server-1 -r my-app --local a.yml b.yml ./assets --remote /app
```

`--remote` und `--remote-file` schließen sich gegenseitig aus. `--remote-file` erfordert genau einen `--local`-Pfad, der auf eine Datei zeigt.

`--mirror` kann nicht mit einer Dateiquelle kombiniert werden; es würde Nachbardateien im Fernverzeichnis löschen.

### Dateien herunterladen

Verwenden Sie `--remote` für ein Verzeichnis (Standard) oder `--remote-file` für eine einzelne Datei. Die beiden Flags schließen sich gegenseitig aus.

```bash
# Verzeichnis
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data

# Einzelne Datei - --local muss ein vorhandenes Verzeichnis sein
rdc repo sync download -m server-1 -r my-app --remote-file /app/conf/config.yml --local ./local-conf
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
| `--remote-file <path>` | Entfernter Dateipfad für einzelne Datei-Uploads oder Downloads (Alternative zu `--remote`) |
| `--dry-run` | Änderungen anzeigen, ohne zu übertragen |
| `--mirror` | Quelle auf Ziel spiegeln, zusätzliche Dateien löschen (nur Verzeichnisquellen) |
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

Oder verwenden Sie den `connect`-Unterbefehl mit demselben Ergebnis und expliziten Flags:

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

### VS Code im Browser

Kein lokales VS Code? Starten Sie den Editor direkt aus der Repository-Sandbox und öffnen Sie ihn in jedem Browser:

```bash
rdc vscode connect -r my-app -m server-1 --browser
```

Dieser Befehl:
1. Installiert den Open-Source-Editor-Server einmalig auf der Maschine (schreibgeschützter gemeinsamer Pfad, mit Prüfsummenverifikation)
2. Startet ihn innerhalb der Repository-Sandbox, sodass der Dateibaum, das integrierte Terminal und alle untergeordneten Prozesse genau das sehen, was das Repository sieht
3. Öffnet einen SSH-Tunnel zu einem lokalen Port und startet Ihren Browser mit einer sitzungsbezogenen Token-URL

Der Server läuft weiter, nachdem Sie den Tunnel schließen; beim erneuten Verbinden wird er wiederverwendet. Verwalten Sie ihn mit:

```bash
rdc vscode serve status -r my-app -m server-1
rdc vscode serve stop -r my-app -m server-1
```

| Option | Beschreibung |
|--------|-------------|
| `--no-open` | URL ausgeben statt Browser zu starten |
| `--url-only` | Genau eine URL-Zeile auf stdout ausgeben (für Scripting) und den Tunnel halten |
| `--local <port>` | Lokalen Tunnel-Port festlegen |
| `--server-provider <id>` | Editor-Server-Implementierung: `openvscode` (Standard) oder `code-server` |
| `--server-archive <file>` | Aus einem vorbereiteten Tarball auf der Maschine installieren (kein Internet erforderlich) |

Funktioniert unter Linux, macOS, Windows oder auf einem Tablet. Lokal wird nur ein Browser benötigt.

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

#### Release-Kanäle

```bash
rdc update --channel edge      # Kontinuierlich bereitgestellte Produktions-Updates
rdc update --channel stable    # Nach 7-tägiger Erprobung von edge befördert (Standard)
rdc update --status            # Zeigt aktuellen Kanal und Versionsinformationen an
```
