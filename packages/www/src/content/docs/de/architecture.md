---
title: Architektur
description: >-
  Überblick über die Funktionsweise von Rediacc: Zwei-Tool-Architektur,
  Adapter-Erkennung, Sicherheitsmodell und Konfigurationsstruktur.
category: Concepts
order: 0
language: de
sourceHash: "2c2d289c280e2a7f"
sourceCommit: "5c97ef070ea0c474b03651ceea03433b3f48abcd"
---

# Architektur

Diese Seite erklärt, wie Rediacc unter der Haube funktioniert: die Zwei-Tool-Architektur, Adapter-Erkennung, das Sicherheitsmodell und die Konfigurationsstruktur.

## Gesamtstack-Überblick

Der Traffic fließt vom Internet durch einen Reverse-Proxy in isolierte Docker-Daemons, die jeweils durch verschlüsselten Speicher abgesichert sind:

![Gesamtstack-Architektur](/img/arch-full-stack.svg)

Jedes Repository erhält seinen eigenen Docker-Daemon, ein Loopback-IP-Subnetz (/26 = 64 IPs) und ein LUKS-verschlüsseltes BTRFS-Volume. Der Route-Server erkennt laufende Container über alle Daemons hinweg und speist die Routing-Konfiguration in Traefik ein.

## Zwei-Tool-Architektur

Rediacc verwendet zwei Binaries, die über SSH zusammenarbeiten:

![Zwei-Tool-Architektur](/img/arch-two-tool.svg)

- **rdc** läuft auf Ihrer Workstation (macOS, Linux oder Windows). Es liest Ihre lokale Konfiguration, verbindet sich über SSH mit entfernten Rechnern und ruft renet-Befehle auf.
- **renet** läuft auf dem entfernten Server mit Root-Rechten. Es verwaltet LUKS-verschlüsselte Disk-Images, isolierte Docker-Daemons, Service-Orchestrierung und Reverse-Proxy-Konfiguration.

Jeder Befehl, den Sie lokal eingeben, wird in einen SSH-Aufruf übersetzt, der renet auf dem entfernten Rechner ausführt. Sie müssen sich nie manuell per SSH auf den Servern anmelden.

Für eine operatorfokussierte Faustregel, siehe [rdc vs renet](/en/docs/rdc-vs-renet). Sie können auch `rdc ops` verwenden, um einen lokalen VM-Cluster zum Testen zu starten, siehe [Experimentelle VMs](/en/docs/experimental-vms).

## Konfiguration

Der gesamte CLI-Zustand wird in flachen JSON-Konfigurationsdateien unter `~/.config/rediacc/` gespeichert.

### Lokaler Adapter (Standard)

Der Standard für die Selbsthosting-Nutzung. Der gesamte Zustand liegt in einer Konfigurationsdatei auf Ihrer Workstation (z. B. `~/.config/rediacc/rediacc.json`).

- Direkte SSH-Verbindungen zu Maschinen
- Keine externen Dienste erforderlich
- Einzelbenutzer, einzelne Workstation
- Die Standardkonfiguration wird beim ersten CLI-Aufruf automatisch erstellt. Benannte Konfigurationen werden mit `rdc config init <name>` erstellt

### Cloud-Adapter (Experimentell)

Wird automatisch aktiviert, wenn eine Konfiguration `apiUrl`- und `token`-Felder enthält. Verwendet die Rediacc-API für Zustandsverwaltung und Teamzusammenarbeit.

- Zustand in der Cloud-API gespeichert
- Mehrbenutzerbetrieb mit rollenbasiertem Zugriff
- Web-Konsole für visuelle Verwaltung
- Eingerichtet mit `rdc auth login`

> **Hinweis:** Cloud-Adapter-Befehle sind experimentell. Aktivieren Sie sie durch Setzen von `REDIACC_EXPERIMENTAL=1`.

Beide Adapter verwenden die gleichen CLI-Befehle. Der Adapter beeinflusst nur, wo der Zustand gespeichert wird und wie die Authentifizierung funktioniert.

## Der rediacc-Benutzer

Wenn Sie `rdc config machine setup` ausführen, erstellt renet einen Systembenutzer namens `rediacc` auf dem entfernten Server:

- **UID**: 7111
- **Shell**: `/sbin/nologin` (kann sich nicht per SSH anmelden)
- **Zweck**: Besitzt Repository-Dateien und führt Rediaccfile-Funktionen aus

Der `rediacc`-Benutzer kann nicht direkt per SSH erreicht werden. Stattdessen verbindet sich rdc als der von Ihnen konfigurierte SSH-Benutzer (z. B. `deploy`), und renet führt Repository-Operationen über `sudo -u rediacc /bin/sh -c '...'` aus. Das bedeutet:

1. Ihr SSH-Benutzer benötigt `sudo`-Rechte
2. Alle Repository-Daten gehören `rediacc`, nicht Ihrem SSH-Benutzer
3. Rediaccfile-Funktionen (`up()`, `down()`) laufen als `rediacc`

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

### Daemon-Pfadstruktur

Docker-Daten und -Konfiguration werden innerhalb des Repository-Einhängepunkts gespeichert, wodurch jeder Daemon vollständig vom Host und von anderen Repositories isoliert bleibt.

**Pro-Repository-Struktur:**
```
{datastore}/mounts/{guid}/.rediacc/docker/data/    # Docker-Datenwurzel
{datastore}/mounts/{guid}/.rediacc/docker/config/  # Docker-Konfiguration
```

**Standalone-Struktur** (Daemons ohne angehängten Repository-Einhängepunkt):
```
{datastore}/standalone/{N}/.rediacc/docker/data/
{datastore}/standalone/{N}/.rediacc/docker/config/
```

**Gemeinsamer Laufzeitpfad** (unverändert):
```
/run/rediacc/docker-{N}.sock
```

Diese einheitliche Struktur beseitigt Konflikte zwischen schreibgeschützten und schreibbaren Einhängepunkten, die auftraten, wenn Daemon-Pfade zwischen dem Host-Dateisystem und dem verschlüsselten Volume aufgeteilt waren. Sowohl Pro-Repository- als auch Standalone-Daemons folgen derselben Verzeichnisstruktur, sodass Werkzeuge und Diagnosen in beiden Fällen identisch funktionieren.

## LUKS-Verschlüsselung

Repositories sind LUKS-verschlüsselte Disk-Images, die im Datastore des Servers gespeichert werden (Standard: `/mnt/rediacc`). Jedes Repository:

1. Hat eine zufällig generierte Verschlüsselungs-Passphrase (das "Credential")
2. Wird als Datei gespeichert: `{datastore}/repos/{guid}.img`
3. Wird über `cryptsetup` eingebunden, wenn darauf zugegriffen wird

Das Credential wird in Ihrer Konfigurationsdatei gespeichert, jedoch **niemals** auf dem Server. Ohne das Credential können die Repository-Daten nicht gelesen werden. Wenn Autostart aktiviert ist, wird eine sekundäre LUKS-Schlüsseldatei auf dem Server gespeichert, um das automatische Einbinden beim Hochfahren zu ermöglichen.

## Konfigurationsstruktur

Jede Konfiguration ist eine flache JSON-Datei, die unter `~/.config/rediacc/` gespeichert wird. Die Standardkonfiguration ist `rediacc.json`; benannte Konfigurationen verwenden den Namen als Dateiname (z. B. `production.json`). Hier ist ein kommentiertes Beispiel:

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 1,
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
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**Wichtige Felder:**

| Feld | Beschreibung |
|------|-------------|
| `id` | Eindeutiger Bezeichner für diese Konfigurationsdatei |
| `version` | Schema-Version der Konfigurationsdatei |
| `ssh.privateKeyPath` | Privater SSH-Schlüssel, der für alle Maschinenverbindungen verwendet wird |
| `machines.<name>.user` | SSH-Benutzername für die Verbindung zur Maschine |
| `machines.<name>.knownHosts` | SSH-Host-Schlüssel von `ssh-keyscan` |
| `repositories.<name>.repositoryGuid` | UUID, die das verschlüsselte Disk-Image identifiziert |
| `repositories.<name>.credential` | LUKS-Verschlüsselungs-Passphrase (**wird nicht auf dem Server gespeichert**) |
| `repositories.<name>.networkId` | Bestimmt das IP-Subnetz (2816 + n*64), automatisch zugewiesen |
| `nextNetworkId` | Globaler Zähler für die Vergabe von Netzwerk-IDs |
| `universalUser` | Überschreibt den Standard-Systembenutzer (`rediacc`) |

> Diese Datei enthält sensible Daten (SSH-Schlüsselpfade, LUKS-Credentials). Sie wird mit `0600`-Berechtigungen gespeichert (nur Eigentümer lesen/schreiben). Teilen Sie sie nicht und committen Sie sie nicht in die Versionsverwaltung.
