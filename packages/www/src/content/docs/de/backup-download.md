---
title: "Backup-Download"
description: "Das verschlüsselte Image eines Repositorys in ein lokales Verzeichnis oder auf ein externes Laufwerk kopieren, bei späteren Läufen an Ort und Stelle aktualisieren oder ohne Maschine direkt aus dem Backup-Store neu aufbauen."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: de
sourceHash: "c52e6a0471befc30"
---

# Backup-Download

`rdc backup download` hält eine Kopie des verschlüsselten Images eines Repositorys in einem lokalen Verzeichnis oder auf einem externen Laufwerk vor. Die Kopie ist derselbe Chiffretext, der auf der Maschine liegt, daher wird unterwegs nichts entschlüsselt. Die Zugangsdaten zum Öffnen bleiben in der Konfiguration, weshalb die Anmeldung bei [Config-Storage](/de/docs/config-storage) der Weg ist, sie sicher aufzubewahren. Ohne diese Zugangsdaten lässt sich das Image nicht öffnen.

Es gibt zwei Quellen. Standard ist eine laufende Maschine. Die andere ist der Backup-Store, ausgewählt mit `--store`.

## Download von einer Maschine

```bash
rdc backup download mail@prod --to /mnt/usb
```

`--to` benennt ein vorhandenes, beschreibbares Verzeichnis. Es wird nie angelegt, das Laufwerk muss also zuvor eingehängt sein. Das Image landet unter `<machine>/<name>.<tag>.img`, daneben liegt eine `.state.json`-Datei.

Jeder Lauf erstellt einen frischen Snapshot des Repositorys, der nur so lange besteht, wie die Übertragung läuft, sendet die Unterschiede mit rsync und vergleicht einen sha256 des Ergebnisses mit dem Snapshot der Maschine.

| Flag | Wirkung |
|------|--------|
| `--all -m <machine>` | Jedes auf der Maschine platzierte Grand-Repository kopieren |
| `--include-forks` | Zusammen mit `--all` auch Forks kopieren |
| `--bwlimit <rate>` | Netzwerkbandbreite begrenzen, etwa `100Mbps` oder `12.5M` |
| `--checkpoint` | Das Repository vor dem Snapshot per Checkpoint einfrieren (Hot-Backup) |
| `--retries <n>` | Wiederholungen innerhalb des Laufs nach einem Netzwerkfehler (Standard 3) |
| `--skip-verify` | Den sha256-Vergleich überspringen; die eigene Prüfsumme von rsync läuft weiterhin |
| `--skip-space-check` | Nur warnen statt abzulehnen, wenn auf dem Ziel möglicherweise der freie Platz fehlt |

### Kopie aktualisieren

Ein zweiter Lauf aktualisiert das vorhandene Image per rsync-Delta an Ort und Stelle. Ein wöchentlicher Lauf sendet nur das Geänderte, und das Ziel braucht Platz für eine Kopie des Images, nicht für zwei. Vor dem Start eines Laufs wird der freie Platz gegen die Image-Größe geprüft, und `--skip-space-check` macht aus einer Ablehnung eine Warnung.

### Unterbrochene Läufe und Fortsetzen

Die Statusdatei hält `status` fest. Der Wert ist `incomplete`, ab bevor das erste Byte geschrieben wird, bis ein Lauf verifiziert ist, und ein `incomplete`-Image ist nicht verwendbar. Strg-C, eine verlorene Verbindung oder ein beendeter Prozess hinterlassen es in diesem Zustand. Derselbe Befehl, erneut ausgeführt, setzt den Lauf fort, und nur die Unterschiede werden gesendet. Der Befehl endet mit Exit-Code 0, sobald der Status `complete` ist.

### Voraussetzungen

Die Übertragung braucht rsync 3.1.3 oder neuer auf diesem Rechner und kennt keinen SFTP-Fallback. Linux-Distributionen liefern es mit. Unter macOS ersetzt `brew install rsync` das mitgelieferte openrsync, das die Übertragung nicht ausführen kann. Unter Windows wird MSYS2 mit dem rsync-Paket installiert, alternativ dient die Desktop-App.

### Externe Laufwerke

Das Dateisystem des Ziels entscheidet, was passt.

- **FAT32** kann keine Datei über 4 GiB aufnehmen, und der Befehl lehnt den Lauf ab.
- **exFAT** ohne Unterstützung für Sparse-Dateien speichert das Image in seiner vollen scheinbaren Größe, daher zählt die Prüfung des freien Platzes diese Größe.
- Ein lokal erstellter **Copy-on-Write-Snapshot** des Ziels (btrfs, ZFS, APFS) bewahrt frühere Versionen des Images. Jede Aktualisierung an Ort und Stelle kostet dann die geänderten Blöcke zusätzlich zu den alten.

## Download aus dem Backup-Store

```bash
export REDIACC_TOKEN=<api-token>
rdc backup download mail --store --to /mnt/usb
```

`--store` baut das Image direkt aus dem Chunk-Store neu auf, ganz ohne Maschine. Das Token in `REDIACC_TOKEN` braucht die Scopes `backup:read` und `backup:restore`. Eine CLI-Anmeldung trägt `backup:restore` nie, daher wird das Token auf der Portalseite „API Tokens“ erstellt. Es muss zu einem Team gehören und von einem aktuellen Eigentümer oder Administrator der Organisation erstellt worden sein.

`--store` nimmt genau einen Repository-Namen. Es akzeptiert weder `-m`, `--checkpoint`, `--all`, `--include-forks`, `--bwlimit`, `--retries`, `--skip-verify` noch `--skip-space-check`: Der Store-Abruf hat eine eigene Fortsetzung und verifiziert jeden Chunk.

Das Image wird nach `<dir>/<name>.<tag>.img` geschrieben. Ein unterbrochener Abruf behält die Teilkopie, und derselbe Befehl setzt dort fort.

### Snapshot mit `--at` wählen

Standardmäßig wird der neueste Snapshot abgerufen. `--at <time|snapshot>` wählt einen anderen, entweder einen Zeitpunkt in ISO 8601 oder eine Snapshot-ID. Die Option gilt nur zusammen mit `--store`.

```bash
rdc backup download mail --store --to /mnt/usb --at 2026-10-01T00:00:00Z
```

Auf einer anderen Plattform als Linux ist das abgerufene Image verschlüsselt und lässt sich lokal nicht öffnen. Mit `rdc backup upload` wird es an eine Linux-Maschine gesendet.

## Eine Kopie zurückladen

```bash
rdc backup upload /mnt/usb/prod/mail.latest.img --to prod --as mail-copy --up
```

`rdc backup upload` sendet ein heruntergeladenes Image an eine Maschine und registriert es als neues Repository. Die Übertragung wird nach einer Unterbrechung fortgesetzt, und die Maschine prüft sha256 und LUKS-Header, bevor sie das Image ablegt. Die Statusdatei neben dem Image liefert die Zugangsdaten. Ist diese Datei verloren, benennt `--from-repo <name>` das Repository, das sie liefert.

| Flag | Wirkung |
|------|--------|
| `--as <name>` | Name für das neue Repository (Standard: der Name des Images) |
| `--datastore <name>` | Das Image auf einem benannten Datastore ablegen |
| `--from-repo <name>` | Zugangsdaten und Lineage liefern, wenn die Statusdatei unbrauchbar ist |
| `--bwlimit <rate>`, `--retries <n>` | Wie beim Download |
| `--up` | Das Repository starten, sobald es registriert ist |
| `--skip-verify` | Den Vergleich mit dem beim Download festgehaltenen sha256 überspringen |

## Veraltete Transfer-Snapshots

Ein hart beendeter Transfer kann seinen Snapshot auf der Maschine zurücklassen. `rdc machine status` zählt veraltete Transfer-Snapshots in der Pool-Zusammenfassung, und `rdc machine prune <machine> --dry-run` listet sie auf. `rdc machine prune <machine>` entfernt sie.

Zu Snapshots in den Chunk-Speicher siehe [Backup & Wiederherstellung](/de/docs/backup-restore).
