---
title: rdc vs renet
description: Wann Sie rdc verwenden und wann renet — eine Übersicht.
category: Concepts
order: 1
language: de
sourceHash: 0396eec8815a0b4e
---

# rdc vs renet

Rediacc hat zwei Binaries. Hier erfahren Sie, wann Sie welches verwenden.

| | rdc | renet |
|---|-----|-------|
| **Läuft auf** | Ihrer Workstation | Dem entfernten Server |
| **Verbindet über** | SSH | Läuft lokal mit Root-Rechten |
| **Verwendet von** | Allen Benutzern | Nur für fortgeschrittenes Debugging |
| **Installation** | Sie installieren es | `rdc` stellt es automatisch bereit |

> Für die tägliche Arbeit verwenden Sie `rdc`. Sie benötigen `renet` nur selten direkt.

## Wie sie zusammenarbeiten

`rdc` verbindet sich über SSH mit Ihrem Server und führt `renet`-Befehle für Sie aus. Sie geben einen einzigen Befehl auf Ihrer Workstation ein, und `rdc` übernimmt den Rest:

1. Liest Ihre lokale Konfiguration (`~/.rediacc/config.json`)
2. Verbindet sich über SSH mit dem Server
3. Aktualisiert die `renet`-Binary bei Bedarf
4. Führt die entsprechende `renet`-Operation auf dem Server aus
5. Gibt das Ergebnis an Ihr Terminal zurück

## Verwenden Sie `rdc` für die normale Arbeit

Alle gängigen Aufgaben laufen über `rdc` auf Ihrer Workstation:

```bash
# Einen neuen Server einrichten
rdc context setup-machine server-1

# Ein Repository erstellen und starten
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount

# Ein Repository stoppen
rdc repo down my-app -m server-1

# Maschinengesundheit prüfen
rdc machine health server-1
```

Siehe den [Schnellstart](/de/docs/quick-start) für eine vollständige Anleitung.

## Verwenden Sie `renet` für serverseitiges Debugging

Sie benötigen `renet` nur direkt, wenn Sie sich per SSH auf einem Server anmelden für:

- Notfall-Debugging, wenn `rdc` keine Verbindung herstellen kann
- Überprüfung von Systeminterna, die über `rdc` nicht verfügbar sind
- Low-Level-Wiederherstellungsoperationen

Alle `renet`-Befehle benötigen Root-Rechte (`sudo`). Siehe [Server-Referenz](/de/docs/server-reference) für die vollständige Liste der `renet`-Befehle.

## Experimentell: `rdc ops` (Lokale VMs)

`rdc ops` umschließt `renet ops` für die Verwaltung lokaler VM-Cluster auf Ihrer Workstation:

```bash
rdc ops setup       # Voraussetzungen installieren (KVM oder QEMU)
rdc ops up --basic  # Einen minimalen Cluster starten
rdc ops status      # VM-Status prüfen
rdc ops ssh 1       # SSH in die Bridge-VM
rdc ops down        # Cluster zerstören
```

Diese Befehle führen `renet` lokal aus (nicht über SSH). Siehe [Experimentelle VMs](/de/docs/experimental-vms) für die vollständige Dokumentation.

## Hinweis zum Rediaccfile

In einem `Rediaccfile` können Sie `renet compose -- ...` sehen. Das ist normal — Rediaccfile-Funktionen laufen auf dem Server, wo `renet` verfügbar ist.

Von Ihrer Workstation aus starten und stoppen Sie Workloads mit `rdc repo up` und `rdc repo down`.
