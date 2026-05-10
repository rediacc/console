---
title: "Ihr erstes Repository erstellen"
description: "Erstellen Sie ein verschlüsseltes Repository auf Ihrem Server und öffnen Sie es in VS Code."
category: "Tutorials"
subcategory: essentials
order: 4
language: de
sourceHash: "1294b0494f20671b"
---

# Ihr erstes Repository erstellen

Ein Rediacc-Repository ist eine einzelne verschlüsselte Datei auf Ihrem Server. Wenn es eingebunden wird, wird es zu einem Ordner mit einem eigenen Docker-Daemon und eigenen Anwendungsdaten: vollständig isoliert, vollständig portierbar.

Stellen Sie es sich wie einen USB-Stick für die Produktion vor: eine ruhende Datei, ein laufender Server.

## Tutorial ansehen

![Tutorial: Ihr erstes Repository erstellen](/assets/tutorials/tutorial-create-repo.cast)

## Datei auf dem Datenträger, Umgebung beim Einhängen

![Verschlüsselte Datei wird als isolierter Ordner eingehängt](/img/tutorials/tutorial-create-repo/slide-1.svg)

Die Form auf dem Datenträger ist ein einzelnes verschlüsseltes Image. Wenn es eingehängt wird, erhalten Sie:

- Einen dedizierten Docker-Daemon (getrennt vom Host-Daemon)
- Anwendungsdaten innerhalb des verschlüsselten Volumes
- Loopback-IPs, die mit nichts anderem auf dem Server kollidieren

Repositories sind portierbar. Sie können eines zwischen Maschinen verschieben, es sichern oder sofort forken. Jedes Repo ist von jedem anderen Repo auf demselben Server isoliert.

## Eines erstellen

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

Hiermit wird ein 2 GB großes verschlüsseltes Repository auf `my-server` erstellt. Überprüfen Sie es:

```bash
time rdc repo list -m my-server
```

## In VS Code öffnen

```bash
rdc vscode connect -m my-server -r my-app
```

VS Code öffnet sich direkt innerhalb des Repositorys. Beachten Sie, dass der Arbeitsbereich leer ist. Das ist Ihre isolierte Umgebung. Alles, was Sie hier erstellen, lebt innerhalb des verschlüsselten Volumes und ist für jedes andere Repo auf demselben Server unsichtbar.

---

Weiter: [Ihre erste App deployen](/de/docs/tutorial-deploy-app).
