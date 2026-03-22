---
title: "Lokale VM-Bereitstellung"
description: "Einen lokalen VM-Cluster bereitstellen, Befehle über SSH ausführen und alles über die CLI wieder abbauen."
category: "Tutorials"
order: 1
language: de
sourceHash: "2fdc49f796b03e18"
---

# So stellen Sie lokale VMs mit Rediacc bereit

Infrastruktur lokal zu testen, bevor Sie in die Produktion deployen, spart Zeit und verhindert Fehlkonfigurationen. In diesem Tutorial stellen Sie einen minimalen VM-Cluster auf Ihrer Workstation bereit, überprüfen die Konnektivität, führen Befehle über SSH aus und bauen alles wieder ab. Am Ende haben Sie eine wiederholbare lokale Entwicklungsumgebung.

## Voraussetzungen

- Eine Linux- oder macOS-Workstation mit aktivierter Hardware-Virtualisierung
- Die `rdc` CLI installiert und eine Konfiguration mit dem lokalen Adapter initialisiert
- KVM/libvirt (Linux) oder QEMU (macOS) installiert — siehe [Experimentelle VMs](/de/docs/experimental-vms) für Einrichtungsanweisungen

## Interaktive Aufzeichnung

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

### Schritt 1: Systemanforderungen überprüfen

Bevor Sie bereitstellen, stellen Sie sicher, dass Ihre Workstation Virtualisierungsunterstützung hat und die erforderlichen Pakete installiert sind.

```bash
rdc ops check
```

Rediacc prüft auf Hardware-Virtualisierung (VT-x/AMD-V), erforderliche Pakete (libvirt, QEMU) und Netzwerkkonfiguration. Alle Prüfungen müssen bestanden werden, bevor Sie VMs erstellen können.

### Schritt 2: Minimalen VM-Cluster bereitstellen

```bash
rdc ops up --basic --skip-orchestration
```

Erstellt einen Zwei-VM-Cluster: eine **Bridge**-VM (1 CPU, 1024 MB RAM, 8 GB Festplatte) und eine **Worker**-VM (2 CPU, 4096 MB RAM, 16 GB Festplatte). Das Flag `--skip-orchestration` überspringt die Rediacc-Plattformbereitstellung und gibt Ihnen reine VMs nur mit SSH-Zugang.

> **Hinweis:** Die erste Bereitstellung lädt Basisimages herunter, was länger dauert. Nachfolgende Durchläufe verwenden zwischengespeicherte Images.

### Schritt 3: Cluster-Status prüfen

```bash
rdc ops status
```

Zeigt den Status jeder VM im Cluster an — IP-Adressen, Ressourcenzuweisung und Ausführungsstatus. Beide VMs sollten als laufend angezeigt werden.

### Schritt 4: Befehle auf einer VM ausführen

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

Führt Befehle auf der Bridge-VM (ID `1`) über SSH aus. Übergeben Sie einen beliebigen Befehl nach der VM-ID. Für eine interaktive Shell lassen Sie den Befehl weg: `rdc ops ssh 1`.

### Schritt 5: Cluster abbauen

Wenn Sie fertig sind, zerstören Sie alle VMs und geben Ressourcen frei.

```bash
rdc ops down
```

Entfernt alle VMs und bereinigt das Netzwerk. Der Cluster kann jederzeit mit `rdc ops up` neu bereitgestellt werden.

## Fehlerbehebung

**"KVM not available" oder "hardware virtualization not supported"**
Überprüfen Sie, ob die Virtualisierung in Ihren BIOS/UEFI-Einstellungen aktiviert ist. Unter Linux prüfen Sie mit `lscpu | grep Virtualization`. Unter WSL2 erfordert verschachtelte Virtualisierung bestimmte Kernel-Flags.

**"libvirt daemon not running"**
Starten Sie den libvirt-Dienst: `sudo systemctl start libvirtd`. Unter macOS überprüfen Sie, ob QEMU über Homebrew installiert ist: `brew install qemu`.

**"Insufficient memory for VM allocation"**
Der Basiscluster benötigt mindestens 6 GB freien RAM (1 GB Bridge + 4 GB Worker + Overhead). Schließen Sie andere ressourcenintensive Anwendungen oder reduzieren Sie die VM-Spezifikationen.

## Nächste Schritte

Sie haben einen lokalen VM-Cluster bereitgestellt, Befehle über SSH ausgeführt und ihn abgebaut. Um echte Infrastruktur zu deployen:

- [Experimentelle VMs](/de/docs/experimental-vms) — vollständige Referenz für `rdc ops`-Befehle, VM-Konfiguration und Plattformunterstützung
- [Tutorial: Maschinen-Einrichtung](/de/docs/tutorial-setup) — Remote-Maschinen registrieren und Infrastruktur konfigurieren
- [Schnellstart](/de/docs/quick-start) — einen containerisierten Service End-to-End deployen
