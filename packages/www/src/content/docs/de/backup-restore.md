---
title: Backup & Wiederherstellung
description: >-
  Verschlüsselte Repositories auf externem Speicher sichern, aus Backups
  wiederherstellen und automatische Backups planen.
category: Guides
order: 7
language: de
sourceHash: "2ac1e17539336175"
---

# Backup & Wiederherstellung

Rediacc kann verschlüsselte Repositories auf externen Speicheranbietern sichern und sie auf derselben oder einer anderen Maschine wiederherstellen. Backups sind verschlüsselt -- das LUKS-Credential des Repositories wird zur Wiederherstellung benötigt.

## Speicher konfigurieren

Bevor Sie Backups übertragen, registrieren Sie einen Speicheranbieter. Rediacc unterstützt jeden rclone-kompatiblen Speicher: S3, B2, Google Drive und viele mehr.

### Aus rclone importieren

Wenn Sie bereits ein rclone-Remote konfiguriert haben:

```bash
rdc config storage import rclone.conf
```

Dies importiert Speicherkonfigurationen aus einer rclone-Konfigurationsdatei in die aktuelle Konfiguration. Unterstützte Typen: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob und Swift.

### Speicher anzeigen

```bash
rdc config storage list
```

## Ein Backup erstellen

Ein Repository-Backup auf externen Speicher übertragen:

```bash
rdc repo push my-app -m server-1 --to my-storage
```

| Option | Beschreibung |
|--------|-------------|
| `--to <storage>` | Ziel-Speicherort |
| `--to-machine <machine>` | Zielmaschine für Maschine-zu-Maschine-Backup |
| `--dest <filename>` | Benutzerdefinierter Zieldateiname |
| `--checkpoint` | Einen Checkpoint vor dem Übertragen erstellen |
| `--force` | Ein vorhandenes Backup überschreiben |
| `--tag <tag>` | Das Backup markieren |
| `-w, --watch` | Den Fortschritt der Operation beobachten |
| `--debug` | Ausführliche Ausgabe aktivieren |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Backup abrufen / wiederherstellen

Ein Repository-Backup vom externen Speicher abrufen:

```bash
rdc repo pull my-app -m server-1 --from my-storage
```

| Option | Beschreibung |
|--------|-------------|
| `--from <storage>` | Quell-Speicherort |
| `--from-machine <machine>` | Quellmaschine für Maschine-zu-Maschine-Wiederherstellung |
| `--force` | Vorhandenes lokales Backup überschreiben |
| `-w, --watch` | Den Fortschritt der Operation beobachten |
| `--debug` | Ausführliche Ausgabe aktivieren |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Backups auflisten

Verfügbare Backups an einem Speicherort anzeigen:

```bash
rdc repo backup list --from my-storage -m server-1
```

## Massen-Synchronisation

Alle Repositories auf einmal übertragen oder abrufen:

### Alle zum Speicher übertragen

```bash
rdc repo push --to my-storage -m server-1
```

### Alle vom Speicher abrufen

```bash
rdc repo pull --from my-storage -m server-1
```

| Option | Beschreibung |
|--------|-------------|
| `--to <storage>` | Ziel-Speicher (Push-Richtung) |
| `--from <storage>` | Quell-Speicher (Pull-Richtung) |
| `--repo <name>` | Bestimmte Repositories synchronisieren (wiederholbar) |
| `--override` | Vorhandene Backups überschreiben |
| `--debug` | Ausführliche Ausgabe aktivieren |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Geplante Backups

Automatisieren Sie Backups mit einem Cron-Zeitplan, der als systemd-Timer auf der entfernten Maschine ausgeführt wird.

### Zeitplan festlegen

```bash
rdc config backup-strategy set --destination my-storage --cron "0 2 * * *" --enable
```

Sie können mehrere Ziele mit verschiedenen Zeitplänen konfigurieren:

```bash
rdc config backup-strategy set --destination my-s3 --cron "0 2 * * *" --enable
rdc config backup-strategy set --destination azure-backup --cron "0 6 * * *" --enable
```

| Option | Beschreibung |
|--------|-------------|
| `--destination <storage>` | Backup-Ziel (kann pro Ziel festgelegt werden) |
| `--cron <expression>` | Cron-Ausdruck (z. B. `"0 2 * * *"` für täglich um 2 Uhr) |
| `--enable` | Den Zeitplan aktivieren |
| `--disable` | Den Zeitplan deaktivieren |

### Zeitplan auf Maschine übertragen

Die Zeitplan-Konfiguration als systemd-Timer auf eine Maschine verteilen:

```bash
rdc machine deploy-backup server-1
```

### Zeitplan anzeigen

```bash
rdc config backup-strategy show
```

## Speicher durchsuchen

Den Inhalt eines Speicherorts durchsuchen:

```bash
rdc storage browse my-storage
```

## Bewährte Methoden

- **Planen Sie tägliche Backups** bei mindestens einem Speicheranbieter
- **Testen Sie Wiederherstellungen** regelmäßig, um die Backup-Integrität zu überprüfen
- **Verwenden Sie mehrere Speicheranbieter** für kritische Daten (z. B. S3 + B2)
- **Bewahren Sie Zugangsdaten sicher auf** -- Backups sind verschlüsselt, aber das LUKS-Credential wird zur Wiederherstellung benötigt
