---
title: RDC CLI Cheat Sheet
description: "Kurzreferenz für rdc: Konfigurationen, Repos, Maschinen, Dateisynchronisierung und Container. Vollständiger Optionssatz: füge --help zu einem beliebigen Befehl hinzu."
category: Guides
order: 3
language: de
sourceHash: "bc52628ba870dfbb"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# RDC CLI Cheat Sheet

Nicht alle `rdc`-Befehle sind hier aufgelistet, nur die, die bei jeder Bereitstellung verwendet werden. Für den vollständigen Optionssatz führe einen beliebigen rdc-Befehl mit `--help` aus. Spezialfälle und selten verwendete Optionen findest du in der vollständigen Referenz.

## Repository-Lebenszyklus

| Befehl | Beschreibung |
|--------|--------------|
| `rdc repo create --name <repo> -m <machine>` | Neues Repository auf einer Maschine erstellen |
| `rdc repo up --name <repo> -m <machine>` | Repository bereitstellen oder aktualisieren |
| `rdc repo down --name <repo> -m <machine>` | Repository stoppen |
| `rdc repo delete --name <repo> -m <machine>` | Repository löschen |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | Repository forken (nahezu sofort, BTRFS-Reflink) |
| `rdc repo takeover --name <repo> -m <machine>` | Eigentümerschaft eines vorhandenen Repositorys übernehmen |
| `rdc config repository list` | Alle Repositories mit Name und GUID auflisten |

## Per-Repository-Geheimnisse

Schreibgeschützte Anmeldedaten zur Bereitstellungszeit. `get` gibt nur den Digest zurück. Der Wert wird niemals zurückgegeben. Siehe [Repositories § Geheimnisse](/en/docs/repositories#secrets) für das vollständige Handbuch.

| Befehl | Beschreibung |
|--------|--------------|
| `rdc repo secret set --name <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Neues Geheimnis erstellen (`--current ""` beim ersten Schreiben) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --current <prev>` | Vorhandenes Geheimnis überschreiben (Passwort-ähnliche Vorbedingung) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --rotate-secret` | Überschreiben ohne Überprüfung des vorherigen Wertes (wird als Rotation protokolliert) |
| `rdc repo secret list --name <repo>` | Geheimnisnamen und Lieferungsmodi auflisten (nie Werte, nie Digests) |
| `rdc repo secret get --name <repo> --key <KEY>` | Geheimnis-Digest und Modus anzeigen (kein Klartext-Wert, niemals) |
| `rdc repo secret unset --name <repo> --key <KEY> --current <prev>` | Geheimnis löschen |
| `rdc repo secret unset --name <repo> --key <KEY> --rotate-secret` | Löschen ohne Überprüfung des vorherigen Wertes |

> Forks erben keine Geheimnisse. Lege sie auf dem Fork explizit mit `rdc repo secret set --name <repo>:<tag>` fest.

## Sicherung und Wiederherstellung

| Befehl | Beschreibung |
|--------|--------------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | Repository-Sicherung in Speicher hochladen |
| `rdc repo push --to <storage> -m <machine>` | Alle Repositories in Speicher hochladen |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | Repository aus Speicher wiederherstellen |
| `rdc repo pull --from <storage> -m <machine>` | Alle Repositories aus Speicher wiederherstellen |
| `rdc repo push ... --bwlimit <limit>` | rsync-Bandbreite beim Hochladen begrenzen (z. B. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | rsync-Bandbreite beim Herunterladen begrenzen |
| `rdc repo push ... --checkpoint` | Container vor dem Hochladen sichern |
| `rdc repo backup list --from <storage> -m <machine>` | Verfügbare Sicherungen im Speicher auflisten |
| `rdc storage browse --name <storage>` | Speicherinhalte durchsuchen |

## Repository-Migration

| Befehl | Beschreibung |
|--------|--------------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | Repository zwischen Maschinen verschieben |
| `rdc repo migrate ... --provision` | Zielmaschine vor der Übertragung bereitstellen |
| `rdc repo migrate ... --checkpoint` | Vor der Migration sichern |
| `rdc repo migrate ... --skip-dns` | DNS-Aktualisierung nach der Migration überspringen |
| `rdc repo migrate ... --bwlimit <limit>` | Übertragungsbandbreite begrenzen |

## Sicherungsstrategien

| Befehl | Beschreibung |
|--------|--------------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Benannte Sicherungsstrategie erstellen oder aktualisieren |
| `rdc config backup-strategy list` | Alle definierten Sicherungsstrategien auflisten |
| `rdc config backup-strategy show --name <name>` | Details einer Strategie anzeigen |
| `rdc config backup-strategy remove --name <name>` | Strategie entfernen |
| `rdc machine backup schedule -m <machine>` | Konfigurierte Sicherungsstrategien auf einer Maschine bereitstellen |

## Sicherungsoperationen

| Befehl | Beschreibung |
|--------|--------------|
| `rdc machine backup schedule -m <machine>` | Gebundene Strategien als systemd-Timer bereitstellen |
| `rdc machine backup schedule -m <machine> --dry-run` | Timer-Units ohne Bereitstellung anzeigen (Token maskiert) |
| `rdc machine backup now -m <machine>` | Alle gebundenen Strategien sofort ausführen |
| `rdc machine backup now -m <machine> --strategy <name>` | Eine bestimmte Strategie sofort ausführen |
| `rdc machine backup status -m <machine>` | Timer-Status und aktuelle Jobergebnisse anzeigen |
| `rdc machine backup status -m <machine> --strategy <name>` | Status einer bestimmten Strategie anzeigen |
| `rdc machine backup cancel -m <machine>` | Laufende Sicherungen abbrechen |
| `rdc machine backup cancel -m <machine> --strategy <name>` | Eine bestimmte laufende Sicherung abbrechen |

## Maschinenverwaltung

| Befehl | Beschreibung |
|--------|--------------|
| `rdc machine query --name <machine>` | Vollständiger Maschinenstatus (System, Container, Dienste, Repos, Netzwerk) |
| `rdc machine query --name <machine> --system` | Nur Systeminformationen |
| `rdc machine query --name <machine> --containers` | Nur Container-Liste |
| `rdc machine query --name <machine> --repositories` | Nur Repository-Liste |
| `rdc machine query --name <machine> --services` | Nur Dienste-Liste |
| `rdc machine query --name <machine> --network` | Nur Netzwerkinformationen |
| `rdc machine query --name <machine> --block-devices` | Nur Block-Geräteinformationen |
| `rdc machine list` | Alle Maschinen in der Konfiguration auflisten |
| `rdc config machine setup --name <machine>` | Erstmalige Maschinenbereitstellung ausführen |
| `rdc machine prune --name <machine>` | Ungenutzte Ressourcen von der Maschine entfernen |
| `rdc machine deprovision --name <machine>` | Maschine vollständig deprovisionieren |
| `rdc machine vault-status --name <machine>` | LUKS-Vault-Status anzeigen |

## Terminal und Synchronisierung

| Befehl | Beschreibung |
|--------|--------------|
| `rdc term connect -m <machine>` | SSH-Terminal zur Maschine öffnen |
| `rdc term connect -m <machine> -r <repo>` | SSH-Terminal zum Repository öffnen (setzt DOCKER_HOST) |
| `rdc term connect -m <machine> -c "<command>"` | Befehl auf der Maschine ausführen |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | Eine oder mehrere lokale Dateien/Verzeichnisse ins Repository hochladen |
| `rdc repo sync upload -m <machine> -r <repo> --local <file> --remote-file <path>` | Einzelne lokale Datei in einen expliziten Remote-Pfad hochladen |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | Repository-Verzeichnis lokal herunterladen |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | Einzelne Remote-Datei in ein lokales Verzeichnis herunterladen |
| `rdc vscode connect -m <machine> -r <repo>` | VS Code Remote SSH-Sitzung öffnen |

## Konfiguration

| Befehl | Beschreibung |
|--------|--------------|
| `rdc config init --name <name>` | Benannte Konfigurationsdatei erstellen |
| `rdc config machine add --name <machine> --host <host> --user <user>` | Maschine zur Konfiguration hinzufügen |
| `rdc config storage import --file rclone.conf` | Speicheranbieter aus rclone-Konfiguration importieren |
| `rdc config storage list` | Konfigurierte Speicheranbieter auflisten |
| `rdc config backup-strategy set ...` | Benannte Sicherungsstrategie definieren |
| `rdc --config <name> <command>` | Benannte Konfigurationsdatei verwenden |

## Diagnose und Direktzugriff

| Befehl | Beschreibung |
|--------|--------------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | Container in einem Repository auflisten |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | Container-Logs abrufen |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | Befehl in Container ausführen |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | Container neu starten |
