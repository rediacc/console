---
title: Architektur
description: >-
  Überblick über die Funktionsweise von Rediacc: Zwei-Tool-Architektur,
  Betriebsmodi, Sicherheitsmodell und Konfigurationsstruktur.
category: Concepts
order: 0
language: de
sourceHash: 58ba0da9645bb9dd
---

# Architektur

Wenn Sie unsicher sind, welches Tool Sie verwenden sollen, lesen Sie [rdc vs renet](/de/docs/rdc-vs-renet).

Diese Seite erklärt, wie Rediacc unter der Haube funktioniert: die Zwei-Tool-Architektur, Betriebsmodi, das Sicherheitsmodell und die Konfigurationsstruktur.

## Full Stack Overview

Traffic flows from the internet through a reverse proxy, into isolated Docker daemons, each backed by encrypted storage:

![Full Stack Architecture](/img/arch-full-stack.svg)

Each repository gets its own Docker daemon, loopback IP subnet (/26 = 64 IPs), and LUKS-encrypted BTRFS volume. The route server discovers running containers across all daemons and feeds routing configuration to Traefik.

## Zwei-Tool-Architektur

Rediacc verwendet zwei Binaries, die über SSH zusammenarbeiten:

![Zwei-Tool-Architektur](/img/arch-two-tool.svg)

- **rdc** läuft auf Ihrer Workstation (macOS, Linux oder Windows). Es liest Ihre lokale Konfiguration, verbindet sich über SSH mit entfernten Rechnern und ruft renet-Befehle auf.
- **renet** läuft auf dem entfernten Server mit Root-Rechten. Es verwaltet LUKS-verschlüsselte Disk-Images, isolierte Docker-Daemons, Service-Orchestrierung und Reverse-Proxy-Konfiguration.

Jeder Befehl, den Sie lokal eingeben, wird in einen SSH-Aufruf übersetzt, der renet auf dem entfernten Rechner ausführt. Sie müssen sich nie manuell per SSH auf den Servern anmelden.

## Betriebsmodi

Rediacc unterstützt drei Modi, die jeweils bestimmen, wo der Zustand gespeichert wird und wie Befehle ausgeführt werden.

![Betriebsmodi](/img/arch-operating-modes.svg)

### Lokaler Modus

Der Standard für die Selbsthosting-Nutzung. Der gesamte Zustand liegt in `~/.rediacc/config.json` auf Ihrer Workstation.

- Direkte SSH-Verbindungen zu Maschinen
- Keine externen Dienste erforderlich
- Einzelbenutzer, einzelne Workstation
- Kontext wird mit `rdc context create-local` erstellt

### Cloud-Modus (Experimentell)

Verwendet die Rediacc-API für Zustandsverwaltung und Teamzusammenarbeit.

- Zustand in der Cloud-API gespeichert
- Mehrbenutzerbetrieb mit rollenbasiertem Zugriff
- Web-Konsole für visuelle Verwaltung
- Kontext wird mit `rdc context create` erstellt

> **Hinweis:** Cloud-Modus-Befehle sind experimentell. Aktivieren Sie sie mit `rdc --experimental <befehl>` oder durch Setzen von `REDIACC_EXPERIMENTAL=1`.

### S3-Modus

Speichert verschlüsselten Zustand in einem S3-kompatiblen Bucket. Kombiniert die Selbsthosting-Natur des lokalen Modus mit Portabilität über Workstations hinweg.

- Zustand in einem S3/R2-Bucket als `state.json` gespeichert
- AES-256-GCM-Verschlüsselung mit einem Master-Passwort
- Portabel: Jede Workstation mit den Bucket-Zugangsdaten kann die Infrastruktur verwalten
- Kontext wird mit `rdc context create-s3` erstellt

Alle drei Modi verwenden die gleichen CLI-Befehle. Der Modus beeinflusst nur, wo der Zustand gespeichert wird und wie die Authentifizierung funktioniert.

## Der rediacc-Benutzer

Wenn Sie `rdc context setup-machine` ausführen, erstellt renet einen Systembenutzer namens `rediacc` auf dem entfernten Server:

- **UID**: 7111
- **Shell**: `/sbin/nologin` (kann sich nicht per SSH anmelden)
- **Zweck**: Besitzt Repository-Dateien und führt Rediaccfile-Funktionen aus

Der `rediacc`-Benutzer kann nicht direkt per SSH erreicht werden. Stattdessen verbindet sich rdc als der von Ihnen konfigurierte SSH-Benutzer (z. B. `deploy`), und renet führt Repository-Operationen über `sudo -u rediacc /bin/sh -c '...'` aus. Das bedeutet:

1. Ihr SSH-Benutzer benötigt `sudo`-Rechte
2. Alle Repository-Daten gehören `rediacc`, nicht Ihrem SSH-Benutzer
3. Rediaccfile-Funktionen (`prep()`, `up()`, `down()`) laufen als `rediacc`

Diese Trennung stellt sicher, dass Repository-Daten unabhängig vom verwaltenden SSH-Benutzer eine konsistente Eigentümerschaft haben.

## Docker-Isolation

Jedes Repository erhält seinen eigenen isolierten Docker-Daemon. Wenn ein Repository eingebunden wird, startet renet einen dedizierten `dockerd`-Prozess mit einem einzigartigen Socket:

![Docker-Isolation](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

Zum Beispiel verwendet ein Repository mit Netzwerk-ID `2816`:
```
/var/run/rediacc/docker-2816.sock
```

Das bedeutet:
- Container aus verschiedenen Repositories können sich gegenseitig nicht sehen
- Jedes Repository hat seinen eigenen Image-Cache, eigene Netzwerke und Volumes
- Der Docker-Daemon des Hosts (falls vorhanden) ist vollständig getrennt

Rediaccfile-Funktionen haben automatisch `DOCKER_HOST` auf den korrekten Socket gesetzt.

## LUKS-Verschlüsselung

Repositories sind LUKS-verschlüsselte Disk-Images, die im Datastore des Servers gespeichert werden (Standard: `/mnt/rediacc`). Jedes Repository:

1. Hat eine zufällig generierte Verschlüsselungs-Passphrase (das "Credential")
2. Wird als Datei gespeichert: `{datastore}/repos/{guid}.img`
3. Wird über `cryptsetup` eingebunden, wenn darauf zugegriffen wird

Das Credential wird in Ihrer lokalen `config.json` gespeichert, jedoch **niemals** auf dem Server. Ohne das Credential können die Repository-Daten nicht gelesen werden. Wenn Autostart aktiviert ist, wird eine sekundäre LUKS-Schlüsseldatei auf dem Server gespeichert, um das automatische Einbinden beim Hochfahren zu ermöglichen.

## Konfigurationsstruktur

Die gesamte Konfiguration wird in `~/.rediacc/config.json` gespeichert. Hier ist ein kommentiertes Beispiel:

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "storages": {
        "backblaze": {
          "provider": "b2",
          "vaultContent": { "...": "..." }
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**Wichtige Felder:**

| Feld | Beschreibung |
|------|-------------|
| `mode` | `"local"`, `"s3"`, oder weggelassen für Cloud-Modus |
| `apiUrl` | `"local://"` für lokalen Modus, API-URL für Cloud-Modus |
| `ssh.privateKeyPath` | Privater SSH-Schlüssel, der für alle Maschinenverbindungen verwendet wird |
| `machines.<name>.user` | SSH-Benutzername für die Verbindung zur Maschine |
| `machines.<name>.knownHosts` | SSH-Host-Schlüssel von `ssh-keyscan` |
| `repositories.<name>.repositoryGuid` | UUID, die das verschlüsselte Disk-Image identifiziert |
| `repositories.<name>.credential` | LUKS-Verschlüsselungs-Passphrase (**wird nicht auf dem Server gespeichert**) |
| `repositories.<name>.networkId` | Bestimmt das IP-Subnetz (2816 + n*64), automatisch zugewiesen |
| `nextNetworkId` | Globaler Zähler für die Vergabe von Netzwerk-IDs |
| `universalUser` | Überschreibt den Standard-Systembenutzer (`rediacc`) |

> Diese Datei enthält sensible Daten (SSH-Schlüsselpfade, LUKS-Credentials). Sie wird mit `0600`-Berechtigungen gespeichert (nur Eigentümer lesen/schreiben). Teilen Sie sie nicht und committen Sie sie nicht in die Versionsverwaltung.
