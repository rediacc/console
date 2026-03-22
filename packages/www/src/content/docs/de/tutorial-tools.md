---
title: "Werkzeuge für den Alltag"
description: "Nutzen Sie SSH-Terminalzugriff, Dateisynchronisation, VS Code-Integration und CLI-Aktualisierungsbefehle für Ihre Infrastruktur."
category: "Tutorials"
order: 5
language: de
sourceHash: "9391a34dfb244942"
---

# So verwenden Sie Terminal-, Sync- und VS Code-Werkzeuge mit Rediacc

Das CLI enthält Produktivitätswerkzeuge für den täglichen Betrieb: SSH-Terminalzugriff, Dateisynchronisation über rsync, VS Code-Remote-Entwicklung und CLI-Updates. In diesem Tutorial führen Sie Remote-Befehle aus, synchronisieren Dateien mit einem Repository, prüfen die VS Code-Integration und überprüfen Ihre CLI-Version.

## Voraussetzungen

- Die `rdc` CLI installiert mit einer initialisierten Konfiguration
- Eine bereitgestellte Maschine mit einem laufenden Repository (siehe [Tutorial: Repository-Lebenszyklus](/de/docs/tutorial-repos))

## Interaktive Aufzeichnung

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

### Schritt 1: Mit einer Maschine verbinden

Führen Sie Inline-Befehle auf einer Remote-Maschine über SSH aus, ohne eine interaktive Sitzung zu öffnen.

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

Das `-c`-Flag führt einen einzelnen Befehl aus und gibt die Ausgabe zurück. Lassen Sie `-c` weg, um eine interaktive SSH-Sitzung zu öffnen.

### Schritt 2: Mit einem Repository verbinden

Um Befehle in der isolierten Docker-Umgebung eines Repositories auszuführen:

```bash
rdc term server-1 my-app -c "docker ps"
```

Beim Verbinden mit einem Repository wird `DOCKER_HOST` automatisch auf den isolierten Docker-Socket des Repositories gesetzt. Jeder Docker-Befehl wird nur gegen die Container dieses Repositories ausgeführt.

### Schritt 3: Dateisynchronisation vorschauen (Probelauf)

Bevor Sie Dateien übertragen, schauen Sie sich an, was sich ändern würde.

```bash
rdc repo sync upload -m server-1 -r my-app --local ./src --dry-run
```

Das `--dry-run`-Flag zeigt neue Dateien, geänderte Dateien und die gesamte Übertragungsgröße an, ohne tatsächlich etwas hochzuladen.

### Schritt 4: Dateien hochladen

Übertragen Sie Dateien von Ihrem lokalen Rechner zum Remote-Repository-Mount.

```bash
rdc repo sync upload -m server-1 -r my-app --local ./src
```

Dateien werden über rsync via SSH übertragen. Bei nachfolgenden Uploads werden nur geänderte Dateien gesendet.

### Schritt 5: Hochgeladene Dateien überprüfen

Bestätigen Sie die Ankunft der Dateien, indem Sie das Mount-Verzeichnis des Repositories auflisten.

```bash
rdc term server-1 my-app -c "ls -la"
```

### Schritt 6: VS Code-Integrationsprüfung

Um remote mit VS Code zu entwickeln, überprüfen Sie, ob die erforderlichen Komponenten installiert sind.

```bash
rdc vscode check
```

Prüft Ihre VS Code-Installation, die Remote SSH-Erweiterung und die SSH-Konfiguration. Folgen Sie der Ausgabe, um fehlende Voraussetzungen zu beheben, und verbinden Sie sich dann mit `rdc vscode <machine> [repo]`.

### Schritt 7: Nach CLI-Updates suchen

```bash
rdc update --check-only
```

Meldet, ob eine neuere Version des CLI verfügbar ist. Um das Update zu installieren, führen Sie `rdc update` ohne `--check-only` aus.

## Fehlerbehebung

**"rsync: command not found" bei der Dateisynchronisation**
Installieren Sie rsync sowohl auf Ihrem lokalen Rechner als auch auf dem Remote-Server. Auf Debian/Ubuntu: `sudo apt install rsync`. Auf macOS: rsync ist standardmäßig enthalten.

**"Permission denied" beim Sync-Upload**
Überprüfen Sie, ob Ihr SSH-Benutzer Schreibzugriff auf das Mount-Verzeichnis des Repositories hat. Repository-Mounts gehören dem Benutzer, der bei der Maschinenregistrierung angegeben wurde.

**"VS Code Remote SSH extension not found"**
Installieren Sie die Erweiterung aus dem VS Code Marketplace: Suchen Sie nach "Remote - SSH" von Microsoft. Nach der Installation starten Sie VS Code neu und führen `rdc vscode check` erneut aus.

## Nächste Schritte

Sie haben Remote-Befehle ausgeführt, Dateien synchronisiert, die VS Code-Integration geprüft und CLI-Updates überprüft. Um Ihre Daten zu schützen:

- [Tools](/de/docs/tools) — vollständige Referenz für Terminal-, Sync-, VS Code- und Update-Befehle
- [Tutorial: Backup & Netzwerk](/de/docs/tutorial-backup) — Backup-Planung und Netzwerkkonfiguration
- [Services](/de/docs/services) — Rediaccfile-Referenz und Service-Netzwerke
