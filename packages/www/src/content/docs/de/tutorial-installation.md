---
title: "Installation"
description: "Installieren Sie die rdc CLI auf Ihrem Laptop mit einem einzigen Befehl und überprüfen Sie die Installation mit rdc doctor."
category: "Tutorials"
subcategory: essentials
order: 1
language: de
sourceHash: "99d4ca1a4f89278e"
---

# Installation

Die Installation von `rdc` besteht aus drei Schritten: Öffnen Sie die Installationsseite, wählen Sie Ihr Betriebssystem aus und fügen Sie den Befehl in Ihr Terminal ein. Der gesamte Vorgang dauert in der Regel ein bis zwei Minuten.

## Tutorial ansehen

![Tutorial: Installation](/assets/tutorials/tutorial-installation.cast)

## Die drei Schritte

![Übersicht der drei Schritte](/img/tutorials/tutorial-installation/slide-1.svg)

1. Öffnen Sie die [Installationsseite](/en/install).
2. Wählen Sie Ihr Betriebssystem.
3. Kopieren Sie den Installationsbefehl und fügen Sie ihn in Ihr Terminal ein.

## Installation auf Ihrer Plattform

Die Installationsseite generiert den richtigen Befehl für Sie. Hier sind die kanonischen Einzeiler.

**Linux / macOS:**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> Das Präfix `time` ist ein Shell-Trick, der anzeigt, wie lange ein Befehl gedauert hat. Wir verwenden es in dieser Serie, damit Sie die tatsächliche Geschwindigkeit jedes Schritts sehen können. Es ist optional. Lassen Sie es weg, wenn Sie es nicht benötigen.

## Installation überprüfen

Sobald das Skript abgeschlossen ist, prüfen Sie, ob alles vorhanden ist, was `rdc` benötigt:

```bash
time rdc doctor
```

`rdc doctor` prüft Node, SSH und die übrigen Abhängigkeiten von `rdc` und meldet eventuelle Lücken.

## Warum `rdc` auf Ihrem Laptop liegt

![rdc auf Ihrem Laptop, renet auf dem Server](/img/tutorials/tutorial-installation/slide-2.svg)

`rdc` ist die CLI auf Ihrem Laptop. Der Server betreibt eine separate Komponente namens `renet`, die `rdc` über SSH bereitstellt und steuert. Sie müssen sich niemals manuell per SSH in einen Server einloggen. `rdc` erledigt das für Sie.

Das richten wir in den nächsten zwei Tutorials ordentlich ein.

---

Weiter: [SSH-Schlüsselkonfiguration](/de/docs/tutorial-ssh-keys).
