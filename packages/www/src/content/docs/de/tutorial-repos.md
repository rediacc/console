---
title: "Repository-Lebenszyklus"
description: "Ein verschlüsseltes Repository erstellen, eine containerisierte Anwendung bereitstellen, Container inspizieren und aufräumen."
category: "Tutorials"
order: 3
language: de
sourceHash: "0c4edddefa30df1c"
---

# So stellen Sie Repositories mit Rediacc bereit und verwalten sie

Repositories sind die zentrale Bereitstellungseinheit in Rediacc — jedes ist eine isolierte, verschlüsselte Umgebung mit eigenem Docker Daemon und dediziertem Speicher. In diesem Tutorial erstellen Sie ein verschlüsseltes Repository, stellen eine containerisierte Anwendung bereit, inspizieren laufende Container und räumen auf. Am Ende haben Sie einen vollständigen Bereitstellungszyklus abgeschlossen.

## Voraussetzungen

- Die `rdc` CLI installiert mit einer initialisierten Konfiguration
- Eine bereitgestellte Maschine (siehe [Tutorial: Maschineneinrichtung](/de/docs/tutorial-setup))
- Eine einfache Anwendung mit einem `Rediaccfile` und einer `docker-compose.yml`

## Interaktive Aufzeichnung

![Tutorial: Repository-Lebenszyklus](/assets/tutorials/repos-tutorial.cast)

### Schritt 1: Verschlüsseltes Repository erstellen

Jedes Repository erhält sein eigenes LUKS-verschlüsseltes Speichervolumen. Geben Sie die Maschine und die Speichergröße an.

```bash
rdc repo create test-app -m server-1 --size 2G
```

Rediacc erstellt ein 2 GB verschlüsseltes Volumen, formatiert es und mountet es automatisch. Das Repository ist bereit für Datei-Uploads.

### Schritt 2: Repositories auflisten

Bestätigen Sie, dass das neue Repository verfügbar ist.

```bash
rdc repo list -m server-1
```

Zeigt alle Repositories auf der Maschine mit ihrer Größe, Mount-Status und Verschlüsselungsstatus.

### Schritt 3: Mount-Pfad inspizieren

Überprüfen Sie vor der Bereitstellung, ob der Speicher des Repositories gemountet und zugänglich ist.

```bash
rdc term server-1 -c "ls -la /mnt/rediacc/mounts/test-app/"
```

Das Mount-Verzeichnis ist der Ort, an dem sich die Anwendungsdateien befinden — `Rediaccfile`, `docker-compose.yml` und alle Datenvolumen.

### Schritt 4: Dienste starten

Stellen Sie die Anwendung bereit, indem Sie das Repository mounten und seine Docker-Dienste starten.

```bash
rdc repo up test-app -m server-1 --mount
```

Dies mountet das Repository (falls nicht bereits gemountet), startet einen isolierten Docker Daemon und startet Dienste über `up()`.

> **Hinweis:** Die erste Bereitstellung dauert länger, da Docker-Images heruntergeladen werden. Nachfolgende Starts verwenden zwischengespeicherte Images.

### Schritt 5: Laufende Container anzeigen

```bash
rdc machine containers server-1
```

Zeigt alle laufenden Container über alle Repositories auf der Maschine, einschließlich CPU- und Speichernutzung.

### Schritt 6: Auf das Repository-Terminal zugreifen

Um Befehle in der isolierten Docker-Umgebung des Repositories auszuführen:

```bash
rdc term server-1 test-app -c "docker ps"
```

Die Terminal-Sitzung setzt `DOCKER_HOST` auf den isolierten Docker-Socket des Repositories. Jeder Docker-Befehl wird nur gegen die Container dieses Repositories ausgeführt.

### Schritt 7: Stoppen und aufräumen

Wenn Sie fertig sind, stoppen Sie die Dienste, schließen Sie das verschlüsselte Volumen und löschen Sie optional das Repository.

```bash
rdc repo down test-app -m server-1      # Dienste stoppen
rdc repo unmount test-app -m server-1   # Verschlüsseltes Volumen schließen
rdc repo delete test-app -m server-1    # Repository dauerhaft löschen
```

`down` stoppt Container und den Docker Daemon. `unmount` schließt das LUKS-Volumen. `delete` entfernt das Repository und seinen verschlüsselten Speicher dauerhaft.

> **Warnung:** `repo delete` ist unwiderruflich. Alle Daten im Repository werden zerstört. Erstellen Sie bei Bedarf vorher ein Backup.

## Fehlerbehebung

**„Unzureichender Speicherplatz" bei der Repository-Erstellung**
Das verschlüsselte Volumen benötigt zusammenhängenden freien Speicherplatz auf dem Host. Überprüfen Sie den verfügbaren Speicherplatz mit `df -h` auf dem Server. Erwägen Sie einen kleineren `--size`-Wert oder geben Sie Speicherplatz frei.

**Docker-Image-Pull-Timeout während `repo up`**
Große Images können bei langsamen Verbindungen das Zeitlimit überschreiten. Wiederholen Sie mit `rdc repo up` — es setzt dort fort, wo es aufgehört hat. Für Air-Gapped-Umgebungen laden Sie Images vorab in den Docker Daemon des Repositories.

**„Mount fehlgeschlagen" oder „LUKS-Öffnung fehlgeschlagen"**
Die LUKS-Passphrase wird aus der Konfiguration abgeleitet. Überprüfen Sie, dass Sie dieselbe Konfiguration verwenden, mit der das Repository erstellt wurde. Wenn das Volumen bereits von einem anderen Prozess gemountet ist, unmounten Sie es zuerst.

## Nächste Schritte

Sie haben ein verschlüsseltes Repository erstellt, eine Anwendung bereitgestellt, Container inspiziert und aufgeräumt. Um Ihre Bereitstellungen zu überwachen:

- [Dienste](/de/docs/services) — Rediaccfile-Referenz, Service-Netzwerke, Autostart und Multi-Service-Layouts
- [Tutorial: Überwachung & Diagnose](/de/docs/tutorial-monitoring) — Gesundheitsprüfungen, Container-Inspektion und Diagnose
- [Tools](/de/docs/tools) — Terminal, Dateisynchronisierung und VS Code-Integration
