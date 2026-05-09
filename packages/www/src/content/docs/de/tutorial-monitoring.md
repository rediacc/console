---
title: "Monitoring"
description: "Prüfen Sie den Zustand Ihrer Server und Repos von Ihrem Laptop aus mit rdc machine-Befehlen."
category: "Tutorials"
subcategory: advanced
order: 12
language: de
sourceHash: "e6eaaed180c35e36"
sourceCommit: "be90e8e7896623c088b86360ec29c1baef2e86b4"
---

# Monitoring

Ihre App ist deployed, live und gesichert. Stellen Sie jetzt sicher, dass alles gesund bleibt. `rdc` gibt Ihnen ein vollständiges Bild jedes Servers (Zustand, Container, Repos) von Ihrem Laptop aus.

## Tutorial ansehen

![Tutorial: Monitoring](/assets/tutorials/tutorial-monitoring.cast)

## Drei Dinge, die Sie prüfen können

![Zustand, Container, Repos](/img/tutorials/tutorial-monitoring/slide-1.svg)

## Zustand: Systeminformationen

Beginnen Sie mit der Systemansicht:

```bash
time rdc machine query --name my-server --system
```

Das zeigt System-Uptime, Festplattennutzung und Speicherstatus. Wenn etwas nicht stimmt, meldet es sich.

## Container

Alle laufenden Container über jedes Repo auf der Maschine anzeigen:

```bash
time rdc machine query --name my-server --containers
```

Sie erhalten Name, Status, Zustand, CPU und Speicher für jeden Container, plus welches Repo ihn besitzt.

## Repos

Ihre Repositories prüfen:

```bash
time rdc machine query --name my-server --repositories
```

Das zeigt jedes Repo mit seiner Größe, Einhängestatus, Docker-Status und Festplattennutzung.

## Alles auf einmal

```bash
time rdc machine query --name my-server
```

Systeminformationen, Repos, Container, alles in einem Befehl. Derselbe `query`-Befehl ohne Filter gibt das vollständige Bild zurück. Mit `--system`, `--containers`, `--repositories`, `--services`, `--network` oder `--block-devices` wird er auf genau diesen Bereich eingeschränkt.

## Lokale Plausibilitätsprüfung

`rdc doctor` prüft Ihr lokales Setup (Node, SSH-Schlüssel, `renet`, Docker), unabhängig von einem bestimmten Server:

```bash
time rdc doctor
```

## Sie sind fertig

Das ist die vollständige Serie. Sie können jetzt installieren, konfigurieren, deployen, forken, live gehen, Autostart einrichten, sichern und überwachen. Alles aus Ihrem Terminal, alles auf Ihren eigenen Servern.
