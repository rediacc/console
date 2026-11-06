---
title: Überwachung
description: 'Maschinengesundheit, Container, Dienste, Repositories und Diagnose überwachen.'
category: Guides
tags:
  - operations
subcategory: operations
order: 9
language: de
sourceHash: "6e4968522e118c98"
sourceCommit: "9b8aa220de6eb4f7c7b7783456af6871202c8305"
---

# Überwachung

Rediacc bietet integrierte Überwachungsbefehle, um Maschinengesundheit, laufende Container, Dienste, Repository-Status und Systemdiagnose zu inspizieren.

## Maschinengesundheit

Einen vollständigen Gesundheitsbericht für eine Maschine abrufen:

```bash
rdc machine health server-1
```

Dieser meldet:
- **System**: Laufzeit, Arbeitsspeicher (Warnung über 80 %, Fehler über 90 %), Festplatten- und Datastore-Auslastung (Warnung über 85 %, Fehler über 95 %)
- **Container**: Anzahl laufender, gesunder und ungesunder Container; ein Container in einer `Restarting`-Schleife ist kritisch
- **Dienste**: fehlgeschlagene systemd-Units (ein Fehler) und Units, die ständig neu starten (kritisch)
- **Speicher**: SMART-Gesundheitsstatus (eine ausfallende Festplatte ist kritisch) und Festplattentemperatur
- **Repositories**: Autostart-Repositories, die nicht eingehängt sind, und die Dateisystemauslastung jedes Repositorys (Warnung über 85 %, Fehler über 95 %)
- **Backups**: Repositories ohne Backup seit über 10 Tagen, hinter ihrem Zeitplan oder Ziel zurück oder mit fehlgeschlagener letzter Verifizierung
- **Lizenzen**: abgelaufene, fehlende, nicht passende oder ungültige Repository-Lizenzen und Lizenzen, die erneuert werden müssen
- **Renet-Prozesse**: Daemons, die noch eine ersetzte renet-Binärdatei ausführen
- **Repository-Gesundheit**: das `health()`-Ergebnis jedes eingehängten Repositorys (siehe unten)
- **Zertifikate**: Zertifikate des Proxys kurz vor dem Ablauf und gemeinsam genutzte ACME-Challenge-CNAMEs
- **Probleme**: Erkannte Probleme

Der Exit-Code ist das Urteil: `0` gesund, `1` Warnung, `2` Fehler, `3` kritisch (eine ausfallende Festplatte oder ein Container oder Dienst in einer Neustart-Schleife). Verwenden Sie `--output json` für maschinenlesbare Ausgabe; sie enthält `repo_health` (ein Bericht pro Repository) und `findings`, jeweils mit Code, Schweregrad (`info`, `warning`, `error` oder `critical`), Betreff, Detail und, wo es eine Lösung gibt, `fix` (siehe [Reparatur](#repair)).

## Repository-Gesundheit

Ein Rediaccfile kann eine Funktion `health()` definieren, die die eigenen Dienste des Repositorys prüft ([Dienste](/de/docs/services)): Exit `0` ok, `1` Warnung, `2` Fehler. Für ein Repository ausführen:

```bash
rdc repo health my-app@server-1
```

Der Befehl endet mit der schlechtesten Stufe über alle Rediaccfiles des Repositorys. Ein Repository, in dem kein Rediaccfile `health()` definiert, gibt **keine Prüfung** aus und endet mit `0`; es wird nie als gesund gemeldet. Ein `health()` mit Zeitüberschreitung, das beendet wird oder mit einem anderen Code endet, ist ein Fehler, ebenso ein fehlgeschlagener Verbindungsaufbau zur Maschine (Exit `2`).

`rdc machine health` führt das `health()` jedes eingehängten Repositorys in einem Aufruf aus und übernimmt die schlechteste Stufe in den eigenen Exit-Code, mit einem Befund pro Repository als Warnung (`repo.health.warning`) oder Fehler (`repo.health.error`). Repositories ohne Prüfung werden aufgelistet, aber nicht bewertet. Kennt das renet der Maschine noch keine Repository-Gesundheitsprüfungen, lautet das Ergebnis eine Warnung, `renet.repo-health.unsupported`, bis `rdc machine setup` es aktualisiert.

## Zertifikatsablauf und ACME-Challenges

`rdc machine health` liest die ACME-Zertifikate des Proxys und meldet `cert.expiry.near` für jedes Zertifikat mit weniger als 21 Tagen bis zum Ablauf (eine Warnung) oder weniger als 7 Tagen (ein Fehler). Der Proxy erneuert 30 Tage vorher, ein Zertifikat unter 21 Tagen bedeutet also, dass seine Erneuerung seit mindestens neun Tagen fehlschlägt.

Außerdem meldet es `acme.challenge.cname-shared`, wenn der Eintrag `_acme-challenge.<name>` eines Zertifikatsnamens über einen CNAME auf einen Namen verweist, der selbst kein `_acme-challenge.`-Name ist, oder wenn zwei Namen am selben Namen enden. Ein Wildcard-Eintrag, der ein CNAME ist, erzeugt diese Form: Jede Challenge landet auf einem Namen, und die Erneuerungen kollidieren. Eine bewusste Delegation (zum Beispiel `_acme-challenge.mail.example.com` mit Verweis auf `_acme-challenge.mail.example.io`) wird nicht gemeldet; jede andere gewollte Delegation gehört in `ACME_DELEGATED_NAMES` (eine kommagetrennte Liste von Zertifikatsnamen) in der `config.env` des Proxys. Ein Name, dessen Challenge-Kette nicht aufgelöst werden konnte (DNS-Fehler oder Zeitüberschreitung), wird als `acme.challenge.unknown` gemeldet, eine Warnung, weil die Prüfung für ihn nicht gelaufen ist.

## Reparatur

Jeder Befund trägt einen Code und, wo es eine sichere Lösung gibt, ein `fix` mit `action`, einer Sicherheits-`class` und `window_only`. `rdc machine health` bleibt schreibgeschützt; `rdc machine repair` ist der Befehl, der handelt:

```bash
rdc machine repair server-1 --dry-run     # list what would run
rdc machine repair server-1               # run the auto-safe fixes, then re-check
rdc machine repair server-1 --code cert.expiry.near
```

| Klasse | Bedeutung |
|---|---|
| `auto-safe` | Läuft standardmäßig: einen Container oder Traefik neu starten, trimmen und bereinigen, den ACME-Anker schreiben |
| `auto-with-backup` | Läuft nur mit `--with-backup`, nach einem erfolgreichen Snapshot des Repositorys; ein fehlgeschlagener Snapshot bricht die Lösung ab |
| `operator-only` | Läuft nie. Der Befehl gibt den genauen Befehl aus, der von Hand auszuführen ist. Alles, was benannte Daten löscht oder Geld kostet, gehört hierher |

`window_only` ist eine zusätzliche Bedingung zur Klasse: Die Lösung läuft nur innerhalb des Wartungsfensters der Maschine, `HH:MM-HH:MM` in UTC (es darf über Mitternacht reichen). Eine Maschine ohne Fenster führt diese Lösungen nie von selbst aus; `--window-override` führt sie von Hand aus. Das Fenster setzen oder löschen:

```bash
rdc machine repair server-1 --set-window 00:00-03:00
rdc machine repair server-1 --set-window off
```

Jede Lösung prüft zuerst, ob ihr Befund noch besteht, sodass ein zweiter Lauf nichts zu tun meldet. Lösungen, die auf dasselbe wirken, laufen einmal (ein Traefik-Neustart deckt alle Zertifikate ab). Jede Lösung wird mit dem Tag `rediacc-repair` im Journal der Maschine und im JSON unter `actions` (`code`, `subject`, `action`, `class`, `result`, `before`, `after`) protokolliert, und der Lauf endet mit einer vollständigen erneuten Prüfung. Der Exit-Code ist `0`, wenn nichts übrig bleibt, `1`, wenn Warnungen oder Operator-only-Punkte übrig bleiben, und `2`, wenn ein Fehler übrig bleibt oder eine Lösung fehlschlug.

| Befund | Lösung | Klasse |
|---|---|---|
| `datastore.usage.high`, `repo.disk.high` | Trimmen, dann gestoppte Container, anonyme verwaiste Volumes und ungenutzte Images bereinigen | auto-safe |
| `container.unhealthy`, `container.restart-loop` | Den Container neu starten | auto-safe |
| `renet.binary.replaced` | Die betroffenen Repository-Supervisoren neu starten (`rdc machine restart-services --include-docker`, darauf beschränkt) | auto-safe, nur im Wartungsfenster |
| `cert.expiry.near` | Traefik neu starten, damit es die Erneuerung wiederholt | auto-safe |
| `acme.challenge.cname-shared` | Den ACME-Anker schreiben (siehe unten) | auto-safe |
| `repo.health.warning`, `repo.health.error` | Das `repair()` des Repositorys ausführen ([Dienste](/de/docs/services)) | die Klasse, die das Rediaccfile deklariert |
| `repo.unmounted`, `service.failed`, `service.restart-loop`, `backup.*`, `license.*`, `renet.repo-health.unsupported` | Als auszuführender Befehl ausgegeben | operator-only |

Befunde ohne Lösung (SMART-Fehler, Temperatur, Arbeitsspeicher, die Systemfestplatte, eine fehlgeschlagene Verifizierung) werden gemeldet und dem Operator überlassen.

Die Bereinigung berührt den Hub nie: Container mit dem Label `rediacc.hub.*` und Volumes mit dem Label `rediacc.hub.user` oder dem Namen `rediacc-hub-home-*` sind ausgenommen, sodass das Home-Verzeichnis eines Hub-Benutzers jede Rückgewinnung übersteht. Ein Rest, den Trimmen und Bereinigen nicht freigeben können (benannte Volumes, große Anwendungsdaten), bleibt eine Entscheidung des Operators.

### Repository-Reparatur

```bash
rdc repo repair my-app@server-1 --dry-run
rdc repo repair my-app@server-1
```

`rdc repo repair` führt die `repair()`-Funktionen des Repositorys mit denselben Klassen aus: `auto-safe` läuft, `auto-with-backup` braucht `--with-backup`, und ein nicht deklariertes (`operator-only`) `repair()` läuft erst nach beantworteter Rückfrage oder mit `--yes`. Danach läuft `health()` erneut, und der Exit-Code folgt der Stufe, bei der es endet: `0` ok oder keine Prüfung, `1` Warnung, `2` Fehler oder ein fehlgeschlagenes `repair()`.

### Der ACME-Anker

Ein Wildcard-DNS-Eintrag, der ein CNAME ist, lässt jeden Namen `_acme-challenge.<host>` ihm folgen, sodass alle Challenges auf einem Namen landen und die Erneuerungen kollidieren (`acme.challenge.cname-shared`). Die Lösung schreibt über den Cloudflare-Token des Proxys an jedem kollidierenden `_acme-challenge.<name>` einen TXT-Eintrag mit dem Wert `rediacc-acme-anchor` und startet dann Traefik neu. Ein expliziter Eintrag nimmt den Namen aus dem Einflussbereich des Wildcards, sodass die Challenge dort landet, wo sie hingehört. Die Lösung fügt nur Einträge hinzu, und ein vorhandener Anker bleibt unverändert.

In `ACME_DELEGATED_NAMES` (eine kommagetrennte Liste von Zertifikatsnamen in der `config.env` des Proxys) aufgeführte Namen sind bewusste Delegationen: Sie werden nie verankert und nie gemeldet. Hat der Proxy keinen brauchbaren Cloudflare-Token, weicht die Lösung auf `LEGO_DISABLE_CNAME_SUPPORT=true` in `config.env` aus, aber nur, wenn keine delegierten Namen deklariert sind, weil diese Variable das Folgen von CNAMEs für jeden Namen abschaltet; bei deklarierter Delegation bleibt der Befund operator-only. Dieselbe Lösung läuft bei jeder Proxy-Installation (`rdc machine infra push`) und für sich allein mit `renet proxy acme-fix` auf der Maschine.

## Container auflisten

Alle laufenden Container über alle Repositories auf einer Maschine anzeigen:

```bash
rdc machine status server-1 --containers
```

| Spalte | Beschreibung |
|--------|-------------|
| Name | Container-Name |
| Status | Laufzeit oder Beendigungsgrund |
| Zustand | Laufend, beendet usw. |
| Gesundheit | Gesund, ungesund, keine |
| CPU | CPU-Auslastung in Prozent |
| Speicher | Speicherauslastung / Limit |
| Repository | Welchem Repository der Container gehört |

Optionen:
- `--health-check`, Aktive Gesundheitsprüfungen an Containern durchführen
- `--output json`, Maschinenlesbare JSON-Ausgabe

Die JSON-Ausgabe enthält vollständige Containerdetails (`labels`, `port_mappings`, `image`, `id`) sowie `repository` (aufgelöster Name), `repository_guid` (ursprüngliche GUID), `domain` und `autoRoute`.

## Dienste auflisten

Systemd-Dienste im Zusammenhang mit Rediacc auf einer Maschine anzeigen:

```bash
rdc machine status server-1 --services
```

| Spalte | Beschreibung |
|--------|-------------|
| Name | Dienstname |
| Zustand | Aktiv, inaktiv, fehlgeschlagen |
| Unterzustand | Laufend, beendet usw. |
| Neustarts | Neustart-Zähler |
| Speicher | Speicherauslastung des Dienstes |
| Repository | Zugehöriges Repository |

Optionen:
- `--stability-check`, Instabile Dienste markieren (fehlgeschlagen, >3 Neustarts, automatischer Neustart)
- `--output json`, Maschinenlesbare JSON-Ausgabe

Die JSON-Ausgabe enthält vollständige Dienstdetails mit `repository` (aufgelöster Name) und `repository_guid` (ursprüngliche GUID).

## Repositories auflisten

Repositories auf einer Maschine mit detaillierten Statistiken anzeigen:

```bash
rdc machine status server-1 --repositories
```

| Spalte | Beschreibung |
|--------|-------------|
| Name | Repository-Name |
| Größe | Disk-Image-Größe |
| Eingebunden | Eingebunden oder ausgehängt |
| Docker | Docker-Daemon läuft oder gestoppt |
| Container | Container-Anzahl |
| Festplattennutzung | Tatsächliche Festplattennutzung innerhalb des Repositories |
| Geändert | Letzte Änderungszeit |

Optionen:
- `--search <text>`, Nach Name oder Einbindungspfad filtern
- `--output json`, Maschinenlesbare JSON-Ausgabe

Die JSON-Ausgabe enthält `name` (aufgelöst) und `guid` (ursprüngliche GUID) und verschachtelt für jedes Repository die Arrays `containers` (mit `domain`, `autoRoute`, `repository`/`repository_guid`) und `services`.

## Speichergesundheit

BTRFS-Fragmentierung und Reflink-Freigabe über alle Repositories auf einer Maschine prüfen:

```bash
rdc machine status server-1 --storage-health
```

| Spalte | Beschreibung |
|--------|-------------|
| Quota | Die maximale Größe des Repositories (seine Wachstumsobergrenze, gesetzt bei der Erstellung oder durch resize/auto-grow) |
| Allocated | Was das Sparse-Image aktuell tatsächlich im Pool belegt |
| Unique | Tatsächlich einzigartige Daten, die nur diesem Repository gehören |
| Shared | Datenblöcke, die über Repositories via BTRFS-Reflinks wiederverwendet werden (kostenlose Kopien) |
| Reclaimable | Die Lücke zwischen belegtem und genutztem Speicher, die [`repo trim`](/de/docs/repositories#reclaim-space-trim) an den Pool zurückgeben kann. Zeigt `-` für unmountete Repositories |
| Discards | Ob das verschlüsselte Volume Discards durchleitet (`on` für jedes Repository, das mit einer aktuellen Version gemountet wurde) |
| Divergence | Prozentualer Anteil des Images, der einzigartig für dieses Repository ist und nicht geteilt wird (höher bedeutet mehr rückgewinnbaren Speicher bei Löschung) |
| Frag | Extents pro GB im copy-on-write-Image (nur informativ) |

Quota und Allocation sind bewusst unterschiedliche Werte: Ein Repository mit 20 GB Quota, das 6 GB Daten speichert, kostet den Pool nur das tatsächlich Belegte. Der Pool kann daher mehr Quota versprechen als er physisch besitzt, und die Reclaimable-Spalte zeigt, wie viel der Allocation jedes Repositories nicht mehr genutzt wird und zurückgetrimmt werden kann.

Unterhalb der Tabelle liefert eine Pool-Zusammenfassung den Füllstand des Datastores und wie viel Speicher Backup-Snapshots derzeit belegen:

```
Pool: 265.4 GB used, 95.2 GB free (73.6% full)
Backup snapshots pin 2.1 GB (1 active, 0 stale; stale ones are removed by 'rdc machine prune')
```

Während ein Backup läuft, referenziert sein Snapshot weiterhin jeden Block, den er mit aktiven Repositories teilt; Löschungen und Trims geben daher weniger Pool-Speicher frei, bis der Backup-Zyklus abgeschlossen und der Snapshot gelöscht ist. Veraltete Snapshots aus unterbrochenen Backups werden vom Storage-Maintainer innerhalb von Minuten automatisch entfernt.

Die Zusammenfassung zeigt Gesamteinsparungen durch BTRFS-Reflinks:

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **Virtuelle Größe** ist die Summe aller Repository-Image-Größen. Dies zeigt, wie die Repositories aussehen, zählt jedoch gemeinsam genutzte Blöcke via Reflinks doppelt.
- **Einzigartige Daten** sind der tatsächlich verbrauchte Speicher durch Repository-Daten, die nur in einem Repository vorhanden sind. Dies ist das, was beim Löschen eines Repositories freigegeben wird.
- **Geteilt** sind Daten, die über Repositories via BTRFS-Reflinks wiederverwendet werden. Das Forken eines Repositories erstellt Reflink-Kopien, die Blöcke teilen, bis eine Seite neue Daten schreibt; dann divergieren die Blöcke.
- **Effizienz** ist der Prozentsatz der via Reflinks wiederverwendeten Daten. Höher ist besser. Eine Maschine mit vielen Forks desselben Parent-Repositories zeigt eine Effizienz nahe 100%.

Die Frag-Spalte ist nur informativ. Sie zählt Extents der copy-on-write-Image-Datei, nicht die Dateien, die deine Anwendung darin liest, daher liest sie unter normalen zufälligen Schreib-Workloads (Datenbanken, Container-Layer) hoch und sagt auf SSD-gestütztem Speicher nichts über die Leseperformance aus. Rediacc bietet bewusst keinen Defragmentierungsbefehl an: `btrfs filesystem defragment` hebt die Reflinks von refgelinkten Forks und Snapshots auf, was auf einem nahezu vollen Pool die Nutzung dramatisch aufblähen kann, während Benchmarks keinen messbaren Lesegewinn zeigen. Die vollständigen Messungen und Begründungen findest du unter [Deine Fragmentierungszahl sieht erschreckend aus. Ich habe gemessen, was sie kostet.](/de/blog/i-benchmarked-btrfs-fragmentation).

Der Scan läuft parallel und dauert je nach Anzahl und Größe der Repositories 5-15 Sekunden. Wenn `--storage-health` nicht angegeben ist, erscheint nach der Abfrageausgabe ein einzeiliger Hinweis als Erinnerung.

## BTRFS-Scrub

Rediacc plant automatisch einen wöchentlichen BTRFS-Scrub auf jeder Maschine. Der Scrub liest jeden Datenblock im Datastore, prüft Prüfsummen und meldet Korruptionen. Dies erkennt stille Datenkorrumpierung (Bitrot), bevor sie sich auf Backups und Forks ausbreitet.

Der Scrub läuft jeden Sonntag um 02:00 Uhr Ortszeit (Maschinenzeitszone) mit einer zufälligen Verzögerung von bis zu 1 Stunde. Er läuft mit niedrigster I/O-Priorität (`ionice idle`, `nice 19`), sodass er laufende Dienste nicht beeinträchtigt. Auf SSD-gestützten Maschinen sind etwa 8 Minuten pro 100 GB Datastore zu erwarten.

Der Scrub-Timer wird automatisch beim ersten Daemon-Start nach einem renet-Upgrade installiert. Wenn sich die Scrub-Richtlinie in einer zukünftigen renet-Version ändert, aktualisiert sie sich beim nächsten Daemon-Start ohne Benutzereingriff.

### Scrub-Status

Das Ergebnis des letzten Scrubs wird außerhalb des BTRFS-Volumes gespeichert (unter `/var/lib/rediacc/scrub-last-result.json`), sodass es auch bei Problemen mit dem Volume lesbar bleibt. Die Ausgabe von `rdc machine status --system` enthält ein `scrub_status`-Feld:

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| Status | Bedeutung |
|--------|-----------|
| `ok` | Letzter Scrub abgeschlossen ohne Fehler |
| `never_run` | Scrub noch nicht gelaufen (Timer gerade installiert) |
| `overdue` | Letzter Scrub war vor mehr als 14 Tagen |
| `errors_found` | Scrub hat Prüfsummen-Fehler gefunden (prüfen Sie die Zähler `total_errors` und `uncorrectable`) |
| `failed` | Scrub-Prozess mit Nicht-Null-Code beendet |

Wenn `uncorrectable` größer als null ist, können die betroffenen Blöcke nicht automatisch repariert werden (Einzeldisk-BTRFS hat keine redundante Kopie). Stellen Sie das betroffene Repository aus dem neuesten Backup wieder her.

### Manueller Scrub

Um einen Scrub sofort auszuführen (z.B. nach einem Stromausfall oder einer Festplattenmigration):

```bash
rdc term connect server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

Das Ergebnis wird in derselben JSON-Datei gespeichert und ist sofort im nächsten `rdc machine status --system` sichtbar.

## Maschinenübersicht

Einen vollständigen Überblick über eine Maschine einschließlich Bereitstellungsinformationen erhalten:

```bash
rdc machine status server-1
```

Dies liefert:
- Hostname und Laufzeit
- Speicher-, Festplatten- und Datastore-Auslastung
- Gesamtzahl der Repositories, Anzahl der eingebundenen und Anzahl der Repositories, deren Docker-Daemon antwortet
- Detaillierte Informationen pro Repository

Verwenden Sie `--output json` für maschinenlesbare Ausgabe.

## Verbindung testen

SSH-Konnektivität zu einer Maschine überprüfen:

```bash
rdc term connect server-1 -c "hostname"
```

Der Befehl gibt bei Erfolg den Remote-Hostnamen aus, andernfalls einen
Verbindungsfehler, und prüft damit DNS, den SSH-Port und die
Schlüsselauthentifizierung in einem Schritt.

## Diagnose (doctor)

Eine vollständige Diagnoseprüfung Ihrer Rediacc-Umgebung durchführen:

```bash
rdc doctor
```

| Kategorie | Prüfungen |
|-----------|-----------|
| **Umgebung** | Node.js-Version, CLI-Version, SEA-Modus, Go-Installation, Docker-Verfügbarkeit |
| **Renet** | Binary-Standort, Version, CRIU, rsync, SEA eingebettete Assets |
| **Konfiguration** | Aktive Konfiguration, Adapter, Maschinen, SSH-Schlüssel |
| **Virtualisierung** | Prüft, ob Ihr System lokale virtuelle Maschinen ausführen kann (`rdc ops`) |

Jede Prüfung meldet **OK**, **Warnung** oder **Fehler**. Verwenden Sie dies als ersten Schritt bei der Fehlerbehebung jeglicher Probleme.

Exit-Codes: `0` = alles bestanden, `1` = Warnungen, `2` = Fehler.

## Bereitschaftsprüfung der Dienste

Während `repo up` wartet renet darauf, dass HTTP-Dienste Verbindungen akzeptieren, bevor sie als bereit deklariert werden. Die Wartelogik berücksichtigt dabei Docker-Healthchecks:

- Container, die Docker als **healthy** meldet, werden sofort als bereit akzeptiert, ohne TCP-Probe.
- Container, die sich noch innerhalb des `start_period` ihres Healthchecks befinden, lösen eine informative Meldung aus, keine Warnung; der Proxy versucht weiterhin, die Verbindung herzustellen.
- Compose-Dienste ohne laufenden Container (etwa hinter einem inaktiven Profil) werden übersprungen.
- Alle anderen Dienste werden per TCP für bis zu 15 Sekunden geprüft (änderbar mit `REDIACC_READINESS_TIMEOUT` in Sekunden).

Wer auf langsam startenden Diensten einen [Docker-Healthcheck](https://docs.docker.com/reference/dockerfile/#healthcheck) definiert, gibt renet ein verlässliches Bereitschaftssignal und vermeidet überflüssige Probe-Meldungen in der Deploy-Ausgabe.
