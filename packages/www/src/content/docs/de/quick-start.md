---
title: "Schnellstart"
description: "Starten Sie einen containerisierten Dienst auf Ihrem Server in 5 Minuten."
category: "Guides"
order: -1
language: de
---

# Schnellstart

Stellen Sie eine verschlusselte, isolierte Container-Umgebung auf Ihrem eigenen Server in 5 Minuten bereit. Diese Anleitung verwendet den **lokalen Modus** — keine Cloud-Konten oder SaaS-Abhangigkeiten.

## Voraussetzungen

- Eine Linux- oder macOS-Workstation
- Ein Remote-Server (Ubuntu 24.04+, Debian 12+ oder Fedora 43+) mit SSH-Zugang und sudo-Berechtigungen
- Ein SSH-Schlusselpaar (z.B. `~/.ssh/id_ed25519`)

## 1. CLI installieren

```bash
curl -fsSL https://get.rediacc.com | sh
```

## 2. Kontext erstellen

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

## 3. Server hinzufugen

```bash
rdc context add-machine server-1 --ip <your-server-ip> --user <your-ssh-user>
```

## 4. Server einrichten

```bash
rdc context setup-machine server-1
```

Dies installiert Docker, cryptsetup und die renet-Binary auf Ihrem Server.

## 5. Verschlusseltes Repository erstellen

```bash
rdc repo create my-app -m server-1 --size 5G
```

## 6. Dienste bereitstellen

Mounten Sie das Repository, erstellen Sie Ihre `docker-compose.yml` und `Rediaccfile` darin und starten Sie dann:

```bash
rdc repo up my-app -m server-1 --mount
```

## 7. Verifizieren

```bash
rdc machine containers server-1
```

Sie sollten Ihre laufenden Container sehen.

## Was ist Rediacc?

Rediacc stellt containerisierte Dienste auf entfernten Servern bereit, die Sie kontrollieren. Alles wird im Ruhezustand mit LUKS verschlusselt, jedes Repository erhalt seinen eigenen isolierten Docker-Daemon, und die gesamte Orchestrierung erfolgt uber SSH von Ihrer Workstation aus.

Keine Cloud-Konten. Keine SaaS-Abhangigkeiten. Ihre Daten bleiben auf Ihren Servern.

## Nachste Schritte

- **[Architektur](/de/docs/architecture)** — Verstehen Sie, wie Rediacc funktioniert: Modi, Sicherheitsmodell, Docker-Isolation
- **[Server-Einrichtung](/de/docs/setup)** — Detaillierte Einrichtungsanleitung: Kontexte, Maschinen, Infrastrukturkonfiguration
- **[Repositories](/de/docs/repositories)** — Repositories erstellen, verwalten, skalieren, forken und validieren
- **[Dienste](/de/docs/services)** — Rediaccfiles, Service-Netzwerke, Bereitstellung, Autostart
- **[Backup & Wiederherstellung](/de/docs/backup-restore)** — Sicherung auf externen Speicher und automatisierte Backups planen
- **[Monitoring](/de/docs/monitoring)** — Server-Gesundheit, Container, Dienste, Diagnose
- **[Werkzeuge](/de/docs/tools)** — Dateisynchronisation, SSH-Terminal, VS Code-Integration
- **[Migrationsleitfaden](/de/docs/migration)** — Bestehende Projekte in Rediacc-Repositories uberfuhren
- **[Fehlerbehebung](/de/docs/troubleshooting)** — Losungen fur haufige Probleme
- **[CLI-Referenz](/de/docs/cli-application)** — Vollstandige Befehlsreferenz
