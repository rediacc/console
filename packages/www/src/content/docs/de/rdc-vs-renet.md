---
title: "rdc vs renet"
description: "Wann Sie rdc verwenden und wann renet."
category: "Guides"
order: 1
language: de
sourceHash: "a002ea55958664f1"
---

# rdc vs renet

Rediacc verwendet zwei Binaries:

- `rdc` ist die benutzerorientierte CLI auf Ihrer Workstation.
- `renet` ist das entfernte Low-Level-Binary auf dem Server.

Fur fast alle taglichen Ablaufe sollten Sie `rdc` nutzen.

## Mentales Modell

Sehen Sie `rdc` als Control Plane und `renet` als Data Plane.

`rdc`:
- Liest lokalen Kontext und Maschinenzuordnungen
- Verbindet sich per SSH mit Servern
- Provisioniert/aktualisiert `renet` bei Bedarf
- Fuhrt die passende Remote-Operation fur Sie aus

`renet`:
- Lauft mit erhohten Rechten auf dem Server
- Verwaltet Datastore, LUKS-Volumes, Mounts und isolierte Docker-Daemons
- Fuhrt Low-Level-Operationen auf Repository- und Systemebene aus

## Was Sie in der Praxis nutzen sollten

### `rdc` verwenden (Standard)

Nutzen Sie `rdc` fur normale Workflows:

```bash
rdc context setup-machine server-1
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount
rdc repo down my-app -m server-1
rdc machine status server-1
```

### `renet` verwenden (fortgeschritten / Remote-Seite)

Verwenden Sie `renet` direkt nur dann, wenn Sie bewusst Low-Level-Kontrolle auf dem Server brauchen, z. B.:

- Notfall-Debugging direkt auf dem Server
- Host-Level-Wartung und Wiederherstellung
- Prufen von Interna, die in `rdc` nicht direkt verfugbar sind

Die meisten Nutzer mussen `renet` im Alltag nicht direkt aufrufen.

## Hinweis zu Rediaccfile

Sie konnen `renet compose -- ...` in einem `Rediaccfile` sehen. Das ist erwartetes Verhalten: Rediaccfile-Funktionen laufen auf der Remote-Seite, wo `renet` verfugbar ist.

Von Ihrer Workstation aus starten/stoppen Sie Workloads in der Regel weiter mit `rdc repo up` und `rdc repo down`.
