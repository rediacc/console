---
title: "Ein Repository forken"
description: "Klonen Sie ein gesamtes Repository (App, Datenbank, Dateien) in Sekunden. Beliebige Größe. Null zusätzlicher Speicher."
category: "Tutorials"
subcategory: advanced
order: 7
language: de
sourceHash: "9237f00dce2ee5ec"
---

# Ein Repository forken

Das ist das Killer-Feature: Eine gesamte Produktionsumgebung (die App, die Datenbank, die Konfigurationsdateien) in Sekunden klonen. Beliebige Größe. Null zusätzlicher Speicher. So oft forken, wie Sie möchten.

Der Leitspruch: **Produktion klonen, nichts kaputt machen.**

## Tutorial ansehen

![Tutorial: Ein Repository forken](/assets/tutorials/tutorial-forking.cast)

## Etwas zum Verlieren einrichten

Geben Sie der laufenden App zunächst eine Datei, damit Sie die Isolation des Forks beweisen können. Öffnen Sie das Repo in VS Code:

```bash
rdc vscode connect -m my-server -r my-app
```

Erstellen Sie im Repo eine Markierungsdatei:

```bash
time echo "Hello from production" > index.html
```

Jetzt forken.

## Forken

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![Der Parent verzweigt sich in unabhängige Klone](/img/tutorials/tutorial-forking/slide-1.svg)

Ein Befehl. Alles wurde geklont (die App, die Datenbank, die Konfigurationsdateien), und es dauerte Sekunden. Führen Sie es erneut aus und Sie erhalten einen weiteren unabhängigen Klon.

## Warum ist es so schnell?

![Das Teilen eines Ordner-Links ist gleich schnell, unabhängig von der Größe des Ordners](/img/tutorials/tutorial-forking/slide-2.svg)

Stellen Sie sich vor, Sie teilen einen Ordner-Link. Der Link ist gleich, egal ob der Ordner klein oder riesig ist. Der Ordner ist schwer, der Link ist leicht.

![1 GB, 100 GB, 1 TB. Immer die gleiche Zeit.](/img/tutorials/tutorial-forking/slide-3.svg)

Forken funktioniert genauso. 1 GB, 100 GB, 1 TB. Immer die gleiche Zeit.

## Was geteilt wird, was Ihnen gehört

![Viele Spiegel, eine Sonne: gemeinsame Basis, Ihre Änderungen gehören Ihnen](/img/tutorials/tutorial-forking/slide-4.svg)

Stellen Sie sich das Parent-Repo als die Sonne vor. Sie können die Sonne nicht festhalten, aber Sie können einen Spiegel halten, der sie auffängt. Dieser Spiegel ist Ihr Fork. Malen Sie auf den Spiegel, und Ihre Zeichnungen gehören Ihnen. Die Sonne bleibt gleich, egal wie viele Spiegel ihr gegenüberstehen.

> Sie können die Sonne nicht festhalten, aber Sie können sie in einem Spiegel halten.

## Was, wenn der Parent sich später ändert?

![Ein Fork ist ein eingefrorenes Foto; der Parent fließt weiter wie ein Fluss](/img/tutorials/tutorial-forking/slide-5.svg)

Denken Sie jetzt an einen Fluss. Das Wasser fließt weiter. In jedem Moment ist es anders. Wenn Sie forken, machen Sie ein Foto des Flusses, eingefroren in diesem Moment. Der Fluss fließt weiter. Ihr Foto nicht.

Wenn sich das Parent-Repo später ändert, bleibt Ihr Fork dort, wo er war.

> Sie können einen Fluss nicht festhalten, aber Sie können ihn in einem Foto festhalten.

## Speichernutzung bleibt konstant

![Fünf Forks eines 100-GB-Repos, insgesamt immer noch etwa 100 GB](/img/tutorials/tutorial-forking/slide-6.svg)

Deshalb läuft Ihr Speicher nicht voll. Fünf Forks eines 100-GB-Repos? Insgesamt immer noch etwa 100 GB. Sie zahlen nur Speicher für das, was Sie in jedem Fork ändern.

> Forken Sie fünfmal, wenn Sie möchten. Ihr Speicher wird es kaum bemerken.

## Was Forks *nicht* erben: Secrets

Es gibt eine Sache, der der Fork bewusst nicht folgt: Secrets. Ein Fork startet ohne API-Schlüssel, ohne Datenbankpasswörter, ohne Stripe-Tokens. Deshalb funktioniert "Produktion klonen, nichts kaputt machen" wirklich. Ihre Sandbox kann keine echten Kunden belasten, weil sie nicht so tun kann, als wären Sie es. Das richten wir ordentlich im Tutorial [Secrets verwalten](/de/docs/tutorial-managing-secrets) ein.

## Isolation verifizieren

Beide Repos nebeneinander auflisten:

```bash
time rdc repo list -m my-server
```

Sie sehen `my-app` und `my-app:experiment`, die gleichzeitig laufen.

Im Original-Repo prüfen, was läuft:

```bash
time docker ps
```

Notieren Sie die Betriebszeit. Das sind die Original-Container. Jetzt zum Fork wechseln:

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

Gleiche Images, aber die Betriebszeit ist frisch. Diese wurden gestartet, als der Fork erstellt wurde.

Den Unterschied noch deutlicher machen. Einen Container nur zum Fork hinzufügen:

```bash
time docker run --rm -it -d nginx
time docker ps
```

Nginx läuft, aber nur innerhalb dieses Forks.

Etwas Destruktives versuchen:

```bash
time rm index.html
```

Hier weg. Jetzt zurück zum Original:

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

Kein nginx. Die Container des Forks blieben im Fork. Und `index.html` ist noch hier, unberührt. Das Original hat nie etwas davon mitbekommen. Gleiche Images, getrennte Docker-Daemons, getrennte Dateisysteme.

## Aufräumen

Wenn Sie fertig sind, löschen Sie einfach den Fork:

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

Das Original bleibt genau so, wie es war. **Forken, experimentieren, Dinge kaputtmachen, löschen.** Kein Risiko.

---

Weiter: [Secrets verwalten](/de/docs/tutorial-managing-secrets).
