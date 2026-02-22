---
title: Voraussetzungen
description: >-
  Systemvoraussetzungen und unterstützte Plattformen für den Betrieb von
  Rediacc.
category: Guides
order: 0
language: de
sourceHash: 35e75948e9858c6d
---

# Voraussetzungen

Wenn Sie unsicher sind, welches Tool Sie verwenden sollen, lesen Sie [rdc vs renet](/de/docs/rdc-vs-renet).

Bevor Sie mit Rediacc bereitstellen, stellen Sie sicher, dass Ihre Workstation und Ihre entfernten Server die folgenden Voraussetzungen erfüllen.

## Workstation (Steuerungsebene)

Die `rdc`-CLI läuft auf Ihrer Workstation und orchestriert entfernte Server über SSH.

| Plattform | Mindestversion | Hinweise |
|-----------|---------------|----------|
| macOS | 12 (Monterey)+ | Intel und Apple Silicon unterstützt |
| Linux (x86_64) | Jede moderne Distribution | glibc 2.31+ (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10+ | Native Unterstützung über PowerShell-Installer |

**Zusätzliche Voraussetzungen:**
- Ein SSH-Schlüsselpaar (z. B. `~/.ssh/id_ed25519` oder `~/.ssh/id_rsa`)
- Netzwerkzugriff auf Ihre entfernten Server über den SSH-Port (Standard: 22)

## Entfernter Server (Datenebene)

Die `renet`-Binary läuft auf entfernten Servern mit Root-Rechten. Sie verwaltet verschlüsselte Disk-Images, isolierte Docker-Daemons und Service-Orchestrierung.

### Unterstützte Betriebssysteme

| Betriebssystem | Version | Architektur |
|----------------|---------|-------------|
| Ubuntu | 24.04+ | x86_64 |
| Debian | 12+ | x86_64 |
| Fedora | 43+ | x86_64 |
| openSUSE Leap | 15.6+ | x86_64 |
| Alpine | 3.19+ | x86_64 (erfordert gcompat) |
| Arch Linux | Rolling Release | x86_64 |

Dies sind die in CI getesteten Distributionen. Andere Linux-Distributionen mit systemd, Docker-Unterstützung und cryptsetup können funktionieren, werden aber nicht offiziell unterstützt.

### Server-Voraussetzungen

- Ein Benutzerkonto mit `sudo`-Rechten (passwortloses sudo empfohlen)
- Ihr öffentlicher SSH-Schlüssel in `~/.ssh/authorized_keys` hinterlegt
- Mindestens 20 GB freier Speicherplatz (mehr je nach Ihren Workloads)
- Internetzugang zum Abrufen von Docker-Images (oder eine private Registry)

### Automatisch installiert

Der Befehl `rdc context setup-machine` installiert Folgendes auf dem entfernten Server:

- **Docker** und **containerd** (Container-Runtime)
- **cryptsetup** (LUKS-Festplattenverschlüsselung)
- **renet**-Binary (per SFTP hochgeladen)

Sie müssen diese nicht manuell installieren.

## Local Virtual Machines (Optional)

If you want to test deployments locally using `rdc ops`, your workstation needs virtualization support: KVM on Linux or QEMU on macOS. See the [Experimental VMs](/de/docs/experimental-vms) guide for setup steps and platform details.
