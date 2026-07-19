---
title: RDC CLI Cheat Sheet
description: "Kurzreferenz für rdc: Konfigurationen, Repos, Maschinen, Dateisynchronisierung und Container. Vollständiger Optionssatz: füge --help zu einem beliebigen Befehl hinzu."
category: Guides
order: 3
language: de
sourceHash: "d92987c4766d91ae"
sourceCommit: "70a4ca883754f1c0a7f4684c9fde02a5a01d3681"
---

# RDC CLI Cheat Sheet

Nicht alle `rdc`-Befehle sind hier aufgelistet, nur die, die bei jeder Bereitstellung verwendet werden. Für den vollständigen Optionssatz führe einen beliebigen rdc-Befehl mit `--help` aus. Spezialfälle und selten verwendete Optionen findest du in der vollständigen Referenz.

## Repository-Lebenszyklus

| Befehl | Beschreibung |
|--------|--------------|
| `rdc repo create <repo> -m <machine>` | Neues Repository auf einer Maschine erstellen |
| `rdc repo up <repo>@<machine>` | Repository bereitstellen oder aktualisieren |
| `rdc repo down <repo>@<machine>` | Repository stoppen |
| `rdc repo delete <repo>@<machine>` | Repository löschen |
| `rdc repo fork <repo>@<machine> --tag <tag>` | Repository forken (nahezu sofort, BTRFS-Reflink) |
| `rdc repo promote <repo>:<tag>` | Einen validierten Fork unter dem Namen des übergeordneten Repositorys in Produktion überführen |
| `rdc repo list` | Alle Repositories mit Name und GUID auflisten |

## Per-Repository-Geheimnisse

Schreibgeschützte Anmeldedaten zur Bereitstellungszeit. `get` gibt nur den Digest zurück. Der Wert wird niemals zurückgegeben. Siehe [Repositories § Geheimnisse](/en/docs/repositories#secrets) für das vollständige Handbuch.

| Befehl | Beschreibung |
|--------|--------------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Neues Geheimnis erstellen (`--current ""` beim ersten Schreiben) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | Vorhandenes Geheimnis überschreiben (Passwort-ähnliche Vorbedingung) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | Überschreiben ohne Überprüfung des vorherigen Wertes (wird als Rotation protokolliert) |
| `rdc repo secret list <repo>` | Geheimnisnamen und Lieferungsmodi auflisten (nie Werte, nie Digests) |
| `rdc repo secret get <repo> --key <KEY>` | Geheimnis-Digest und Modus anzeigen (kein Klartext-Wert, niemals) |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | Geheimnis löschen |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | Löschen ohne Überprüfung des vorherigen Wertes |

> Forks erben keine Geheimnisse. Lege sie auf dem Fork explizit mit `rdc repo secret set <repo>:<tag>` fest.

## Sicherung und Wiederherstellung

| Befehl | Beschreibung |
|--------|--------------|
| `rdc repo push <repo>@<machine> --to <storage>` | Repository-Sicherung in Speicher hochladen |
| `rdc repo pull <repo>@<machine> --from <storage>` | Repository aus Speicher wiederherstellen |
| `rdc repo push ... --bwlimit <limit>` | rsync-Bandbreite beim Hochladen begrenzen (z. B. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | rsync-Bandbreite beim Herunterladen begrenzen |
| `rdc repo push ... --checkpoint` | Container vor dem Hochladen sichern |
| `rdc backup list --storage <storage> | Verfügbare Sicherungen im Speicher auflisten |
| `rdc storage browse <storage>` | Speicherinhalte durchsuchen |

## Repository-Migration

| Befehl | Beschreibung |
|--------|--------------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | Repository zwischen Maschinen verschieben |
| `rdc repo migrate ... --provision` | Zielmaschine vor der Übertragung bereitstellen |
| `rdc repo migrate ... --checkpoint` | Vor der Migration sichern |
| `rdc repo migrate ... --skip-dns` | DNS-Aktualisierung nach der Migration überspringen |
| `rdc repo migrate ... --bwlimit <limit>` | Übertragungsbandbreite begrenzen |

## Sicherungsstrategien

| Befehl | Beschreibung |
|--------|--------------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Benannte Sicherungsstrategie erstellen oder aktualisieren |
| `rdc backup strategy list` | Alle definierten Sicherungsstrategien auflisten |
| `rdc backup strategy show <name>` | Details einer Strategie anzeigen |
| `rdc backup strategy remove <name>` | Strategie entfernen |
| `rdc backup schedule -m <machine>` | Konfigurierte Sicherungsstrategien auf einer Maschine bereitstellen |

## Sicherungsoperationen

| Befehl | Beschreibung |
|--------|--------------|
| `rdc backup schedule -m <machine>` | Gebundene Strategien als systemd-Timer bereitstellen |
| `rdc backup schedule -m <machine> --dry-run` | Timer-Units ohne Bereitstellung anzeigen (Token maskiert) |
| `rdc backup run -m <machine>` | Alle gebundenen Strategien sofort ausführen |
| `rdc backup run <name> -m <machine>` | Eine bestimmte Strategie sofort ausführen |
| `rdc backup status -m <machine>` | Timer-Status und aktuelle Jobergebnisse anzeigen |
| `rdc backup status <name> -m <machine>` | Status einer bestimmten Strategie anzeigen |
| `rdc backup cancel -m <machine>` | Laufende Sicherungen abbrechen |
| `rdc backup cancel <name> -m <machine>` | Eine bestimmte laufende Sicherung abbrechen |

## Maschinenverwaltung

| Befehl | Beschreibung |
|--------|--------------|
| `rdc machine status <machine>` | Vollständiger Maschinenstatus (System, Container, Dienste, Repos, Netzwerk) |
| `rdc machine status <machine> --system` | Nur Systeminformationen |
| `rdc machine status <machine> --containers` | Nur Container-Liste |
| `rdc machine status <machine> --repositories` | Nur Repository-Liste |
| `rdc machine status <machine> --services` | Nur Dienste-Liste |
| `rdc machine status <machine> --network` | Nur Netzwerkinformationen |
| `rdc machine status <machine> --block-devices` | Nur Block-Geräteinformationen |
| `rdc machine list` | Alle Maschinen in der Konfiguration auflisten |
| `rdc machine setup <machine>` | Erstmalige Maschinenbereitstellung ausführen |
| `rdc machine prune <machine>` | Ungenutzte Ressourcen von der Maschine entfernen |
| `rdc machine deprovision <machine>` | Maschine vollständig deprovisionieren |

## Terminal und Synchronisierung

| Befehl | Beschreibung |
|--------|--------------|
| `rdc term connect <machine>` | SSH-Terminal zur Maschine öffnen |
| `rdc term connect <repo>@<machine>` | SSH-Terminal zum Repository öffnen (setzt DOCKER_HOST) |
| `rdc term connect <machine> -c "<command>"` | Befehl auf der Maschine ausführen |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | Eine oder mehrere lokale Dateien/Verzeichnisse ins Repository hochladen |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | Einzelne lokale Datei in einen expliziten Remote-Pfad hochladen |
| `rdc repo sync download <repo>@<machine> --local <dir>` | Repository-Verzeichnis lokal herunterladen |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | Einzelne Remote-Datei in ein lokales Verzeichnis herunterladen |
| `rdc vscode connect <repo>@<machine>` | VS Code Remote SSH-Sitzung öffnen |

## Konfiguration

| Befehl | Beschreibung |
|--------|--------------|
| `rdc config init <name>` | Benannte Konfigurationsdatei erstellen |
| `rdc machine add <machine> --ip <host> --user <user>` | Maschine zur Konfiguration hinzufügen |
| `rdc storage import rclone.conf` | Speicheranbieter aus rclone-Konfiguration importieren |
| `rdc storage list` | Konfigurierte Speicheranbieter auflisten |
| `rdc backup strategy set ...` | Benannte Sicherungsstrategie definieren |
| `rdc --config <name> <command>` | Benannte Konfigurationsdatei verwenden |

## Diagnose und Direktzugriff

| Befehl | Beschreibung |
|--------|--------------|
| `rdc term connect <repo>@<machine> -c "docker ps"` | Container in einem Repository auflisten |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | Container-Logs abrufen |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | Befehl in Container ausführen |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | Container neu starten |
