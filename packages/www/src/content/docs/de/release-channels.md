---
title: "Release-Kanäle"
description: "Was Edge und Stable unterscheidet und welchen Kanal man nutzen sollte."
category: "Concepts"
tags:
  - cli
  - operations
subcategory: platform
order: 2
language: de
sourceHash: "bb653747883615f5"
sourceCommit: "c69b28b08afd5e7602afd1e8efe90785e6e36938"
---

Rediacc liefert CLI-Updates über zwei Kanäle: **Stable** und **Edge**. Beide nutzen dasselbe Produkt, daher sind Konto, Plan und Limits auf beiden Kanälen identisch. Die Kanäle unterscheiden sich nur darin, wie früh ein Release bei Ihnen ankommt.

## Stable-Kanal

Stable ist der Standard. Ein Release erreicht ihn nur, nachdem er 7 Tage auf Edge ohne gemeldete Probleme verbracht hat.

- Empfohlen, wenn Sie eine konservative Update-Kadenz bevorzugen
- Nach 7 Testtagen auf Edge bereitgestellt
- Kritische Hotfixes können direkt verteilt werden

## Edge-Kanal

Edge nimmt jede Änderung in dem Moment auf, in dem sie in den Hauptzweig eingeführt wird. Es ist die Live-Version der Software, die kontinuierlich bereitgestellt wird.

- Bei jedem Merge in main veröffentlicht
- Dieselben Konten, Pläne und Limits wie bei Stable
- Ideal, um neue Funktionen früh auszuprobieren

## Ein Produkt, zwei Kanäle

Ihr Konto liegt in Ihrer Datenregion auf `eu.rediacc.cloud`, `us.rediacc.cloud` oder `asia.rediacc.cloud`, unabhängig vom Kanal. Ein Kanalwechsel berührt weder Konto noch Daten oder Abonnement. Mehr zu den Regionen finden Sie unter [Datenregionen](/de/docs/data-regions).

## Vergleich

| | Stable | Edge |
|---|---|---|
| **Bereitstellungsrhythmus** | Nach 7-tägiger Einlaufphase | Bei jedem Merge in main |
| **Stabilität** | 7 Tage getestet | Neuester Code, weniger Einlaufzeit |
| **Pläne und Limits** | Gleich | Gleich |
| **Konto und Daten** | Gemeinsam | Gemeinsam |
| **Geeignet für** | Produktion, kostenpflichtige Workloads | Early Access, Evaluierung |

## Wie Förderungen funktionieren

1. Jeder Merge in den Hauptzweig wird sofort auf Edge bereitgestellt.
2. Nach 7 Tagen ohne Probleme wird Edge automatisch auf Stable gefördert.
3. Kritische Hotfixes können gleichzeitig auf beide Kanäle verteilt werden.

Stable liegt also höchstens 7 Tage hinter Edge. Das Einlauffenster erkennt Regressionen auf Edge, bevor sie Stable erreichen.

## Welchen Kanal wählen?

**Stable wählen, wenn:**
- eine konservative Update-Kadenz mit 7-tägigem Einlauffenster bevorzugt wird
- Maximale Zuverlässigkeit gegenüber neuesten Funktionen bevorzugt wird

**Edge wählen, wenn:**
- Neue Funktionen frühzeitig ausprobiert werden sollen
- Die Plattform evaluiert wird
- Neuerer, weniger getesteter Code akzeptabel ist

## Installation

Die Installationsbefehle, Paketverwaltungskonfiguration und Docker-Tags für jeden Kanal finden sich unter [Installation](/de/docs/installation).

## CLI-Kanalverwaltung

Die CLI verwendet den Kanal, den Sie bei der Installation konfiguriert haben. So wechseln Sie:

```bash
rdc update --channel edge      # Zu Edge wechseln
rdc update --channel stable    # Zu Stable wechseln
```
