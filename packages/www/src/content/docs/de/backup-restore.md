---
title: "Backup & Wiederherstellung"
description: "Verschlüsselte Repositories auf externem Speicher sichern, aus Backups wiederherstellen und automatische Backups planen."
category: "Guides"
order: 7
language: de
---

# Backup & Wiederherstellung

Rediacc kann verschlüsselte Repositories auf externen Speicheranbietern sichern und sie auf derselben oder einer anderen Maschine wiederherstellen. Backups sind verschlüsselt -- das LUKS-Credential des Repositories wird zur Wiederherstellung benötigt.

## Speicher konfigurieren

Bevor Sie Backups übertragen, registrieren Sie einen Speicheranbieter. Rediacc unterstützt jeden rclone-kompatiblen Speicher: S3, B2, Google Drive und viele mehr.

### Aus rclone importieren

Wenn Sie bereits ein rclone-Remote konfiguriert haben:

```bash
rdc context import-storage my-storage
```

Dies importiert die Speicherkonfiguration aus Ihrer rclone-Konfiguration in den aktuellen Kontext.

### Speicher anzeigen

```bash
rdc context storages
```

## Ein Backup erstellen

Ein Repository-Backup auf externen Speicher übertragen:

```bash
rdc backup push my-app -m server-1 --to my-storage
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

## Backup abrufen / wiederherstellen

Ein Repository-Backup vom externen Speicher abrufen:

```bash
rdc backup pull my-app -m server-1 --from my-storage
```

| Option | Beschreibung |
|--------|-------------|
| `--from <storage>` | Quell-Speicherort |
| `--from-machine <machine>` | Quellmaschine für Maschine-zu-Maschine-Wiederherstellung |
| `--force` | Vorhandenes lokales Backup überschreiben |
| `-w, --watch` | Den Fortschritt der Operation beobachten |
| `--debug` | Ausführliche Ausgabe aktivieren |

## Backups auflisten

Verfügbare Backups an einem Speicherort anzeigen:

```bash
rdc backup list --from my-storage -m server-1
```

## Massen-Synchronisation

Alle Repositories auf einmal übertragen oder abrufen:

### Alle zum Speicher übertragen

```bash
rdc backup sync --to my-storage -m server-1
```

### Alle vom Speicher abrufen

```bash
rdc backup sync --from my-storage -m server-1
```

| Option | Beschreibung |
|--------|-------------|
| `--to <storage>` | Ziel-Speicher (Push-Richtung) |
| `--from <storage>` | Quell-Speicher (Pull-Richtung) |
| `--repo <name>` | Bestimmte Repositories synchronisieren (wiederholbar) |
| `--override` | Vorhandene Backups überschreiben |
| `--debug` | Ausführliche Ausgabe aktivieren |

## Geplante Backups

Automatisieren Sie Backups mit einem Cron-Zeitplan, der als systemd-Timer auf der entfernten Maschine ausgeführt wird.

### Zeitplan festlegen

```bash
rdc backup schedule set --destination my-storage --cron "0 2 * * *" --enable
```

| Option | Beschreibung |
|--------|-------------|
| `--destination <storage>` | Standard-Backup-Ziel |
| `--cron <expression>` | Cron-Ausdruck (z. B. `"0 2 * * *"` für täglich um 2 Uhr) |
| `--enable` | Den Zeitplan aktivieren |
| `--disable` | Den Zeitplan deaktivieren |

### Zeitplan auf Maschine übertragen

Die Zeitplan-Konfiguration als systemd-Timer auf eine Maschine verteilen:

```bash
rdc backup schedule push server-1
```

### Zeitplan anzeigen

```bash
rdc backup schedule show
```

## Speicher durchsuchen

Den Inhalt eines Speicherorts durchsuchen:

```bash
rdc storage browse my-storage -m server-1
```

## Bewährte Methoden

- **Planen Sie tägliche Backups** bei mindestens einem Speicheranbieter
- **Testen Sie Wiederherstellungen** regelmäßig, um die Backup-Integrität zu überprüfen
- **Verwenden Sie mehrere Speicheranbieter** für kritische Daten (z. B. S3 + B2)
- **Bewahren Sie Zugangsdaten sicher auf** -- Backups sind verschlüsselt, aber das LUKS-Credential wird zur Wiederherstellung benötigt
