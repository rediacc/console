---
title: "Ihren ersten Server hinzufügen"
description: "Registrieren Sie Ihren ersten Server bei rdc, stellen Sie ihn bereit und verstehen Sie die rdc-plus-renet-Architektur."
category: "Tutorials"
subcategory: essentials
order: 3
language: de
sourceHash: "2b5de59f61cfb88c"
---

# Ihren ersten Server hinzufügen

Bevor Sie einen Server hinzufügen, ist es hilfreich zu verstehen, wie `rdc` funktioniert. Rediacc hat eine Zwei-Tool-Architektur: `rdc` auf Ihrem Laptop, `renet` auf dem Server.

## Tutorial ansehen

![Tutorial: Ihren ersten Server hinzufügen](/assets/tutorials/tutorial-add-server.cast)

## Warum zwei Tools?

![rdc auf dem Laptop, renet auf dem Server, SSH dazwischen](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`** ist die CLI auf Ihrem Laptop. Hier tippen Sie Befehle ein.
- **`renet`** ist der Orchestrator auf dem Server. Es verwaltet Verschlüsselung, Docker und Isolation.

Wenn Sie lokal einen Befehl ausführen, verbindet sich `rdc` über SSH und führt `renet` auf dem Server aus. Sie müssen sich niemals manuell per SSH in Ihre Server einloggen. `rdc` erledigt das für Sie.

## Schritt 1: Server registrieren

Teilen Sie `rdc` den Server mit. Ersetzen Sie Name, IP und Benutzer durch Ihre eigenen Angaben.

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## Schritt 2: Server bereitstellen

Die Einrichtung installiert `renet` und erstellt den verschlüsselten Datenspeicher auf dem Server.

```bash
time rdc config machine setup --name my-server
```

Wenn der Vorgang abgeschlossen ist, ist Ihr Server bereit, Repositories zu hosten.

## Wo die Konfiguration liegt

Überprüfen Sie, was `rdc` über Ihre Einrichtung weiß:

```bash
time rdc config show
```

Oder öffnen Sie die JSON-Datei direkt:

```bash
vim ~/.config/rediacc/rediacc.json
```

Diese einzelne Datei enthält alles: Maschinen, Repos, SSH-Schlüssel, Verschlüsselungsdaten. Kopieren Sie sie auf einen anderen Laptop und Sie können von dort aus direkt loslegen.

---

Weiter: [Ihr erstes Repository erstellen](/de/docs/tutorial-create-repo).
