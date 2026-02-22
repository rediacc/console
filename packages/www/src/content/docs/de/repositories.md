---
title: Repositories
description: >-
  LUKS-verschlüsselte Repositories auf entfernten Maschinen erstellen, verwalten
  und betreiben.
category: Guides
order: 4
language: de
sourceHash: 04fe287348176b64
---

# Repositories

Ein **Repository** ist ein LUKS-verschlüsseltes Disk-Image auf einem entfernten Server. Nach dem Einbinden bietet es:
- Ein isoliertes Dateisystem für Ihre Anwendungsdaten
- Einen dedizierten Docker-Daemon (getrennt vom Docker des Hosts)
- Einzigartige Loopback-IPs für jeden Dienst innerhalb eines /26-Subnetzes

## Repository erstellen

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Option | Erforderlich | Beschreibung |
|--------|-------------|--------------|
| `-m, --machine <name>` | Ja | Zielmaschine, auf der das Repository erstellt wird. |
| `--size <size>` | Ja | Größe des verschlüsselten Disk-Images (z. B. `5G`, `10G`, `50G`). |
| `--skip-router-restart` | No | Skip restarting the route server after the operation |

Die Ausgabe zeigt drei automatisch generierte Werte:

- **Repository-GUID** -- Eine UUID, die das verschlüsselte Disk-Image auf dem Server identifiziert.
- **Credential** -- Eine zufällige Passphrase zum Ver- und Entschlüsseln des LUKS-Volumes.
- **Netzwerk-ID** -- Eine Ganzzahl (beginnend bei 2816, um 64 inkrementiert), die das IP-Subnetz für die Dienste dieses Repositories bestimmt.

> **Bewahren Sie das Credential sicher auf.** Es ist der Verschlüsselungsschlüssel für Ihr Repository. Bei Verlust können die Daten nicht wiederhergestellt werden. Das Credential wird in Ihrer lokalen `config.json` gespeichert, jedoch nicht auf dem Server.

## Einbinden und Aushängen

Das Einbinden entschlüsselt und macht das Repository-Dateisystem zugänglich. Das Aushängen schließt das verschlüsselte Volume.

```bash
rdc repo mount my-app -m server-1       # Entschlüsseln und einbinden
rdc repo unmount my-app -m server-1     # Aushängen und wieder verschlüsseln
```

| Option | Beschreibung |
|--------|-------------|
| `--checkpoint` | Einen Checkpoint vor dem Einbinden/Aushängen erstellen |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Status prüfen

```bash
rdc repo status my-app -m server-1
```

## Repositories auflisten

```bash
rdc repo list -m server-1
```

## Größe ändern

Das Repository auf eine exakte Größe setzen oder um einen bestimmten Betrag erweitern:

```bash
rdc repo resize my-app -m server-1 --size 20G    # Auf exakte Größe setzen
rdc repo expand my-app -m server-1 --size 5G      # 5G zur aktuellen Größe hinzufügen
```

> Das Repository muss vor der Größenänderung ausgehängt werden.

## Forken

Eine Kopie eines vorhandenen Repositories in seinem aktuellen Zustand erstellen:

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

Dies erstellt eine neue verschlüsselte Kopie mit eigener GUID und Netzwerk-ID. Der Fork teilt sich das gleiche LUKS-Credential wie das übergeordnete Repository.

## Validieren

Die Dateisystemintegrität eines Repositories prüfen:

```bash
rdc repo validate my-app -m server-1
```

## Eigentümerschaft

Die Dateieigentümerschaft innerhalb eines Repositories auf den universellen Benutzer (UID 7111) setzen. Dies ist typischerweise erforderlich, nachdem Dateien von Ihrer Workstation hochgeladen wurden, die mit Ihrer lokalen UID ankommen.

```bash
rdc repo ownership my-app -m server-1
```

Der Befehl erkennt automatisch Docker-Container-Datenverzeichnisse (beschreibbare Bind-Mounts) und schließt sie aus. Dies verhindert das Beschädigen von Containern, die Dateien mit eigenen UIDs verwalten (z. B. MariaDB=999, www-data=33).

| Option | Beschreibung |
|--------|-------------|
| `--uid <uid>` | Eine benutzerdefinierte UID anstelle von 7111 setzen |
| `--force` | Docker-Volume-Erkennung überspringen und alles chownen |
| `--skip-router-restart` | Skip restarting the route server after the operation |

Um die Eigentümerschaft aller Dateien zu erzwingen, einschließlich Container-Daten:

```bash
rdc repo ownership my-app -m server-1 --force
```

> **Warnung:** Die Verwendung von `--force` bei laufenden Containern kann diese beschädigen. Stoppen Sie Dienste vorher mit `rdc repo down`, falls nötig.

Siehe den [Migrationsleitfaden](/de/docs/migration) für eine vollständige Anleitung, wann und wie die Eigentümerschaft bei der Projektmigration verwendet wird.

## Vorlage

Eine Vorlage anwenden, um ein Repository mit Dateien zu initialisieren:

```bash
rdc repo template my-app -m server-1 --file ./my-template.tar.gz
```

## Löschen

Ein Repository und alle darin enthaltenen Daten dauerhaft zerstören:

```bash
rdc repo delete my-app -m server-1
```

> Dies zerstört dauerhaft das verschlüsselte Disk-Image. Diese Aktion kann nicht rückgängig gemacht werden.
