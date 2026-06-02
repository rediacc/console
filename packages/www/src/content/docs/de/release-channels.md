---
title: "Release-Kanäle"
description: "Was Edge und Stable unterscheidet und welchen Kanal man nutzen sollte."
category: "Concepts"
order: 2
language: de
sourceHash: "5fdcb0e8944f5d60"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

Rediacc liefert Updates über zwei Kanäle: **Stable** und **Edge**. Sie laufen auf separater Infrastruktur und tragen unterschiedliche Kompromisse.

## Stable-Kanal

Stable ist der Standard. Ein Release erreicht ihn nur, nachdem er 7 Tage auf Edge ohne gemeldete Probleme verbracht hat.

- Empfohlen, wenn Sie eine konservative Update-Kadenz bevorzugen und Zugang zu kostenpflichtigen Plänen möchten
- Nach 7 Testtagen auf Edge bereitgestellt
- Kritische Hotfixes können direkt verteilt werden
- Domains: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Edge-Kanal

Edge nimmt jede Änderung in dem Moment auf, in dem sie in den Hauptzweig eingeführt wird. Es ist die Live-Version der Software, die kontinuierlich bereitgestellt wird.

- Neueste Funktionen und Fixes, bei jedem Merge bereitgestellt
- Doppelte Community-Plan-Limits (siehe Tabelle unten)
- Dauerhaft kostenlos. Keine kostenpflichtigen Pläne auf Edge verfügbar.
- Separate Konten von Stable. Daten werden nicht zwischen Kanälen übertragen.
- Domains: `edge-eu.rediacc.com`, `edge-us.rediacc.com`, `edge-asia.rediacc.com`

## Vergleich

| | Stable | Edge |
|---|---|---|
| **Bereitstellungsrhythmus** | Nach 7-tägiger Einlaufphase | Bei jedem Merge in main |
| **Stabilität** | 7 Tage getestet | Neuester Code, weniger Einlaufzeit |
| **Community-Plan-Limits** | 10 GB Repos, 500 Ausstellungen/Monat, 2 Maschinen | 20 GB Repos, 1.000 Ausstellungen/Monat, 4 Maschinen |
| **Kostenpflichtige Pläne** | Verfügbar (Professional, Business, Enterprise) | Nicht verfügbar |
| **Konten** | Unabhängig | Unabhängig (von Stable getrennt) |
| **Geeignet für** | Produktion, kostenpflichtige Workloads | Tests, Evaluierung, Nebenprojekte, Early Access |

## Edge-Doppellimits

Nutzen Sie Edge im Community-Plan und Ihre Ressourcenlimits verdoppeln sich, ohne zusätzliche Kosten:

| Ressource | Stable Community | Edge Community |
|---|---|---|
| Repository-Größe | 10 GB | 20 GB |
| Lizenzausstellungen pro Monat | 500 | 1.000 |
| Maschinenaktivierungen | 2 | 4 |

Höhere Limits oder kostenpflichtige Funktionen benötigt? Erstellen Sie Ihr Konto auf Stable und upgraden Sie dort.

## Getrennte Konten

Edge und Stable laufen auf separater Infrastruktur mit separaten Datenbanken. Ein Konto auf einem Kanal existiert nicht auf dem anderen, und es gibt keinen Migrationspfad. Wer mit Edge beginnt und später einen kostenpflichtigen Plan möchte, muss ein neues Konto auf Stable von Grund auf erstellen.

## Wie Förderungen funktionieren

1. Jeder Merge in den Hauptzweig wird sofort auf Edge bereitgestellt.
2. Nach 7 Tagen ohne Probleme wird Edge automatisch auf Stable gefördert.
3. Kritische Hotfixes können gleichzeitig auf beide Kanäle verteilt werden.

Stable liegt also höchstens 7 Tage hinter Edge. Das Einlauffenster erkennt Regressionen auf Edge, bevor sie Stable erreichen.

## Welchen Kanal wählen?

**Stable wählen, wenn:**
- eine konservative Update-Kadenz mit 7-tägigem Einlauffenster bevorzugt wird
- Kostenpflichtige Pläne benötigt werden (Professional, Business, Enterprise)
- Maximale Zuverlässigkeit gegenüber neuesten Funktionen bevorzugt wird

**Edge wählen, wenn:**
- Neue Funktionen frühzeitig ausprobiert werden sollen
- Die Plattform evaluiert wird
- Großzügige kostenlose Limits für Nebenprojekte gewünscht werden
- Neuerer, weniger getesteter Code akzeptabel ist

## Installation

Die Installationsbefehle, Paketverwaltungskonfiguration und Docker-Tags für jeden Kanal finden sich unter [Installation](/de/docs/installation).

## CLI-Kanalverwaltung

Die CLI verwendet den Kanal, den Sie bei der Installation oder Anmeldung konfiguriert haben. So wechselt man:

```bash
rdc update --channel edge      # Zu Edge wechseln
rdc update --channel stable    # Zu Stable wechseln
```

Führen Sie `rdc subscription login` aus und wählen Sie eine Edge-Region, setzt die CLI den Edge-Update-Kanal automatisch für Sie. Kein `--channel`-Parameter erforderlich.
