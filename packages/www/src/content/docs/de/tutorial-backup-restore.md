---
title: "Backup und Wiederherstellung"
description: "Übertragen Sie Ihr Repository auf externen Speicher und stellen Sie es auf einem neuen Server wieder her, wenn Sie es benötigen."
category: "Tutorials"
subcategory: advanced
order: 11
language: de
sourceHash: "8b48f3b19352aebe"
---

# Backup und Wiederherstellung

Ihre App läuft in der Produktion. Stellen Sie jetzt sicher, dass Sie sie nie verlieren. `rdc` kann Ihr gesamtes Repository (App, Datenbank, Dateien, Konfigurationen) auf externen Speicher übertragen und jederzeit zurückziehen. Ransomware, Hardwareausfall, alles überlebbar.

## Tutorial ansehen

![Tutorial: Backup und Wiederherstellung](/assets/tutorials/tutorial-backup-restore.cast)

## Drei Schritte

![Konfigurieren, übertragen, wiederherstellen](/img/tutorials/tutorial-backup-restore/slide-1.svg)

1. **Speicheranbieter konfigurieren.**
2. **Backup übertragen.**
3. **Wiederherstellen, wenn nötig.**

## Schritt 1: Speicher konfigurieren

Sie benötigen eine `rclone`-Konfigurationsdatei. Wenn Sie rclone bereits verwenden, importieren Sie sie direkt:

```bash
time rdc config storage import --file rclone.conf
```

Dies unterstützt S3, B2, Google Drive, Dropbox und viele mehr. Prüfen Sie, was eingerichtet ist:

```bash
time rdc config storage list
```

## Schritt 2: Backup übertragen

```bash
time rdc repo push --name my-app -m my-server --to my-storage
```

Ihr gesamtes Repository (App, Datenbank, Dateien, alles) ist jetzt gesichert. Da das Repository selbst verschlüsselt ist, ist auch das Backup verschlüsselt. Kein zusätzliches Schlüsselmanagement.

Backups jederzeit auflisten:

```bash
time rdc repo backup list --from my-storage -m my-server
```

## Warum kein Ausfall?

Die App läuft weiter, während das Backup hochlädt. Wie ist das konsistent?

Gleiche Logik wie bei einem [Fork](/de/docs/tutorial-forking). `rdc` forkt zuerst, dann lädt es den Fork hoch. Der Fork hält den Moment fest; Ihre Live-App läuft weiter. Kein Ausfall, keine Inkonsistenz.

## Schritt 3: Auf einem neuen Server wiederherstellen

Angenommen, Ihr Server fällt aus. Richten Sie einen neuen Server ein, fügen Sie ihn zu `rdc` hinzu und ziehen Sie:

```bash
time rdc repo pull --name my-app -m new-server --from my-storage
```

Dann starten:

```bash
time rdc repo up --name my-app -m new-server
```

Ihre App ist zurück. Gleiche Daten, gleiche Container, andere Maschine.

## Schnellere Backups: Maschine zu Maschine

Sie können auch direkt zwischen Maschinen übertragen, ohne Cloud-Speicher dazwischen:

```bash
time rdc repo push --name my-app -m my-server --to-machine backup-server
```

> **Tipp.** Speicher-Uploads senden immer alles. Maschine-zu-Maschine sendet nur den Unterschied. Der erste Maschine-zu-Maschine-Push dauert die übliche Zeit, aber jeder folgende Push ist deutlich schneller. Ideal für häufige Backups.

---

Weiter: [Monitoring](/de/docs/tutorial-monitoring).
