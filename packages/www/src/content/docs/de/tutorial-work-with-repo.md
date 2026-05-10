---
title: "Mit Ihrem Repo arbeiten"
description: "Tunneln Sie einen Port zu Ihrem Browser, führen Sie Befehle in der Sandbox aus und synchronisieren Sie Dateien zwischen Ihrem Laptop und dem Repo."
category: "Tutorials"
subcategory: essentials
order: 6
language: de
sourceHash: "3d56eb69e72c1a5a"
---

# Mit Ihrem Repo arbeiten

Ihre App läuft, aber bisher haben Sie sie nur über `docker ps` gesehen. Drei Befehle decken den täglichen Workflow ab: **tunnel**, um die App im Browser anzuzeigen, **term**, um Befehle in der Sandbox auszuführen, **sync**, um Dateien zwischen Laptop und Repo zu verschieben.

## Tutorial ansehen

![Tutorial: Mit Ihrem Repo arbeiten](/assets/tutorials/tutorial-work-with-repo.cast)

## Die täglichen drei

![Tunnel, term, sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel**: App im Browser öffnen.
2. **Term**: Befehl in der Sandbox ausführen.
3. **Sync**: Dateien rein- und rausschieben.

## Tunnel: App im Browser anzeigen

Die App läuft auf dem Server, nicht auf Ihrem Laptop. Leiten Sie den Port eines Containers über SSH weiter:

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

Öffnen Sie `localhost` in Ihrem Browser. Ihre App ist direkt da. Drücken Sie `Ctrl+C`, wenn Sie fertig sind.

Für einen anderen Container tauschen Sie `-c` aus und wählen den Port:

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term: Befehle im Repo ausführen

Überspringen Sie VS Code, wenn Sie nur eine Shell benötigen:

```bash
rdc term connect -m my-server -r my-app
```

Sie befinden sich nun in der Sandbox des Repos. Probieren Sie es aus:

```bash
time docker ps
```

Sie sehen nur die Container von `my-app`, dieselbe Ansicht wie in VS Code.

Für einmalige Befehle verwenden Sie `-c` und überspringen die interaktive Shell:

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync: Dateien zwischen Laptop und Repo verschieben

Einen Ordner von Ihrem Laptop ins Repo übertragen:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

Dateien zurückziehen:

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

Vorher eine Vorschau erstellen, wenn Sie unsicher sind. `--dry-run` zeigt, was sich ändern würde, ohne tatsächlich etwas zu kopieren:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel, term, sync. Drei Befehle decken den täglichen Ablauf ab.

---

Weiter: [Ein Repository forken](/de/docs/tutorial-forking).
