---
title: "Produktionsmodus"
description: "Lassen Sie Ihre App unabhängig von Ihrem Laptop laufen und überleben Sie Server-Neustarts mit Autostart."
category: "Tutorials"
subcategory: advanced
order: 10
language: de
sourceHash: "0e070fcd877900ab"
---

# Produktionsmodus

Bisher haben Sie die App mit `renet dev up` von innerhalb des Repos gestartet. Das ist ideal für die Entwicklung. Für die Produktion verwalten Sie alles von Ihrem Laptop aus mit `rdc`. Klappen Sie Ihren Laptop zu, und die App läuft weiter.

## Tutorial ansehen

![Tutorial: Produktionsmodus](/assets/tutorials/tutorial-production-mode.cast)

## Entwicklung vs. Produktion

Der Unterschied ist einfach:

- `renet dev up` läuft **innerhalb des Repos**. Sie müssen verbunden sein.
- `rdc repo up` läuft **von Ihrem Laptop aus**. Danach ist keine Verbindung mehr nötig.

Drei Aktionen bringen Sie von der Entwicklung in die Produktion:

![Stoppen, starten, Autostart](/img/tutorials/tutorial-production-mode/slide-1.svg)

## Schritt 1: Entwicklungssitzung beenden

Verbinden Sie sich mit dem Repo und bringen Sie es herunter:

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## Schritt 2: Im Produktionsmodus starten

Vom Terminal Ihres Laptops aus:

```bash
time rdc repo up --name my-app -m my-server
```

Das war es. Ihre App läuft, und Sie können Ihren Laptop zuklappen. Der `Rediaccfile` kümmert sich um alles. `rdc repo up` ruft dieselbe `up`-Funktion auf, die `renet dev up` verwendet hat. Gleicher `Rediaccfile`, andere Art des Aufrufs.

## Schritt 3: Server-Neustarts überleben

Stellen Sie sicher, dass Ihre App automatisch startet, wenn der Server neu startet:

```bash
time rdc repo autostart enable --name my-app -m my-server
```

Prüfen Sie, welche Repos Autostart aktiviert haben:

```bash
time rdc repo autostart list -m my-server
```

## In der Produktion stoppen

Wenn Sie Ihre App stoppen müssen:

```bash
time rdc repo down --name my-app -m my-server
```

Ein Befehl hoch, ein Befehl runter. Alles von Ihrem Laptop.

---

Weiter: [Backup und Wiederherstellung](/de/docs/tutorial-backup-restore).
