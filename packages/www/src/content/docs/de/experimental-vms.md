---
title: "Experimentelle VMs"
description: "Lokale VM-Cluster für Entwicklung und Tests mit rdc ops bereitstellen."
category: "Concepts"
order: 2
language: de
sourceHash: fa4069c48c650a79
---

# Experimentelle VMs

Lokale VM-Cluster auf Ihrer Workstation für Entwicklung und Tests bereitstellen — keine externen Cloud-Anbieter erforderlich.

## Voraussetzungen

`rdc ops` erfordert den **lokalen Adapter**. Es ist nicht mit dem Cloud-Adapter verfügbar.

```bash
rdc ops check
```

## Übersicht

Mit den `rdc ops`-Befehlen können Sie experimentelle VM-Cluster lokal erstellen und verwalten. Dies ist dieselbe Infrastruktur, die von der CI-Pipeline für Integrationstests verwendet wird, und steht nun für praktische Experimente zur Verfügung.

Anwendungsfälle:
- Rediacc-Deployments ohne externe VM-Anbieter testen (Linode, Vultr usw.)
- Repository-Konfigurationen lokal entwickeln und debuggen
- Die Plattform in einer vollständig isolierten Umgebung kennenlernen
- Integrationstests auf Ihrer Workstation ausführen

## Plattformunterstützung

| Plattform | Architektur | Backend | Status |
|-----------|-------------|---------|--------|
| Linux | x86_64 | KVM (libvirt) | In CI getestet |
| macOS | Intel | QEMU + HVF | In CI getestet |
| Linux | ARM64 | KVM (libvirt) | Unterstützt (nicht CI-getestet) |
| macOS | ARM (Apple Silicon) | QEMU + HVF | Unterstützt (nicht CI-getestet) |
| Windows | x86_64 / ARM64 | Hyper-V | Geplant |

**Linux (KVM)** verwendet libvirt für native Hardware-Virtualisierung mit Bridged-Networking.

**macOS (QEMU)** verwendet QEMU mit Apples Hypervisor Framework (HVF) für nahezu native Leistung, mit User-Mode-Networking und SSH-Port-Forwarding.

**Windows (Hyper-V)** Unterstützung ist geplant. Siehe [Issue #380](https://github.com/rediacc/console/issues/380) für Details. Erfordert Windows Pro/Enterprise.

## Voraussetzungen & Einrichtung

### Linux

```bash
# Voraussetzungen automatisch installieren
rdc ops setup

# Oder manuell:
sudo apt install libvirt-daemon-system virtinst qemu-utils cloud-image-utils docker.io
sudo systemctl enable --now libvirtd
```

### macOS

```bash
# Voraussetzungen automatisch installieren
rdc ops setup

# Oder manuell:
brew install qemu cdrtools
```

### Einrichtung überprüfen

```bash
rdc ops check
```

Dieser Befehl führt plattformspezifische Prüfungen durch und meldet Bestanden/Fehlgeschlagen für jede Voraussetzung.

## Schnellstart

```bash
# 1. Voraussetzungen prüfen
rdc ops check

# 2. Minimalen Cluster bereitstellen (Bridge + 1 Worker)
rdc ops up --basic

# 3. VM-Status prüfen
rdc ops status

# 4. SSH in die Bridge-VM
rdc ops ssh 1

# 4b. Oder direkt einen Befehl ausführen
rdc ops ssh 1 hostname

# 5. Abbauen
rdc ops down
```

## Cluster-Zusammensetzung

Standardmäßig stellt `rdc ops up` folgende VMs bereit:

| VM | ID | Rolle |
|----|-----|-------|
| Bridge | 1 | Primärknoten — führt den Rediacc-Bridge-Dienst aus |
| Worker 1 | 11 | Worker-Knoten für Repository-Deployments |
| Worker 2 | 12 | Worker-Knoten für Repository-Deployments |

Verwenden Sie das `--basic`-Flag, um nur die Bridge und den ersten Worker bereitzustellen (IDs 1 und 11).

Verwenden Sie `--skip-orchestration`, um VMs ohne Start der Rediacc-Dienste bereitzustellen — nützlich zum Testen der VM-Schicht isoliert.

## Konfiguration

Die Bridge-VM verwendet kleinere Standardwerte als Worker-VMs:

| VM-Rolle | CPUs | RAM | Festplatte |
|----------|------|-----|------------|
| Bridge | 1 | 1024 MB | 8 GB |
| Worker | 2 | 4096 MB | 16 GB |

Umgebungsvariablen überschreiben die Worker-VM-Ressourcen:

| Variable | Standard | Beschreibung |
|----------|---------|--------------|
| `VM_CPU` | 2 | CPU-Kerne pro Worker-VM |
| `VM_RAM` | 4096 | RAM in MB pro Worker-VM |
| `VM_DSK` | 16 | Festplattengröße in GB pro Worker-VM |
| `VM_NET_BASE` | 192.168.111 | Netzwerkbasis (nur KVM) |
| `RENET_DATA_DIR` | ~/.renet | Datenverzeichnis für VM-Festplatten und Konfiguration |

## Befehlsreferenz

| Befehl | Beschreibung |
|--------|-------------|
| `rdc ops setup` | Plattform-Voraussetzungen installieren (KVM oder QEMU) |
| `rdc ops check` | Voraussetzungen auf Installation und Funktion prüfen |
| `rdc ops up [options]` | VM-Cluster bereitstellen |
| `rdc ops down` | Alle VMs zerstören und aufräumen |
| `rdc ops status` | Status aller VMs anzeigen |
| `rdc ops ssh <vm-id> [command...]` | SSH in eine VM, oder Befehl darauf ausführen |

### `rdc ops up` Optionen

| Option | Beschreibung |
|--------|-------------|
| `--basic` | Minimaler Cluster (Bridge + 1 Worker) |
| `--lite` | VM-Bereitstellung überspringen (nur SSH-Schlüssel) |
| `--force` | Vorhandene VMs erzwungen neu erstellen |
| `--parallel` | VMs parallel bereitstellen |
| `--skip-orchestration` | Nur VMs, keine Rediacc-Dienste |
| `--backend <kvm\|qemu>` | Automatisch erkanntes Backend überschreiben |
| `--os <name>` | OS-Image (Standard: ubuntu-24.04) |
| `--debug` | Ausführliche Ausgabe |

## Plattformunterschiede

### Linux (KVM)
- Verwendet libvirt für VM-Lifecycle-Management
- Bridged-Networking — VMs erhalten IPs in einem virtuellen Netzwerk (192.168.111.x)
- Direktes SSH zu VM-IPs
- Erfordert `/dev/kvm` und den libvirtd-Dienst

### macOS (QEMU + HVF)
- Verwendet QEMU-Prozesse, die über PID-Dateien verwaltet werden
- User-Mode-Networking mit SSH-Port-Forwarding (localhost:222XX)
- SSH über weitergeleitete Ports, keine direkten IPs
- Cloud-init-ISOs werden über `mkisofs` erstellt

## Fehlerbehebung

### Debug-Modus

Fügen Sie `--debug` zu jedem Befehl für ausführliche Ausgabe hinzu:

```bash
rdc ops up --basic --debug
```

### Häufige Probleme

**KVM nicht verfügbar (Linux)**
- Prüfen Sie, ob `/dev/kvm` existiert: `ls -la /dev/kvm`
- Virtualisierung im BIOS/UEFI aktivieren
- Kernel-Modul laden: `sudo modprobe kvm_intel` oder `sudo modprobe kvm_amd`

**libvirtd läuft nicht (Linux)**
```bash
sudo systemctl enable --now libvirtd
```

**QEMU nicht gefunden (macOS)**
```bash
brew install qemu cdrtools
```

**VMs starten nicht**
- Festplattenspeicher in `~/.renet/disks/` prüfen
- `rdc ops check` ausführen, um alle Voraussetzungen zu verifizieren
- `rdc ops down` versuchen, dann `rdc ops up --force`
