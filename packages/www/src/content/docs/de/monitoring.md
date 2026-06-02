---
title: Überwachung
description: 'Maschinengesundheit, Container, Dienste, Repositories und Diagnose überwachen.'
category: Guides
order: 9
language: de
sourceHash: "1d0af1a74a12d49e"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Überwachung

Rediacc bietet integrierte Überwachungsbefehle, um Maschinengesundheit, laufende Container, Dienste, Repository-Status und Systemdiagnose zu inspizieren.

## Maschinengesundheit

Einen vollständigen Gesundheitsbericht für eine Maschine abrufen:

```bash
rdc machine health --name server-1
```

Dieser meldet:
- **System**: Laufzeit, Festplattennutzung, Datastore-Auslastung
- **Container**: Anzahl laufender, gesunder und ungesunder Container
- **Speicher**: SMART-Gesundheitsstatus
- **Probleme**: Erkannte Probleme

Verwenden Sie `--output json` für maschinenlesbare Ausgabe.

## Container auflisten

Alle laufenden Container über alle Repositories auf einer Maschine anzeigen:

```bash
rdc machine containers --name server-1
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
rdc machine services --name server-1
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
rdc machine repos --name server-1
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
rdc machine query --name server-1 --storage-health
```

| Spalte | Beschreibung |
|--------|-------------|
| Size | Größe der LUKS-Image-Datei (wie das Repository aussieht) |
| Unique | Tatsächlich einzigartige Daten, die nur diesem Repository gehören |
| Shared | Datenblöcke, die über Repositories via BTRFS-Reflinks wiederverwendet werden (kostenlose Kopien) |
| Divergence | Prozentualer Anteil des Images, der einzigartig für dieses Repository ist und nicht geteilt wird (höher bedeutet mehr rückgewinnbarer Speicher bei Löschung) |
| Extents | Anzahl der Dateiextents im copy-on-write-Image (höher = stärker fragmentiert) |
| Frag | Fragmentierungsgrad: niedrig, mittel oder hoch (nur informativ) |

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

Das Ergebnis des letzten Scrubs wird außerhalb des BTRFS-Volumes gespeichert (unter `/var/lib/rediacc/scrub-last-result.json`), sodass es auch bei Problemen mit dem Volume lesbar bleibt. Die Ausgabe von `rdc machine query --system` enthält ein `scrub_status`-Feld:

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
rdc term connect -m server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

Das Ergebnis wird in derselben JSON-Datei gespeichert und ist sofort im nächsten `rdc machine query --system` sichtbar.

## Vault-Status

Einen vollständigen Überblick über eine Maschine einschließlich Bereitstellungsinformationen erhalten:

```bash
rdc machine vault-status --name server-1
```

Dies liefert:
- Hostname und Laufzeit
- Speicher-, Festplatten- und Datastore-Auslastung
- Gesamtzahl der Repositories, Anzahl der eingebundenen und laufenden Docker-Instanzen
- Detaillierte Informationen pro Repository

Verwenden Sie `--output json` für maschinenlesbare Ausgabe.

## Verbindung testen

> **Nur Cloud-Adapter.** Beim lokalen Adapter verwenden Sie `rdc term connect -m server-1 -c "hostname"`, um die Konnektivität zu prüfen.

SSH-Konnektivität zu einer Maschine überprüfen:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Meldet:
- Verbindungsstatus (Erfolg/Fehlgeschlagen)
- Verwendete Authentifizierungsmethode
- SSH-Schlüssel-Konfiguration
- Status der Public-Key-Bereitstellung
- Known-Hosts-Eintrag

Optionen:
- `--port <number>`, SSH-Port (Standard: 22)
- `--save -m server-1`, Verifizierten Host-Schlüssel in der Maschinenkonfiguration speichern

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
