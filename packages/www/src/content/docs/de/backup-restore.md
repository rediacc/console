---
title: "Backup & Wiederherstellung"
description: "Verschlüsselte Repositories auf zwei Wegen sichern: über inhaltsadressierten Chunk-Storage, der nur geänderte Zellen hochlädt, oder per vollständigem Push zu jedem rclone-kompatiblen Speicher. Auf jeder Maschine wiederherstellen und mit benannten Strategien und systemd-Timern automatisieren."
category: "Guides"
order: 7
language: de
sourceHash: "c02ab3e78c40fa92"
sourceCommit: "522dceadb04b6a3e7f4ea60ac1e47308f6a1a600"
---

# Backup & Wiederherstellung

Rediacc kann verschlüsselte Repositories auf externen Speicheranbietern sichern und sie auf derselben oder einer anderen Maschine wiederherstellen. Backups sind verschlüsselt; das LUKS-Credential des Repositories wird zur Wiederherstellung benötigt.

## Zwei Backup-Wege

Rediacc bietet zwei unabhängige Backup-Wege, und dieser Leitfaden behandelt beide. Sie verwenden unterschiedlichen Speicher und unterschiedliche Befehle, sodass ein Repository, das über den einen Weg gesichert wurde, über den anderen nicht gesichert ist.

**Chunk-Storage** (`rdc backup snapshot`) lädt das Repository-Image in Zellen fester Größe hoch, die über ihren Inhalt adressiert werden. Der erste Lauf lädt das vollständige, nicht-leere Inventar hoch; jeder folgende Lauf lädt nur die geänderten Zellen hoch, ermittelt anhand der Allokationsmetadaten des Dateisystems statt durch Lesen des gesamten Images. Identische Zellen werden über Snapshots und über eine ganze Fork-Familie hinweg nur einmal gespeichert, und die Nutzung wird gegen Ihr Speicherkontingent angerechnet (`rdc backup usage`).

**Storage-Push wurde eingestellt.** `rdc repo push --to <storage>` kopierte früher eine vollständige Backup-Datei zu einem rclone-kompatiblen Anbieter, den Sie selbst registrierten. Der rclone-Zweig wurde vollständig entfernt, und Push, Pull, List und Restore verweigern jetzt ein Speicherziel und verweisen hierher. Die Maschine-zu-Maschine-Übertragung bleibt unangetastet: Sie lief nie über rclone.

Die Wiederherstellung aus dem Chunk-Storage funktioniert: `rdc backup restore <repo> --at <snapshot-id>` materialisiert einen gespeicherten Snapshot, und `--at` akzeptiert auch einen RFC-3339-Zeitstempel, der gegen das Snapshot-Inventar aufgelöst wird. Fügen Sie `--as <name>` hinzu, um unter einem anderen Namen wiederherzustellen, und `--up`, um das Repository anschließend hochzufahren. Chunk-Storage bietet auch Upload (`rdc backup snapshot`), Verifizierung (`rdc backup verify`, mit `--deep` zur erneuten Hashberechnung jeder Zelle statt nur einer Stichprobe), das Snapshot-Inventar (`rdc backup manifests`) und Kontingentabrechnung (`rdc backup usage`).

### Chunk-Storage-Befehle

```bash
# Snapshot hochladen. Der erste Lauf sät, spätere Läufe senden nur geänderte Zellen.
rdc backup snapshot my-app

# Planen, ohne hochzuladen: zeigt, was sich bewegen würde.
rdc backup snapshot my-app --dry-run

# Dem lokalen Anker misstrauen und das vollständige Inventar neu hochladen.
# Dies lädt alles neu hoch und belastet erneut das Kontingent; nur verwenden,
# wenn der Anker nachweislich fehlerhaft ist.
rdc backup snapshot my-app --reseed

# Das gespeicherte Inventar und Ihr Kontingent prüfen.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

## Cold-Snapshots (`--cold`)

Ein Cold-Snapshot stoppt ein Repository, bevor es eingefroren wird. Das gespeicherte Image ist damit anwendungskonsistent statt nur absturzkonsistent. Der Befehl läuft auf der Maschine selbst:

```bash
# Jedes Repository auf dem Standard-Datastore.
sudo renet backup snapshot --cold

# Nur die genannten Repositories. --repo nimmt eine Repository-GUID und ist wiederholbar.
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold` lässt sich nicht mit `--dry-run` kombinieren. Ein Probelauf, der Container stoppt, ist kein Probelauf, und einer, der es nicht tut, ist nicht cold. Deshalb weist renet die Kombination zurück, statt sich selbst für eine Bedeutung zu entscheiden.

### Was bei einem Cold-Lauf passiert

Für jedes ausgewählte Repository, in dieser Reihenfolge:

1. Seine Container stoppen.
2. Repository-Mount und Datastore auf die Platte schreiben.
3. Prüfen, dass die Container wirklich gestoppt sind.
4. Einen Copy-on-Write-Reflink des Repository-Images anlegen.
5. Die Container wieder starten.

Erst danach beginnt der Upload, und zwar mit längst wieder laufenden Repositories.

Die Ausfallzeit ist das Einfrieren, nicht die Übertragung. Ein Reflink besteht nur aus Metadaten und dauert deshalb gleich lang, ob das Repository 1 GB oder 100 GB hält. Beim Upload ist das anders: er wächst mit den geänderten Bytes, und der erste Snapshot lädt das gesamte nicht-leere Inventar hoch. Container bis zum Ende des Uploads unten zu halten, würde die Ausfallzeit an die Datenmenge koppeln, was bei einer Erstsicherung Stunden statt Millisekunden bedeutet.

Alle ausgewählten Repositories werden in einem gemeinsamen Fenster gestoppt, nicht nacheinander. Das kostet pro Repository etwas mehr Ausfallzeit und bringt dafür einen einzigen Konsistenzpunkt über den ganzen Satz.

Ein Repository ohne laufende Container ist bereits ruhig. Es wird ganz ohne Ausfallzeit gesichert, und das ist ein normales Ergebnis, kein Fehler.

### Was die Ausfallzeit kostet

Auf einer echten Maschine gemessen betrug die gesamte Ausfallzeit **222 ms**:

| Phase | Gemessen | Was passiert |
|-------|----------|--------------|
| `cold_down` | 64 ms | Container stoppen |
| `cold_sync` | 26 ms | Repository-Mounts und Datastore werden auf die Platte geschrieben |
| `cold_verify` | 31 ms | Container werden als gestoppt bestätigt |
| `cold_stage` | 0 ms | Reflink des Repository-Images |
| `cold_up` | 99 ms | Container starten wieder |

Der Neustart der Container dominiert, und das Staging ist praktisch kostenlos: der Reflink taucht in Millisekunden-Auflösung gar nicht erst auf. Lesen Sie diese Null aber neben den Datensätzen der einzelnen Repositories und nicht für sich allein. Ein Lauf, der jedes Repository zurückgewiesen hat, meldet ebenfalls `cold_stage=0ms`, und nur die Datensätze sagen, welcher der beiden Fälle vorliegt.

Die Aufschlüsselung ist der Beleg, keine Dekoration. Keine dieser fünf Phasen liest oder sendet Repository-Daten, also wächst auch keine davon mit dem Backup. Der Teil, der wächst, ist der Upload, und der läuft erst, wenn die Ausfallzeit schon vorbei ist.

renet gibt dieselben Werte am Ende eines Laufs aus, sodass Sie Ihre eigenen Maschinen messen können statt uns zu glauben:

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

Der JSON-Datensatz jedes Repositorys trägt dieselbe Ausfallzeit und dieselben Phasen, sodass später erkennbar bleibt, ob ein Snapshot cold oder hot entstanden ist, ohne es aus Zeiten zu erraten.

### Wann Sie cold wählen sollten

Hot ist die Voreinstellung und für die meisten Repositories die richtige Wahl. Ein Hot-Snapshot ist absturzkonsistent, also in dem Zustand, in dem ein Repository nach einem Stromausfall wäre, und kostet gar keine Ausfallzeit. Die meisten Datenbanken und Queues kommen damit von allein zurecht.

Cold ist für Daten gedacht, die sich während des Schreibens nicht sicher erfassen lassen. Eine Datenbank mit eigenem Write-Ahead-Log und Zustand im Arbeitsspeicher ist der klassische Fall. Sie tauschen eine kurze, gemessene Ausfallzeit gegen einen Snapshot, den die Anwendung ohne vorherige Reparatur öffnen kann.

### Was ein Cold-Lauf zurückweist

Das Zurückweisen ist das Feature. Ein Backup mit dem Etikett cold, das nie etwas stillgelegt hat, ist eine Lüge, die erst beim Restore auffliegt. Deshalb stuft renet einen Cold-Lauf nie stillschweigend auf hot herunter:

- **Container, die nicht gestoppt sind.** Nach dem Stoppen fragt renet den Docker-Socket des Repositorys, ob dort noch etwas läuft. Wenn ja, wird dieses Repository zurückgewiesen statt gesichert. Die Prüfung entscheidet im Zweifel gegen den Lauf: Ist der Socket nicht erreichbar oder die Containerliste nicht lesbar, gilt die Stilllegung als unbestätigt, und unbestätigt wird zurückgewiesen.
- **Eine Lizenz, die sich nicht lesen lässt.** Lizenzen werden vor der Ausfallzeit geprüft, nicht danach, denn ein Repository mit unlesbarer Lizenz hätte ohnehin nie etwas hochladen können. Ein solches Repository wird übersprungen, ohne gestoppt zu werden. Hat kein einziges der ausgewählten Repositories eine lesbare Lizenz, wird der ganze Lauf zurückgewiesen, bevor auch nur ein Container heruntergefahren wird.
- **Ein zweiter Cold-Lauf auf demselben Datastore.** Die Sperre gilt für den ganzen Datastore, und eine belegte Sperre wird sofort zurückgewiesen, ohne irgendetwas gestoppt zu haben. Zwei überlappende Läufe würden jeweils Container stoppen, die der andere für seine hält, und der zweite würde Repositories starten, die der erste noch einfriert. Den Lauf auszulassen und auf den nächsten zu warten, ist besser.

Wird ein Lauf unterbrochen, während die Container unten sind, etwa durch ein `systemctl stop` oder einen Neustart, startet renet sie vor dem Beenden wieder. Die Wiederherstellung auf der Maschine ist der Rückhalt: Sie erkennt ein Cold-Backup, dessen Besitzer verschwunden ist, und fährt diese Repositories wieder hoch.

## Speicher konfigurieren

Bevor Sie Backups übertragen, registrieren Sie einen Speicheranbieter. Rediacc unterstützt jeden rclone-kompatiblen Speicher: S3, B2, Google Drive und viele mehr.

### Aus rclone importieren

Wenn Sie bereits ein rclone-Remote konfiguriert haben:

```bash
rdc storage import rclone.conf
```

Dies importiert Speicherkonfigurationen aus einer rclone-Konfigurationsdatei in die aktuelle Konfiguration. Unterstützte Typen: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob und Swift.

### Speicher anzeigen

```bash
rdc storage list
```

## Ein Backup auf eine andere Maschine übertragen

Ein Repository per SSH auf eine zweite Maschine kopieren:

```bash
rdc repo push my-app --to-machine server-1
```

Das verschlüsselte Image wird mit der GLEICHEN GUID kopiert, es handelt sich also um ein Backup oder eine Migration, nicht um einen Fork. Für eine unabhängige Kopie zuerst `rdc repo fork` ausführen und dann den Fork pushen.

Für ein Backup zu einem bestimmten Zeitpunkt stattdessen Chunk-Storage verwenden: `rdc backup snapshot my-app` lädt nur die geänderten Zellen hoch, und `rdc backup restore my-app --at <snapshot>` holt jede davon zurück.

| Option | Beschreibung |
|--------|-------------|
| `--to-machine <machine>` | Zielmaschine für Maschine-zu-Maschine-Backup |
| `--dest <filename>` | Benutzerdefinierter Zieldateiname |
| `--checkpoint` | CRIU-Checkpoint vor dem Pushen erstellen (für Container mit Label `rediacc.checkpoint=true`). Ziel stellt automatisch bei `repo up` wieder her |
| `--force` | Ein vorhandenes Backup überschreiben |
| `--bwlimit <limit>` | Bandbreitenlimit für den rsync-Transfer (z. B. `10M`, `500K`) |
| `--tag <tag>` | Das Backup markieren |
| `-w, --watch` | Den Fortschritt der Operation beobachten |
| `--debug` | Ausführliche Ausgabe aktivieren |
| `--skip-router-restart` | Den Neustart des Route-Servers nach der Operation überspringen |

## Ein Backup von einer anderen Maschine abrufen

Ein Repository von der Maschine zurückholen, auf der es liegt:

```bash
rdc repo pull my-app --from-machine server-1
```

Um stattdessen aus dem Chunk-Storage wiederherzustellen, verwenden Sie
`rdc backup restore my-app --at <snapshot-id>`.

Pull verweigert das Überschreiben eines Repositorys, das aktuell **eingehängt** ist. Hängen Sie es zuerst aus, führen Sie den Pull aus, und bringen Sie es anschließend mit `rdc repo up` wieder hoch. Verzeichnisbasierte Repositories sind die Ausnahme: Sie synchronisieren sich im eingehängten Zustand direkt an Ort und Stelle.

| Option | Beschreibung |
|--------|-------------|
| `--from-machine <machine>` | Quellmaschine für Maschine-zu-Maschine-Wiederherstellung |
| `--force` | Vorhandenes lokales Backup überschreiben |
| `--bwlimit <limit>` | Bandbreitenlimit für den rsync-Transfer (z. B. `10M`, `500K`) |
| `-w, --watch` | Den Fortschritt der Operation beobachten |
| `--debug` | Ausführliche Ausgabe aktivieren |
| `--skip-router-restart` | Den Neustart des Route-Servers nach der Operation überspringen |

## Backups auflisten

Die Snapshots im Chunk-Storage auflisten:

```bash
rdc backup snapshot list my-app
```

Um Backup-Artefakte auf einer Maschine zu sehen:

```bash
rdc backup list -m server-1
```

Die Ausgabe ist eine vereinheitlichte Tabelle, die beide [Ordner für geplante Backups](#geplante-backups) (`hot/` und `cold/`) zusammenführt, sodass Sie jedes Backup in einer einzigen Ansicht sehen:

| Spalte | Bedeutung |
|---|---|
| `Mode` | `hot` oder `cold`. In welchem Ordner für geplante Backups dieser Eintrag liegt |
| `Name` | Aus Ihrer lokalen Konfiguration aufgelöster Repository-Name (Fallback auf GUID für Repos, die nicht in der Konfiguration sind) |
| `GUID` | Die Repository-GUID auf der Festplatte |
| `Size` | Menschenlesbare Größe der Backup-Datei |
| `Modified` | UTC-Zeitstempel vom Storage-Backend |

Das Auflisten eines Storage-Backends wurde zusammen mit dem rclone-Zweig eingestellt; der Befehl verweigert die Ausführung und nennt diese beiden Ersatzbefehle.

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

## Ein Repository nach dem anderen synchronisieren

Push und Pull wirken jeweils auf ein einzelnes Repository, adressiert über einen Ref (`name`, `name:tag` oder `name@machine`). Es gibt keine Form für "alle Repositories auf einmal": Führen Sie den Befehl einmal pro Repository aus.

### Auf eine andere Maschine übertragen

```bash
rdc repo push shop@server-1 --to-machine server-2
```

### Von einer anderen Maschine abrufen

```bash
rdc repo pull shop@server-1 --from-machine server-2
```

| Option | Beschreibung |
|--------|-------------|
| `--to-machine <machine>` | Zielmaschine für Maschine-zu-Maschine-Push |
| `--from-machine <machine>` | Quellmaschine für Maschine-zu-Maschine-Pull |
| `--force` | Ein vorhandenes Backup oder Repository überschreiben |
| `--checkpoint` | Vor dem Pushen einen CRIU-Checkpoint erstellen (nur Push) |
| `--up` | Das Repository nach dem Pull einhängen und bereitstellen (nur Pull) |
| `--bwlimit <limit>` | Bandbreitenlimit für den rsync-Transfer (z. B. `10M`) |
| `--delta-base <guid>` | Nur geänderte Blöcke gegenüber einer unveränderlichen Basis-GUID übertragen |
| `--debug` | Ausführliche Ausgabe aktivieren |
| `--skip-router-restart` | Den Neustart des Route-Servers nach der Operation überspringen |

## Geplante Backups

Rediacc verwendet benannte Backup-Strategien. Jede Strategie definiert einen Zeitplan, einen Backup-Modus, ein optionales Bandbreitenlimit und Dateifilter. Sie binden Strategienamen an Maschinen, um zu steuern, welche Backups dort ausgeführt werden.

### Backup-Modi

| Modus | Verhalten | Ausfallzeit |
|-------|-----------|-------------|
| `hot` | BTRFS-Snapshot wird bei laufenden Diensten erstellt (absturzkonsistent) | Keine |
| `cold` | Dienste gestoppt, Snapshot erstellt, Dienste neu gestartet, Snapshot hochgeladen (anwendungskonsistent) | Stop+Start-Fenster pro Repo, parallel über alle Repos. Siehe "Abschätzung der Cold-Backup-Ausfallzeit" unten. |

Verwenden Sie `hot` für Dienste, die absturzkonsistente Snapshots tolerieren. Verwenden Sie `cold`, wenn Sie garantierte Konsistenz benötigen und einen kurzen Neustart akzeptieren können.

### Cold-Backup-Semantik

Ein Cold-Backup läuft in drei Phasen pro enthaltenem Repository: **Stopp - Snapshot - Start**. Das Verstehen der Grenzen der Garantien hilft Betreibern, Teilausfälle frühzeitig zu erkennen.

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

- `rdc machine status <machine> --containers` zeigt den Laufzustand. Vergleichen Sie mit der erwarteten Menge.
- `/var/run/rediacc/cold-backup-<guid>.status.json` auf der Maschine. Prüfen Sie via `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` mit einem veralteten `startedAt` bedeutet, dass das letzte Backup nicht sauber abgeschlossen wurde.
- Protokolle des renet-Backup-Laufs (`journalctl -u renet-*` oder der direkte `rdc backup schedule`-Aufruf) geben eine abschließende Zusammenfassungszeile der Form `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]` aus. Ein nicht leeres `failed_repos` ist das grep-Ziel.

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
| Dienstag | Zweites Feuern | Stil verworfen (vorheriger Lauf ist noch aktiv) |
| Mittwoch | Drittes Feuern | Stil verworfen (vorheriger Lauf ist noch aktiv) |
| Donnerstag | Lauf endet mittags | Kein Nachholen; nächster Lauf ist Freitag 03:00 UTC |

Die `Persistent=true`-Direktive des Timers rettet diese Feuer **nicht**. `Persistent=true` wiederholt Feuer, die verpasst wurden, weil der Timer selbst inaktiv war (System aus, Timer deaktiviert). Feuer, die verworfen wurden, weil der Dienst beschäftigt war, sind weg.

Dieses Verhalten ist bewusst gewählt. Zwei parallele Cold-Backups gegen denselben Datastore würden um den BTRFS-Snapshot-Pfad, das rclone-Remote und die Per-Repo-Sidecars unter `/var/run/rediacc/cold-backup-<guid>.status.json` konkurrieren. Die Serialisierung hinter einem langen Lauf ist das sichere Ergebnis.

**Monitoring-Konsequenz.** Ein hängendes Backup (zum Beispiel rclone, das an einem Netzwerk-Blackhole hängenbleibt) verwirft still jedes nachfolgende Timer-Feuern. Der Scheduler gibt keinen Alarm aus. Beobachten Sie `systemctl show <unit> -p ActiveEnterTimestamp`: Wenn der Dienst länger als erwartet `activating` ist (zum Beispiel mehr als 48 h bei einem nächtlichen Timer), untersuchen Sie dies.

**Wenn Sie möchten, dass jedes geplante Feuern läuft**, wechseln Sie den Timer von `OnCalendar=<cron>` zu `OnUnitInactiveSec=<Intervall>`. Das feuert N Stunden nach Abschluss des vorherigen Laufs statt nach einem festen Wall-Clock-Zeitplan, sodass lange Läufe keine Verluste verursachen. Sie schieben nur den nächsten Lauf nach hinten. Der Kompromiss ist Zeitplan-Drift: Ihr nächtliches 03:00 wird zu "24 h nach Abschluss des letzten Laufs."

### Snapshots, Unterbrechungen und Pool-Speicher

Jeder Push arbeitet von einem kurzlebigen Datastore-Snapshot, sodass die hochgeladenen Daten konsistent sind, auch während Repositories weiter schreiben. Während das Backup läuft, referenziert dieser Snapshot weiterhin jeden Block, den er mit aktiven Repositories teilt: Löschungen und [Trims](/de/docs/repositories#speicherplatz-zuruckgewinnen-trim) geben bis zum Abschluss des Zyklus und zum Löschen des Snapshots weniger Pool-Speicher frei. Der [Speichergesundheitsbericht](/de/docs/monitoring#speichergesundheit) zeigt, wie viel Speicher Backup-Snapshots aktuell belegen.

Unterbrechungen sind sicher. Wird der Dienst gestoppt (oder die Maschine neu gestartet), bricht das Backup seine Übertragung ab und löscht seinen Snapshot vor dem Beenden; der nächste geplante Lauf setzt dort fort, wo er aufgehört hat, da unveränderte Dateien per Prüfsumme übersprungen werden. Wird der Prozess zu hart beendet, um aufzuräumen (Stromausfall), wird der verwaiste Snapshot vom Storage-Maintainer innerhalb von Minuten automatisch erkannt und entfernt.

### Strategie definieren

Der kanonische Standard ist eine Aufteilung in zwei Strategien: ein schneller stündlicher Hot-Stream, der jedes Repo erfasst, und ein langsamerer wöchentlicher Cold-Stream, der anwendungskonsistente Snapshots erstellt. Die beiden Strategien schreiben in unterschiedliche Speicher-Unterordner (`hot/` und `cold/`), sodass sich Backups nie vermischen.

```bash
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

Der `--exclude`-Filter der Cold-Strategie ist der empfohlene Notausgang für sehr große Repos, die nicht in Ihr wöchentliches Wartungsfenster passen. Die stündliche Hot-Strategie deckt sie weiterhin ab; Cold überspringt sie einfach. Repository-Namen in `--exclude` werden gegen den lokalen Konfigurationsnamen des Repos abgeglichen (ohne `:tag`).

| Option | Beschreibung |
|--------|-------------|
| `<strategy>` (positional) | Name der Strategie (wird zur Maschinenbindung verwendet) |
| `--destination <storage>` | Speicheranbieter zum Hochladen |
| `--cron <expression>` | Cron-Ausdruck (z. B. `"0 2 * * *"` für täglich um 2 Uhr) |
| `--mode <hot\|cold>` | Backup-Modus |
| `--bwlimit <limit>` | Bandbreitenlimit für Uploads (z. B. `10M`) |
| `--include <pattern>` | Einschlussfilter (wiederholbar) |
| `--exclude <pattern>` | Ausschlussfilter (wiederholbar) |
| `--enable` / `--disable` | Strategie aktivieren oder deaktivieren |

### Strategien anzeigen

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### Strategie entfernen

```bash
rdc backup strategy remove weekly-cold
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

> **Bindung ist nur lokale Konfiguration.** Eine Strategie zu definieren und an eine Maschine zu binden, hat keine Auswirkung auf die Maschine. Führen Sie `rdc backup schedule -m <machine>` aus (siehe [Zeitplan auf Maschine deployen](#zeitplan-auf-maschine-deployen)), um die systemd-Timer zu deployen, und führen Sie den Befehl nach jeder Strategie- oder Bindungsänderung erneut aus.

## Hot vs. Cold und Repo-Filterung im Vergleich

### Hot vs. Cold auf einen Blick

| | Hot | Cold |
|---|-----|------|
| **Konsistenz** | Absturzkonsistent (BTRFS-Snapshot bei laufenden Diensten) | Anwendungskonsistent (Stopp - Snapshot - Start) |
| **Ausfallzeit** | Keine | Stop+Start-Fenster pro Repo (typischerweise 5-120 s) |
| **Geeignete Häufigkeit** | Hoch (z. B. stündlich) | Niedrig (z. B. täglich oder wöchentlich) |
| **Typischer Einsatz** | Häufiges Sicherheitsnetz | Geplantes Backup mit garantierter Konsistenz |

**Hot** ist die richtige Standardwahl für hochfrequente Läufe. Dienste laufen weiter, während der Snapshot erstellt wird, sodass das Backup-Fenster Benutzer nicht unterbricht. Der Snapshot ist absturzkonsistent: Er entspricht dem, was Sie nach einem unsauberen Herunterfahren erhalten würden. Für die meisten modernen Datenbanken und Message-Queues ist dies akzeptabel.

**Cold** ist geeignet, wenn Sie einen garantiert anwendungskonsistenten Snapshot benötigen und einen kurzen Neustart pro Repo akzeptieren können. Dienste werden vor dem Snapshot gestoppt und vor Beginn des Uploads neu gestartet, sodass ein langsamer oder fehlgeschlagener Upload das Ausfallzeitfenster nie verlängert. Das vollständige Garantiemodell finden Sie unter [Cold-Backup-Semantik](#cold-backup-semantik).

### Repos pro Strategie filtern

Jede Strategie kann `--include`- und `--exclude`-Filter tragen. Repository-Namen, die einem `--exclude`-Muster entsprechen, werden für diese Strategie übersprungen; `--include` beschränkt den Lauf auf genau diese Namen. Filter passen auf den lokalen Konfigurationsnamen des Repositories (ohne `:tag`).

```bash
# Hot-Strategie: alles stündlich sichern
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Cold-Strategie: alles wöchentlich sichern, außer dem großen abgeleiteten Datensatz
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude analytics-demo \
  --enable
```

### Wann ein Repo aus der hochfrequenten Hot-Strategie ausschließen

Schließen Sie ein Repository aus dem hochfrequenten Lauf aus, wenn:

- Das Repo groß ist und **vollständig aus Quelldaten regeneriert werden kann**, die bereits auf dem Volume liegen, sodass jedes stündliche Backup erhebliche Bandbreite verschwendet, ohne echten Wiederherstellungswert zu bieten.
- Der Backup-Lauf bei Ihrer verfügbaren Upload-Geschwindigkeit sein eigenes Zeitplan-Intervall überschreiten würde.

**Beispiel.** Ein `analytics-demo`-Repository enthält ungefähr 114 GB abgeleitete Postgres-Tabellen, die vollständig aus rohen CSV-Dump-Dateien, die bereits im selben Volume gespeichert sind, neu aufgebaut werden können. Bei einem Upload-Limit von 6 MB/s dauert ein einzelnes Hot-Backup dieses Repos über 5 Stunden. Wenn dies stündlich läuft, ist jeder Lauf noch aktiv, wenn der nächste feuert, was dazu führt, dass jeder nachfolgende Lauf still verworfen wird (siehe [Lange Läufe und überlappende Zeitpläne](#lange-läufe-und-überlappende-zeitpläne)). Es aus `hourly-hot` auszuschließen und in `weekly-cold` zu belassen bedeutet, dass es einmal pro Woche gesichert wird statt gar nicht.

> **Wenn die Daten rein regenerierbar sind**, überlegen Sie, ob Sie sie überhaupt sichern müssen. Eine Alternative ist, nur die rohen Quelleingaben (in diesem Beispiel die CSV-Dumps) zu sichern und die abgeleitete Kopie ganz zu überspringen. Ein wöchentliches Cold-Backup der Quelleingaben ist viel kleiner und für eine Wiederherstellung vollständig ausreichend.

Repos, die aus keiner der beiden Strategien ausgeschlossen sind, erscheinen sowohl in den `hot/`- als auch in den `cold/`-Speicher-Unterordnern. Die zusammengeführte Ausgabe von `rdc backup list` zeigt beide Zeilen, sodass Sie überprüfen können, welche Streams welche Repos abdecken.

## Backup-Operationen

### Zeitplan auf Maschine deployen

Die gebundenen Strategien als systemd-Timer auf eine Maschine übertragen:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

Das Deploy ist ein State-Reconciler. Er liest die aktuellen Unit-Dateien und den systemd-Zustand auf der Maschine, vergleicht sie mit dem, was die Konfiguration erzeugen würde (SHA-256 pro Datei), und berührt nur Units, deren Inhalt sich tatsächlich geändert hat. Ein erneuter Aufruf ohne Konfigurationsänderungen ist ein No-op: keine Writes, kein `daemon-reload`, kein Timer-Churn.

`--dry-run` gibt den Plan pro Strategie aus (`created`, `updated (service, timer, env)`, `unchanged`, `removed`), ohne die Maschine anzufassen. In Kombination mit `--debug` werden auch die generierten Unit-Inhalte ausgegeben; rclone-Tokens werden redigiert.

Wenn gerade ein Backup für eine Strategie läuft, die aktualisiert oder entfernt werden soll, bricht das Deploy sofort ab und weist darauf hin, das Backup abzubrechen oder `--force` zu übergeben. Mit `--force` behält der laufende Vorgang seine In-Memory-Unit, und die neue Konfiguration greift beim nächsten Timer-Tick, sodass das laufende Backup niemals beendet wird.

`--reset-failed` ist opt-in. Wenn übergeben, löscht es nach einem erfolgreichen Deploy den Failed-Status auf berührten Services. Standardmäßig aus, damit vorherige Fehlersignale für Alerting sichtbar bleiben.

### Backup jetzt ausführen

Ein Backup sofort auslösen, ohne auf den Timer zu warten. Funktioniert auch ohne deployte Timer via `systemd-run` für Ad-hoc-Ausführung:

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### Backup-Status anzeigen

Den aktuellen Status der Backup-Timer und neueste Job-Ergebnisse anzeigen:

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### Laufendes Backup abbrechen

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## Repository-Migration

Ein Repository von einer Maschine auf eine andere verschieben:

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| Option | Beschreibung |
|--------|-------------|
| `<ref>` (positional) | Repository-Ref, das migriert werden soll; das `@machine` darin benennt die Quelle |
| `--to <place>` | Zielmaschine oder Cluster |
| `--provision` | Repository auf der Zielmaschine provisionieren, bevor übertragen wird |
| `--checkpoint` | CRIU-Checkpoint vor der Migration erstellen |
| `--skip-dns` | DNS-Aktualisierung nach der Migration überspringen |
| `--bwlimit <limit>` | Bandbreitenlimit für die Übertragung (z. B. `50M`) |

Die Migration überträgt die verschlüsselten Repository-Daten via rsync. Das Quell-Repository bleibt intakt, bis Sie es explizit entfernen.

## Speicher durchsuchen

`rdc storage browse` und `rdc storage import` sind die Ausnahme von dieser Einstellung: Sie starten Ihr eigenes rclone aus PATH statt einer eingebetteten Kopie und bleiben der Weg, um ein vor der Umstellung geschriebenes Archiv zu lesen.

```bash
rdc storage browse my-storage
```

Das Durchsuchen ist nur lesend. Push zu, Pull von und Auflisten eines Storage-Backends sind eingestellt; jeder Befehl verweigert die Ausführung und nennt den Chunk-Storage-Befehl, der ihn ersetzt.

## Bewährte Methoden

- Tägliche Cold-Backups für anwendungskonsistente Snapshots kritischer Daten einplanen
- Hot-Backups für hochfrequente Snapshots verwenden, bei denen keinerlei Ausfallzeit akzeptabel ist
- Wiederherstellungen regelmäßig testen, um die Backup-Integrität zu überprüfen
- Mehrere Speicheranbieter für kritische Daten verwenden (z. B. S3 + B2)
- Zugangsdaten sicher aufbewahren; Backups sind verschlüsselt, aber das LUKS-Credential wird zur Wiederherstellung benötigt
