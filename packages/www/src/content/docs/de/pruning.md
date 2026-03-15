---
title: "Bereinigung"
description: "Verwaiste Sicherungskopien, überholte Snapshots und ungenützte Repository-Images löschen, um Speicherplatz freizugeben."
category: "Guides"
order: 12
language: de
sourceHash: "39df2a50797597f6"
---

# Bereinigung

Die Bereinigung entfernt Ressourcen, die von keiner Konfigurationsdatei mehr referenziert werden. Es gibt zwei Bereinigungsbefehle, die auf unterschiedliche Ressourcentypen abzielen:

- **`rdc storage prune`** -- löscht verwaiste Backup-Dateien aus Cloud-/externem Speicher
- **`rdc machine prune`** -- bereinigt Datastore-Artefakte und (optional) verwaiste Repository-Images auf einer Maschine

## Storage Prune

Durchsucht einen Speicheranbieter und löscht Backups, deren GUIDs in keiner Konfigurationsdatei mehr vorkommen.

```bash
# Dry-run (default) — shows what would be deleted
rdc storage prune my-s3 -m server-1

# Actually delete orphaned backups
rdc storage prune my-s3 -m server-1

# Override grace period (default 7 days)
rdc storage prune my-s3 -m server-1 --grace-days 14
```

### Was geprüft wird

1. Listet alle Backup-GUIDs im angegebenen Speicher auf.
2. Durchsucht alle Konfigurationsdateien auf der Festplatte (`~/.config/rediacc/*.json`).
3. Ein Backup ist **verwaist**, wenn seine GUID in keinem Repositories-Abschnitt einer Konfiguration referenziert wird.
4. Kürzlich archivierte Repositories innerhalb der Schonfrist sind **geschützt**, auch wenn sie aus der aktiven Konfiguration entfernt wurden.

## Machine Prune

Bereinigt Ressourcen auf der Maschine in zwei Phasen.

### Phase 1: Datastore-Bereinigung (wird immer ausgeführt)

Entfernt leere Mount-Verzeichnisse, veraltete Lock-Dateien und veraltete BTRFS-Snapshots.

```bash
# Dry-run
rdc machine prune server-1 --dry-run

# Execute cleanup
rdc machine prune server-1
```

### Phase 2: Verwaiste Repository-Images (optional)

Mit `--orphaned-repos` identifiziert die CLI zusätzlich LUKS-Repository-Images auf der Maschine, die in keiner Konfigurationsdatei vorkommen, und löscht sie.

```bash
# Dry-run (default behavior when is set)
rdc machine prune server-1

# Actually delete orphaned repos
rdc machine prune server-1

# Custom grace period
rdc machine prune server-1 --grace-days 30
```

## Sicherheitsmodell

Die Bereinigung ist standardmäßig für Multi-Konfigurations-Setups sicher konzipiert.

### Multi-Konfigurations-Bewusstsein

Beide Bereinigungsbefehle durchsuchen **alle** Konfigurationsdateien in `~/.config/rediacc/`, nicht nur die aktive. Ein Repository, das von `production.json` referenziert wird, wird nicht gelöscht, auch wenn es in `staging.json` fehlt. Dies verhindert versehentliches Löschen, wenn Konfigurationen auf unterschiedliche Umgebungen ausgerichtet sind.

### Schonfrist

Wenn ein Repository aus einer Konfiguration entfernt wird, kann es mit einem Zeitstempel archiviert werden. Die Bereinigungsbefehle respektieren eine Schonfrist (standardmäßig 7 Tage), während der kürzlich archivierte Repositories vor dem Löschen geschützt sind. Dies gibt Ihnen Zeit, ein Repository wiederherzustellen, falls es versehentlich entfernt wurde.

### Dry-Run als Standard

`storage prune` und `machine prune` verwenden standardmäßig den Dry-Run-Modus. Sie zeigen an, was entfernt würde, ohne Änderungen vorzunehmen. Übergeben Sie `--no-dry-run` oder `--force`, um die tatsächliche Löschung durchzuführen.

## Konfiguration

### `pruneGraceDays`

Legen Sie eine benutzerdefinierte Standard-Schonfrist in Ihrer Konfigurationsdatei fest, damit Sie nicht jedes Mal `--grace-days` übergeben müssen:

```bash
# Set grace period to 14 days in the active config
rdc config set pruneGraceDays 14
```

Das CLI-Flag `--grace-days` überschreibt diesen Wert, wenn es angegeben wird.

### Rangfolge

1. `--grace-days <N>` Flag (höchste Priorität)
2. `pruneGraceDays` in der Konfigurationsdatei
3. Eingebauter Standard: 7 Tage

## Best Practices

- **Dry-Run zuerst ausführen.** Immer eine Vorschau anzeigen, bevor eine destruktive Bereinigung durchgeführt wird, besonders auf Produktivspeicher.
- **Mehrere Konfigurationen aktuell halten.** Die Bereinigung prüft alle Konfigurationen im Konfigurationsverzeichnis. Wenn eine Konfigurationsdatei veraltet oder gelöscht ist, verlieren ihre Repositories den Schutz. Halten Sie Konfigurationsdateien aktuell.
- **Großzügige Schonfristen für Produktion verwenden.** Die standardmäßige 7-Tage-Schonfrist eignet sich für die meisten Workflows. Für Produktionsumgebungen mit seltenen Wartungsfenstern sollten Sie 14 oder 30 Tage in Betracht ziehen.
- **Storage Prune nach Backup-Läufen planen.** Kombinieren Sie `storage prune` mit Ihrem Backup-Zeitplan, um die Speicherkosten ohne manuellen Eingriff unter Kontrolle zu halten.
- **Machine Prune mit deploy-backup kombinieren.** Nach dem Bereitstellen von Backup-Zeitplänen (`rdc machine deploy-backup`) fügen Sie eine periodische Maschinenbereinigung hinzu, um veraltete Snapshots und verwaiste Datastore-Artefakte zu bereinigen.
- **Vor Verwendung von `--force` prüfen.** Das `--force`-Flag umgeht die Schonfrist. Verwenden Sie es nur, wenn Sie sicher sind, dass keine andere Konfiguration die betreffenden Repositories referenziert.
