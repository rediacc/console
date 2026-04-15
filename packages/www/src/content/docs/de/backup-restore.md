---
title: Backup & Wiederherstellung
description: >-
  Verschlüsselte Repositories auf externem Speicher sichern, aus Backups
  wiederherstellen und automatische Backups planen.
category: Guides
order: 7
language: de
sourceHash: "0c7ebc3efb8877c5"
sourceCommit: "8b0f83c57ebaaa0a2bee93143db34ab677b4e68b"
---

# Backup & Wiederherstellung

Rediacc kann verschlüsselte Repositories auf externen Speicheranbietern sichern und sie auf derselben oder einer anderen Maschine wiederherstellen. Backups sind verschlüsselt; das LUKS-Credential des Repositories wird zur Wiederherstellung benötigt.

## Speicher konfigurieren

Bevor Sie Backups übertragen, registrieren Sie einen Speicheranbieter. Rediacc unterstützt jeden rclone-kompatiblen Speicher: S3, B2, Google Drive und viele mehr.

### Aus rclone importieren

Wenn Sie bereits ein rclone-Remote konfiguriert haben:

```bash
rdc config storage import --file rclone.conf
```

Dies importiert Speicherkonfigurationen aus einer rclone-Konfigurationsdatei in die aktuelle Konfiguration. Unterstützte Typen: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob und Swift.

### Speicher anzeigen

```bash
rdc config storage list
```

## Ein Backup erstellen

Ein Repository-Backup auf externen Speicher übertragen:

```bash
rdc repo push --name my-app -m server-1 --to my-storage
```

Push prüft immer, ob das Ziel-Repository eingehängt ist, bevor geschrieben wird. Ist es nicht eingehängt, wird die Operation abgebrochen.

| Option | Beschreibung |
|--------|-------------|
| `--to <storage>` | Ziel-Speicherort |
| `--to-machine <machine>` | Zielmaschine für Maschine-zu-Maschine-Backup |
| `--dest <filename>` | Benutzerdefinierter Zieldateiname |
| `--checkpoint` | CRIU-Checkpoint vor dem Pushen erstellen (für Container mit Label `rediacc.checkpoint=true`). Ziel stellt automatisch bei `repo up` wieder her |
| `--force` | Ein vorhandenes Backup überschreiben |
| `--bwlimit <limit>` | Bandbreitenlimit für den rsync-Transfer (z. B. `10M`, `500K`) |
| `--tag <tag>` | Das Backup markieren |
| `-w, --watch` | Den Fortschritt der Operation beobachten |
| `--debug` | Ausführliche Ausgabe aktivieren |
| `--skip-router-restart` | Den Neustart des Route-Servers nach der Operation überspringen |

## Backup abrufen / wiederherstellen

Ein Repository-Backup vom externen Speicher abrufen:

```bash
rdc repo pull --name my-app -m server-1 --from my-storage
```

Pull prüft immer, ob das Ziel-Repository eingehängt ist, bevor geschrieben wird. Ist es nicht eingehängt, wird die Operation abgebrochen.

| Option | Beschreibung |
|--------|-------------|
| `--from <storage>` | Quell-Speicherort |
| `--from-machine <machine>` | Quellmaschine für Maschine-zu-Maschine-Wiederherstellung |
| `--force` | Vorhandenes lokales Backup überschreiben |
| `--bwlimit <limit>` | Bandbreitenlimit für den rsync-Transfer (z. B. `10M`, `500K`) |
| `-w, --watch` | Den Fortschritt der Operation beobachten |
| `--debug` | Ausführliche Ausgabe aktivieren |
| `--skip-router-restart` | Den Neustart des Route-Servers nach der Operation überspringen |

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
| `--skip-router-restart` | Den Neustart des Route-Servers nach der Operation überspringen |

## Geplante Backups

Rediacc verwendet benannte Backup-Strategien. Jede Strategie definiert einen Zeitplan, einen Backup-Modus, ein optionales Bandbreitenlimit und Dateifilter. Maschinen referenzieren Strategien nach Namen, um festzulegen, welche Backups auf ihnen ausgeführt werden.

### Backup-Modi

| Modus | Verhalten | Ausfallzeit |
|-------|-----------|-------------|
| `hot` | BTRFS-Snapshot wird bei laufenden Diensten erstellt (absturzkonsistent) | Keine |
| `cold` | Dienste gestoppt, Snapshot erstellt, Dienste neu gestartet, Snapshot hochgeladen (anwendungskonsistent) | Kurz |

Verwenden Sie `hot` für Dienste, die absturzkonsistente Snapshots tolerieren. Verwenden Sie `cold`, wenn Sie garantierte Konsistenz benötigen und einen kurzen Neustart akzeptieren können.

### Cold-Backup-Semantik

Ein Cold-Backup läuft in drei Phasen pro enthaltenem Repository: **Stopp -- Snapshot -- Start**. Das Verstehen der Grenzen der Garantien hilft Betreibern, Teilausfälle frühzeitig zu erkennen.

**Was Cold-Backup garantiert:**

- Vor dem Snapshot wird jeder laufende Container in jedem enthaltenen Repository über den `down()`-Hook der Rediaccfile kontrolliert gestoppt, und der repository-eigene Docker-Daemon wird stillgelegt. Der Snapshot ist daher anwendungskonsistent, nicht nur absturzkonsistent.
- Die Menge der Container-IDs, die vor dem Snapshot liefen, wird in eine Sidecar-Datei unter `/var/run/rediacc/cold-backup-<guid>.running.json` geschrieben. Dies ist die Wahrheitsquelle dafür, "was nach Abschluss wieder laufen soll."
- Nach dem Snapshot wird der `up()`-Hook der Rediaccfile des Repositories aufgerufen, um den vollständigen Compose-Stack wiederherzustellen.
- Eine laufzeitbezogene Status-Sidecar-Datei unter `/var/run/rediacc/cold-backup-<guid>.status.json` zeichnet Phase, Ergebnis und etwaige Fehler jedes Versuchs auf.

**Was Cold-Backup NICHT garantiert:**

- `up()` ist ein Best-Effort-Versuch. Es kann aus Gründen scheitern, die außerhalb der Kontrolle des Cold-Backups liegen (eine `depends_on: service_healthy`-Bedingung wartet noch, ein Compose-Datei-Syntaxfehler, ein vorübergehender Netzwerkfehler beim Image-Pull). Bei einem Fehler protokolliert Cold-Backup den Fehler auf Fehlerebene, schreibt die Status-Sidecar-Datei und fährt mit dem nächsten Repository fort.
- Wenn `up()` fehlschlägt, greift ein **direkter Fallback-Neustart**: Die Running-Sidecar wird gelesen, und jede aufgezeichnete Container-ID wird direkt über die Docker API neu gestartet (ohne Compose). Dies bringt Dienste auch dann wieder zum Laufen, wenn der Compose-Ablauf ein Problem hat, allerdings ohne erneute Ausführung von Rediaccfile-Hooks.
- Wenn der Fallback für einige Container-IDs fehlschlägt (z. B. ist der Docker-Daemon selbst ausgefallen), bleibt die Sidecar-Datei **bestehen**, damit der Router-Watchdog bei jedem Tick erneut versuchen kann.

**Watchdog-Wiederherstellung:** Bei jedem Tick prüft der Watchdog, ob eine Running-Sidecar vorhanden ist. Jede dort aufgelistete Container-ID, die derzeit gestoppt ist, wird neu gestartet, *unabhängig von der gespeicherten `restart_policy` des Containers*. Dies bedeutet, dass Dienste mit `restart: on-failure` (die Docker nach einem sauberen Stopp NICHT neu starten würde) nach einem Cold-Backup wieder starten. Sobald alle aufgelisteten Container laufen, wird die Sidecar-Datei gelöscht.

**Wie Betreiber Ausfälle erkennen:**

- `rdc machine query --name <machine> --containers` zeigt den Laufzustand. Vergleichen Sie mit der erwarteten Menge.
- `/var/run/rediacc/cold-backup-<guid>.status.json` auf der Maschine. Prüfen Sie via `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` mit einem veralteten `startedAt` bedeutet, dass das letzte Backup nicht sauber abgeschlossen wurde.
- Protokolle des renet-Backup-Laufs (`journalctl -u renet-*` oder der direkte `rdc machine deploy-backup`-Aufruf) geben eine abschließende Zusammenfassungszeile der Form `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]` aus. Ein nicht leeres `failed_repos` ist das grep-Ziel.

### Strategie definieren

```bash
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc config backup-strategy set \
  --name nightly-cold \
  --destination my-storage \
  --cron "0 2 * * *" \
  --mode cold \
  --include "*.db" \
  --exclude "tmp/**" \
  --enable
```

| Option | Beschreibung |
|--------|-------------|
| `--name <name>` | Strategiename (für Maschinenbindung verwendet) |
| `--destination <storage>` | Speicheranbieter zum Hochladen |
| `--cron <expression>` | Cron-Ausdruck (z. B. `"0 2 * * *"` für täglich um 2 Uhr) |
| `--mode <hot\|cold>` | Backup-Modus |
| `--bwlimit <limit>` | Bandbreitenlimit für Uploads (z. B. `10M`) |
| `--include <pattern>` | Einschlussfilter (wiederholbar) |
| `--exclude <pattern>` | Ausschlussfilter (wiederholbar) |
| `--enable` / `--disable` | Strategie aktivieren oder deaktivieren |

### Strategien anzeigen

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name nightly-cold
```

### Strategie entfernen

```bash
rdc config backup-strategy remove --name nightly-cold
```

### Strategien an eine Maschine binden

Binden Sie in Ihrer Konfiguration einen oder mehrere Strategienamen an eine Maschine:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "nightly-cold"]
    }
  }
}
```

## Backup-Operationen

### Zeitplan auf Maschine deployen

Die gebundenen Strategien als systemd-Timer auf eine Maschine übertragen:

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

`--dry-run` gibt die generierten systemd-Unit-Dateien aus, ohne sie zu deployen. rclone-Tokens werden in der Dry-run-Ausgabe maskiert.

### Backup jetzt ausführen

Ein Backup sofort auslösen, ohne auf den Timer zu warten. Funktioniert auch ohne deployte Timer via `systemd-run` für Ad-hoc-Ausführung:

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy nightly-cold
```

### Backup-Status anzeigen

Den aktuellen Status der Backup-Timer und neueste Job-Ergebnisse anzeigen:

```bash
rdc machine backup status -m server-1
rdc machine backup status -m server-1 --strategy hourly-hot
```

### Laufendes Backup abbrechen

```bash
rdc machine backup cancel -m server-1
rdc machine backup cancel -m server-1 --strategy nightly-cold
```

## Repository-Migration

Ein Repository von einer Maschine auf eine andere verschieben:

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Option | Beschreibung |
|--------|-------------|
| `--name <repo>` | Zu migrierendes Repository |
| `--from <machine>` | Quellmaschine |
| `--to <machine>` | Zielmaschine |
| `--provision` | Repository auf der Zielmaschine provisionieren, bevor übertragen wird |
| `--checkpoint` | CRIU-Checkpoint vor der Migration erstellen |
| `--skip-dns` | DNS-Aktualisierung nach der Migration überspringen |
| `--bwlimit <limit>` | Bandbreitenlimit für die Übertragung (z. B. `50M`) |

Die Migration überträgt die verschlüsselten Repository-Daten via rsync. Das Quell-Repository bleibt intakt, bis Sie es explizit entfernen.

## Speicher durchsuchen

Den Inhalt eines Speicherorts durchsuchen:

```bash
rdc storage browse --name my-storage
```

## Bewährte Methoden

- Tägliche Cold-Backups für anwendungskonsistente Snapshots kritischer Daten einplanen
- Hot-Backups für hochfrequente Snapshots verwenden, bei denen keinerlei Ausfallzeit akzeptabel ist
- Wiederherstellungen regelmäßig testen, um die Backup-Integrität zu überprüfen
- Mehrere Speicheranbieter für kritische Daten verwenden (z. B. S3 + B2)
- Zugangsdaten sicher aufbewahren; Backups sind verschlüsselt, aber das LUKS-Credential wird zur Wiederherstellung benötigt
