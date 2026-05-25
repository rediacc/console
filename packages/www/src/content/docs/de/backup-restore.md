---
title: Backup & Wiederherstellung
description: >-
  Verschlüsselte Repositories auf externem Speicher sichern, aus Backups
  wiederherstellen und automatische Backups planen.
category: Guides
order: 7
language: de
sourceHash: "633ed49fd412e0ec"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
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

Die Ausgabe ist eine vereinheitlichte Tabelle, die beide [Ordner für geplante Backups](#geplante-backups) (`hot/` und `cold/`) zusammenführt, sodass Sie jedes Backup in einer einzigen Ansicht sehen:

| Spalte | Bedeutung |
|---|---|
| `Mode` | `hot` oder `cold`. In welchem Ordner für geplante Backups dieser Eintrag liegt |
| `Name` | Aus Ihrer lokalen Konfiguration aufgelöster Repository-Name (Fallback auf GUID für Repos, die nicht in der Konfiguration sind) |
| `GUID` | Die Repository-GUID auf der Festplatte |
| `Size` | Menschenlesbare Größe der Backup-Datei |
| `Modified` | UTC-Zeitstempel vom Storage-Backend |

Um in einen einzelnen Modus hineinzuzoomen, übergeben Sie `--path`:

```bash
rdc repo backup list --from my-storage -m server-1 --path hot
rdc repo backup list --from my-storage -m server-1 --path cold
```

### Storage layout

Geplante Backups landen in moduspezifischen Unterordnern innerhalb des konfigurierten Ordners des Speichers, sodass derselbe Speicher sowohl den stündlichen als auch den wöchentlichen Stream sauber beherbergt, ohne sie zu vermischen:

```text
<bucket>/<folder>/
├── hot/
│   ├── <guid-1>
│   ├── <guid-2>
│   └── ...
└── cold/
    ├── <guid-1>
    ├── <guid-3>
    └── ...
```

Ein Repo kann sowohl in `hot/` als auch in `cold/` erscheinen (der stündliche Zeitplan erfasst es; der wöchentliche erfasst es erneut). Die zusammengeführte Auflistung zeigt beide Zeilen, sodass klar ist, welche Streams welche Repos abdecken.

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
| `cold` | Dienste gestoppt, Snapshot erstellt, Dienste neu gestartet, Snapshot hochgeladen (anwendungskonsistent) | Stop+Start-Fenster pro Repo, parallel über alle Repos. Siehe "Abschätzung der Cold-Backup-Ausfallzeit" unten. |

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
- Protokolle des renet-Backup-Laufs (`journalctl -u renet-*` oder der direkte `rdc machine backup schedule`-Aufruf) geben eine abschließende Zusammenfassungszeile der Form `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]` aus. Ein nicht leeres `failed_repos` ist das grep-Ziel.

### Abschätzung der Cold-Backup-Ausfallzeit

Jedes Repository ist nur während seines eigenen `down()` + `up()`-Fensters ausgefallen. Auf einem warmen Host sind das typischerweise:

| Repository-Form | Typisches Stop+Start |
|-----------------|----------------------|
| Klein (1-2 Container, keine DB) | 5-15 s |
| Mittel (Webanwendung + Cache) | 20-45 s |
| Schwer (DB + Queues + Mail) | 60-120 s |

Der Snapshot-Schritt (`btrfs subvolume snapshot -r`) ist O(1), unabhängig von der Repository-Größe: 0,1-1 s. Ein Repository wird nicht für die Snapshots anderer Repositories heruntergefahren gehalten. Der Uploader läuft dann gegen einen schreibgeschützten Snapshot, während alle Repositories bereits wieder oben sind.

**Die Gesamt-Wall-Clock für den gesamten Lauf** wird davon bestimmt, wie viele Repositories gleichzeitig neu starten. Renet leitet diesen Wert vom Host ab:

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Beispiele:

| Host | Repositories | Parallelität | Wall-Clock-Neustart |
|------|--------------|-------------|---------------------|
| 4-CPU-VM | 5 Repos, ø 30 s je | 2 | ~75 s |
| 16-CPU-Server | 10 Repos, ø 40 s je | 8 | ~80 s |
| 64-CPU-Fleet-Knoten | 50 Repos, ø 40 s je | 8 | ~4 Min |

**Override per Umgebungsvariable:** Setzen Sie `REDIACC_COLD_BACKUP_CONCURRENCY=N` in der Umgebung des Backup-Dienstes (meist über ein systemd-Drop-in), um einen bestimmten Wert festzulegen. `=1` erzwingt streng serielle Neustarts, nützlich beim Debuggen eines Crashloops im `up()`-Hook eines Repositories.

Wenn Sie ein latenzempfindliches Repository betreiben (öffentliche Webanwendung, Mail), ist dessen Ausfallzeit durch sein eigenes Stop+Start begrenzt (typischerweise 30-90 s), nicht durch die Gesamtlaufzeit. Repositories werden in der Reihenfolge ihrer Erkennung in Parallelitäts-Slots eingeplant; es gibt keine Prioritätswarteschlange. Teilen Sie schwere Repositories in eigene, mit `--exclude` begrenzte Strategien auf, wenn Sie eine feinere Zeitplanung benötigen.

### Lange Läufe und überlappende Zeitpläne

Ein Cold-Backup, das länger als sein eigenes Zeitplan-Intervall dauert (zum Beispiel eine erste Vollsicherung eines 500 GB-Repositories über eine moderate Leitung kann legitim mehr als 24 h benötigen, während der nächtliche Timer erneut feuert), löst weder einen zweiten Lauf aus noch stellt er einen in die Warteschlange. Die systemd-`Type=oneshot`-Unit ist eine Einzelinstanz: Wenn der Timer feuert und der Dienst bereits `activating` ist, fasst systemd den Start in den laufenden Job zusammen. Kein neuer Prozess wird gestartet, kein Lauf für später gespeichert.

Konkret: Ein Lauf, der am Montag um 03:00 UTC startet und am Donnerstag Mittag endet:

| Tag | 03:00 UTC feuert | Ergebnis |
|------|-----------------|----------|
| Montag | Erstes Feuern | Lauf beginnt |
| Dienstag | Zweites Feuern | Still verworfen (vorheriger Lauf ist noch aktiv) |
| Mittwoch | Drittes Feuern | Still verworfen (vorheriger Lauf ist noch aktiv) |
| Donnerstag | Lauf endet mittags | Kein Nachholen; nächster Lauf ist Freitag 03:00 UTC |

Die `Persistent=true`-Direktive des Timers rettet diese Feuer **nicht**. `Persistent=true` wiederholt Feuer, die verpasst wurden, weil der Timer selbst inaktiv war (System aus, Timer deaktiviert). Feuer, die verworfen wurden, weil der Dienst beschäftigt war, sind weg.

Dieses Verhalten ist bewusst gewählt. Zwei parallele Cold-Backups gegen denselben Datastore würden um den BTRFS-Snapshot-Pfad, das rclone-Remote und die Per-Repo-Sidecars unter `/var/run/rediacc/cold-backup-<guid>.status.json` konkurrieren. Die Serialisierung hinter einem langen Lauf ist das sichere Ergebnis.

**Monitoring-Konsequenz.** Ein hängendes Backup (zum Beispiel rclone, das an einem Netzwerk-Blackhole hängenbleibt) verwirft still jedes nachfolgende Timer-Feuern. Der Scheduler gibt keinen Alarm aus. Beobachten Sie `systemctl show <unit> -p ActiveEnterTimestamp`: Wenn der Dienst länger als erwartet `activating` ist (zum Beispiel mehr als 48 h bei einem nächtlichen Timer), untersuchen Sie dies.

**Wenn Sie möchten, dass jedes geplante Feuer läuft**, wechseln Sie den Timer von `OnCalendar=<cron>` zu `OnUnitInactiveSec=<Intervall>`. Das feuert N Stunden nach Abschluss des vorherigen Laufs statt nach einem festen Wall-Clock-Zeitplan, sodass lange Läufe keine Verluste verursachen. Sie schieben nur den nächsten Lauf nach hinten. Der Kompromiss ist Zeitplan-Drift: Ihr nächtliches 03:00 wird zu "24 h nach Abschluss des letzten Laufs."

### Strategie definieren

Der kanonische Standard ist eine Aufteilung in zwei Strategien: ein schneller stündlicher Hot-Stream, der jedes Repo erfasst, und ein langsamerer wöchentlicher Cold-Stream, der anwendungskonsistente Snapshots erstellt. Die beiden Strategien schreiben in unterschiedliche Speicher-Unterordner (`hot/` und `cold/`), sodass sich Backups nie vermischen.

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
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

Der `--exclude`-Filter der Cold-Strategie ist der empfohlene Notausgang für sehr große Repos, die nicht in Ihr wöchentliches Wartungsfenster passen. Die stündliche Hot-Strategie deckt sie weiterhin ab; Cold überspringt sie einfach. Repository-Namen in `--exclude` werden gegen den lokalen Konfigurationsnamen des Repos abgeglichen (ohne `:tag`).

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
rdc config backup-strategy show --name weekly-cold
```

### Strategie entfernen

```bash
rdc config backup-strategy remove --name weekly-cold
```

### Strategien an eine Maschine binden

Binden Sie in Ihrer Konfiguration einen oder mehrere Strategienamen an eine Maschine:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
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

Das Deploy ist ein State-Reconciler. Er liest die aktuellen Unit-Dateien und den systemd-Zustand auf der Maschine, vergleicht sie mit dem, was die Konfiguration erzeugen würde (SHA-256 pro Datei), und berührt nur Units, deren Inhalt sich tatsächlich geändert hat. Ein erneuter Aufruf ohne Konfigurationsänderungen ist ein No-op: keine Writes, kein `daemon-reload`, kein Timer-Churn.

`--dry-run` gibt den Plan pro Strategie aus (`created`, `updated (service, timer, env)`, `unchanged`, `removed`), ohne die Maschine anzufassen. In Kombination mit `--debug` werden auch die generierten Unit-Inhalte ausgegeben; rclone-Tokens werden redigiert.

Wenn gerade ein Backup für eine Strategie läuft, die aktualisiert oder entfernt werden soll, bricht das Deploy sofort ab und weist darauf hin, das Backup abzubrechen oder `--force` zu übergeben. Mit `--force` behält der laufende Vorgang seine In-Memory-Unit, und die neue Konfiguration greift beim nächsten Timer-Tick, sodass das laufende Backup niemals beendet wird.

`--reset-failed` ist opt-in. Wenn übergeben, löscht es nach einem erfolgreichen Deploy den Failed-Status auf berührten Services. Standardmäßig aus, damit vorherige Fehlersignale für Alerting sichtbar bleiben.

### Backup jetzt ausführen

Ein Backup sofort auslösen, ohne auf den Timer zu warten. Funktioniert auch ohne deployte Timer via `systemd-run` für Ad-hoc-Ausführung:

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy weekly-cold
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
rdc machine backup cancel -m server-1 --strategy weekly-cold
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
