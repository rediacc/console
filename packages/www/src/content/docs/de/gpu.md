---
title: "GPU"
description: "Einem Repo über eine CDI-Geräte-Freigabe Zugriff auf eine GPU geben: die GPUs der Maschine auflisten, Geräte pro Repo freigeben und entziehen, eine Karte exklusiv reservieren und unter WSL arbeiten."
category: "Guides"
tags:
  - gpu
  - containers
subcategory: workloads
order: 7
language: de
sourceHash: "5a113ad69c52c63d"
---

# GPUs

Ein Repo erreicht eine GPU nur über eine **Geräte-Freigabe**. Die Maschine veröffentlicht ihre GPUs als benannte Geräte, und ein Operator gibt einem Repo die Namen frei, die es verwenden darf. Ein Repo ohne Freigabe bekommt keine GPU, und ein [Fork](/de/docs/repositories) startet ohne Freigabe, auch wenn das Eltern-Repo eine hat.

Die Namen folgen dem Container Device Interface (CDI), dem Standard, mit dem Docker ab Version 25 ein Gerät und alles beschreibt, was ein Container zu seiner Nutzung braucht. Ein CDI-Name hat die Form `<vendor>/<class>=<device>`, zum Beispiel `nvidia.com/gpu=all`.

## Was eine CDI-Freigabe ist

Jedes Repo betreibt einen eigenen Docker-Daemon hinter einem API-Gate, das jeden Weg ablehnt, Hardware an einen Container zu hängen. Eine GPU lässt sich also nicht mit Flags für `docker run` erreichen. Die Freigabe ist die einzige Tür. Sie hält einen exakten CDI-Namen für ein Repo fest, und das Gate lässt dann eine Container-Anfrage zu, die genau dieses Gerät nennt und nichts sonst.

- Freigaben gelten ab der nächsten Docker-Anfrage, ohne Neustart des Daemons.
- Eine Freigabe nennt genau ein Gerät. Die Freigabe von `nvidia.com/gpu=all` lässt `nvidia.com/gpu=all` zu, nicht `nvidia.com/gpu=0`. Für eine einzelne Karte wird der Name dieser Karte freigegeben.
- Beim Schreiben wird eine Freigabe gegen die Geräte-Specs der Maschine geprüft, ein falsch geschriebener Name wird also abgelehnt statt gespeichert.
- Eine Freigabe gehört zu dem Repo, für das sie erteilt wurde. Forks und Kopien brauchen eine eigene Freigabe.

## Die Maschine einrichten

`rdc machine setup <machine>` erkennt die GPUs der Maschine und hält das Ergebnis in `/etc/rediacc/gpu/inventory.json` fest. Ist eine NVIDIA-GPU vorhanden, installiert das Setup außerdem das NVIDIA Container Toolkit und erzeugt die CDI-Spec unter `/etc/cdi/nvidia.yaml`. Eine Maschine ohne GPU bekommt trotzdem eine Inventardatei mit leeren Listen.

Die Installation des Toolkits steuert die `renet setup`-Option `--install-nvidia-toolkit`:

| Wert | Verhalten |
|---|---|
| `auto` | Das Toolkit wird installiert, wenn eine NVIDIA-GPU vorhanden ist. Das ist der Standard. |
| `true` | Das Toolkit wird in jedem Fall installiert. |
| `false` | Das Toolkit wird übersprungen, und es entsteht keine NVIDIA-Spec. |

Das Setup konfiguriert keine Container-Runtime, denn zugelassen ist nur `runc`. Das Toolkit dient allein der Spec, und die Spec wird bei jedem Setup neu erzeugt, damit sie Treiberänderungen folgt.

Zwei Gerätearten stammen von Rediacc selbst und brauchen keine Userspace-Komponenten des Herstellers, weil sie nur Gerätedateien abbilden:

| Art | Geräte | Quelle |
|---|---|---|
| `rediacc.io/dri` | Eines pro Render-Node, etwa `rediacc.io/dri=renderD128` | `/dev/dri/renderD<N>` |
| `rediacc.io/amd` | `gpu<N>` für eine AMD-Karte und `all` | `/dev/kfd` plus der Render-Node der Karte |

NVIDIA-Geräte kommen aus der Spec des Toolkits: `nvidia.com/gpu=all` und ein Name pro Karte. AMD-Compute braucht den ROCm-Userspace im Container-Image, denn das Setup installiert kein ROCm.

## GPUs auflisten

```bash
rdc machine gpu list <machine>
rdc machine gpu list <machine> -o json
```

Die Tabelle zeigt jede GPU mit Name, Treiberversion und Speicher, die Plattform (nativ oder WSL), das Alter des Inventars und jeden CDI-Gerätenamen, der freigegeben werden kann. `-o json` gibt das Inventar so aus, wie es auf der Maschine steht. Die aktuell erteilten Freigaben werden live von der Maschine gelesen.

## Freigeben und entziehen

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=all
rdc repo gpu revoke <repo-ref> --device nvidia.com/gpu=all
```

`<repo-ref>` ist ein Repo-Name, optional mit Maschine, etwa `gpu-a@wsl-gpu`. Beide Befehle lassen sich mit verschiedenen `--device`-Werten wiederholen. Nach einer Freigabe startet ein Container in diesem Repo mit dem Gerät:

```bash
docker run --rm --device nvidia.com/gpu=all ubuntu:24.04 nvidia-smi -L
```

Derselbe Container wird in einem Repo ohne Freigabe abgelehnt, und die Meldung nennt die fehlende Freigabe.

## Exklusive Freigaben

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=0 --exclusive
```

Eine exklusive Freigabe reserviert ein Gerät für ein Repo. Sie wird abgelehnt, wenn ein anderes Repo denselben Namen hält, und solange sie besteht, wird jede Freigabe dieses Namens an ein anderes Repo abgelehnt. Die Prüfung läuft beim Erteilen, unter einer Sperre über alle Freigaben der Maschine.

Eine exklusive Freigabe ist eine Reservierung, kein Scheduler. Zwei Container im selben freigegebenen Repo teilen sich die Karte weiterhin.

## Abgelehnte Schreibweisen

Jeder andere Weg zu einer GPU bleibt abgelehnt, mit oder ohne Freigabe. Die CDI-Form ersetzt jeden davon.

| Abgelehnt | Stattdessen |
|---|---|
| `docker run --gpus all` | `docker run --device nvidia.com/gpu=all` |
| `runtime: nvidia` in Compose | `devices: [nvidia.com/gpu=all]` |
| `deploy.resources.reservations.devices` in Compose | `devices: [nvidia.com/gpu=all]` |
| `gpus: all` in Compose | `devices: [nvidia.com/gpu=all]` |
| Rohe `/dev/dri`- oder `/dev/kfd`-Geräte oder ein Bind unter `/dev` | `rediacc.io/dri=renderD128` oder `rediacc.io/amd=gpu0` |
| Device-cgroup-Regeln | Eine CDI-Freigabe für das Gerät |

Ein Compose-Service mit einem freigegebenen Gerät sieht so aus:

```yaml
services:
  inference:
    image: ubuntu:24.04
    command: nvidia-smi -L
    devices:
      - nvidia.com/gpu=all
```

Eine Gruppe wie `video` oder `render` über `group_add` wird akzeptiert, gewährt aber nichts, denn die Gruppe öffnet kein Gerät, das dem Repo nicht freigegeben wurde.

## WSL

Unter WSL2 stellt der Windows-Treiber die GPU über `/dev/dxg` und die Bibliotheken unter `/usr/lib/wsl/lib` bereit. Die Maschine meldet ihre Plattform als `wsl`, und das Setup erzeugt die NVIDIA-Spec im WSL-Modus:

```bash
nvidia-ctk cdi generate --mode=wsl --output=/etc/cdi/nvidia.yaml
```

Der Treiber liegt auf der Windows-Seite, deshalb wird ein Treiber-Update dort beim nächsten Lauf von `rdc machine setup` übernommen. Die Befehle zum Freigeben, Auflisten und Entziehen funktionieren wie auf einer nativen Maschine.

## Natives NVIDIA

Auf einer nativen NVIDIA-Maschine erzeugt der Dienst `nvidia-cdi-refresh` des Toolkits die Spec nach einer Installation, einer Treiberänderung und einem Boot neu. Das Setup richtet ihn auf `/etc/cdi/nvidia.yaml` aus, das einzige Spec-Verzeichnis, das der Docker-Daemon eines Repos liest. Läuft `nvidia-persistenced`, wird sein Socket für die Repo-Daemons sichtbar gemacht, weil die Spec ihn in Container einbindet.
