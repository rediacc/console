---
title: "Ihre erste App deployen"
description: "Deployen Sie eine containerisierte App aus einer integrierten Vorlage mit renet dev up."
category: "Tutorials"
subcategory: essentials
order: 5
language: de
sourceHash: "f75b5b6a716e94bf"
---

# Ihre erste App deployen

Sie haben ein leeres Repository. `rdc` enthält integrierte Vorlagen, mit denen Sie echte Apps starten können, ohne ein `docker-compose` von Grund auf schreiben zu müssen. Drei Schritte: Vorlage auswählen, anwenden, starten.

## Tutorial ansehen

![Tutorial: Ihre erste App deployen](/assets/tutorials/tutorial-deploy-app.cast)

## Auswählen - Anwenden - Starten

![Vorlage auswählen, anwenden, starten](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## Schritt 1: Auswählen

Verfügbare Vorlagen durchsuchen:

```bash
time rdc repo template list
```

Sie sehen fertige Setups für gängige Apps: Postgres, Redis, Webserver und mehr.

## Schritt 2: Anwenden

Fügen Sie die Vorlage in Ihr Repo ein. Wir verwenden `app-postgres`:

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

Im Repo erscheinen zwei neue Dateien: `docker-compose.yml` und `Rediaccfile`. Die Compose-Datei beschreibt die Container. Der `Rediaccfile` definiert, was beim Start und Stopp der App passiert (die Lifecycle-Hooks `up` und `down`).

## Schritt 3: Starten

Sie befinden sich bereits in der Sandbox des Repos (über die VS Code-Verbindung aus dem vorherigen Tutorial), also verwenden Sie `renet` direkt:

```bash
time renet dev up
```

Das war es. Ihre App läuft. Überprüfen Sie es:

```bash
time docker ps
```

`docker ps` listet hier nur die Container dieses Repos auf. Andere Repos auf demselben Server haben ihre eigenen Docker-Daemons und sind von diesem vollständig unsichtbar.

---

Weiter: [Mit Ihrem Repo arbeiten](/de/docs/tutorial-work-with-repo).
