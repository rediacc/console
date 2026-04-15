---
title: Voraussetzungen
description: >-
  Systemvoraussetzungen und unterstützte Plattformen für den Betrieb von
  Rediacc.
category: Guides
order: 0
language: de
sourceHash: "eb237c7beb1bb942"
sourceCommit: "d5c06171af0ef58b551a9682905d98af81e496cd"
---

# Voraussetzungen

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

Wenn Sie unsicher sind, welches Tool Sie verwenden sollen, lesen Sie [rdc vs renet](/en/docs/rdc-vs-renet). Kurz gesagt: Verwenden Sie `rdc` für normale Operationen und `renet` direkt nur für erweiterte Aufgaben auf der Serverseite.

### Unterstützte Betriebssysteme

Entfernte Server führen die `renet`-Binary aus und hosten die verschlüsselten, repo-spezifischen Docker-Daemons. Die folgenden fünf Distributionen werden von der Bridge Workers-Matrix in CI bei jedem Pull Request getestet und sind die einzigen offiziell unterstützten:

| Betriebssystem | Version | Standard-Kernel | Hinweise |
|----------------|---------|-----------------|----------|
| Ubuntu | 24.04 LTS | 6.8 | Empfohlen. AppArmor standardmäßig aktiviert. |
| Debian | 13 (Trixie) | 6.12 | Debian 12 funktioniert auch (Kernel 6.1 minimum). |
| Fedora | 43 | 6.12 | SELinux standardmäßig im Enforcing-Modus. |
| openSUSE Leap | 16.0 | 6.4+ | AppArmor standardmäßig aktiviert. |
| Oracle Linux | 10 | UEK 7+ | Verwendet UEK, das das btrfs-Modul beibehält. SELinux standardmäßig im Enforcing-Modus. Siehe "Warum UEK?" unten. |

Alle Einträge sind `x86_64`. `arm64` wird gebaut, aber nicht kontinuierlich für jedes Server-OS getestet; eröffnen Sie ein Issue, wenn Sie es auf einer bestimmten Distribution benötigen. Andere Linux-Distributionen mit systemd, Docker-Unterstützung und cryptsetup können funktionieren, werden aber nicht offiziell unterstützt und können bei Upgrades ohne Vorankündigung aufhören zu funktionieren.

#### Warum UEK? (und warum Rocky 10 / Standard-RHEL 10 nicht unterstützt wird)

Das verschlüsselte Speicher-Backend von Rediacc benötigt das integrierte `btrfs`-Kernelmodul. **Der Standard-Kernel von RHEL 10 wird ohne dieses ausgeliefert**: `modprobe btrfs` schlägt mit "Module btrfs not found" fehl und `dnf search btrfs` gibt nichts zurück. Rocky Linux 10 und AlmaLinux 10 erben denselben Kernel und können daher nicht als Rediacc-Server betrieben werden.

Oracle Linux 10 verwendet standardmäßig den **Unbreakable Enterprise Kernel (UEK)**, der btrfs integriert behält. Das ist das einzige RHEL-kompatible Ziel auf der unterstützten Liste. Wenn Sie unbedingt einen RHEL-basierten Server betreiben müssen, verwenden Sie Oracle Linux 10 mit UEK. (Die Grundlage für diese Entscheidung liegt in `.github/workflows/ct-tests.yml` als CI Bridge Workers-Matrix.)

#### Nur für Workstations (CLI-Installationsziele)

Die `rdc`-CLI lässt sich zusätzlich sauber auf Alpine 3.19+ (APK mit der `gcompat`-Kompatibilitätsschicht, automatisch installiert) und Arch Linux (Rolling, via pacman) installieren. Dies sind nur clientseitige Installationspfade (siehe [Installation](/en/docs/installation)) und werden nicht als `renet`-Serverziele unterstützt.

### Sicherheitsrichtlinien nach Betriebssystem

Der repo-spezifische Docker-Daemon und die Repo-Container laufen mit **Standard-Container-Labels** auf jedem unterstützten OS. `rdc config machine setup` installiert keine benutzerdefinierten SELinux-Richtlinien oder AppArmor-Profile. Verhalten nach Betriebssystem:

- **Ubuntu 24.04, openSUSE Leap 16.0**: AppArmor ist standardmäßig aktiviert. Das Standard-Docker-Container-Profil wird angewendet; kein zusätzliches Setup erforderlich.
- **Fedora 43, Oracle Linux 10**: SELinux läuft im Enforcing-Modus. Der repo-spezifische Daemon kennzeichnet Container mit dem Standard-`container_t`-Kontext. Keine benutzerdefinierte SELinux-Richtlinie erforderlich.
- **CRIU** (Checkpoint/Restore) ist der einzige Fall, der das AppArmor-Profil mit `apparmor=unconfined` umgeht, da die AppArmor-Unterstützung von upstream CRIU noch nicht stabil ist. Siehe die CRIU-Hinweise in [Regeln von Rediacc](/en/docs/rules-of-rediacc).

Wenn ein Setup-Schritt mit SELinux-AVC-Ablehnungen oder AppArmor-Zurückweisungen fehlschlägt, lesen Sie [Fehlerbehebung](/en/docs/troubleshooting) unter "Distributionsspezifische Setup-Probleme".

### Server-Voraussetzungen

- Ein Benutzerkonto mit `sudo`-Rechten (passwortloses sudo empfohlen)
- Ihr öffentlicher SSH-Schlüssel in `~/.ssh/authorized_keys` hinterlegt
- Mindestens 20 GB freier Speicherplatz (mehr je nach Ihren Workloads)
- Internetzugang zum Abrufen von Docker-Images (oder eine private Registry)

### Automatisch installiert

Der Befehl `rdc config machine setup` installiert Folgendes auf dem entfernten Server:

- **Docker** und **containerd** (Container-Runtime)
- **cryptsetup** (LUKS-Festplattenverschlüsselung)
- **renet**-Binary (per SFTP hochgeladen)

Sie müssen diese nicht manuell installieren.

## Lokale virtuelle Maschinen (Optional)

Wenn Sie Deployments lokal mit `rdc ops` testen möchten, benötigt Ihre Workstation Virtualisierungsunterstützung: KVM auf Linux oder QEMU auf macOS. Lesen Sie den Leitfaden [Experimentelle VMs](/en/docs/experimental-vms) für Einrichtungsschritte und Plattformdetails.
